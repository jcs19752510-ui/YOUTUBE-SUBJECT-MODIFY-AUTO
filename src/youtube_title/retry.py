"""재시도: 최대 2회, 지수 백오프, 무한 재시도 금지(SEC-003, NFR-004)."""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")
MAX_RETRIES = 2


def default_is_retryable(exc: BaseException) -> bool:
    flag = getattr(exc, "retryable", None)
    if flag is not None:
        return bool(flag)
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    status = getattr(getattr(exc, "resp", None), "status", None)
    return status in (500, 502, 503, 504)


def call_with_retry(
    fn: Callable[[], T],
    *,
    retries: int = MAX_RETRIES,
    base_delay: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
    is_retryable: Callable[[BaseException], bool] = default_is_retryable,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """fn을 호출한다. 재시도 가능한 오류만 최대 `retries`회 다시 시도한다(상한 MAX_RETRIES)."""
    retries = max(0, min(retries, MAX_RETRIES))
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if attempt >= retries or not is_retryable(exc):
                raise
            if on_retry:
                on_retry(attempt + 1, exc)
            sleep(base_delay * (2 ** attempt))
            attempt += 1
