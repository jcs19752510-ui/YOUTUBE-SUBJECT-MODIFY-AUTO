"""게이트웨이 선택(M3 단위 2). 아래 3가지가 **모두** 맞을 때만 실제 유튜브에 쓰고, 하나라도 아니면 모의 게이트웨이를 쓴다.
 1. 환경변수 YTWEB_LIVE_WRITE=1 (기본 꺼짐)  2. 쓰기 토큰 연결됨(secrets/google_write_token.json)  3. YTWEB_LIVE_ALLOWED_VIDEOS 에 영상 ID가 1개 이상
실제 수정은 허용 영상 ID만 가능하다(live_write 가 재검사). 반영이 확인되면 DB 의 videos 행도 같은 값으로 맞춘다.
"""
from __future__ import annotations

import copy
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from ytweb.db.models import Video
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.base import YouTubeGateway, make_excerpt
from ytweb.youtube.live_read import GoogleAccess
from ytweb.youtube.live_write import LiveYouTubeGateway
from ytweb.youtube.mock import MockYouTubeGateway

WRITE_TOKEN_FILE = "google_write_token.json"


def secrets_dir_from_env() -> Path:
    return Path(os.environ.get("YTWEB_SECRETS_DIR", "/var/lib/ytweb/secrets"))


def allowed_videos(env: dict[str, str] | None = None) -> frozenset[str]:
    raw = (env if env is not None else os.environ).get("YTWEB_LIVE_ALLOWED_VIDEOS", "")
    return frozenset(v.strip() for v in raw.split(",") if v.strip())


def live_write_enabled(env: dict[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get("YTWEB_LIVE_WRITE", "0") == "1"


def write_access(secrets_dir: Path, env: dict[str, str] | None = None) -> GoogleAccess:
    client = Path((env if env is not None else os.environ).get("YTWEB_GOOGLE_CLIENT_FILE", "/run/secrets/google_client"))
    return GoogleAccess(client, oauth.TokenStore(secrets_dir / WRITE_TOKEN_FILE))


def live_write_ready(secrets_dir: Path, env: dict[str, str] | None = None) -> bool:
    return live_write_enabled(env) and bool(allowed_videos(env)) and write_access(secrets_dir, env).connected()


class SyncedLiveGateway:
    """실제 유튜브에 쓰고, 반영이 확인되면 videos 행(제목·snippet)을 같은 값으로 맞춘다."""

    def __init__(self, session: Session, live: LiveYouTubeGateway, now: datetime) -> None:
        self._session, self._live, self._now = session, live, now

    def read_snippet(self, video_id: str) -> dict | None:
        return self._live.read_snippet(video_id)

    def update_snippet(self, video_id: str, body: dict) -> dict:
        out = self._live.update_snippet(video_id, body)  # 오류(definite 구분 포함)는 그대로 전달
        video = self._session.get(Video, video_id)
        if video is not None:
            video.snippet, video.title = copy.deepcopy(out), out["title"]
            video.category_id = out.get("categoryId", video.category_id)
            video.description_excerpt = make_excerpt(out.get("description"))
            video.fetched_at = self._now
            self._session.flush()
        return out


def select_gateway(session: Session, now: datetime, secrets_dir: Path | None = None, env: dict[str, str] | None = None) -> YouTubeGateway:
    sd = secrets_dir or secrets_dir_from_env()
    if live_write_ready(sd, env):
        return SyncedLiveGateway(session, LiveYouTubeGateway(write_access(sd, env), allowed_videos(env)), now)
    return MockYouTubeGateway(session, clock=lambda: now)


# ───────────── 실제 모드 안전장치(M3 단위 4) ─────────────

LIVE_CONFIRM_PREFIX = "실제 실행"


def live_mode(secrets_dir: Path, env: dict[str, str] | None = None) -> bool:
    """실제 수정이 가능한 상태(3조건)인지. 이 상태에서만 아래 추가 안전장치가 적용된다."""
    return live_write_ready(secrets_dir, env)


def is_live(gateway: object) -> bool:
    return isinstance(gateway, SyncedLiveGateway)


def confirm_text(n: int, live: bool) -> str:
    """배치 실행 확인 문구. 실제 모드는 데모와 문구가 달라 헷갈려서 실제로 바꾸는 사고를 막는다."""
    return f"{LIVE_CONFIRM_PREFIX} {n}건" if live else f"실행 {n}건"


def not_allowed_reason(video_id: str, secrets_dir: Path, env: dict[str, str] | None = None) -> str | None:
    """실제 모드에서 허용 목록에 없는 영상이면 사유(한국어), 아니면 None."""
    if live_mode(secrets_dir, env) and video_id not in allowed_videos(env):
        return "실제 수정 허용 영상이 아닙니다. 서버 설정 YTWEB_LIVE_ALLOWED_VIDEOS 에 영상 ID를 추가하기 전에는 실제로 바꾸지 않습니다."
    return None
