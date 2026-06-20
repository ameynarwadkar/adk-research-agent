"""
FastAPI backend server that wraps the ADK Research Agent pipeline
and streams agent progress via Server-Sent Events (SSE).

Run with:
    uv run uvicorn server:app --host 0.0.0.0 --port 8080 --reload
"""
import asyncio
import json
import logging
import os
import traceback
import urllib.parse
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("adk_server")

# ─── Load research_agent/.env BEFORE ADK imports ───────────────
# (adk web does this automatically; uvicorn does not)
_env_path = Path(__file__).parent / "research_agent" / ".env"
if _env_path.exists():
    logger.info(f"Loading env from {_env_path}")
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from research_agent.agent import root_agent

# ─── App Setup ──────────────────────────────────────────────────
app = FastAPI(
    title="Research Agent API",
    description="Backend for the Research Agent frontend — streams pipeline progress via SSE",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── ADK Session & Runner ──────────────────────────────────────
APP_NAME = "research_agent_app"
session_service = InMemorySessionService()


def _create_runner() -> Runner:
    """Create a fresh ADK Runner."""
    return Runner(
        agent=root_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )


# ─── Agent ordering (matches your SequentialAgent pipeline) ─────
AGENT_ORDER = [
    "clarifier",
    "planner",
    "searcher",
    "analyzer",
    "reasoner",
    "synthesizer",
    "validator",
    "formatter",
]


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# ─── SSE Stream Endpoint ───────────────────────────────────────
@app.get("/api/research/stream")
async def stream_research(
    query: str = Query(..., description="The research question"),
    session_id: str = Query("", description="Optional session ID"),
):
    """
    Stream the research pipeline via SSE.

    Events emitted:
      - agent_start:        {agent: str}
      - agent_output:       {agent: str, text: str}
      - tool_call:          {agent: str, tool: str, args: dict}
      - agent_end:          {agent: str}
      - pipeline_complete:  {report: str}
      - error_event:        {message: str}
    """
    decoded_query = urllib.parse.unquote(query)
    logger.info(f"Starting research stream for: {decoded_query}")

    async def event_generator() -> AsyncGenerator[str, None]:
        runner = _create_runner()

        # Create a session for this run
        user_id = f"user_{session_id}" if session_id else "default_user"
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
        )

        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=decoded_query)],
        )

        current_agent = None
        report_text = ""

        try:
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=user_content,
            ):
                # Track which agent is producing events
                author = getattr(event, "author", None) or ""

                # Detect agent transitions
                if author and author != current_agent and author in AGENT_ORDER:
                    # End previous agent
                    if current_agent:
                        yield _sse_event("agent_end", {"agent": current_agent})

                    current_agent = author
                    yield _sse_event("agent_start", {"agent": current_agent})

                # Handle event content
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        # Function call (tool invocation)
                        if part.function_call:
                            yield _sse_event("tool_call", {
                                "agent": current_agent or author,
                                "tool": part.function_call.name,
                                "args": dict(part.function_call.args) if part.function_call.args else {},
                            })

                        # Function response — skip to reduce noise
                        elif part.function_response:
                            pass

                        # Text output
                        elif part.text:
                            yield _sse_event("agent_output", {
                                "agent": current_agent or author,
                                "text": part.text,
                            })

                            # Accumulate formatter output for final report
                            if current_agent == "formatter" or author == "formatter":
                                report_text += part.text

                # Yield control to keep connection alive
                await asyncio.sleep(0)

            # End the last agent
            if current_agent:
                yield _sse_event("agent_end", {"agent": current_agent})

            # If we didn't capture the report from streaming, try session state
            if not report_text:
                final_session = await session_service.get_session(
                    app_name=APP_NAME,
                    user_id=session.user_id,
                    session_id=session.id,
                )
                if final_session and final_session.state:
                    report_text = final_session.state.get("formatted_report", "")

            yield _sse_event("pipeline_complete", {"report": report_text})

        except Exception as e:
            traceback.print_exc()
            logger.error(f"Pipeline error: {e}")
            yield _sse_event("error_event", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Health Check ───────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok", "agents": AGENT_ORDER}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, log_level="info")
