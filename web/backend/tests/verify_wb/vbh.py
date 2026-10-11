"""독립 검증 공용 도구(구현자 helpers 와 겹치지 않게 별도 작성)."""
from __future__ import annotations

import copy
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ytweb.ai.base import SuggestionDraft
from ytweb.db.models import BatchItem, Change, QuotaUsage, Suggestion, Video
from ytweb.domain.batches import create_draft, execute_batch
from ytweb.domain.common import Env
from ytweb.domain.suggestions import approve, generate_for_video
from ytweb.youtube.mock import MockYouTubeGateway

UTC = timezone.utc


class Stub:
    """원하는 응답을 그대로 돌려주는 가짜 AI(검증기·가드의 방어를 시험할 때)."""

    name, model = "stub", "stub-0"

    def __init__(self, drafts):
        self.drafts = drafts
        self.briefs = []

    def suggest(self, brief, *, count, tone):
        self.briefs.append((brief, count, tone))
        if isinstance(self.drafts, Exception):
            raise self.drafts
        return self.drafts


class Faulty(MockYouTubeGateway):
    """호출 순서별로 결함을 주입하는 게이트웨이."""

    def __init__(self, session, clock):
        super().__init__(session, clock)
        self.reads = 0
        self.updates = 0
        self.on_read = None      # (n, snippet|None) -> snippet|None | raise
        self.on_update = None    # (n, body) -> body | raise
        self.after_update = None  # (video row) -> None  (갱신 후 외부 변경 흉내)

    def read_snippet(self, video_id):
        self.reads += 1
        snap = super().read_snippet(video_id)
        return self.on_read(self.reads, snap) if self.on_read else snap

    def update_snippet(self, video_id, body):
        self.updates += 1
        if self.on_update:
            body = self.on_update(self.updates, body)
        out = super().update_snippet(video_id, body)
        if self.after_update:
            self.after_update(self._session.get(Video, video_id))
        return out


def life_ids(db: Session, n: int, skip: int = 0) -> list[str]:
    """제외 사유 없고 생활 주제(엄격 모드 아님)인 영상 ID."""
    rows = db.execute(select(Video).order_by(Video.video_id)).scalars().all()
    ids = [v.video_id for v in rows if not v.exclusion_reasons and v.category_id == "26"]
    assert len(ids) >= n + skip
    return ids[skip:skip + n]


def make_sug(db: Session, env: Env, now: datetime, video_id: str, title: str | None = None, *, evidence: str | None = None, topic: str = "life") -> Suggestion:
    """제안 1개를 만든다(title 을 주면 그 제목, 아니면 모의 AI 의 첫 번째 통과 후보)."""
    video = db.get(Video, video_id)
    if title is None:
        from ytweb.ai.mock import MockSuggester
        return generate_for_video(db, video_id, count=1, tone="t", now=now, env=env, suggester=MockSuggester())[0]
    ev = evidence if evidence is not None else (video.description_excerpt or "").split(".")[0] + "."
    return generate_for_video(db, video_id, count=1, tone="t", now=now, env=env, suggester=Stub([SuggestionDraft(title, ev, topic)]))[0]


def ok_sug(db, env, now, video_id, approver="검수자") -> Suggestion:
    s = make_sug(db, env, now, video_id)
    assert s.validation_result == "pass", (s.title, s.validation_reasons)
    approve(db, s.id, approver, now=now, env=env)
    return s


def queued(db: Session, env: Env, now: datetime, n: int, skip: int = 0):
    sugs = [ok_sug(db, env, now, v) for v in life_ids(db, n, skip)]
    b, pre = create_draft(db, [s.id for s in sugs], None, now=now, env=env)
    b, job = execute_batch(db, b.id, pre["confirm_text"], now=now, env=env)
    db.commit()
    return b, sugs


def set_all_due(db: Session, batch_id: int, day) -> None:
    db.execute(update(BatchItem).where(BatchItem.batch_id == batch_id).values(scheduled_date=day))
    db.commit()


def changes(db: Session, video_id: str | None = None) -> list[Change]:
    stmt = select(Change).order_by(Change.id)
    if video_id:
        stmt = stmt.where(Change.video_id == video_id)
    return list(db.execute(stmt).scalars())


def quota_units(db: Session) -> int:
    from sqlalchemy import func
    return int(db.execute(select(func.coalesce(func.sum(QuotaUsage.units), 0))).scalar_one())


def snippet_of(db: Session, vid: str) -> dict:
    db.expire_all()
    return copy.deepcopy(db.get(Video, vid).snippet)


def set_cap(db: Session, clock, cap) -> None:
    from ytweb.core.settings_store import set_web_setting
    set_web_setting(db, "daily_apply_cap", cap, now=clock())
    db.commit()


def day_counts(db: Session, batch_id: int | None = None) -> dict[str, int]:
    db.expire_all()
    stmt = select(BatchItem)
    if batch_id is not None:
        stmt = stmt.where(BatchItem.batch_id == batch_id)
    out: dict[str, int] = {}
    for it in db.execute(stmt).scalars():
        k = it.scheduled_date.isoformat() if it.scheduled_date else "none"
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def add_change(db: Session, video_id: str, when: datetime, *, result: str = "success", change_type: str = "apply", n: int = 1):
    """이력 직접 삽입(한도 경계 시험용). planned 는 영상당 1개 고유 제약이 있으므로 n>1 이면 success 만."""
    rows = []
    for i in range(n):
        c = Change(video_id=video_id, change_type=change_type, previous_title=f"p{i}", new_title=f"n{i}", result=result, mode="demo",
                   created_at=when, applied_at=when if result == "success" else None, backup_snippet=None)
        db.add(c)
        rows.append(c)
    db.flush()
    return rows


def fill_quota(db: Session, now: datetime, units: int) -> None:
    from ytweb.core.clock import pt_date
    db.add(QuotaUsage(pt_date=pt_date(now), method="videos.list", units=units, called_at=now, status="ok"))
    db.commit()
