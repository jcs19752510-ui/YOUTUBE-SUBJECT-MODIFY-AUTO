"""6단계 독립 검증(verify_wa) 공용 도우미. 구현자 테스트(tests/core)와 별개로 작성했다."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from tests.conftest import CORE_ROUTERS, ORIGIN  # noqa: F401  (재노출)

ALLOWED_ORIGINS = {"http://127.0.0.1:8080", "http://localhost:8080"}
OWNER_HOST = "127.0.0.1:8080"
SECRET_PIN = "135792468"


def asgi_call(app, method: str, path: str, headers: list[tuple[str, str]] | None = None,
              chunks: list[bytes] | None = None, query: bytes = b"") -> dict[str, Any]:
    """TestClient 가 만들어 주지 못하는 원시 요청(중복 Host, 음수 Content-Length, 쪼개진 본문)을 ASGI 로 직접 보낸다."""
    chunks = chunks if chunks is not None else []
    out: dict[str, Any] = {"status": None, "headers": [], "body": b""}
    queue = list(chunks) or [b""]

    async def receive():
        if queue:
            body = queue.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(queue)}
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
            out["headers"] = [(k.decode("latin-1").lower(), v.decode("latin-1")) for k, v in msg["headers"]]
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "path": path,
        "raw_path": path.encode(), "query_string": query, "root_path": "", "scheme": "http",
        "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or [])],
        "client": ("127.0.0.1", 50000), "server": ("127.0.0.1", 8080),
    }
    asyncio.run(app(scope, receive, send))
    return out


def body_json(out: dict[str, Any]) -> Any:
    return json.loads(out["body"].decode("utf-8"))


def header(out: dict[str, Any], name: str) -> str | None:
    for k, v in out["headers"]:
        if k == name.lower():
            return v
    return None


def login(client, pin: str | None = None, origin: str = ORIGIN) -> str:
    r = client.post("/api/v1/auth/session", json={"pin": pin} if pin else None, headers={"Origin": origin})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def hdr(csrf: str, origin: str = ORIGIN) -> dict[str, str]:
    return {"Origin": origin, "X-CSRF-Token": csrf}


def cookie_header(client) -> str:
    return "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)


def set_cookie_values(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def parse_set_cookie(raw: str) -> tuple[str, str, dict[str, str]]:
    parts = [p.strip() for p in raw.split(";")]
    name, _, value = parts[0].partition("=")
    attrs: dict[str, str] = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        attrs[k.strip().lower()] = v.strip()
    return name, value, attrs
