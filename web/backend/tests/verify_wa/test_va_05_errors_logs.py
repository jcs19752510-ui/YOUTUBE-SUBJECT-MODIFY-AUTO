"""독립 점검 5: 오류 응답의 정보 비노출 · 로그 마스킹 (S-W08, S-W09, S-W13)."""
from __future__ import annotations

import json

import pytest

from tests.verify_wa import probe_routes
from tests.verify_wa.helpers import ORIGIN, SECRET_PIN, asgi_call, body_json, hdr, login
from ytweb.app import create_app
from ytweb.core.logsetup import MASK, mask_secrets
from tests.conftest import CORE_ROUTERS

LEAK_NEEDLES = ["Traceback", "site-packages", "/home/", ".py", "RuntimeError", "sqlalchemy", "IntegrityError", "psycopg",
                "settings_kv", "INSERT INTO", "sqlite", "/etc/shadow", probe_routes.SECRET_IN_EXC, "Background on this error"]


def _assert_clean(text_: str):
    for n in LEAK_NEEDLES:
        assert n not in text_, n


def test_unhandled_exception_returns_generic_500_without_leaks(pclient, log_capture):
    """TC-VA-088 [S-W09] 처리되지 않은 예외(경로·비밀이 든 메시지)는 일반 문구 500 problem+json 이고 응답 어디에도 예외 클래스/경로/메시지가 없으며 보안 헤더가 유지된다."""
    r = pclient.get("/api/v1/_t/boom")
    assert r.status_code == 500 and r.headers["content-type"].startswith("application/problem+json")
    _assert_clean(r.text)
    j = r.json()
    assert j["code"] == "internal_error" and set(j) == {"type", "title", "status", "detail", "code", "hint"}
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-request-id"]
    # 서버 로그에는 원인이 남는다(운영자용) 단 비밀은 마스킹
    logs = log_capture.getvalue()
    assert "unhandled error" in logs and "RuntimeError" in logs
    assert probe_routes.SECRET_IN_EXC not in logs


def test_db_error_returns_generic_500_without_sql(pclient):
    """TC-VA-089 [S-W09] DB 제약 위반(IntegrityError)도 SQL/테이블/드라이버 정보 없이 일반 500."""
    login(pclient)
    r = pclient.get("/api/v1/_t/dberr")
    assert r.status_code == 500
    _assert_clean(r.text)


def test_db_error_log_does_not_contain_bound_parameter_values(pclient, log_capture):
    """TC-VA-090 [S-W09] DB 오류 로그에 바인딩 파라미터 값(비밀일 수 있음)이 남지 않아야 한다."""
    pclient.get("/api/v1/_t/dberr-param")
    assert "PinHash-Looking-Value-ABC" not in log_capture.getvalue()


def test_http_exception_detail_not_echoed(pclient):
    """TC-VA-091 [S-W09] 코드가 던진 HTTPException(detail=경로/비밀)의 detail 은 응답에 나가지 않는다."""
    r = pclient.get("/api/v1/_t/http")
    assert r.status_code == 418
    _assert_clean(r.text)


def test_validation_error_does_not_echo_submitted_values(pclient):
    """TC-VA-092 [S-W09] 검증 오류(422)는 위치와 사유만 알리고 제출한 값(비밀일 수 있음)을 되돌리지 않는다. 깨진 JSON 도 마찬가지."""
    csrf = login(pclient)
    secret = "TopSecretValue-ABC123"
    cases = [
        {"json": {"n": secret}},
        {"json": {"n": 1, "extra": secret}},
        {"content": ('{"n": %s' % secret).encode(), "headers": {"Content-Type": "application/json"}},
        {"content": ('{"n": "%s", ' % secret).encode(), "headers": {"Content-Type": "application/json"}},
        {"json": [secret]},
    ]
    for kw in cases:
        h = hdr(csrf)
        h.update(kw.pop("headers", {}))
        r = pclient.post("/api/v1/_t/validate", headers=h, **kw)
        assert r.status_code in (400, 422), (kw, r.status_code)
        assert secret not in r.text, kw
    r = pclient.get("/api/v1/audit", params={"page": secret})
    assert r.status_code == 422 and secret not in r.text


def test_404_405_are_problem_json_without_echoing_path(pclient):
    """TC-VA-093 [S-W09] 404/405 도 problem+json 이고 요청 경로를 되돌리지 않는다."""
    r = pclient.get("/api/v1/secret-path-xyz")
    assert r.status_code == 404 and "secret-path-xyz" not in r.text and r.headers["content-type"].startswith("application/problem+json")
    r = pclient.delete("/api/v1/auth/me")
    assert r.status_code == 405 and r.headers["content-type"].startswith("application/problem+json")


def test_db_unreachable_gives_503_ready_and_500_api_without_connection_details(tmp_path, web_settings, clock, fake_time, log_capture, monkeypatch):
    """TC-VA-094 [S-W08, S-W09] DB 가 죽어 있으면 /readyz 는 503(degraded) 이고 API 는 500 이며, 응답·로그에 DB 비밀번호/호스트/경로가 없다."""
    from dataclasses import replace
    pw = "SuperSecretPw123"
    s = replace(web_settings, database_url=f"postgresql+psycopg://ytweb_app:{pw}@127.0.0.1:9/ytweb")
    monkeypatch.delenv("YTWEB_AUTO_CREATE", raising=False)
    app = create_app(s, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time)
    h = [("host", "127.0.0.1:8080")]
    ready = asgi_call(app, "GET", "/readyz", h)
    assert ready["status"] == 503 and body_json(ready)["db"] == "down"
    api = asgi_call(app, "GET", "/api/v1/auth/me", h)
    assert api["status"] == 500
    for out in (ready, api):
        txt = out["body"].decode()
        assert pw not in txt and "127.0.0.1:9" not in txt and "psycopg" not in txt
    assert pw not in log_capture.getvalue()


# ---------------------------------------------------------------- 로그 마스킹

MASKED = [
    ("password=hunter2secret", "hunter2secret"),
    ('{"password": "hunter2secret"}', "hunter2secret"),
    ("PIN=987654", "987654"),
    ("pin: 987654", "987654"),
    ("token: abc123def456", "abc123def456"),
    ("Cookie: ytw_session=AAAAsessionvalue; other=1", "AAAAsessionvalue"),
    ("Set-Cookie: ytw_session=BBBBsessionvalue; HttpOnly; Path=/api", "BBBBsessionvalue"),
    ("X-CSRF-Token: csrfvalue123", "csrfvalue123"),
    ("csrf_token=csrfvalue123", "csrfvalue123"),
    ("api_key=sk-live-abcdef", "sk-live-abcdef"),
    ("access_token=ya29.a0AfH6SMB", "ya29.a0AfH6SMB"),
    ("client_secret=abcdefg1234", "abcdefg1234"),
    ("https://user:p4ssw0rdX@db.example/x", "p4ssw0rdX"),
    ("postgresql+psycopg://ytweb_app:Pw!Secret9@db:5432/ytweb", "Pw!Secret9"),
    ("session " + "A" * 43 + " end", "A" * 43),
    ('{"pin": "123456"}', "123456"),
]


@pytest.mark.parametrize("text_,secret", MASKED)
def test_mask_secrets_known_forms(text_, secret):
    """TC-VA-095 [S-W09] 비밀 형태 16종(키=값, JSON, 쿠키, URL 자격증명, 43자 토큰)이 마스킹된다."""
    out = mask_secrets(text_)
    assert secret not in out, out
    assert MASK in out


@pytest.mark.parametrize("text_,secret", [
    ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
    ("authorization=Bearer abc123.def456", "abc123.def456"),
    ("Authorization: Basic dXNlcjpwYXNzd29yZA==", "dXNlcjpwYXNzd29yZA=="),
])
def test_mask_secrets_authorization_header_values(text_, secret):
    """TC-VA-096 [S-W09] Authorization 헤더 값(스킴 뒤 자격증명)까지 모두 마스킹돼야 한다."""
    assert secret not in mask_secrets(text_)


def test_mask_does_not_destroy_ordinary_text():
    """TC-VA-097 [S-W09] 일반 문구·짧은 값·경로는 과하게 가리지 않는다(디버깅 가능성 유지)."""
    s = "request path=/api/v1/videos status=200 ms=12 count=5 page=2"
    assert mask_secrets(s) == s


def test_json_formatter_masks_extra_fields_nested_and_exc(log_capture):
    """TC-VA-098 [S-W09] JSON 로그의 extra 필드(민감 키 이름·중첩 dict/list 값)와 예외 본문이 마스킹된다."""
    import logging
    lg = logging.getLogger("ytweb.test_va")
    lg.info("hello", extra={"cookie": "ytw_session=XYZ-secret-cookie", "headers": {"X-CSRF-Token": "csrf-secret-aaa", "ok": "fine"},
                            "items": [{"password": "pw-secret-1"}, "plain"], "authorization": "Bearer top-secret-token"})
    try:
        raise ValueError("boom password=exc-secret-1 and https://u:exc-secret-2@host/x")
    except ValueError:
        lg.error("failed", exc_info=True)
    out = log_capture.getvalue()
    for s in ("XYZ-secret-cookie", "csrf-secret-aaa", "pw-secret-1", "top-secret-token", "exc-secret-1", "exc-secret-2"):
        assert s not in out, s
    assert "fine" in out and "plain" in out
    for line in out.strip().splitlines():
        json.loads(line)  # 한 줄 JSON 유지


def test_secrets_never_reach_logs_through_real_request_flows(client, log_capture):
    """TC-VA-099 [S-W08, S-W09] 실제 요청 흐름(PIN 설정·로그인·CSRF·쿠키·쿼리스트링·Authorization·검증오류)을 모두 거친 뒤 로그에 비밀이 하나도 없다."""
    csrf = login(client)
    token = client.cookies.get("ytw_session")
    client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": SECRET_PIN}}, headers=hdr(csrf))
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    client.post("/api/v1/auth/session", json={"pin": "0000"}, headers={"Origin": ORIGIN})
    csrf2 = login(client, SECRET_PIN)
    client.get("/api/v1/settings", params={"pin": "QS-SECRET-PIN-4242", "token": "QS-SECRET-TOKEN"},
               headers={"Authorization": "Bearer HDR-SECRET-BEARER-77", "Cookie": f"ytw_session={token}"})
    client.patch("/api/v1/settings", json={"daily_apply_cap": "BODY-SECRET-VALUE"}, headers=hdr(csrf2))
    client.get("/api/v1/nope/QS-SECRET-PATHTOKEN")
    logs = log_capture.getvalue()
    assert '"request"' in logs or "request" in logs
    for s in (SECRET_PIN, "QS-SECRET-PIN-4242", "QS-SECRET-TOKEN", "HDR-SECRET-BEARER-77", "BODY-SECRET-VALUE", csrf, csrf2, token,
              client.cookies.get("ytw_session")):
        assert s not in logs, s
    # 접근 로그 필드는 고정 목록뿐: 헤더/쿼리/본문 필드가 없다
    for line in logs.splitlines():
        rec = json.loads(line)
        if rec.get("logger") == "ytweb.access":
            assert set(rec) <= {"ts", "level", "logger", "msg", "method", "path", "status", "ms", "request_id"}, rec
