from __future__ import annotations

import asyncio
import concurrent.futures
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union, Awaitable, cast
import logging

import pybreaker
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError, retry_if_exception_type, AsyncRetrying, Retrying, retry_if_exception
from app.utils import getenv_int, getenv_float

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger("connectors.external_call")


class ExternalCallError(Exception):
    """Raised when an external call ultimately fails after retries/breaker."""


# Global stability policy settings (single place)
MAX_ATTEMPTS = getenv_int("CONNECTOR_MAX_ATTEMPTS", 3)
INITIAL_BACKOFF = getenv_float("CONNECTOR_INITIAL_BACKOFF", 0.2)  # seconds
MAX_BACKOFF = getenv_float("CONNECTOR_MAX_BACKOFF", 2.0)  # seconds
TIMEOUT_SECONDS = getenv_float("CONNECTOR_TIMEOUT_SECONDS", 5.0)

# Circuit breaker configuration
BREAKER_FAIL_MAX = getenv_int("CONNECTOR_BREAKER_FAIL_MAX", 5)
BREAKER_RESET_TIMEOUT = getenv_int("CONNECTOR_BREAKER_RESET_TIMEOUT", 30)  # seconds

# Single, shared breaker instance to protect the external dependencies
external_breaker = pybreaker.CircuitBreaker(
    fail_max=BREAKER_FAIL_MAX,
    reset_timeout=BREAKER_RESET_TIMEOUT,
    name="external_calls_breaker",
)


def _with_timeout_sync(fn: Callable[..., Any], timeout: float) -> Callable[..., Any]:
    @wraps(fn)
    def _inner(*args: Any, **kwargs: Any) -> Any:
        # Run fn in a separate thread and wait with a timeout so we raise during execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, *args, **kwargs)
            try:
                return future.result(timeout=timeout)
            except concurrent.futures.TimeoutError as e:
                # Attempt to cancel; note this won't stop CPU-bound/C-extension blocking calls
                future.cancel()
                raise TimeoutError(f"External call exceeded timeout {timeout}s") from e
    return _inner


async def _with_timeout_async(afn: Callable[..., Awaitable[Any]], timeout: float, *args: Any, **kwargs: Any) -> Any:
    return await asyncio.wait_for(afn(*args, **kwargs), timeout=timeout)


def external_call(
    *,
    timeout: Optional[float] = None,
    max_attempts: Optional[int] = None,
    initial_backoff: Optional[float] = None,
    max_backoff: Optional[float] = None,
    breaker: Optional[pybreaker.CircuitBreaker] = None,
    retry_on: Union[type[BaseException], tuple[type[BaseException], ...]] = (Exception,),
) -> Callable[[F], F]:
    """
    Common decorator to wrap any external operation with stability policy:
    - Circuit breaker (pybreaker)
    - Retries with exponential backoff (tenacity)
    - Timeout for each attempt (async and sync supported)

    Usage:
    @external_call()
    def call_service(...):
        ...

    @external_call(timeout=2.0)
    async def fetch_async(...):
        ...
    """

    t = TIMEOUT_SECONDS if timeout is None else timeout
    attempts = MAX_ATTEMPTS if max_attempts is None else max_attempts
    backoff_start = INITIAL_BACKOFF if initial_backoff is None else initial_backoff
    backoff_max = MAX_BACKOFF if max_backoff is None else max_backoff
    used_breaker: pybreaker.CircuitBreaker = external_breaker if breaker is None else breaker

    def decorator(func: F) -> F:
        is_async = asyncio.iscoroutinefunction(func)

        if is_async:
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async def attempt() -> Any:
                    # timeout per attempt
                    return await _with_timeout_async(cast(Callable[..., Awaitable[Any]], func), t, *args, **kwargs)

                # Breaker protected, with retries
                async def run_with_policies() -> Any:
                    # Use breaker context manager to handle open/half-open/closed accounting
                    # and to ensure CircuitBreakerError is raised immediately when open.
                    # Retries will not count as separate successes; breaker handles success/failure once per attempt.
                    pass  # placeholder to keep structure; context used below
                    try:
                        # Build retry predicate that excludes CircuitBreakerError
                        retry_types = retry_on if isinstance(retry_on, tuple) else (retry_on,)
                        retry_pred = retry_if_exception(lambda e: isinstance(e, retry_types) and not isinstance(e, pybreaker.CircuitBreakerError))
                        async for retry_state in AsyncRetrying(
                            stop=stop_after_attempt(attempts),
                            wait=wait_exponential(multiplier=backoff_start, max=backoff_max),
                            retry=retry_pred,
                            reraise=True,
                        ):
                            attempt_number = retry_state.retry_state.attempt_number
                            if attempt_number == 1:
                                logger.debug("external_call: starting async attempt 1 (timeout=%ss, max_attempts=%s, backoff_start=%ss, backoff_max=%ss, breaker_state=%s)", t, attempts, backoff_start, backoff_max, used_breaker.current_state)
                            else:
                                logger.debug("external_call: retrying async attempt %s after backoff (breaker_state=%s)", attempt_number, used_breaker.current_state)
                            with retry_state:
                                try:
                                    with used_breaker.calling():
                                        result = await attempt()
                                    logger.debug("external_call: async attempt %s succeeded", attempt_number)
                                    return result
                                except pybreaker.CircuitBreakerError:
                                    logger.debug("external_call: breaker open on async attempt %s", attempt_number)
                                    raise
                                except Exception as e:
                                    logger.debug("external_call: async attempt %s failed with %s: %s", attempt_number, type(e).__name__, e)
                                    raise
                    except pybreaker.CircuitBreakerError:
                        raise
                    except Exception:
                        # Breaker accounting is handled by the context manager.
                        raise

                try:
                    result = await run_with_policies()
                    return result
                except RetryError as re:
                    logger.debug("external_call: async exhausted after %s attempts; last error: %s", attempts, re)
                    # Unwrap for clearer error
                    raise ExternalCallError(f"External async call failed after {attempts} attempts: {re}") from re

            return cast(F, async_wrapper)
        else:
            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                def attempt() -> Any:
                    wrapped = _with_timeout_sync(cast(Callable[..., Any], func), t)
                    return wrapped(*args, **kwargs)

                def run_with_policies() -> Any:
                    try:
                        # Build retry predicate that excludes CircuitBreakerError
                        retry_types = retry_on if isinstance(retry_on, tuple) else (retry_on,)
                        retry_pred = retry_if_exception(lambda e: isinstance(e, retry_types) and not isinstance(e, pybreaker.CircuitBreakerError))
                        for retry_state in Retrying(
                            stop=stop_after_attempt(attempts),
                            wait=wait_exponential(multiplier=backoff_start, max=backoff_max),
                            retry=retry_pred,
                            reraise=True,
                        ):
                            attempt_number = retry_state.retry_state.attempt_number
                            if attempt_number == 1:
                                logger.debug("external_call: starting sync attempt 1 (timeout=%ss, max_attempts=%s, backoff_start=%ss, backoff_max=%ss, breaker_state=%s)", t, attempts, backoff_start, backoff_max, used_breaker.current_state)
                            else:
                                logger.debug("external_call: retrying sync attempt %s after backoff (breaker_state=%s)", attempt_number, used_breaker.current_state)
                            with retry_state:
                                try:
                                    with used_breaker.calling():
                                        result = attempt()
                                    logger.debug("external_call: sync attempt %s succeeded", attempt_number)
                                    return result
                                except pybreaker.CircuitBreakerError:
                                    logger.debug("external_call: breaker open on sync attempt %s", attempt_number)
                                    raise
                                except Exception as e:
                                    logger.debug("external_call: sync attempt %s failed with %s: %s", attempt_number, type(e).__name__, e)
                                    raise
                    except pybreaker.CircuitBreakerError:
                        raise
                    except Exception:
                        # Breaker accounting is handled by the context manager.
                        raise

                try:
                    result = run_with_policies()
                    return result
                except RetryError as re:
                    logger.debug("external_call: sync exhausted after %s attempts; last error: %s", attempts, re)
                    raise ExternalCallError(f"External sync call failed after {attempts} attempts: {re}") from re

            return cast(F, sync_wrapper)

    return decorator
