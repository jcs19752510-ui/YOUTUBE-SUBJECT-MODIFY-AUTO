"""관리자 로그인 인프라 정적 점검(DEC-057: web/.env 의 YTWEB_ADMIN_ID·YTWEB_ADMIN_PASSWORD 로 서버가 시작할 때 계정 준비). 도커 데몬 불필요.
PowerShell 은 Windows 에서 실행하지 못하므로 문자열·구조 검사만 한다(Windows 실행 미확인).
계약: 값은 api 에만 ${...:-} 로 전달, 웹 계정 생성 없음, reset-admin·set-admin 없음, api 비밀 파일은 db_app_password 하나. 실제 자격 증명은 쓰지 않는다."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parent
SCRIPTS = WEB / "scripts"
OLD_SECRETS = ["admin_login_id", "admin_login_password"]
needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI 없음")


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(_t(WEB / "compose.yaml"))


def _secret_names(s: dict) -> list:
    return [x if isinstance(x, str) else x.get("source") for x in s.get("secrets", [])]


def _env_keys(s: dict):
    env = s.get("environment", {}) or {}
    return list(env.keys()) if isinstance(env, dict) else [e.split("=")[0] for e in env]


def test_tc_adm_001_api_has_login_env_from_dotenv_and_no_file_env(compose):
    env = compose["services"]["api"]["environment"]
    assert str(env["YTWEB_ADMIN_LOGIN"]) == "1"
    assert str(env["YTWEB_SESSION_IDLE_MINUTES"]) == "60"
    assert env["YTWEB_ADMIN_ID"] == "${YTWEB_ADMIN_ID:-}"
    assert env["YTWEB_ADMIN_PASSWORD"] == "${YTWEB_ADMIN_PASSWORD:-}"
    assert not [k for k in env if k.endswith("_FILE") and "ADMIN" in k]


def test_tc_adm_002_api_only_db_app_password(compose):
    assert _secret_names(compose["services"]["api"]) == ["db_app_password"]
    assert _secret_names(compose["services"]["worker"]) == ["db_app_password"]


@pytest.mark.parametrize("svc", ["db", "migrate", "worker", "web", "api"])
def test_tc_adm_003_no_service_has_admin_secret_or_file_env(compose, svc):
    s = compose["services"][svc]
    assert not set(OLD_SECRETS) & set(_secret_names(s))
    if svc != "api":
        assert not [k for k in _env_keys(s) if k.startswith("YTWEB_ADMIN_")]
        assert "YTWEB_SESSION_IDLE_MINUTES" not in _env_keys(s)


def test_tc_adm_004_no_top_level_admin_secrets(compose):
    for n in OLD_SECRETS:
        assert n not in compose["secrets"]
    assert "admin_login" not in _t(WEB / "compose.yaml")


def test_tc_adm_005_hardening_and_networks_unchanged(compose):
    api = compose["services"]["api"]
    assert api["read_only"] is True and api["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in api["security_opt"]
    assert set(api["networks"]) == {"front", "back"}
    assert "ports" not in api
    assert compose["services"]["web"]["ports"] == ["127.0.0.1:8080:8080"]


def test_tc_adm_006_no_literal_credentials_in_compose_or_env_example():
    c = _t(WEB / "compose.yaml")
    assert not re.search(r"YTWEB_ADMIN_(ID|PASSWORD):\s*(?!\$\{YTWEB_ADMIN_(ID|PASSWORD):-\}\s*$)\S", c, re.M)
    for line in _t(WEB / ".env.example").splitlines():  # 예시 파일의 값 줄은 비어 있어야 한다(실제 값 없음)
        m = re.match(r"\s*YTWEB_ADMIN_(ID|PASSWORD)\s*=(.*)$", line)
        if m:
            assert m.group(2).strip() == "", line


def test_tc_adm_007_set_admin_removed():
    assert not (SCRIPTS / "set-admin.ps1").exists() and not (SCRIPTS / "set-admin.bat").exists()
    for p in SCRIPTS.iterdir():
        if p.suffix in (".ps1", ".bat"):
            assert not re.search(r"(?<!re)set-admin", _t(p)), p
    for n in ("README.md", ".env.example"):
        assert not re.search(r"(?<!re)set-admin", _t(WEB / n))


def test_tc_adm_008_start_and_common_have_no_admin_input_code():
    for n in ("start.ps1", "_common.ps1"):
        t = _t(SCRIPTS / n)
        assert not re.search(r"admin_login|AdminLogin|AdminId|AdminPw|Save-Admin|Initialize-Admin|reset-admin", t), n
        assert "AsSecureString" not in t and "SecureString" not in t, n
        for line in t.splitlines():
            if "Read-Host" in line:
                assert "관리자" not in line and "아이디" not in line and "비밀번호" not in line, line


def test_tc_adm_009_start_checks_env_without_printing_values_or_asking():
    s = _t(SCRIPTS / "start.ps1")
    assert "YTWEB_ADMIN_ID" in s and "YTWEB_ADMIN_PASSWORD" in s and "Write-Warn" in s and "start.ps1" in s
    assert "Read-Host" not in s and "Get-Credential" not in s and "SecureString" not in s
    assert "관리자 계정을 만드세요" not in s and "브라우저에서 로그인하세요" in s
    assert s.index("브라우저에서 로그인하세요") > s.index("준비 완료")
    # 값을 담는 변수 출력 금지: Write-* 줄에는 환경 파일에서 읽은 줄/값 변수가 없어야 한다
    for line in s.splitlines():
        if re.search(r"Write-(Host|Ok|Info|Warn|Output)", line):
            assert "$envLine" not in line and "$Matches" not in line, line
    # 설정이 없어도 중단하지 않는다(해당 블록에 exit/Stop-Script 없음)
    blk = s[s.index("$adminEnvFile"):s.index("Write-Info '3/5")]
    assert "exit" not in blk and "Stop-Script" not in blk and "Copy-Item" not in blk


def test_tc_adm_010_start_flow_order():
    s = _t(SCRIPTS / "start.ps1")
    i = [s.index(x) for x in ("Initialize-Secrets", "Test-PortInUse $YtwebPort", "'up', '-d'", "Wait-ForStack")]
    assert i == sorted(i)


def test_tc_adm_011_db_secret_names_unchanged():
    c = _t(SCRIPTS / "_common.ps1")
    names = re.search(r"\$YtwebSecretNames\s*=\s*@\(([^)]*)\)", c).group(1)
    assert "admin" not in names and names.count("'") == 6


def test_tc_adm_012_reset_admin_and_set_admin_files_removed():
    for n in ("reset-admin.ps1", "reset-admin.bat", "set-admin.ps1", "set-admin.bat"):
        assert not (SCRIPTS / n).exists(), n
    for p in list(SCRIPTS.iterdir()) + [WEB / "README.md", WEB / ".env.example", WEB / "compose.yaml"]:
        if p.is_file():
            assert "reset-admin" not in _t(p) and "admin_cli" not in _t(p), p


def test_tc_adm_018_gitignore_and_check_ignore():
    ig = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "web/secrets/" in ig
    r0 = subprocess.run(["git", "check-ignore", "-v", "web/.env"], cwd=ROOT, capture_output=True, text=True)
    assert r0.returncode == 0, r0.stdout + r0.stderr
    assert subprocess.run(["git", "ls-files", "web/.env"], cwd=ROOT, capture_output=True, text=True).stdout.strip() == ""
    r = subprocess.run(["git", "check-ignore", "-v", "web/secrets/db_app_password"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0
    assert subprocess.run(["git", "ls-files", "web/secrets"], cwd=ROOT, capture_output=True, text=True).stdout.strip() == ""
    assert "web/secrets/" in (ROOT / ".dockerignore").read_text(encoding="utf-8")


def test_tc_adm_019_docs_describe_dotenv_login():
    r, e = _t(WEB / "README.md"), _t(WEB / ".env.example")
    for k in ("YTWEB_ADMIN_ID=admin1234", "<8~64자 비밀번호>", "60분", "YTWEB_SESSION_IDLE_MINUTES", "start.ps1", "계정을 만들 수 없"):
        assert k in r, k
    assert "4~20자" in r and "8~64자" in r and "#" in r
    assert "YTWEB_ADMIN_ID=" in e and "YTWEB_ADMIN_PASSWORD=" in e and "60분" in e and "8~64자" in e
    for tx in (r, e):
        assert "admin_login_id" not in tx and "admin_login_password" not in tx and "관리자 계정 만들기" not in tx


def test_tc_adm_020_restore_and_reset_demo_need_no_admin_secret():
    for n in ("restore.ps1", "reset-demo.ps1", "start.ps1"):
        assert "admin_login" not in _t(SCRIPTS / n)
    assert "admin_login" not in _t(WEB / "compose.yaml") and "admin_login" not in _t(WEB / "compose.online.yaml")


@needs_docker
def test_tc_adm_021_docker_compose_config_renders_without_admin_secrets():
    import json
    out = subprocess.run(["docker", "compose", "-f", str(WEB / "compose.yaml"), "config", "--format", "json"], capture_output=True, text=True, timeout=60)
    if out.returncode != 0 and "secrets" in out.stderr:
        pytest.skip("secrets 파일 없음으로 렌더링 불가: " + out.stderr[:120])
    assert out.returncode == 0, out.stderr
    cfg = json.loads(out.stdout)
    for name, s in cfg["services"].items():
        have = {x["source"] for x in s.get("secrets", [])}
        assert not set(OLD_SECRETS) & have, name
    assert {x["source"] for x in cfg["services"]["api"]["secrets"]} == {"db_app_password"}
