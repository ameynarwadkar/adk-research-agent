# research_agent/agents/synthesizer.py
from google.adk.agents import LlmAgent

synthesizer_agent = LlmAgent(
    name="synthesizer",
    model="gemini-2.0-flash",
    instruction="""You are an expert academic researcher. Given:
    - Research question: (see original question in the conversation above)
    - Search results: {search_results}
    - Analysis: {analysis_results}
    - Evidence assessment: {reasoning_output}

    Write a structured literature mini-review as JSON matching the
    LiteratureReview schema. Use ONLY paper IDs from the search results.
    Include evidence_excerpts for every finding.""",
    output_key="final_review",
)
