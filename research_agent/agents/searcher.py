# research_agent/agents/searcher.py
import os
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from research_agent.tools.arxiv_search import search_arxiv
from research_agent.tools.pubmed_search import search_pubmed
from research_agent.tools.openalex_search import search_openalex
from research_agent.tools.paper_filter import filter_papers
from research_agent.tools.paper_ranker import rank_papers
from research_agent.tools.abstract_extractor import extract_abstracts
from research_agent.tools.citation_traversal import traverse_citations

searcher_agent = LlmAgent(
    name="searcher",
    model=LiteLlm(model=f"azure/{os.environ['AZURE_DEPLOYMENT_ID']}"),
    instruction="""You are a research paper searcher. Use the search guidance provided below
to find relevant academic papers.

Search guidance from planner:
{search_guidance}

Your job:
1. Use search_arxiv and search_pubmed with multiple queries derived from the guidance
2. Use search_openalex for broader interdisciplinary coverage (it indexes 250M+ works)
3. Use filter_papers to narrow down results by year, keywords, etc.
4. Use rank_papers to prioritize the most relevant papers
5. Use extract_abstracts to prepare a digest of the top papers
6. Optionally use traverse_citations to find related work via citation graph

Be thorough — run at least 3 different search queries across ArXiv, PubMed, and OpenAlex.
Aim to collect 15-30 relevant papers before finishing.

Provide a comprehensive summary of what you found, organized by sub-topic.""",
    tools=[search_arxiv, search_pubmed, search_openalex, filter_papers,
           rank_papers, extract_abstracts, traverse_citations],
    output_key="search_results",
)