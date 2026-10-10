"""problem+json 형식과 내부 정보 비노출."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from tests.conftest import ORIGIN, hdr, login
from ytweb.core.errors import ProblemError, problem_body


def test_problem_body_shape():
    """TC-WA-017 problem_body 는 type,title,status,detail,code,hint 를 가진다."""
    b = problem_body(409, "x_y", "제목", "상세", "힌트")
    assert set(b) == {"type", "title", "status", "detail", "code", "hint"}
    assert b["status"] == 409 and b["code"] == "x_y" and b["type"].endswith("x_y")


def test_problem_error_converted_with_headers(app):
    """TC-WA-018 ProblemError 는 application/problem+json 으로 변환되고 사용자 지정 헤더가 유지된다."""
    r = APIRouter()

    @r.get("/api/v1/_t/problem")
    def _p():
        raise ProblemError(418, "teapot", "주전자", "상세", "힌트", headers={"X-Test": "1"})

    app.include_router(r)
    with TestClient(app, base_url=ORIGIN) as c:
        resp = c.get("/api/v1/_t/problem")
    assert resp.status_code == 418
    assert resp.headers["content-type"].startswith("application/problem+json")
    assert resp.headers["x-test"] == "1"
    assert resp.json() == {"type": "urn:ytweb:problem:teapot", "title": "주전자", "status": 418, "detail": "상세", "code": "teapot", "hint": "힌트"}


def test_unhandled_exception_hides_internals(app):
    """TC-WA-019 처리되지 않은 예외는 500 internal_error 이고 스택트레이스·경로·예외 메시지가 응답에 없다."""
    r = APIRouter()

    @r.get("/api/v1/_t/boom")
    def _boom():
        raise RuntimeError("secret-detail /home/user/app/x.py")

    app.include_router(r)
    with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as c:
        resp = c.get("/api/v1/_t/boom")
    assert resp.status_code == 500
    body = resp.text
    assert resp.json()["code"] == "internal_error"
    for leak in ("Traceback", "secret-detail", "/home/user", ".py", "RuntimeError"):
        assert leak not in body
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_unhandled_exception_logged_with_trace(app, caplog):
    """TC-WA-020 500 의 원인은 서버 로그에 남는다(응답에는 없음)."""
    import logging
    records: list[logging.LogRecord] = []

    class H(logging.Handler):
        def emit(self, record):
            records.append(record)

    h = H()
    logging.getLogger("ytweb.access").addHandler(h)
    r = APIRouter()

    @r.get("/api/v1/_t/boom2")
    def _boom():
        raise RuntimeError("kaboom")

    app.include_router(r)
    try:
        with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as c:
            c.get("/api/v1/_t/boom2")
    finally:
        logging.getLogger("ytweb.access").removeHandler(h)
    assert any(rec.levelno == logging.ERROR and rec.exc_info for rec in records)


def test_validation_error_is_problem_and_does_not_echo_input(client, csrf):
    """TC-WA-021 검증 실패는 422 validation_error 이고 입력값을 되돌려 보내지 않는다."""
    r = client.post("/api/v1/auth/session", json={"pin": 123, "extra": "TOPSECRETVALUE"}, headers={"Origin": ORIGIN})
    assert r.status_code == 422
    j = r.json()
    assert j["code"] == "validation_error"
    assert "TOPSECRETVALUE" not in r.text
    assert r.headers["content-type"].startswith("application/problem+json")


def test_not_found_and_method_not_allowed_are_problem(client):
    """TC-WA-022 404/405 도 problem+json."""
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
    r = client.put("/api/v1/audit", headers={"Origin": ORIGIN})
    assert r.status_code == 405 and r.json()["code"] == "method_not_allowed"
    assert r.headers["content-type"].startswith("application/problem+json")


def test_invalid_json_body_is_422(client, csrf):
    """TC-WA-023 깨진 JSON 본문은 422 problem+json(서버 오류 아님)."""
    r = client.patch("/api/v1/settings", content=b"{not json", headers={**hdr(csrf), "content-type": "application/json"})
    assert r.status_code == 422
    assert r.json()["code"] == "validation_error"
