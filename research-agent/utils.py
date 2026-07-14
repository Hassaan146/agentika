"""Small shared helpers."""

import time

import httpx

# Only transient failures are retried; auth/bad-input errors fail immediately.
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def retry_http(fn, attempts: int = 3, base_delay: float = 1.0):
    """Run fn() with exponential backoff (1s -> 2s -> 4s) on timeouts and
    retryable HTTP status codes. fn must raise httpx errors (use
    response.raise_for_status())."""
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
