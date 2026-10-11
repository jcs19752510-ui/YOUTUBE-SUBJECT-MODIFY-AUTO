"""최외곽 ASGI 미들웨어: Host 허용 목록(DNS 리바인딩 방어) · 요청 크기 제한 · 속도 제한 · 보안 헤더 · 요청 로그.

순수 ASGI 로 구현해 요청 본문 스트림을 직접 계수한다(Content-Length 없는 chunked 요청도 제한).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable

import anyio

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
        self.origins = frozenset(f"http://{h}" for h in self.allowed)
        self.limiter = limiter
        self.max_body = max_body
        self.docs_enabled = docs_enabled
        self._time = time_fn

    def _is_foreign(self, method: str, req_headers: dict[str, str]) -> bool:
        """출처가 소유자 화면이 아닌 요청. 이런 요청은 deps 가 어차피 403 으로 거부하므로, 소유자의 속도 제한 한도를 소모하지 않게 별도 한도로 센다."""
        sec = req_headers.get("sec-fetch-site")
        if sec is not None and sec.strip().lower() not in ("same-origin", "none"):
            return True
        if method in ("POST", "PUT", "PATCH", "DELETE"):
            return req_headers.get("origin", "").strip().lower() not in self.origins
        return False

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
        host_values = [v.decode("latin-1").lower() for k, v in scope["headers"] if k.lower() == b"host"]
        cl_values = [v.decode("latin-1") for k, v in scope["headers"] if k.lower() == b"content-length"]
        request_id = uuid.uuid4().hex
        scope["ytweb_request_id"] = request_id
        started = self._time()
        status_holder = {"status": 0}
        extra = self._headers_for(path)
        extra["x-request-id"] = request_id

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                # 응답이 나가기 전에 DB 변경을 확정한다(FastAPI 는 yield 의존성 종료를 응답 뒤에 실행 -> 다음 요청이 옛 상태를 읽는 경합, DEF-VA-010).
                # 예외로 끝난 요청은 의존성 종료에서 이미 rollback 되어 이 commit 은 아무것도 확정하지 않는다(상태 코드와 무관하게 안전).
                # 확정이 실패하면 예외가 올라가 아래 바깥 처리에서 500 이 된다(성공 응답 후 조용한 유실 방지).
                pending = list(scope.get("ytweb_open_sessions", ()))
                scope["ytweb_open_sessions"] = []  # 실패 뒤 500 응답을 만들 때 같은 commit 을 되풀이하지 않게 비운다
                for db_session in pending:
                    await anyio.to_thread.run_sync(db_session.commit)
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
            # Host 헤더는 정확히 1개여야 하고 허용 목록에 있어야 한다(중복 헤더 밀수 방어: 하나라도 비허용이면 거부).
            if path not in HEALTH_PATHS and (len(host_values) != 1 or host_values[0] not in self.allowed):
                await reject(403, "host_not_allowed", "허용되지 않은 접속 주소입니다.",
                             hint="http://127.0.0.1:8080 주소로 접속하세요.")
                return

            cl = req_headers.get("content-length")
            if cl is not None:
                # RFC 9110: 1*DIGIT 만 허용(int() 는 '-1', '+5', '1_0' 도 받으므로 직접 검사). 값이 여러 개면 거부.
                if len(cl_values) != 1 or not (cl.isascii() and cl.isdigit()):
                    await reject(400, "bad_content_length", "Content-Length 값이 올바르지 않습니다.", hint="요청을 만드는 프로그램의 헤더 설정을 확인하세요.")
                    return
                too_big = int(cl) > self.max_body
                if too_big:
                    await reject(413, "payload_too_large", "요청 본문이 너무 큽니다.", hint="1MB 이하로 줄여서 보내세요.")
                    return

            if path.startswith("/api") and path not in HEALTH_PATHS:
                wait = self.limiter.check_foreign() if self._is_foreign(method, req_headers) else self.limiter.check(method, path)
                if wait:
                    retry = max(1, int(wait + 0.999))
                    await reject(429, "rate_limited", "요청이 너무 많습니다.", hint=f"{retry}초 후에 다시 시도하세요.",
                                 headers={"retry-after": str(retry)})
                    return

            received = 0
            overflow = False
            replaced = False

            async def too_large():
                nonlocal replaced
                if not replaced:
                    replaced = True
                    await reject(413, "payload_too_large", "요청 본문이 너무 큽니다.", hint="1MB 이하로 줄여서 보내세요.")

            async def receive_limited():
                nonlocal received, overflow
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > self.max_body:
                        overflow = True
                        raise _BodyTooLarge
                return message

            async def send_guarded(message):
                # 본문 읽기 중 한도를 넘으면 FastAPI 가 400 으로 바꿔 버리므로, 앱의 응답을 버리고 413 으로 대체한다.
                if overflow:
                    await too_large()
                    return
                await send_wrapped(message)

            try:
                await self.app(scope, receive_limited, send_guarded)
            except Exception:
                if overflow:
                    await too_large()
                else:
                    # 스택트레이스는 로그에만 남기고 응답에는 넣지 않는다. ServerErrorMiddleware 는 이 계층 밖이라 보안 헤더가 빠지므로 여기서 처리한다.
                    log.error("unhandled error path=%s", path, exc_info=True, extra={"request_id": request_id})
                    if status_holder["status"] != 0:
                        raise
                    await reject(500, "internal_error", "서버 내부 오류가 발생했습니다.",
                                 hint="잠시 후 다시 시도하고, 계속되면 로그를 확인하세요.")
            else:
                if overflow:
                    await too_large()
        finally:
            if path.startswith("/api") or status_holder["status"] >= 400:
                log.info(
                    "request",
                    extra={"method": method, "path": path, "status": status_holder["status"],
                           "ms": int((self._time() - started) * 1000), "request_id": request_id},
                )
