"""DEF-LIVE-005: 실제 수정이 꺼진 상태에서 실제(youtube) 영상은 모의로 '성공' 처리되지 않고 막힌다(선생님 PC 배치 #2 재현)."""
from __future__ import annotations

import pytest

from ytweb.core.errors import ProblemError
from ytweb.db.models import Video
from ytweb.domain.batches import LIVE_OFF_MESSAGE, apply_one, create_draft

from tests.domain.helpers import approved, eligible_video_ids
from tests.verify_wb.vbh import Faulty, changes, queued


def test_real_video_cannot_be_put_in_a_batch_while_live_is_off(seeded, db, env, clock):
    vid = eligible_video_ids(db, 1)[0]
    sug = approved(db, env, clock(), vid)
    db.get(Video, vid).source = "youtube"
    db.flush()
    with pytest.raises(ProblemError) as e:
        create_draft(db, [sug.id], None, now=clock(), env=env)
    assert e.value.code == "batch_empty" and LIVE_OFF_MESSAGE[:20] in (e.value.detail or "")


def test_demo_video_still_works_with_mock_gateway(seeded, db, env, clock):
    vid = eligible_video_ids(db, 1)[0]
    sug = approved(db, env, clock(), vid)
    b, pre = create_draft(db, [sug.id], None, now=clock(), env=env)
    assert pre["item_count"] == 1 and pre["blocked"] == []


def test_queued_real_video_item_is_skipped_not_applied_in_mock_mode(seeded, db, env, clock):
    b, _ = queued(db, env, clock(), 1)
    item = b.items[0]
    db.get(Video, item.video_id).source = "youtube"  # 대기열에 들어간 뒤 실제 영상이 된 경우(깊은 방어)
    db.flush()
    out = apply_one(db, item.id, now=clock(), env=env, gateway=Faulty(db, clock))
    assert out.code == "live_off" and out.status in ("skipped", "failed")
    assert changes(db) == []  # 변경 기록·쓰기 없음
