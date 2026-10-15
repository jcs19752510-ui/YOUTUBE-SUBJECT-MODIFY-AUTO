"""W-INF 정적 점검: compose·Dockerfile·nginx·DB 설정·스크립트. 도커 데몬이 필요 없다.

`docker compose config` 를 쓰는 TC 는 docker CLI 가 없으면 건너뛴다(결과서에 건너뜀으로 센다).
TC 번호는 TC-WI-001 부터 연속이며 이 파일 안에서 중복되지 않는다(마지막 TC 가 검사한다).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
COMPOSE = WEB / "compose.yaml"
ONLINE = WEB / "compose.online.yaml"
DOCKER = WEB / "docker"
SCRIPTS = WEB / "scripts"
SERVICES = ["db", "migrate", "api", "worker", "web"]
SENSITIVE_KEY = re.compile(r"(PASS|SECRET|TOKEN|KEY|CREDENTIAL)", re.I)


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def svc(compose) -> dict:
    return compose["services"]


def _env(service: dict) -> dict:
    env = service.get("environment", {})
    if isinstance(env, list):
        return dict(e.split("=", 1) for e in env)
    return {k: str(v) for k, v in env.items()}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _docker_config(*files: Path) -> dict:
    cmd = ["docker", "compose"]
    for f in files:
        cmd += ["-f", str(f)]
    cmd += ["config", "--format", "json"]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI 없음")


def test_tc_wi_001_only_web_publishes_a_port_on_loopback(svc):
    published = {n: s["ports"] for n, s in svc.items() if s.get("ports")}
    assert list(published) == ["web"]
    assert published["web"] == ["127.0.0.1:8080:8080"]


def test_tc_wi_002_internal_services_have_no_host_ports(svc):
    for name in ("db", "api", "worker", "migrate"):
        assert "ports" not in svc[name], name


def test_tc_wi_003_no_privileged_host_namespaces(svc):
    for name, s in svc.items():
        assert not s.get("privileged"), name
        assert s.get("network_mode") is None, name
        for key in ("pid", "ipc", "userns_mode", "cgroup", "uts"):
            assert s.get(key) != "host", (name, key)


def test_tc_wi_004_no_docker_socket_or_bind_mounts(compose, svc):
    named = set(compose["volumes"])
    for name, s in svc.items():
        for v in s.get("volumes", []):
            source = v.split(":")[0] if isinstance(v, str) else v.get("source", "")
            assert "docker.sock" not in str(v), name
            assert source in named, f"{name}: 바인드 마운트 금지 -> {v}"


def test_tc_wi_005_all_services_run_as_non_root(svc):
    for name, s in svc.items():
        user = str(s.get("user", ""))
        uid = user.split(":")[0]
        assert uid.isdigit() and int(uid) > 0, f"{name}: user={user!r}"


def test_tc_wi_006_read_only_root_filesystem(svc):
    for name, s in svc.items():
        assert s.get("read_only") is True, name


def test_tc_wi_007_all_capabilities_dropped(svc):
    for name, s in svc.items():
        assert [c.upper() for c in s.get("cap_drop", [])] == ["ALL"], name
        assert not s.get("cap_add"), name


def test_tc_wi_008_no_new_privileges(svc):
    for name, s in svc.items():
        assert "no-new-privileges:true" in s.get("security_opt", []), name


def test_tc_wi_009_no_plaintext_secrets_in_environment(compose, svc):
    for name, s in svc.items():
        for key, value in _env(s).items():
            if name == "api" and key == "YTWEB_ADMIN_PASSWORD":  # DEC-057 유일한 예외: 값은 web/.env 에서 오는 자리표시자만 허용(실제 값 금지)
                assert value == "${YTWEB_ADMIN_PASSWORD:-}"
                continue
            if SENSITIVE_KEY.search(key) and not key.endswith("_DIR"):
                assert key.endswith("_FILE"), f"{name}: {key} 는 *_FILE 이어야 함"
                assert value.startswith("/run/secrets/"), (name, key)
            assert not re.search(r"://[^/\s:@]+:[^/\s@]+@", value), f"{name}: URL 에 비밀번호 포함 {key}"
    for secret in compose["secrets"].values():
        assert set(secret) == {"file"} and secret["file"].startswith("./secrets/")


def test_tc_wi_010_db_only_on_internal_network(compose, svc):
    # DEF-VI-001 조치(DEC-045): front(web↔api)·back(api/worker/migrate↔db) 둘 다 internal, web 은 db 에 도달할 수 없다.
    assert set(svc["db"]["networks"]) == {"back"}
    assert compose["networks"]["front"]["internal"] is True and compose["networks"]["back"]["internal"] is True
    assert not compose["networks"].get("edge", {}).get("internal")
    for name in ("db", "api", "worker", "migrate"):
        assert "edge" not in svc[name]["networks"], name
    assert set(svc["web"]["networks"]) == {"front", "edge"}
    assert "back" not in svc["web"]["networks"], "web 이 db 망(back)에 붙어 있다"
    assert set(svc["api"]["networks"]) == {"front", "back"}
    assert set(svc["worker"]["networks"]) == {"back"} and set(svc["migrate"]["networks"]) == {"back"}
    assert "egress" not in compose["networks"]


def test_tc_wi_011_egress_only_for_api_and_worker_in_online_overlay():
    overlay = yaml.safe_load(ONLINE.read_text(encoding="utf-8"))
    attached = {n for n, s in overlay["services"].items() if "egress" in s.get("networks", {})}
    assert attached == {"api", "worker"}
    assert not overlay["networks"]["egress"].get("internal")


def test_tc_wi_012_data_lives_in_named_volumes(compose, svc):
    assert set(compose["volumes"]) == {"pgdata", "backups", "app_secrets"}
    assert "pgdata:/var/lib/postgresql/data" in svc["db"]["volumes"]
    assert "app_secrets:/var/lib/ytweb/secrets" in svc["api"]["volumes"]
    assert "app_secrets:/var/lib/ytweb/secrets" in svc["worker"]["volumes"]
    for s in compose["volumes"].values():
        assert not (s or {}).get("driver_opts"), "볼륨에 호스트 경로 바인딩 금지"


def test_tc_wi_013_resource_limits_everywhere(svc):
    for name, s in svc.items():
        limits = s["deploy"]["resources"]["limits"]
        assert {"cpus", "memory", "pids"} <= set(limits), name


def test_tc_wi_014_healthchecks_and_restart_policy(svc):
    for name, s in svc.items():
        if name == "migrate":
            assert s["healthcheck"] == {"disable": True}
            assert str(s["restart"]) == "no"
        else:
            assert s["healthcheck"]["test"], name
            assert s["restart"] == "unless-stopped", name


def test_tc_wi_015_log_rotation(svc):
    for name, s in svc.items():
        log = s["logging"]
        assert log["driver"] == "json-file", name
        assert log["options"]["max-size"] and log["options"]["max-file"], name


def test_tc_wi_016_startup_order(svc):
    assert svc["migrate"]["depends_on"]["db"]["condition"] == "service_healthy"
    for name in ("api", "worker"):
        assert svc[name]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert svc["web"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_tc_wi_017_timezone_and_db_runtime_settings(svc):
    for name, s in svc.items():
        assert _env(s)["TZ"] == "Asia/Seoul", name
    cmd = " ".join(svc["db"]["command"])
    for expected in ("timezone=UTC", "max_connections=", "password_encryption=scram-sha-256", "hba_file=/etc/postgresql/pg_hba.conf"):
        assert expected in cmd
    assert int(str(svc["db"]["stop_grace_period"]).rstrip("s")) >= 30


def test_tc_wi_018_db_password_from_file_and_utf8(svc):
    env = _env(svc["db"])
    assert env["POSTGRES_PASSWORD_FILE"] == "/run/secrets/db_superuser_password"
    assert "POSTGRES_PASSWORD" not in env
    assert "--encoding=UTF8" in env["POSTGRES_INITDB_ARGS"]
    assert set(svc["db"]["secrets"]) == {"db_superuser_password", "db_owner_password", "db_app_password"}
    assert svc["api"]["secrets"] == ["db_app_password"]  # 관리자 계정은 웹 화면에서 만들고 비밀 파일 없음
    assert svc["worker"]["secrets"] == ["db_app_password"]
    assert svc["migrate"]["secrets"] == ["db_owner_password"]


def test_tc_wi_019_service_commands_match_interface(svc):
    assert svc["api"]["command"][:4] == ["uvicorn", "ytweb.app:create_app", "--factory", "--host"]
    assert "--no-access-log" in svc["api"]["command"] and "8000" in svc["api"]["command"]
    assert svc["worker"]["command"] == ["python", "-m", "ytweb.worker"]
    assert svc["migrate"]["command"] == ["python", "-m", "ytweb.migrate"]
    env = _env(svc["api"])
    assert env["YTWEB_MODE"] == "demo" and env["YTWEB_ALLOWED_HOSTS"] == "127.0.0.1:8080,localhost:8080"
    assert env["YTWEB_DB_USER"] == "ytweb_app" and env["YTWEB_BASE_DIR"] == "/app"
    assert _env(svc["migrate"])["YTWEB_DB_OWNER_PASSWORD_FILE"] == "/run/secrets/db_owner_password"


def test_tc_wi_020_scripts_never_delete_volumes_by_default():
    pattern = re.compile(r"(down\s+(-v\b|--volumes)|'--volumes'|'-v')")
    for script in SCRIPTS.glob("*.ps1"):
        text = _read(script)
        if script.name == "reset-demo.ps1":
            continue
        assert not pattern.search(text), script.name
    reset = _read(SCRIPTS / "reset-demo.ps1")
    block = reset[reset.index("if ($DeleteVolumes) {\n    Write-Info"):]
    assert "'--volumes'" in block and block.index("'--volumes'") > 0
    assert "Read-ConfirmText" in reset[: reset.index("'--volumes'")]
    assert "모든 데이터 삭제" in reset


def test_tc_wi_021_dockerignore_required_entries():
    entries = {l.strip() for l in _read(ROOT / ".dockerignore").splitlines() if l.strip() and not l.startswith("#")}
    for required in (".git", ".env", ".env.*", "secrets/", "web/secrets/", "data/", "token*.json", ".harness-tmp/",
                     "**/node_modules/", "web/frontend/dist/", "config/settings.local.yaml", "web/backups/"):
        assert required in entries, required


@pytest.mark.parametrize("name", ["api", "web", "db"])
def test_tc_wi_022_dockerfiles_non_root_pinned_and_clean(name):
    text = _read(DOCKER / f"{name}.Dockerfile")
    users = re.findall(r"(?m)^USER\s+(\S+)", text)
    assert users and users[-1].split(":")[0] not in ("root", "0"), users
    args = re.findall(r"(?m)^ARG\s+\w+_IMAGE=(\S+)$", text)
    assert args, "베이스 이미지 ARG 없음"
    for ref in args:
        assert re.search(r"@sha256:[0-9a-f]{64}$", ref), f"다이제스트 고정 아님: {ref}"
        assert ":latest" not in ref
    assert re.search(r"(?m)^FROM \$\{\w+_IMAGE\}", text)
    assert not re.search(r"(?mi)^(ADD\s+https?://|.*curl[^\n]*\|\s*(ba)?sh)", text)
    assert not re.search(r"(?i)COPY[^\n]*(secrets|\.env|token)", text)
    if name in ("api", "web"):
        assert "HEALTHCHECK" in text
    if name == "web":
        assert "find dist -name '*.map'" in text and "--ignore-scripts" in text
    if name == "api":
        assert "--require-hashes" in text and text.count("AS ") == 2


def test_tc_wi_023_nginx_security_headers_in_every_location():
    conf = _read(DOCKER / "nginx" / "nginx.conf")
    headers = _read(DOCKER / "nginx" / "security-headers.conf")
    assert "default-src 'self'" in headers and "frame-ancestors 'none'" in headers
    for h in ("X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"):
        assert h in headers
    directives = [l for l in headers.splitlines() if l.startswith("add_header")]
    assert directives and all(l.endswith("always;") for l in directives)
    assert "server_tokens off;" in conf
    assert re.search(r"client_max_body_size\s+1m;", conf)
    assert "limit_req_zone" in conf and "limit_req_status 429;" in conf
    for block in re.findall(r"(?s)location [^{]+\{(.*?)\n        \}", conf):
        if "add_header" in block:
            assert re.search(r"include /etc/nginx/snippets/security-headers(-api)?\.conf;", block)
    assert conf.count("include /etc/nginx/snippets/security-headers.conf;") >= 6


def test_tc_wi_024_nginx_host_allowlist_and_routes():
    conf = _read(DOCKER / "nginx" / "nginx.conf")
    assert '"127.0.0.1:8080" 1;' in conf and '"localhost:8080" 1;' in conf and "return 444;" in conf
    assert "location = /nginx-health" in conf
    assert re.search(r"location = /api/healthz \{.*?proxy_pass \$api_upstream/healthz;", conf, re.S)
    assert re.search(r"location = /api/readyz \{.*?proxy_pass \$api_upstream/readyz;", conf, re.S)
    assert "pid /tmp/nginx.pid;" in conf and "listen 8080" in conf
    assert "limit_except GET HEAD" in conf


def test_tc_wi_025_pg_hba_scram_only_and_default_reject():
    rules = [l.split() for l in _read(DOCKER / "db" / "pg_hba.conf").splitlines() if l.strip() and not l.startswith("#")]
    methods = {r[-1] for r in rules}
    assert methods <= {"scram-sha-256", "reject"}
    assert rules[-1][-1] == "reject" and rules[-1][-2] == "all"
    for r in rules:
        if r[0] == "host" and r[-1] != "reject":
            assert r[3] in {"127.0.0.1/32", "::1/128", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"}, r


def test_tc_wi_026_role_init_script():
    sh = _read(DOCKER / "db" / "init" / "01-roles.sh")
    assert "set -Eeuo pipefail" in sh
    assert "/run/secrets" in sh and "db_owner_password" in sh and "db_app_password" in sh
    for role in ("CREATE ROLE ytweb_owner", "CREATE ROLE ytweb_app", "CREATE DATABASE ytweb"):
        assert role in sh
    assert sh.count("NOSUPERUSER") == 2
    assert not re.search(r"PASSWORD\s+'[^']+'", sh), "비밀번호 리터럴 금지"
    grants = _read(DOCKER / "db" / "schema-grants.sql")
    assert "REVOKE ALL ON SCHEMA public FROM PUBLIC" in grants
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE ytweb_owner" in grants
    assert "SELECT, INSERT, UPDATE, DELETE ON TABLES TO ytweb_app" in grants
    assert "USAGE, SELECT ON SEQUENCES TO ytweb_app" in grants
    assert "TRUNCATE" not in grants and "CREATE" not in grants.replace("REVOKE ALL ON SCHEMA public FROM PUBLIC", "").replace("CREATE SCHEMA", "")
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.audit_log FROM ytweb_app" in _read(DOCKER / "db" / "audit-guard.sql")


def test_tc_wi_027_powershell_scripts_have_bom_and_no_secret_output():
    scripts = sorted(SCRIPTS.glob("*.ps1"))
    assert {s.name for s in scripts} >= {"start.ps1", "stop.ps1", "status.ps1", "logs.ps1", "backup.ps1", "restore.ps1",
                                         "reset-demo.ps1", "pin-digests.ps1", "_common.ps1"}
    for s in scripts:
        assert s.read_bytes().startswith(b"\xef\xbb\xbf"), f"{s.name}: UTF-8 BOM 필요(PowerShell 5.1 한글)"
        for line in _read(s).splitlines():
            if re.match(r"\s*(Write-Host|Write-Ok|Write-Info|Write-Warn)\b", line):
                assert "New-RandomSecret" not in line and "Get-Content" not in line, (s.name, line)
    start = _read(SCRIPTS / "start.ps1")
    for needle in ("docker info" if False else "Test-DockerReady", "Initialize-Secrets", "Test-PortInUse", "--build", "Wait-ForStack"):
        assert needle in start


def test_tc_wi_028_shell_and_config_files_use_lf():
    for p in list((DOCKER / "db").rglob("*")) + list((DOCKER / "nginx").glob("*")) + list(DOCKER.glob("*.Dockerfile")):
        if p.is_file():
            assert b"\r\n" not in p.read_bytes(), p
    assert "*.sh text eol=lf" in (DOCKER / ".gitattributes").read_text()


def test_tc_wi_029_secret_paths_ignored_by_git_and_not_tracked():
    ignore = _read(ROOT / ".gitignore")
    assert "web/secrets/" in ignore and "web/backups/" in ignore
    if shutil.which("git"):
        tracked = subprocess.run(["git", "ls-files", "web/secrets", "web/backups"], cwd=ROOT, capture_output=True, text=True).stdout
        assert tracked.strip() == ""
    for p in [COMPOSE, ONLINE, *DOCKER.rglob("*")]:
        if p.is_file() and p.suffix in {".yaml", ".sh", ".conf", ".sql", ".Dockerfile", ""}:
            text = re.sub(r"sha256:[0-9a-f]{64}", "", p.read_text(encoding="utf-8", errors="ignore"))
            assert not re.search(r"\b[0-9a-f]{64}\b", text), f"비밀로 보이는 64자 16진수: {p}"


@needs_docker
def test_tc_wi_030_compose_config_resolves_and_publishes_loopback_only():
    cfg = _docker_config(COMPOSE)
    ports = [(n, p) for n, s in cfg["services"].items() for p in s.get("ports", [])]
    assert len(ports) == 1
    name, p = ports[0]
    assert name == "web" and p["host_ip"] == "127.0.0.1" and p["published"] == "8080" and p["target"] == 8080
    assert cfg["networks"]["front"]["internal"] is True and cfg["networks"]["back"]["internal"] is True


@needs_docker
def test_tc_wi_031_compose_online_overlay_keeps_db_off_egress():
    cfg = _docker_config(COMPOSE, ONLINE)
    nets = {n: set(s["networks"]) for n, s in cfg["services"].items()}
    assert nets["api"] == {"front", "back", "egress"} and nets["worker"] == {"back", "egress"}
    assert nets["db"] == {"back"} and nets["web"] == {"front", "edge"} and nets["migrate"] == {"back"}


@needs_docker
def test_tc_wi_032_compose_config_matches_hardening_after_resolution():
    cfg = _docker_config(COMPOSE)
    for name, s in cfg["services"].items():
        assert s["read_only"] is True and s["cap_drop"] == ["ALL"], name
        assert "no-new-privileges:true" in s["security_opt"], name
        assert not s.get("privileged"), name
        assert s["user"].split(":")[0].isdigit(), name


def test_tc_wi_033_powershell_scripts_parse():
    pwsh = shutil.which("pwsh") or next(iter(sorted((ROOT / ".harness-tmp" / "inf" / "pwsh").glob("pwsh"))), None)
    if not pwsh:
        pytest.skip("pwsh 없음(문법 검사 미수행)")
    code = ("$bad=0; Get-ChildItem '%s' -Filter *.ps1 | ForEach-Object { $e=$null;$t=$null;"
            "[void][System.Management.Automation.Language.Parser]::ParseFile($_.FullName,[ref]$t,[ref]$e);"
            "if($e.Count){$bad+=$e.Count; $_.Name; $e|ForEach-Object{$_.Message}} }; exit $bad" % SCRIPTS)
    out = subprocess.run([str(pwsh), "-NoProfile", "-Command", code], capture_output=True, text=True, timeout=120,
                         env={"DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1", "PATH": "/usr/bin:/bin"})
    assert out.returncode == 0, out.stdout + out.stderr


def test_tc_wi_034_tc_numbers_are_unique_and_contiguous():
    names = re.findall(r"(?m)^def test_tc_wi_(\d{3})_", Path(__file__).read_text(encoding="utf-8"))
    nums = [int(n) for n in names]
    assert nums == list(range(1, len(nums) + 1))
