"""독립 점검 8: 코드 정적 검토(보안 불변식) + 실제 uvicorn 기동 스모크 (S-W02, S-W04, S-W08, S-W09, S-W13)."""
from __future__ import annotations

import http.client
import inspect
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import ytweb
from ytweb.core import deps, pin, sessions

from tests.conftest import REPO_ROOT

PKG = Path(ytweb.__file__).parent
CORE_FILES = sorted((PKG / "core").glob("*.py")) + sorted((PKG / "routers").glob("*.py")) + [PKG / "app.py", PKG / "worker.py", PKG / "migrate.py"]
OWNED = [p for p in CORE_FILES if p.name not in {"__init__.py"}]
# W-BE-B 소유 라우터는 이 단위의 검토 대상이 아니다
OWNED = [p for p in OWNED if p.name in {"errors.py", "clock.py", "canonical.py", "audit.py", "idempotency.py", "jobs.py", "settings_store.py", "deps.py",
                                         "sessions.py", "pin.py", "guard.py", "ratelimit.py", "logsetup.py", "app.py", "worker.py", "migrate.py",
                                         "health.py", "auth.py", "settings.py"}]


def _src(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_secret_comparisons_use_constant_time_compare():
    """TC-VA-127 [S-W08] CSRF 토큰과 PIN 해시 비교는 hmac.compare_digest 를 쓰고, 토큰/해시를 ==/!= 로 직접 비교하는 코드가 없다."""
    assert "hmac.compare_digest" in inspect.getsource(deps.require_csrf)
    assert "hmac.compare_digest" in inspect.getsource(pin.verify_pin_hash)
    for name, fn in (("require_csrf", deps.require_csrf), ("verify_pin_hash", pin.verify_pin_hash)):
        code = "\n".join(l for l in inspect.getsource(fn).splitlines() if not l.strip().startswith("#"))
        assert not re.search(r"(csrf_token|digest|expected|actual|stored)\w*\s*[!=]=\s*", code), name
        assert not re.search(r"[!=]=\s*\w*(csrf_token|digest|expected|actual)", code), name


def test_tokens_come_from_secrets_module_with_256_bits_and_no_random_module():
    """TC-VA-128 [S-W08] 세션/CSRF 토큰은 secrets.token_urlsafe(32)(256비트), PIN 솔트는 secrets.token_bytes(16) 이며 보안 코드에 random 모듈이 없다."""
    s = inspect.getsource(sessions.create_session)
    assert s.count("secrets.token_urlsafe(32)") == 2
    assert "secrets.token_bytes(16)" in inspect.getsource(pin.hash_pin)
    for p in OWNED:
        assert not re.search(r"^\s*(import random|from random import)", _src(p), re.M), p.name
        assert "uuid.uuid1" not in _src(p), p.name


def test_no_dynamic_sql_or_dangerous_calls_in_owned_code():
    """TC-VA-129 [S-W13] 이 단위 코드에 SQL 문자열 이어붙이기(f-string/format/% 로 만든 text())·eval·exec·pickle·shell=True·yaml.load 가 없다."""
    bad = []
    for p in OWNED:
        src = _src(p)
        for m in re.finditer(r"(text|execute)\(\s*f[\"']", src):
            bad.append((p.name, "f-string SQL", m.group(0)))
        if re.search(r"(text|execute)\([^)]*\.format\(", src) or re.search(r"(text|execute)\([^)]*\"\s*%\s", src):
            bad.append((p.name, "format SQL"))
        for pat in (r"\beval\(", r"\bexec\(", r"\bpickle\b", r"shell\s*=\s*True", r"yaml\.load\(", r"os\.system\(", r"__import__\("):
            if re.search(pat, src):
                bad.append((p.name, pat))
    # DROP TABLE 를 만드는 downgrade 는 상수 목록만 쓴다(마이그레이션은 별도 점검)
    assert not bad, bad


def test_no_hardcoded_secret_literals_in_owned_code():
    """TC-VA-130 [S-W08] 이 단위 소스에 비밀번호/토큰/키로 보이는 하드코딩 문자열 대입이 없다."""
    pat = re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\w*\s*=\s*[\"'][^\"']{6,}[\"']")
    hits = [(p.name, m.group(0)) for p in OWNED for m in pat.finditer(_src(p))]
    assert not hits, hits


def test_scrypt_parameters_meet_recorded_minimum():
    """TC-VA-131 [S-W08] scrypt 비용 N=2^14, r=8, p=1 이 코드에 고정돼 있다(권고 비교: OWASP 는 N>=2^17 을 제시 -> 6절 권고 R-1)."""
    assert (pin._N, pin._R, pin._P) == (2**14, 8, 1)
    assert pin.MAX_FAILURES == 5 and pin.BASE_LOCK.total_seconds() == 300 and pin.MAX_LOCK.total_seconds() == 3600


def test_health_routes_have_no_dependency_on_session_and_expose_nothing_else():
    """TC-VA-132 [S-W02, S-W09] 헬스 라우트 소스는 세션/DB 값을 응답에 싣지 않는다(상태·db·mode 외 필드 없음)."""
    src = _src(PKG / "routers" / "health.py")
    assert src.count('"status"') >= 2 and "database_url" not in src and "str(exc" not in src and "exc_info" not in src


# ---------------------------------------------------------------- 실서버(uvicorn) 스모크

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live(tmp_path):
    port = _free_port()
    # cwd 가 tmp_path 이므로 패키지 미설치 환경에서도 ytweb 를 찾도록 소스 루트를 PYTHONPATH 로 준다.
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2]), "YTWEB_DATABASE_URL": f"sqlite:///{tmp_path / 'live.db'}", "YTWEB_AUTO_CREATE": "1",
           "YTWEB_ALLOWED_HOSTS": f"127.0.0.1:{port},localhost:{port}", "YTWEB_PORT": str(port),
           "YTWEB_BASE_DIR": str(REPO_ROOT), "YTWEB_SECRETS_DIR": str(tmp_path / "sec"), "YTWEB_LOG_JSON": "1"}
    err = open(tmp_path / "uvicorn.err", "wb")
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "ytweb.app:create_app", "--factory", "--host", "127.0.0.1", "--port", str(port),
                          "--no-server-header", "--no-access-log"], env=env, stdout=err, stderr=err, cwd=str(tmp_path))
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            c.request("GET", "/healthz")
            if c.getresponse().status == 200:
                break
        except OSError:
            time.sleep(0.2)
    else:
        p.kill()
        pytest.fail("uvicorn 이 기동하지 않음: " + (tmp_path / "uvicorn.err").read_text(errors="replace")[-500:])
    yield {"port": port, "proc": p, "err": tmp_path / "uvicorn.err"}
    if p.poll() is None:
        p.kill()
        p.wait(timeout=5)
    err.close()


def _raw(port: int, payload: bytes, read_timeout=15.0) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=read_timeout) as s:
        s.sendall(payload)
        s.settimeout(read_timeout)
        buf = b""
        try:
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if b"\r\n\r\n" in buf and (b"content-length" not in buf.lower() or len(buf) > 100):
                    # 헤더와 본문 일부를 받으면 충분
                    time.sleep(0.05)
                    s.settimeout(0.3)
        except (socket.timeout, ConnectionError):
            pass
    return buf


def _status(raw: bytes) -> int:
    m = re.match(rb"HTTP/1\.[01] (\d{3})", raw)
    return int(m.group(1)) if m else 0


def test_live_duplicate_host_headers_never_served(live):
    """TC-VA-133 [S-W02] 실서버: 중복 Host 헤더(허용+비허용, 순서 두 가지)는 어느 쪽도 200 이 되지 않는다(서버 또는 가드가 거부)."""
    port = live["port"]
    for hosts in ([f"127.0.0.1:{port}", "evil.com"], ["evil.com", f"127.0.0.1:{port}"]):
        req = b"GET /api/v1/auth/me HTTP/1.1\r\n" + b"".join(b"Host: " + h.encode() + b"\r\n" for h in hosts) + b"Connection: close\r\n\r\n"
        st = _status(_raw(port, req))
        assert st in (400, 403), (hosts, st)


@pytest.mark.parametrize("cl", ["-1", "+5", "1_0", "5, 5", "abc"])
def test_live_malformed_content_length_never_reaches_app_as_success(live, cl):
    """TC-VA-134 [S-W13] 실서버: 비정상 Content-Length 는 서버(h11) 또는 가드가 4xx 로 거부한다(200 불가)."""
    port = live["port"]
    req = (f"POST /api/v1/auth/session HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: http://127.0.0.1:{port}\r\n"
           f"Content-Type: application/json\r\nContent-Length: {cl}\r\nConnection: close\r\n\r\n{{}}").encode()
    st = _status(_raw(port, req))
    assert st == 0 or 400 <= st < 500, (cl, st)  # 0 = 서버가 응답 없이 연결을 닫음(파싱 거부)


def test_live_chunked_body_over_1mb_gets_413_and_small_chunked_ok(live):
    """TC-VA-135 [S-W13] 실서버: Transfer-Encoding: chunked 로 1MB 를 넘기면 413, 작은 chunked 본문은 정상 처리된다."""
    port = live["port"]
    head = (f"POST /api/v1/auth/session HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: http://127.0.0.1:{port}\r\n"
            "Content-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n").encode()
    small = head + b"2\r\n{}\r\n0\r\n\r\n"
    assert _status(_raw(port, small)) == 200
    chunk = b"x" * 65536
    big = head + b"".join(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n" for _ in range(17)) + b"0\r\n\r\n"
    assert _status(_raw(port, big)) == 413


def test_live_full_flow_cookie_headers_and_no_secret_in_server_output(live):
    """TC-VA-136 [S-W04, S-W08, S-W09] 실서버 전체 흐름: 헬스(임의 Host) -> 세션 발급(쿠키 속성) -> CSRF 설정 변경 -> 로그아웃. Server 헤더 없음, 보안 헤더 존재, 서버 출력(stderr)에 쿼리스트링 비밀·토큰이 없다."""
    port = live["port"]
    host = f"127.0.0.1:{port}"
    origin = f"http://{host}"
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request("GET", "/healthz", headers={"Host": "api:8000"})
    r = c.getresponse(); r.read()
    assert r.status == 200 and r.getheader("Server") is None
    c.request("GET", "/api/v1/auth/me", headers={"Host": "evil.com"})
    r = c.getresponse(); r.read()
    assert r.status == 403
    c.request("POST", "/api/v1/auth/session", body=b"{}", headers={"Origin": origin, "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"})
    r = c.getresponse(); body = json.loads(r.read())
    assert r.status == 200
    sc = r.getheader("Set-Cookie")
    assert "HttpOnly" in sc and "SameSite=strict" in sc.replace("Strict", "strict") and "Path=/api" in sc and "Max-Age=43200" in sc
    token = sc.split(";")[0].split("=", 1)[1]
    csrf = body["csrf_token"]
    assert r.getheader("X-Content-Type-Options") == "nosniff" and r.getheader("Cache-Control") == "no-store"
    c.request("PATCH", "/api/v1/settings?pin=QS-LIVE-SECRET&token=QS-LIVE-TOKEN", body=json.dumps({"daily_apply_cap": 8}),
              headers={"Origin": origin, "Content-Type": "application/json", "X-CSRF-Token": csrf, "Cookie": f"ytw_session={token}",
                       "Authorization": "Bearer LIVE-HDR-SECRET-123"})
    r = c.getresponse(); out = json.loads(r.read())
    assert r.status == 200 and out["daily_apply_cap"] == 8
    c.request("DELETE", "/api/v1/auth/session", headers={"Origin": origin, "X-CSRF-Token": csrf, "Cookie": f"ytw_session={token}"})
    r = c.getresponse(); r.read()
    assert r.status == 204
    c.request("GET", "/api/v1/settings", headers={"Cookie": f"ytw_session={token}"})
    r = c.getresponse(); r.read()
    assert r.status == 401
    time.sleep(0.3)
    server_output = live["err"].read_text(errors="replace")
    for s in ("QS-LIVE-SECRET", "QS-LIVE-TOKEN", "LIVE-HDR-SECRET-123", token, csrf):
        assert s not in server_output, s
    assert "Traceback" not in server_output


def test_live_sigterm_graceful_shutdown(live):
    """TC-VA-137 [S-W12] 실서버: SIGTERM 에 10초 안에 종료하고(uvicorn 은 정리 후 신호를 다시 올려 returncode -15), 종료 로그에 'Finished server process' 가 남는다."""
    p = live["proc"]
    p.send_signal(signal.SIGTERM)
    assert p.wait(timeout=10) in (0, -signal.SIGTERM)
    out = live["err"].read_text(errors="replace")
    assert "Finished server process" in out and "Traceback" not in out


def _live_req(port, method, path, token=None, csrf=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)  # 요청마다 새 연결(브라우저가 연결을 새로 쓰는 경우와 같게)
    h = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"}
    if token:
        h["Cookie"] = f"ytw_session={token}"
    if csrf:
        h["X-CSRF-Token"] = csrf
    c.request(method, path, body=json.dumps(body).encode() if body is not None else b"{}" if method != "GET" else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    sc = r.getheader("Set-Cookie")
    c.close()
    return r.status, (json.loads(raw) if raw else None), sc


def test_live_read_after_write_sees_committed_state_pin_cannot_be_bypassed(live):
    """TC-VA-190 [S-W08, DEF-VA-010 회귀] 실서버: 세션 발급 직후 첫 요청이 401 이 되지 않고, PIN 설정 직후 current_pin 없는 PIN 변경이 단 한 번도 통과하지 않는다(요청마다 새 연결; 세션 발급 8회 + PIN 변경 시도 4회, 발급 한도 때문에 반복 수는 제한). 한계: 수정 전 코드에서도 이 환경에서는 6회 모두 통과해 경쟁을 재현하지 못했다 -> 결정적 증명은 TC-VA-182/183, 이 시험은 실서버 스모크."""
    port = live["port"]
    for _ in range(8):  # 세션 발급 한도(분당 10)를 넘지 않게
        st, body, sc = _live_req(port, "POST", "/api/v1/auth/session")
        assert st == 200
        token = sc.split(";")[0].split("=", 1)[1]
        st2, me, _ = _live_req(port, "GET", "/api/v1/settings", token=token)
        assert st2 == 200, "세션 발급 직후 첫 요청이 옛 상태를 읽음(401)"
    st, body, sc = _live_req(port, "POST", "/api/v1/auth/session")
    token, csrf = sc.split(";")[0].split("=", 1)[1], body["csrf_token"]
    st, _, _ = _live_req(port, "PATCH", "/api/v1/settings", token, csrf, {"pin": {"action": "set", "new_pin": "246810"}})
    assert st == 200
    statuses = []
    for _ in range(4):  # 잠금(5회) 이전까지만: 모두 current_pin 없음 -> 401 이어야 한다
        st, _, _ = _live_req(port, "PATCH", "/api/v1/settings", token, csrf, {"pin": {"action": "set", "new_pin": "111111"}})
        statuses.append(st)
    assert statuses == [401] * 4, statuses
