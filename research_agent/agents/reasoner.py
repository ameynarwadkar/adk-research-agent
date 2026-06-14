# research_agent/agents/reasoner.py
from google.adk.agents import LlmAgent

reasoner_agent = LlmAgent(
    name="reasoner",
    model="gemini-2.5-flash",
    instruction="""You are an evidence quality assessor. Review the search results
and thematic analysis provided by the previous agents in this conversation.

Your job:
- Grade evidence quality for each finding
- Verify claims against the paper abstracts
- Detect coverage gaps in the literature
- If gaps exist, specify re-query suggestions

Output structured JSON with:
  - evidence_scores: per-finding quality scores (strong/moderate/weak)
  - claim_verifications: each claim verified or flagged as unsupported
  - gaps: topics or populations not adequately covered
  - requery_suggestions: additional search queries if gaps exist

The original research question is available in the conversation above.""",
    output_key="reasoning_output",
)
