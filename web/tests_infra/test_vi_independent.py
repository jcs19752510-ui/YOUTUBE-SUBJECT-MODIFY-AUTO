"""W-INF 독립 검증(6단계 심사자 `vi`) — TC-VI-nnn.

구현자 시험(test_compose_security.py, TC-WI)을 복사하지 않고 설계서·요구사항(D-01~D-14)에서 직접 만든 시험이다.
세 묶음으로 나뉜다.
  A. 정적(기본 실행, 도커 불필요): compose·Dockerfile·nginx·pg_hba·SQL·스크립트·README 파싱
  B. 도구 수준(도커 필요, VI_DOCKER=1): 일회용 nginx(+스텁 api) 하네스, 일회용 PostgreSQL 초기화
  C. 실가동 스택(VI_LIVE=1): 이미 떠 있는 compose 프로젝트에 대한 실측(보안 설정·포트·격리·DB 권한·비밀·스크립트)

환경변수
  VI_WEB_ROOT   검사 대상 web 폴더(기본: 이 저장소의 web). 변이 점검은 사본 폴더를 지정한다.
  DOCKER_HOST   심사자 전용 도커 소켓
  VI_PROJECT    compose 프로젝트 이름(기본 harness-tmp-vi), VI_PORT 게시 포트(기본 18081)
  VI_RUN        스크립트 실행용 사본 폴더(<VI_RUN>/web/{compose.yaml,scripts_p,secrets,backups})
  VI_PWSH       pwsh 실행 파일
재실행: 결과서(web-WU-INF-test.md) 8절.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import yaml

REPO_WEB = Path(__file__).resolve().parents[1]
WEB = Path(os.environ.get("VI_WEB_ROOT", str(REPO_WEB)))
ROOT = WEB.parent
COMPOSE = WEB / "compose.yaml"
ONLINE = WEB / "compose.online.yaml"
DOCKER_DIR = WEB / "docker"
SCRIPTS = WEB / "scripts"
PROJECT = os.environ.get("VI_PROJECT", "harness-tmp-vi")
PORT = os.environ.get("VI_PORT", "18081")
RUN = Path(os.environ.get("VI_RUN", "")) if os.environ.get("VI_RUN") else None
PWSH = os.environ.get("VI_PWSH") or shutil.which("pwsh")
SERVICES = ["db", "migrate", "api", "worker", "web"]

needs_docker = pytest.mark.skipif(os.environ.get("VI_DOCKER") != "1", reason="VI_DOCKER=1 필요(도커 데몬)")
live = pytest.mark.skipif(os.environ.get("VI_LIVE") != "1", reason="VI_LIVE=1 필요(실가동 스택)")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load(read(COMPOSE))


@pytest.fixture(scope="module")
def svc(cfg) -> dict:
    return cfg["services"]


def env_of(s: dict) -> dict:
    e = s.get("environment", {})
    if isinstance(e, list):
        return dict(x.split("=", 1) for x in e)
    return {k: str(v) for k, v in e.items()}


def sh(cmd: list[str], timeout: int = 120, input: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    if env:
        e.update(env)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input, env=e)


def docker(*args: str, timeout: int = 120, input: str | None = None) -> subprocess.CompletedProcess:
    return sh(["docker", *args], timeout=timeout, input=input)


# ======================================================================================
# A. 정적
# ======================================================================================

def test_tc_vi_001_exactly_one_published_port_bound_to_loopback_8080(svc):
    pubs = [(n, p) for n, s in svc.items() for p in (s.get("ports") or [])]
    assert len(pubs) == 1, pubs
    name, spec = pubs[0]
    assert name == "web"
    assert isinstance(spec, str) and re.fullmatch(r"127\.0\.0\.1:\d+:8080", spec), spec
    for n, s in svc.items():
        assert not s.get("expose") or n in ("web",), n  # expose 로 내부 포트를 열 필요도 없다


def test_tc_vi_002_every_service_has_numeric_non_root_uid_and_gid(svc):
    assert set(svc) == set(SERVICES)
    for n, s in svc.items():
        m = re.fullmatch(r"(\d+):(\d+)", str(s.get("user", "")))
        assert m and int(m[1]) > 0 and int(m[2]) > 0, (n, s.get("user"))


def test_tc_vi_003_hardening_flags_on_all_services(svc):
    for n, s in svc.items():
        assert s.get("read_only") is True, n
        assert s.get("cap_drop") == ["ALL"], n
        assert "cap_add" not in s, n
        assert s.get("security_opt") == ["no-new-privileges:true"], n
        assert s.get("init") is True, n
        for bad in ("privileged", "devices", "pid", "ipc", "network_mode", "userns_mode", "cgroup_parent", "sysctls", "volumes_from", "extra_hosts", "dns"):
            assert bad not in s, (n, bad)


def test_tc_vi_004_no_docker_socket_no_host_folder_mounts(cfg, svc):
    named = set(cfg["volumes"])
    for n, s in svc.items():
        for v in s.get("volumes", []):
            assert isinstance(v, str), (n, v)
            src = v.split(":")[0]
            assert src in named, (n, v)
            assert not src.startswith(("/", ".", "~")) and "sock" not in v, (n, v)
        for t in s.get("tmpfs", []):
            assert t.startswith("/") and "noexec" in t and "nosuid" in t, (n, t)
    for name, vol in cfg["volumes"].items():
        assert not vol, (name, vol)  # driver/driver_opts(호스트 경로 바인딩) 금지
    for p in (COMPOSE, ONLINE):
        assert "docker.sock" not in read(p) and "/var/run" not in read(p)


def test_tc_vi_005_network_topology(cfg, svc):
    nets = cfg["networks"]
    # DEF-VI-001 조치(DEC-045): front/back 분리 — web 은 db 망(back)에 붙지 않는다.
    assert nets["front"] == {"internal": True} and nets["back"] == {"internal": True}
    assert set(nets) == {"front", "back", "edge"}
    assert set(svc["web"]["networks"]) == {"front", "edge"}
    assert set(svc["api"]["networks"]) == {"front", "back"}
    for n in ("db", "worker", "migrate"):
        assert set(svc[n]["networks"]) == {"back"}, n


def test_tc_vi_006_online_overlay_is_opt_in_and_never_touches_db_or_web(cfg):
    ov = yaml.safe_load(read(ONLINE))
    assert set(ov["services"]) == {"api", "worker"}
    for s in ov["services"].values():
        assert set(s["networks"]) == {"egress"}
    assert "egress" not in cfg["networks"]
    assert not (ov["networks"]["egress"] or {}).get("internal")
    assert "ports" not in json.dumps(ov)


def test_tc_vi_007_resource_limits_sane(svc):
    def mem(v: str) -> int:
        return int(v[:-1]) * {"M": 1, "G": 1024}[v[-1]]
    for n, s in svc.items():
        lim = s["deploy"]["resources"]["limits"]
        assert 0 < float(lim["cpus"]) <= 2, n
        assert 0 < mem(str(lim["memory"])) <= 1024, n
        assert 0 < int(lim["pids"]) <= 512, n
    assert sum(mem(str(s["deploy"]["resources"]["limits"]["memory"])) for s in svc.values()) <= 2560


def test_tc_vi_008_secrets_only_by_file_never_in_env_command_or_build_args(cfg, svc):
    pat = re.compile(r"(PASS|SECRET|TOKEN|KEY|CRED)", re.I)
    for n, s in svc.items():
        for k, v in env_of(s).items():
            if k == "YTWEB_SECRETS_DIR":
                assert v == "/var/lib/ytweb/secrets"  # 서명 키 폴더 경로(값 아님)
            elif pat.search(k):
                assert k.endswith("_FILE") and v.startswith("/run/secrets/"), (n, k)
        blob = json.dumps({"command": s.get("command"), "build": s.get("build"), "labels": s.get("labels")})
        assert not re.search(r"[0-9a-f]{32,}", blob), n
        assert "args" not in (s.get("build") or {}), n
    assert all(set(v) == {"file"} and v["file"].startswith("./secrets/") for v in cfg["secrets"].values())
    # 최소 권한: 각 서비스는 자기가 쓰는 비밀만 받는다
    assert set(svc["db"]["secrets"]) == set(cfg["secrets"])
    assert svc["api"]["secrets"] == ["db_app_password"] == svc["worker"]["secrets"]
    assert svc["migrate"]["secrets"] == ["db_owner_password"]
    assert "secrets" not in svc["web"]
    assert not any("POSTGRES_PASSWORD" == k for k in env_of(svc["db"]))


def test_tc_vi_009_startup_chain_and_restart_policy(svc):
    assert svc["migrate"]["depends_on"] == {"db": {"condition": "service_healthy"}}
    for n in ("api", "worker"):
        assert svc[n]["depends_on"] == {"migrate": {"condition": "service_completed_successfully"}}
    assert svc["web"]["depends_on"] == {"api": {"condition": "service_healthy"}}
    assert str(svc["migrate"]["restart"]) in ("no", "False")
    for n in ("db", "api", "worker", "web"):
        assert svc[n]["restart"] == "unless-stopped"
        hc = svc[n]["healthcheck"]
        assert hc["test"] and hc["interval"] and hc["timeout"] and hc["retries"]
    assert svc["migrate"]["healthcheck"] == {"disable": True}
    assert int(svc["db"]["stop_grace_period"].rstrip("s")) >= 30


def test_tc_vi_010_log_rotation_and_timezone(svc):
    for n, s in svc.items():
        assert s["logging"]["driver"] == "json-file"
        o = s["logging"]["options"]
        assert re.fullmatch(r"\d+[km]", o["max-size"]) and (o["max-size"].endswith("k") or int(o["max-size"][:-1]) <= 100), n
        assert 2 <= int(o["max-file"]) <= 10, n
        assert env_of(s)["TZ"] == "Asia/Seoul", n
    cmd = svc["db"]["command"]
    assert "timezone=UTC" in cmd and "log_timezone=UTC" in cmd


def test_tc_vi_011_db_command_hardening(svc):
    cmd = svc["db"]["command"]
    assert "hba_file=/etc/postgresql/pg_hba.conf" in cmd
    assert "password_encryption=scram-sha-256" in cmd
    assert "log_statement=none" in cmd
    assert not any("ssl=off" in c or "fsync=off" in c for c in cmd)
    mc = [c for c in cmd if c.startswith("max_connections=")]
    assert mc and 30 <= int(mc[0].split("=")[1]) <= 100
    e = env_of(svc["db"])
    assert "--data-checksums" in e["POSTGRES_INITDB_ARGS"] and "--encoding=UTF8" in e["POSTGRES_INITDB_ARGS"]
    assert "POSTGRES_HOST_AUTH_METHOD" not in e


def test_tc_vi_012_app_env_does_not_enable_docs_or_wide_hosts(svc):
    for n in ("api", "worker", "migrate"):
        e = env_of(svc[n])
        assert e["YTWEB_ENABLE_DOCS"] == "0"
        assert e["YTWEB_MODE"] == "demo"
        hosts = e["YTWEB_ALLOWED_HOSTS"].split(",")
        assert hosts == ["127.0.0.1:8080", "localhost:8080"], n
    assert "--no-access-log" in svc["api"]["command"] and "--no-server-header" in svc["api"]["command"]
    assert "--reload" not in svc["api"]["command"] and "--proxy-headers" not in svc["api"]["command"]


def _resolve_dockerfile(name: str) -> str:
    return read(DOCKER_DIR / f"{name}.Dockerfile")


@pytest.mark.parametrize("name", ["api", "web", "db"])
def test_tc_vi_013_dockerfile_base_images_pinned_by_digest(name):
    t = _resolve_dockerfile(name)
    arg = dict(re.findall(r"(?m)^ARG\s+(\w+)=(\S+)$", t))
    froms = re.findall(r"(?m)^FROM\s+(\S+)(?:\s+AS\s+\w+)?$", t)
    assert froms
    for f in froms:
        m = re.fullmatch(r"\$\{(\w+)\}", f)
        ref = arg[m[1]] if m else f
        assert re.fullmatch(r"[\w./-]+:[\w.-]+@sha256:[0-9a-f]{64}", ref), (name, ref)
        assert not re.search(r":(latest|stable|lts)@", ref) or "nginx" in ref  # nginx 는 stable 태그 + 다이제스트


@pytest.mark.parametrize("name", ["api", "web", "db"])
def test_tc_vi_014_dockerfile_final_user_non_root_and_no_risky_instructions(name):
    t = _resolve_dockerfile(name)
    users = re.findall(r"(?m)^USER\s+(\S+)", t)
    assert users and re.fullmatch(r"\d+(:\d+)?", users[-1]) and int(users[-1].split(":")[0]) > 0
    for bad in (r"(?m)^ADD\s", r"curl[^\n]*\|\s*(ba)?sh", r"wget[^\n]*\|\s*(ba)?sh", r"--privileged", r"chmod\s+(-R\s+)?[0-7]*7[0-7]*7\b.*(/etc|/app)",
                r"(?m)^ENV\s+\w*(PASS|SECRET|TOKEN|KEY)\w*=", r"(?m)^ARG\s+\w*(PASS|SECRET|TOKEN)\w*", r"--trusted-host", r"--no-check-certificate", r"-k\s+https", r"--insecure"):
        assert not re.search(bad, t), (name, bad)


def test_tc_vi_015_api_image_installs_with_hash_lock_and_multistage():
    t = _resolve_dockerfile("api")
    assert t.count("AS ") == 2
    installs = re.findall(r"(?m)pip install[^\n&]*", t)
    assert len(installs) >= 2
    for i in installs:
        assert "--require-hashes" in i and "--only-binary=:all:" in i and "--no-deps" in i, i
    assert "COPY --from=builder /opt/venv /opt/venv" in t
    assert "HEALTHCHECK" in t and "EXPOSE 8000" in t
    assert not re.search(r"(?m)^COPY\s+\.\s", t), "컨텍스트 전체 복사 금지"
    for src in re.findall(r"(?m)^COPY\s+(?:--\S+\s+)*(\S+)\s", t):
        assert not src.startswith(("secrets", "data", ".env", "approvals")), src


def test_tc_vi_016_web_image_build_strips_sourcemaps_and_ignores_scripts():
    t = _resolve_dockerfile("web")
    assert "npm ci --ignore-scripts" in t
    assert re.search(r"find dist -name '\*\.map' -type f -delete", t)
    assert "COPY --from=build" in t and "/dist" in t
    final = t.split("AS runtime")[1]
    assert "node" not in final.lower().replace("nginx", "")
    assert "USER 101:101" in final and "HEALTHCHECK" in final


def _parse_req(path: Path) -> dict:
    out, cur = {}, None
    for line in read(path).splitlines():
        s = line.strip()
        m = re.match(r"^([A-Za-z0-9_.-]+)==([^\s;\\]+)", s)
        if m:
            cur = m[1].lower()
            out[cur] = {"ver": m[2], "hashes": []}
        for h in re.findall(r"--hash=sha256:([0-9a-f]{64})", s):
            assert cur, line
            out[cur]["hashes"].append(h)
        if s and not s.startswith(("#", "--hash")) and not m and not s.startswith("-"):
            pytest.fail(f"잠금 형식이 아닌 줄: {s}")
    return out


@pytest.mark.parametrize("rel", ["docker/requirements-youtube-title.txt", "backend/requirements.txt"])
def test_tc_vi_017_every_requirement_is_pinned_with_hashes(rel):
    reqs = _parse_req(WEB / rel)
    assert len(reqs) >= 3
    for name, r in reqs.items():
        assert r["hashes"], name
        assert len(set(r["hashes"])) == len(r["hashes"]), name
    if rel.startswith("docker"):
        assert {"pyyaml", "python-dotenv", "tzdata"} <= set(reqs)


def test_tc_vi_018_dockerignore_blocks_secrets_and_noise():
    ents = {l.strip() for l in read(ROOT / ".dockerignore").splitlines() if l.strip() and not l.startswith("#")}
    for must in (".git", ".env", ".env.*", "**/.env", "secrets/", "**/secrets/", "web/secrets/", "web/backups/", "data/", "token*.json",
                 "client_secret*.json", "config/settings.local.yaml", "approvals/", ".harness-tmp/", "**/node_modules/", "web/frontend/dist/",
                 "**/tests/", "docs/", "*.sqlite3", ".claude/"):
        assert must in ents, must
    gi = read(ROOT / ".gitignore")
    for must in ("web/secrets/", "web/backups/", "*.dump"):
        assert must in gi, must


def test_tc_vi_019_nginx_security_baseline():
    c = read(DOCKER_DIR / "nginx" / "nginx.conf")
    assert re.search(r"(?m)^\s*server_tokens off;", c)
    assert re.search(r"client_max_body_size\s+1m;", c)
    assert re.search(r"client_header_timeout\s+10s;", c) and re.search(r"client_body_timeout\s+10s;", c)
    assert re.search(r"large_client_header_buffers\s+4\s+8k;", c)
    assert re.search(r"limit_req_zone \$binary_remote_addr zone=ytweb_auth:\d+m rate=10r/m;", c)
    assert re.search(r"limit_req_zone \$binary_remote_addr zone=ytweb_api:\d+m rate=30r/s;", c)
    assert "limit_req_status 429;" in c
    assert "autoindex" not in c and "stub_status" not in c and "user root" not in c
    assert re.search(r"(?m)^pid /tmp/nginx\.pid;", c)
    assert re.search(r"(?m)^error_log /dev/stderr (warn|error);", c)
    assert len(re.findall(r"(?m)^\s*listen\s", c)) == 1 and "listen 8080 default_server;" in c
    assert re.search(r'map \$http_host \$ytweb_host_ok \{\s*default 0;\s*"127\.0\.0\.1:8080" 1;\s*"localhost:8080" 1;\s*\}', c)
    assert re.search(r"if \(\$ytweb_host_ok = 0\) \{\s*return 444;\s*\}", c)
    assert "resolver 127.0.0.11" in c
    assert "access_log /dev/stdout json_log;" in c and "$query_string" not in c and "$http_cookie" not in c and "$args" not in c and "$request_uri" not in c


def test_tc_vi_020_nginx_every_location_that_adds_headers_includes_security_headers_and_limits_methods():
    c = read(DOCKER_DIR / "nginx" / "nginx.conf")
    blocks = re.findall(r"(?s)(location [^{]+)\{(.*?)\n        \}", c)
    assert len(blocks) == 9      # W-FIX-INF: /healthz·/readyz 404 두 곳 추가(DEF-7-006)
    for head, body in blocks:
        if "add_header" in body or "return" in body or "proxy_pass" in body or "try_files" in body:
            # /api 계열은 JSON 응답용 헤더 파일(CSP default-src 'none', DEF-7-007), 나머지는 페이지용
            want = "security-headers-api.conf" if "proxy_pass" in body else "security-headers.conf"
            assert f"include /etc/nginx/snippets/{want};" in body, head
        if "proxy_pass" in body:
            assert "limit_req zone=" in body and "include /etc/nginx/snippets/proxy.conf;" in body, head
            if head.strip() not in ("location = /api/healthz", "location = /api/readyz"):  # 관찰 O-VI-01: 두 곳은 메서드 제한이 없다
                assert "limit_except" in body, head
            assert 'Cache-Control "no-store"' in body, head
        if head.strip() in ("location /", "location /assets/"):
            assert re.search(r"limit_except GET HEAD \{ deny all; \}", body), head
    sec = read(DOCKER_DIR / "nginx" / "security-headers.conf")
    lines = [l for l in sec.splitlines() if l.startswith("add_header")]
    assert len(lines) == 7 and all(l.rstrip().endswith("always;") for l in lines)
    for must in ("default-src 'self'", "script-src 'self'", "object-src 'none'", "base-uri 'none'", "frame-ancestors 'none'", "form-action 'self'",
                 "X-Content-Type-Options \"nosniff\"", "X-Frame-Options \"DENY\"", "Referrer-Policy", "Permissions-Policy", "Cross-Origin-Opener-Policy", "Cross-Origin-Resource-Policy"):
        assert must in sec, must
    assert "unsafe-eval" not in sec and "script-src 'self' 'unsafe" not in sec and "*" not in re.sub(r"\(\)", "", sec.replace("camera=()", ""))
    proxy = read(DOCKER_DIR / "nginx" / "proxy.conf")
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in proxy  # 클라이언트가 보낸 값을 이어 붙이지 않는다
    assert "$proxy_add_x_forwarded_for" not in proxy
    for h in ("Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy", "Permissions-Policy", "X-Powered-By", "Server"):
        assert f"proxy_hide_header {h};" in proxy, h
    assert re.search(r"proxy_read_timeout\s+\d+s;", proxy) and re.search(r"proxy_connect_timeout\s+\d+s;", proxy)


def _hba_rules() -> list[list[str]]:
    return [l.split() for l in read(DOCKER_DIR / "db" / "pg_hba.conf").splitlines() if l.strip() and not l.lstrip().startswith("#")]


def test_tc_vi_021_pg_hba_closed_by_default():
    rules = _hba_rules()
    assert rules[-1] == ["host", "all", "all", "all", "reject"]
    assert not any(r[0] in ("hostssl", "hostnossl", "hostgssenc") for r in rules)
    for r in rules[:-1]:
        assert r[-1] == "scram-sha-256", r
        if r[0] == "host":
            assert r[3] in ("127.0.0.1/32", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"), r
            if r[2] == "postgres":
                assert r[3] in ("127.0.0.1/32", "::1/128"), r  # 슈퍼유저는 루프백만
            else:
                assert r[1] == "ytweb" and r[2] == "ytweb_app,ytweb_owner", r
        if r[0] == "local":
            assert r[1] in ("all", "ytweb")
    assert not any(r[1] == "replication" for r in rules)
    assert not any("trust" in r or "password" in r or "md5" in r for r in rules)


def test_tc_vi_022_role_init_script_rules():
    s = read(DOCKER_DIR / "db" / "init" / "01-roles.sh")
    assert s.startswith("#!/bin/bash") and "set -Eeuo pipefail" in s
    assert s.count("NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS") == 2
    assert "CONNECTION LIMIT 10" in s and "CONNECTION LIMIT 30" in s
    assert "REVOKE ALL ON DATABASE ytweb FROM PUBLIC;" in s and "GRANT CONNECT ON DATABASE ytweb TO ytweb_app;" in s
    assert "ENCODING 'UTF8'" in s and "OWNER ytweb_owner" in s
    assert "SET log_min_error_statement = 'panic';" in s and "SET log_statement = 'none';" in s
    assert re.search(r'\[ "\$\{#owner_pw\}" -lt 16 \]', s) and re.search(r'\[ "\$\{#app_pw\}" -lt 16 \]', s)
    assert '[ "$owner_pw" = "$app_pw" ]' in s
    assert not re.search(r"echo[^\n]*\$(owner_pw|app_pw)", s) and "PGPASSWORD" not in s
    assert ":'owner_pw'" in s and ":'app_pw'" in s  # 바인딩된 psql 변수(따옴표 처리)
    assert s.rstrip().splitlines()[-2].startswith("touch ") and ".ytweb-init-ok" in s.rstrip().splitlines()[-2]
    assert s.index("schema-grants.sql") < s.index(".ytweb-init-ok")


def test_tc_vi_023_schema_grants_and_audit_guard_sql():
    g = read(DOCKER_DIR / "db" / "schema-grants.sql")
    for must in ("ALTER SCHEMA public OWNER TO ytweb_owner;", "REVOKE ALL ON SCHEMA public FROM PUBLIC;", "GRANT USAGE ON SCHEMA public TO ytweb_app;",
                 "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ytweb_app;", "GRANT USAGE, SELECT ON SEQUENCES TO ytweb_app;"):
        assert must in g, must
    stmts = [l for l in g.splitlines() if l.strip() and not l.strip().startswith("--")]
    joined = "\n".join(stmts)
    assert "TRUNCATE" not in joined and "CREATE" not in joined.replace("CREATE SCHEMA", "") and "ALL PRIVILEGES" not in joined
    assert re.search(r"FOR ROLE ytweb_owner IN SCHEMA public", joined)
    a = read(DOCKER_DIR / "db" / "audit-guard.sql")
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.audit_log FROM ytweb_app;" in a
    for p in ("'UPDATE'", "'DELETE'", "'TRUNCATE'"):
        assert f"has_table_privilege('ytweb_app', 'public.audit_log', {p})" in a, p
    assert "RAISE EXCEPTION" in a and "to_regclass('public.audit_log') IS NOT NULL" in a


def test_tc_vi_024_db_dockerfile_copies_scripts_with_safe_modes():
    t = _resolve_dockerfile("db")
    assert "COPY --chmod=0755 web/docker/db/init/01-roles.sh /docker-entrypoint-initdb.d/01-roles.sh" in t
    assert "COPY --chmod=0755 web/docker/db/bin/ytweb-db /usr/local/bin/ytweb-db" in t
    assert re.search(r"COPY --chmod=0644 web/docker/db/pg_hba\.conf /etc/postgresql/pg_hba\.conf", t)
    assert "install -d -o 999 -g 999 -m 0700 /backups" in t
    assert "sed -i 's/\\r$//'" in t
    for p in list((DOCKER_DIR / "db").rglob("*")) + list((DOCKER_DIR / "nginx").glob("*")) + list(DOCKER_DIR.glob("*.Dockerfile")):
        if p.is_file():
            assert b"\r\n" not in p.read_bytes(), p


def test_tc_vi_025_ytweb_db_static_safety():
    s = read(DOCKER_DIR / "db" / "bin" / "ytweb-db")
    assert "set -Eeuo pipefail" in s and "umask 077" in s
    assert "^[A-Za-z0-9._-]+\\.dump$" in s
    assert "--single-transaction" in s and "--exit-on-error" in s and "--clean --if-exists" in s
    assert s.index("audit-guard.sql") > s.index("--single-transaction")
    assert "--format=custom" in s and "--no-owner" in s and "--lock-wait-timeout" in s
    assert not re.search(r"echo[^\n]*PGPASSWORD|echo[^\n]*\$\(secret", s)
    assert "-U ytweb_owner" in s and "-U postgres" not in s
    assert "pg_restore --list" in s
    assert re.search(r"DROP SCHEMA public CASCADE; CREATE SCHEMA public AUTHORIZATION ytweb_owner;", s)


def test_tc_vi_026_ytweb_db_cli_rejects_bad_names_and_unknown_commands(tmp_path):
    exe = DOCKER_DIR / "db" / "bin" / "ytweb-db"
    env = {"YTWEB_BACKUP_DIR": str(tmp_path), "YTWEB_DB_SECRETS_DIR": str(tmp_path)}
    bad = ["", "../x.dump", "a/b.dump", "x.sql", "a b.dump", "x.dump;id", "x.dump\n", ".dump", "$(id).dump", "x.DUMP", "한글.dump", "a|b.dump"]
    for cmd in ("dump", "list", "restore", "remove"):
        for name in bad:
            r = sh(["bash", str(exe), cmd, name], env=env)
            assert r.returncode == 1, (cmd, repr(name), r.stdout, r.stderr)
            assert "백업 파일 이름이 올바르지 않습니다" in r.stderr, (cmd, repr(name), r.stderr)
    r = sh(["bash", str(exe), "bogus"], env=env)
    assert r.returncode == 1 and "사용법" in r.stderr
    r = sh(["bash", str(exe)], env=env)
    assert r.returncode == 1 and "사용법" in r.stderr
    (tmp_path / "e.dump").write_bytes(b"")
    r = sh(["bash", str(exe), "list", "e.dump"], env=env)
    assert r.returncode == 1 and "비어" in r.stderr
    r = sh(["bash", str(exe), "restore", "nonexist.dump"], env=env)
    assert r.returncode == 1 and "없거나 비어" in r.stderr
    (tmp_path / "ok.dump").write_bytes(b"x")
    r = sh(["bash", str(exe), "dump", "ok.dump"], env=env)
    assert r.returncode == 1 and "이미 같은 이름" in r.stderr  # 기존 백업 덮어쓰기 금지
    assert (tmp_path / "ok.dump").read_bytes() == b"x"
    (tmp_path / "rm.dump").write_bytes(b"x")
    assert sh(["bash", str(exe), "remove", "rm.dump"], env=env).returncode == 0 and not (tmp_path / "rm.dump").exists()
    # 비밀 파일이 없으면 값 출력 없이 실패
    r = sh(["bash", str(exe), "counts"], env=env)
    assert r.returncode == 1 and "비밀 파일이 없거나 비어" in r.stderr


def test_tc_vi_027_powershell_scripts_encoding_and_dangerous_commands():
    files = sorted(SCRIPTS.glob("*.ps1"))
    assert [f.name for f in files] == sorted(["_common.ps1", "backup.ps1", "e2e.ps1", "live-check.ps1", "logs.ps1", "pin-digests.ps1", "reset-demo.ps1", "restore.ps1", "start.ps1", "status.ps1", "stop.ps1"])
    for f in files:
        raw = f.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf"), f.name
        assert b"\r\x00" not in raw
        t = raw.decode("utf-8-sig")
        for bad in (r"Invoke-Expression", r"(?i)\biex\b", r"DownloadString", r"(?i)Set-ExecutionPolicy\s+-Scope\s+(LocalMachine|CurrentUser)", r"Remove-Item[^\n]*-Recurse[^\n]*(\$Ytweb|secrets|backups)",
                    r"(?i)docker\s+system\s+prune", r"(?i)docker\s+volume\s+(rm|prune)", r"(?i)--privileged", r"Start-Process[^\n]*-Verb\s+RunAs", r"(?i)-ExecutionPolicy\s+Bypass"):
            assert not re.search(bad, t), (f.name, bad)
        for m in re.finditer(r"(?im)^.*(Write-Host|Write-Ok|Write-Info|Write-Warn|Write-Output).*$", t):
            assert not re.search(r"(Get-Content|ReadAllText|New-RandomSecret|\$secret|\$pw|password_file)", m[0], re.I), (f.name, m[0])
        if f.name not in ("reset-demo.ps1",):
            assert not re.search(r"'--volumes'|'-v'|down\s+(-v|--volumes)", t), f.name
    code = "\n".join(l for l in read(SCRIPTS / "stop.ps1").splitlines() if not l.lstrip().startswith("#"))
    assert re.search(r"'down'", code) and not re.search(r"down.*(-v\b|--volumes)", code)


def test_tc_vi_028_reset_demo_confirmation_precedes_any_destruction():
    t = read(SCRIPTS / "reset-demo.ps1")
    i_phrase = t.index("Read-ConfirmText")
    assert i_phrase < t.index("'--volumes'") and i_phrase < t.index("'reset-schema'") and i_phrase < t.index("backup.ps1")
    assert "$phrase = '모든 데이터 삭제'" in t and "$phrase = '데모 초기화'" in t
    assert t.count("exit 2") == 1 and "확인 문구가 맞지 않아" in t
    i_bk = t.index("backup.ps1")
    assert i_bk < t.index("'--volumes'") and i_bk < t.index("'reset-schema'")
    assert "-SkipBackup" in t and "pre-reset" in t
    assert "-not $SkipBackup" in t
    assert re.search(r"\$LASTEXITCODE -ne 0\) \{ Stop-Script '자동 백업에 실패해 초기화를 중단했습니다", t)
    c = read(SCRIPTS / "_common.ps1")
    assert re.search(r"function Read-ConfirmText[\s\S]*?\(\$typed -eq \$Expected\)", c)  # -eq 는 대소문자 구분 안 함: 아래 시험에서 별도 지적
    assert "if ($Provided) { return ($Provided -eq $Expected) }" in c


def test_tc_vi_029_restore_order_confirm_then_safety_backup_then_stop_then_restore():
    t = read(SCRIPTS / "restore.ps1")
    order = [t.index(x) for x in ("Assert-BackupFileName $leaf", "Get-FileHash", "Read-ConfirmText", "'backup.ps1'", "'stop', 'web', 'api', 'worker'", "'restore', $leaf")]
    assert order == sorted(order), order
    assert "$phrase" not in t and "'복원합니다'" in t and "exit 2" in t
    assert "pre-restore" in t and "-SkipSafetyBackup" in t
    assert "Remove-Item -LiteralPath $tmpDir -Recurse -Force" in t and "GetTempPath" in t
    assert "if ($expected -ne $actual) { Stop-Script" in t
    assert t.index("if (-not $ok)") > t.index("'up', '-d'")  # 실패해도 서비스는 먼저 되살린 뒤 오류를 보고한다


def test_tc_vi_030_backup_script_integrity_chain():
    t = read(SCRIPTS / "backup.ps1")
    assert "ValidatePattern('^[A-Za-z0-9-]+$')" in t
    assert t.index("Assert-BackupFileName $name") < t.index("'dump', $name")
    for x in ("'list', $name", "'cp'", "Get-FileHash", "SHA256", ".sha256", "-ne $inContainerSize", "$size -le 0"):
        assert x in t, x
    assert t.index("'list', $name") < t.index("'cp'") < t.index("Get-FileHash") < t.index("'remove', $name) -Quiet)", t.index("'cp'"))


def test_tc_vi_031_status_script_checks_published_ports_strictly():
    t = read(SCRIPTS / "status.ps1")
    assert "^127\\.0\\.0\\.1:8080->8080/tcp$" in t
    assert "[위험]" in t and "$problems++" in t
    assert "exit 1" in t and "if ($problems -eq 0)" in t
    assert "IsLoopback" in t and "/api/healthz" in t and "/api/readyz" in t
    assert "$svc -eq 'web'" in t


def test_tc_vi_032_common_script_guards():
    t = read(SCRIPTS / "_common.ps1")
    assert "Set-StrictMode -Version 2.0" in t and "$ErrorActionPreference = 'Stop'" in t
    assert "$major -lt 2 -or ($major -eq 2 -and $minor -lt 20)" in t
    assert "$parts[1].Trim() -ne 'linux'" in t
    assert t.count("(Get-Item -LiteralPath $p).Length -gt 0) { continue }") == 2
    for n in ("db_superuser_password", "db_owner_password", "db_app_password"):
        assert n in t
    assert "Test-VolumeExists 'pgdata'" in t
    assert "[System.IO.File]::WriteAllText($p, (New-RandomSecret)" in t
    assert "RandomNumberGenerator" in t and "System.Random" not in t and "Get-Random" not in t
    assert "(Get-Item -LiteralPath $p).Length -gt 0) { continue }" in t  # 기존 비밀 덮어쓰기 금지
    assert re.search(r"function Assert-BackupFileName[\s\S]*?\^\[A-Za-z0-9\._-\]\+\\\.dump\$", t)


def test_tc_vi_033_start_script_flow():
    t = read(SCRIPTS / "start.ps1")
    seq = [t.index(x) for x in ("Test-DockerReady", "Initialize-Secrets", "Test-PortInUse", "'up', '-d'", "Wait-ForStack", "'port', 'web', '8080'")]
    assert seq == sorted(seq)
    assert "--build" in t and "$NoBuild" in t and "127.0.0.1:" in t
    assert "-and (Test-PortInUse $YtwebPort)" in t


@pytest.mark.skipif(PWSH is None, reason="pwsh 없음")
def test_tc_vi_034_powershell_parse_errors_zero():
    code = ("$bad=0; Get-ChildItem '%s' -Filter *.ps1 | ForEach-Object { $e=$null;$t=$null;"
            "[void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$t,[ref]$e);"
            "if($e.Count){$bad+=$e.Count; $_.Name; $e|ForEach-Object{$_.Message}} }; exit $bad" % SCRIPTS)
    r = sh([PWSH, "-NoProfile", "-Command", code], timeout=180, env={"DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1"})
    assert r.returncode == 0, r.stdout + r.stderr


def test_tc_vi_035_readme_security_claims_match_config(svc):
    t = read(WEB / "README.md")
    assert "127.0.0.1:8080" in t and "같은 와이파이" in t
    assert "docker compose down -v" in t and "영구 삭제" in t and "reset-demo.ps1 -DeleteVolumes" in t
    assert "복원합니다" in t and "데모 초기화" in t and "모든 데이터 삭제" in t
    assert "PostgreSQL 17" in t and "postgres:17-bookworm" in t
    for w in ("web", "api", "db", "worker"):
        assert w in t
    assert "Docker Desktop" in t and "체크리스트" in t
    # 문서의 확인 문구가 스크립트와 일치
    assert "복원합니다" in read(SCRIPTS / "restore.ps1") and "데모 초기화" in read(SCRIPTS / "reset-demo.ps1")


def test_tc_vi_036_no_secret_like_literals_anywhere_in_unit_files():
    for p in [COMPOSE, ONLINE, *DOCKER_DIR.rglob("*"), *SCRIPTS.glob("*.ps1"), WEB / "README.md"]:
        if not p.is_file() or p.name.startswith("requirements"):
            continue
        t = re.sub(r"sha256:[0-9a-f]{64}", "", p.read_text(encoding="utf-8-sig", errors="ignore"))
        assert not re.search(r"\b[0-9a-f]{40,}\b", t), p
        assert not re.search(r"(?i)(password|passwd|secret|token)(\s*=\s*|:\s+)['\"][^'\"$<{\s][^'\"]{5,}['\"]", t.replace("PASSWORD_FILE", "")), p
        assert not re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|ya29\.|AIza[0-9A-Za-z_-]{20}", t), p


def test_tc_vi_037_secrets_dir_not_inside_build_context_files():
    # 비밀 폴더가 컨텍스트로 새지 않도록 Dockerfile 어디에서도 secrets 를 복사하지 않고 .dockerignore 가 막는다
    for n in ("api", "web", "db"):
        t = _resolve_dockerfile(n)
        assert not re.search(r"(?mi)^COPY[^\n]*(secrets|backups|\.env|token|\.git\b)", t), n
        assert not re.search(r"(?mi)^COPY\s+(--\S+\s+)*\.\s", t), n


# ======================================================================================
# B. 일회용 nginx 하네스 (VI_DOCKER=1) — 저장소의 nginx 설정을 실제 이미지에서 시험
# ======================================================================================
STUB_PY = r'''
import json, http.server
class H(http.server.BaseHTTPRequestHandler):
    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        out = json.dumps({"path": self.path, "method": self.command, "headers": dict(self.headers), "len": len(body)}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Security-Policy", "default-src *")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("X-Powered-By", "stub")
        self.send_header("Server", "stubsrv")
        self.send_header("Set-Cookie", "ytw_session=abc; HttpOnly; SameSite=strict")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _go
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
'''


@pytest.fixture(scope="module")
def ngx():
    yield from _ngx_gen("ngx")


@pytest.fixture()
def ngx_fresh():
    yield from _ngx_gen("ngxf")


def _ngx_gen(tag: str):
    if os.environ.get("VI_DOCKER") != "1":
        pytest.skip("VI_DOCKER=1 필요")
    names = [f"{PROJECT}-{tag}-stub", f"{PROJECT}-{tag}-web"]
    NGX_NET = f"{PROJECT}-{tag}"
    for n in names:
        docker("rm", "-f", n)
    docker("network", "rm", NGX_NET)
    assert docker("network", "create", NGX_NET).returncode == 0
    try:
        r = docker("run", "-d", "--name", names[0], "--network", NGX_NET, "--network-alias", "api", "--read-only", "--cap-drop", "ALL",
                   "--entrypoint", "python", f"{PROJECT}-api:local", "-c", STUB_PY)
        assert r.returncode == 0, r.stderr
        ng = DOCKER_DIR / "nginx"
        r = docker("run", "-d", "--name", names[1], "--network", NGX_NET, "--read-only", "--cap-drop", "ALL", "--tmpfs", "/tmp:rw,noexec,nosuid,uid=101,gid=101,mode=1777",
                   "-v", f"{ng/'nginx.conf'}:/etc/nginx/nginx.conf:ro", "-v", f"{ng/'security-headers.conf'}:/etc/nginx/snippets/security-headers.conf:ro",
                   "-v", f"{ng/'proxy.conf'}:/etc/nginx/snippets/proxy.conf:ro",
                   "-v", f"{ng/'security-headers-api.conf'}:/etc/nginx/snippets/security-headers-api.conf:ro", f"{PROJECT}-web:local")
        assert r.returncode == 0, r.stderr
        ip = ""
        for _ in range(30):
            ip = docker("inspect", names[1], "--format", f"{{{{(index .NetworkSettings.Networks \"{NGX_NET}\").IPAddress}}}}").stdout.strip()
            st = docker("inspect", names[1], "--format", "{{.State.Running}}").stdout.strip()
            if ip and st == "true":
                try:
                    urllib.request.urlopen(urllib.request.Request(f"http://{ip}:8080/nginx-health", headers={"Host": "127.0.0.1:8080"}), timeout=2)
                    break
                except Exception:
                    pass
            time.sleep(0.5)
        else:
            pytest.fail("nginx 하네스 기동 실패: " + docker("logs", names[1]).stderr[-800:])
        yield ip
    finally:
        for n in names:
            docker("rm", "-f", n)
        docker("network", "rm", NGX_NET)


def curl(ip: str, path: str = "/", method: str = "GET", host: str | None = "127.0.0.1:8080", headers: dict | None = None, data: bytes | None = None,
         extra: list[str] | None = None) -> tuple[int, dict, str]:
    args = ["curl", "-s", "-m", "10", "--path-as-is", "-i", "-X", method, f"http://{ip}:8080{path}"]
    if method == "HEAD":
        args = ["curl", "-s", "-m", "10", "--path-as-is", "-I", f"http://{ip}:8080{path}"]
    if host is not None:
        args += ["-H", f"Host: {host}"]
    else:
        args += ["-H", "Host:"]
    for k, v in (headers or {}).items():
        args += ["-H", f"{k}: {v}"]
    if data is not None:
        args += ["--data-binary", "@-"]
    args += extra or []
    r = subprocess.run(args, capture_output=True, input=data, timeout=30)
    raw = r.stdout.decode("latin-1")
    if not raw:
        return 0, {}, ""
    head, _, body = raw.partition("\r\n\r\n")
    lines = head.split("\r\n")
    status = int(lines[0].split()[1])
    hdrs: dict[str, list[str]] = {}
    for l in lines[1:]:
        k, _, v = l.partition(":")
        hdrs.setdefault(k.strip().lower(), []).append(v.strip())
    return status, hdrs, body


SEC_HEADERS = ["content-security-policy", "x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy",
               "cross-origin-opener-policy", "cross-origin-resource-policy"]


@needs_docker
@pytest.mark.parametrize("host,expect", [("127.0.0.1:8080", 200), ("localhost:8080", 200), ("evil.example:8080", 0), ("127.0.0.1", 0), ("127.0.0.1:18081", 0),
                                          ("LOCALHOST:8080", 200), ("localhost:8080.evil.com", 0), ("127.0.0.1:8080 ", 200), ("0.0.0.0:8080", 0), ("[::1]:8080", 0),
                                          ("localhost:8080,evil.com", 0), ("evil.example", 0), ("evil.example:80", 0), ("", 400)])
def test_tc_vi_040_nginx_host_allowlist(ngx, host, expect):
    status, _, _ = curl(ngx, "/", host=host)
    if expect == 0:
        assert status in (0, 400), (host, status)  # 444(무응답) 또는 잘못된 Host 로 400 — 어느 쪽이든 거부
    else:
        assert status == expect, (host, status)


@needs_docker
@pytest.mark.parametrize("path,method,expected", [
    ("/", "GET", 200), ("/", "HEAD", 200), ("/", "POST", 403), ("/", "PUT", 403), ("/", "DELETE", 403), ("/", "PATCH", 403), ("/", "OPTIONS", 403), ("/", "TRACE", 405),
    ("/no/such/route", "GET", 200),  # SPA 폴백
    ("/assets/missing.js", "GET", 404), ("/assets/x", "POST", 403),
    ("/api/v1/x", "GET", 200), ("/api/v1/x", "POST", 200), ("/api/v1/x", "PUT", 200), ("/api/v1/x", "PATCH", 200), ("/api/v1/x", "DELETE", 200),
    ("/api/v1/x", "OPTIONS", 403), ("/api/v1/x", "TRACE", 405), ("/api/v1/x", "PROPFIND", 403),
    ("/api/v1/auth/session", "GET", 200), ("/api/v1/auth/session", "POST", 200), ("/api/v1/auth/session", "DELETE", 200), ("/api/v1/auth/session", "PUT", 403), ("/api/v1/auth/session", "PATCH", 403),
    ("/api/healthz", "GET", 200), ("/nginx-health", "GET", 200),
])
def test_tc_vi_041_nginx_method_matrix(ngx, path, method, expected):
    time.sleep(0.05)
    status, _, _ = curl(ngx, path, method)
    assert status == expected, (method, path, status)


@needs_docker
@pytest.mark.parametrize("path,method", [("/", "GET"), ("/nginx-health", "GET"), ("/api/healthz", "GET"), ("/api/v1/x", "GET"), ("/assets/missing.js", "GET"), ("/", "POST"),
                                         ("/", "TRACE"), ("/api/v1/auth/session", "PUT"), ("/api/readyz", "GET")])
def test_tc_vi_042_security_headers_present_exactly_once_on_all_responses(ngx, path, method):
    status, h, _ = curl(ngx, path, method)
    for k in SEC_HEADERS:
        assert len(h.get(k, [])) == 1, (path, method, status, k, h.get(k))
    csp = dict((d.strip().split(" ", 1) + [""])[:2] for d in h["content-security-policy"][0].split(";") if d.strip())
    if path.startswith("/api/"):        # W-FIX-INF(DEF-7-007): JSON 응답은 아무것도 불러오지 못하게 default-src 'none'
        assert csp == {"default-src": "'none'", "frame-ancestors": "'none'", "base-uri": "'none'", "form-action": "'none'"}, csp
    else:
        assert csp == {"default-src": "'self'", "script-src": "'self'", "style-src": "'self'", "style-src-attr": "'unsafe-inline'", "img-src": "'self' data:",
                       "font-src": "'self'", "connect-src": "'self'", "object-src": "'none'", "base-uri": "'none'", "frame-ancestors": "'none'", "form-action": "'self'"}, csp
    assert h["x-frame-options"] == ["DENY"] and h["x-content-type-options"] == ["nosniff"]
    assert "server" not in h or not re.search(r"\d", h["server"][0]), h.get("server")


@needs_docker
def test_tc_vi_043_security_headers_on_nginx_generated_errors(ngx):
    for host, path in (("127.0.0.1:8080", "/" + "a" * 9000), ):
        status, h, _ = curl(ngx, path, host=host)
        assert status in (414, 400), status
    status, h, _ = curl(ngx, "/api/v1/x", "POST", data=b"x" * 1_500_000, headers={"Content-Type": "application/json"})
    assert status == 413
    for k in SEC_HEADERS:
        assert h.get(k), (k, "413 응답에 보안 헤더 없음")


@needs_docker
def test_tc_vi_044_body_size_limit_boundaries(ngx):
    lim = 1024 * 1024
    for size, want in ((0, 200), (1024, 200), (lim - 1, 200), (lim, 200), (lim + 1, 413), (2 * lim, 413)):
        st, _, body = curl(ngx, "/api/v1/x", "POST", data=b"a" * size, headers={"Content-Type": "application/json"})
        assert st == want, (size, st)


@needs_docker
def test_tc_vi_045_proxy_headers_forwarding_and_hiding(ngx):
    st, h, body = curl(ngx, "/api/v1/things?q=1", "POST", host="localhost:8080", data=b"{}",
                       headers={"X-Forwarded-For": "6.6.6.6", "X-Forwarded-Proto": "https", "Content-Type": "application/json", "Cookie": "a=b", "Connection": "close"})
    assert st == 200
    echo = json.loads(body)
    seen = {k.lower(): v for k, v in echo["headers"].items()}
    assert echo["path"] == "/api/v1/things?q=1" and echo["method"] == "POST"
    assert seen["host"] == "localhost:8080"
    assert seen["x-forwarded-for"] != "6.6.6.6" and "6.6.6.6" not in seen["x-forwarded-for"] and "," not in seen["x-forwarded-for"]
    assert seen["x-forwarded-proto"] == "http"
    # 백엔드 보안 헤더는 숨기고 nginx 가 한 벌만
    assert h["content-security-policy"] == [h["content-security-policy"][0]] and "default-src *" not in h["content-security-policy"][0]
    assert h["x-frame-options"] == ["DENY"]
    assert "x-powered-by" not in h
    assert "stubsrv" not in " ".join(h.get("server", []))
    assert h["cache-control"] == ["no-store"]
    assert any(c.startswith("ytw_session=") and "HttpOnly" in c and "SameSite=strict" in c for c in h["set-cookie"])


@needs_docker
def test_tc_vi_046_healthz_readyz_rewrite_to_backend_root_paths(ngx):
    for p, back in (("/api/healthz", "/healthz"), ("/api/readyz", "/readyz")):
        st, _, body = curl(ngx, p)
        assert st == 200 and json.loads(body)["path"] == back
    st, _, body = curl(ngx, "/api/healthz?x=1")
    assert json.loads(body)["path"] == "/healthz"
    st, _, _ = curl(ngx, "/api/healthz", "POST")
    assert st == 200  # 관찰 O-VI-01: healthz 는 메서드 제한이 없어 POST 도 백엔드로 전달된다(스텁은 200)


@needs_docker
def test_tc_vi_047_auth_rate_limit_and_independence_from_api_zone(ngx_fresh):
    ngx = ngx_fresh
    codes = [curl(ngx, "/api/v1/auth/session", "POST", data=b"{}")[0] for _ in range(30)]
    assert codes[0] == 200
    assert 429 in codes, codes
    first = codes.index(429)
    assert 10 <= first <= 12, (first, codes)  # 즉시 1 + burst 10 = 11건 통과(+ 6초당 1건 보충 오차 1)
    assert set(codes[first:]) == {429}
    st, h, _ = curl(ngx, "/api/v1/auth/session", "POST", data=b"{}")
    assert st == 429
    for k in SEC_HEADERS:
        assert h.get(k), k
    # 같은 사이드의 다른 API 구역은 아직 여유가 있다(구역 분리)
    assert curl(ngx, "/api/v1/other")[0] == 200
    assert curl(ngx, "/")[0] == 200


@needs_docker
def test_tc_vi_048_api_rate_limit_triggers_on_flood(ngx):
    time.sleep(2)
    codes = []
    for _ in range(3):
        r = subprocess.run(["bash", "-c", f"for i in $(seq 1 200); do curl -s -o /dev/null -m 5 -w '%{{http_code}}\\n' -H 'Host: 127.0.0.1:8080' http://{ngx}:8080/api/v1/flood & done; wait"],
                           capture_output=True, text=True, timeout=60)
        codes += r.stdout.split()
    assert "429" in codes and "200" in codes, {c: codes.count(c) for c in set(codes)}


@needs_docker
@pytest.mark.parametrize("path", ["/.env", "/../etc/passwd", "/%2e%2e/etc/passwd", "/assets/../../etc/passwd", "/..%2f..%2fetc/passwd", "/assets/%2e%2e/%2e%2e/etc/passwd",
                                  "/etc/passwd", "/proc/self/environ", "/nginx.conf", "//etc/passwd", "/assets/..;/x", "/%00", "/assets/%00.js"])
def test_tc_vi_049_path_traversal_never_leaks_files(ngx, path):
    st, h, body = curl(ngx, path)
    assert "root:x:0:0" not in body and "worker_processes" not in body and "PATH=" not in body
    if st == 200:
        assert body.lstrip().lower().startswith("<!doctype html"), (path, body[:80])  # SPA 폴백만 허용


@needs_docker
def test_tc_vi_050_sourcemaps_and_dotfiles_not_served_and_cache_policy(ngx):
    st, h, body = curl(ngx, "/")
    assert st == 200 and h["cache-control"] == ["no-cache"]
    m = re.search(r'/assets/[^"\']+\.js', body)
    assert m, body[:300]
    st, h, jsbody = curl(ngx, m[0])
    assert st == 200 and "immutable" in h["cache-control"][0] and h["content-type"][0].startswith(("application/javascript", "text/javascript"))
    assert "sourceMappingURL" not in jsbody
    st, h, b = curl(ngx, m[0] + ".map")
    assert "mappings" not in b
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", body), "인라인 스크립트 금지"
    assert not re.search(r"<style", body), "인라인 <style> 금지"
    assert " onclick=" not in body and "javascript:" not in body


@needs_docker
def test_tc_vi_051_header_injection_and_oversized_headers(ngx):
    st, h, _ = curl(ngx, "/", headers={"X-Big": "a" * 9000})
    assert st == 400
    st, h, _ = curl(ngx, "/", host="127.0.0.1:8080\r\nX-Injected: 1")
    assert "x-injected" not in h
    st, h, body = curl(ngx, "/api/v1/x%0d%0aX-Evil:1")
    assert "x-evil" not in h


@needs_docker
def test_tc_vi_052_slowloris_header_timeout(ngx):
    import socket
    s = socket.create_connection((ngx, 8080), timeout=20)
    s.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nX-Slow: a")
    t0 = time.time()
    s.settimeout(20)
    data = s.recv(1024)
    dt = time.time() - t0
    s.close()
    assert dt < 14, dt  # client_header_timeout 10s
    assert data == b"" or b"408" in data


@needs_docker
def test_tc_vi_054_access_log_is_json_without_query_string_or_cookies(ngx):
    curl(ngx, "/api/v1/probe?token=Q-SECRET-1&x=2", headers={"Cookie": "ytw_session=C-SECRET-2", "Authorization": "Bearer A-SECRET-3", "User-Agent": "ua-probe"})
    curl(ngx, "/?page=Q-SECRET-4")
    time.sleep(1)
    lg = docker("logs", f"{PROJECT}-ngx-web")
    for sec in ("C-SECRET-2", "A-SECRET-3", "ua-probe"):
        assert sec not in lg.stdout + lg.stderr, sec
    for sec in ("Q-SECRET-1", "Q-SECRET-4", "token="):
        assert sec not in lg.stdout, sec  # 접근 로그(stdout)
    rows = [json.loads(l) for l in lg.stdout.splitlines() if l.startswith("{")]
    assert any(r["uri"] == "/api/v1/probe" and r["method"] == "GET" and r["status"] == 200 for r in rows), rows[-3:]
    assert all(set(r) == {"time", "method", "uri", "status", "bytes", "request_time"} for r in rows)


@needs_docker
@pytest.mark.xfail(strict=False, reason="DEF-VI-003 부분 조치(7단계 재확인): 속도 제한(limit_req) 경로는 쿼리가 오류 로그에 남지 않는다(통과). 업스트림 오류(504/502) 줄에는 요청 줄이 남는 잔여가 수용됨(DEC-045, M2 OAuth 설계 때 재평가). 이 하네스는 stub api 기동 전 첫 요청이 502 가 되면 잔여 경로를 타 XFAIL, 아니면 XPASS 가 되는 경쟁이 있어 strict 를 해제")
def test_tc_vi_055_error_log_never_contains_query_strings(ngx_fresh):
    for _ in range(30):
        curl(ngx_fresh, "/api/v1/auth/session?code=ZZ-SECRET-9", "POST", data=b"{}")
    time.sleep(1)
    lg = docker("logs", f"{PROJECT}-ngxf-web")
    assert "ZZ-SECRET-9" not in lg.stdout + lg.stderr


@needs_docker
def test_tc_vi_056_nginx_starts_without_config_warnings(ngx_fresh):
    # 회귀: DEF-VI-004 (gzip_types 에 text/html 중복 -> 시작 때마다 [warn] duplicate MIME type)
    lg = docker("logs", f"{PROJECT}-ngxf-web")
    text = lg.stdout + lg.stderr
    assert not re.search(r"\[(warn|emerg|alert|crit|error)\]|nginx: \[", text), text
    assert docker("exec", f"{PROJECT}-ngxf-web", "nginx", "-t").returncode == 0
    t = docker("exec", f"{PROJECT}-ngxf-web", "nginx", "-t")
    assert "successful" in t.stderr + t.stdout and "warn" not in (t.stderr + t.stdout)
    # gzip 은 정적 HTML/JS/CSS 에만 동작해야 한다(압축 대상 확인)
    st, h, _ = curl(ngx_fresh, "/", headers={"Accept-Encoding": "gzip"})
    assert st == 200 and h.get("content-encoding") == ["gzip"]


@needs_docker
def test_tc_vi_053_slow_request_body_is_cut_off(ngx):
    import socket
    s = socket.create_connection((ngx, 8080), timeout=25)
    s.sendall(b"POST /api/v1/x HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{")
    t0 = time.time()
    s.settimeout(25)
    try:
        data = s.recv(2048)
    except socket.timeout:
        data = b"TIMEOUT"
    dt = time.time() - t0
    s.close()
    assert data != b"TIMEOUT" and dt < 15, (dt, data[:60])  # client_body_timeout 10s
    assert data == b"" or b"408" in data


# ---------------------------------------------------------------- 일회용 PostgreSQL 초기화
def _fresh_db(tmp_path: Path, owner_pw: str, app_pw: str, su_pw: str, name: str):
    sec = tmp_path / "sec"
    sec.mkdir(exist_ok=True)
    for n, v in (("db_superuser_password", su_pw), ("db_owner_password", owner_pw), ("db_app_password", app_pw)):
        (sec / n).write_text(v)
        (sec / n).chmod(0o644)
    db = DOCKER_DIR / "db"
    cname = f"{PROJECT}-{name}"
    docker("rm", "-f", "-v", cname)
    args = ["run", "-d", "--name", cname, "--network", "none", "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true", "--user", "999:999",
            "--tmpfs", "/tmp:rw,noexec,nosuid,uid=999,gid=999", "--tmpfs", "/run/postgresql:rw,noexec,nosuid,uid=999,gid=999,mode=0775", "--tmpfs", "/var/lib/postgresql/data:rw,uid=999,gid=999,mode=0700",
            "-e", "POSTGRES_USER=postgres", "-e", "POSTGRES_DB=postgres", "-e", "POSTGRES_PASSWORD_FILE=/run/secrets/db_superuser_password",
            "-e", "POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=C.UTF-8 --data-checksums"]
    for n in ("db_superuser_password", "db_owner_password", "db_app_password"):
        args += ["-v", f"{sec/n}:/run/secrets/{n}:ro"]
    args += ["--tmpfs", "/backups:rw,uid=999,gid=999,mode=0700", "-v", f"{db/'bin'/'ytweb-db'}:/usr/local/bin/ytweb-db:ro",
             "-v", f"{db/'init'/'01-roles.sh'}:/docker-entrypoint-initdb.d/01-roles.sh:ro", "-v", f"{db/'schema-grants.sql'}:/usr/local/share/ytweb/schema-grants.sql:ro",
             "-v", f"{db/'audit-guard.sql'}:/usr/local/share/ytweb/audit-guard.sql:ro", "-v", f"{db/'pg_hba.conf'}:/etc/postgresql/pg_hba.conf:ro", f"{PROJECT}-db:local",
             "postgres", "-c", "hba_file=/etc/postgresql/pg_hba.conf", "-c", "listen_addresses=*", "-c", "password_encryption=scram-sha-256"]
    r = docker(*args)
    assert r.returncode == 0, r.stderr
    return cname


def _wait_db(cname: str, ok=True, tries=60) -> bool:
    for _ in range(tries):
        st = docker("inspect", cname, "--format", "{{.State.Running}}").stdout.strip()
        if st != "true":
            return False
        if docker("exec", cname, "test", "-f", "/var/lib/postgresql/data/.ytweb-init-ok").returncode == 0 and \
                docker("exec", cname, "pg_isready", "-q", "-h", "127.0.0.1").returncode == 0:
            return True
        time.sleep(1)
    return False


def dbq(cname: str, user: str, pwfile: str, sql: str, db: str = "ytweb") -> subprocess.CompletedProcess:
    return docker("exec", "-i", cname, "bash", "-c",
                  f'PGPASSWORD=$(cat /run/secrets/{pwfile}) psql -h 127.0.0.1 -U {user} -d {db} -X -At -v ON_ERROR_STOP=1 -c "$0"', sql)


GOOD = ("o" * 20 + "WNER9876543210", "a" * 20 + "PP0123456789zz", "s" * 20 + "UPER111222333")


@needs_docker
def test_tc_vi_060_fresh_init_creates_least_privilege_roles(tmp_path):
    cname = _fresh_db(tmp_path, *GOOD, name="initok")
    try:
        assert _wait_db(cname), docker("logs", cname).stderr[-1500:]
        r = dbq(cname, "postgres", "db_superuser_password",
                "select rolname||':'||rolsuper::int||rolcreaterole::int||rolcreatedb::int||rolreplication::int||rolbypassrls::int||':'||rolconnlimit from pg_roles where rolname like 'ytweb%' order by 1", db="postgres")
        assert r.stdout.split() == ["ytweb_app:00000:30", "ytweb_owner:00000:10"], r.stdout + r.stderr
        for sql, want in (("select string_agg(array_to_string(rolconfig,';'),',' order by rolname) from pg_roles where rolname like 'ytweb%'", "TimeZone=UTC,TimeZone=UTC"), ("select pg_encoding_to_char(encoding) from pg_database where datname='ytweb'", "UTF8"),
                          ("select datacl::text from pg_database where datname='ytweb'", "{ytweb_owner=CTc/ytweb_owner,ytweb_app=c/ytweb_owner}"),
                          ("select nspowner::regrole::text from pg_namespace where nspname='public'", "ytweb_owner"),
                          ("select has_schema_privilege('ytweb_app','public','USAGE')::text||has_schema_privilege('ytweb_app','public','CREATE')::text", "truefalse"),
                          ("select has_schema_privilege('public','public','USAGE')::text", "false"),
                          ("select count(*) from pg_authid where rolname like 'ytweb%' and rolpassword like 'SCRAM-SHA-256$%'", "2")):
            r = dbq(cname, "postgres", "db_superuser_password", sql)
            assert r.stdout.strip() == want, (sql, r.stdout, r.stderr)
        # 소유자가 만든 새 테이블/시퀀스에 앱 기본 권한이 붙는지
        assert dbq(cname, "ytweb_owner", "db_owner_password", "create table t1(id serial primary key, v text); create table audit_log(id serial primary key)").returncode == 0
        r = dbq(cname, "ytweb_owner", "db_owner_password",
                "select has_table_privilege('ytweb_app','t1','SELECT,INSERT,UPDATE,DELETE')::text||has_table_privilege('ytweb_app','t1','TRUNCATE')::text||has_table_privilege('ytweb_app','t1','REFERENCES')::text||has_sequence_privilege('ytweb_app','t1_id_seq','USAGE')::text")
        assert r.stdout.strip() == "truefalsefalsetrue", r.stdout + r.stderr
        # audit-guard: 권한을 일부러 늘린 뒤 가드가 회수하는지
        assert dbq(cname, "ytweb_owner", "db_owner_password", "select has_table_privilege('ytweb_app','audit_log','UPDATE')::text").stdout.strip() == "true"
        r = docker("exec", "-i", cname, "bash", "-c", "PGPASSWORD=$(cat /run/secrets/db_owner_password) psql -h 127.0.0.1 -U ytweb_owner -d ytweb -X -q -v ON_ERROR_STOP=1 -f /usr/local/share/ytweb/audit-guard.sql")
        assert r.returncode == 0, r.stderr
        # PUBLIC 에 UPDATE 가 열려 있어 앱 계정 회수만으로는 막을 수 없으면 가드는 실패(시끄럽게)해야 한다
        assert dbq(cname, "ytweb_owner", "db_owner_password", "grant update on audit_log to public").returncode == 0
        r = docker("exec", "-i", cname, "bash", "-c", "PGPASSWORD=$(cat /run/secrets/db_owner_password) psql -h 127.0.0.1 -U ytweb_owner -d ytweb -X -q -v ON_ERROR_STOP=1 -f /usr/local/share/ytweb/audit-guard.sql")
        assert r.returncode != 0 and "audit_log 권한 회수에 실패" in r.stderr, r.stderr
        assert dbq(cname, "ytweb_owner", "db_owner_password", "revoke update on audit_log from public").returncode == 0
        r = dbq(cname, "ytweb_owner", "db_owner_password",
                "select has_table_privilege('ytweb_app','audit_log','UPDATE')::text||has_table_privilege('ytweb_app','audit_log','DELETE')::text||has_table_privilege('ytweb_app','audit_log','TRUNCATE')::text||has_table_privilege('ytweb_app','audit_log','INSERT')::text||has_table_privilege('ytweb_app','audit_log','SELECT')::text")
        assert r.stdout.strip() == "falsefalsefalsetruetrue", r.stdout
        # 로그에 비밀번호가 없다
        logs = docker("logs", cname)
        for pw in GOOD:
            assert pw not in logs.stdout + logs.stderr
    finally:
        docker("rm", "-f", "-v", cname)


@needs_docker
@pytest.mark.parametrize("owner,app,su,why", [
    ("short", GOOD[1], GOOD[2], "소유자 비밀번호 15자 미만"),
    (GOOD[0], "short", GOOD[2], "앱 비밀번호 15자 미만"),
    ("x" * 15, GOOD[1], GOOD[2], "경계: 소유자 15자"),
    (GOOD[0], GOOD[0], GOOD[2], "소유자=앱 동일"),
    ("", GOOD[1], GOOD[2], "소유자 비어 있음"),
])
def test_tc_vi_061_init_fails_closed_on_weak_or_equal_passwords(tmp_path, owner, app, su, why):
    cname = _fresh_db(tmp_path, owner, app, su, name="initbad")
    try:
        ok = _wait_db(cname, tries=25)
        assert not ok, f"{why}: 초기화가 성공해 버림"
        logs = docker("logs", cname)
        assert "[ytweb-init]" in logs.stdout + logs.stderr, logs.stderr[-500:]
        # 헬스 표식이 없어 healthy 로 보이지 않는다
        assert docker("exec", cname, "test", "-f", "/var/lib/postgresql/data/.ytweb-init-ok").returncode != 0
    finally:
        docker("rm", "-f", "-v", cname)


@needs_docker
def test_tc_vi_062_exactly_16_char_passwords_are_accepted(tmp_path):
    cname = _fresh_db(tmp_path, "o" * 16, "a" * 16, "s" * 20, name="init16")
    try:
        assert _wait_db(cname), docker("logs", cname).stderr[-800:]
    finally:
        docker("rm", "-f", "-v", cname)


@needs_docker
def test_tc_vi_063_pg_hba_enforced_for_local_and_loopback_connections(tmp_path):
    cname = _fresh_db(tmp_path, *GOOD, name="hba")
    try:
        assert _wait_db(cname)
        def conn(user, pw, db, host="127.0.0.1"):
            return docker("exec", "-i", cname, "bash", "-c", f'PGPASSWORD={pw} psql -h {host} -U {user} -d {db} -X -At -c "select 1"')
        assert conn("ytweb_app", GOOD[1], "ytweb").stdout.strip() == "1"
        assert conn("ytweb_owner", GOOD[0], "ytweb").stdout.strip() == "1"
        assert conn("postgres", GOOD[2], "postgres").stdout.strip() == "1"
        for u, p, d in (("ytweb_app", GOOD[1], "postgres"), ("ytweb_app", GOOD[1], "template1"), ("ytweb_owner", GOOD[0], "postgres"), ("ytweb_app", "wrong", "ytweb"),
                        ("ytweb_app", GOOD[0], "ytweb"), ("ytweb_owner", GOOD[1], "ytweb"), ("ytweb_app", GOOD[2], "ytweb"), ("nobody", "x", "ytweb"), ("replicator", "x", "replication")):
            r = conn(u, p, d)
            assert r.returncode != 0 and r.stdout.strip() == "", (u, d, r.stdout)
        # 유닉스 소켓(local) 접속도 비밀번호가 필요하다(trust 금지)
        for u, d in (("postgres", "postgres"), ("ytweb_app", "ytweb"), ("ytweb_owner", "ytweb")):
            r = docker("exec", cname, "psql", "-w", "-U", u, "-d", d, "-X", "-At", "-c", "select 1")
            assert r.returncode != 0 and "password" in r.stderr.lower(), (u, r.stderr)
        r = docker("exec", cname, "bash", "-c", f"PGPASSWORD={GOOD[2]} psql -U postgres -d postgres -X -At -c 'select 1'")
        assert r.stdout.strip() == "1"
        r = docker("exec", cname, "bash", "-c", f"PGPASSWORD={GOOD[1]} psql -U ytweb_app -d postgres -X -At -c 'select 1'")
        assert r.returncode != 0
        # 앱 계정: DDL·파일·서버 프로그램·역할 변경·확장 불가
        for sql in ("create table z(a int)", "create schema s", "create extension pg_trgm", "create role r", "alter role ytweb_app superuser", "set role ytweb_owner",
                    "select pg_read_file('/etc/passwd')", "copy (select 1) to program 'id'", "copy (select 1) to '/tmp/x'", "select lo_import('/etc/passwd')",
                    "create function f() returns int language sql as 'select 1'", "create temp table tt(a int)", "alter database ytweb owner to ytweb_app",
                    "alter system set fsync=off", "select pg_reload_conf()"):
            r = dbq(cname, "ytweb_app", "db_app_password", sql)
            assert r.returncode != 0, (sql, r.stdout)
    finally:
        docker("rm", "-f", "-v", cname)


def _exec_tool(cname_: str, *a: str) -> subprocess.CompletedProcess:
    if os.environ.get("VI_SH_TRACE"):  # 줄 커버리지 측정: xtrace 를 별도 파일 기술자로 모은다
        return docker("exec", cname_, "bash", "-c", "exec 9>>/tmp/cov.trace; PS4='+COV:${BASH_SOURCE}:${LINENO}:' BASH_XTRACEFD=9 bash -x /usr/local/bin/ytweb-db \"$@\"", "_", *a)
    return docker("exec", cname_, "ytweb-db", *a)


@needs_docker
def test_tc_vi_064_dump_restore_roundtrip_single_transaction_and_audit_guard(tmp_path):
    cn = _fresh_db(tmp_path, *GOOD, name="tool")
    try:
        assert _wait_db(cn), docker("logs", cn).stderr[-800:]
        own = lambda sql: dbq(cn, "ytweb_owner", "db_owner_password", sql)
        assert own("create table t1(id serial primary key, v text); create table audit_log(id serial primary key, v text); "
                   "insert into t1(v) select 'row'||g from generate_series(1,20000) g; insert into audit_log(v) values ('a1')").returncode == 0
        r = _exec_tool(cn, "dump", "good.dump")
        assert r.returncode == 0 and "크기(바이트):" in r.stdout, r.stderr
        assert _exec_tool(cn, "dump", "good.dump").returncode == 1  # 덮어쓰기 거부
        r = _exec_tool(cn, "list", "good.dump")
        assert r.returncode == 0 and "목차 항목 수:" in r.stdout
        c = _exec_tool(cn, "counts")
        assert c.returncode == 0 and "audit_log 1" in c.stdout and "t1 20000" in c.stdout, c.stdout
        # 복원은 변경분을 되돌리고, 앱 계정에 새로 생긴 audit_log UPDATE 권한을 다시 회수한다
        assert own("insert into t1(v) values ('later'); grant update, delete, truncate on audit_log to ytweb_app").returncode == 0
        assert own("select has_table_privilege('ytweb_app','audit_log','UPDATE')::text").stdout.strip() == "true"
        r = _exec_tool(cn, "restore", "good.dump")
        assert r.returncode == 0 and "복원 완료" in r.stdout, r.stdout + r.stderr
        assert own("select count(*) from t1").stdout.strip() == "20000"
        r = own("select has_table_privilege('ytweb_app','audit_log','UPDATE')::text||has_table_privilege('ytweb_app','audit_log','DELETE')::text||has_table_privilege('ytweb_app','audit_log','TRUNCATE')::text")
        assert r.stdout.strip() == "falsefalsefalse", r.stdout
        # 중간에 실패하는(끝이 잘린) 덤프: 목차는 읽히지만 복원은 실패 -> 단일 트랜잭션이라 기존 데이터가 그대로
        assert docker("exec", cn, "bash", "-c", "f=/backups/good.dump; n=$(stat -c %s $f); head -c $((n-3000)) $f > /backups/cut.dump").returncode == 0
        assert _exec_tool(cn, "list", "cut.dump").returncode == 0
        assert own("insert into t1(v) values ('keepme')").returncode == 0
        r = _exec_tool(cn, "restore", "cut.dump")
        assert r.returncode != 0, "잘린 덤프 복원이 성공해 버림"
        assert own("select count(*) from t1").stdout.strip() == "20001", "실패한 복원이 기존 데이터를 지움(트랜잭션 아님)"
        assert own("select count(*) from t1 where v='keepme'").stdout.strip() == "1"
        # 경로 탈출: 백업 폴더 밖에 파일을 만들거나 읽지 못한다
        assert docker("exec", cn, "bash", "-c", "cp /backups/good.dump /tmp/outside.dump").returncode == 0
        for cmd in ("dump", "restore", "list", "remove"):
            r = _exec_tool(cn, cmd, "../tmp/outside.dump")
            assert r.returncode == 1 and "올바르지 않습니다" in r.stderr, (cmd, r.stderr)
        assert docker("exec", cn, "test", "-f", "/tmp/outside.dump").returncode == 0
        assert _exec_tool(cn, "dump", "../tmp/newout.dump").returncode == 1
        assert docker("exec", cn, "test", "-e", "/tmp/newout.dump").returncode != 0
        # 읽을 수 없는 파일은 복원 전에 친절한 오류로 막는다(pg_restore 로 넘어가기 전)
        assert docker("exec", cn, "bash", "-c", "echo garbage > /backups/junk.dump").returncode == 0
        r = _exec_tool(cn, "restore", "junk.dump")
        assert r.returncode == 1 and "읽을 수 없습니다" in r.stderr, r.stderr
        assert own("select count(*) from t1").stdout.strip() == "20001"
        # 나쁜 이름/없는 파일
        assert _exec_tool(cn, "restore", "../good.dump").returncode == 1
        assert _exec_tool(cn, "restore", "none.dump").returncode == 1
        # reset-schema: 테이블 삭제 + 권한 재부여(앱은 새 테이블에 기본 DML 만)
        assert _exec_tool(cn, "reset-schema").returncode == 0
        assert own("select count(*) from information_schema.tables where table_schema='public'").stdout.strip() == "0"
        assert own("create table t9(id int); select has_table_privilege('ytweb_app','t9','INSERT')::text||has_table_privilege('ytweb_app','t9','TRUNCATE')::text").stdout.strip().endswith("truefalse")
        assert _exec_tool(cn, "remove", "good.dump").returncode == 0 and _exec_tool(cn, "list", "good.dump").returncode == 1
        # 덤프 파일 권한은 소유자 전용(umask 077)
        _exec_tool(cn, "dump", "perm.dump")
        assert docker("exec", cn, "stat", "-c", "%a", "/backups/perm.dump").stdout.strip() == "600"
    finally:
        if os.environ.get("VI_SH_TRACE"):
            with open(os.environ["VI_SH_TRACE"], "a", encoding="utf-8") as f:
                f.write(docker("exec", cn, "cat", "/tmp/cov.trace").stdout)
        docker("rm", "-f", "-v", cn)


# ======================================================================================
# C. 실가동 스택 실측 (VI_LIVE=1)
# ======================================================================================
PROBE = f"vi-probe-{os.getpid()}-{int(time.time())}"


def cname(s: str) -> str:
    return f"{PROJECT}-{s}-1"


def inspect(s: str) -> dict:
    r = docker("inspect", cname(s))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)[0]


@live
@pytest.mark.parametrize("s", SERVICES)
def test_tc_vi_100_live_container_security_settings(s):
    d = inspect(s)
    h = d["HostConfig"]
    uid = d["Config"]["User"]
    assert re.fullmatch(r"\d+:\d+", uid) and int(uid.split(":")[0]) > 0
    assert h["ReadonlyRootfs"] is True and h["Privileged"] is False
    assert h["CapDrop"] == ["ALL"] and not h["CapAdd"]
    assert h["SecurityOpt"] == ["no-new-privileges:true"]
    assert h["Init"] is True and h["PidMode"] == "" and h["IpcMode"] == "private" and not h["Devices"] and h["UsernsMode"] == ""
    assert h["Memory"] > 0 and h["NanoCpus"] > 0 and h["PidsLimit"] > 0
    assert h["MemorySwap"] in (2 * h["Memory"], h["Memory"])  # 스왑 무제한 아님
    assert h["LogConfig"]["Type"] == "json-file" and h["LogConfig"]["Config"] == {"max-file": "3", "max-size": "10m"}
    for m in d["Mounts"]:
        assert "docker.sock" not in m["Source"] and m["Source"] != "/"
        if m["Type"] == "bind":
            # 호스트 폴더 마운트 금지: 비밀 파일 1개씩(읽기 전용)만 허용
            assert m["Destination"].startswith("/run/secrets/") and m["RW"] is False, m
            assert re.search(r"/web/secrets/" + re.escape(m["Destination"].rsplit("/", 1)[1]) + r"$", m["Source"]), m
        else:
            assert m["Type"] == "volume" and "/volumes/" in m["Source"] and m["Name"].startswith(f"{PROJECT}_"), m
    assert all(not b.split(":")[0].startswith(("/", ".", "~")) for b in (h.get("Binds") or []))  # 이름 있는 볼륨만
    for k in ("ExtraHosts", "Dns"):
        assert not h.get(k)
    assert d["Config"]["Image"].startswith(f"{PROJECT}-")


@live
@pytest.mark.parametrize("s", ["db", "api", "worker", "web"])
def test_tc_vi_101_live_process_has_no_capabilities_and_no_new_privs(s):
    r = docker("exec", cname(s), "sh", "-c", "grep -E '^(CapEff|CapPrm|CapBnd|NoNewPrivs|Uid|Seccomp):' /proc/1/status; grep -E '^(CapEff|NoNewPrivs):' /proc/self/status")
    out = r.stdout
    assert re.search(r"CapEff:\s+0{16}", out) and re.search(r"CapPrm:\s+0{16}", out) and re.search(r"CapBnd:\s+0{16}", out), out
    assert re.search(r"NoNewPrivs:\s+1", out) and re.search(r"Seccomp:\s+2", out)
    uid = int(re.search(r"Uid:\s+(\d+)", out)[1])
    assert uid in (999, 10001, 101)
    ro = docker("exec", cname(s), "sh", "-c", "touch /vi_probe 2>&1; cp /bin/sh /tmp/vi_sh 2>/dev/null && /tmp/vi_sh -c true 2>&1")
    assert "Read-only file system" in ro.stdout and "Permission denied" in ro.stdout, ro.stdout


@live
def test_tc_vi_102_live_published_ports_only_loopback_one():
    ports = {}
    for s in SERVICES:
        d = inspect(s)
        ports[s] = d["NetworkSettings"]["Ports"]
        assert not d["HostConfig"]["PublishAllPorts"]
    pub = {s: {k: v for k, v in p.items() if v} for s, p in ports.items()}
    assert {s: p for s, p in pub.items() if p} == {"web": {"8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": PORT}]}}, pub
    listeners = []
    for l in Path("/proc/net/tcp").read_text().splitlines()[1:]:
        f = l.split()
        if f[3] == "0A":
            ip, port = f[1].split(":")
            if int(port, 16) in (int(PORT), 8000, 5432, 8080):
                listeners.append((ip, int(port, 16)))
    assert (("0100007F", int(PORT))) in listeners
    assert all(ip == "0100007F" for ip, p in listeners if p == int(PORT)), listeners
    assert not [x for x in listeners if x[1] in (8000, 5432)]
    # 호스트의 다른 주소로는 접속 불가
    ips = sh(["hostname", "-I"]).stdout.split()
    assert ips
    for ip in ips:
        r = subprocess.run(["curl", "-s", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}", "-H", "Host: 127.0.0.1:8080", f"http://{ip}:{PORT}/api/healthz"], capture_output=True, text=True)
        assert r.stdout.strip() in ("000", ""), (ip, r.stdout)
    for p in (5432, 8000):
        r = subprocess.run(["curl", "-s", "-m", "2", f"http://127.0.0.1:{p}/"], capture_output=True, text=True)
        assert r.returncode != 0 or r.stdout == ""


@live
@pytest.mark.xfail(strict=True, reason="낡은 시험(7단계 확인): DEC-045 이후 망이 front/back/edge 3개이고 `_app` 단일망은 없다. 새 구성의 망·소속은 web/tests_integration IT-521·IT-530 이 실가동에서 직접 검증한다. 시험을 새 구성으로 고치는 것은 6단계(W-INF) 소관")
def test_tc_vi_103_live_networks_internal_and_membership():
    n = json.loads(docker("network", "inspect", f"{PROJECT}_app").stdout)[0]
    assert n["Internal"] is True
    assert {c["Name"] for c in n["Containers"].values()} == {cname(s) for s in ("db", "api", "worker", "web")}
    e = json.loads(docker("network", "inspect", f"{PROJECT}_edge").stdout)[0]
    assert e["Internal"] is False and {c["Name"] for c in e["Containers"].values()} == {cname("web")}
    assert docker("network", "inspect", f"{PROJECT}_egress").returncode != 0, "기본 실행에 egress 네트워크가 있으면 안 됨"
    for s in ("db", "api", "worker"):
        assert set(inspect(s)["NetworkSettings"]["Networks"]) == {f"{PROJECT}_app"}


@live
@pytest.mark.parametrize("s,cmd", [
    ("api", "python -c \"import socket;socket.create_connection(('1.1.1.1',443),3)\""),
    ("api", "python -c \"import socket;socket.create_connection(('8.8.8.8',53),3)\""),
    ("api", "python -c \"import socket;socket.gethostbyname('example.com')\""),
    ("api", "python -c \"import socket;socket.create_connection(('169.254.169.254',80),3)\""),
    ("worker", "python -c \"import socket;socket.create_connection(('1.1.1.1',443),3)\""),
    ("worker", "python -c \"import socket;socket.gethostbyname('example.com')\""),
    ("db", "bash -c 'echo > /dev/tcp/1.1.1.1/443'"),
    ("db", "bash -c 'echo > /dev/tcp/8.8.8.8/53'"),
])
def test_tc_vi_104_live_api_worker_db_have_no_outbound_connectivity(s, cmd):
    r = docker("exec", cname(s), "sh", "-c", cmd, timeout=30)
    assert r.returncode != 0, (s, cmd, r.stdout, r.stderr)


@live
def test_tc_vi_105_live_lateral_paths_between_services():
    # 정상 경로: api->db 5432, web->api 8000
    ok = docker("exec", cname("api"), "python", "-c", "import socket;socket.create_connection(('db',5432),3)")
    assert ok.returncode == 0
    ok = docker("exec", cname("web"), "wget", "-q", "-O", "/dev/null", "http://api:8000/healthz")
    assert ok.returncode == 0
    # db 는 아무에게도 연결을 열 필요가 없다 / 워커·api 는 web 으로 접속할 이유가 없다 (관찰만)
    r = docker("exec", cname("db"), "bash", "-c", "echo > /dev/tcp/api/8000")
    assert r.returncode == 0  # 같은 internal 네트워크이므로 도달 가능(관찰)


@live
@pytest.mark.xfail(strict=False, reason="DEF-VI-001 부분 조치(7단계 재확인): 3망 분리(DEC-045)로 web 은 db 에 도달하지 못한다(통과). 외부 egress(edge 경유)는 수용된 잔여다. 이 시험의 egress 판정은 wget 종료 코드라 프록시가 403 을 돌려주는 환경에서는 XPASS 가 되고(연결은 됨), 직접 차단 환경이 아니면 실패한다 -> 환경 의존이라 strict 를 해제")
def test_tc_vi_106_live_web_container_is_isolated_from_db_and_internet():
    r = docker("exec", cname("web"), "sh", "-c", "timeout 4 nc -z db 5432")
    assert r.returncode != 0, "web 이 db 포트에 도달 가능"
    r = docker("exec", cname("web"), "sh", "-c", "timeout 4 wget -q -T 3 -O /dev/null http://1.1.1.1/")
    assert r.returncode != 0, "web 이 인터넷으로 나갈 수 있음"


@live
def test_tc_vi_107_live_secrets_not_in_env_images_or_inspect(request):
    run = RUN
    assert run is not None
    sec = {n: (run / "web" / "secrets" / n).read_text().strip() for n in ("db_superuser_password", "db_owner_password", "db_app_password")}
    assert len(set(sec.values())) == 3 and all(len(v) >= 32 for v in sec.values())
    for s in SERVICES:
        raw = docker("inspect", cname(s)).stdout
        for n, v in sec.items():
            assert v not in raw, (s, n)
        env = {e.split("=", 1)[0]: e.split("=", 1)[1] for e in inspect(s)["Config"]["Env"]}
        for k, v in env.items():
            if re.search(r"(PASS|SECRET|TOKEN|KEY)", k) and k != "GPG_KEY":  # GPG_KEY: 파이썬 베이스 이미지의 공개 서명키 ID
                assert k.endswith(("_FILE", "_DIR")) and v.startswith(("/run/secrets/", "/var/lib/ytweb/")), (s, k)
    for img in ("api", "web", "db"):
        hist = docker("history", "--no-trunc", "--format", "{{.CreatedBy}}", f"{PROJECT}-{img}:local").stdout
        save = subprocess.run(f"docker save {PROJECT}-{img}:local", shell=True, capture_output=True, timeout=300).stdout
        for n, v in sec.items():
            assert v not in hist and v.encode() not in save, (img, n)
    expected = {"db": ["db_app_password", "db_owner_password", "db_superuser_password"], "api": ["db_app_password"], "worker": ["db_app_password"], "migrate": None, "web": None}
    for s in ("db", "api", "worker"):
        r = docker("exec", cname(s), "ls", "/run/secrets")
        assert r.stdout.split() == expected[s], (s, r.stdout)
    assert docker("exec", cname("web"), "ls", "/run/secrets").returncode != 0
    # 비밀 파일 값이 로그에 없다
    for s in SERVICES:
        lg = docker("logs", cname(s))
        for v in sec.values():
            assert v not in lg.stdout + lg.stderr, s


@live
def test_tc_vi_108_live_image_contents_no_tests_maps_envfiles_or_toolchain():
    def find(img: str, where: str, expr: str) -> list[str]:
        r = docker("run", "--rm", "--network", "none", "--entrypoint", "sh", f"{PROJECT}-{img}:local", "-c", f"find {where} {expr} 2>/dev/null")
        return r.stdout.split()
    assert find("web", "/usr/share/nginx/html", "-type f") and not find("web", "/usr/share/nginx/html", "\\( -name '*.map' -o -name '*.ts' -o -name '*.tsx' -o -name '*.test.*' \\)")
    assert not find("api", "/app /opt/venv/lib", "\\( -name '.env*' -o -name 'token*.json' -o -name 'client_secret*' -o -name '.git' -o -name '*.sqlite3' -o -path '*/approvals/*' \\)")
    assert not find("api", "/app", "-type d -name tests")
    assert not find("api", "/app", "-type d \\( -name data -o -name secrets \\)")
    for img in ("api", "web", "db"):
        d = json.loads(docker("image", "inspect", f"{PROJECT}-{img}:local").stdout)[0]
        assert re.fullmatch(r"\d+(:\d+)?", d["Config"]["User"]) and int(d["Config"]["User"].split(":")[0]) > 0
        env = " ".join(d["Config"]["Env"])
        assert not re.search(r"(PASSWORD|SECRET|TOKEN)=[^ ]", env.replace("PASSWORD_FILE", ""))
    assert not find("api", "/usr/bin /usr/local/bin /bin", "\\( -name gcc -o -name cc -o -name make -o -name curl -o -name git -o -name sudo \\)")
    assert not find("web", "/usr/bin /bin /usr/local/bin", "\\( -name gcc -o -name node -o -name npm -o -name git -o -name sudo \\)")


@live
def test_tc_vi_109_live_healthchecks_report_and_detect_failure():
    for s in ("db", "api", "worker", "web"):
        d = inspect(s)
        assert d["State"]["Health"]["Status"] == "healthy", s
    hc = "import os,sys; me=str(os.getpid()); sys.exit(0 if any(b'ytweb.worker' in open('/proc/'+p+'/cmdline','rb').read() for p in os.listdir('/proc') if p.isdigit() and p!=me) else 1)"
    assert docker("exec", cname("worker"), "python", "-c", hc).returncode == 0
    assert docker("exec", cname("api"), "python", "-c", hc).returncode == 1  # 워커가 없으면 실패
    mig = inspect("migrate")
    assert mig["State"]["Status"] == "exited" and mig["State"]["ExitCode"] == 0
    # DB 초기화 표식이 없으면 healthcheck 가 실패(반쯤 초기화된 볼륨 방어)
    t = docker("exec", cname("db"), "bash", "-c", 'f=$PGDATA/.ytweb-init-ok; mv $f $f.bak; pg_isready -q -h 127.0.0.1 -p 5432 -U ytweb_app -d ytweb && test -f "$f"; rc=$?; mv $f.bak $f; echo $rc')
    assert t.stdout.strip() == "1", t


def _live_psql(user: str, pwfile: str, sql: str, db: str = "ytweb"):
    return dbq(cname("db"), user, pwfile, sql, db)


@live
@pytest.mark.parametrize("sql,ok", [
    ("select count(*) from audit_log", True), ("select count(*) from videos", True),
    ("insert into audit_log(ts,actor,action,detail,prev_hash,hash) values (now(),'vi','probe','{}','0','PROBEHASH')", True),
    ("update audit_log set actor='x' where hash='PROBEHASH'", False), ("delete from audit_log where hash='PROBEHASH'", False), ("truncate audit_log", False),
    ("truncate videos", False), ("alter table audit_log disable trigger all", False), ("alter table audit_log add column z int", False), ("drop table audit_log", False),
    ("drop table videos", False), ("create table zz(a int)", False), ("create index zi on audit_log(id)", False), ("alter table audit_log owner to ytweb_app", False),
    ("grant all on audit_log to ytweb_app", None), ("grant all on audit_log to public", None), ("revoke all on audit_log from ytweb_owner", None),
    ("create trigger tg before insert on audit_log for each row execute function now()", False), ("comment on table audit_log is 'x'", False),
    ("drop schema public cascade", False), ("alter schema public rename to p2", False), ("create role vi_r", False), ("alter role ytweb_owner password 'x'", False),
    ("set role ytweb_owner", False), ("set session authorization postgres", False), ("create database vi_db", False), ("drop database ytweb", False),
    ("select pg_read_file('/etc/passwd')", False), ("select pg_ls_dir('/')", False), ("copy audit_log to program 'id'", False), ("copy audit_log to '/tmp/vi.csv'", False),
    ("create extension pg_trgm", False), ("select lo_import('/etc/passwd')", False), ("create function vi_f() returns int language sql as 'select 1'", False),
    ("select count(*) from pg_authid", False), ("select setting from pg_settings where name='hba_file'", True), ("show hba_file", False), ("alter system set fsync=off", False),
    ("update settings_kv set value='{}'::jsonb where false", True),
    ("select nextval('audit_log_id_seq')", True), ("delete from sessions where false", True),
])
def test_tc_vi_110_live_app_account_privilege_boundary(sql, ok):
    r = _live_psql("ytweb_app", "db_app_password", sql.replace("PROBEHASH", PROBE))
    if ok is None:
        return  # 소유자가 아니면 GRANT/REVOKE 는 경고만 내고 무효 -> 효과가 없음은 111(권한 행렬)에서 확인
    assert (r.returncode == 0) is ok, (sql, r.stdout, r.stderr)


@live
def test_tc_vi_111_live_audit_log_privilege_matrix_and_probe_row_unmodifiable():
    r = _live_psql("ytweb_owner", "db_owner_password",
                   "select string_agg(p,',' order by p) from unnest(array['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p "
                   "where has_table_privilege('ytweb_app','public.audit_log',p)")
    assert r.stdout.strip() == "INSERT,SELECT", r.stdout + r.stderr
    r = _live_psql("ytweb_owner", "db_owner_password", f"select count(*) from audit_log where hash='{PROBE}'")
    assert r.stdout.strip() == "1"
    r = _live_psql("ytweb_owner", "db_owner_password",
                   "select string_agg(table_name,',') from information_schema.role_table_grants where grantee='ytweb_app' and privilege_type in ('TRUNCATE','REFERENCES','TRIGGER') and table_schema='public'")
    assert (r.stdout.strip() or "") == "", r.stdout
    r = _live_psql("postgres", "db_superuser_password", "select string_agg(rolname,',') from pg_roles where rolsuper or rolcreaterole or rolreplication or rolbypassrls", "postgres")
    assert r.stdout.strip() == "postgres", r.stdout
    r = _live_psql("postgres", "db_superuser_password", "select string_agg(a.rolname||'->'||b.rolname,',') from pg_auth_members m join pg_roles a on a.oid=m.member join pg_roles b on b.oid=m.roleid where a.rolname like 'ytweb%'", "postgres")
    assert r.stdout.strip() == "", f"앱/소유자 계정이 다른 역할의 구성원임: {r.stdout}"


@live
def test_tc_vi_112_live_app_account_cannot_tamper_alembic_version():
    r = _live_psql("postgres", "db_superuser_password",
                   "select has_table_privilege('ytweb_app','public.alembic_version','UPDATE')::text||has_table_privilege('ytweb_app','public.alembic_version','DELETE')::text", "ytweb")
    assert r.stdout.strip() == "falsefalse", r.stdout


@live
def test_tc_vi_113_live_server_settings():
    r = _live_psql("postgres", "db_superuser_password",
                   "select current_setting('password_encryption')||'|'||current_setting('data_checksums')||'|'||current_setting('timezone')||'|'||current_setting('max_connections')||'|'||current_setting('log_statement')||'|'||current_setting('ssl')||'|'||current_setting('hba_file')||'|'||current_setting('server_version_num')::int/10000", "postgres")
    assert r.stdout.strip() == "scram-sha-256|on|UTC|50|none|off|/etc/postgresql/pg_hba.conf|17", r.stdout
    r = _live_psql("postgres", "db_superuser_password", "select count(*) from pg_hba_file_rules where error is not null", "postgres")
    assert r.stdout.strip() == "0"
    r = _live_psql("postgres", "db_superuser_password", "select count(*) from pg_hba_file_rules where auth_method not in ('scram-sha-256','reject')", "postgres")
    assert r.stdout.strip() == "0"
    r = _live_psql("postgres", "db_superuser_password", "select string_agg(rolname||':'||coalesce(array_to_string(rolconfig,';'),''),',' order by rolname) from pg_roles where rolname like 'ytweb%'", "postgres")
    assert r.stdout.strip() == "ytweb_app:TimeZone=UTC,ytweb_owner:TimeZone=UTC", r.stdout


def _http_live(path, method, host, headers, data):
    args = ["curl", "-s", "-m", "10", "-i", "-X", method, f"http://127.0.0.1:{PORT}{path}", "-H", f"Host: {host}"]
    for k, v in (headers or {}).items():
        args += ["-H", f"{k}: {v}"]
    if data is not None:
        args += ["--data-binary", "@-"]
    r = subprocess.run(args, capture_output=True, input=data, timeout=30)
    raw = r.stdout.decode("latin-1")
    if not raw:
        return 0, {}, ""
    head, _, body = raw.partition("\r\n\r\n")
    lines = head.split("\r\n")
    hd: dict[str, list[str]] = {}
    for l in lines[1:]:
        k, _, v = l.partition(":")
        hd.setdefault(k.strip().lower(), []).append(v.strip())
    return int(lines[0].split()[1]), hd, body


@live
def test_tc_vi_120_live_end_to_end_through_nginx():
    st, h, b = _http_live("/api/healthz", "GET", "127.0.0.1:8080", None, None)
    assert st == 200 and json.loads(b) == {"status": "ok"}
    st, h, b = _http_live("/api/readyz", "GET", "localhost:8080", None, None)
    assert st == 200 and json.loads(b) == {"status": "ok", "db": "ok", "mode": "demo"}
    assert _http_live("/api/healthz", "GET", "evil:8080", None, None)[0] == 0
    st, h, b = _http_live("/", "GET", "127.0.0.1:8080", None, None)
    assert st == 200 and "<div id=\"root\"" in b
    for k in SEC_HEADERS:
        assert len(h[k]) == 1
    st, h, b = _http_live("/api/docs", "GET", "127.0.0.1:8080", None, None)
    assert st == 404
    st, h, b = _http_live("/api/openapi.json", "GET", "127.0.0.1:8080", None, None)
    assert st == 404
    st, h, b = _http_live("/api/v1/auth/session", "POST", "127.0.0.1:8080", {"Origin": "http://evil.example", "Content-Type": "application/json"}, b"{}")
    assert st == 403 and "origin_not_allowed" in b


@live
def test_tc_vi_121_live_survives_api_recreate_via_dynamic_dns():
    d0 = inspect("api")["Id"]
    r = sh(["docker", "compose", "-p", PROJECT, "-f", str(RUN / "web" / "compose.yaml"), "up", "-d", "--force-recreate", "--no-deps", "api"],
           env={"YTWEB_IMAGE_PREFIX": PROJECT}, timeout=240)
    assert r.returncode == 0, r.stderr
    assert inspect("api")["Id"] != d0
    for _ in range(60):
        if inspect("api")["State"].get("Health", {}).get("Status") == "healthy":
            break
        time.sleep(2)
    st, _, b = _http_live("/api/healthz", "GET", "localhost:8080", None, None)
    assert st == 200, st


@live
def test_tc_vi_123_migrate_failure_is_fail_closed_and_does_not_leak_password():
    alt = RUN.parent / "run3" / "web"
    (alt / "secrets").mkdir(parents=True, exist_ok=True)
    shutil.copy2(RUN / "web" / "compose.yaml", alt / "compose.yaml")
    for n in ("db_superuser_password", "db_owner_password", "db_app_password"):
        shutil.copy2(RUN / "web" / "secrets" / n, alt / "secrets" / n)
    (alt / "secrets" / "db_owner_password").write_text("f" * 64)  # 틀린 소유자 비밀번호
    env = {"YTWEB_IMAGE_PREFIX": PROJECT}
    base = ["docker", "compose", "-p", PROJECT]
    good = base + ["-f", str(RUN / "web" / "compose.yaml")]
    bad = base + ["-f", str(alt / "compose.yaml")]
    try:
        r = sh(bad + ["up", "-d", "--force-recreate", "--no-deps", "migrate"], env=env, timeout=120)
        time.sleep(8)
        mig = inspect("migrate")
        assert mig["State"]["ExitCode"] != 0, "틀린 비밀번호인데 마이그레이션이 성공"
        lg = docker("logs", cname("migrate"))
        assert "f" * 64 not in lg.stdout + lg.stderr and "password authentication failed" in lg.stderr
        r = sh(bad + ["up", "-d"], env=env, timeout=180)
        assert r.returncode != 0 and "didn't complete successfully" in r.stderr, r.stderr
        assert "f" * 64 not in r.stdout + r.stderr
    finally:
        sh(good + ["up", "-d", "--force-recreate", "--no-deps", "migrate"], env=env, timeout=120)
        sh(good + ["up", "-d"], env=env, timeout=240)
    assert inspect("migrate")["State"]["ExitCode"] == 0
    assert _http_live("/api/readyz", "GET", "127.0.0.1:8080", None, None)[0] == 200


@live
def test_tc_vi_122_live_graceful_stop_exit_codes_and_restart_policy():
    for s in ("worker", "api", "web"):
        r = sh(["docker", "stop", "-t", "30", cname(s)], timeout=60)
        assert r.returncode == 0
        d = inspect(s)
        if s == "api":  # 관찰 O-VI-02: uvicorn 0.54 는 우아한 종료 후 SIGTERM 을 다시 던져 종료 코드가 143 이다(노트의 "exit 0" 주장과 다름)
            assert d["State"]["ExitCode"] in (0, 143) and "Finished server process" in docker("logs", cname(s)).stderr[-2000:]
        else:
            assert d["State"]["ExitCode"] == 0, (s, d["State"])
        assert not d["State"]["OOMKilled"], (s, d["State"])
    sh(["docker", "start", cname("api"), cname("worker"), cname("web")], timeout=60)
    for _ in range(60):
        if all(inspect(s)["State"].get("Health", {}).get("Status") == "healthy" for s in ("api", "worker", "web")):
            break
        time.sleep(2)
    assert _http_live("/api/readyz", "GET", "127.0.0.1:8080", None, None)[0] == 200
    for s in ("db", "api", "worker", "web"):
        assert inspect(s)["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
    assert inspect("migrate")["HostConfig"]["RestartPolicy"]["Name"] == "no"


# ---------------------------------------------------------------- 스크립트(pwsh) 실측
def ps(script: str, *args: str, timeout: int = 600, subdir: str = "scripts_p") -> subprocess.CompletedProcess:
    assert PWSH and RUN
    home = RUN.parent / "home"
    home.mkdir(exist_ok=True)
    env = {"YTWEB_PROJECT": PROJECT, "YTWEB_IMAGE_PREFIX": PROJECT, "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1", "HOME": str(home)}
    trace = os.environ.get("VI_PS_TRACE")
    if trace:  # 줄 커버리지 측정용: Set-PSDebug -Trace 1 출력을 파일에 모은다(결과는 동일해야 한다)
        q = lambda a: a if re.fullmatch(r"-[A-Za-z]+", a) else "'" + a.replace("'", "''") + "'"  # 매개변수 이름은 따옴표 없이
        cmd = f"Set-PSDebug -Trace 1; & {q(str(RUN / 'web' / subdir / script))} " + " ".join(q(a) for a in args) + "; $ec = $LASTEXITCODE; if ($ec) { exit $ec } elseif (-not $?) { exit 1 } else { exit 0 }"
        r = sh([PWSH, "-NoProfile", "-NonInteractive", "-Command", cmd], timeout=timeout, env=env)
        with open(trace, "a", encoding="utf-8") as f:
            f.write(f"##### {subdir}/{script} {args}\n{r.stdout}\n")
        plain = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout)
        clean = "\n".join(l for l in plain.splitlines() if not re.match(r"^DEBUG:", l) and l.strip())
        return subprocess.CompletedProcess(r.args, r.returncode, clean, r.stderr)
    return sh([PWSH, "-NoProfile", "-NonInteractive", "-File", str(RUN / "web" / subdir / script), *args], timeout=timeout, env=env)


needs_ps = pytest.mark.skipif(not (os.environ.get("VI_LIVE") == "1" and PWSH and RUN), reason="VI_LIVE=1, pwsh, VI_RUN 필요")


def count_rows() -> str:
    r = _live_psql("ytweb_owner", "db_owner_password", "select string_agg(key,',' order by key) from settings_kv")
    return r.stdout.strip()


@needs_ps
def test_tc_vi_130_status_script_clean_on_healthy_stack_and_flags_wrong_port():
    ok = ps("status.ps1", "-Detail")
    assert ok.returncode == 0 and "점검 결과: 문제 없음" in ok.stdout, ok.stdout
    assert "[위험]" not in ok.stdout and "루프백(127.0.0.1)뿐" in ok.stdout
    for s in ("capDrop=[ALL]", "readOnly=true", "privileged=false"):
        assert s in ok.stdout
    bad = ps("status.ps1", subdir="scripts")  # 원본 스크립트는 8080 을 기대하므로 18081 게시를 [위험] 으로 표시해야 한다
    assert bad.returncode == 1 and "[위험] web" in bad.stdout, bad.stdout


@needs_ps
def test_tc_vi_130b_logs_script_and_prefix_validation():
    r = ps("logs.ps1", "-Service", "db", "-Tail", "5")
    assert r.returncode == 0 and r.stdout.strip(), r.stdout
    r = ps("logs.ps1", "-Service", "api;id")
    assert r.returncode != 0
    for pw in ("db_superuser_password", "db_owner_password", "db_app_password"):
        v = (RUN / "web" / "secrets" / pw).read_text().strip()
        for svc_ in SERVICES:
            r = ps("logs.ps1", "-Service", svc_, "-Tail", "400")
            assert v not in r.stdout
    for bad in ("a/b", "x;y", "a b", "한글", ".."):
        r = ps("backup.ps1", "-Prefix", bad)
        assert r.returncode != 0, bad


@needs_ps
def test_tc_vi_131_backup_restore_roundtrip_with_guards():
    marker = "vi_roundtrip"
    assert _live_psql("ytweb_owner", "db_owner_password", f"insert into settings_kv values ('{marker}','{{}}',now()) on conflict do nothing").returncode == 0
    bdir = RUN / "web" / "backups"
    before = set(p.name for p in bdir.glob("*.dump")) if bdir.exists() else set()
    b = ps("backup.ps1")
    assert b.returncode == 0 and "백업 완료" in b.stdout, b.stdout
    new = sorted(set(p.name for p in bdir.glob("*.dump")) - before)
    assert len(new) == 1
    dump = bdir / new[0]
    sha = (bdir / (new[0] + ".sha256")).read_text().split()[0]
    import hashlib
    assert hashlib.sha256(dump.read_bytes()).hexdigest() == sha
    assert docker("exec", cname("db"), "ls", "/backups").stdout.strip() == "", "컨테이너 안 임시 백업이 남음"
    # 데이터 변경 후 오답 문구 -> 취소, 무변경
    assert _live_psql("ytweb_owner", "db_owner_password", "delete from settings_kv; insert into settings_kv values ('changed','{}',now())").returncode == 0
    for wrong in ("", "복원", "복원합니다 ", "복원 합니다", "yes", "복원합니다;ls"):
        r = ps("restore.ps1", "-File", new[0], "-ConfirmText", wrong)
        assert r.returncode in (1, 2), (wrong, r.returncode)
        assert count_rows() == "changed", wrong
    # -Latest 는 가장 최근 파일을 고른다(확인 문구가 틀리므로 취소됨)
    time.sleep(1.1)
    newest = bdir / "vi-newest.dump"
    newest.write_bytes(dump.read_bytes())
    r = ps("restore.ps1", "-Latest", "-ConfirmText", "no")
    assert r.returncode == 2 and "vi-newest.dump" in r.stdout and count_rows() == "changed", r.stdout
    newest.unlink()
    # 변조된 파일은 거부
    t = bdir / "vi-tamper.dump"
    t.write_bytes(dump.read_bytes() + b"X")
    (bdir / "vi-tamper.dump.sha256").write_text(f"{sha}  vi-tamper.dump\n")
    r = ps("restore.ps1", "-File", "vi-tamper.dump", "-ConfirmText", "복원합니다")
    assert r.returncode == 1 and "SHA-256" in r.stdout and count_rows() == "changed"
    # 나쁜 파일 이름
    for n in ("../x.dump", "x.sql", "a b.dump"):
        r = ps("restore.ps1", "-File", n, "-ConfirmText", "복원합니다")
        assert r.returncode == 1 and count_rows() == "changed", n
    # 쓰레기 덤프(해시 없음)는 단일 트랜잭션/사전검증으로 실패하고 데이터는 그대로, 서비스는 복구
    (bdir / "vi-garbage.dump").write_bytes(b"garbage")
    r = ps("restore.ps1", "-File", "vi-garbage.dump", "-ConfirmText", "복원합니다", "-SkipSafetyBackup")
    assert r.returncode == 1 and count_rows() == "changed"
    assert _http_live("/api/readyz", "GET", "127.0.0.1:8080", None, None)[0] == 200
    # 정상 복원: 사전 백업 생성 + 데이터 복원 + 감사 로그 권한 재회수
    assert _live_psql("postgres", "db_superuser_password", "grant update on audit_log to ytweb_app", "ytweb").returncode == 0
    r = ps("restore.ps1", "-File", new[0], "-ConfirmText", "복원합니다")
    assert r.returncode == 0 and "복원이 끝났습니다" in r.stdout, r.stdout
    assert marker in count_rows().split(",")
    assert "changed" not in count_rows()
    pre = [p for p in bdir.glob("pre-restore-*.dump")]
    assert pre, "복원 전 자동 백업 없음"
    r = _live_psql("ytweb_owner", "db_owner_password", "select has_table_privilege('ytweb_app','audit_log','UPDATE')::text||has_table_privilege('ytweb_app','audit_log','DELETE')::text")
    assert r.stdout.strip() == "falsefalse"
    assert docker("exec", cname("db"), "ls", "/backups").stdout.strip() == ""
    assert _http_live("/api/readyz", "GET", "127.0.0.1:8080", None, None)[0] == 200


@needs_ps
def test_tc_vi_132_reset_demo_confirmation_and_volume_protection():
    vols = lambda: sorted(docker("volume", "ls", "--filter", f"name={PROJECT}", "--format", "{{.Name}}").stdout.split())
    v0 = vols()
    assert len(v0) == 3
    for flags, wrong in (([], "x"), ([], "모든 데이터 삭제"), ([], ""), (["-DeleteVolumes"], "데모 초기화"), (["-DeleteVolumes"], "모든 데이터 삭제 "), (["-DeleteVolumes"], "모든데이터삭제"), (["-DeleteVolumes"], "")):
        r = ps("reset-demo.ps1", *flags, "-ConfirmText", wrong)
        if wrong == "":  # 빈 값은 대화형 입력으로 넘어가며, 비대화형에서는 실패(fail-closed)
            assert r.returncode != 0, (flags, r.stdout)
        else:
            assert r.returncode == 2 and "확인 문구가 맞지 않아" in r.stdout, (flags, wrong, r.returncode)
        assert vols() == v0
    assert "vi_roundtrip" in count_rows()
    r = ps("reset-demo.ps1", "-ConfirmText", "데모 초기화")
    assert r.returncode == 0 and "초기화 완료" in r.stdout, r.stdout
    assert count_rows() == ""
    pri = _live_psql("ytweb_owner", "db_owner_password", "select has_table_privilege('ytweb_app','audit_log','UPDATE')::text||has_table_privilege('ytweb_app','audit_log','INSERT')::text")
    assert pri.stdout.strip() == "falsetrue"
    assert any((RUN / "web" / "backups").glob("pre-reset-*.dump"))
    assert vols() == v0


def _wait_healthy(service: str, tries: int = 60) -> None:
    for _ in range(tries):
        if inspect(service)["State"].get("Health", {}).get("Status") == "healthy":
            return
        time.sleep(2)
    pytest.fail(f"{service} 가 healthy 가 되지 않음")


@needs_ps
def test_tc_vi_132b_status_and_start_flag_a_wildcard_published_port():
    alt = RUN.parent / "run4" / "web"
    (alt / "secrets").mkdir(parents=True, exist_ok=True)
    for n in ("db_superuser_password", "db_owner_password", "db_app_password"):
        shutil.copy2(RUN / "web" / "secrets" / n, alt / "secrets" / n)
    text = (RUN / "web" / "compose.yaml").read_text(encoding="utf-8")
    assert f'"127.0.0.1:{PORT}:8080"' in text
    (alt / "compose.yaml").write_text(text.replace(f'"127.0.0.1:{PORT}:8080"', f'"0.0.0.0:{PORT}:8080"'), encoding="utf-8")
    shutil.rmtree(alt / "scripts_p", ignore_errors=True)
    shutil.copytree(RUN / "web" / "scripts_p", alt / "scripts_p")
    env = {"YTWEB_PROJECT": PROJECT, "YTWEB_IMAGE_PREFIX": PROJECT, "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1", "HOME": str(RUN.parent / "home")}
    good = ["docker", "compose", "-p", PROJECT, "-f", str(RUN / "web" / "compose.yaml")]
    try:
        r = sh(["docker", "compose", "-p", PROJECT, "-f", str(alt / "compose.yaml"), "up", "-d", "--force-recreate", "--no-deps", "web"], env={"YTWEB_IMAGE_PREFIX": PROJECT}, timeout=120)
        assert r.returncode == 0, r.stderr
        assert inspect("web")["NetworkSettings"]["Ports"]["8080/tcp"][0]["HostIp"] == "0.0.0.0"
        _wait_healthy("web")
        st = sh([PWSH, "-NoProfile", "-NonInteractive", "-File", str(alt / "scripts_p" / "status.ps1")], env=env, timeout=120)
        assert st.returncode == 1 and "[위험] web" in st.stdout and "점검 결과: 문제 없음" not in st.stdout, st.stdout
        assert "[위험] docker compose port: 0.0.0.0" in st.stdout
    finally:
        sh(good + ["up", "-d", "--force-recreate", "--no-deps", "web"], env={"YTWEB_IMAGE_PREFIX": PROJECT}, timeout=120)
    _wait_healthy("web")
    ok = ps("status.ps1")
    assert ok.returncode == 0 and "점검 결과: 문제 없음" in ok.stdout, ok.stdout


@needs_ps
def test_tc_vi_133_stop_keeps_volumes_then_start_restores_service_and_secret_guard():
    vols = lambda: sorted(docker("volume", "ls", "--filter", f"name={PROJECT}", "--format", "{{.Name}}").stdout.split())
    v0 = vols()
    r = ps("stop.ps1")
    assert r.returncode == 0 and vols() == v0
    assert docker("ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}").stdout.strip() == ""
    guard = RUN.parent / "run2"
    r = sh([PWSH, "-NoProfile", "-File", str(guard / "web" / "scripts" / "start.ps1"), "-NoBuild"],
           env={"YTWEB_PROJECT": PROJECT, "YTWEB_IMAGE_PREFIX": PROJECT, "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1", "HOME": str(RUN.parent / "home")})
    assert r.returncode == 1 and "데이터베이스 볼륨은 이미 있습니다" in r.stdout
    assert not (guard / "web" / "secrets").exists(), "비밀 파일을 새로 만들어 버림"
    r = ps("start.ps1", "-NoBuild")
    assert r.returncode == 0 and "준비 완료" in r.stdout, r.stdout
    assert vols() == v0
    assert _http_live("/api/readyz", "GET", "127.0.0.1:8080", None, None)[0] == 200


@needs_ps
def test_tc_vi_134_zz_delete_volumes_only_with_exact_phrase_and_keeps_host_files():
    vols = lambda: sorted(docker("volume", "ls", "--filter", f"name={PROJECT}", "--format", "{{.Name}}").stdout.split())
    r = ps("reset-demo.ps1", "-DeleteVolumes", "-ConfirmText", "모든 데이터 삭제")
    assert r.returncode == 0, r.stdout
    assert vols() == []
    assert any((RUN / "web" / "backups").glob("pre-reset-*.dump"))
    assert all((RUN / "web" / "secrets" / n).exists() for n in ("db_superuser_password", "db_owner_password", "db_app_password"))
    assert docker("ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}").stdout.strip() == ""


@needs_ps
def test_tc_vi_136_pin_digests_compare_and_apply_on_a_copy():
    dst = RUN / "web" / "docker"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(DOCKER_DIR, dst)
    try:
        f = dst / "db.Dockerfile"
        good = re.search(r"sha256:[0-9a-f]{64}", f.read_text(encoding="utf-8"))[0]
        f.write_text(f.read_text(encoding="utf-8").replace(good, "sha256:" + "0" * 64), encoding="utf-8")
        envx = os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"
        os.environ.setdefault("SSL_CERT_FILE", envx)
        r = ps("pin-digests.ps1")
        if "조회" in r.stdout and "실패" in r.stdout:
            pytest.skip("레지스트리 조회 불가(네트워크/속도 제한): " + r.stdout[-200:])
        assert good in r.stdout and "0" * 64 in r.stdout, r.stdout  # 비교만: 차이 보고
        assert "0" * 64 in f.read_text(encoding="utf-8"), "-Apply 없이 파일이 바뀜"
        r = ps("pin-digests.ps1", "-Apply")
        assert good in f.read_text(encoding="utf-8") and "0" * 64 not in f.read_text(encoding="utf-8"), r.stdout
        assert not f.read_bytes().startswith(b"\xef\xbb\xbf") and b"\r\n" not in f.read_bytes()  # LF·BOM 없음 유지
    finally:
        shutil.rmtree(dst, ignore_errors=True)


@needs_ps
def test_tc_vi_135_zz_start_refuses_when_port_is_taken_by_another_program():
    import socket
    assert docker("ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}").stdout.strip() == "", "스택이 내려가 있어야 함"
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", int(PORT)))
    srv.listen(1)
    try:
        r = ps("start.ps1", "-NoBuild")
        assert r.returncode == 1 and f"포트 {PORT} 를 다른 프로그램이 이미 사용 중" in r.stdout, r.stdout
        assert docker("ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}").stdout.strip() == "", "컨테이너를 만들어 버림"
    finally:
        srv.close()


@needs_ps
def test_tc_vi_137_zz_first_run_generates_distinct_random_secrets_and_brings_stack_up():
    proj = PROJECT + "-s"
    base = RUN.parent / "run5" / "web"
    shutil.rmtree(base.parent, ignore_errors=True)
    base.mkdir(parents=True)
    shutil.copy2(RUN / "web" / "compose.yaml", base / "compose.yaml")
    shutil.copytree(RUN / "web" / "scripts_p", base / "scripts")
    env = {"YTWEB_PROJECT": proj, "YTWEB_IMAGE_PREFIX": PROJECT, "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1", "HOME": str(RUN.parent / "home")}
    assert docker("ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}").stdout.strip() == ""
    try:
        r = sh([PWSH, "-NoProfile", "-NonInteractive", "-File", str(base / "scripts" / "start.ps1"), "-NoBuild"], env=env, timeout=400)
        assert r.returncode == 0 and "준비 완료" in r.stdout, r.stdout[-1500:]
        vals = []
        for n in ("db_superuser_password", "db_owner_password", "db_app_password"):
            v = (base / "secrets" / n).read_text()
            assert re.fullmatch(r"[0-9a-f]{64}", v), n  # 256비트 무작위, 개행 없음
            vals.append(v)
            assert v not in r.stdout + r.stderr, "비밀 값이 화면에 출력됨"
        assert len(set(vals)) == 3
        assert not set(vals) & {(RUN / "web" / "secrets" / n).read_text() for n in ("db_superuser_password", "db_owner_password", "db_app_password")}
        assert "내용은 표시하지 않습니다" in r.stdout
        # 두 번째 실행은 기존 비밀을 덮어쓰지 않는다
        r2 = sh([PWSH, "-NoProfile", "-NonInteractive", "-File", str(base / "scripts" / "start.ps1"), "-NoBuild"], env=env, timeout=400)
        assert r2.returncode == 0 and "이미 있습니다" in r2.stdout
        assert [(base / "secrets" / n).read_text() for n in ("db_superuser_password", "db_owner_password", "db_app_password")] == vals
        ps_ = sh(["docker", "compose", "-p", proj, "-f", str(base / "compose.yaml"), "ps", "--format", "{{.Service}} {{.Health}} {{.State}}"], env={"YTWEB_IMAGE_PREFIX": PROJECT})
        assert "db healthy running" in ps_.stdout and "web healthy running" in ps_.stdout, ps_.stdout
    finally:
        sh(["docker", "compose", "-p", proj, "-f", str(base / "compose.yaml"), "down", "-v"], env={"YTWEB_IMAGE_PREFIX": PROJECT}, timeout=200)
