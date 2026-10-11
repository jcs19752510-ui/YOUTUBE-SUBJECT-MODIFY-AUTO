"""내 채널 영상 읽기(읽기 전용) — M2 단위 3. 영상 정보를 조회만 하고 수정 호출은 이 모듈에 없다.

호출 비용(쿼터): channels.list 1 + playlistItems.list 페이지당 1(50개) + videos.list 50개당 1. 영상 200개면 약 9단위.
네트워크는 주입 가능한 `http_get` 으로만 하므로 시험에서는 가짜 응답을 쓴다. 새 의존성 없음(표준 라이브러리, https 만).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.base import GatewayError, make_excerpt

API = "https://www.googleapis.com/youtube/v3"
MAX_PAGES = 40  # 50개 × 40쪽 = 영상 2,000개까지(채널이 더 커도 여기서 멈추고 알린다)
BATCH = 50

HttpGet = Callable[[str, str], dict]


def default_http_get(url: str, token: str) -> dict:
    if not url.startswith("https://"):
        raise GatewayError("insecure_url", "보안 연결(https)이 아닌 주소로는 요청하지 않습니다.")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (https 만 허용, 위에서 검사)
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        reason = ""
        try:
            reason = str(((json.loads(e.read().decode("utf-8")).get("error") or {}).get("errors") or [{}])[0].get("reason", ""))
        except Exception:  # noqa: BLE001
            pass
        if e.code == 401:
            raise GatewayError("unauthorized", "구글 로그인이 만료됐습니다. 구글 계정을 다시 연결해 주세요.") from None
        if e.code == 403 and reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise GatewayError("quota_exceeded", "오늘 구글 API 사용량 한도를 넘었습니다. 내일(태평양 시간 자정 이후) 다시 시도해 주세요.") from None
        if e.code == 403:
            raise GatewayError("forbidden", "구글이 접근을 거부했습니다. YouTube Data API 사용 설정과 테스트 사용자 등록을 확인해 주세요.") from None
        raise GatewayError(f"http_{e.code}", "구글(유튜브) 응답 오류입니다. 잠시 뒤 다시 시도해 주세요.") from None
    except Exception:  # noqa: BLE001  (네트워크 오류 — 상세는 숨긴다)
        raise GatewayError("network", "구글(유튜브)에 연결하지 못했습니다. 인터넷 연결을 확인하고 다시 시도해 주세요.") from None


class GoogleAccess:
    """저장된 로그인 정보로 접근 토큰을 준비한다(만료됐으면 갱신해 저장)."""

    def __init__(self, client_file: Path, store: oauth.TokenStore, http_post: oauth.HttpPost = oauth.default_http_post) -> None:
        self.client_file, self.store, self.http_post = Path(client_file), store, http_post

    def connected(self) -> bool:
        return self.client_file.is_file() and self.store.load() is not None

    def access_token(self, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        tokens = self.store.load()
        if tokens is None:
            raise GatewayError("not_connected", "구글 계정이 연결돼 있지 않습니다. 먼저 구글 계정을 연결해 주세요.")
        if self.store.is_fresh(tokens, now):
            return tokens["access_token"]
        try:
            tokens = oauth.refresh_tokens(self.http_post, oauth.load_client(self.client_file), tokens, now)
        except oauth.OAuthError as e:
            raise GatewayError("unauthorized", e.message) from None
        self.store.save(tokens)
        return tokens["access_token"]


_DUR = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(value: object) -> int | None:
    m = _DUR.match(value) if isinstance(value, str) else None
    if not m or value in ("P", "PT"):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _int(v: object) -> int | None:
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def to_video_fields(item: dict) -> dict | None:
    """videos.list 항목 하나 → videos 테이블 필드(is_short·exclusion_reasons 는 호출한 쪽이 정책으로 계산). 형식이 이상하면 None."""
    vid, sn = item.get("id"), item.get("snippet")
    if not isinstance(vid, str) or len(vid) != 11 or not isinstance(sn, dict) or not isinstance(sn.get("title"), str):
        return None
    status, details, stats = item.get("status") or {}, item.get("contentDetails") or {}, item.get("statistics") or {}
    return {
        "video_id": vid, "title": sn["title"], "category_id": sn.get("categoryId"), "privacy_status": status.get("privacyStatus"),
        "made_for_kids": status.get("madeForKids"), "live_broadcast_content": sn.get("liveBroadcastContent"),
        "duration_sec": parse_duration(details.get("duration")), "description_excerpt": make_excerpt(sn.get("description")),
        "snippet": sn, "views": _int(stats.get("viewCount")), "source": "youtube",
    }


class YouTubeReader:
    def __init__(self, token: Callable[[], str], http_get: HttpGet = default_http_get) -> None:
        self._token, self._get = token, http_get

    def _call(self, path: str, **params: str | int) -> dict:
        return self._get(f"{API}/{path}?" + urllib.parse.urlencode(params), self._token())

    def uploads_playlist(self) -> str:
        items = self._call("channels", part="contentDetails", mine="true").get("items") or []
        pid = ((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") if items else None
        if not pid:
            raise GatewayError("no_channel", "이 구글 계정에서 유튜브 채널을 찾지 못했습니다. 채널을 소유한 계정으로 연결했는지 확인해 주세요.")
        return pid

    def video_ids(self, playlist_id: str) -> Iterator[str]:
        token = ""
        for _ in range(MAX_PAGES):
            params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": BATCH}
            if token:
                params["pageToken"] = token
            data = self._call("playlistItems", **params)
            for it in data.get("items") or []:
                vid = (it.get("contentDetails") or {}).get("videoId")
                if isinstance(vid, str):
                    yield vid
            token = data.get("nextPageToken") or ""
            if not token:
                return

    def videos(self, ids: list[str]) -> list[dict]:
        out: list[dict] = []
        for i in range(0, len(ids), BATCH):
            chunk = ids[i:i + BATCH]
            data = self._call("videos", part="snippet,contentDetails,status,statistics", id=",".join(chunk), maxResults=BATCH)
            out.extend(it for it in (data.get("items") or []) if isinstance(it, dict))
        return out

    def fetch_all(self) -> list[dict]:
        """내 채널의 모든(최대 2,000개) 영상을 읽어 videos 필드 목록으로 돌려준다. 이상한 항목은 건너뛴다."""
        ids = list(dict.fromkeys(self.video_ids(self.uploads_playlist())))
        rows = (to_video_fields(it) for it in self.videos(ids))
        return [r for r in rows if r is not None]
