"""프로세스 내 슬라이딩 윈도 속도 제한(단일 소유자 로컬 앱 전제, 다중 프로세스 공유 안 함)."""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimits:
    global_per_min: int = 600
    write_per_min: int = 120
    auth_per_min: int = 10


class SlidingWindow:
    def __init__(self, limit: int, window: float = 60.0, time_fn: Callable[[], float] = time.monotonic) -> None:
        self.limit, self.window, self._time = limit, window, time_fn
        self._hits: deque[float] = deque()

    def peek(self) -> float:
        """0 이면 허용, 아니면 재시도까지 남은 초."""
        now = self._time()
        while self._hits and self._hits[0] <= now - self.window:
            self._hits.popleft()
        if len(self._hits) >= self.limit:
            return max(0.001, self._hits[0] + self.window - now)
        return 0.0

    def hit(self) -> None:
        self._hits.append(self._time())


class RateLimiter:
    def __init__(self, limits: RateLimits, time_fn: Callable[[], float] = time.monotonic) -> None:
        self._g = SlidingWindow(limits.global_per_min, time_fn=time_fn)
        self._w = SlidingWindow(limits.write_per_min, time_fn=time_fn)
        self._a = SlidingWindow(limits.auth_per_min, time_fn=time_fn)
        self._f = SlidingWindow(limits.global_per_min, time_fn=time_fn)  # 출처 불명(외부 사이트) 요청 전용

    def check(self, method: str, path: str) -> float:
        """허용이면 0 을 돌려주고 사용량을 기록, 아니면 재시도까지 남은 초(기록 안 함)."""
        windows = [self._g]
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            windows.append(self._w)
        if method == "POST" and path.rstrip("/") in ("/api/v1/auth/session", "/api/v1/auth/login"):
            windows.append(self._a)
        waits = [w.peek() for w in windows]
        if any(waits):
            return max(waits)
        for w in windows:
            w.hit()
        return 0.0

    def check_foreign(self) -> float:
        """소유자 화면이 아닌 출처의 요청을 별도 창에서 센다(소유자 한도를 소진시키는 DoS 방지)."""
        wait = self._f.peek()
        if wait:
            return wait
        self._f.hit()
        return 0.0
