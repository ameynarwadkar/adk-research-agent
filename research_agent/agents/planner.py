# research_agent/agents/planner.py
import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

planner_agent = LlmAgent(
    name="planner",
    model=LiteLlm(model=f"azure/{os.environ['AZURE_DEPLOYMENT_ID']}"),
    instruction="""You are a research planning assistant. Given a research question,
    produce search guidance: 3-5 search queries, year ranges, key terms,
    fields of study, and priorities (foundational vs. recent).""",
    output_key="search_guidance",  #  saved to session state
    # No tools - pure LLM reasoning
)
