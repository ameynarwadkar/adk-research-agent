# research_agent/retrylogic/breakers.py
from research_agent.retrylogic.circuit_breaker import CircuitBreaker

# Shared circuit breaker instances to maintain failure state across tool calls
pubmed_breaker = CircuitBreaker(name="PubMed", failure_threshold=5, recovery_timeout=60.0)
openalex_breaker = CircuitBreaker(name="OpenAlex", failure_threshold=5, recovery_timeout=60.0)
s2_breaker = CircuitBreaker(name="SemanticScholar", failure_threshold=5, recovery_timeout=60.0)
