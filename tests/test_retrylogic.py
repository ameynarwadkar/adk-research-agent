"""Tests for retrylogic — exceptions, RetryConfig, retry decorator, CircuitBreaker."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from research_agent.retrylogic.exceptions import (
    CircuitBreakerOpen,
    ExternalAPIError,
    RateLimitError,
    ResearchAgentError,
)
from research_agent.retrylogic.retry import RetryConfig, retry, retry_async
from research_agent.retrylogic.circuit_breaker import CircuitBreaker, CircuitState


# ── Exception hierarchy ───────────────────────────────────────────────────

class TestExceptions:
    def test_external_api_error_is_research_agent_error(self):
        err = ExternalAPIError("oops")
        assert isinstance(err, ResearchAgentError)
        assert str(err) == "oops"

    def test_external_api_error_fields(self):
        err = ExternalAPIError("bad gateway", status_code=502, service_name="PubMed")
        assert err.status_code == 502
        assert err.service_name == "PubMed"

    def test_rate_limit_error_inherits_external_api(self):
        err = RateLimitError(retry_after=30)
        assert isinstance(err, ExternalAPIError)
        assert err.retry_after == 30

    def test_circuit_breaker_open_message(self):
        err = CircuitBreakerOpen("ArXiv")
        assert "ArXiv" in str(err)
        assert err.service_name == "ArXiv"


# ── RetryConfig ───────────────────────────────────────────────────────────

class TestRetryConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_attempts == 3
        assert cfg.base_delay == 1.0
        assert cfg.max_delay == 30.0
        assert cfg.exponential_base == 2.0
        assert cfg.jitter is True

    def test_calculate_delay_without_jitter(self):
        cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, jitter=False)
        # attempt 0 → 1.0 * 2^0 = 1.0
        assert cfg.calculate_delay(0) == pytest.approx(1.0)
        # attempt 1 → 1.0 * 2^1 = 2.0
        assert cfg.calculate_delay(1) == pytest.approx(2.0)
        # attempt 2 → 1.0 * 2^2 = 4.0
        assert cfg.calculate_delay(2) == pytest.approx(4.0)

    def test_calculate_delay_capped_at_max_delay(self):
        cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=5.0, jitter=False)
        # attempt 10 → 1.0 * 2^10 = 1024, but capped at 5.0
        assert cfg.calculate_delay(10) == pytest.approx(5.0)

    def test_calculate_delay_with_jitter_is_random(self):
        cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=30.0, jitter=True)
        delay = cfg.calculate_delay(2)  # max without jitter = 4.0
        assert 0 <= delay <= 4.0


# ── @retry decorator ──────────────────────────────────────────────────────

class TestRetryDecorator:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        call_count = 0

        @retry(max_attempts=3)
        async def success_func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await success_func()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        call_count = 0

        @retry(
            max_attempts=3,
            base_delay=0,
            retry_on=(ExternalAPIError,),
        )
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ExternalAPIError("transient")
            return "recovered"

        result = await flaky_func()
        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_attempts(self):
        @retry(
            max_attempts=2,
            base_delay=0,
            retry_on=(ExternalAPIError,),
        )
        async def always_fails():
            raise ExternalAPIError("permanent")

        with pytest.raises(ExternalAPIError, match="permanent"):
            await always_fails()

    @pytest.mark.asyncio
    async def test_non_retryable_exception_propagates_immediately(self):
        call_count = 0

        @retry(max_attempts=3, retry_on=(ExternalAPIError,))
        async def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError):
            await raises_value_error()
        assert call_count == 1  # no retry

    @pytest.mark.asyncio
    async def test_rate_limit_error_uses_retry_after(self):
        """When RateLimitError has retry_after, that value should be used as delay."""
        delays_used = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            delays_used.append(delay)

        call_count = 0

        @retry(
            max_attempts=3,
            base_delay=999,  # would use this if not for retry_after
            retry_on=(RateLimitError,),
        )
        async def rate_limited():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError(retry_after=5)
            return "ok"

        import unittest.mock
        with unittest.mock.patch("research_agent.retrylogic.retry.asyncio.sleep", mock_sleep):
            result = await rate_limited()

        assert result == "ok"
        assert delays_used[0] == 5  # retry_after value, not base_delay


# ── retry_async utility ───────────────────────────────────────────────────

class TestRetryAsync:
    @pytest.mark.asyncio
    async def test_success(self):
        async def fn(x):
            return x * 2

        result = await retry_async(fn, 21, config=RetryConfig(max_attempts=1))
        assert result == 42

    @pytest.mark.asyncio
    async def test_raises_after_exhausting(self):
        async def always_fails():
            raise ExternalAPIError("boom")

        cfg = RetryConfig(max_attempts=2, base_delay=0, retry_on=(ExternalAPIError,))
        with pytest.raises(ExternalAPIError):
            await retry_async(always_fails, config=cfg)


# ── CircuitBreaker ────────────────────────────────────────────────────────

class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initially_closed(self):
        breaker = CircuitBreaker(name="test", failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_successful_calls_stay_closed(self):
        breaker = CircuitBreaker(name="test", failure_threshold=2)
        for _ in range(5):
            async with breaker:
                pass  # no exception
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self):
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=2,
            expected_exceptions=(ExternalAPIError,),
        )
        for _ in range(2):
            try:
                async with breaker:
                    raise ExternalAPIError("fail")
            except ExternalAPIError:
                pass

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_circuit_raises_immediately(self):
        breaker = CircuitBreaker(name="test", failure_threshold=1)
        try:
            async with breaker:
                raise ExternalAPIError("fail")
        except ExternalAPIError:
            pass

        with pytest.raises(CircuitBreakerOpen):
            async with breaker:
                pass  # should not reach here

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self, monkeypatch):
        breaker = CircuitBreaker(
            name="test",
            failure_threshold=1,
            recovery_timeout=0.01,
            expected_exceptions=(ExternalAPIError,),
        )
        try:
            async with breaker:
                raise ExternalAPIError("fail")
        except ExternalAPIError:
            pass

        # Fast-forward past recovery_timeout
        monkeypatch.setattr(
            "research_agent.retrylogic.circuit_breaker.time.time",
            lambda: breaker._last_failure_time + 1.0,
        )
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_reset_clears_state(self):
        breaker = CircuitBreaker(name="test", failure_threshold=1)
        try:
            async with breaker:
                raise ExternalAPIError("fail")
        except ExternalAPIError:
            pass

        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker._failure_count == 0
