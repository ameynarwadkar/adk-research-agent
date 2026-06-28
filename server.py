"""
FastAPI backend server that wraps the ADK Research Agent pipeline
and streams agent progress via Server-Sent Events (SSE).

Run with:
    uv run uvicorn server:app --host 0.0.0.0 --port 8080 --reload
"""
import asyncio
from contextlib import asynccontextmanager
import json
import logging
import os
import time
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
from research_agent import initialize_logging
from research_agent.agent import root_agent

# ─── App Setup ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_logging()
    logger.info("FastAPI application started, logger re-initialized.")
    yield

app = FastAPI(
    title="Research Agent API",
    description="Backend for the Research Agent frontend — streams pipeline progress via SSE",
    version="0.1.0",
    lifespan=lifespan,
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

        logger.info(
            "Initializing research session. Query: '%s' | User ID: %s | Session ID: %s",
            decoded_query, user_id, session.id
        )

        user_content = types.Content(
            role="user",
            parts=[types.Part.from_text(text=decoded_query)],
        )

        current_agent = None
        report_text = ""
        agent_outputs = {agent_name: [] for agent_name in AGENT_ORDER}

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
                        logger.info("<<< Agent ended: %s", current_agent)
                        yield _sse_event("agent_end", {"agent": current_agent})

                    current_agent = author
                    logger.info(">>> Agent started: %s", current_agent)
                    yield _sse_event("agent_start", {"agent": current_agent})

                # Handle event content
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        # Function call (tool invocation)
                        if part.function_call:
                            tool_name = part.function_call.name
                            tool_args = dict(part.function_call.args) if part.function_call.args else {}
                            logger.info(
                                "Agent '%s' invoking tool: %s with args %s",
                                current_agent or author, tool_name, tool_args
                            )
                            yield _sse_event("tool_call", {
                                "agent": current_agent or author,
                                "tool": tool_name,
                                "args": tool_args,
                            })

                        # Function response — skip to reduce noise
                        elif part.function_response:
                            pass

                        # Text output
                        elif part.text:
                            snippet = part.text.strip().replace("\n", " ")
                            if len(snippet) > 80:
                                snippet = snippet[:80] + "..."
                            logger.info(
                                "Agent '%s' output chunk: %s",
                                current_agent or author, snippet
                            )
                            yield _sse_event("agent_output", {
                                "agent": current_agent or author,
                                "text": part.text,
                            })

                            # Accumulate outputs for each agent step
                            agent_key = current_agent or author
                            if agent_key in agent_outputs:
                                agent_outputs[agent_key].append(part.text)

                            # Accumulate formatter output for final report
                            if current_agent == "formatter" or author == "formatter":
                                report_text += part.text

                # Yield control to keep connection alive
                await asyncio.sleep(0)

            # End the last agent
            if current_agent:
                logger.info("<<< Agent ended: %s", current_agent)
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

            logger.info(
                "Pipeline execution complete. Report generated successfully (%d characters).",
                len(report_text)
            )
            save_agent_outputs(session.id, agent_outputs, decoded_query)
            yield _sse_event("pipeline_complete", {"report": report_text})

        except Exception as e:
            logger.error(
                "Fatal error encountered in research pipeline: %s\n%s",
                e, traceback.format_exc()
            )
            try:
                save_agent_outputs(session.id, agent_outputs, decoded_query)
            except Exception as save_err:
                logger.error("Failed to save partial agent outputs: %s", save_err)
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


def save_agent_outputs(session_id: str, agent_outputs: dict[str, list[str]], query: str) -> None:
    """Save the text output of each agent/step to outputs/session_{session_id}/ in Markdown format."""
    outputs_dir = Path(__file__).parent / "outputs" / f"session_{session_id}"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Saving agent step outputs to directory: %s", outputs_dir)

    # Write a summary metadata index file
    meta_file = outputs_dir / "00_metadata.md"
    try:
        with open(meta_file, "w", encoding="utf-8") as f:
            f.write(f"# Research Session Metadata\n\n")
            f.write(f"- **Session ID**: `{session_id}`\n")
            f.write(f"- **Research Query**: {query}\n")
            f.write(f"- **Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        logger.info("Saved metadata index file: %s", meta_file)
    except Exception as e:
        logger.error("Failed to write metadata index file: %s", e)

    # Write each agent's accumulated output
    for idx, agent_name in enumerate(AGENT_ORDER, 1):
        content = "".join(agent_outputs.get(agent_name, []))
        if not content:
            content = f"*No direct text output was recorded for agent '{agent_name}'.*\n"
        
        agent_file = outputs_dir / f"{idx:02d}_{agent_name}.md"
        try:
            with open(agent_file, "w", encoding="utf-8") as f:
                f.write(f"# Step {idx}: {agent_name.capitalize()}\n\n")
                f.write(content)
                f.write("\n")
            logger.info("Saved step output: %s (%d chars)", agent_file.name, len(content))
        except Exception as e:
            logger.error("Failed to write step output for agent '%s': %s", agent_name, e)


# ─── Health Check ───────────────────────────────────────────────
@app.get("/api/health")
async def health():
    logger.info("Health check endpoint queried.")
    return {"status": "ok", "agents": AGENT_ORDER}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, log_level="info")
