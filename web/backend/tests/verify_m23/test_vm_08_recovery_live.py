"""TC-VM-700~: 실제 모드에서 재시작 복구(recover_running_items)와 구글 읽기 실패 — 워커 틱이 죽지 않는지, 이중 반영이 없는지."""
from __future__ import annotations

import re

import pytest
from sqlalchemy import select

from tests.verify_m23.conftest import approve_via_api, do_execute, make_draft
from ytweb.db.models import BatchItem, Change
from ytweb.domain.batches import run_due_items, recover_running_items
from tests.verify_m23.test_vm_07_live_e2e import prepare, queued, tick, changes

HANGUL = re.compile("[가-힣]")


def crash_after_planned(w):
    """반영 직전(planned 기록 확정, PUT 전)에 워커가 죽은 상태를 만든다: PUT 5xx(미반영)로 planned 를 남기고 항목을 running 으로 되돌린다."""
    queued(w)
    w.fg.update_mode = "http_5xx_not_applied"
    tick(w)
    w.fg.update_mode = "ok"
    with w.factory() as s:
        it = s.execute(select(BatchItem)).scalars().one()
        it.status = "running"
        ch = s.execute(select(Change)).scalars().one()
        ch.result = "planned"
        s.commit()
    w.fg.calls.clear()


def test_tc_vm_700_recovery_title_unchanged_marks_aborted_without_second_put(live):
    crash_after_planned(live)
    assert recover_running_items(live.factory, live.clock(), live.env, stale_after=__import__("datetime").timedelta(0)) == 1
    assert live.fg.put_calls() == []
    assert [c.result for c in changes(live)] == ["aborted"]


def test_tc_vm_701_recovery_title_applied_confirms_success_without_second_put(live):
    crash_after_planned(live)
    live.fg.videos[live.ids[0]]["title"] = changes(live)[0].new_title            # 사실은 반영돼 있었음
    recover_running_items(live.factory, live.clock(), live.env, stale_after=__import__("datetime").timedelta(0))
    assert live.fg.put_calls() == [] and [c.result for c in changes(live)] == ["success"]


@pytest.mark.parametrize("fail", ["quota_on_read"])
def test_tc_vm_702_google_read_failure_during_recovery_must_not_crash_the_tick(live, fail):
    crash_after_planned(live)
    live.fg.quota_on_read = True
    live.clock.advance(minutes=11)                                               # 10분 지나야 복구 대상(STALE_RUNNING)
    try:
        run_due_items(live.factory, live.clock(), live.env)
    except Exception as e:                                                       # noqa: BLE001
        pytest.fail(f"복구 중 구글 읽기 실패가 워커 틱 전체를 중단시킴: {type(e).__name__}: {e}")
    assert live.fg.put_calls() == []
    with live.factory() as s:
        assert s.execute(select(BatchItem)).scalars().one().status in ("running", "failed")   # 항목이 사라지거나 성공으로 둔갑하지 않음


def test_tc_vm_703_recovery_reads_only_allowed_videos_after_allowed_list_shrinks_OBSERVATION(live):
    """관찰(Low): 복구는 허용 목록을 보지 않고 읽기만 한다(쓰기는 안 함). 읽기 호출 id 와 PUT 0회를 기록."""
    crash_after_planned(live)
    live.mp.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", live.ids[1])
    recover_running_items(live.factory, live.clock(), live.env, stale_after=__import__("datetime").timedelta(0))
    assert live.fg.put_calls() == []
