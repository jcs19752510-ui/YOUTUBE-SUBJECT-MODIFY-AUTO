"""M3 단위 4 시험(TC-M3-040~): 실제 모드 안전장치 — 확인 문구, 허용 영상 사전 차단, 변경 기록 mode. 실제 구글 호출 없음."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from tests.domain.helpers import approved_many, eligible_video_ids, queued_batch
from ytweb.core.errors import ProblemError
from ytweb.db.models import Change
from ytweb.domain import live_gateway as lg
from ytweb.domain.batches import create_draft, execute_batch
from ytweb.youtube import google_oauth as oauth


@pytest.fixture
def live_env(env, monkeypatch, tmp_path):
    """실제 모드 3조건을 모두 갖춘 환경(쓰기 토큰·플래그·허용 목록 설정은 호출 쪽에서 허용 영상만 바꾼다)."""
    client = tmp_path / "client.json"
    client.write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    oauth.TokenStore(env.secrets_dir / lg.WRITE_TOKEN_FILE).save(
        {"access_token": "AT", "refresh_token": "RT", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    monkeypatch.setenv("YTWEB_GOOGLE_CLIENT_FILE", str(client))
    monkeypatch.setenv("YTWEB_LIVE_WRITE", "1")
    return env


def _problem(fn, *a, **kw) -> ProblemError:
    with pytest.raises(ProblemError) as e:
        fn(*a, **kw)
    return e.value


def test_tc_m3_040_demo_confirm_text_unchanged(seeded, env, clock):
    sugs = approved_many(seeded, env, clock(), 2)
    _, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    assert pre["confirm_text"] == "실행 2건" and not any("실제 모드" in w for w in pre["warnings"])


def test_tc_m3_041_live_precheck_uses_live_phrase_and_warns(seeded, live_env, clock, monkeypatch):
    sugs = approved_many(seeded, live_env, clock(), 2)
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", ",".join(s.video_id for s in sugs))
    batch, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=live_env)
    assert pre["confirm_text"] == "실제 실행 2건" and pre["blocked"] == []
    assert "실제 모드입니다" in pre["warnings"][0] and "2개" in pre["warnings"][0]
    e = _problem(execute_batch, seeded, batch.id, "실행 2건", now=clock(), env=live_env)  # 데모 문구로는 실행할 수 없다
    assert e.code == "confirm_text_mismatch" and "실제 실행 2건" in e.detail
    b, job = execute_batch(seeded, batch.id, "실제 실행 2건", now=clock(), env=live_env)
    assert b.status == "queued" and job.type == "batch.execute"


def test_tc_m3_042_video_not_in_allowlist_is_blocked_before_any_record(seeded, live_env, clock, monkeypatch):
    sugs = approved_many(seeded, live_env, clock(), 2)
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", sugs[0].video_id)  # 2번째 영상은 허용 안 함
    _, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=live_env)
    assert pre["item_count"] == 1
    assert [b.get("code") or b.get("reason_code") for b in pre["blocked"]] and "live_not_allowed" in json.dumps(pre["blocked"], ensure_ascii=False)
    assert seeded.query(Change).count() == 0  # 기록·쿼터 소비 없음


def test_tc_m3_043_demo_mode_does_not_apply_allowlist(seeded, env, clock, monkeypatch):
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", "zzzzzzzzzzz")  # 허용 목록이 있어도 실제 모드가 아니면(플래그·토큰 없음) 영향 없음
    sugs = approved_many(seeded, env, clock(), 1)
    _, pre = create_draft(seeded, [s.id for s in sugs], None, now=clock(), env=env)
    assert pre["item_count"] == 1 and pre["blocked"] == []


def test_tc_m3_044_not_allowed_reason_and_modes(live_env, monkeypatch):
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", "abcdefghijk")
    assert lg.not_allowed_reason("abcdefghijk", live_env.secrets_dir) is None
    assert "허용 영상이 아닙니다" in lg.not_allowed_reason("zzzzzzzzzzz", live_env.secrets_dir)
    assert lg.confirm_text(3, True) == "실제 실행 3건" and lg.confirm_text(3, False) == "실행 3건"
    assert lg.is_live(object()) is False


def test_tc_m3_045_live_gateway_records_mode_live_and_demo_records_demo(seeded, live_env, env, clock, monkeypatch):
    from sqlalchemy import select
    from ytweb.db.models import BatchItem
    from ytweb.domain.batches import apply_one
    from ytweb.youtube.mock import MockYouTubeGateway
    demo_batch, _, _ = queued_batch(seeded, live_env, clock(), 1)  # 허용 목록 없음 = 데모로 확정
    d_item = seeded.execute(select(BatchItem).where(BatchItem.batch_id == demo_batch.id)).scalars().one()
    apply_one(seeded, d_item.id, now=clock(), env=live_env, gateway=MockYouTubeGateway(seeded, clock=clock))
    second = eligible_video_ids(seeded, 2)[1]
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", second)  # 이제 실제 모드로 확정
    live_batch, _, _ = queued_batch(seeded, live_env, clock(), 1, skip=1)
    l_item = seeded.execute(select(BatchItem).where(BatchItem.batch_id == live_batch.id)).scalars().one()
    live = lg.SyncedLiveGateway(seeded, MockYouTubeGateway(seeded, clock=clock), clock())  # 실제 구글 대신 모의를 안쪽에 둔다
    apply_one(seeded, l_item.id, now=clock(), env=live_env, gateway=live)
    modes = {c.video_id: c.mode for c in seeded.query(Change).all()}
    assert modes[d_item.video_id] == "demo" and modes[l_item.video_id] == "live"


def test_tc_m3_046_apply_blocks_not_allowed_video_before_planned_record(seeded, live_env, clock, monkeypatch):
    from sqlalchemy import select
    from ytweb.db.models import BatchItem
    from ytweb.domain.batches import apply_one
    from ytweb.youtube.mock import MockYouTubeGateway
    batch, sugs, _ = queued_batch(seeded, live_env, clock(), 1)
    item = seeded.execute(select(BatchItem).where(BatchItem.batch_id == batch.id)).scalars().one()
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", "zzzzzzzzzzz")  # 이 영상은 허용 안 함
    out = apply_one(seeded, item.id, now=clock(), env=live_env, gateway=MockYouTubeGateway(seeded, clock=clock))
    assert out.status != "success" and out.code == "live_not_allowed"
    assert seeded.query(Change).count() == 0


def test_tc_m3_047_rollback_blocks_not_allowed_video(seeded, live_env, clock, monkeypatch):
    from ytweb.domain.batches import apply_one
    from ytweb.domain.changes import rollback_change
    from ytweb.youtube.mock import MockYouTubeGateway
    from sqlalchemy import select
    from ytweb.db.models import BatchItem
    batch, sugs, _ = queued_batch(seeded, live_env, clock(), 1)
    item = seeded.execute(select(BatchItem).where(BatchItem.batch_id == batch.id)).scalars().one()
    gw = MockYouTubeGateway(seeded, clock=clock)
    apply_one(seeded, item.id, now=clock(), env=live_env, gateway=gw)
    change = seeded.query(Change).one()
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", "zzzzzzzzzzz")
    e = _problem(rollback_change, seeded, change.id, change.video_id, "홍길동", now=clock(), env=live_env, gateway=gw)
    assert e.code == "live_not_allowed"


class _StaleAfterWrite:
    """반영 직후 재조회가 한동안 이전 제목을 돌려주는 유튜브(실제로 겪은 현상)를 흉내 낸다."""

    def __init__(self, inner, stale_reads: int) -> None:
        self._inner, self._stale, self._wrote, self._before = inner, stale_reads, False, None

    def read_snippet(self, video_id):
        snap = self._inner.read_snippet(video_id)
        if self._wrote and self._stale > 0 and snap is not None:
            self._stale -= 1
            snap = {**snap, "title": self._before}
        return snap

    def update_snippet(self, video_id, body):
        self._before = self._inner.read_snippet(video_id)["title"]
        self._wrote = True
        return self._inner.update_snippet(video_id, body)


def _live_apply(seeded, live_env, clock, monkeypatch, stale_reads):
    from sqlalchemy import select
    from ytweb.db.models import BatchItem
    from ytweb.domain import batches as bt
    from ytweb.domain.batches import apply_one
    from ytweb.youtube.mock import MockYouTubeGateway
    monkeypatch.setattr(bt, "_sleep", lambda s: None)
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", eligible_video_ids(seeded, 1)[0])  # 실제 모드로 확정된 배치여야 한다
    batch, sugs, _ = queued_batch(seeded, live_env, clock(), 1)
    item = seeded.execute(select(BatchItem).where(BatchItem.batch_id == batch.id)).scalars().one()
    live = lg.SyncedLiveGateway(seeded, _StaleAfterWrite(MockYouTubeGateway(seeded, clock=clock), stale_reads), clock())
    out = apply_one(seeded, item.id, now=clock(), env=live_env, gateway=live)
    assert out.status == "success" or out.code == "verify_failed", (out.status, out.code)
    return out, seeded.query(Change).one(), item


def test_tc_m3_048_live_stale_reread_is_retried_and_succeeds(seeded, live_env, clock, monkeypatch):
    """결함: 유튜브에는 바뀌었는데 직후 재조회가 이전 제목이라 '실패'로 표시됨. 재시도로 성공 처리돼야 한다."""
    out, change, item = _live_apply(seeded, live_env, clock, monkeypatch, stale_reads=2)
    assert out.status == "success" and change.error_code is None and change.verify_result["ok"] and change.verify_result.get("retried")
    assert item.status == "success" and item.skip_reason is None


def test_tc_m3_049_live_title_never_matches_stays_failed_not_silent(seeded, live_env, clock, monkeypatch):
    """재시도 횟수를 넘도록 계속 다르면 실패로 남는다(조용히 성공 처리하지 않는다)."""
    out, change, item = _live_apply(seeded, live_env, clock, monkeypatch, stale_reads=99)
    assert out.status == "failed" and change.error_code == "verify_failed" and "제목" in item.skip_reason


def test_tc_m3_050_reconcile_fixes_failed_item_when_youtube_shows_new_title(seeded, live_env, clock, monkeypatch):
    """이미 '실패'로 남은 항목(유튜브에는 바뀜)을 워커가 다시 읽어 성공으로 바로잡고, 쓰기는 하지 않는다."""
    from ytweb.domain.batches import reconcile_verify_failed
    from ytweb.youtube.mock import MockYouTubeGateway
    out, change, item = _live_apply(seeded, live_env, clock, monkeypatch, stale_reads=99)
    assert item.status == "failed"
    rows = reconcile_verify_failed(seeded, lg.SyncedLiveGateway(seeded, MockYouTubeGateway(seeded, clock=clock), clock()), clock())
    seeded.refresh(item), seeded.refresh(change)
    assert [i for i, _ in rows] == [item.id] and item.status == "success" and item.skip_reason is None and change.error_code is None


def test_tc_m3_051_reconcile_leaves_truly_different_and_does_not_reread_again(seeded, live_env, clock, monkeypatch):
    from ytweb.domain.batches import reconcile_verify_failed
    from ytweb.youtube.mock import MockYouTubeGateway
    out, change, item = _live_apply(seeded, live_env, clock, monkeypatch, stale_reads=99)
    stale = _StaleAfterWrite(MockYouTubeGateway(seeded, clock=clock), 99)
    stale._wrote, stale._before = True, change.previous_title
    gw = lg.SyncedLiveGateway(seeded, stale, clock())
    assert "여전히 다름" in reconcile_verify_failed(seeded, gw, clock())[0][1]
    seeded.refresh(item)
    assert item.status == "failed"
    assert reconcile_verify_failed(seeded, gw, clock()) == []  # 두 번째는 읽지 않는다
