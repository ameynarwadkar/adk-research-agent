# research_agent/agents/planner.py
from google.adk.agents import LlmAgent

planner_agent = LlmAgent(
    name="planner",
    model="gemini-2.5-flash",
    instruction="""You are a research planning assistant. Given a REFINED research question:
    {refined_query}
    
    produce search guidance: 3-5 search queries, year ranges, key terms,
    fields of study, and priorities (foundational vs. recent).""",
    output_key="search_guidance",  # saved to session state
    # No tools — pure LLM reasoning
)
