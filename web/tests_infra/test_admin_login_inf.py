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


def test_tc_adm_001_api_has_login_mode_and_no_credential_env(compose):
    """TC-ADM-001 (DEC-058) api 는 로그인 필수·60분 무활동만 켜고, 아이디·비밀번호는 환경 변수로 받지 않는다."""
    env = compose["services"]["api"]["environment"]
    assert env["YTWEB_ADMIN_LOGIN"] == "1" and env["YTWEB_SESSION_IDLE_MINUTES"] == "60"
    assert not [k for k in env if k.startswith("YTWEB_ADMIN_") and k != "YTWEB_ADMIN_LOGIN"]


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


def test_tc_adm_006_no_credentials_anywhere_in_compose_or_env_example():
    """TC-ADM-006 compose·.env.example 에 관리자 아이디·비밀번호 변수가 없다(DEC-058: 평문은 어디에도 두지 않는다)."""
    for f in (WEB / "compose.yaml", WEB / ".env.example"):
        text = f.read_text(encoding="utf-8")
        assert "YTWEB_ADMIN_ID" not in text and "YTWEB_ADMIN_PASSWORD" not in text, f.name


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


def test_tc_adm_009_start_never_asks_or_prints_credentials():
    """TC-ADM-009 start.ps1 은 아이디·비밀번호를 묻지도 읽지도 않는다."""
    t = (SCRIPTS / "start.ps1").read_text(encoding="utf-8")
    assert "Read-Host" not in t and "SecureString" not in t and "YTWEB_ADMIN_PASSWORD" not in t and ".env" not in t.split("Initialize-Secrets")[0]


def test_tc_adm_010_start_flow_order():
    s = _t(SCRIPTS / "start.ps1")
    i = [s.index(x) for x in ("Initialize-Secrets", "Test-PortInUse $YtwebPort", "'up', '-d'", "Wait-ForStack")]
    assert i == sorted(i)


def test_tc_adm_011_db_secret_names_unchanged():
    c = _t(SCRIPTS / "_common.ps1")
    names = re.search(r"\$YtwebSecretNames\s*=\s*@\(([^)]*)\)", c).group(1)
    assert "admin" not in names and names.count("'") == 6


def test_tc_adm_012_register_admin_exists_and_old_scripts_removed():
    """TC-ADM-012 register-admin(ps1/bat)이 있고 reset-admin·set-admin 은 없다. register 는 비밀번호를 다루지 않고 컨테이너 안 프로그램에 입력을 맡긴다."""
    for n in ("register-admin.ps1", "register-admin.bat"):
        assert (SCRIPTS / n).exists(), n
    for n in ("reset-admin.ps1", "reset-admin.bat", "set-admin.ps1", "set-admin.bat"):
        assert not (SCRIPTS / n).exists(), n
    t = (SCRIPTS / "register-admin.ps1").read_text(encoding="utf-8")
    assert "ytweb.admin_cli register" in t
    code = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith("#"))
    assert "Read-Host" not in code and "SecureString" not in code and "ConvertFrom-SecureString" not in code
    assert not re.search(r"exec\s+-T", code)  # 대화형(TTY)이어야 비밀번호가 숨김 입력된다


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


def test_tc_adm_019_readme_describes_register_admin():
    """TC-ADM-019 README 가 register-admin 한 번 실행·DB 해시 저장을 설명하고 .env 관리자 설정은 없다."""
    t = (WEB / "README.md").read_text(encoding="utf-8")
    assert "register-admin" in t and "YTWEB_ADMIN_PASSWORD" not in t


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
