"""
Custom Exception for the retry logic layer.

Only includes the exception relevant to the external API calls and retries.
Agent-level exceptions are handled by ADK.
"""

from __future__ import annotations

class ResearchAgentError(Exception):
    """Base exception for all research agent errors."""
    pass

class ExternalAPIError(ResearchAgentError):
    """Exception for errors calling external APIs (Arxiv, PubMed, etc.).
    
    Attributes:
        status_code: HTTP status code, if availble.
        service_name: Name of the external service.
    """
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        service_name: str = "Unknown Service",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.service_name = service_name

class RateLimitError(ExternalAPIError):
    """Rate limited by an External API - caller should back off.
    
    Attributes:
        retry_after: Seconds to wait before retrying, if provided by the API.
    """
    def __init__(
        self,
        message: str = "Rate Limited",
        service_name: str = "Unknown Service",
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, service_name)
        self.retry_after = retry_after
        

class CircuitBreakerOpen(ResearchAgentError):
    """Circuit Breaker is open - do not call external service."""
    def __init__(self, service_name: str) -> None:
        super().__init__(f"Circuit Breaker is open for {service_name}. Do not call external service.")
        self.service_name = service_name