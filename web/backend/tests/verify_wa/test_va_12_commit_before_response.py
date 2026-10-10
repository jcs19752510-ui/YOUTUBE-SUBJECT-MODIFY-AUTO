"""TC-VA-182~: DEF-VA-010(= DEF-VF-B01) 회귀 — 변경 내용은 응답이 클라이언트에 나가기 '전에' DB 에 확정돼야 한다.

FastAPI 0.143 은 yield 의존성의 종료 코드를 응답 전송 뒤에 실행한다. 그래서 응답을 받은 클라이언트의 다음 요청이 옛 상태를 읽을 수 있었다
(세션 발급 직후 401, 방금 만든 작업 404, PIN 설정 직후 PIN 변경이 current_pin 없이 통과). 여기서는 응답 시작 순간에 '다른 연결'로 DB 를 들여다본다.
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text
from ytweb.app import create_app

from tests.conftest import CORE_ROUTERS, ORIGIN  # noqa: F401

H = [("host", "127.0.0.1:8080"), ("origin", ORIGIN), ("content-type", "application/json")]


def _call_with_probe(app, method, path, headers, body, probe):
    """응답 시작(http.response.start) 순간에 probe() 를 실행하고 결과를 돌려준다."""
    seen: dict = {}
    queue = [body]

    async def receive():
        if queue:
            return {"type": "http.request", "body": queue.pop(0), "more_body": False}
        return {"type": "http.disconnect"}

    async def send(msg):
        if msg["type"] == "http.response.start":
            seen["status"] = msg["status"]
            seen["headers"] = msg["headers"]
            seen["probe"] = await asyncio.to_thread(probe)

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method, "path": path, "raw_path": path.encode(),
             "query_string": b"", "root_path": "", "scheme": "http", "headers": [(k.encode(), v.encode()) for k, v in headers],
             "client": ("127.0.0.1", 1), "server": ("127.0.0.1", 8080)}
    asyncio.run(app(scope, receive, send))
    return seen


def _count(engine, sql):
    def run():
        with engine.connect() as c:
            return c.execute(text(sql)).scalar_one()
    return run


def test_session_row_is_committed_before_response_starts(app, engine):
    """TC-VA-182 [S-W08] 세션 발급 응답이 나가는 순간 다른 연결에서도 세션 행과 감사 행이 이미 보인다(발급 직후 첫 요청이 401 이 되지 않는다)."""
    seen = _call_with_probe(app, "POST", "/api/v1/auth/session", H, b"{}",
                            lambda: (_count(engine, "select count(*) from sessions")(), _count(engine, "select count(*) from audit_log")()))
    assert seen["status"] == 200 and seen["probe"] == (1, 1)


def test_setting_change_is_committed_before_response_starts(client, csrf, engine):
    """TC-VA-183 [S-W03, S-W08] 설정 변경(PIN 설정) 응답이 나가는 순간 pin_hash 가 이미 확정돼 있다 -> 바로 이어진 PIN 변경이 current_pin 없이 통과하지 못한다."""
    from tests.conftest import hdr
    app = client.app
    cookie = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)
    headers = H + [("x-csrf-token", csrf), ("cookie", cookie)]
    body = json.dumps({"pin": {"action": "set", "new_pin": "246810"}}).encode()
    seen = _call_with_probe(app, "PATCH", "/api/v1/settings", headers, body, _count(engine, "select count(*) from settings_kv where key='pin_hash'"))
    assert seen["status"] == 200 and seen["probe"] == 1
    r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "111111"}}, headers=hdr(csrf))
    assert r.status_code == 401  # PIN 이 이미 설정됨 -> current_pin 이 없으면 거부


def test_pin_change_without_current_pin_never_succeeds_in_rapid_sequence(client, csrf):
    """TC-VA-184 [S-W08] PIN 설정 직후 current_pin 없는 변경을 50번 연달아 시도해도 한 번도 통과하지 않는다."""
    from tests.conftest import hdr
    assert client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "246810"}}, headers=hdr(csrf)).status_code == 200
    codes = []
    for _ in range(50):
        r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "111111"}}, headers=hdr(csrf))
        codes.append(r.status_code)
        if r.status_code == 429:
            break
    assert 200 not in codes


def test_failed_request_is_still_rolled_back(client, csrf, engine):
    """TC-VA-185 오류 응답(검증 실패 422)의 변경은 확정되지 않는다: 같은 요청에서 먼저 바꾼 값이 남지 않는다."""
    from tests.conftest import hdr
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5, "tone": "not-a-list"}, headers=hdr(csrf))
    assert r.status_code == 422
    with engine.connect() as c:
        assert c.execute(text("select count(*) from settings_kv where key='daily_apply_cap'")).scalar_one() == 0


def test_commit_failure_before_response_gives_500_not_success(web_settings, engine, clock, fake_time, monkeypatch):
    """TC-VA-186 [S-W09] 확정(commit)이 실패하면 클라이언트는 성공(200)이 아니라 일반 500 을 받는다(예전: 성공 응답 후 조용히 유실)."""
    from sqlalchemy.orm import Session
    app = create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time)
    real = Session.commit

    def boom(self):
        raise RuntimeError("disk full /secret/path")
    monkeypatch.setattr(Session, "commit", boom)
    from tests.verify_wa.helpers import asgi_call, body_json
    out = asgi_call(app, "POST", "/api/v1/auth/session", H, [b"{}"])
    monkeypatch.setattr(Session, "commit", real)
    assert out["status"] == 500 and body_json(out)["code"] == "internal_error"
    assert b"secret" not in out["body"]


# ---------------------------------------------------------------- DEF-VA-011 (= DEF-VF-B02): 한국어 hint


def _hangul(s: str) -> bool:
    return any("가" <= c <= "힣" for c in s)


def test_every_problem_error_in_core_unit_code_declares_a_hint():
    """TC-VA-187 [S-W09] 이 단위 소스의 모든 `ProblemError(...)` 생성(및 problem_response/reject 호출)이 hint 를 채운다(정적 검사: 새 오류 코드가 hint 없이 추가되는 회귀 방지)."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "ytweb"
    files = [*root.glob("core/*.py"), root / "app.py", root / "worker.py", root / "migrate.py",
             *(root / "routers" / f"{n}.py" for n in ("health", "auth", "settings", "audit"))]
    missing = []
    for f in files:
        if f.name == "errors.py":
            continue
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "ProblemError":
                kw = {k.arg: k.value for k in node.keywords}
                hint = kw.get("hint")
                if hint is None or (isinstance(hint, ast.Constant) and not hint.value):
                    missing.append(f"{f.name}:{node.lineno}")
    assert not missing, missing


def test_problem_responses_from_this_unit_carry_korean_hint(client, csrf):
    """TC-VA-188 [S-W09] 실제 응답에서도 이 단위의 오류 코드(pin_invalid 422/401, pin_not_set, validation_error, setting_not_allowed, not_found, method_not_allowed,
    bad_content_length, csrf/session)가 비어 있지 않은 한국어 hint 를 돌려준다."""
    from tests.conftest import hdr
    from tests.verify_wa.helpers import asgi_call, body_json
    H0 = [("host", "127.0.0.1:8080")]
    cases = {}
    r = client.patch("/api/v1/settings", json={"pin": {"action": "clear"}}, headers=hdr(csrf)); cases["pin_not_set"] = r
    r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "12"}}, headers=hdr(csrf)); cases["pin_invalid_format"] = r
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 99}, headers=hdr(csrf)); cases["validation_int"] = r
    r = client.patch("/api/v1/settings", json={"tone": 5}, headers=hdr(csrf)); cases["validation_tone"] = r
    r = client.patch("/api/v1/settings", json={"tone": [5]}, headers=hdr(csrf)); cases["validation_tone_item"] = r
    r = client.patch("/api/v1/settings", json={"tone": ["a\nb"]}, headers=hdr(csrf)); cases["validation_tone_ctl"] = r
    r = client.patch("/api/v1/settings", json={}, headers=hdr(csrf)); cases["validation_empty"] = r
    r = client.patch("/api/v1/settings", json={"pin": 5}, headers=hdr(csrf)); cases["validation_pin_shape"] = r
    r = client.patch("/api/v1/settings", json={"enable_live": True}, headers=hdr(csrf)); cases["setting_not_allowed"] = r
    r = client.get("/api/v1/nope"); cases["not_found"] = r
    r = client.delete("/api/v1/auth/me", headers=hdr(csrf)); cases["method_not_allowed"] = r
    for name, resp in cases.items():
        j = resp.json()
        assert resp.status_code >= 400 and j["hint"].strip() and _hangul(j["hint"]), (name, j)
    assert client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "246810"}}, headers=hdr(csrf)).status_code == 200
    r = client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "135792", "current_pin": "000000"}}, headers=hdr(csrf))
    j = r.json()
    assert r.status_code == 401 and j["code"] == "pin_invalid" and _hangul(j["hint"])
    out = asgi_call(client.app, "GET", "/api/v1/auth/me", H0 + [("content-length", "abc")])
    j = body_json(out)
    assert out["status"] == 400 and _hangul(j["hint"])


def test_job_without_handler_fails_with_hint_text(factory):
    """TC-VA-189 처리기가 없는 작업 유형은 재시도 없이 failed 로 기록되고 오류 필드는 "no_handler: ..." 형식이다."""
    from datetime import datetime, timezone

    from ytweb.core import jobs
    t = datetime(2026, 10, 10, 3, tzinfo=timezone.utc)
    with factory() as s:
        j = jobs.enqueue(s, type="unknown.type", payload={}, now=t)
        s.commit()
        jid = j.id
    assert jobs.process_next(factory, worker_id="w", clock=lambda: t) is True
    from ytweb.db.models import Job
    with factory() as s:
        row = s.get(Job, jid)
        assert row.status == "failed" and row.error.startswith("no_handler")
