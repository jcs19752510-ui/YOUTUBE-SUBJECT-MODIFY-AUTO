"""제외 사유(Q-7 기존 제외 정책 유지): 비공개·아동용·예약 라이브/프리미어·Shorts. 모르는 값은 제외 쪽으로 본다."""
from __future__ import annotations

from ytitle.config import Settings
from ytitle.updater import sequential_exclusions

from ytweb.db.models import Video


def exclusion_reasons(video: Video, policy: Settings) -> list[str]:
    # 메시지는 CLI 와 같아야 하므로 유튜브 제목 코어의 규칙 함수를 그대로 쓴다(행 대신 같은 키의 dict 를 넘김).
    row = {
        "privacy_status": video.privacy_status,
        "made_for_kids": video.made_for_kids,
        "live_broadcast_content": video.live_broadcast_content,
        "duration_sec": video.duration_sec,
    }
    return list(sequential_exclusions(row, policy))  # type: ignore[arg-type]
