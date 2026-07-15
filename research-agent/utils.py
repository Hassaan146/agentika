"""Small shared helpers."""

import time

import httpx

from config import settings

# Only transient failures are retried; auth/bad-input errors fail immediately.
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def retry_http(fn, attempts: int | None = None, base_delay: float | None = None):
    """Run fn() with exponential backoff (1s -> 2s -> 4s) on timeouts and
    retryable HTTP status codes. fn must raise httpx errors (use
    response.raise_for_status()). Defaults come from config so retry behaviour
    is tunable without touching call sites."""
    attempts = settings.retry_attempts if attempts is None else attempts
    base_delay = settings.retry_base_delay if base_delay is None else base_delay
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except httpx.TimeoutException as exc:
            last_exc = exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in RETRYABLE_STATUS:
                raise
            last_exc = exc
        if attempt < attempts:
            time.sleep(base_delay * 2 ** (attempt - 1))
    raise last_exc
