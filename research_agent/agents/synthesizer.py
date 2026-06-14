# research_agent/agents/synthesizer.py
from google.adk.agents import LlmAgent

synthesizer_agent = LlmAgent(
    name="synthesizer",
    model="gemini-2.5-flash",
    instruction="""You are an expert academic researcher. Review all prior agent outputs
in this conversation — search results, thematic analysis, and evidence assessment.

Write a structured literature mini-review as JSON with the following schema:
{
  "research_question": "...",
  "population": "...",
  "methods_covered": ["RCT", "meta-analysis", ...],
  "evidence_summary_by_outcome": [
    {
      "outcome": "...",
      "finding": "...",
      "evidence_source_pmids": ["PMID:...", ...],
      "evidence_excerpts": [
        {"paper_id": "...", "excerpt": "..."}
      ]
    }
  ],
  "primary_trials": [
    {"paper_id": "...", "design": "...", "intervention": "...", "comparator": "...", "key_result": "..."}
  ],
  "systematic_reviews": [
    {"paper_id": "...", "scope": "...", "key_finding": "..."}
  ],
  "limitations": ["...", "..."],
  "bottom_line": "..."
}

Rules:
- Use ONLY paper IDs that appear in the search results above
- Include at least one evidence_excerpt per outcome finding
- Do NOT invent PMIDs or paper IDs""",
    output_key="final_review",
)
