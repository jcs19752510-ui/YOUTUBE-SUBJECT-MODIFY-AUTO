"""W-FIX-INF + M2 compose.online 독립 검증(6단계, 2026-10-11) 실가동 시험 — TC-VIF-100 부터.

이미 떠 있는 임시 스택(프로젝트 harness-tmp-v2, 127.0.0.1:18081)을 실제로 두드린다. 기본은 건너뜀.
  VINF2_LIVE=1                 실행 스위치
  VINF2_PROJECT                compose 프로젝트 이름(기본 harness-tmp-v2, 반드시 harness-tmp- 로 시작)
  VINF2_PORT                   게시된 호스트 포트(기본 18081). nginx 는 Host 를 127.0.0.1:8080 만 허용하므로 요청에 Host 헤더를 직접 지정한다.
  VINF2_OVERRIDE               포트만 18081 로 바꾼 덧씌우기 파일 경로(.harness-tmp/v2/override.yaml)
pwsh 가 없어 backup.ps1/restore.ps1 은 못 돌린다 → 스크립트가 부르는 것과 같은 `ytweb-db` 명령을 `docker compose exec` 로 같은 순서로 수행한다(결과서에 명시).
시험 순서가 의미를 가진다(상태 유지) — 파일 안 순서대로 실행한다.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import socket
import subprocess
import time
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
WEB = ROOT / "web"
PROJECT = os.environ.get("VINF2_PROJECT", "harness-tmp-v2")
PORT = int(os.environ.get("VINF2_PORT", "18081"))
OVERRIDE = os.environ.get("VINF2_OVERRIDE", str(ROOT / ".harness-tmp" / "v2" / "override.yaml"))
HOSTOK = "127.0.0.1:8080"
ORIGIN = "http://127.0.0.1:8080"
SEC = ["Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy",
       "Permissions-Policy", "Cross-Origin-Opener-Policy", "Cross-Origin-Resource-Policy"]

pytestmark = pytest.mark.skipif(os.environ.get("VINF2_LIVE") != "1", reason="VINF2_LIVE=1 필요(임시 스택)")
assert PROJECT.startswith("harness-tmp-"), "운영 스택 보호: 프로젝트 이름은 harness-tmp- 로 시작해야 한다"


def sh(args, timeout=120, input_=None):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, input=input_)


def dc(*a, timeout=240):
    env = {**os.environ, "YTWEB_IMAGE_PREFIX": PROJECT}
    return subprocess.run(["docker", "compose", "-p", PROJECT, "-f", str(WEB / "compose.yaml"), "-f", OVERRIDE, *a],
                          capture_output=True, text=True, timeout=timeout, env=env, cwd=str(WEB))


def cname(svc):
    return f"{PROJECT}-{svc}-1"


def inspect(svc):
    p = sh(["docker", "inspect", cname(svc)])
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)[0]


def dexec(svc, *cmd, timeout=60, user=None):
    a = ["docker", "exec"] + (["-u", user] if user else []) + [cname(svc), *cmd]
    return sh(a, timeout=timeout)


def req(method, path, headers=None, body=None, host=HOSTOK, timeout=10):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=timeout)
    h = {"Host": host} if host is not None else {}
    h.update(headers or {})
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    for k, v in h.items():
        c.putheader(k, v)
    if body is not None:
        c.putheader("Content-Length", str(len(body)))
    c.endheaders(body)
    r = c.getresponse()
    data = r.read()
    hs = r.getheaders()
    c.close()
    return r.status, hs, data


def hdr(hs, name):
    return [v for k, v in hs if k.lower() == name.lower()]


def wait_ready(timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s, _, d = req("GET", "/api/readyz")
            if s == 200 and b'"db":"ok"' in d:
                return time.time() - t0
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError("readyz 200 대기 초과")


def owner_sh(script, *args, timeout=120):
    return dexec("db", "bash", "-c", 'export PGPASSWORD="$(tr -d \'\\r\\n\' < /run/secrets/db_owner_password)"; ' + script, "_", *args, timeout=timeout)


def app_sh(script, *args, timeout=60):
    return dexec("db", "bash", "-c", 'export PGPASSWORD="$(tr -d \'\\r\\n\' < /run/secrets/db_app_password)"; ' + script, "_", *args, timeout=timeout)


PSQL_O = 'psql -At -F "|" --no-psqlrc -h 127.0.0.1 -U ytweb_owner -d ytweb -c "$1"'
PSQL_A = 'psql -At -F "|" --no-psqlrc -h 127.0.0.1 -U ytweb_app -d ytweb -c "$1"'


def counts() -> dict[str, int]:
    p = dexec("db", "ytweb-db", "counts")
    assert p.returncode == 0, p.stderr
    return {l.split()[0]: int(l.split()[1]) for l in p.stdout.strip().splitlines()}


def secret_values() -> dict[str, str]:
    d = WEB / "secrets"
    return {n: (d / n).read_text().strip() for n in ("db_superuser_password", "db_owner_password", "db_app_password")}


class Sess:
    """최소 세션 클라이언트(쿠키·CSRF·Origin 수동 처리)."""

    def __init__(self):
        s, hs, d = req("POST", "/api/v1/auth/session", {"Origin": ORIGIN, "Content-Type": "application/json"}, b"{}")
        assert s == 200, (s, d[:200])
        self.cookie = hdr(hs, "Set-Cookie")[0].split(";")[0]
        self.csrf = json.loads(d)["csrf_token"]

    def call(self, method, path, body=None):
        h = {"Origin": ORIGIN, "Cookie": self.cookie, "X-CSRF-Token": self.csrf, "Content-Type": "application/json"}
        return req(method, path, h, None if body is None else json.dumps(body).encode())

    def job(self, job_id, timeout=60):
        t0 = time.time()
        while time.time() - t0 < timeout:
            s, _, d = self.call("GET", f"/api/v1/jobs/{job_id}")
            j = json.loads(d)
            if j["status"] in ("succeeded", "failed", "cancelled"):
                return j
            time.sleep(0.4)
        raise TimeoutError


STATE: dict = {}


# ------------------------------------------------------------------ 가동·하드닝

def test_vif_100_all_containers_up_and_healthy():
    """TC-VIF-100 db/api/worker/web 은 running+healthy, migrate 는 exited(0)."""
    t0 = time.time()                                                  # up -d 는 의존 서비스만 기다리므로(worker 는 start_period 20s) 상태를 폴링한다(1회차 경합 실패 후 수정)
    while time.time() - t0 < 120:
        sts = {s: inspect(s)["State"] for s in ("db", "api", "worker", "web")}
        if all(v["Status"] == "running" and v["Health"]["Status"] == "healthy" for v in sts.values()):
            break
        time.sleep(2)
    for svc, st in sts.items():
        assert st["Status"] == "running" and st["Health"]["Status"] == "healthy", (svc, st["Status"], st["Health"]["Status"])
    STATE["healthy_wait_s"] = round(time.time() - t0, 1)
    st = inspect("migrate")["State"]
    assert st["Status"] == "exited" and st["ExitCode"] == 0


@pytest.mark.parametrize("svc,user", [("db", "999:999"), ("api", "10001:10001"), ("worker", "10001:10001"), ("web", "101:101"), ("migrate", "10001:10001")])
def test_vif_101_runtime_hardening(svc, user):
    """TC-VIF-101 실제 컨테이너의 하드닝: ReadonlyRootfs, CapDrop ALL, no-new-privileges, 비특권, 호스트망·소켓·바인드 마운트 없음."""
    i = inspect(svc)
    hc = i["HostConfig"]
    assert hc["ReadonlyRootfs"] is True and hc["Privileged"] is False
    assert hc["CapDrop"] == ["ALL"] and not hc.get("CapAdd")
    assert any(x.replace(" ", "") == "no-new-privileges:true" for x in hc["SecurityOpt"])
    assert i["Config"]["User"] == user
    assert hc["NetworkMode"] not in ("host", "none") and not hc.get("PidMode") and not hc.get("IpcMode") in ("host",)
    for m in i["Mounts"]:
        if m["Type"] == "bind":                                     # 파일 비밀(file:)은 /run/secrets 아래 읽기 전용 바인드
            assert m["Destination"].startswith("/run/secrets/") and m["RW"] is False, m
        else:
            assert m["Type"] in ("volume", "tmpfs"), m
        assert "docker.sock" not in m.get("Source", "")
    assert hc["PidsLimit"] and hc["Memory"] > 0
    if i["State"]["Status"] == "running":
        # 실제 프로세스가 비루트이고 유효 능력이 없다
        p = dexec(svc, "sh", "-c", "grep -E '^(Uid|CapEff|NoNewPrivs):' /proc/1/status")
        assert p.returncode == 0, p.stderr
        d = dict(l.split(":\t") if ":\t" in l else l.split(":", 1) for l in p.stdout.strip().splitlines())
        assert d["Uid"].split()[0] == user.split(":")[0]
        assert d["CapEff"].strip() == "0000000000000000", d
        assert d["NoNewPrivs"].strip() == "1"


def test_vif_102_writes_blocked_on_read_only_root():
    """TC-VIF-102 읽기 전용 루트: 이미지 영역에 파일을 만들 수 없고 /tmp(tmpfs, noexec)에서만 쓰기 가능."""
    for svc, tmpdir in (("api", "/tmp"), ("worker", "/tmp"), ("web", "/tmp")):
        bad = dexec(svc, "sh", "-c", "touch /usr/vif_probe 2>&1; echo rc=$?")
        assert "Read-only file system" in bad.stdout and "rc=1" in bad.stdout, (svc, bad.stdout)
        ok = dexec(svc, "sh", "-c", f"touch {tmpdir}/vif_probe && echo ok")
        assert ok.stdout.strip() == "ok", svc
    x = dexec("api", "sh", "-c", "printf '#!/bin/sh\\necho hi\\n' > /tmp/vx.sh; chmod +x /tmp/vx.sh; /tmp/vx.sh 2>&1; echo rc=$?")
    assert "rc=0" not in x.stdout and ("Permission denied" in x.stdout or "denied" in x.stdout.lower()), x.stdout


def test_vif_103_only_web_publishes_loopback_port():
    """TC-VIF-103 호스트 게시는 web 하나, 127.0.0.1 한정. 리스너가 루프백뿐이고 외부 주소로는 접속이 안 된다."""
    for svc in ("db", "api", "worker", "migrate"):
        assert not inspect(svc)["HostConfig"]["PortBindings"], svc
        assert not inspect(svc)["NetworkSettings"]["Ports"] or all(v is None for v in inspect(svc)["NetworkSettings"]["Ports"].values()), svc
    pb = inspect("web")["HostConfig"]["PortBindings"]
    assert pb == {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]}, pb
    # ss 가 없는 환경이라 /proc/net/tcp(상태 0A=LISTEN)에서 읽는다. 127.0.0.1 = 0100007F(리틀엔디언)
    lines = []
    for f in [x for x in ("/proc/net/tcp", "/proc/net/tcp6") if Path(x).exists()]:
        for l in Path(f).read_text().splitlines()[1:]:
            cols = l.split()
            if cols[3] == "0A" and int(cols[1].split(":")[1], 16) == PORT:
                lines.append(cols[1])
    assert lines, "리스너 없음"
    assert all(x.split(":")[0] == "0100007F" for x in lines), lines
    others = [a for a in sh(["hostname", "-I"]).stdout.split() if not a.startswith("127.") and ":" not in a]
    STATE["non_loopback_ips"] = others
    for ip in others[:3]:
        s = socket.socket(); s.settimeout(3)
        assert s.connect_ex((ip, PORT)) != 0, f"{ip}:{PORT} 로 접속됨"
        s.close()


def test_vif_104_networks_internal_and_membership():
    """TC-VIF-104 front/back 은 internal, edge 만 비-internal, 서비스별 소속이 설계와 같다(web 은 back 에 없음)."""
    flags = {}
    for n in ("front", "back", "edge"):
        p = sh(["docker", "network", "inspect", f"{PROJECT}_{n}"])
        assert p.returncode == 0, n
        flags[n] = json.loads(p.stdout)[0]["Internal"]
    assert flags == {"front": True, "back": True, "edge": False}
    exp = {"db": {"back"}, "migrate": {"back"}, "api": {"front", "back"}, "worker": {"back"}, "web": {"front", "edge"}}
    for svc, nets in exp.items():
        have = {k.removeprefix(f"{PROJECT}_") for k in inspect(svc)["NetworkSettings"]["Networks"]}
        assert have == nets, (svc, have)
    # 기본 실행에서 egress 망에 붙은 컨테이너가 없다(오버레이를 썼다 걷은 뒤에는 compose 가 빈 망을 남길 수 있어 '망 부재'가 아니라 '붙은 컨테이너 부재'로 본다 — 1회차 실패 후 수정)
    n = sh(["docker", "network", "inspect", f"{PROJECT}_egress"])
    assert n.returncode != 0 or json.loads(n.stdout)[0]["Containers"] == {}


# ------------------------------------------------------------------ 경로·헤더

def test_vif_110_probe_paths():
    """TC-VIF-110 DEC-047: 루트 /healthz·/readyz 404, /api/healthz 200, /api/readyz 200(db ok), /nginx-health 200."""
    for p in ("/healthz", "/readyz"):
        s, hs, d = req("GET", p)
        assert s == 404 and d == b"not found\n" and hdr(hs, "Content-Type")[0].startswith("text/plain"), (p, s)
    s, _, d = req("GET", "/api/healthz")
    assert s == 200 and json.loads(d) == {"status": "ok"}
    s, _, d = req("GET", "/api/readyz")
    assert s == 200 and json.loads(d) == {"status": "ok", "db": "ok", "mode": "demo"}
    s, _, d = req("GET", "/nginx-health")
    assert (s, d) == (200, b"ok\n")
    # HEAD·POST 는 HTML 200 을 돌려주지 않는다
    assert req("HEAD", "/healthz")[0] == 404
    assert req("POST", "/healthz")[0] in (404, 405)
    assert req("POST", "/api/healthz")[0] == 405


def test_vif_111_probe_variants_report():
    """TC-VIF-111 변형 경로 실측(결함 DEF-VIF-001 의 증거): 정확 경로 외 변형이 HTML 200 을 주지 않아야 한다."""
    out = {}
    for p in ("/healthz/", "/HEALTHZ", "/readyz/", "/healthz?x=1", "//healthz", "/healthz%2f", "/api/healthz/", "/api/HEALTHZ", "/api//healthz"):
        s, hs, d = req("GET", p)
        out[p] = (s, (hdr(hs, "Content-Type") or [""])[0].split(";")[0])
    STATE["variants"] = out
    html200 = {p: v for p, v in out.items() if v == (200, "text/html")}
    pytest.xfail(f"DEF-VIF-001 open — HTML 200 을 주는 변형: {sorted(html200)} / 전체: {out}") if html200 else None


def _assert_headers(path, method="GET", expect_cc=None, **kw):
    s, hs, d = req(method, path, **kw)
    for h in SEC:
        assert len(hdr(hs, h)) == 1, (path, h, hdr(hs, h))
    cc = hdr(hs, "Cache-Control")
    assert len(cc) == (0 if expect_cc is None else 1), (path, cc)
    if expect_cc is not None:
        assert cc[0] == expect_cc, (path, cc)
    assert hdr(hs, "Server") == ["nginx"], (path, hdr(hs, "Server"))        # 버전 노출 없음, 업스트림 Server 중복 없음
    assert not hdr(hs, "X-Powered-By")
    return s, hs, d


def test_vif_112_security_headers_once_everywhere():
    """TC-VIF-112 DEF-7-001: 모든 응답 유형(정적·404·SPA 폴백·API 200/401/405·프록시 오류)에 보안 7헤더 1벌, Cache-Control 최대 1줄."""
    sess = Sess()
    s, hs, d = _assert_headers("/", expect_cc="no-cache")
    assert s == 200
    assert "default-src 'self'" in hdr(hs, "Content-Security-Policy")[0]
    _assert_headers("/some/spa/route", expect_cc="no-cache")
    _assert_headers("/healthz", expect_cc="no-store")
    _assert_headers("/readyz", expect_cc="no-store")
    s, hs, _ = _assert_headers("/api/healthz", expect_cc="no-store")
    assert hdr(hs, "Content-Security-Policy")[0].startswith("default-src 'none'")
    _assert_headers("/api/readyz", expect_cc="no-store")
    _assert_headers("/api/v1/auth/me", expect_cc="no-store")                    # 세션 없음 → 401 계열
    _assert_headers("/api/v1/auth/me", expect_cc="no-store", headers={"Cookie": sess.cookie})
    _assert_headers("/api/nope", expect_cc="no-store")                          # 업스트림 404
    _assert_headers("/api/healthz", method="POST", expect_cc="no-store")        # 405
    _assert_headers("/", method="DELETE", expect_cc="no-cache")                 # limit_except 403
    _assert_headers("/nginx-health", expect_cc=None)
    # 해시 자산: 변경 불가 캐시 1줄
    idx = req("GET", "/")[2].decode()
    asset = re.search(r'(/assets/[^"\']+\.js)', idx).group(1)
    s, hs, _ = _assert_headers(asset, expect_cc="public, max-age=31536000, immutable")
    assert s == 200
    _assert_headers("/assets/nope.js", expect_cc="public, max-age=31536000, immutable")   # 404 도 같은 정책
    STATE["asset"] = asset


def test_vif_113_upstream_error_and_login_responses_have_no_dup_headers():
    """TC-VIF-113 세션 발급(POST)·잘못된 본문(422/400)·너무 큰 본문(413) 응답도 헤더 중복이 없다."""
    h = {"Origin": ORIGIN, "Content-Type": "application/json"}
    s, hs, _ = _assert_headers("/api/v1/auth/session", method="POST", expect_cc="no-store", headers=h, body=b"{}")
    assert s == 200
    s, hs, _ = _assert_headers("/api/v1/auth/session", method="POST", expect_cc="no-store", headers=h, body=b"{bad json")
    assert s in (400, 422)
    s, hs, _ = _assert_headers("/api/v1/auth/session", method="POST", expect_cc="no-store", headers=h, body=b"x" * (1024 * 1024 + 10))
    assert s == 413


def test_vif_114_host_and_method_gates():
    """TC-VIF-114 허용 Host(127.0.0.1:8080, localhost:8080) 외에는 응답 없이 연결 종료(444), 허용되지 않은 메서드는 거부."""
    def blocked(host):
        try:
            s, _, d = req("GET", "/api/healthz", host=host)
        except (http.client.RemoteDisconnected, ConnectionError, http.client.BadStatusLine):
            return "closed"
        assert s in (400, 421) and b"status" not in d, (host, s, d[:80])   # nginx 가 형식 오류로 거부(본문에 앱 응답 없음)
        return s
    res = {h: blocked(h) for h in ("evil.com", "127.0.0.1", f"127.0.0.1:{PORT}", "localhost", "127.0.0.1:8080.evil.com", "[::1]:8080", "127.0.0.1:08080", "", None)}
    STATE["host_gate"] = res
    assert res["evil.com"] == "closed" and res[f"127.0.0.1:{PORT}"] == "closed"
    assert req("GET", "/api/healthz", host="localhost:8080")[0] == 200
    for m, p in (("TRACE", "/"), ("DELETE", "/"), ("PUT", "/"), ("PATCH", "/assets/x.js"), ("POST", "/assets/x.js"), ("TRACE", "/api/v1/x"), ("CONNECT", "/api/x"), ("PROPFIND", "/api/x")):
        s = req(m, p)[0]
        assert s in (400, 403, 405, 501), (m, p, s)


def test_vif_115_access_log_has_no_query_or_cookie():
    """TC-VIF-115 쿼리 문자열(OAuth ?code= 유사)·쿠키가 web 로그에 남지 않는다."""
    token = "VIFQUERYSECRET" + str(int(time.time()))
    req("GET", f"/api/v1/google/callback?code={token}&state=zz", {"Cookie": "ytw_session=" + token})
    req("GET", f"/?q={token}")
    req("GET", f"/api/healthz?code={token}")
    time.sleep(1)
    log = sh(["docker", "logs", cname("web")]).stdout + sh(["docker", "logs", cname("web")]).stderr
    assert '"uri"' in log and "/api/healthz" in log
    assert token not in log


# ------------------------------------------------------------------ 격리·비밀

def test_vif_120_web_cannot_reach_db_but_api_can():
    """TC-VIF-120 DEF-VI-001/DEC-045: web 에서 db 이름 해석·IP 접속 불가(양성 대조: web→api 성공, api→db 성공)."""
    db_ip = list(inspect("db")["NetworkSettings"]["Networks"].values())[0]["IPAddress"]
    assert db_ip
    pos = dexec("web", "sh", "-c", "nc -z -w 3 api 8000; echo rc=$?")
    assert pos.stdout.strip().endswith("rc=0"), pos.stdout + pos.stderr                   # 양성 대조
    r1 = dexec("web", "sh", "-c", "nc -z -w 3 db 5432; echo rc=$?")
    r2 = dexec("web", "sh", "-c", f"nc -z -w 3 {db_ip} 5432; echo rc=$?")
    r3 = dexec("web", "sh", "-c", "getent hosts db; echo rc=$?")
    assert not r1.stdout.strip().endswith("rc=0") and not r2.stdout.strip().endswith("rc=0"), (r1.stdout, r2.stdout)
    assert not r3.stdout.strip().endswith("rc=0") and "db" not in r3.stdout.replace("rc=", ""), r3.stdout
    api_db = dexec("api", "python", "-c", f"import socket;s=socket.create_connection(('db',5432),3);print('connected')")
    assert api_db.stdout.strip() == "connected", api_db.stderr


def test_vif_121_no_external_egress_from_internal_services():
    """TC-VIF-121 db·api·worker 는 외부로 나가지 못한다(internal 망). web 의 외부 통신은 수용된 잔여 위험(DEC-045)이라 관찰만 한다."""
    py = "import socket,sys\ntry:\n  socket.create_connection(('1.1.1.1',443),4); print('OPEN')\nexcept Exception as e: print('BLOCKED',type(e).__name__)"
    for svc in ("api", "worker"):
        p = dexec(svc, "python", "-c", py, timeout=30)
        assert p.stdout.startswith("BLOCKED"), (svc, p.stdout, p.stderr)
    p = dexec("db", "bash", "-c", "timeout 4 bash -c '</dev/tcp/1.1.1.1/443' && echo OPEN || echo BLOCKED", timeout=30)
    assert p.stdout.strip() == "BLOCKED", p.stdout
    # DNS 로 외부 이름도 해석되지 않는다
    p = dexec("api", "python", "-c", "import socket\ntry:\n  socket.gethostbyname('example.com'); print('RESOLVED')\nexcept Exception as e: print('NORES')")
    assert p.stdout.strip() == "NORES", p.stdout
    w = dexec("web", "sh", "-c", "nc -z -w 3 1.1.1.1 443; echo rc=$?", timeout=30)
    STATE["web_egress_observation"] = w.stdout.strip()


def test_vif_122_secrets_not_in_env_images_logs_or_proc():
    """TC-VIF-122 비밀값이 inspect(환경변수·명령·라벨)·이미지 이력·이미지 파일·프로세스 환경·로그 어디에도 평문으로 없다. /run/secrets 분배는 최소 권한."""
    sv = secret_values()
    assert all(len(v) >= 32 for v in sv.values())
    for svc in ("db", "migrate", "api", "worker", "web"):
        raw = sh(["docker", "inspect", cname(svc)]).stdout
        for n, v in sv.items():
            assert v not in raw, (svc, n, "inspect")
        logs = sh(["docker", "logs", cname(svc)])
        for n, v in sv.items():
            assert v not in logs.stdout + logs.stderr, (svc, n, "logs")
    for svc in ("db", "api", "worker", "web"):
        env = dexec(svc, "sh", "-c", "cat /proc/1/environ | tr '\\0' '\\n'").stdout
        for n, v in sv.items():
            assert v not in env, (svc, n, "environ")
        assert re.search(r"PASSWORD=|SECRET=|TOKEN=", env) is None, (svc, [l for l in env.splitlines() if re.search("PASS|SECRET|TOKEN", l)])
    exp = {"db": {"db_superuser_password", "db_owner_password", "db_app_password"}, "api": {"db_app_password"}, "worker": {"db_app_password"}, "web": set()}
    for svc, names in exp.items():
        p = dexec(svc, "sh", "-c", "ls /run/secrets 2>/dev/null")
        assert set(p.stdout.split()) == names, (svc, p.stdout)
    # 비밀 파일 권한: api 의 비밀은 api 사용자만(또는 root 소유 0400/0440 계열) — 다른 서비스 비밀을 읽을 수 없음
    p = dexec("api", "sh", "-c", "cat /run/secrets/db_owner_password 2>&1; echo rc=$?")
    assert "rc=0" not in p.stdout
    # 이미지 이력·파일 시스템
    for svc in ("db", "api", "web"):
        img = f"{PROJECT}-{svc}:local"
        hist = sh(["docker", "history", "--no-trunc", img]).stdout + sh(["docker", "image", "inspect", img]).stdout
        for n, v in sv.items():
            assert v not in hist, (img, n, "history/inspect")
        save = subprocess.run(f"docker save {img} | tar -xO 2>/dev/null | grep -c -a -F -e {sv['db_app_password']} -e {sv['db_owner_password']} -e {sv['db_superuser_password']} || true",
                              shell=True, capture_output=True, text=True, timeout=300)
        assert save.stdout.strip() == "0", (img, save.stdout)
    # 이미지 안에 secrets 폴더 자체가 없다
    for svc in ("api", "web"):
        p = dexec(svc, "sh", "-c", "find / -xdev \\( -name 'google_client*' -o -name 'db_*_password' \\) -not -path '/run/*' -not -path '/proc/*' 2>/dev/null | head")
        assert p.stdout.strip() == "", (svc, p.stdout)
    # 이미지 환경변수에 빌드용 CA 환경이 새어 들어가지 않았다(시험 환경 우회가 하드닝 결과에 영향 없음 확인)
    for svc in ("api", "web"):
        env = json.loads(sh(["docker", "image", "inspect", f"{PROJECT}-{svc}:local"]).stdout)[0]["Config"]["Env"]
        assert not any(e.startswith(("SSL_CERT_FILE", "PIP_CERT", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE")) for e in env), env


# ------------------------------------------------------------------ 데이터 유지·재시작·백업/복원

def test_vif_130_seed_data_via_api():
    """TC-VIF-130 실제 API 로 세션 발급→영상 불러오기(작업 큐→워커)를 수행해 데이터를 만든다."""
    s = Sess()
    st, _, d = s.call("POST", "/api/v1/videos/sync")
    assert st == 202, (st, d[:200])
    j = s.job(json.loads(d)["id"])
    assert j["status"] == "succeeded", j
    c = counts()
    assert c["videos"] > 0 and c["audit_log"] > 0 and c["alembic_version"] == 1, c
    STATE["c0"] = c


def test_vif_131_data_survives_restart_and_down_up():
    """TC-VIF-131 전체 restart 와 down(볼륨 유지)→up 뒤에도 행 수가 같고 readyz 가 200 으로 돌아온다."""
    c0 = STATE["c0"]
    p = dc("restart", timeout=300)
    assert p.returncode == 0, p.stderr[-400:]
    t = wait_ready()
    assert counts() == c0
    p = dc("down", timeout=300)
    assert p.returncode == 0, p.stderr[-400:]
    assert sh(["docker", "volume", "ls", "-q", "--filter", f"name=^{PROJECT}_pgdata$"]).stdout.strip()
    p = dc("up", "-d", "--no-build", timeout=300)
    assert p.returncode == 0, p.stderr[-400:]
    wait_ready()
    assert counts() == c0
    for svc in ("db", "api", "worker", "web"):
        assert inspect(svc)["State"]["Status"] == "running"
    assert inspect("migrate")["State"]["ExitCode"] == 0
    STATE["restart_ready_s"] = t


def test_vif_132_db_restart_recovers_api():
    """TC-VIF-132 DB 만 재시작해도 api 가 재연결해 readyz 200 으로 돌아온다(그 사이 503 은 허용)."""
    sh(["docker", "restart", cname("db")], timeout=120)
    t = wait_ready(120)
    assert counts() == STATE["c0"]
    s, _, d = req("GET", "/api/readyz")
    assert s == 200
    STATE["db_restart_ready_s"] = t


def test_vif_133_backup_dump_list_checksum():
    """TC-VIF-133 backup.ps1 와 같은 단계(dump→list→파일 확인)를 docker exec 로 수행. 중복 이름·경로 이탈 이름은 거부."""
    name = f"vif-{int(time.time())}.dump"
    STATE["dump"] = name
    p = dexec("db", "ytweb-db", "dump", name)
    assert p.returncode == 0 and "크기(바이트):" in p.stdout, p.stderr
    size = int(re.search(r"(\d+)", p.stdout).group(1))
    assert size > 1000
    p = dexec("db", "ytweb-db", "list", name)
    assert p.returncode == 0 and "목차 항목 수:" in p.stdout
    mode = dexec("db", "stat", "-c", "%a", f"/backups/{name}").stdout.strip()
    assert mode == "600", mode                                                   # umask 077
    assert dexec("db", "ytweb-db", "dump", name).returncode != 0                  # 덮어쓰기 거부
    for bad in ("../x.dump", "a/b.dump", "x.sql", ".dump", "a b.dump", "x.dump;id", "$(id).dump"):
        assert dexec("db", "ytweb-db", "dump", bad).returncode != 0, bad
        assert dexec("db", "ytweb-db", "restore", bad).returncode != 0, bad
    STATE["dump_c"] = counts()


def test_vif_134_corrupt_backup_restore_fails_without_touching_data():
    """TC-VIF-134 손상된 .dump 복원은 실패하고 현재 데이터는 그대로다."""
    before = counts()
    dexec("db", "sh", "-c", "head -c 4096 /dev/urandom > /backups/vif-corrupt.dump")
    p = dexec("db", "ytweb-db", "restore", "vif-corrupt.dump")
    assert p.returncode != 0
    dexec("db", "sh", "-c", "head -c 3000 /backups/" + STATE["dump"] + " > /backups/vif-trunc.dump")
    p = dexec("db", "ytweb-db", "restore", "vif-trunc.dump")
    assert p.returncode != 0
    assert counts() == before
    assert dexec("db", "ytweb-db", "restore", "vif-missing.dump").returncode != 0
    dexec("db", "ytweb-db", "remove", "vif-corrupt.dump")
    dexec("db", "ytweb-db", "remove", "vif-trunc.dump")


def test_vif_135_restore_sequence_and_alembic_version_privileges():
    """TC-VIF-135 DEF-7-002: 복원(restore.ps1 와 같은 순서: 안전 백업→web/api/worker 중지→restore→up) 뒤 앱 계정에 alembic_version 쓰기 권한이 없고 감사 로그 UPDATE/DELETE 도 없다."""
    base_c = STATE["dump_c"]
    # 1) 백업 이후 데이터를 바꾼다(세션 발급 → 감사 로그 증가)
    for _ in range(2):
        Sess()
    changed = counts()
    assert changed["audit_log"] > base_c["audit_log"] or changed != base_c, (changed, base_c)
    # 2) 안전 백업
    safe = f"vif-pre-{int(time.time())}.dump"
    assert dexec("db", "ytweb-db", "dump", safe).returncode == 0
    # 3) 서비스 중지
    assert dc("stop", "web", "api", "worker").returncode == 0
    # 4) (대조) 가드 스크립트 없이 복원하면 권한이 풀리는지 — 가드가 의미 있는 시험임을 증명
    raw = owner_sh('pg_restore -h 127.0.0.1 -U ytweb_owner -d ytweb --single-transaction --exit-on-error --clean --if-exists --no-owner /backups/' + STATE["dump"])
    assert raw.returncode == 0, raw.stderr
    loose = app_sh(PSQL_A, "SELECT has_table_privilege('ytweb_app','public.alembic_version','INSERT') OR has_table_privilege('ytweb_app','public.alembic_version','UPDATE') OR has_table_privilege('ytweb_app','public.alembic_version','DELETE')")
    STATE["loose_without_guard"] = loose.stdout.strip()
    # 5) 실제 복원 명령(가드 포함)
    p = dexec("db", "ytweb-db", "restore", STATE["dump"], timeout=180)
    assert p.returncode == 0 and "복원 완료" in p.stdout, p.stderr
    assert dexec("db", "ytweb-db", "remove", STATE["dump"]).returncode == 0
    # 6) 권한 확인(앱 계정 관점)
    q = app_sh(PSQL_A, "SELECT string_agg(p||'='||has_table_privilege('ytweb_app','public.alembic_version',p)::text, ',' ORDER BY p) FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p")
    assert q.stdout.strip() == "DELETE=false,INSERT=false,REFERENCES=false,SELECT=true,TRIGGER=false,TRUNCATE=false,UPDATE=false", q.stdout
    for stmt in ("UPDATE alembic_version SET version_num='x'", "DELETE FROM alembic_version", "INSERT INTO alembic_version VALUES ('x')", "UPDATE audit_log SET actor='x'", "DELETE FROM audit_log"):
        r = app_sh(PSQL_A, stmt)
        assert r.returncode != 0 and "permission denied" in r.stderr, (stmt, r.stderr)
    # 일반 테이블 DML 은 가능(권한을 과하게 회수하지 않음)
    ok = app_sh(PSQL_A, "SELECT count(*) FROM videos")
    assert ok.returncode == 0
    # 7) 서비스 재시작(필요한 마이그레이션 자동 적용) 후 정상
    up = dc("up", "-d", "--no-build", timeout=300)
    assert up.returncode == 0, up.stderr[-400:]
    wait_ready()
    assert inspect("migrate")["State"]["ExitCode"] == 0
    after = counts()
    assert after == base_c, (after, base_c)                                        # 백업 시점으로 되돌아감
    # 8) 복원 뒤 앱이 실제로 쓰기 가능(세션·감사 기록)
    Sess()
    assert counts()["audit_log"] >= after["audit_log"]
    # 안전 백업으로 되돌릴 수 있음(복원 전 상태 복구 가능성)
    assert dexec("db", "ytweb-db", "list", safe).returncode == 0
    dexec("db", "ytweb-db", "remove", safe)
    STATE["post_restore_c"] = counts()


def test_vif_136_head_version_and_migration_idempotent():
    """TC-VIF-136 복원 뒤 alembic head 가 코드의 head 와 같고 migrate 재실행이 변경 없이 성공한다."""
    v = owner_sh(PSQL_O, "SELECT version_num FROM alembic_version")
    heads = sh(["docker", "exec", cname("api"), "python", "-c",
                "from alembic.config import Config;from alembic.script import ScriptDirectory;print(ScriptDirectory.from_config(Config('/app/backend/alembic.ini')).get_current_head())"]).stdout.strip()
    assert v.stdout.strip() == heads and heads, (v.stdout, heads)
    r = dc("run", "--rm", "--no-deps", "migrate", timeout=180)
    assert r.returncode == 0, r.stderr[-300:]
    assert owner_sh(PSQL_O, "SELECT version_num FROM alembic_version").stdout.strip() == heads


def dc_online(*a, timeout=300):
    env = {**os.environ, "YTWEB_IMAGE_PREFIX": PROJECT}
    return subprocess.run(["docker", "compose", "-p", PROJECT, "-f", str(WEB / "compose.yaml"), "-f", str(WEB / "compose.online.yaml"), "-f", OVERRIDE, *a],
                          capture_output=True, text=True, timeout=timeout, env=env, cwd=str(WEB))


def test_vif_140_online_overlay_live_adds_only_google_secret_and_egress():
    """TC-VIF-140 M2: 구글 비밀 파일(가짜 값)이 있을 때 _common.ps1 이 하는 것과 같이 compose.online.yaml 을 얹어 실제로 띄운다.
    api·worker 에 google_client 비밀과 egress 망만 늘고, 포트·권한·db/web 구성은 그대로이며, db 는 여전히 외부로 못 나간다. 끝나면 오버레이를 걷어 원상복구한다."""
    gc = WEB / "secrets" / "google_client.json"
    assert not gc.exists()
    base_ports = {s: inspect(s)["HostConfig"]["PortBindings"] for s in ("db", "api", "worker", "web", "migrate")}
    fake = '{"installed":{"client_id":"vif-fake.apps.googleusercontent.com","client_secret":"VIFFAKESECRET1234567890","redirect_uris":["http://localhost"]}}'
    try:
        gc.write_text(fake)
        up = dc_online("up", "-d", "--no-build")
        assert up.returncode == 0, up.stderr[-500:]
        wait_ready()
        for svc in ("api", "worker"):
            i = inspect(svc)
            nets = {k.removeprefix(f"{PROJECT}_") for k in i["NetworkSettings"]["Networks"]}
            assert nets == ({"front", "back", "egress"} if svc == "api" else {"back", "egress"}), (svc, nets)
            dests = {m["Destination"] for m in i["Mounts"] if m["Type"] == "bind"}
            assert dests == {"/run/secrets/db_app_password", "/run/secrets/google_client"}, dests
            assert "YTWEB_GOOGLE_CLIENT_FILE=/run/secrets/google_client" in i["Config"]["Env"]
            hc = i["HostConfig"]
            assert hc["ReadonlyRootfs"] and hc["CapDrop"] == ["ALL"] and not hc.get("CapAdd") and not hc["Privileged"] and not hc["PortBindings"]
            assert i["Config"]["User"] == "10001:10001"
            assert "VIFFAKESECRET1234567890" not in json.dumps(i)          # 비밀 내용이 inspect 에 없다
            assert dexec(svc, "sh", "-c", "cat /run/secrets/google_client | head -c 20").stdout.startswith('{"installed"')
            assert dexec(svc, "touch", "/run/secrets/google_client").returncode != 0     # 읽기 전용
        for svc in ("db", "migrate", "web"):
            nets = {k.removeprefix(f"{PROJECT}_") for k in inspect(svc)["NetworkSettings"]["Networks"]}
            assert "egress" not in nets, svc
        assert {s: inspect(s)["HostConfig"]["PortBindings"] for s in base_ports} == base_ports
        assert sh(["docker", "exec", cname("db"), "sh", "-c", "ls /run/secrets"]).stdout.split() == ["db_app_password", "db_owner_password", "db_superuser_password"]
        assert "google_client" not in dexec("web", "sh", "-c", "ls /run/secrets 2>&1").stdout
        # db 는 외부로 못 나간다(양성 대조: api 는 egress 망에 붙어 도달 가능한지 관찰)
        p = dexec("db", "bash", "-c", "timeout 4 bash -c '</dev/tcp/1.1.1.1/443' && echo OPEN || echo BLOCKED", timeout=30)
        assert p.stdout.strip() == "BLOCKED"
        q = dexec("api", "python", "-c", "import socket\ntry:\n  socket.create_connection(('1.1.1.1',443),4); print('OPEN')\nexcept Exception as e: print('BLOCKED')", timeout=30)
        STATE["api_egress_with_overlay"] = q.stdout.strip()
        # 비밀(가짜 값)이 로그에 새지 않는다
        for svc in ("api", "worker"):
            lg = sh(["docker", "logs", cname(svc)])
            assert "VIFFAKESECRET1234567890" not in lg.stdout + lg.stderr
    finally:
        gc.unlink(missing_ok=True)
        r = dc("up", "-d", "--no-build", "--remove-orphans")       # 오버레이 없이 다시 (api/worker 재생성)
        assert r.returncode == 0, r.stderr[-300:]
        wait_ready()
    for svc in ("api", "worker"):
        nets = {k.removeprefix(f"{PROJECT}_") for k in inspect(svc)["NetworkSettings"]["Networks"]}
        assert "egress" not in nets, (svc, nets)
        assert not any(m["Destination"].endswith("google_client") for m in inspect(svc)["Mounts"])
    # 오버레이를 걷은 뒤 compose 는 빈 egress 망을 지우지 않는다(compose 동작) → 남아 있어도 붙은 컨테이너가 없으면 통과
    n = sh(["docker", "network", "inspect", f"{PROJECT}_egress"])
    if n.returncode == 0:
        STATE["egress_network_left_behind_empty"] = True
        assert json.loads(n.stdout)[0]["Containers"] == {}
    assert not gc.exists()


def test_vif_150_live_sensitivity_header_dup_detected_on_mutated_proxy_conf(tmp_path):
    """TC-VIF-150 시험의 민감도: proxy.conf 에서 `proxy_hide_header Cache-Control` 을 뺀 변이 nginx 를 일회용 컨테이너(harness-tmp-v2-mutweb, 포트 18082)로 띄우면
    같은 헤더 검사가 Cache-Control 중복을 실제로 잡아낸다(= DEF-7-001 재현). 원본 설정은 건드리지 않는다."""
    d = tmp_path / "ngx"
    d.mkdir()
    src = WEB / "docker" / "nginx"
    for f in src.iterdir():
        (d / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    pc = d / "proxy.conf"
    txt = pc.read_text(encoding="utf-8")
    assert "proxy_hide_header Cache-Control;" in txt
    pc.write_text(txt.replace("proxy_hide_header Cache-Control;", ""), encoding="utf-8")
    for f in d.iterdir():
        f.chmod(0o644)
    d.chmod(0o755)
    name = f"{PROJECT}-mutweb"
    sh(["docker", "rm", "-f", name])
    args = ["docker", "run", "-d", "--name", name, "--read-only", "--cap-drop", "ALL", "--user", "101:101",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m,uid=101,gid=101", "--network", f"{PROJECT}_front", "-p", "127.0.0.1:18082:8080",
            "-v", f"{d / 'nginx.conf'}:/etc/nginx/nginx.conf:ro", "-v", f"{d / 'proxy.conf'}:/etc/nginx/snippets/proxy.conf:ro",
            "-v", f"{d / 'security-headers.conf'}:/etc/nginx/snippets/security-headers.conf:ro",
            "-v", f"{d / 'security-headers-api.conf'}:/etc/nginx/snippets/security-headers-api.conf:ro", f"{PROJECT}-web:local"]
    try:
        r = sh(args)
        assert r.returncode == 0, r.stderr
        sh(["docker", "network", "connect", f"{PROJECT}_edge", name])
        t0 = time.time()
        while time.time() - t0 < 20:
            try:
                c = http.client.HTTPConnection("127.0.0.1", 18082, timeout=3)
                c.request("GET", "/api/healthz", headers={"Host": HOSTOK})
                resp = c.getresponse(); resp.read(); hs = resp.getheaders(); c.close()
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise AssertionError("변이 nginx 가 응답하지 않음: " + sh(["docker", "logs", name]).stderr[-300:])
        cc = hdr(hs, "Cache-Control")
        assert len(cc) == 2, cc                      # 변이에서는 중복이 생긴다 → 정상 스택에서 1줄이었다는 112 의 판정이 의미를 가진다
    finally:
        sh(["docker", "rm", "-f", name])


def test_vif_199_dump_observations():
    """TC-VIF-199 관찰값(판정 아님)을 .harness-tmp/v2/live_state.json 에 남겨 결과서가 인용한다."""
    out = ROOT / ".harness-tmp" / "v2" / "live_state.json"
    out.write_text(json.dumps(STATE, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    assert "loose_without_guard" in STATE
