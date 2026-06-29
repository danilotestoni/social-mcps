from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _is_transient(exc: BaseException) -> bool:
    """Retry on 5xx/429 responses and low-level network errors. Never retry 4xx."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError))


def _is_transient_with_timeout(exc: BaseException) -> bool:
    """Like _is_transient but also retries on TimeoutException (for slow APIs like Threads)."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(
        exc,
        (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException),
    )


def _is_connection_only(exc: BaseException) -> bool:
    """Only retry if the request never reached the server (safe for non-idempotent writes)."""
    return isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))


def _retried(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception(_is_transient),
        reraise=True,
    )(func)


def _retried_with_timeout(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception(_is_transient_with_timeout),
        reraise=True,
    )(func)


def _retried_publish(func):
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        retry=retry_if_exception(_is_connection_only),
        reraise=True,
    )(func)
