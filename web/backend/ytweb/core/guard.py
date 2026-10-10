"""최외곽 ASGI 미들웨어: Host 허용 목록(DNS 리바인딩 방어) · 요청 크기 제한 · 속도 제한 · 보안 헤더 · 요청 로그.

순수 ASGI 로 구현해 요청 본문 스트림을 직접 계수한다(Content-Length 없는 chunked 요청도 제한).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable

from ytweb.core.errors import PROBLEM_MEDIA_TYPE, problem_body
from ytweb.core.ratelimit import RateLimiter

log = logging.getLogger("ytweb.access")

HEALTH_PATHS = frozenset({"/healthz", "/readyz", "/api/healthz", "/api/readyz"})
MAX_BODY_BYTES = 1024 * 1024

_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
_APP_CSP = "default-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
_COMMON_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}


class _BodyTooLarge(Exception):
    pass


class GuardMiddleware:
    def __init__(
        self,
        app,
        *,
        allowed_hosts: tuple[str, ...],
        limiter: RateLimiter,
        max_body: int = MAX_BODY_BYTES,
        docs_enabled: bool = False,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.app = app
        self.allowed = frozenset(h.lower() for h in allowed_hosts)
        self.limiter = limiter
        self.max_body = max_body
        self.docs_enabled = docs_enabled
        self._time = time_fn

    def _headers_for(self, path: str) -> dict[str, str]:
        h = dict(_COMMON_HEADERS)
        is_docs = self.docs_enabled and path.startswith(("/docs", "/redoc", "/openapi.json"))
        if path.startswith("/api") or path in HEALTH_PATHS:
            h["content-security-policy"] = _API_CSP
            h["cache-control"] = "no-store"
        elif not is_docs:
            h["content-security-policy"] = _APP_CSP
        return h

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        method: str = scope["method"]
        req_headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        request_id = uuid.uuid4().hex
        scope["ytweb_request_id"] = request_id
        started = self._time()
        status_holder = {"status": 0}
        extra = self._headers_for(path)
        extra["x-request-id"] = request_id

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = [(k, v) for k, v in message["headers"] if k.decode("latin-1").lower() not in extra]
                headers += [(k.encode("latin-1"), v.encode("latin-1")) for k, v in extra.items()]
                message = {**message, "headers": headers}
            await send(message)

        async def reject(status: int, code: str, title: str, hint: str = "", headers: dict[str, str] | None = None):
            body = json.dumps(problem_body(status, code, title, hint=hint), ensure_ascii=False).encode()
            hdrs = {"content-type": PROBLEM_MEDIA_TYPE, "content-length": str(len(body)), **(headers or {})}
            await send_wrapped({"type": "http.response.start", "status": status,
                                "headers": [(k.encode("latin-1"), v.encode("latin-1")) for k, v in hdrs.items()]})
            await send_wrapped({"type": "http.response.body", "body": body})

        try:
            if path not in HEALTH_PATHS and req_headers.get("host", "").lower() not in self.allowed:
                await reject(403, "host_not_allowed", "허용되지 않은 접속 주소입니다.",
                             hint="http://127.0.0.1:8080 주소로 접속하세요.")
                return

            cl = req_headers.get("content-length")
            if cl is not None:
                try:
                    too_big = int(cl) > self.max_body
                except ValueError:
                    await reject(400, "bad_content_length", "Content-Length 값이 올바르지 않습니다.")
                    return
                if too_big:
                    await reject(413, "payload_too_large", "요청 본문이 너무 큽니다.", hint="1MB 이하로 줄여서 보내세요.")
                    return

            if path.startswith("/api") and path not in HEALTH_PATHS:
                wait = self.limiter.check(method, path)
                if wait:
                    retry = max(1, int(wait + 0.999))
                    await reject(429, "rate_limited", "요청이 너무 많습니다.", hint=f"{retry}초 후에 다시 시도하세요.",
                                 headers={"retry-after": str(retry)})
                    return

            received = 0

            async def receive_limited():
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > self.max_body:
                        raise _BodyTooLarge
                return message

            try:
                await self.app(scope, receive_limited, send_wrapped)
            except _BodyTooLarge:
                if status_holder["status"] == 0:
                    await reject(413, "payload_too_large", "요청 본문이 너무 큽니다.", hint="1MB 이하로 줄여서 보내세요.")
                else:
                    raise
            except Exception:
                # 스택트레이스는 로그에만 남기고 응답에는 넣지 않는다. ServerErrorMiddleware 는 이 계층 밖이라 보안 헤더가 빠지므로 여기서 처리한다.
                log.error("unhandled error path=%s", path, exc_info=True, extra={"request_id": request_id})
                if status_holder["status"] == 0:
                    await reject(500, "internal_error", "서버 내부 오류가 발생했습니다.",
                                 hint="잠시 후 다시 시도하고, 계속되면 로그를 확인하세요.")
                else:
                    raise
        finally:
            if path.startswith("/api") or status_holder["status"] >= 400:
                log.info(
                    "request",
                    extra={"method": method, "path": path, "status": status_holder["status"],
                           "ms": int((self._time() - started) * 1000), "request_id": request_id},
                )
