"""Circuit breaker pattern for external service calls.

States:
  CLOSED   → Normal operation. Failures are counted.
  OPEN     → Service is considered down. Calls fail immediately.
  HALF_OPEN → After recovery_timeout, one test call is allowed through.
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable

from research_agent.retrylogic.exceptions import CircuitBreakerOpen, ExternalAPIError

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Async circuit breaker for protecting external service calls.

    Usage:
        breaker = CircuitBreaker(name="pubmed", failure_threshold=5)

        async with breaker:
            result = await call_api()
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exceptions: tuple[type[Exception], ...] = (ExternalAPIError,),
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._success_count = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    async def __aenter__(self) -> CircuitBreaker:
        await self._before_call()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        if exc_type is None:
            await self._on_success()
        elif exc_type and issubclass(exc_type, self.expected_exceptions):
            await self._on_failure()
        return False

    async def _before_call(self) -> None:
        current_state = self.state
        if current_state == CircuitState.OPEN:
            raise CircuitBreakerOpen(self.name)
        if current_state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker '%s' HALF_OPEN — allowing test call", self.name)

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("Circuit breaker '%s' recovered → CLOSED", self.name)
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count += 1

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker '%s' test failed → OPEN", self.name)
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker '%s' tripped OPEN after %d failures",
                    self.name, self._failure_count,
                )

    def reset(self) -> None:
        """Manually reset to CLOSED."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0