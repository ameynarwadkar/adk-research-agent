# Research Agent

A multi-agent research assistant built with [Google ADK](https://google.github.io/adk-docs/) that automatically searches academic databases, analyzes papers, assesses evidence quality, and produces a formatted literature review - given a single research question.



## What It Does

You type a research question. The pipeline does the rest:

1. Plans targeted search strategies
2. Searches ArXiv + PubMed + OpenAlex
3. Analyzes themes and clusters findings
4. Assesses evidence quality and detects gaps
5. Synthesizes results into a structured review
6. Formats the output as a clean markdown report



## Agent Pipeline

![Agent Pipeline Graph](research_agent/screenshots/1.png)

### Tools (currently available to agents)

| Tool | Used by | Description |
|---|---|---|
| `search_arxiv` | Searcher | Queries ArXiv via the `arxiv` Python library |
| `search_pubmed` | Searcher | Queries PubMed via NCBI E-utilities (esearch + efetch) |
| `search_openalex` | Searcher | Queries OpenAlex (250M+ works, no API key required) |
| `filter_papers` | Searcher, Analyzer | Filters by year, citation count, keywords, open access |
| `rank_papers` | Searcher | Sorts papers by citations, year, or title |
| `extract_abstracts` | Searcher, Analyzer | Batches abstracts + metadata for downstream agents |
| `traverse_citations` | Searcher | Forward/backward citation traversal via Semantic Scholar |

---

## Project Structure

```
adk-agent/
├── research_agent/
│   ├── agent.py              # Main SequentialAgent - wires the pipeline
│   ├── agents/
│   │   ├── planner.py
│   │   ├── searcher.py
│   │   ├── analyzer.py
│   │   ├── reasoner.py
│   │   ├── synthesizer.py
│   │   └── formatter.py
│   ├── tools/
│   │   ├── arxiv_search.py
│   │   ├── pubmed_search.py
│   │   ├── paper_filter.py
│   │   ├── paper_ranker.py
│   │   ├── abstract_extractor.py
│   │   └── citation_traversal.py
│   ├── models/
│   │   └── paper.py          # Shared Paper / Author / PaperCollection models
│   └── retrylogic/
│       ├── retry.py          # Decorator + retry_async
│       ├── circuit_breaker.py  # Circuit Breaker
│       └── exceptions.py     # Exceptions
├── pyproject.toml
└── README.md
```



## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- A **Google Cloud project** with Vertex AI enabled
- [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) (`gcloud`)

### 1. Clone and install

```bash
git clone https://github.com/ameynarwadkar/adk-research-agent.git
cd adk-research-agent

uv sync
```

### 2. Authenticate with Google Cloud

```bash
# One-time login (sets Application Default Credentials)
gcloud auth application-default login

# Set your project
gcloud config set project YOUR_PROJECT_ID
```

### 3. Configure environment

Create `research_agent/.env`:

```bash
cp research_agent/.env.example research_agent/.env
```

Edit the `.env` file and replace the placeholder values with your actual values:

```env
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

### 4. Run

```bash
adk web research_agent
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

## Test it yourself!
### Example Prompt

```
Does intermittent fasting improve metabolic health markers (blood glucose,
insulin sensitivity, BMI) in adults with type 2 diabetes compared to
continuous caloric restriction?

Population: Adults (18+) with type 2 diabetes
Geography: Global
Method: RCTs and systematic reviews preferred
Time range: 2015–2025
```

### Example output (truncated)

```markdown
# Literature Review: Does intermittent fasting improve metabolic health...

## Overview
This review synthesizes evidence from 3 systematic reviews/meta-analyses and
1 primary RCT identified across PubMed...

## Evidence by Outcome

### Blood Glucose / HbA1c
- **Finding**: IF/TRE generally improves glycaemic markers versus control,
  with effects strongest in the short term.
- **Strength**: Moderate–Strong
> "IF significantly decreased HbA1c ... in the short term compared to
>  control interventions." (PMID:40367729)

## Bottom Line
Evidence from multiple meta-analyses supports short-term glycaemic benefits
of intermittent fasting in adults with type 2 diabetes...
```


## Architecture Notes

- All agents share session state via ADK's built-in session mechanism. Each agent writes its output to a named key (`search_guidance`, `search_results`, etc.) which downstream agents read via `{variable}` template substitution in instructions.
- The `retrylogic` package provides an `@retry` decorator with exponential backoff + jitter and a `CircuitBreaker` context manager for protecting external API calls (ArXiv, PubMed, Semantic Scholar).
- The `Paper` Pydantic model is the shared data contract between all tools and agents and every tool returns `Paper.model_dump()` dicts for consistent serialisation.
- Models are specified as plain strings (`"gemini-2.0-flash"`); ADK handles authentication automatically via Application Default Credentials.


## Dependencies

| Package | Purpose |
|---|---|
| `google-adk >= 2.2.0` | Agent framework, SequentialAgent, LlmAgent, tools |
| `pydantic >= 2.0` | Data models (Paper, Author, PaperCollection) |
| `httpx >= 0.27` | HTTP client for PubMed + Semantic Scholar |
| `arxiv >= 4.0.0` | ArXiv search library |
