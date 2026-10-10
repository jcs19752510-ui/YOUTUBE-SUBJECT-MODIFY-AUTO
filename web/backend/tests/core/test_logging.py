"""JSON 로그와 비밀 마스킹."""
from __future__ import annotations

import io
import json
import logging

from fastapi.testclient import TestClient

from tests.conftest import ORIGIN, hdr
from ytweb.core.logsetup import MASK, JsonFormatter, mask_secrets, setup_logging


def test_mask_key_value_forms():
    """TC-WA-@@@ token/password/secret/pin/cookie/csrf 형태의 값은 가려진다."""
    for raw in ["token=abc123", "password: hunter2", "secret='s3cr3t'", 'pin": "1234"', "X-CSRF-Token: zzzz", "Cookie: ytw_session=aaaa", "api_key=KEY1"]:
        out = mask_secrets(raw)
        assert MASK in out
        for leaked in ("abc123", "hunter2", "s3cr3t", "1234", "zzzz", "aaaa", "KEY1"):
            assert leaked not in out


def test_mask_bearer_url_credentials_and_long_tokens():
    """TC-WA-@@@ Bearer 값, URL 안의 user:pass, 40자 이상 토큰 모양 문자열을 가린다."""
    assert "abc.def" not in mask_secrets("Authorization header Bearer abc.def-123")
    out = mask_secrets("postgresql://ytweb_app:pw123@db:5432/ytweb")
    assert "pw123" not in out and "ytweb_app:" not in out and "@db:5432/ytweb" in out
    tok = "A" * 43
    assert tok not in mask_secrets(f"value {tok} end")


def test_mask_keeps_ordinary_text():
    """TC-WA-@@@ 일반 문장은 변하지 않는다."""
    s = "배치 3건 처리 완료 video_id=abc123DEF45"
    assert mask_secrets(s) == s


def _record(msg, **extra):
    r = logging.LogRecord("ytweb.t", logging.INFO, __file__, 1, msg, (), None)
    r.__dict__.update(extra)
    return r


def test_json_formatter_valid_json_and_masks_extra_fields():
    """TC-WA-@@@ JSON 한 줄 출력, 민감 키의 extra 값은 가리고 중첩 값도 가린다."""
    out = JsonFormatter().format(_record("hello token=XYZ", password="p", nested={"csrf_token": "c", "ok": 1}, count=3))
    j = json.loads(out)
    assert j["level"] == "INFO" and j["logger"] == "ytweb.t" and j["count"] == 3
    assert "XYZ" not in j["msg"] and j["password"] == MASK
    assert j["nested"] == {"csrf_token": MASK, "ok": 1}


def test_json_formatter_masks_exception_text():
    """TC-WA-@@@ 예외 트레이스백 안의 비밀도 가린다."""
    try:
        raise ValueError("password=hunter2")
    except ValueError:
        import sys
        r = _record("fail")
        r.exc_info = sys.exc_info()
    j = json.loads(JsonFormatter().format(r))
    assert "hunter2" not in j["exc"] and "ValueError" in j["exc"]


def test_setup_logging_idempotent_and_text_mode():
    """TC-WA-@@@ setup_logging 을 여러 번 불러도 핸들러는 하나, 텍스트 모드도 마스킹."""
    setup_logging(json_format=True)
    lg = setup_logging(json_format=False)
    assert sum(1 for h in lg.handlers if getattr(h, "_ytweb", False)) == 1
    h = next(x for x in lg.handlers if getattr(x, "_ytweb", False))
    assert "hunter2" not in h.format(_record("password=hunter2"))
    setup_logging(json_format=True)


def test_access_log_has_no_query_cookie_or_csrf(app):
    """TC-WA-@@@ 접근 로그에는 쿼리 문자열·쿠키·CSRF 토큰·요청 본문이 들어가지 않는다."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    lg = logging.getLogger("ytweb.access")
    lg.addHandler(handler)
    try:
        with TestClient(app, base_url=ORIGIN) as c:
            r = c.post("/api/v1/auth/session", headers={"Origin": ORIGIN})
            csrf = r.json()["csrf_token"]
            cookie = c.cookies.get("ytw_session")
            c.patch("/api/v1/settings?secretquery=SQVALUE", json={"tone": ["BODYVALUE"]}, headers=hdr(csrf))
    finally:
        lg.removeHandler(handler)
    text = buf.getvalue()
    lines = [json.loads(line) for line in text.splitlines()]
    assert any(line["path"] == "/api/v1/settings" and line["status"] == 200 and line["method"] == "PATCH" for line in lines)
    for leaked in (csrf, cookie, "SQVALUE", "BODYVALUE", "secretquery"):
        assert leaked not in text
