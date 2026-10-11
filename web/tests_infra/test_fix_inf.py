"""W-FIX-INF(2026-10-11) 수정 단위 시험 — TC-WIX-001 부터 연속(이 파일 안에서 중복 금지, 마지막 TC 가 검사한다).

결함 ID 와의 대응: DEF-7-002(복원 뒤 alembic_version 권한), DEF-9-006(.gitignore), DEF-9-017(.dockerignore·api 이미지 내용물),
DEF-7-006(/healthz·/readyz), DEF-7-007(/api CSP), DEF-7-001(Cache-Control 이중), DEF-9-011·013·014(보안 결정 문서화).

  A. 정적(기본 실행, 도커 불필요)
  B. 실가동(WIX_LIVE=1): 이미 떠 있는 임시 compose 프로젝트에 대한 실측. 프로젝트 이름은 반드시 harness-tmp- 로 시작해야 하며
     (운영 스택을 건드리지 않기 위한 안전장치), TC-WIX-032 는 그 프로젝트의 DB 를 복원(덮어쓰기)한다.
환경변수: WIX_PROJECT(기본 harness-tmp-fixinf), WIX_PORT(기본 18480), WIX_IMAGE_PREFIX(기본 =WIX_PROJECT)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
DOCKER_DIR = WEB / "docker"
NGINX = DOCKER_DIR / "nginx"
PROJECT = os.environ.get("WIX_PROJECT", "harness-tmp-fixinf")
PORT = os.environ.get("WIX_PORT", "18480")
IMAGE_PREFIX = os.environ.get("WIX_IMAGE_PREFIX", PROJECT)

live = pytest.mark.skipif(os.environ.get("WIX_LIVE") != "1", reason="WIX_LIVE=1 필요(임시 compose 스택)")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def lines_of(p: Path) -> list[str]:
    return [l.strip() for l in read(p).splitlines() if l.strip() and not l.strip().startswith("#")]


def location_blocks(conf: str) -> dict[str, str]:
    return {m.group(1).strip(): m.group(2) for m in re.finditer(r"(?s)(location [^{]+)\{(.*?)\n        \}", conf)}


# ======================================================================================
# A. 정적
# ======================================================================================

def test_tc_wix_001_audit_guard_revokes_and_verifies_alembic_version():
    g = read(DOCKER_DIR / "db" / "audit-guard.sql")
    assert "to_regclass('public.alembic_version') IS NOT NULL" in g
    assert re.search(r"REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public\.alembic_version FROM ytweb_app;", g)
    for p in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
        assert f"has_table_privilege('ytweb_app', 'public.alembic_version', '{p}')" in g, p
    assert "alembic_version 권한 회수에 실패했습니다" in g and "RAISE EXCEPTION" in g
    # 읽기는 남아 있어야 한다(앱이 버전을 읽는다): 회수 목록에 SELECT 가 없고 SELECT 보존 검사가 있다
    revoke = re.search(r"REVOKE ([A-Z, ]+) ON TABLE public\.alembic_version", g).group(1)
    assert "SELECT" not in revoke
    assert "has_table_privilege('ytweb_app', 'public.alembic_version', 'SELECT')" in g


def test_tc_wix_002_guard_privilege_set_matches_migration_0002():
    mig = read(WEB / "backend" / "alembic" / "versions" / "0002_revoke_alembic_version_dml.py")
    m = re.search(r"REVOKE ([A-Z, ]+) ON alembic_version FROM ytweb_app", mig)
    assert m, "마이그레이션 0002 의 REVOKE 문을 찾지 못했다"
    g = read(DOCKER_DIR / "db" / "audit-guard.sql")
    g_set = set(re.search(r"REVOKE ([A-Z, ]+) ON TABLE public\.alembic_version", g).group(1).replace(" ", "").split(","))
    assert set(m.group(1).replace(" ", "").split(",")) == g_set


def test_tc_wix_003_guard_keeps_audit_log_revoke_and_runs_after_restore():
    g = read(DOCKER_DIR / "db" / "audit-guard.sql")
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.audit_log FROM ytweb_app;" in g
    assert "to_regclass('public.audit_log') IS NOT NULL" in g
    s = read(DOCKER_DIR / "db" / "bin" / "ytweb-db")
    restore = s[s.index("cmd_restore()"):s.index("cmd_reset_schema()")]
    assert restore.index("pg_restore -h") < restore.index("audit-guard.sql")
    assert "set -Eeuo pipefail" in s      # guard 실패(예외)는 복원 명령 전체를 실패시킨다


def test_tc_wix_004_gitignore_has_client_secret_patterns_and_baseline_kept():
    g = set(lines_of(ROOT / ".gitignore"))
    for need in ("client_secret*.json", "*client_secret*.json", "credentials*.json", "*.pem", "*.key"):
        assert need in g, need
    for old in (".harness-tmp/", ".env", "secrets/", "token*.json", "*.token", "data/", "config/settings.local.yaml", "approvals/",
                "web/secrets/", "web/backups/", "web/frontend/dist/", "*.dump", "node_modules/", "__pycache__/"):
        assert old in g, f"기존 줄이 사라졌다: {old}"


def test_tc_wix_005_dockerignore_has_secret_like_and_cache_patterns_and_baseline_kept():
    d = set(lines_of(ROOT / ".dockerignore"))
    for need in ("*.pem", "**/*.pem", "*.key", "**/*.key", "credentials*.json", "**/credentials*.json", "**/client_secret*.json",
                 "**/.ruff_cache", "**/.mypy_cache", "**/.coverage", "**/.coverage.*"):
        assert need in d, need
    for old in (".git", ".env", "secrets/", "web/secrets/", "web/backups/", "data/", "token*.json", "client_secret*.json", ".harness-tmp/",
                "docs/", "**/tests/", ".claude/", "approvals/", "config/settings.local.yaml", "**/node_modules/", "web/frontend/dist/"):
        assert old in d, f"기존 줄이 사라졌다: {old}"


def test_tc_wix_006_api_dockerfile_copies_only_runtime_paths():
    t = read(DOCKER_DIR / "api.Dockerfile")
    copies = [l.split() for l in t.splitlines() if l.startswith("COPY ")]
    srcs = {c[-2] for c in copies if not c[1].startswith("--from")}
    allowed = {"web/backend/requirements.txt", "web/docker/requirements-ytitle.txt", "src/ytitle", "config",
               "web/backend/ytweb", "web/backend/alembic", "web/backend/alembic.ini"}
    assert srcs == allowed, srcs ^ allowed
    assert not re.search(r"(?m)^COPY\s+web/backend\s", t) and not re.search(r"(?m)^COPY\s+\.\s", t)
    # 런타임 단계에는 요구 파일(requirements*)을 복사하지 않는다(builder 단계 전용)
    runtime = t[t.index("AS runtime"):]
    assert "requirements" not in runtime and "pyproject" not in runtime


def test_tc_wix_007_root_healthz_readyz_are_404_not_spa():
    blocks = location_blocks(read(NGINX / "nginx.conf"))
    for path in ("/healthz", "/readyz"):
        b = blocks[f"location = {path}"]
        assert re.search(r'return 404 "', b) and "proxy_pass" not in b and "try_files" not in b, path
        assert "include /etc/nginx/snippets/security-headers.conf;" in b and 'add_header Cache-Control "no-store" always;' in b, path
    # /api/healthz·/api/readyz 는 그대로 백엔드의 루트 경로로 넘어간다
    assert "proxy_pass $api_upstream/healthz;" in blocks["location = /api/healthz"]
    assert "proxy_pass $api_upstream/readyz;" in blocks["location = /api/readyz"]


def test_tc_wix_008_api_security_headers_file_differs_only_in_csp():
    page = [l for l in lines_of(NGINX / "security-headers.conf")]
    api = [l for l in lines_of(NGINX / "security-headers-api.conf")]
    assert len(page) == len(api) == 7
    csp_api = [l for l in api if "Content-Security-Policy" in l][0]
    assert "default-src 'none'" in csp_api and "frame-ancestors 'none'" in csp_api
    assert "'self'" not in csp_api and "unsafe" not in csp_api and "*" not in csp_api
    assert sorted(l for l in page if "Content-Security-Policy" not in l) == sorted(l for l in api if "Content-Security-Policy" not in l)
    assert all(l.endswith("always;") for l in api)
    w = read(DOCKER_DIR / "web.Dockerfile")
    assert "COPY --chown=0:0 web/docker/nginx/security-headers-api.conf /etc/nginx/snippets/security-headers-api.conf" in w


def test_tc_wix_009_every_proxy_location_uses_api_headers_and_single_cache_control():
    blocks = location_blocks(read(NGINX / "nginx.conf"))
    proxied = {h: b for h, b in blocks.items() if "proxy_pass" in b}
    assert set(proxied) == {"location = /api/healthz", "location = /api/readyz", "location = /api/v1/auth/session", "location /api/"}
    for h, b in proxied.items():
        assert "include /etc/nginx/snippets/security-headers-api.conf;" in b, h
        assert "include /etc/nginx/snippets/security-headers.conf;" not in b, h
        assert len(re.findall(r"add_header Cache-Control", b)) == 1, h
    for h, b in blocks.items():
        if "proxy_pass" not in b:
            assert "security-headers-api.conf" not in b, h      # 페이지·정적 경로는 페이지용 CSP
    assert "proxy_hide_header Cache-Control;" in read(NGINX / "proxy.conf")


DOC_FILES = {
    "install": ROOT / "docs" / "yt" / "WEB_INSTALL.md",
    "runbook": ROOT / "docs" / "yt" / "WEB_RUNBOOK.md",
    "readme": WEB / "README.md",
}


@pytest.mark.parametrize("key", ["install", "runbook", "readme"])
def test_tc_wix_010_docs_state_security_decisions_in_plain_words(key):
    t = read(DOC_FILES[key])
    for need in ("DEF-9-011", "DEF-9-013", "DEF-9-014", "DEC-046"):
        assert need in t, (key, need)
    assert "방화벽" in t and "실측" in t                      # 011: 호스트 서비스 점검 + Docker Desktop 실측 필요
    assert "법률 자문" in t and "전문가" in t                  # 013: 개인정보 해당 여부는 전문가 확인, 법률 자문 아님
    assert "재계산" in t                                       # 014: DB 소유자 재계산 미탐지
    if key != "readme":
        for need in ("선생님이 지금 할 일", "M2 착수 전", "다중 사용자", "외부 접속", "30일"):
            assert need in t, (key, need)


def test_tc_wix_011_tc_numbers_are_unique_and_contiguous():
    src = Path(__file__).read_text(encoding="utf-8")
    nums = [int(n) for n in re.findall(r"(?m)^def test_tc_wix_(\d{3})_", src)]
    assert nums == sorted(set(nums))
    # 정적 001~011, 실가동 030~ 로 구간을 나눠 쓴다(중간 번호는 비워 둔다)
    assert [n for n in nums if n <= 29] == list(range(1, 12))
    assert [n for n in nums if n >= 30] == list(range(30, 30 + len([n for n in nums if n >= 30])))


# ======================================================================================
# B. 실가동 (WIX_LIVE=1)
# ======================================================================================

def sh(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def http(path: str, method: str = "GET", host: str = "127.0.0.1:8080", data: bytes | None = None, headers: dict | None = None) -> tuple[int, dict, str]:
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", method=method, data=data, headers={"Host": host, **(headers or {})})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        status, hdr, body = r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        status, hdr, body = e.code, e.headers, e.read()
    h: dict[str, list[str]] = {}
    for k, v in hdr.items():
        h.setdefault(k.lower(), []).append(v)
    return status, h, body.decode("utf-8", "replace")


@live
def test_tc_wix_030_live_root_healthz_readyz_404_and_api_health_json():
    for p in ("/healthz", "/readyz"):
        st, h, body = http(p)
        assert st == 404 and h["content-type"][0].startswith("text/plain") and "<html" not in body.lower(), (p, st)
    st, h, body = http("/api/healthz")
    assert st == 200 and json.loads(body) == {"status": "ok"}
    st, h, body = http("/api/readyz")
    assert st == 200 and json.loads(body)["status"] == "ok" and json.loads(body)["db"] == "ok"
    st, h, body = http("/")                       # SPA 는 그대로
    assert st == 200 and "<html" in body.lower()
    st, h, body = http("/some/spa/route")
    assert st == 200 and "<html" in body.lower()


@live
def test_tc_wix_031_live_api_csp_none_page_csp_unchanged_and_single_cache_control():
    st, h, _ = http("/api/healthz")
    assert h["content-security-policy"] == ["default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"]
    assert h["cache-control"] == ["no-store"]
    for path, method in (("/api/healthz", "GET"), ("/api/readyz", "GET"), ("/api/v1/nope", "GET"), ("/api/v1/auth/session", "GET"), ("/api/v1/auth/session", "POST")):
        st, h, _ = http(path, method, data=b"{}" if method == "POST" else None, headers={"Content-Type": "application/json"} if method == "POST" else None)
        assert h["cache-control"] == ["no-store"], (path, method, h.get("cache-control"))
        assert len(h["content-security-policy"]) == 1 and "default-src 'none'" in h["content-security-policy"][0], (path, method)
        for name in ("x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy", "cross-origin-opener-policy", "cross-origin-resource-policy"):
            assert len(h[name]) == 1, (path, method, name)
    st, h, _ = http("/")
    assert len(h["content-security-policy"]) == 1 and "default-src 'self'" in h["content-security-policy"][0] and h["cache-control"] == ["no-cache"]


def _psql(role: str, sql: str) -> str:
    pw = {"postgres": "db_superuser_password", "ytweb_owner": "db_owner_password", "ytweb_app": "db_app_password"}[role]
    r = subprocess.run(["docker", "exec", "-i", "-e", f"ROLE={role}", "-e", f"F={pw}", f"{PROJECT}-db-1", "bash", "-c",
                        'PGPASSWORD=$(cat /run/secrets/$F) psql -h 127.0.0.1 -U $ROLE -d ytweb -X -v ON_ERROR_STOP=0 -At -F"|" 2>&1'],
                       input=sql, capture_output=True, text=True, timeout=60)
    return r.stdout.strip()


def _app_privs(table: str, privs: list[str]) -> dict[str, bool]:
    sql = "select " + ", ".join(f"has_table_privilege('ytweb_app','public.{table}','{p}')" for p in privs)
    return dict(zip(privs, [x == "t" for x in _psql("postgres", sql).split("|")]))


@live
def test_tc_wix_032_live_restore_revokes_alembic_version_and_audit_log_again():
    """백업 → (대조군) 가드 없는 pg_restore 로 권한이 풀리는 것을 재현 → ytweb-db restore 로 다시 회수. 이 프로젝트의 DB 를 덮어쓴다."""
    assert PROJECT.startswith("harness-tmp-"), "임시 프로젝트(harness-tmp-*)에서만 실행한다"
    db = f"{PROJECT}-db-1"
    name = "wix032.dump"
    write_privs = ["INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]
    assert not any(_app_privs("alembic_version", write_privs).values())                 # 시작 상태(0002 적용)
    assert _app_privs("alembic_version", ["SELECT"]) == {"SELECT": True}
    sh(["docker", "exec", db, "ytweb-db", "remove", name])
    r = sh(["docker", "exec", db, "ytweb-db", "dump", name])
    assert r.returncode == 0, r.stdout + r.stderr
    try:
        # 대조군: 가드 없이 복원하면 앱 계정이 버전표·감사 로그를 다시 고칠 수 있다(결함 재현 — 시험이 공허하지 않다는 증거)
        r = sh(["docker", "exec", db, "bash", "-c",
                f"PGPASSWORD=$(cat /run/secrets/db_owner_password) pg_restore -h 127.0.0.1 -U ytweb_owner -d ytweb --single-transaction --exit-on-error --clean --if-exists --no-owner /backups/{name}"])
        assert r.returncode == 0, r.stderr
        loose = _app_privs("alembic_version", write_privs)
        assert loose["UPDATE"] and loose["DELETE"], loose
        assert _app_privs("audit_log", ["UPDATE", "DELETE"]) == {"UPDATE": True, "DELETE": True}
        # 실제 복원 경로
        r = sh(["docker", "exec", db, "ytweb-db", "restore", name], timeout=180)
        assert r.returncode == 0, r.stdout + r.stderr
        assert not any(_app_privs("alembic_version", write_privs).values())
        assert _app_privs("alembic_version", ["SELECT"]) == {"SELECT": True}
        assert not any(_app_privs("audit_log", ["UPDATE", "DELETE", "TRUNCATE"]).values())
        assert _app_privs("audit_log", ["INSERT"]) == {"INSERT": True}
        for stmt in ("update alembic_version set version_num = version_num", "delete from alembic_version", "truncate alembic_version",
                     "update audit_log set actor = 'x'", "delete from audit_log"):
            assert "permission denied" in _psql("ytweb_app", stmt), stmt
        assert _psql("ytweb_app", "select version_num from alembic_version") == "0002"
        # 두 번 실행해도 같은 결과(멱등)
        r = sh(["docker", "exec", db, "ytweb-db", "restore", name], timeout=180)
        assert r.returncode == 0, r.stdout + r.stderr
        assert not any(_app_privs("alembic_version", write_privs).values())
    finally:
        sh(["docker", "exec", db, "ytweb-db", "remove", name])


@live
def test_tc_wix_033_live_api_image_has_no_dev_cache_secret_like_or_test_files():
    img = f"{IMAGE_PREFIX}-api:local"
    r = sh(["docker", "run", "--rm", "--entrypoint", "sh", img, "-c",
            r'find /app \( -name ".ruff_cache" -o -name ".mypy_cache" -o -name ".pytest_cache" -o -name ".coverage*" -o -name "*.egg-info" '
            r'-o -name "pyproject.toml" -o -name "requirements*" -o -name "*.pem" -o -name "*.key" -o -name "credentials*" -o -name "client_secret*" '
            r'-o -name "token*.json" -o -name ".env*" -o -name tests -o -name "*.md" -o -name "settings.local.yaml" -o -name "*.sqlite3" \)'])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", r.stdout
    r = sh(["docker", "run", "--rm", "--entrypoint", "sh", img, "-c", "ls -A /app /app/backend; ls /app/backend/alembic/versions"])
    out = r.stdout.split()
    for must in ("alembic.ini", "ytweb", "alembic", "0001_initial.py", "0002_revoke_alembic_version_dml.py", "src", "config"):
        assert must in out, must
    r = sh(["docker", "run", "--rm", "--entrypoint", "python", img, "-c", "import ytweb.app, ytweb.migrate, ytweb.worker, ytitle.config; print('ok')"])
    assert r.stdout.strip() == "ok", r.stderr
