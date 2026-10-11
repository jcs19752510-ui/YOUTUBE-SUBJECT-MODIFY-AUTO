"""IT 그룹 N — nginx 경유 경계(W-INF nginx ↔ W-BE-A 가드 ↔ W-FE 정적 파일).

단위 시험이 이미 증명한 것(설정 문자열, 일회용 컨테이너)을 되풀이하지 않고, 실제 5개 컨테이너가 함께 떠 있을 때
브라우저가 보게 되는 최종 응답(헤더 한 벌, 프록시 경로, 이중 방어의 계층 구분)을 확인한다.
"""
from __future__ import annotations

import json
import re
import threading
import time

import httpx
import pytest

from itlib import (
    BASE, HOST_OK, ORIGIN_OK, PORT, PROJECT, Api, dc, dexec, inside_api_python, parse_raw, raw_request, wait_healthy,
)

CSP_EXPECTED = (
    "default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
# W-FIX-INF(DEF-7-007): /api 응답(JSON)은 아무것도 불러오지 못하게 default-src 'none' 한 벌을 쓴다(nginx security-headers-api.conf).
CSP_API_EXPECTED = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
SEC_HEADERS = {
    "content-security-policy": CSP_EXPECTED,
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}


def _get(path: str, method: str = "GET", headers: dict | None = None, **kw) -> httpx.Response:
    h = {"Host": HOST_OK}
    h.update(headers or {})
    with httpx.Client(base_url=BASE, timeout=15) as c:
        return c.request(method, path, headers=h, **kw)


def _asset_paths() -> list[str]:
    html = _get("/").text
    return re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)


# ─────────────────────────── 보안 헤더 한 벌 ───────────────────────────

def test_it_001_security_headers_exactly_one_set_everywhere():
    """IT-001: 정적·SPA 대체·API(정상/401/404)·nginx 자체 오류(403/404/405)에서 7종 헤더가 정확히 한 벌이고 nginx 값이다(백엔드의 다른 값이 섞이지 않는다).
    검증: S-W04, NFR-W06(보안 헤더), TB-W3"""
    assets = _asset_paths()
    assert assets, "index.html 에 /assets 참조가 없음"
    cases = [
        ("GET", "/", 200), ("GET", assets[0], 200), ("GET", "/videos/abc/def", 200),  # SPA 대체(index.html)
        ("GET", "/assets/not-there.js", 404),
        ("GET", "/api/v1/dashboard", 401),
        ("GET", "/api/v1/not-there", 404),
        ("GET", "/api/healthz", 200), ("GET", "/api/readyz", 200), ("GET", "/nginx-health", 200),
        ("PUT", "/", 403), ("DELETE", "/assets/x.js", 403),
        ("TRACE", "/", 405),
        ("PATCH", "/api/v1/auth/session", 403),  # nginx limit_except(세션 경로는 GET/HEAD/POST/DELETE 만)
    ]
    for method, path, want in cases:
        r = _get(path, method)
        assert r.status_code == want, (method, path, r.status_code, r.text[:120])
        for name, val in SEC_HEADERS.items():
            if name == "content-security-policy" and path.startswith("/api/"):
                val = CSP_API_EXPECTED
            got = r.headers.get_list(name)
            assert got == [val], (method, path, name, got)
        assert r.headers.get("server") == "nginx", (path, r.headers.get("server"))  # 버전 비노출
        for leak in ("x-powered-by", "via", "x-aspnet-version"):
            assert leak not in r.headers


def test_it_002_cache_and_compression_policy():
    """IT-002: 정적(해시 파일 immutable, index no-cache)·API(no-store) 캐시 정책과 gzip 이 실제로 적용된다. 검증: NFR-W06, W-003 화면 로딩"""
    assets = _asset_paths()
    js = next(a for a in assets if a.endswith(".js"))
    r = _get(js, headers={"Accept-Encoding": "gzip"})
    assert r.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert r.headers.get("content-encoding") == "gzip"
    assert r.headers["content-type"].startswith(("application/javascript", "text/javascript"))
    assert len(r.content) > 1000  # httpx 가 gzip 을 이미 풀었다
    r = _get("/", headers={"Accept-Encoding": "gzip"})
    assert r.headers["cache-control"] == "no-cache"
    r = _get("/api/healthz")
    assert {v.strip() for x in r.headers.get_list("cache-control") for v in x.split(",")} == {"no-store"}
    # 소스맵은 이미지에 없다(최종 이미지에 소스 비노출)
    assert _get(js + ".map").status_code == 404


def test_it_003_no_docs_no_openapi_no_dotfiles():
    """IT-003: /docs·/openapi.json 은 API 문서가 노출되지 않고(꺼짐), 점 파일·상위 경로 탈출·디렉터리 목록이 열리지 않는다. 검증: S-W04/W13, 정보 노출"""
    for p in ("/api/openapi.json", "/api/docs", "/api/redoc", "/openapi.json"):
        r = _get(p)
        assert r.status_code in (404, 200)
        if r.status_code == 200:
            assert r.headers["content-type"].startswith("text/html"), p  # SPA 대체 index.html 이지 API 문서가 아님
            assert "openapi" not in r.text[:400].lower() and "swagger" not in r.text.lower()
    r = _get("/api/openapi.json")
    assert r.status_code == 404 and r.json()["code"]
    r = _get("/docs")
    assert "swagger" not in r.text.lower()
    for p in ("/.git/config", "/.env", "/..%2f..%2fetc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/assets/", "/assets/../index.html"):
        r = _get(p)
        assert "root:x:" not in r.text
        assert "[core]" not in r.text
    r = raw_parse(b"GET /../../../../etc/passwd HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n")
    assert "root:x:" not in r[2].decode("latin-1")
    # nginx 뒤가 아니라 백엔드 자신이 문서를 끄고 있는가(두 번째 층: 설정 한 줄이 바뀌어도 nginx 경로 때문에 가려지지 않게 직접 확인)
    script = """
import http.client, json
out = {}
for p in ("/openapi.json", "/docs", "/redoc", "/api/openapi.json", "/api/docs", "/docs/oauth2-redirect"):
    c = http.client.HTTPConnection("127.0.0.1", 8000, timeout=10)
    c.request("GET", p, headers={"Host": "127.0.0.1:8080"})
    r = c.getresponse(); b = r.read().decode("utf-8", "replace")
    out[p] = [r.status, "swagger" in b.lower() or '"openapi"' in b]
print(json.dumps(out))
"""
    p = inside_api_python(script)
    assert p.returncode == 0, p.stderr[-300:]
    d = json.loads(p.stdout.strip().splitlines()[-1])
    assert all(v[0] == 404 and v[1] is False for v in d.values()), d


def raw_parse(data: bytes):
    return parse_raw(raw_request(data))


# ─────────────────────────── Host 허용 목록 ───────────────────────────

@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1", "127.0.0.1:8081", "localhost", "127.0.0.1.:8080", "0.0.0.0:8080",
                                  "[::1]:8080", "127.0.0.1:8080.evil.example", "evil.example:8080", " 127.0.0.1:8080x", ""])
def test_it_010_host_not_allowed_gets_no_response(host):
    """IT-010: 허용 목록 밖 Host 는 응답 없이 연결이 닫힌다(444). 정적·API·헬스 경로 모두. 검증: S-W02, TB-W1(DNS 리바인딩)"""
    for path in ("/", "/api/v1/auth/me", "/api/healthz", "/nginx-health"):
        data = f"GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode()
        resp = raw_request(data)
        # 444(응답 없이 종료) 또는 문법이 잘못된 Host 에 대한 nginx 자체 400(앱까지 가지 않음). 200 이면 우회
        assert resp == b"" or (parse_raw(resp)[0] == 400 and b"nginx" in resp.lower()), (host, path, resp[:80])


def test_it_011_host_duplicate_and_smuggling_forms():
    """IT-011: Host 중복·절대 URI·HTTP/1.0 무 Host·개행 삽입이 허용 목록을 우회하지 못한다. 검증: S-W02"""
    ok = b"Host: 127.0.0.1:8080\r\n"
    bad = b"Host: evil.example\r\n"
    for req in (
        b"GET /api/v1/auth/me HTTP/1.1\r\n" + bad + ok + b"Connection: close\r\n\r\n",
        b"GET /api/v1/auth/me HTTP/1.1\r\n" + ok + bad + b"Connection: close\r\n\r\n",
        b"GET http://evil.example/api/v1/auth/me HTTP/1.1\r\nHost: evil.example\r\nConnection: close\r\n\r\n",
        b"GET /api/v1/auth/me HTTP/1.0\r\n\r\n",
    ):
        st, _, body = parse_raw(raw_request(req))
        assert st in (0, 400, 403, 444), (req[:60], st)  # 200 이면 우회 성공
    # 허용 Host + 절대 URI(호스트는 허용): 어느 쪽이든 200 이면 곧 허용 Host 로 응답한 것이어야 한다(보안 동치)
    st, _, body = parse_raw(raw_request(b"GET http://127.0.0.1:8080/api/healthz HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n"))
    assert st == 200
    # 대소문자: nginx map 은 정확 일치라 대문자 Host 는 거부될 수 있다(더 엄격한 쪽은 안전). 허용 이면 200 이어야 한다
    st, _, _ = parse_raw(raw_request(b"GET /api/healthz HTTP/1.1\r\nHost: LOCALHOST:8080\r\nConnection: close\r\n\r\n"))
    assert st in (0, 200)


def test_it_012_both_allowed_hosts_work_and_origin_must_match_host_family():
    """IT-012: localhost:8080 도 끝까지(세션 발급 → 조회) 동작하고, Origin 이 다른 가족(127.0.0.1 ↔ localhost)이어도 허용 목록 안이면 통과한다. 검증: S-W02, API.md 1-1"""
    a = Api(host="localhost:8080", origin="http://localhost:8080")
    r = a.login()
    assert r.status_code == 200, r.text
    assert a.get("/api/v1/dashboard").status_code == 200
    # 같은 쿠키·CSRF 로 Origin 만 127.0.0.1 로 바꿔 상태 변경: 허용 출처 둘 중 하나이므로 허용
    r = a.patch("/api/v1/settings", json={"daily_apply_cap": 10}, headers={"Origin": ORIGIN_OK})
    assert r.status_code == 200, r.text
    a.close()


# ─────────────────────────── 쿠키·출처 ───────────────────────────

def test_it_020_cookie_attributes_and_scope_over_plain_http(owner):
    """IT-020: 쿠키 속성(HttpOnly·SameSite=Strict·Path=/api·Max-Age, Secure/Domain 없음)과, Secure 가 없어 평문 HTTP 로 그대로 오가는 실제 영향 범위.
    검증: S-W04, SEC-W20. 쿠키는 /api 경로에만 붙고 정적 경로 요청에는 붙지 않는다."""
    with httpx.Client(base_url=BASE, headers={"Host": HOST_OK}, timeout=10) as c:
        r = c.post("/api/v1/auth/session", json={}, headers={"Origin": ORIGIN_OK})
        assert r.status_code == 200
        sc = r.headers.get_list("set-cookie")
        assert len(sc) == 1
        ck = sc[0]
        assert ck.startswith("ytw_session=")
        low = ck.lower()
        assert "httponly" in low and "samesite=strict" in low and "path=/api" in low and "max-age=43200" in low
        assert "secure" not in low and "domain=" not in low
        token = ck.split(";")[0].split("=", 1)[1]
        assert len(token) >= 32
        # 요청 경로별 쿠키 전송(브라우저 동작 모의): /api 에서만 세션 인정
        assert c.get("/api/v1/auth/me").json()["authenticated"] is True
        # 토큰 원문은 DB 에 없다(sha256 만): 앱 계정으로 조회해 원문이 어디에도 없는지 확인
        from itlib import psql_app
        ids = psql_app("select id from sessions")
        assert token not in ids
        # 쿠키 이름/값은 nginx 접근 로그에 남지 않는다
    logs = dc("logs", "--no-log-prefix", "web").stdout
    assert token not in logs


@pytest.mark.parametrize("extra,want", [
    ({"Origin": "http://evil.example"}, 403),
    ({"Origin": "http://127.0.0.1:8081"}, 403),
    ({"Origin": "null"}, 403),
    ({"Origin": ORIGIN_OK, "Sec-Fetch-Site": "cross-site"}, 403),
    ({"Origin": ORIGIN_OK, "Sec-Fetch-Site": "same-site"}, 403),
    ({"Origin": ORIGIN_OK, "Sec-Fetch-Site": "same-origin"}, 200),
])
def test_it_021_origin_and_fetch_site_through_nginx(owner, extra, want):
    """IT-021: 상태 변경의 Origin·Sec-Fetch-Site 판정이 nginx 프록시 뒤에서도 그대로 동작한다(헤더가 잘리거나 덮이지 않는다). 검증: S-W02, S-W03"""
    h = {"X-CSRF-Token": owner.csrf, **extra}
    r = owner.c.patch("/api/v1/settings", json={"daily_apply_cap": 10}, headers=h)
    assert r.status_code == want, (extra, r.status_code, r.text[:200])
    if want == 403:
        assert r.headers["content-type"].startswith("application/problem+json")
        assert r.json()["code"] in ("origin_not_allowed", "cross_site_request")


def test_it_022_csrf_and_missing_origin_and_get_cannot_mutate(owner):
    """IT-022: CSRF 토큰 누락·오류, Origin 없음, GET 으로 상태 변경 시도는 모두 거부된다. 검증: S-W02, S-W03"""
    r = owner.c.patch("/api/v1/settings", json={"daily_apply_cap": 10}, headers={"Origin": ORIGIN_OK})
    assert r.status_code == 403 and r.json()["code"] == "csrf_invalid"
    r = owner.c.patch("/api/v1/settings", json={"daily_apply_cap": 10}, headers={"Origin": ORIGIN_OK, "X-CSRF-Token": "x" * 40})
    assert r.status_code == 403
    r = owner.c.patch("/api/v1/settings", json={"daily_apply_cap": 10}, headers={"X-CSRF-Token": owner.csrf})
    assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed"
    before = owner.get("/api/v1/dashboard").json()["counts"]
    for path in ("/api/v1/videos/sync", "/api/v1/batches/1/execute", "/api/v1/changes/1/rollback", "/api/v1/suggestions/1/approve"):
        r = owner.get(path)
        assert r.status_code in (404, 405, 422), (path, r.status_code)  # 422: 경로 변수로 해석됨(변경 아님)
    assert owner.get("/api/v1/dashboard").json()["counts"] == before


def test_it_023_logout_invalidates_server_side_even_if_cookie_replayed():
    """IT-023: 로그아웃하면 서버의 세션 행이 지워져, 훔친(복제한) 쿠키를 재사용해도 401 이다. 검증: SEC-W20, S-W02"""
    a = Api()
    assert a.login().status_code == 200
    stolen = a.c.cookies.get("ytw_session")
    assert a.delete("/api/v1/auth/session").status_code == 204
    b = Api()
    b.c.cookies.set("ytw_session", stolen, domain="127.0.0.1", path="/api")
    r = b.get("/api/v1/dashboard")
    assert r.status_code == 401
    assert b.get("/api/v1/auth/me").json()["authenticated"] is False
    a.close(); b.close()


# ─────────────────────────── 프록시 경로·메서드 ───────────────────────────

def test_it_030_proxy_paths_and_error_format_reach_browser_intact(owner):
    """IT-030: /api 프록시가 응답 본문(problem+json)·상태·Retry-After·X-Request-Id 를 보존하고, 알 수 없는 /api 경로는 SPA 가 아니라 JSON 404 를 준다.
    검증: API.md 1-2·1-7, W-017"""
    r = owner.get("/api/v1/nothing-here")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] and r.headers.get("x-request-id")
    r = owner.get("/api/v1/videos/BADID")
    assert r.status_code in (404, 422)
    assert r.headers["content-type"].startswith("application/problem+json")
    # 헬스 경로 두 쌍(/healthz 는 nginx 가 /api/healthz 만 프록시)
    assert _get("/api/healthz").json() == {"status": "ok"}
    d = _get("/api/readyz").json()
    assert d == {"status": "ok", "db": "ok", "mode": "demo"}
    # 루트 /healthz·/readyz 는 일부러 닫았다(DEF-7-006): SPA HTML 200 대신 404 (상태 확인은 /api/healthz·/api/readyz 만)
    for root_path in ("/healthz", "/readyz"):
        rr = _get(root_path)
        assert rr.status_code == 404 and rr.headers["content-type"].startswith("text/plain"), (root_path, rr.status_code, rr.headers["content-type"])
    # 쿼리 문자열·한글·인코딩 보존
    vs = owner.get("/api/v1/videos", params={"q": "냉장고", "page_size": 5})
    assert vs.status_code == 200
    assert all("냉장고" in v["title"] or "냉장고" in v["video_id"] for v in vs.json()["items"])


def test_it_031_methods_allowed_by_location():
    """IT-031: nginx 메서드 제한이 실제로 적용된다(정적은 GET/HEAD 만, /api 는 5종, TRACE/OPTIONS/CONNECT 차단). 검증: TB-W3(메서드 제한·TRACE 차단)"""
    assert _get("/", "HEAD").status_code == 200
    for m in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
        assert _get("/", m).status_code == 403, m
    assert _get("/api/v1/dashboard", "OPTIONS").status_code == 403
    assert _get("/api/v1/dashboard", "TRACE").status_code == 405
    st, _, _ = parse_raw(raw_request(b"CONNECT 127.0.0.1:8080 HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n"))
    assert st in (400, 403, 405, 0)
    st, _, _ = parse_raw(raw_request(b"FOO / HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nConnection: close\r\n\r\n"))
    assert st in (400, 403, 405, 501)


# ─────────────────────────── 크기·시간 제한 ───────────────────────────

def _post_session_body(n: int, chunked: bool = False) -> int:
    h = {"Host": HOST_OK, "Origin": ORIGIN_OK, "Content-Type": "application/json"}
    body = b" " * (n - 2) + b"{}"
    with httpx.Client(base_url=BASE, timeout=20) as c:
        if chunked:
            def gen():
                for i in range(0, len(body), 65536):
                    yield body[i:i + 65536]
            r = c.post("/api/v1/auth/session", content=gen(), headers=h)
        else:
            r = c.post("/api/v1/auth/session", content=body, headers=h)
    return r.status_code


def test_it_040_body_limits_nginx_layer_and_backend_layer():
    """IT-040: 본문 1MB 제한이 nginx(Content-Length·chunked)와 백엔드(컨테이너 안에서 nginx 우회) 양쪽에서 독립적으로 적용된다.
    경계: 정확히 1 MiB 는 두 계층 모두 통과(백엔드가 내용을 본다), 1 MiB+1 은 거부. 검증: S-W13, NFR-W06"""
    MB = 1024 * 1024
    # 세션 발급 경로는 속도 제한이 빡빡하므로 크기 시험은 설정 PATCH(쓰기 120/분)로 한다 — 로그인 한 번만
    a = Api()
    assert a.login().status_code == 200
    def patch_len(n: int, chunked: bool) -> httpx.Response:
        body = b" " * (n - 2) + b"{}"
        h = {"Origin": ORIGIN_OK, "X-CSRF-Token": a.csrf, "Content-Type": "application/json"}
        if chunked:
            def gen():
                for i in range(0, len(body), 65536):
                    yield body[i:i + 65536]
            return a.c.patch("/api/v1/settings", content=gen(), headers=h)
        return a.c.patch("/api/v1/settings", content=body, headers=h)
    r = patch_len(MB, False)
    assert r.status_code == 400 and r.json()["code"] == "setting_not_allowed" or r.status_code in (200, 400, 422), (r.status_code, r.text[:200])
    assert r.status_code != 413                       # 경계 정확히 1 MiB: nginx·백엔드 모두 통과
    r = patch_len(MB + 1, False)
    assert r.status_code == 413
    assert r.headers["content-type"].startswith("text/html")   # nginx 가 직접 거절(백엔드는 problem+json)
    assert r.headers.get_list("content-security-policy") == [CSP_API_EXPECTED]     # /api/ location 이 만든 오류라 JSON 용 헤더 파일 적용(DEF-7-007)
    r = patch_len(2 * MB, True)
    assert r.status_code == 413
    # 백엔드 계층(nginx 우회): api 컨테이너 안에서 127.0.0.1:8000 으로 직접
    script = f'''
import http.client, json
MB={MB}
def req(method, path, body=None, headers=None, chunked=False):
    c = http.client.HTTPConnection("127.0.0.1", 8000, timeout=20)
    h = {{"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080"}}; h.update(headers or {{}})
    if chunked:
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in h.items(): c.putheader(k, v)
        c.putheader("Transfer-Encoding", "chunked"); c.endheaders()
        for i in range(0, len(body), 65536):
            ch = body[i:i+65536]; c.send(("%x\\r\\n" % len(ch)).encode() + ch + b"\\r\\n")
        c.send(b"0\\r\\n\\r\\n")
    else:
        c.request(method, path, body=body, headers=h)
    r = c.getresponse(); b = r.read()
    return r.status, r.getheader("content-type"), json.loads(b) if b[:1] == b"{{" else None
out = {{}}
out["exact"] = req("POST", "/api/v1/auth/session", b" " * (MB-2) + b"{{}}", {{"Content-Type": "application/json"}})[0]
out["over"] = req("POST", "/api/v1/auth/session", b" " * (MB-1) + b"{{}}", {{"Content-Type": "application/json"}})[:3]
out["chunked_over"] = req("POST", "/api/v1/auth/session", b"x" * (MB + 5), {{"Content-Type": "application/json"}}, chunked=True)[:3]
# 헤더만 보내고 본문은 보내지 않는 큰 Content-Length: 본문을 기다리지 않고 즉시 413 (자원 점유 방지)
import socket, time
sk = socket.create_connection(("127.0.0.1", 8000), timeout=4)
sk.sendall(b"POST /api/v1/auth/session HTTP/1.1\\r\\nHost: 127.0.0.1:8080\\r\\nOrigin: http://127.0.0.1:8080\\r\\nContent-Type: application/json\\r\\nContent-Length: 5000000\\r\\n\\r\\n")
t0 = time.time()
try:
    first = sk.recv(200)
except Exception:
    first = b""
out["cl_only"] = [first.split(b" ")[1].decode() if first.startswith(b"HTTP") else "none", round(time.time() - t0, 1)]
sk.close()
out["neg_cl"] = req("POST", "/api/v1/auth/session", b"{{}}", {{"Content-Length": "-1", "Content-Type": "application/json"}})[:3] if False else None
print(json.dumps(out))
'''
    p = inside_api_python(script)
    assert p.returncode == 0, p.stderr[-500:]
    d = json.loads(p.stdout.strip().splitlines()[-1])
    assert d["exact"] != 413
    assert d["over"][0] == 413 and d["over"][1].startswith("application/problem+json") and d["over"][2]["code"] == "payload_too_large"
    assert d["chunked_over"][0] == 413 and d["chunked_over"][2]["code"] == "payload_too_large"
    assert d["cl_only"][0] == "413" and d["cl_only"][1] < 2.0, d["cl_only"]    # 큰 Content-Length 는 본문을 받기 전에 거절
    a.close()


def test_it_041_malformed_content_length_and_slow_request_closed():
    """IT-041: 음수·중복 Content-Length 는 두 계층 어디에서든 거부되고(200 불가), 헤더를 천천히 보내는 연결은 nginx 가 10초 안에 끊는다(slowloris 완화). 검증: S-W13, NFR-W05"""
    base = b"POST /api/v1/auth/session HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nOrigin: http://127.0.0.1:8080\r\nContent-Type: application/json\r\n"
    for cl in (b"Content-Length: -1\r\n", b"Content-Length: 2\r\nContent-Length: 2\r\n", b"Content-Length: 1_0\r\n", b"Content-Length: +2\r\n"):
        st, _, _ = parse_raw(raw_request(base + cl + b"Connection: close\r\n\r\n{}"))
        assert st in (0, 400), (cl, st)
    import socket
    s = socket.create_connection(("127.0.0.1", PORT), timeout=20)
    t0 = time.time()
    s.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nX-Slow: ")
    try:
        data = s.recv(1024)  # 10초 헤더 타임아웃 → nginx 가 408 또는 연결 종료
    except (TimeoutError, OSError):
        data = b"timeout"
    dt = time.time() - t0
    s.close()
    assert data != b"timeout" and 8 <= dt <= 16, (dt, data[:50])
    st = parse_raw(data)[0] if data.startswith(b"HTTP") else 0
    assert st in (0, 408)


# ─────────────────────────── 속도 제한 이중 계층 ───────────────────────────

@pytest.mark.destructive
def test_it_050_rate_limits_two_layers_session_issue():
    """IT-050: 세션 발급 제한이 두 계층에서 순서대로 걸린다. 깨끗한 상태(api·web 재시작)에서 연속 14회 발급: 처음 10회 200, 11번째는 백엔드(problem+json
    rate_limited + Retry-After), 12번째부터는 nginx(text/html 429). 제한이 풀린 뒤(약 60초) 다시 발급된다. 검증: S-W13, NFR-W06, API.md 1-3"""
    dc("restart", "api", "web", timeout=240)
    wait_healthy(120)
    time.sleep(3)
    a = Api(throttle=0)
    codes = []
    kinds = []
    for _ in range(14):
        r = a.login(patient=False)
        codes.append(r.status_code)
        kinds.append(r.headers.get("content-type", "").split(";")[0])
    assert codes[:10] == [200] * 10, codes
    assert codes[10] == 429 and kinds[10] == "application/problem+json", (codes, kinds)
    b = a.c.post("/api/v1/auth/session", json={}, headers={"Origin": ORIGIN_OK})
    assert b.status_code == 429
    assert all(c == 429 for c in codes[10:]), codes
    assert kinds[11:] and all(k == "text/html" for k in kinds[11:]), kinds   # nginx 계층
    # 복구: 슬라이딩 1분 경과 후
    t0 = time.time()
    while time.time() - t0 < 80:
        if a.login(patient=False).status_code == 200:
            break
        time.sleep(3)
    else:
        raise AssertionError("제한이 80초 안에 풀리지 않음")
    a.close()


@pytest.mark.destructive
def test_it_051_rate_limit_api_general_and_write_limit():
    """IT-051: /api/ 일반 제한(초당 30·버스트 60: nginx HTML 429)과 백엔드 쓰기 제한(분당 120: problem+json 429)이 각각 걸리고, 429 가 서버 상태를 바꾸지 않는다.
    검증: S-W13, NFR-W06"""
    dc("restart", "api", "web", timeout=240)
    wait_healthy(120)
    time.sleep(3)
    a = Api(throttle=0)
    assert a.login().status_code == 200
    # (1) 읽기 폭주 200건 — 스레드로 동시에(순간 폭주)
    res = []
    lock = threading.Lock()
    cookie = a.c.cookies.get("ytw_session")
    def worker(k: int):
        with httpx.Client(base_url=BASE, headers={"Host": HOST_OK}, cookies={"ytw_session": cookie}, timeout=30) as c:
            for _ in range(k):
                r = c.get("/api/v1/auth/me", headers={"Origin": ORIGIN_OK})
                with lock:
                    res.append((r.status_code, r.headers.get("content-type", "").split(";")[0]))
    ts = [threading.Thread(target=worker, args=(10,)) for _ in range(20)]  # 20 연결 x 10건 = 200건을 동시에
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(res) == 200
    n429 = [x for x in res if x[0] == 429]
    assert len(n429) >= 20, f"nginx 속도 제한이 걸리지 않음: {len(n429)}"
    assert all(x[1] == "text/html" for x in n429), set(x[1] for x in n429)
    assert sum(1 for x in res if x[0] == 200) >= 50
    time.sleep(4)
    assert a.get("/api/v1/auth/me").status_code == 200
    # (2) 쓰기 제한: nginx 한도 아래(초당 ~20건)로 125건 — 백엔드가 막아야 한다(분당 120)
    before = a.get("/api/v1/settings").json()
    out = []
    t0 = time.time()
    for i in range(130):
        r = a.c.patch("/api/v1/settings", json={"suggestions_per_video": 3}, headers={"Origin": ORIGIN_OK, "X-CSRF-Token": a.csrf})
        out.append((r.status_code, r.headers.get("content-type", "").split(";")[0], r.headers.get("retry-after")))
        time.sleep(0.04)
    assert time.time() - t0 < 60, "60초 안에 끝나야 윈도 안에서 센 것"
    bad = [x for x in out if x[0] == 429]
    assert bad, f"백엔드 쓰기 제한이 걸리지 않음: {set(x[0] for x in out)}"
    assert all(x[1] == "application/problem+json" and x[2] and int(x[2]) >= 1 for x in bad), bad[:3]
    assert a.get("/api/v1/settings").json()["suggestions_per_video"] == before["suggestions_per_video"]
    time.sleep(61)  # 다음 시험이 쓰기 한도를 다시 쓸 수 있게 창이 비워지도록 기다린다
    a.close()


def test_it_052_health_checks_all_healthy_and_migrate_exited_zero():
    """IT-052: 컨테이너 헬스체크가 실제로 healthy 이고 migrate 는 종료 코드 0 이다(기동 순서 체인의 결과). 검증: W-017, D-01, D-08"""
    import subprocess
    out = subprocess.run(["docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{.Label \"com.docker.compose.service\"}}|{{.Status}}"],
                         capture_output=True, text=True).stdout.splitlines()
    st = dict(x.split("|", 1) for x in out)
    for s in ("db", "api", "worker", "web"):
        assert "(healthy)" in st[s], st
    assert st["migrate"].startswith("Exited (0)"), st
    assert _get("/nginx-health").text == "ok\n"


def test_it_053_api_responses_have_single_cache_control():
    """IT-053(DEF-7-001 수정 확인): /api 응답의 Cache-Control 은 한 줄이어야 한다(proxy_hide_header Cache-Control)."""
    r = _get("/api/healthz")
    assert len(r.headers.get_list("cache-control")) == 1


# ─────────────────────────── 백엔드 계층의 Host 방어(nginx 우회) ───────────────────────────

def test_it_013_backend_host_guard_independent_of_nginx():
    """IT-013: nginx 를 거치지 않고 api 컨테이너 안에서 127.0.0.1:8000 으로 직접 보내도 비허용·중복 Host 는 백엔드가 403 으로 거부한다(이중 방어의 두 번째 층).
    허용 Host 는 통과하고, 헬스 경로는 Host 와 무관하다(컨테이너 헬스체크용). 검증: S-W02, TB-W1"""
    script = """
import http.client, json
def req(hosts, path="/api/v1/auth/me", method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", 8000, timeout=10)
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for h in hosts: c.putheader("Host", h)
    c.endheaders()
    r = c.getresponse(); b = r.read()
    try: code = json.loads(b).get("code")
    except Exception: code = None
    return r.status, code
out = {
  "evil": req(["evil.example"]), "evil_port": req(["evil.example:8080"]), "other_port": req(["127.0.0.1:8081"]), "bare": req(["127.0.0.1"]),
  "dup_bad_first": req(["evil.example", "127.0.0.1:8080"]), "dup_ok_first": req(["127.0.0.1:8080", "evil.example"]),
  "ok": req(["127.0.0.1:8080"]), "ok_local": req(["localhost:8080"]), "upper": req(["LOCALHOST:8080"]),
  "health_any_host": req(["whatever"], "/healthz"),
}
print(json.dumps(out))
"""
    p = inside_api_python(script)
    assert p.returncode == 0, p.stderr[-400:]
    d = json.loads(p.stdout.strip().splitlines()[-1])
    for k in ("evil", "evil_port", "other_port", "bare"):
        assert d[k][0] == 403 and d[k][1] == "host_not_allowed", (k, d[k])
    for k in ("dup_bad_first", "dup_ok_first"):      # 중복 Host: HTTP 서버(h11)가 400 으로 먼저 거부하거나 가드가 403 으로 거부. 200 이면 밀수 성공
        assert d[k][0] in (400, 403), (k, d[k])
    assert d["ok"][0] == 200 and d["ok_local"][0] == 200, d
    assert d["upper"][0] in (200, 403), d
    assert d["health_any_host"][0] == 200, d


# ─────────────────────────── 실제 브라우저(헤드리스 Chromium) 화면 흐름 ───────────────────────────

def _browser_available() -> bool:
    import os
    from pathlib import Path
    return Path("/opt/node22/lib/node_modules/playwright").exists() and any(Path("/opt/pw-browsers").glob("chromium-*"))


@pytest.mark.slow
@pytest.mark.destructive
def test_it_060_real_browser_core_flow_no_console_csp_or_http_errors():
    """IT-060: 헤드리스 Chromium 으로 nginx 경유 핵심 흐름(PIN 없는 첫 화면 → 영상 불러오기 → 제안 생성 → 승인 → 배치 사전 점검 → 확인 문구 → 실행 → 이력)을
    화면 조작만으로 끝까지 수행한다. 콘솔 오류·경고, 페이지 오류, CSP 위반, 4xx/5xx 응답, 외부 도메인 요청이 0건이고, 쿠키는 HttpOnly·SameSite=Strict 이며,
    CSP 가 실제로 인라인 스크립트·외부 연결·프레임 삽입을 막는다. 화면 조작의 결과는 API·감사 체인으로 다시 확인한다.
    검증: W-001~W-017 핵심 흐름, S-W04, NFR-W06, DEF-VF-B01/B05(브라우저에서의 경합)"""
    import os
    import subprocess
    from pathlib import Path
    from itlib import counts, reset_demo_db
    if not _browser_available():
        pytest.skip("Chromium/playwright 가 없음 — 미수행으로 센다")
    reset_demo_db()
    here = Path(__file__).resolve().parent
    out = Path(os.environ.get("IT_LOGDIR", "/tmp")) / "browser_flow.json"
    shots = os.environ.get("IT_SHOTS", "")
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": "/opt/pw-browsers"}
    p = subprocess.run(["node", str(here / "tools" / "browser_flow.mjs"), str(PORT), str(out), shots] if shots else
                       ["node", str(here / "tools" / "browser_flow.mjs"), str(PORT), str(out)], capture_output=True, text=True, timeout=400, env=env)
    res = json.loads(out.read_text(encoding="utf-8"))
    assert p.returncode == 0, p.stdout[-2500:] + p.stderr[-500:] + json.dumps({k: res[k] for k in ("console", "pageerrors", "csp", "badResponses", "thirdParty")}, ensure_ascii=False)[:1500]
    assert all(s["ok"] for s in res["steps"]) and len(res["steps"]) >= 15
    assert not res["console"] and not res["pageerrors"] and not res["csp"] and not res["badResponses"] and not res["thirdParty"]
    ck = [c for c in res["cookies"] if c["name"] == "ytw_session"]
    assert len(ck) == 1 and ck[0]["httpOnly"] is True and ck[0]["sameSite"] == "Strict" and ck[0]["path"] == "/api" and ck[0]["secure"] is False
    # 화면 조작이 실제로 서버 상태를 만들었다
    assert counts()["changes"] == 1 and counts()["videos"] == 200
    a = Api()
    assert a.login().status_code == 200
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    a.close()


# ─────────────────────────── W-FE 실서버 계약 시험을 nginx 주소로 ───────────────────────────

@pytest.mark.slow
@pytest.mark.destructive
def test_it_061_frontend_live_contract_suite_through_nginx_three_runs_zero_settle():
    """IT-061: W-FE 의 실서버 계약 시험(verify/live.verify.test.ts, 21건)을 nginx 주소(Host/Origin 이 127.0.0.1:8080 이 되도록 Node 연결만 게시 포트로 돌림 — 호스트 8080 은 열지 않는다)로,
    변경 직후 대기 0ms(VF_LIVE_SETTLE_MS=0: DEF-VF-B01 경합 재현 조건)로 3회 연속 돌려 매번 21건 전부 통과한다(조건부 PASS 조건 ① 해소 유지 확인).
    검증: W-FE 계약, DEF-VF-B01/005, S-W03. IT_FE_DIR 은 `npm ci --ignore-scripts` 를 마친 프런트 사본."""
    import os
    import subprocess
    from pathlib import Path
    from itlib import reset_demo_db
    fe = os.environ.get("IT_FE_DIR")
    if not fe or not (Path(fe) / "node_modules").is_dir():
        pytest.skip("IT_FE_DIR(npm ci 한 프런트 사본)가 없음 — 미수행으로 센다")
    here = Path(__file__).resolve().parent
    reset_demo_db()
    # 호스트에 8080 을 열지 않는다: Node 의 TCP 연결만 8080 -> 게시 포트로 돌리는 전처리(tools/redirect8080.cjs)를 쓴다(Host/Origin 은 127.0.0.1:8080 그대로).
    outs = []
    for i in range(3):
        if i:
            reset_demo_db()      # 이 시험은 빈 DB 에서 시작한다고 가정한다(재실행하면 상태가 남아 실패 — 시험의 전제이지 결함 아님)
        env = {**os.environ, "VF_LIVE_API": "http://127.0.0.1:8080", "VF_LIVE_SETTLE_MS": "0", "IT_REDIRECT_TARGET": str(PORT),
               "NODE_OPTIONS": f"--require {here / 'tools' / 'redirect8080.cjs'}"}
        p = subprocess.run(["npx", "vitest", "run", "verify/live.verify.test.ts"], cwd=fe, env=env, capture_output=True, text=True, timeout=300)
        out = p.stdout + p.stderr
        outs.append(out)
        m = re.search(r"Tests\s+(\d+) passed \((\d+)\)", out)
        assert p.returncode == 0 and m and m.group(1) == "21" and m.group(2) == "21", (i, out[-1500:])


@pytest.mark.slow
@pytest.mark.destructive
def test_it_062_real_browser_eight_screens_load_with_data_at_two_widths():
    """IT-062: 헤드리스 Chromium 으로 화면 8개(홈·영상 목록·영상 상세·배치 목록·배치 상세·이력·리포트·설정)와 없는 주소(404 화면)를 실제 데이터가 있는 상태에서
    1280px 과 1024px 두 폭으로 불러온다. 각 화면은 제목(h1)과 내용이 있고 오류 문구가 없으며, 콘솔 오류·경고·페이지 오류·CSP 위반·4xx/5xx·외부 요청이 0건이다.
    검증: W-001~W-017 화면 로딩, S-W04, NFR-W06(UX 최소 폭 1024px)"""
    import os
    import subprocess
    from pathlib import Path
    from itlib import approve_many, reset_demo_db, set_cap, usable_videos
    if not _browser_available():
        pytest.skip("Chromium/playwright 가 없음 — 미수행으로 센다")
    reset_demo_db()
    a = Api()
    assert a.login().status_code == 200
    a.sync_demo()
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 4))
    bid = a.make_batch([s["id"] for s in ap[:2]]).json()["batch"]["id"]
    assert a.execute(bid, 2).status_code == 202
    a.wait_batch(bid)
    a.make_batch([s["id"] for s in ap[2:]])          # 배치 목록에는 완료 1건 + 초안 1건
    a.close()
    here = Path(__file__).resolve().parent
    out = Path(os.environ.get("IT_LOGDIR", "/tmp")) / "screens8.json"
    shots = os.environ.get("IT_SHOTS", "")
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": "/opt/pw-browsers"}
    p = subprocess.run(["node", str(here / "tools" / "screens8.mjs"), str(PORT), str(out)] + ([shots] if shots else []), capture_output=True, text=True, timeout=400, env=env)
    res = json.loads(out.read_text(encoding="utf-8"))
    assert p.returncode == 0, p.stdout[-3000:] + p.stderr[-500:]
    assert len(res["screens"]) == 18 and all(x["ok"] for x in res["screens"])
    assert not res["console"] and not res["pageerrors"] and not res["csp"] and not res["badResponses"] and not res["thirdParty"]
