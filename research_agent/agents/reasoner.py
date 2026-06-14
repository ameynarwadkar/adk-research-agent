# research_agent/agents/reasoner.py
from google.adk.agents import LlmAgent

reasoner_agent = LlmAgent(
    name="reasoner",
    model="gemini-2.5-flash",
    instruction="""You are an evidence quality assessor. Given:
    - Search results: {search_results}
    - Analysis: {analysis_results}

    Grade evidence quality, verify claims against abstracts,
    detect coverage gaps. If gaps exist, specify re-query suggestions.
    Output structured JSON with evidence_scores, claim_verifications, gaps.
    The original research question is available in the conversation above.""",
    output_key="reasoning_output",
)
