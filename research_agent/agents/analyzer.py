# research_agent/agents/analyzer.py
from google.adk.agents import LlmAgent
from research_agent.tools.paper_filter import filter_papers
from research_agent.tools.abstract_extractor import extract_abstracts

analyzer_agent = LlmAgent(
    name="analyzer",
    model="gemini-2.0-flash",
    instruction="""You are a research analyzer. Given the search results below, perform
a thematic analysis of the papers found.

Search results:
{search_results}

Your job:
1. Use extract_abstracts if you need to dig into specific paper details
2. Use filter_papers to focus on subsets (e.g. by year range or keywords)
3. Identify 3-6 thematic clusters across the papers
4. For each theme, extract specific findings with confidence levels:
   - strong: multiple papers with consistent empirical evidence
   - moderate: some supporting evidence but limited replication
   - weak: single paper or theoretical claim only
5. Note methodology patterns (empirical, survey, theoretical, etc.)

Output a structured analysis organized by theme, with specific paper IDs
cited for each finding.""",
    tools=[filter_papers, extract_abstracts],
    output_key="analysis_results",
)