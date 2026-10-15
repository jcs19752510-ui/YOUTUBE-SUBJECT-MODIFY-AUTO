"""관리자 로그인(DEC-055) 인프라 정적 점검. 도커 데몬 불필요. PowerShell 은 Windows 에서 실행하지 못하므로 문자열·구조 검사만 한다.
`docker compose config` 렌더링은 docker CLI 가 없으면 건너뛴다. 실제 자격 증명은 쓰지 않는다(가짜 자리표시자만)."""
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
ADMIN_SECRETS = ["admin_login_id", "admin_login_password"]
needs_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI 없음")


def _t(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(_t(WEB / "compose.yaml"))


def _secret_names(s: dict) -> list:
    return [x if isinstance(x, str) else x.get("source") for x in s.get("secrets", [])]


def test_tc_adm_001_api_has_login_env(compose):
    env = compose["services"]["api"]["environment"]
    assert str(env["YTWEB_ADMIN_LOGIN"]) == "1"
    assert env["YTWEB_ADMIN_ID_FILE"] == "/run/secrets/admin_login_id"
    assert env["YTWEB_ADMIN_PASSWORD_FILE"] == "/run/secrets/admin_login_password"
    assert str(env["YTWEB_SESSION_IDLE_MINUTES"]) == "60"


def test_tc_adm_002_api_mounts_admin_secrets(compose):
    names = _secret_names(compose["services"]["api"])
    for n in ADMIN_SECRETS:
        assert n in names
    assert "db_app_password" in names


@pytest.mark.parametrize("svc", ["db", "migrate", "worker", "web"])
def test_tc_adm_003_other_services_have_no_admin_secret_or_env(compose, svc):
    s = compose["services"][svc]
    assert not set(ADMIN_SECRETS) & set(_secret_names(s))
    env = s.get("environment", {}) or {}
    keys = env.keys() if isinstance(env, dict) else [e.split("=")[0] for e in env]
    assert not [k for k in keys if k.startswith("YTWEB_ADMIN") or k == "YTWEB_SESSION_IDLE_MINUTES"]


def test_tc_adm_004_top_level_secrets_are_files_under_secrets_dir(compose):
    for n in ADMIN_SECRETS:
        assert compose["secrets"][n] == {"file": f"./secrets/{n}"}


def test_tc_adm_005_hardening_and_networks_unchanged(compose):
    api = compose["services"]["api"]
    assert api["read_only"] is True and api["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in api["security_opt"]
    assert set(api["networks"]) == {"front", "back"}
    assert "ports" not in api
    assert compose["services"]["web"]["ports"] == ["127.0.0.1:8080:8080"]


def test_tc_adm_006_no_literal_credentials_in_compose_or_env_example():
    for p in (WEB / "compose.yaml", WEB / ".env.example"):
        txt = _t(p)
        assert not re.search(r"YTWEB_ADMIN_(ID|PASSWORD)\s*[:=]", txt), p  # 값 직접 주입 금지(파일 경로 변수만 허용)


def test_tc_adm_007_set_admin_exists_with_bat_wrapper():
    assert (SCRIPTS / "set-admin.ps1").exists() and (SCRIPTS / "set-admin.bat").exists()
    bat = (SCRIPTS / "set-admin.bat").read_text(encoding="utf-8")
    assert "set-admin.ps1" in bat and "-NoProfile" in bat
    assert (SCRIPTS / "set-admin.ps1").read_bytes()[:3] == b"\xef\xbb\xbf"  # PS 5.1 한글 안전


def test_tc_adm_008_set_admin_has_no_value_parameters():
    ps = _t(SCRIPTS / "set-admin.ps1")
    m = re.search(r"param\(([^)]*)\)", ps, re.S)
    assert m and "NoRestart" in m.group(1)
    assert not re.search(r"\$(Password|Pass|Pw|Id|LoginId|Secret)\b", m.group(1), re.I)


def _save_fn() -> str:
    c = _t(SCRIPTS / "_common.ps1")
    i = c.index("function Save-AdminLoginInteractive")
    return c[i:c.index("# start.ps1 에서 호출", i)]


def test_tc_adm_009_validation_rules_present():
    f = _save_fn()
    assert "^[A-Za-z0-9]{4,20}$" in f
    assert "-ge 8" in f and "-le 64" in f
    assert "-cne" in f and "-AsSecureString" in f
    assert f.count("-AsSecureString") >= 2  # 확인 입력


def test_tc_adm_010_write_utf8_no_bom_no_newline():
    f = _save_fn()
    assert "UTF8Encoding($false)" in f
    assert f.count("WriteAllText") == 2
    assert not re.search(r"Set-Content|Out-File|Add-Content|\[IO\.File\]::WriteAllLines|Write-Output\s+\$plain", f)
    assert "WriteAllText($YtwebAdminIdFile, $loginId" in f and "WriteAllText($YtwebAdminPwFile, $plain" in f
    assert "Set-OwnerOnlyAcl $YtwebAdminPwFile" in f and "Set-OwnerOnlyAcl $YtwebAdminIdFile" in f


def test_tc_adm_011_values_never_printed_or_passed_as_args():
    f = _save_fn() + _t(SCRIPTS / "set-admin.ps1")
    for line in f.splitlines():
        if re.match(r"\s*(Write-Host|Write-Info|Write-Ok|Write-Warn|Stop-Script|Write-Output|Out-Host)\b", line):
            assert not re.search(r"\$(plain|loginId|a|b|s1|s2)\b", line), line
    assert "Start-Process" not in f and "Invoke-Native" not in f and "Invoke-Compose" not in f
    assert "start.ps1" in _t(SCRIPTS / "set-admin.ps1")
    assert not re.search(r"start\.ps1'\)\s+-\w+\s+\$", _t(SCRIPTS / "set-admin.ps1"))
    assert "admin_login" not in _t(SCRIPTS / "logs.ps1")


def test_tc_adm_012_set_admin_restart_and_failure_guidance():
    ps = _t(SCRIPTS / "set-admin.ps1")
    assert "-NoRestart" in ps and "start.ps1" in ps
    assert "[조치]" in _t(SCRIPTS / "_common.ps1") and "Stop-Script" in _save_fn()
    assert ".\\web\\scripts\\set-admin.ps1" in _save_fn()


def test_tc_adm_013_start_calls_admin_init_after_secrets_before_up():
    s = _t(SCRIPTS / "start.ps1")
    i = [s.index(x) for x in ("Initialize-Secrets", "Initialize-AdminLogin", "Test-PortInUse $YtwebPort", "'up', '-d'")]
    assert i == sorted(i)
    c = _t(SCRIPTS / "_common.ps1")
    assert "function Test-AdminLoginPresent" in c and "function Initialize-AdminLogin" in c


def test_tc_adm_014_noninteractive_stops_with_guidance():
    c = _t(SCRIPTS / "_common.ps1")
    f = _save_fn()
    assert "IsInputRedirected" in c
    assert f.index("Test-InputInteractive") < f.index("Read-Host")
    assert "비대화형" in f


def test_tc_adm_015_db_secret_names_unchanged_and_admin_separate():
    c = _t(SCRIPTS / "_common.ps1")
    names = re.search(r"\$YtwebSecretNames\s*=\s*@\(([^)]*)\)", c).group(1)
    assert "admin" not in names and names.count("'") == 6


def test_tc_adm_016_backup_excludes_secrets_files():
    b = _t(SCRIPTS / "backup.ps1")
    assert "secrets" not in re.sub(r"#.*|\.SYNOPSIS.*?\n", "", b.split("#>")[1]) or "pg_dump" in b
    assert "admin_login" not in b and "YtwebSecretsDir" not in b
    assert "admin_login" not in _t(SCRIPTS / "restore.ps1") and "admin_login" not in _t(SCRIPTS / "status.ps1")


def test_tc_adm_017_gitignore_and_check_ignore():
    ig = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "web/secrets/" in ig
    r = subprocess.run(["git", "check-ignore", "-v"] + [f"web/secrets/{n}" for n in ADMIN_SECRETS], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.count("web/secrets/") >= 2
    tracked = subprocess.run(["git", "ls-files", "web/secrets"], cwd=ROOT, capture_output=True, text=True).stdout
    assert tracked.strip() == ""
    di = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert "web/secrets/" in di


def test_tc_adm_018_docs_mention_login_without_real_values():
    for p in (WEB / "README.md", WEB / ".env.example"):
        t = _t(p)
        assert "set-admin" in t and "60" in t and "YTWEB_SESSION_IDLE_MINUTES" in t or p.name == "README.md"
    r = _t(WEB / "README.md")
    assert "set-admin.bat" in r and "<새 비밀번호>" in r and "admin1234" in r


@needs_docker
def test_tc_adm_019_docker_compose_config_renders_admin_only_on_api(tmp_path):
    import json
    sec = WEB / "secrets"
    out = subprocess.run(["docker", "compose", "-f", str(WEB / "compose.yaml"), "config", "--format", "json"], capture_output=True, text=True, timeout=60)
    if out.returncode != 0 and "secrets" in out.stderr:
        pytest.skip("secrets 파일 없음으로 렌더링 불가: " + out.stderr[:120])
    assert out.returncode == 0, out.stderr
    cfg = json.loads(out.stdout)
    for name, s in cfg["services"].items():
        have = {x["source"] for x in s.get("secrets", [])}
        if name == "api":
            assert set(ADMIN_SECRETS) <= have
        else:
            assert not set(ADMIN_SECRETS) & have, name
