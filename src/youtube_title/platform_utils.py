"""OS별 동작을 한곳에 격리한다(NFR-001). Windows 고유 동작은 이 모듈에서만 다룬다."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def is_windows() -> bool:
    return os.name == "nt"


def default_token_dir() -> Path:
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "youtube-title" / "tokens"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "youtube-title" / "tokens"


def restrict_file_permissions(path: Path) -> tuple[bool, str]:
    """파일을 현재 사용자만 읽을 수 있게 시도한다. (성공 여부, 메시지)를 돌려준다."""
    try:
        if is_windows():
            user = os.environ.get("USERNAME", "")
            if not user:
                return False, "사용자 이름을 알 수 없어 권한을 제한하지 못했습니다."
            result = subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                capture_output=True, text=True, check=False,
            )
            return (result.returncode == 0, "권한 제한 완료" if result.returncode == 0 else "icacls 실행에 실패했습니다.")
        os.chmod(path, 0o600)
        return True, "권한 제한 완료"
    except OSError as exc:
        return False, f"권한을 제한하지 못했습니다({type(exc).__name__})."


def ensure_utf8_console() -> None:
    """콘솔 출력이 UTF-8이 되도록 시도한다(한글 깨짐 방지, NFR-002)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
