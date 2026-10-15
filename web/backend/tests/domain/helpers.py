"""도메인 테스트 공용 도구."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ytweb.ai.mock import MockSuggester
from ytweb.db.models import Suggestion, Video
from ytweb.domain.batches import create_draft, execute_batch
from ytweb.domain.common import Env
from ytweb.domain.suggestions import approve, generate_for_video
from ytweb.youtube.base import GatewayError
from ytweb.youtube.mock import MockYouTubeGateway

SUGGESTER = MockSuggester()


class FaultyGateway(MockYouTubeGateway):
    """모의 게이트웨이에 결함을 주입한다(조회 변조, 조회/갱신 오류, 갱신 시 필드 소실)."""

    def __init__(self, session: Session, clock: Callable[[], datetime]) -> None:
        super().__init__(session, clock)
        self.calls: list[str] = []
        self.read_exc: Exception | None = None
        self.update_exc: Exception | None = None
        self.read_override: Callable[[int, dict | None], dict | None] | None = None
        self.drop_on_update: tuple[str, ...] = ()
        self.apply_then_raise: GatewayError | None = None  # 갱신은 반영하고 오류를 낸다(결과 불명 시뮬레이션)
        self.read_count = 0

    def read_snippet(self, video_id: str):
        self.calls.append("read")
        self.read_count += 1
        if self.read_exc is not None:
            raise self.read_exc
        snap = super().read_snippet(video_id)
        return self.read_override(self.read_count, snap) if self.read_override else snap

    def update_snippet(self, video_id: str, body: dict):
        self.calls.append("update")
        if self.update_exc is not None:
            raise self.update_exc
        if self.drop_on_update:
            body = {**body, "snippet": {k: v for k, v in body["snippet"].items() if k not in self.drop_on_update}}
        out = super().update_snippet(video_id, body)
        if self.apply_then_raise is not None:
            raise self.apply_then_raise
        return out


def eligible_video_ids(db: Session, n: int) -> list[str]:
    ids = [v.video_id for v in db.execute(select(Video).order_by(Video.video_id)).scalars() if not v.exclusion_reasons]
    assert len(ids) >= n, "시드 영상이 부족합니다"
    return ids[:n]


def suggest(db: Session, env: Env, now: datetime, video_id: str, count: int = 1) -> list[Suggestion]:
    return generate_for_video(db, video_id, count=count, tone="friendly", now=now, env=env, suggester=SUGGESTER)


def approved(db: Session, env: Env, now: datetime, video_id: str, approver: str = "홍길동") -> Suggestion:
    sug = suggest(db, env, now, video_id, 1)[0]
    assert sug.validation_result == "pass", (sug.title, sug.validation_reasons)
    approve(db, sug.id, approver, now=now, env=env)
    return sug


def approved_many(db: Session, env: Env, now: datetime, n: int, skip: int = 0) -> list[Suggestion]:
    return [approved(db, env, now, vid) for vid in eligible_video_ids(db, n + skip)[skip:]]


def queued_batch(db: Session, env: Env, now: datetime, n: int, skip: int = 0):
    sugs = approved_many(db, env, now, n, skip)
    batch, pre = create_draft(db, [s.id for s in sugs], None, now=now, env=env)
    batch, job = execute_batch(db, batch.id, pre["confirm_text"], now=now, env=env)
    db.commit()
    return batch, sugs, job
