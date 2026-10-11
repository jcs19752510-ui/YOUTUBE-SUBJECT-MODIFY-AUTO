"""실제 유튜브 제목 수정(쓰기) 게이트웨이 — M3 단위 1. `YouTubeGateway` 규약을 그대로 따른다.

안전장치(모두 통과해야 videos.update 가 나간다; 하나라도 어긋나면 네트워크 호출 전에 거부):
 1. 쓰기 전용 토큰(`youtube.force-ssl`, 읽기 토큰과 별도 파일)이 연결돼 있어야 한다.
 2. 허용 영상 목록(`allowed_video_ids`)에 있는 영상만 수정한다. 비어 있으면 아무것도 수정하지 않는다(처음엔 테스트 영상 1개).
 3. 본문은 도메인이 만든 snippet 통째 교체 본문만 받는다(제목 외 항목 보존은 호출한 쪽 책임, 여기서 형식만 재검사).
네트워크는 주입 가능한 `http_send` 로만 하므로 시험에서는 가짜 구글을 쓴다. 새 의존성 없음.
쓰기 호출 비용: videos.update 1회 = 50 쿼터 단위.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable, Collection

from ytweb.youtube.base import GatewayError
from ytweb.youtube import google_oauth as _oauth  # noqa: F401  (import 시 리다이렉트 비추종 opener 가 설치된다)
from ytweb.youtube.live_read import API, GoogleAccess, HttpGet, default_http_get

HttpSend = Callable[[str, str, dict], dict]  # (url, token, json body) -> json


def default_http_send(url: str, token: str, body: dict) -> dict:
    if not url.startswith("https://"):
        raise GatewayError("insecure_url", "보안 연결(https)이 아닌 주소로는 요청하지 않습니다.")
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
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
            raise GatewayError("unauthorized", "구글 쓰기 로그인이 만료됐습니다. 쓰기 권한을 다시 연결해 주세요.") from None
        if e.code == 403 and reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise GatewayError("quota_exceeded", "오늘 구글 API 사용량 한도를 넘었습니다. 내일 다시 시도해 주세요.") from None
        if e.code == 403:
            raise GatewayError("forbidden", "구글이 수정을 거부했습니다. 영상 소유 계정과 쓰기 권한을 확인해 주세요.") from None
        if e.code == 404:
            raise GatewayError("video_not_found", "영상을 찾을 수 없습니다.") from None
        if 400 <= e.code < 500:
            raise GatewayError(f"http_{e.code}", "구글이 요청을 받아들이지 않았습니다(반영되지 않음).") from None
        # 5xx: 서버가 처리했는지 알 수 없다
        raise GatewayError(f"http_{e.code}", "구글(유튜브) 서버 오류입니다. 반영 여부를 확인해야 합니다.", definite=False) from None
    except Exception:  # noqa: BLE001  (타임아웃·끊김: 반영 여부 불명 — 상세는 숨긴다)
        raise GatewayError("network", "구글(유튜브)과의 연결이 끊겼습니다. 반영 여부를 확인해야 합니다.", definite=False) from None


class LiveYouTubeGateway:
    def __init__(self, access: GoogleAccess, allowed_video_ids: Collection[str], *,
                 http_get: HttpGet = default_http_get, http_send: HttpSend = default_http_send) -> None:
        self._access, self._allowed, self._get, self._send = access, frozenset(allowed_video_ids), http_get, http_send

    def read_snippet(self, video_id: str) -> dict | None:
        q = urllib.parse.urlencode({"part": "snippet", "id": video_id})
        items = self._get(f"{API}/videos?{q}", self._access.access_token()).get("items") or []
        sn = items[0].get("snippet") if items else None
        return sn if isinstance(sn, dict) else None

    def update_snippet(self, video_id: str, body: dict) -> dict:
        if video_id not in self._allowed:
            raise GatewayError("not_allowed", "허용 목록에 없는 영상이라 실제 수정을 하지 않았습니다.")
        snippet = body.get("snippet") if isinstance(body, dict) else None
        if not isinstance(body, dict) or body.get("id") != video_id or not isinstance(snippet, dict):
            raise GatewayError("invalid_request", "요청 본문의 영상 ID 또는 snippet 이 올바르지 않습니다.")
        if not isinstance(snippet.get("title"), str) or not snippet["title"].strip():
            raise GatewayError("invalid_request", "snippet.title 이 비어 있습니다.")
        if not isinstance(snippet.get("categoryId"), str) or not snippet["categoryId"]:
            raise GatewayError("invalid_request", "snippet.categoryId 가 없습니다(유튜브는 제목 변경에도 categoryId 를 요구합니다).")
        resp = self._send(f"{API}/videos?part=snippet", self._access.access_token(), body)
        out = resp.get("snippet") if isinstance(resp, dict) else None
        if not isinstance(out, dict) or out.get("title") != snippet["title"]:
            raise GatewayError("unconfirmed", "구글 응답에서 새 제목을 확인하지 못했습니다. 반영 여부를 확인해야 합니다.", definite=False)
        return out
