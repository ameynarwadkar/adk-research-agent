# research_agent/agents/reasoner.py
import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

reasoner_agent = LlmAgent(
    name="reasoner",
    model=LiteLlm(model=f"azure/{os.environ['AZURE_DEPLOYMENT_ID']}"),
    instruction="""You are an evidence quality assessor. Given:
    - Search results: {search_results}
    - Analysis: {analysis_results}

    Grade evidence quality, verify claims against abstracts,
    detect coverage gaps. If gaps exist, specify re-query suggestions.
    Output structured JSON with evidence_scores, claim_verifications, gaps.
    The original research question is available in the conversation above.""",
    output_key="reasoning_output",
)
