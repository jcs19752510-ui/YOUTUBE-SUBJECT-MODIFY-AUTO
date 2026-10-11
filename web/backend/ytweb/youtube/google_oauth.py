"""구글 로그인(OAuth, 읽기 전용) 처리. M2 단위 1.

- 읽기 범위 하나(`youtube.readonly`)만 요청한다. 쓰기 범위는 M3에서 별도 토큰으로 다룬다.
- 보안: state(요청 위조 방지)와 PKCE(코드 가로채기 방지)를 쓴다. state 는 1회용이며 10분 뒤 만료된다.
- 토큰은 로그·오류 메시지에 쓰지 않고, 파일은 소유자만 읽도록(0600) 원자적으로 저장한다.
- 네트워크 호출은 주입 가능한 `http` 함수로만 하므로 시험에서는 가짜 구글로 대체한다. 새 의존성 없음(표준 라이브러리).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE_READ = "https://www.googleapis.com/auth/youtube.readonly"
SCOPE_WRITE = "https://www.googleapis.com/auth/youtube.force-ssl"  # 제목 수정(videos.update)에 필요. 읽기 토큰과 별도 파일로 보관(M3)
STATE_TTL_SECONDS = 600
MAX_PENDING = 20

HttpPost = Callable[[str, dict], dict]


class OAuthError(Exception):
    """사용자에게 보여 줄 수 있는 한국어 메시지를 가진 오류. 토큰·비밀은 담지 않는다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def load_client(path: Path) -> tuple[str, str]:
    """구글에서 받은 클라이언트 JSON(데스크톱 앱 유형은 'installed', 웹 유형은 'web')에서 ID·비밀을 읽는다."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise OAuthError("client_missing", "구글 클라이언트 파일(web/secrets/google_client.json)이 없습니다.") from None
    except (OSError, ValueError):
        raise OAuthError("client_invalid", "구글 클라이언트 파일을 읽을 수 없습니다. 구글에서 다시 내려받아 주세요.") from None
    section = raw.get("installed") or raw.get("web")
    if not isinstance(section, dict) or not section.get("client_id") or not section.get("client_secret"):
        raise OAuthError("client_invalid", "구글 클라이언트 파일 형식이 올바르지 않습니다(client_id·client_secret 없음).")
    return str(section["client_id"]), str(section["client_secret"])


def make_pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return verifier, challenge


class PendingAuth:
    """로그인 진행 중인 요청(state → PKCE verifier)을 메모리에 잠깐 보관한다. 1회용, 10분 만료, 최대 20개."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._items: dict[str, tuple[str, float]] = {}

    def start(self) -> tuple[str, str]:
        now = self._clock()
        self._items = {s: v for s, v in self._items.items() if now - v[1] < STATE_TTL_SECONDS}
        while len(self._items) >= MAX_PENDING:
            self._items.pop(next(iter(self._items)))
        state = secrets.token_urlsafe(32)
        verifier, challenge = make_pkce()
        self._items[state] = (verifier, now)
        return state, challenge

    def finish(self, state: str | None) -> str:
        """state 를 소진하고 PKCE verifier 를 돌려준다. 없거나 만료됐거나 이미 쓴 state 면 거부한다."""
        item = self._items.pop(state or "", None)
        if item is None or self._clock() - item[1] >= STATE_TTL_SECONDS:
            raise OAuthError("state_invalid", "로그인 요청이 만료됐거나 올바르지 않습니다. 처음부터 다시 시도해 주세요.")
        return item[0]


def build_auth_url(client_id: str, redirect_uri: str, state: str, challenge: str, scope: str = SCOPE_READ) -> str:
    q = {
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": scope,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent",
    }
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def default_http_post(url: str, form: dict) -> dict:
    if not url.startswith("https://"):
        raise OAuthError("insecure_url", "보안 연결(https)이 아닌 주소로는 요청하지 않습니다.")
    data = urllib.parse.urlencode(form).encode("ascii")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 (https 만 허용, 위에서 검사)
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        return {"error": str(body.get("error", f"http_{e.code}"))}
    except Exception:  # noqa: BLE001  (네트워크 오류 — 상세는 숨긴다)
        raise OAuthError("network", "구글에 연결하지 못했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.") from None


def _tokens_from(resp: dict, now: datetime, *, keep_refresh: str | None = None) -> dict:
    if "error" in resp or not resp.get("access_token"):
        code = str(resp.get("error", "no_token"))
        msg = "구글 로그인이 만료됐습니다. 다시 로그인해 주세요." if code == "invalid_grant" else "구글이 로그인 요청을 거부했습니다. 다시 시도해 주세요."
        raise OAuthError("grant_" + code, msg)
    refresh = resp.get("refresh_token") or keep_refresh
    if not refresh:
        raise OAuthError("no_refresh", "구글이 장기 로그인 정보를 주지 않았습니다. 다시 로그인하면서 권한을 허용해 주세요.")
    exp = now + timedelta(seconds=int(resp.get("expires_in", 3600)))
    return {"access_token": resp["access_token"], "refresh_token": refresh, "expires_at": exp.isoformat(), "scope": resp.get("scope", SCOPE_READ)}


def exchange_code(http: HttpPost, client: tuple[str, str], code: str, verifier: str, redirect_uri: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    resp = http(TOKEN_URL, {"client_id": client[0], "client_secret": client[1], "code": code, "code_verifier": verifier,
                            "grant_type": "authorization_code", "redirect_uri": redirect_uri})
    return _tokens_from(resp, now)


def refresh_tokens(http: HttpPost, client: tuple[str, str], tokens: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    resp = http(TOKEN_URL, {"client_id": client[0], "client_secret": client[1], "refresh_token": tokens["refresh_token"], "grant_type": "refresh_token"})
    return _tokens_from(resp, now, keep_refresh=tokens["refresh_token"])


class TokenStore:
    """토큰 파일. 소유자만 읽고 쓰며(0600), 임시 파일에 쓴 뒤 교체해 중간에 끊겨도 깨지지 않는다."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def save(self, tokens: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tokens, f)
        os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:  # Windows 등 일부 환경은 권한 비트를 지원하지 않는다
            pass

    def load(self) -> dict | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            return None
        return data if isinstance(data, dict) and data.get("refresh_token") else None

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    @staticmethod
    def is_fresh(tokens: dict, now: datetime | None = None, margin_seconds: int = 60) -> bool:
        now = now or datetime.now(timezone.utc)
        try:
            return datetime.fromisoformat(tokens["expires_at"]) - timedelta(seconds=margin_seconds) > now
        except (KeyError, ValueError):
            return False
