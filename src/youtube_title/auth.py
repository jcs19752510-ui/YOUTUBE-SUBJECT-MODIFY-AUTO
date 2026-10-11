"""OAuth 설치형 앱 인증(FR-016, ADR-004, SEC-008, SEC-015).

읽기 토큰과 쓰기 토큰을 분리해 저장한다. 쓰기 토큰은 `load_credentials("write", ...)`를 호출하는
쓰기 실행 모듈(live_guard)만 읽고, 그 밖의 코드는 읽기 토큰만 쓴다.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterable

from youtube_title.config import Settings
from youtube_title.errors import AuthError
from youtube_title.platform_utils import restrict_file_permissions

# 최소 권한 원칙. 쓰기 범위는 videos.update에 충분한 가장 좁은 것으로 12단계 전에 확정해야 한다 [확인 필요, DEC-016].
READ_SCOPES = (
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
)
WRITE_SCOPES = ("https://www.googleapis.com/auth/youtube.force-ssl",)
_SCOPES = {"read": READ_SCOPES, "write": WRITE_SCOPES}
_FILES = {"read": "read_token.json", "write": "write_token.json"}

RELOGIN_HINT = "`python -m youtube_title auth --read`로 다시 로그인하세요. (테스트 상태의 앱은 약 7일마다 다시 로그인해야 할 수 있습니다)"


def token_path(settings: Settings, kind: str) -> Path:
    return settings.token_dir / _FILES[kind]


def new_flow(settings: Settings, scopes: Iterable[str]):
    """설치형 앱 로그인 흐름. 테스트에서는 이 함수를 교체한다."""
    if not settings.client_secret_path.exists():
        raise AuthError(
            "구글 클라이언트 비밀 파일을 찾을 수 없습니다.",
            f"docs/yt/03_manual_setup.md 5장대로 받은 파일을 `{settings.client_secret_path}` 위치에 저장하세요.",
        )
    from google_auth_oauthlib.flow import InstalledAppFlow

    return InstalledAppFlow.from_client_secrets_file(str(settings.client_secret_path), scopes=list(scopes))


def _save(path: Path, creds) -> bool:
    """토큰을 임시 파일에 쓴 뒤 교체하고 권한을 제한한다. 권한 제한 성공 여부를 돌려준다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(creds.to_json(), encoding="utf-8")
    ok, _ = restrict_file_permissions(tmp)
    os.replace(tmp, path)
    return ok


def login(kind: str, settings: Settings, *, flow_factory: Callable = None, open_browser: bool = True) -> tuple[Path, bool]:
    """브라우저 로그인 후 토큰을 저장한다. (토큰 경로, 권한 제한 성공 여부)를 돌려준다."""
    flow = (flow_factory or new_flow)(settings, _SCOPES[kind])
    try:
        creds = flow.run_local_server(
            port=0,
            open_browser=open_browser,
            authorization_prompt_message="브라우저에서 채널 소유 계정으로 로그인하세요. 열리지 않으면 이 주소를 복사해 열어도 됩니다: {url}",
            success_message="로그인이 끝났습니다. 이 창을 닫고 PowerShell로 돌아가세요.",
        )
    except AuthError:
        raise
    except Exception as exc:  # 사용자가 창을 닫음, 네트워크 오류 등. 원인 이름만 남기고 내용(토큰 가능성)은 숨긴다
        raise AuthError("로그인을 끝내지 못했습니다.", RELOGIN_HINT, cause=type(exc).__name__) from exc
    granted = set(getattr(creds, "scopes", None) or [])
    missing = set(_SCOPES[kind]) - granted
    if missing:
        raise AuthError("필요한 권한이 모두 허용되지 않았습니다.", "로그인 화면에서 요청된 권한을 모두 허용한 뒤 다시 실행하세요.")
    path = token_path(settings, kind)
    return path, _save(path, creds)


def load_credentials(kind: str, settings: Settings, *, refresh: Callable = None):
    """저장된 토큰을 읽고, 만료됐으면 갱신한다. 해당 종류의 파일만 읽는다(SEC-015)."""
    path = token_path(settings, kind)
    if not path.exists():
        flag = "--read" if kind == "read" else "--write"
        raise AuthError("로그인 정보가 없습니다.", f"먼저 `python -m youtube_title auth {flag}`를 실행하세요.")
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        from google.oauth2.credentials import Credentials

        creds = Credentials.from_authorized_user_info(info)
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        raise AuthError("로그인 파일이 손상되었습니다.", "`python -m youtube_title auth --revoke`로 지운 뒤 다시 로그인하세요.", cause=type(exc).__name__) from exc
    if not set(_SCOPES[kind]) <= set(info.get("scopes") or []):
        raise AuthError("저장된 로그인에 필요한 권한이 없습니다.", f"`python -m youtube_title auth --{kind}`로 다시 로그인하세요.")
    if creds.valid:
        return creds
    if not creds.refresh_token:
        raise AuthError("로그인이 만료되었습니다.", RELOGIN_HINT)
    try:
        if refresh is not None:
            refresh(creds)
        else:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
    except Exception as exc:
        raise AuthError("로그인이 만료되었거나 취소되었습니다.", RELOGIN_HINT, cause=type(exc).__name__) from exc
    _save(path, creds)
    return creds


def revoke(settings: Settings) -> list[Path]:
    """로컬 토큰 파일을 모두 지운다(계정 회수 절차의 로컬 부분). 지운 경로 목록을 돌려준다."""
    removed = []
    for kind in _FILES:
        p = token_path(settings, kind)
        if p.exists():
            p.unlink()
            removed.append(p)
    return removed


def status(settings: Settings) -> list[dict]:
    """토큰 값은 읽지 않고 존재 여부만 알려 준다."""
    return [{"kind": kind, "path": token_path(settings, kind), "exists": token_path(settings, kind).exists()} for kind in _FILES]
