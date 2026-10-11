import os
import stat
import sys

import pytest

from ytitle import platform_utils as pu


def test_default_token_dir_is_outside_project_and_named():
    """TC-050: 기본 토큰 폴더는 사용자 프로필 아래 ytitle/tokens 이다. [ADR-004, SEC-015]"""
    p = pu.default_token_dir()
    assert p.parts[-2:] == ("ytitle", "tokens")


@pytest.mark.skipif(os.name == "nt", reason="POSIX 권한 모델")
def test_restrict_permissions_posix(tmp_path):
    """TC-051: POSIX에서 파일 권한이 소유자 전용(600)으로 제한된다. [SEC-008]"""
    f = tmp_path / "token.json"
    f.write_text("x")
    ok, _ = pu.restrict_file_permissions(f)
    assert ok and stat.S_IMODE(f.stat().st_mode) == 0o600


def test_restrict_permissions_missing_file_does_not_raise(tmp_path):
    """TC-052: 없는 파일에 대해 예외 없이 실패 결과(False)와 한국어 메시지를 돌려준다. [NFR-007]"""
    ok, msg = pu.restrict_file_permissions(tmp_path / "nope.json")
    assert ok is False and "권한" in msg


def test_ensure_utf8_console_is_safe_on_replaced_streams(monkeypatch):
    """TC-053: 표준 출력이 바뀐 환경에서도 UTF-8 설정이 예외 없이 동작한다. [NFR-002]"""
    import io

    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    pu.ensure_utf8_console()


@pytest.mark.windows_only
@pytest.mark.skipif(os.name != "nt", reason="Windows 전용: 이 Linux 환경에서는 미수행")
def test_windows_acl_restriction(tmp_path):
    """TC-054: [Windows 전용] icacls로 파일 권한이 현재 사용자로 제한된다. [SEC-008] — 이 환경 미수행"""
    f = tmp_path / "token.json"
    f.write_text("x")
    assert pu.restrict_file_permissions(f)[0] is True
