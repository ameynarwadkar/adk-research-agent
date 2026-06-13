# research_agent/agents/synthesizer.py
import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

synthesizer_agent = LlmAgent(
    name="synthesizer",
    model=LiteLlm(model=f"azure/{os.environ['AZURE_DEPLOYMENT_ID']}"),
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
