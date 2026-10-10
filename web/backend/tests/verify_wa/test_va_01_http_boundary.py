"""독립 점검 1: Host · Origin/Sec-Fetch-Site · 요청 크기 · 속도 제한 · 보안 헤더 (S-W02, S-W03, S-W04, S-W13).

각 테스트 docstring 첫머리의 TC-VA-@@@ 는 번호 부여 스크립트(번호는 파일 순서로 001부터 연속)가 채운다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import select, text

from tests.verify_wa.helpers import (
    ALLOWED_ORIGINS, ORIGIN, asgi_call, body_json, header, hdr, login,
)
from ytweb.app import create_app
from ytweb.core.ratelimit import RateLimits
from ytweb.db.models import AuditLog, SessionRow, SettingKV
from tests.conftest import CORE_ROUTERS

ME = "/api/v1/auth/me"

# ---------------------------------------------------------------- Host

@pytest.mark.parametrize("host", [
    "127.0.0.1:8080", "localhost:8080", "LOCALHOST:8080", "LocalHost:8080",
])
def test_host_allowed_variants(app, host):
    """TC-VA-@@@ [S-W02] 허용 Host(대소문자 무관)는 통과한다."""
    out = asgi_call(app, "GET", ME, [("host", host)])
    assert out["status"] == 200, out


@pytest.mark.parametrize("host", [
    "127.0.0.1:8081", "127.0.0.1", "localhost", "localhost:80", "evil.com", "evil.com:8080",
    "127.0.0.1:8080.evil.com", "127.0.0.1.evil.com:8080", "127.0.0.1:8080@evil.com",
    "evil.com#127.0.0.1:8080", "0.0.0.0:8080", "[::1]:8080", "127.1:8080", "2130706433:8080",
    "127.0.0.1:8080 evil", "127.0.0.1:8080,evil.com", "127.0.0.1:08080", "127.0.0.1:8080.",
    "localhost.:8080", " 127.0.0.1:8080", "127.0.0.1:8080 ", "", "http://127.0.0.1:8080",
])
def test_host_rejected_variants(app, engine, host):
    """TC-VA-@@@ [S-W02] 허용 목록과 정확히 같지 않은 Host(포트 불일치·접미사·userinfo·숫자 표기·공백)는 403 이고 입력을 되돌리지 않는다."""
    out = asgi_call(app, "GET", ME, [("host", host)])
    assert out["status"] == 403, (host, out["status"])
    j = body_json(out)
    assert j["code"] == "host_not_allowed"
    assert "evil" not in out["body"].decode()
    assert header(out, "set-cookie") is None


def test_host_header_missing_rejected(app):
    """TC-VA-@@@ [S-W02] Host 헤더가 아예 없는 요청은 403."""
    assert asgi_call(app, "GET", ME, [])["status"] == 403


def test_multiple_host_headers_one_evil_rejected_when_evil_last(app):
    """TC-VA-@@@ [S-W02] Host 헤더가 여러 개이고 마지막이 비허용이면 거부(헤더 밀수 시도)."""
    out = asgi_call(app, "GET", ME, [("host", "127.0.0.1:8080"), ("host", "evil.com")])
    assert out["status"] == 403


@pytest.mark.xfail(strict=True, reason="DEF-6-001: 중복 Host 헤더 중 마지막 값만 검사해 첫 값이 비허용이어도 통과(h11 은 거부하므로 방어 심층 결함)")
def test_multiple_host_headers_one_evil_rejected_when_evil_first(app):
    """TC-VA-@@@ [S-W02] Host 헤더가 여러 개이고 하나라도 비허용이면 순서와 무관하게 거부돼야 한다."""
    out = asgi_call(app, "GET", ME, [("host", "evil.com"), ("host", "127.0.0.1:8080")])
    assert out["status"] == 403


def test_dns_rebinding_post_creates_no_session(app, engine, client):
    """TC-VA-@@@ [S-W02] DNS 리바인딩: Host/Origin 이 모두 공격자 도메인이어도 세션이 만들어지지 않는다."""
    out = asgi_call(app, "POST", "/api/v1/auth/session",
                    [("host", "evil.com:8080"), ("origin", "http://evil.com:8080"), ("content-type", "application/json")],
                    [b"{}"])
    assert out["status"] == 403 and body_json(out)["code"] == "host_not_allowed"
    with engine.connect() as c:
        assert c.execute(select(text("count(*)")).select_from(SessionRow)).scalar_one() == 0


@pytest.mark.parametrize("path", ["/healthz", "/readyz", "/api/healthz", "/api/readyz"])
def test_health_paths_exempt_but_leak_only_minimal_info(app, path):
    """TC-VA-@@@ [S-W02, S-W09] 헬스 경로만 Host 면제이고 본문은 status/db/mode 외 아무것도 없다(경로·URL·버전 비노출)."""
    out = asgi_call(app, "GET", path, [("host", "api:8000")])
    assert out["status"] == 200
    j = body_json(out)
    assert set(j) <= {"status", "db", "mode"}, j


@pytest.mark.parametrize("path", ["/healthz/", "/healthz/x", "/HEALTHZ", "/api/healthz/../v1/auth/me", "/api/v1/healthz",
                                  "/healthzz", "//healthz", "/readyz/"])
def test_host_exemption_is_exact_path_only(app, path):
    """TC-VA-@@@ [S-W02] Host 면제는 정확한 경로 4개에만 적용된다(유사 경로·슬래시·대소문자 변형은 403)."""
    out = asgi_call(app, "GET", path, [("host", "api:8000")])
    assert out["status"] == 403, (path, out["status"])


def test_host_check_precedes_everything_even_unknown_routes(app):
    """TC-VA-@@@ [S-W02] 존재하지 않는 경로(정적 파일 포함)도 비허용 Host 면 404 가 아니라 403(경로 존재 여부 비노출)."""
    assert asgi_call(app, "GET", "/no/such", [("host", "evil.com")])["status"] == 403
    assert asgi_call(app, "GET", "/no/such", [("host", "127.0.0.1:8080")])["status"] == 404


# ---------------------------------------------------------------- Origin / Sec-Fetch-Site 표

SEC_VALUES = [None, "same-origin", "same-site", "cross-site", "none", "SAME-ORIGIN", "same-origin, cross-site", "", "bogus"]
ORIGIN_VALUES = [
    None, "http://127.0.0.1:8080", "http://localhost:8080", "HTTP://127.0.0.1:8080", "null",
    "http://127.0.0.1:8081", "http://evil.com", "https://127.0.0.1:8080", "http://127.0.0.1:8080/",
    "http://127.0.0.1:8080.evil.com", "http://127.0.0.1:80801", "http://127.0.0.1:8080@evil.com",
    "http://evil.com#http://127.0.0.1:8080", "http://127.0.0.1", "file://", "",
]


def _expected_allowed(sec: str | None, origin: str | None) -> bool:
    """명세(WEB_DESIGN §5 + 단위 노트 3-1)에서 독립적으로 유도한 오라클: Sec-Fetch-Site 가 있으면 same-origin 만, Origin 은 항상 허용 출처와 일치."""
    sec_ok = sec is None or sec.strip().lower() == "same-origin"
    origin_ok = origin is not None and origin.strip().lower() in ALLOWED_ORIGINS
    return sec_ok and origin_ok


@pytest.mark.parametrize("sec", SEC_VALUES)
def test_origin_secfetch_matrix_patch_settings(client, sec):
    """TC-VA-@@@ [S-W02, S-W03] 설정 PATCH 에서 Sec-Fetch-Site(9종) x Origin(16종) 전 조합: 오라클과 일치하고, 거부된 요청은 상태를 바꾸지 않는다."""
    csrf = login(client)
    bad = []
    for origin in ORIGIN_VALUES:
        h = {"X-CSRF-Token": csrf}
        if origin is not None:
            h["Origin"] = origin
        if sec is not None:
            h["Sec-Fetch-Site"] = sec
        r = client.patch("/api/v1/settings", json={"daily_apply_cap": 7}, headers=h)
        want = _expected_allowed(sec, origin)
        got = r.status_code == 200
        if got != want or (not want and r.status_code != 403):
            bad.append((sec, origin, r.status_code))
        if want:
            client.patch("/api/v1/settings", json={"daily_apply_cap": 3}, headers=hdr(csrf))  # 다음 조합을 위해 되돌림
    assert not bad, bad
    # 거부된 요청이 값을 바꾸지 못했다: 마지막 정상 값 3 이어야 한다.
    cur = client.get("/api/v1/settings").json()["daily_apply_cap"]
    assert cur in (3, 10)


@pytest.mark.parametrize("sec", SEC_VALUES)
def test_origin_secfetch_matrix_session_issue(client, engine, sec):
    """TC-VA-@@@ [S-W02] 세션 발급 POST 에서도 같은 표가 적용되고, 거부 시 세션 행이 늘지 않는다."""
    bad = []
    for origin in ORIGIN_VALUES:
        with engine.connect() as c:
            before = c.execute(select(text("count(*)")).select_from(SessionRow)).scalar_one()
        h = {}
        if origin is not None:
            h["Origin"] = origin
        if sec is not None:
            h["Sec-Fetch-Site"] = sec
        r = client.post("/api/v1/auth/session", headers=h)
        want = _expected_allowed(sec, origin)
        with engine.connect() as c:
            after = c.execute(select(text("count(*)")).select_from(SessionRow)).scalar_one()
        if (r.status_code == 200) != want or (want and after != before + 1) or (not want and (after != before or r.status_code != 403)):
            bad.append((sec, origin, r.status_code, before, after))
    assert not bad, bad


def test_foreign_origin_with_valid_session_and_csrf_is_403_and_leaves_no_audit(client, engine):
    """TC-VA-@@@ [S-W02, S-W03, S-W16] 세션·CSRF 가 모두 유효해도 출처가 외부면 403 이고 설정/감사 행이 생기지 않는다."""
    csrf = login(client)
    with engine.connect() as c:
        n_audit = c.execute(select(text("count(*)")).select_from(AuditLog)).scalar_one()
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5},
                     headers={"Origin": "http://evil.com", "X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    with engine.connect() as c:
        assert c.execute(select(text("count(*)")).select_from(AuditLog)).scalar_one() == n_audit
        assert c.execute(select(text("count(*)")).select_from(SettingKV)).scalar_one() == 0


def test_origin_check_precedes_session_check(client):
    """TC-VA-@@@ [S-W02] 외부 출처 요청에는 세션 유무(401/403 차이)를 알리지 않는다: 세션 없는 외부 출처도 403 origin_not_allowed."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers={"Origin": "http://evil.com", "X-CSRF-Token": "x"})
    assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed"
    r2 = client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers={"Origin": ORIGIN, "X-CSRF-Token": "x"})
    assert r2.status_code == 401 and r2.json()["code"] == "session_required"


def test_state_changing_methods_never_succeed_via_get(client):
    """TC-VA-@@@ [S-W03] 상태 변경 엔드포인트에 GET 으로 접근하면 405 이고 아무것도 바뀌지 않는다(GET 으로 상태 변경 불가)."""
    csrf = login(client)
    for p in ("/api/v1/auth/session", "/api/v1/settings/x"):
        r = client.get(p)
        assert r.status_code in (404, 405)
    r = client.request("OPTIONS", "/api/v1/settings", headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "PATCH"})
    assert "access-control-allow-origin" not in r.headers  # CORS 허용 헤더를 절대 내보내지 않는다
    assert csrf


def test_no_cors_headers_ever_for_foreign_origin(client):
    """TC-VA-@@@ [S-W02] 외부 Origin 의 요청에 Access-Control-Allow-* 가 붙지 않는다(브라우저가 응답을 못 읽게)."""
    r = client.get(ME, headers={"Origin": "http://evil.com"})
    assert not [k for k in r.headers if k.lower().startswith("access-control-")]


# ---------------------------------------------------------------- 요청 크기

def _authed_cookie_and_csrf(client):
    csrf = login(client)
    cookie = "; ".join(f"{c.name}={c.value}" for c in client.cookies.jar)
    return cookie, csrf


MAX = 1024 * 1024


def _patch_headers(cookie, csrf, extra=None):
    h = [("host", "127.0.0.1:8080"), ("origin", ORIGIN), ("x-csrf-token", csrf), ("cookie", cookie),
         ("content-type", "application/json")]
    return h + (extra or [])


def test_content_length_boundary_exact_limit_and_one_over(app, client):
    """TC-VA-@@@ [S-W13] Content-Length 1048576 은 413 이 아니고, 1048577 은 413 payload_too_large."""
    cookie, csrf = _authed_cookie_and_csrf(client)
    prefix = b'{"daily_apply_cap":5}'
    ok = prefix + b" " * (MAX - len(prefix))
    over = ok + b" "
    assert len(ok) == MAX
    o1 = asgi_call(app, "PATCH", "/api/v1/settings", _patch_headers(cookie, csrf, [("content-length", str(len(ok)))]), [ok])
    assert o1["status"] != 413
    o2 = asgi_call(app, "PATCH", "/api/v1/settings", _patch_headers(cookie, csrf, [("content-length", str(len(over)))]), [over])
    assert o2["status"] == 413 and body_json(o2)["code"] == "payload_too_large"


def test_chunked_body_boundary_without_content_length(app, client):
    """TC-VA-@@@ [S-W13] Content-Length 없이 여러 조각으로 보내도 합계 1048576 까지만 허용, 1 바이트 초과 시 413 이며 설정은 바뀌지 않는다."""
    cookie, csrf = _authed_cookie_and_csrf(client)
    prefix = b'{"daily_apply_cap":6}'
    pad = MAX - len(prefix)
    chunks_ok = [prefix] + [b" " * 65536] * (pad // 65536) + [b" " * (pad % 65536)]
    assert sum(map(len, chunks_ok)) == MAX
    o1 = asgi_call(app, "PATCH", "/api/v1/settings", _patch_headers(cookie, csrf), chunks_ok)
    assert o1["status"] == 200, o1
    chunks_over = chunks_ok + [b" "]
    csrf2 = csrf
    o2 = asgi_call(app, "PATCH", "/api/v1/settings", _patch_headers(cookie, csrf2).copy() , [b'{"daily_apply_cap":9}'] + [b" " * 65536] * 16 + [b" "])
    assert o2["status"] == 413, o2
    assert body_json(o2)["code"] == "payload_too_large"
    assert client.get("/api/v1/settings").json()["daily_apply_cap"] == 6  # 413 요청의 9 는 적용되지 않았다
    assert chunks_over


@pytest.mark.parametrize("cl", ["abc", "1.5", "", "0x10"])
def test_garbage_content_length_rejected_400(app, cl):
    """TC-VA-@@@ [S-W13] 숫자가 아닌 Content-Length 는 400 bad_content_length(500 이 아님)."""
    out = asgi_call(app, "POST", "/api/v1/auth/session",
                    [("host", "127.0.0.1:8080"), ("origin", ORIGIN), ("content-length", cl)], [b""])
    assert out["status"] in (400, 422), out["status"]
    assert out["status"] != 500


@pytest.mark.xfail(strict=True, reason="DEF-6-002: Python int() 가 '-1', '+5', '1_0' 을 숫자로 받아 가드가 통과시킴(실서버 h11 은 앞단에서 거부 -> Low)")
@pytest.mark.parametrize("cl", ["-1", "+5", "1_0"])
def test_nonstandard_numeric_content_length_rejected(app, cl):
    """TC-VA-@@@ [S-W13] RFC 9110 의 1*DIGIT 가 아닌 Content-Length('-1','+5','1_0')도 가드가 거부해야 한다."""
    out = asgi_call(app, "GET", ME, [("host", "127.0.0.1:8080"), ("content-length", cl)])
    assert out["status"] == 400


def test_oversize_rejected_before_auth_and_before_handler(app, engine):
    """TC-VA-@@@ [S-W13] 인증 없는 1MB+1 요청도 인증 검사 전에 413 으로 잘린다(핸들러 미도달)."""
    out = asgi_call(app, "POST", "/api/v1/auth/session",
                    [("host", "127.0.0.1:8080"), ("origin", ORIGIN), ("content-length", str(MAX + 1))], [b"x" * (MAX + 1)])
    assert out["status"] == 413
    with engine.connect() as c:
        assert c.execute(select(text("count(*)")).select_from(SessionRow)).scalar_one() == 0


# ---------------------------------------------------------------- 속도 제한

def _limited_app(web_settings, clock, fake_time, **limits):
    return create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time, rate_limits=RateLimits(**limits))


def test_rate_limit_global_boundary_and_window_edge(web_settings, engine, clock, fake_time):
    """TC-VA-@@@ [S-W13] 전역 한도 N 번째까지 200, N+1 번째 429(Retry-After 1~60 정수), 창 경계 59.9초 후 아직 429, 정확히 60초 후 200."""
    app = _limited_app(web_settings, clock, fake_time, global_per_min=5, write_per_min=100, auth_per_min=100)
    h = [("host", "127.0.0.1:8080")]
    for i in range(5):
        assert asgi_call(app, "GET", ME, h)["status"] == 200, i
    out = asgi_call(app, "GET", ME, h)
    assert out["status"] == 429 and body_json(out)["code"] == "rate_limited"
    ra = int(header(out, "retry-after"))
    assert 1 <= ra <= 60
    fake_time.t += 59.9
    assert asgi_call(app, "GET", ME, h)["status"] == 429  # 거부된 요청은 기록되지 않아 창이 늘어나지 않는다
    fake_time.t += 0.1
    assert asgi_call(app, "GET", ME, h)["status"] == 200


def test_rate_limit_excludes_health_and_host_rejected(web_settings, engine, clock, fake_time):
    """TC-VA-@@@ [S-W13] 헬스 경로와 Host 거부 요청은 한도를 소모하지 않는다."""
    app = _limited_app(web_settings, clock, fake_time, global_per_min=3, write_per_min=100, auth_per_min=100)
    for _ in range(30):
        assert asgi_call(app, "GET", "/api/healthz", [("host", "api:8000")])["status"] == 200
        assert asgi_call(app, "GET", ME, [("host", "evil.com")])["status"] == 403
    for _ in range(3):
        assert asgi_call(app, "GET", ME, [("host", "127.0.0.1:8080")])["status"] == 200


def test_rate_limit_write_and_auth_buckets_separate(web_settings, engine, clock, fake_time):
    """TC-VA-@@@ [S-W13] 쓰기 한도와 세션 발급 한도는 각자 따로 걸리고, 쓰기 한도가 찬 뒤에도 GET 은 통과한다."""
    app = _limited_app(web_settings, clock, fake_time, global_per_min=1000, write_per_min=3, auth_per_min=2)
    h = [("host", "127.0.0.1:8080"), ("origin", ORIGIN), ("content-type", "application/json")]
    s = [asgi_call(app, "POST", "/api/v1/auth/session", h, [b"{}"])["status"] for _ in range(3)]
    assert s == [200, 200, 429]  # auth 한도 2
    assert asgi_call(app, "PATCH", "/api/v1/settings", h, [b"{}"])["status"] == 401  # 쓰기 3번째(앞서 2 + 이 1)
    assert asgi_call(app, "PATCH", "/api/v1/settings", h, [b"{}"])["status"] == 429  # 쓰기 한도 3 초과
    assert asgi_call(app, "GET", ME, h)["status"] == 200


@pytest.mark.xfail(strict=True, reason="DEF-6-003: 속도 제한이 Origin/Sec-Fetch-Site 검증보다 앞서 외부 사이트 요청이 한도를 소진해 소유자 로그인·화면을 막을 수 있음(DoS)")
def test_cross_site_requests_do_not_exhaust_owner_rate_limit(web_settings, engine, clock, fake_time):
    """TC-VA-@@@ [S-W02, S-W13] 외부 사이트(cross-site)가 보낸 요청은 소유자의 세션 발급 한도를 소모하지 않아야 한다."""
    app = _limited_app(web_settings, clock, fake_time, global_per_min=600, write_per_min=120, auth_per_min=10)
    evil = [("host", "127.0.0.1:8080"), ("origin", "http://evil.com"), ("sec-fetch-site", "cross-site")]
    for _ in range(10):
        assert asgi_call(app, "POST", "/api/v1/auth/session", evil, [b""])["status"] == 403
    owner = [("host", "127.0.0.1:8080"), ("origin", ORIGIN), ("sec-fetch-site", "same-origin")]
    assert asgi_call(app, "POST", "/api/v1/auth/session", owner, [b""])["status"] == 200


# ---------------------------------------------------------------- 보안 헤더 / 오류 형식

def _assert_sec_headers(out, api=True):
    assert header(out, "x-content-type-options") == "nosniff"
    assert header(out, "x-frame-options") == "DENY"
    assert header(out, "referrer-policy") == "no-referrer"
    assert "frame-ancestors 'none'" in (header(out, "content-security-policy") or "")
    assert header(out, "permissions-policy")
    assert header(out, "x-request-id")
    if api:
        assert header(out, "cache-control") == "no-store"
        assert "default-src 'none'" in header(out, "content-security-policy")


def test_security_headers_on_every_api_response_class(app, web_settings):
    """TC-VA-@@@ [S-W04] 보안 헤더가 200/401/403(Host)/404/405/413/422 응답 모두에 붙는다."""
    good = [("host", "127.0.0.1:8080")]
    cases = [
        asgi_call(app, "GET", ME, good),
        asgi_call(app, "GET", "/api/v1/settings", good),                         # 401
        asgi_call(app, "GET", ME, [("host", "evil.com")]),                       # 403 host
        asgi_call(app, "GET", "/api/v1/nope", good),                             # 404
        asgi_call(app, "DELETE", ME, good),                                      # 405
        asgi_call(app, "POST", "/api/v1/auth/session", good + [("origin", ORIGIN), ("content-length", str(MAX + 1))], [b"x" * (MAX + 1)]),  # 413
        asgi_call(app, "POST", "/api/v1/auth/session", good + [("origin", ORIGIN), ("content-type", "application/json")], [b'{"pin": 5}']),  # 422
    ]
    assert [c["status"] for c in cases] == [200, 401, 403, 404, 405, 413, 422]
    for c in cases:
        _assert_sec_headers(c)


def test_problem_json_shape_and_request_id_unique(app):
    """TC-VA-@@@ [S-W09] 모든 오류는 problem+json 이고 키가 {type,title,status,detail,code,hint} 뿐이며 요청 ID 는 요청마다 다르다."""
    ids = set()
    for path in ("/api/v1/settings", "/api/v1/nope"):
        for _ in range(3):
            out = asgi_call(app, "GET", path, [("host", "127.0.0.1:8080")])
            assert header(out, "content-type").startswith("application/problem+json")
            j = body_json(out)
            assert set(j) == {"type", "title", "status", "detail", "code", "hint"}
            assert j["status"] == out["status"]
            ids.add(header(out, "x-request-id"))
    assert len(ids) == 6 and all(len(i) == 32 for i in ids)


def test_docs_and_openapi_hidden_by_default(app):
    """TC-VA-@@@ [S-W04] enable_docs=False 이면 /docs /redoc /openapi.json 이 404 다."""
    for p in ("/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"):
        assert asgi_call(app, "GET", p, [("host", "127.0.0.1:8080")])["status"] == 404


def test_websocket_upgrade_refused_without_reaching_app(app):
    """TC-VA-@@@ [S-W02] 웹소켓 스코프는 Host 와 무관하게 1008 로 닫는다."""
    import asyncio
    sent = []

    async def go():
        async def recv():
            return {"type": "websocket.connect"}

        async def snd(m):
            sent.append(m)
        await app({"type": "websocket", "path": "/api/v1/ws", "headers": [(b"host", b"127.0.0.1:8080")], "query_string": b""}, recv, snd)

    asyncio.run(go())
    assert sent and sent[0]["type"] == "websocket.close" and sent[0]["code"] == 1008
