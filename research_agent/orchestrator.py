import uuid
from google.adk import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai.types import Content, Part
from langfuse.decorators import observe

from research_agent.agents.clarifier import clarifier_agent
from research_agent.agents.planner import planner_agent
from research_agent.agents.searcher import searcher_agent
from research_agent.agents.analyzer import analyzer_agent
from research_agent.agents.reasoner import reasoner_agent
from research_agent.agents.synthesizer import synthesizer_agent
from research_agent.agents.formatter import formatter_agent

# Initialize a global session service for the app
session_service = InMemorySessionService()

@observe(as_type="generation")
async def run_agent(agent, session_id: str, message: str = "") -> str:
    """Helper to run a single ADK agent programmatically and return its text output."""
    runner = Runner(
        agent=agent, 
        session_service=session_service, 
        app_name="research_pipeline",
        auto_create_session=True
    )
    
    parts = []
    if message:
        parts.append(Part.from_text(text=message))
    else:
        # ADK requires a new message even if the agent just reads from state
        parts.append(Part.from_text(text="Proceed to the next step based on the current context."))
        
    async_gen = runner.run_async(
        user_id="api_user",
        session_id=session_id,
        new_message=Content(role="user", parts=parts)
    )
    
    output = ""
    async for event in async_gen:
        text = getattr(event, "content", None)
        if not text and hasattr(event, "data"):
            text = getattr(event.data, "content", None)
        if text:
            output += text
             
    return output

@observe()
async def run_pipeline(question: str) -> str:
    """
    Phase 2 Orchestrator: runs the agents procedurally.
    This replaces the ADK SequentialAgent to allow loops and conditionals.
    """
    session_id = str(uuid.uuid4())
    
    # 1. Clarifier (takes the user question)
    await run_agent(clarifier_agent, session_id, message=question)
    
    # 2. Planner
    await run_agent(planner_agent, session_id)
    
    # Re-query loop implementation (Phase 3)
    MAX_REQUERY = 2
    for iteration in range(MAX_REQUERY + 1):
        # 3. Searcher
        await run_agent(searcher_agent, session_id)
        
        # 4. Analyzer
        await run_agent(analyzer_agent, session_id)
        
        # 5. Reasoner
        reasoning_output_str = await run_agent(reasoner_agent, session_id)
        
        # Parse reasoning output
        try:
            import json
            from research_agent.models.reasoning import ReasonerOutput
            
            # Extract JSON block if surrounded by markdown
            if "```json" in reasoning_output_str:
                reasoning_json = reasoning_output_str.split("```json")[1].split("```")[0].strip()
            elif "```" in reasoning_output_str:
                reasoning_json = reasoning_output_str.split("```")[1].strip()
            else:
                reasoning_json = reasoning_output_str.strip()
                
            reasoner_output = ReasonerOutput.model_validate_json(reasoning_json)
            
            # If we have gaps and haven't exceeded MAX_REQUERY, we loop back
            if reasoner_output.has_gaps and iteration < MAX_REQUERY:
                # We can inject the re-query guidance into the session state or message
                if reasoner_output.re_query_request:
                    requery_msg = f"ADDITIONAL SEARCH ITERATION. Fill these gaps: {reasoner_output.re_query_request.reason}. Queries to try: {', '.join(reasoner_output.re_query_request.queries)}"
                    await run_agent(searcher_agent, session_id, message=requery_msg)
                    continue
            
            # No gaps or max iterations reached, break to synthesize
            break
            
        except Exception as e:
            print(f"Failed to parse ReasonerOutput: {e}")
            break # Proceed to synthesis if parsing fails
        
    # 6. Synthesizer
    await run_agent(synthesizer_agent, session_id)
    
    # 7. Formatter
    final_output = await run_agent(formatter_agent, session_id)
    
    return final_output
