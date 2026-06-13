"""Retry with exponential backoff and jitter.

Provides a decorator and utility function for retrying async operations that
may fail transiently (rate limits, network errors, etc.)
"""

from __future__ import annotations

import asyncio
import logging
import random
from functools import wraps
from typing import Any, Callable, TypeVar

from research_agent.retrylogic.exceptions import(
    ExternalAPIError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

class RetryConfig:
    """Configuration for retry behavior."""
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retry_on: tuple[type[Exception], ...] = (
            ExternalAPIError,
            RateLimitError,
            TimeoutError,
            ConnectionError,
        )
    )-> None:
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retry_on = retry_on

    def calculate_delay(self, attempt: int) -> float:
        """Exponential backoff with optional full jitter."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay = random.uniform(0, delay)
        return delay


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retry_on: tuple[type[Exception], ...] = (
        RateLimitError,
        ExternalAPIError,
    ),
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> Callable[[F], F]:
    """Decorator for retrying async functions with exponential backoff.

    Usage:
        @retry(max_attempts=3, retry_on=(RateLimitError,))
        async def call_api():
            ...
    """
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        jitter=jitter,
        retry_on=retry_on,
    )

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None

            for attempt in range(config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except config.retry_on as e:
                    last_exception = e

                    if attempt == config.max_attempts - 1:
                        logger.error(
                            "Retry exhausted for %s after %d attempts: %s",
                            func.__name__, config.max_attempts, e,
                        )
                        raise

                    if isinstance(e, RateLimitError) and e.retry_after is not None:
                        delay = e.retry_after
                    else:
                        delay = config.calculate_delay(attempt)

                    logger.warning(
                        "Retry %d/%d for %s: %s (delay: %.1fs)",
                        attempt + 1, config.max_attempts, func.__name__, e, delay,
                    )

                    if on_retry:
                        on_retry(attempt + 1, e, delay)

                    await asyncio.sleep(delay)

            if last_exception:
                raise last_exception
            raise RuntimeError("Retry logic error: no exception captured")

        return wrapper  # type: ignore[return-value]

    return decorator


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    config: RetryConfig | None = None,
    **kwargs: Any,
) -> Any:
    """Retry an async function call with the given config.

    Alternative to the decorator for one-off retries:
        result = await retry_async(api_call, query, config=RetryConfig(max_attempts=5))
    """
    config = config or RetryConfig()

    last_exception: Exception | None = None
    for attempt in range(config.max_attempts):
        try:
            return await func(*args, **kwargs)
        except config.retry_on as e:
            last_exception = e
            if attempt == config.max_attempts - 1:
                raise
            delay = config.calculate_delay(attempt)
            logger.warning(
                "Retry %d/%d: %s (delay: %.1fs)",
                attempt + 1, config.max_attempts, e, delay,
            )
            await asyncio.sleep(delay)

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")