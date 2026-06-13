# research_agent/agent.py
from google.adk.agents import SequentialAgent
from research_agent.agents.planner import planner_agent
from research_agent.agents.searcher import searcher_agent
from research_agent.agents.analyzer import analyzer_agent
from research_agent.agents.reasoner import reasoner_agent
from research_agent.agents.synthesizer import synthesizer_agent
from research_agent.agents.formatter import formatter_agent

# The main pipeline — runs agents in order
root_agent = SequentialAgent(
    name="research_pipeline",
    sub_agents=[
        planner_agent,
        searcher_agent,
        analyzer_agent,
        reasoner_agent,
        synthesizer_agent,
        formatter_agent,   # Converts JSON → readable markdown report
    ],
)
