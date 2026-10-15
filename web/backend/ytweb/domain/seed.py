"""데모 영상 시드(WEB_DESIGN §3 videos.sync). 같은 입력이면 항상 같은 결과이고, 다시 실행해도 중복 없이 갱신된다.

- 영상 ID 는 `demoVid0001` 형식(11자). 생활 70% / 건강 20% / 금융 10% 비율의 가상 시니어 생활 채널.
- Shorts·비공개·아동용·예약 게시·일부 비공개 영상이 섞여 있어 제외 사유 표시를 시험할 수 있다.
- 우리 앱이 이미 제목을 바꾼 영상(changes 있음)은 제목·snippet 을 되돌리지 않는다(유튜브 쪽 현재 상태를 덮어쓰지 않는 새로고침).
- 변경 전 성과(before) 스냅샷은 한 번 만들면 다시 만들거나 바꾸지 않는다(전후 비교의 기준선이 흔들리지 않게).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from youtube_title.config import Settings

from ytweb.db.models import Change, MetricsSnapshot, Video
from ytweb.domain.exclusions import exclusion_reasons
from ytweb.youtube.base import make_excerpt

DEFAULT_COUNT = 200
MAX_COUNT = 1000
CHANNEL_ID = "UCdemoSeniorLifeCh0001"
ENDINGS = ("이렇게 하세요", "총정리", "꼭 알아두세요", "처음부터 끝까지", "따라 해보세요")

LIFE = (
    "냉장고 정리", "김치 보관", "전기장판 쓰기", "스마트폰 글자 키우기", "카톡 사진 보내기", "화분 키우기", "베란다 텃밭",
    "세탁기 청소", "가스레인지 청소", "이불 빨래", "난방비 아끼기", "택배 보내기", "손주 영상통화", "유튜브 구독하기",
    "키오스크 주문", "버스 환승", "사진 정리", "앨범 만들기", "멸치볶음 만들기", "된장 담그기", "장 보기",
    "옷장 정리", "신발장 정리", "전구 갈기", "멀티탭 정리", "리모컨 쓰기", "와이파이 연결", "블루투스 이어폰",
)
HEALTH = ("무릎 관절 스트레칭", "아침 혈압 재기", "당뇨 식단 짜기", "허리 근력 운동", "숙면 저녁 습관", "기억력 놀이", "영양제 챙기기", "눈 건강 체조")
FINANCE = ("연금 수령 시기", "적금 만기 확인", "보험 증권 정리", "금리 비교 앱")
TOPIC_CATEGORY = {"life": "26", "health": "27", "finance": "27"}


@dataclass(frozen=True)
class SeedResult:
    created: int
    updated: int
    snapshots_created: int
    total: int


def _topic_and_index(i: int) -> tuple[str, int]:
    """i(1부터)를 생활 7 : 건강 2 : 금융 1 비율로 나누고 주제 안 순번을 돌려준다."""
    block, pos = divmod(i - 1, 10)
    if pos < 7:
        return "life", block * 7 + pos
    if pos < 9:
        return "health", block * 2 + (pos - 7)
    return "finance", block


def _title_for(topic: str, k: int) -> tuple[str, str]:
    subjects = {"life": LIFE, "health": HEALTH, "finance": FINANCE}[topic]
    subject = subjects[k % len(subjects)]
    ending_idx = (k // len(subjects)) % len(ENDINGS)
    round_no = k // (len(subjects) * len(ENDINGS))
    title = f"{subject} {ENDINGS[ending_idx]}" + (f" {round_no + 1}편" if round_no else "")
    return subject, title


def _description(subject: str) -> str:
    return (
        f"{subject} 하는 순서와 주의할 점을 처음이라도 쉽게 따라 할 수 있게 집에서 바로 해보도록 천천히 알려드립니다. "
        f"{subject}의 핵심만 차근차근 설명합니다. ※ 이 영상은 시연용 가상 데이터입니다."
    )


def build_video_fields(i: int) -> dict:
    topic, k = _topic_and_index(i)
    subject, title = _title_for(topic, k)
    description = _description(subject)
    privacy, kids, live, duration = "public", False, "none", 240 + (i * 53) % 1200
    published = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc) + timedelta(days=i)
    if i % 11 == 0:
        privacy = "unlisted"
    if i % 13 == 0:
        duration = 20 + (i * 7) % 100
    if i % 17 == 0:
        privacy = "private"
    if i % 29 == 0:
        kids = True
    if i % 37 == 0:
        privacy, live, published = "private", "upcoming", datetime(2027, 1, 1, 9, 0, tzinfo=timezone.utc)
    views = 0 if privacy == "private" else 300 + (i * 7919) % 48000
    snippet = {
        "publishedAt": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "channelId": CHANNEL_ID,
        "title": title,
        "description": description,
        "thumbnails": {"default": {"url": f"https://i.ytimg.com/vi/demoVid{i:04d}/default.jpg", "width": 120, "height": 90}},
        "channelTitle": "데모 시니어 생활 채널",
        "tags": [subject, "시니어", {"life": "생활", "health": "건강", "finance": "금융"}[topic]],
        "categoryId": TOPIC_CATEGORY[topic],
        "liveBroadcastContent": live,
        "defaultLanguage": "ko",
        "defaultAudioLanguage": "ko",
        "localized": {"title": title, "description": description},
    }
    return {
        "video_id": f"demoVid{i:04d}",
        "title": title,
        "category_id": snippet["categoryId"],
        "privacy_status": privacy,
        "made_for_kids": kids,
        "live_broadcast_content": live,
        "duration_sec": duration,
        "description_excerpt": make_excerpt(description),
        "snippet": snippet,
        "views": views,
    }


def _before_metrics(i: int, today: date) -> dict | None:
    if i % 3 != 1 or i % 13 == 0:
        return None
    # 7의 배수 영상은 최소 노출 기준(1000) 미만이라 '데이터 부족' 시연이 된다
    impressions = 300 + (i * 131) % 600 if i % 7 == 0 else 1200 + (i * 977) % 24000
    ctr = round(2 + ((i * 37) % 60) / 10, 1)
    end = today - timedelta(days=8)
    return {
        "impressions": impressions,
        "ctr": ctr,
        "views": int(impressions * ctr / 100),
        "watch_minutes": round(impressions * ctr / 100 * 3.4, 1),
        "period_end": end,
        "period_start": end - timedelta(days=29),
    }


def seed_demo(session: Session, now: datetime, policy: Settings, *, count: int = DEFAULT_COUNT) -> SeedResult:
    if not 1 <= count <= MAX_COUNT:
        raise ValueError(f"count 는 1~{MAX_COUNT} 이어야 합니다.")
    ids = [f"demoVid{i:04d}" for i in range(1, count + 1)]
    existing = {v.video_id: v for v in session.execute(select(Video).where(Video.video_id.in_(ids))).scalars()}
    touched = set(session.execute(select(Change.video_id).where(Change.video_id.in_(ids)).distinct()).scalars())
    have_snapshot = set(session.execute(
        select(MetricsSnapshot.video_id).where(MetricsSnapshot.phase == "before", MetricsSnapshot.source == "demo", MetricsSnapshot.video_id.in_(ids))
    ).scalars())
    created = updated = snaps = 0
    today = now.astimezone(timezone.utc).date()
    for i in range(1, count + 1):
        fields = build_video_fields(i)
        vid = fields["video_id"]
        video = existing.get(vid)
        if video is None:
            video = Video(**fields, is_short=False, exclusion_reasons=[], source="demo", fetched_at=now)
            session.add(video)
            created += 1
        else:
            video.fetched_at = now
            if vid not in touched:
                for key, value in fields.items():
                    setattr(video, key, value)
            updated += 1
        if vid not in touched or video.exclusion_reasons is None:
            video.is_short = fields["duration_sec"] <= policy.shorts_max_seconds
            video.exclusion_reasons = exclusion_reasons(video, policy)
    session.flush()  # 스냅샷은 영상 행을 외래키로만 참조한다(ORM 관계 없음) — 영상을 먼저 확정해야 PostgreSQL 에서 순서가 맞는다
    for i in range(1, count + 1):
        vid = f"demoVid{i:04d}"
        metrics = _before_metrics(i, today)
        if metrics is not None and vid not in have_snapshot:
            session.add(MetricsSnapshot(video_id=vid, taken_at=now, phase="before", source="demo", **metrics))
            snaps += 1
    session.flush()
    return SeedResult(created, updated, snaps, count)
