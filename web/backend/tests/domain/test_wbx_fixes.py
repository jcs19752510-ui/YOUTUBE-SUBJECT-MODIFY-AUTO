"""수정 단위 W-FIX-BE(2026-10-11) 시험 TC-WBX-001~: 초안 배치 버리기(DEF-7-009), 재시작 복구 감사(DEF-7B-002), 면책 문구(DEF-9-007),
정수 상한(DEF-9-001), 승인자 이름(DEF-9-004). SQLite 에서 도는 것만 둔다(경합은 test_wbx_postgres.py)."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from ytweb.core import audit
from ytweb.db.models import AuditLog, Change, Suggestion
from ytweb.domain.batches import cancel_batch, create_draft, execute_batch, recover_running_items, run_due_items
from ytweb.domain.common import clean_approver, set_default_env
from ytweb.domain.notices import DISCLAIMER
from ytweb.domain.seed import seed_demo
from ytweb.core.errors import ProblemError
from ytweb.youtube.mock import MockYouTubeGateway

from tests.domain.conftest import hdr
from tests.domain.helpers import approved_many, eligible_video_ids, queued_batch, suggest

DISCLAIMER_TEXT = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."


@pytest.fixture
def data(factory, env, clock):
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    set_default_env(env)
    return factory


def _audit(db, action):
    return list(db.execute(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)).scalars())


# ───────────── DEF-7-009: 초안 배치 버리기 ─────────────

def test_tc_wbx_001_draft_holder_is_named_in_blocked_reason(seeded, env, clock):
    s1, s2 = approved_many(seeded, env, clock(), 2)
    draft, _ = create_draft(seeded, [s1.id], None, now=clock(), env=env)
    _, pre = create_draft(seeded, [s1.id, s2.id], None, now=clock(), env=env)
    assert pre["item_count"] == 1
    (blocked,) = pre["blocked"]
    assert blocked["suggestion_id"] == s1.id and blocked["code"] == "already_in_batch" and blocked["batch_id"] == draft.id
    assert f"초안 배치 #{draft.id}" in blocked["reason"]


def test_tc_wbx_002_cancelling_draft_frees_suggestions_for_a_new_batch(seeded, env, clock):
    s1, s2 = approved_many(seeded, env, clock(), 2)
    draft, _ = create_draft(seeded, [s1.id, s2.id], None, now=clock(), env=env)
    seeded.commit()
    out = cancel_batch(seeded, draft.id, now=clock(), env=env)
    seeded.commit()
    assert out.status == "cancelled" and [i.status for i in out.items] == ["cancelled", "cancelled"]
    assert all("초안" in i.skip_reason and i.skip_reason.startswith("[cancelled]") for i in out.items)
    assert [seeded.get(Suggestion, s.id).status for s in (s1, s2)] == ["approved", "approved"]   # 승인은 그대로 남아 다시 담을 수 있다
    again, pre = create_draft(seeded, [s1.id, s2.id], None, now=clock(), env=env)
    assert again.id != draft.id and pre["item_count"] == 2 and pre["blocked"] == []
    (rec,) = _audit(seeded, "batch.cancel")
    assert rec.target_id == str(draft.id) and rec.detail == {"cancelled_items": 2, "was_draft": True}
    assert audit.verify_chain(seeded)


def test_tc_wbx_003_cancel_is_not_repeated_second_call_is_409_without_extra_effects(seeded, env, clock):
    s1, = approved_many(seeded, env, clock(), 1)
    draft, _ = create_draft(seeded, [s1.id], None, now=clock(), env=env)
    cancel_batch(seeded, draft.id, now=clock(), env=env)
    seeded.commit()
    before = seeded.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    with pytest.raises(ProblemError) as e:
        cancel_batch(seeded, draft.id, now=clock(), env=env)
    assert (e.value.status, e.value.code) == (409, "batch_not_cancellable")
    seeded.rollback()
    assert seeded.execute(select(func.count()).select_from(AuditLog)).scalar_one() == before


def test_tc_wbx_004_executed_batch_cancel_keeps_old_meaning(seeded, env, clock):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 2)
    out = cancel_batch(seeded, batch.id, now=clock(), env=env)
    seeded.commit()
    assert out.status == "cancelled" and all("배치를 중지" in i.skip_reason for i in out.items)
    (rec,) = _audit(seeded, "batch.cancel")
    assert rec.detail == {"cancelled_items": 2, "was_draft": False}
    assert [seeded.get(Suggestion, s.id).status for s in sugs] == ["approved", "approved"]


def test_tc_wbx_005_execute_after_draft_discard_is_rejected(seeded, env, clock):
    s1, = approved_many(seeded, env, clock(), 1)
    draft, pre = create_draft(seeded, [s1.id], None, now=clock(), env=env)
    cancel_batch(seeded, draft.id, now=clock(), env=env)
    seeded.commit()
    with pytest.raises(ProblemError) as e:
        execute_batch(seeded, draft.id, pre["confirm_text"], now=clock(), env=env)
    assert (e.value.status, e.value.code) == (409, "batch_not_draft")


def test_tc_wbx_006_executed_batch_holder_is_not_approved_and_non_draft_holder_wording(seeded, env, clock):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 1)
    (extra,) = approved_many(seeded, env, clock(), 1, skip=5)
    _, pre = create_draft(seeded, [sugs[0].id, extra.id], None, now=clock(), env=env)
    (blocked,) = pre["blocked"]
    assert blocked["code"] == "not_approved" and "batch_id" not in blocked            # 실행 확정된 제안은 승인 상태가 아니라 먼저 여기서 막힌다
    from ytweb.domain.batches import _holder_reason

    assert _holder_reason(7, "draft").startswith("초안 배치 #7에") and _holder_reason(7, "queued") == "배치 #7(진행 중)에 이미 담겨 있습니다."


def test_tc_wbx_007_http_discard_draft_then_recreate_and_precheck_fields(api, csrf, data, env, clock):
    with data() as s:
        ids = [x.id for x in approved_many(s, env, clock(), 3)]
        s.commit()
    first = api.post("/api/v1/batches", json={"suggestion_ids": ids[:2]}, headers=hdr(csrf, str(uuid.uuid4())))
    assert first.status_code == 201
    bid = first.json()["batch"]["id"]
    second = api.post("/api/v1/batches", json={"suggestion_ids": ids[1:]}, headers=hdr(csrf, str(uuid.uuid4())))
    assert second.status_code == 201
    pre = second.json()["precheck"]
    assert pre["item_count"] == 1 and pre["blocked"] == [{"suggestion_id": ids[1], "reason": pre["blocked"][0]["reason"], "code": "already_in_batch", "batch_id": bid}]
    assert f"초안 배치 #{bid}" in pre["blocked"][0]["reason"] and pre["notice"] == DISCLAIMER_TEXT
    gone = api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf))
    assert gone.status_code == 200 and gone.json()["status"] == "cancelled" and gone.json()["counts"]["cancelled"] == 2
    third = api.post("/api/v1/batches", json={"suggestion_ids": ids[:2]}, headers=hdr(csrf, str(uuid.uuid4())))
    assert third.status_code == 201 and third.json()["precheck"]["item_count"] == 2 and third.json()["precheck"]["blocked"] == []


# ───────────── DEF-7B-002: 복구 확정 반영의 감사 ─────────────

class _Crash(BaseException):
    """프로세스 강제 종료 흉내(except Exception 에 걸리지 않음)."""


def _crash_after_update(db, env, clock, item_id):
    from ytweb.domain.batches import apply_one

    g = MockYouTubeGateway(db, clock)
    orig = g.update_snippet

    def upd(video_id, body):
        orig(video_id, body)
        db.commit()   # 외부(유튜브) 쪽 변경은 우리 프로세스가 죽어도 남는다
        raise _Crash()

    g.update_snippet = upd   # type: ignore[method-assign]
    with pytest.raises(_Crash):
        apply_one(db, item_id, now=clock(), env=env, gateway=g)
    db.rollback()


def test_tc_wbx_008_recovered_success_leaves_change_apply_audit_with_reason(seeded, factory, env, clock):
    batch, sugs, _ = queued_batch(seeded, env, clock(), 1)
    item_id = batch.items[0].id
    _crash_after_update(seeded, env, clock, item_id)
    assert _audit(seeded, "change.apply") == []
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 1
    seeded.expire_all()
    change = seeded.execute(select(Change)).scalar_one()
    (apply_rec,) = _audit(seeded, "change.apply")
    assert apply_rec.actor == "worker" and apply_rec.target_type == "change" and apply_rec.target_id == str(change.id)
    assert apply_rec.detail == {"batch_id": batch.id, "video_id": change.video_id, "suggestion_id": sugs[0].id, "verify_ok": True, "recovered": True, "reason": "restart_recovery"}
    (rec,) = _audit(seeded, "batch.item.recovered")
    assert rec.detail == {"status": "success", "batch_id": batch.id, "video_id": change.video_id, "change_id": change.id}
    assert apply_rec.id < rec.id and audit.verify_chain(seeded)


def test_tc_wbx_009_recovery_twice_does_not_duplicate_the_apply_audit(seeded, factory, env, clock):
    batch, _, _ = queued_batch(seeded, env, clock(), 1)
    _crash_after_update(seeded, env, clock, batch.items[0].id)
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 1
    assert recover_running_items(factory, clock(), env, stale_after=timedelta(0)) == 0
    seeded.expire_all()
    assert len(_audit(seeded, "change.apply")) == 1


def test_tc_wbx_010_normal_apply_audit_is_not_marked_recovered(seeded, factory, env, clock):
    queued_batch(seeded, env, clock(), 1)
    assert run_due_items(factory, clock(), env).success == 1
    seeded.expire_all()
    (rec,) = _audit(seeded, "change.apply")
    assert "recovered" not in rec.detail


# ───────────── DEF-9-007: 면책 문구 ─────────────

def test_tc_wbx_011_disclaimer_constant_is_the_agreed_sentence():
    assert DISCLAIMER == DISCLAIMER_TEXT


def test_tc_wbx_012_report_notes_and_csv_carry_disclaimer_without_formula_risk(api, csrf, data, env, clock):
    with data() as s:
        batch, _, _ = queued_batch(s, env, clock(), 1)
        s.commit()
    assert run_due_items(data, clock(), env).success == 1
    rep = api.get("/api/v1/reports/changes").json()
    assert rep["notes"][0] == DISCLAIMER_TEXT and len(rep["notes"]) == 5 and rep["notes"].count(DISCLAIMER_TEXT) == 1
    raw = api.get("/api/v1/reports/export.csv")
    assert raw.status_code == 200 and raw.headers["content-type"].startswith("text/csv")
    text = raw.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert [DISCLAIMER_TEXT] in rows
    assert not DISCLAIMER_TEXT.startswith(("=", "+", "-", "@", "\t", "\r"))


def test_tc_wbx_013_precheck_notice_is_returned_and_old_precheck_without_notice_still_serializes(seeded, env, clock):
    s1, = approved_many(seeded, env, clock(), 1)
    batch, pre = create_draft(seeded, [s1.id], None, now=clock(), env=env)
    assert pre["notice"] == DISCLAIMER
    from ytweb.domain.schemas import PrecheckOut

    legacy = {k: v for k, v in pre.items() if k != "notice"}
    assert PrecheckOut(**legacy).notice is None


# ───────────── DEF-9-001: 정수 상한 ─────────────

HUGE = 99999999999999999999999
EDGE = 2**63


@pytest.mark.parametrize("value", [HUGE, EDGE])
def test_tc_wbx_014_oversized_integers_are_422_not_500(api, csrf, data, value):
    gets = [f"/api/v1/batches/{value}", f"/api/v1/batches?page={value}", f"/api/v1/suggestions?page={value}", f"/api/v1/changes?batch_id={value}",
            f"/api/v1/changes?page={value}", f"/api/v1/videos?page={value}"]
    for url in gets:
        r = api.get(url)
        assert r.status_code == 422 and r.json()["code"] == "validation_error", (url, r.status_code, r.text[:200])
    k = lambda: hdr(csrf, str(uuid.uuid4()))  # noqa: E731
    posts = [
        api.post("/api/v1/batches", json={"suggestion_ids": [value]}, headers=k()),
        api.post(f"/api/v1/batches/{value}/cancel", headers=hdr(csrf)),
        api.post(f"/api/v1/batches/{value}/execute", json={"confirm_text": "실행 1건"}, headers=k()),
        api.post(f"/api/v1/changes/{value}/rollback", json={"typed_video_id": "x", "approver": "a"}, headers=k()),
        api.post(f"/api/v1/suggestions/{value}/approve", json={"approver": "a"}, headers=hdr(csrf)),
        api.post(f"/api/v1/suggestions/{value}/reject", headers=hdr(csrf)),
        api.patch(f"/api/v1/suggestions/{value}", json={"title": "x"}, headers=hdr(csrf)),
    ]
    for r in posts:
        assert r.status_code == 422 and r.json()["code"] == "validation_error", (r.request.url, r.status_code, r.text[:200])


def test_tc_wbx_015_upper_bound_values_pass_validation_and_reach_the_domain(api, csrf, data):
    top = 2**63 - 1
    assert api.get(f"/api/v1/batches/{top}").status_code == 404
    assert api.get("/api/v1/batches?page=1000000").status_code == 200
    assert api.get("/api/v1/batches?page=1000001").status_code == 422
    assert api.post(f"/api/v1/batches/{top}/cancel", headers=hdr(csrf)).status_code == 404
    r = api.post("/api/v1/batches", json={"suggestion_ids": [top]}, headers=hdr(csrf, str(uuid.uuid4())))
    assert r.status_code == 422 and r.json()["code"] == "batch_empty"
    r = api.post("/api/v1/batches", json={"suggestion_ids": [0]}, headers=hdr(csrf, str(uuid.uuid4())))
    assert r.status_code == 422 and r.json()["code"] == "validation_error"


# ───────────── DEF-9-004: 승인자 이름 ─────────────

@pytest.mark.parametrize("ch", ["\u200b", "\u200c", "\u200d", "\ufeff", "\u00ad", "\u2060", "\u202e", "\u200e", "\u2028", "\u2029"])
def test_tc_wbx_016_invisible_characters_in_approver_are_rejected(ch):
    names = [f"홍{ch}길동"] + ([] if ch.isspace() else [f"{ch}홍길동", f"홍길동{ch}x"])   # 양끝의 공백류는 strip() 이 먼저 지운다
    for name in names:
        with pytest.raises(ProblemError) as e:
            clean_approver(name)
        assert e.value.code == "approver_invalid", repr(name)


def test_tc_wbx_017_ordinary_names_still_pass():
    for name in ("홍길동", "Hong Gil-dong", "김 선생님", "O'Brien", "<b>x</b>", "이름😀"):
        assert clean_approver(name) == name
    assert clean_approver("  홍길동  ") == "홍길동"


def test_tc_wbx_018_http_approve_rejects_zero_width_approver_and_changes_nothing(api, csrf, data, env, clock):
    with data() as s:
        sug = suggest(s, env, clock(), eligible_video_ids(s, 1)[0])[0]
        s.commit()
    r = api.post(f"/api/v1/suggestions/{sug.id}/approve", json={"approver": "홍\u200b길동"}, headers=hdr(csrf))
    assert r.status_code == 422 and r.json()["code"] == "approver_invalid", r.text[:200]
    with data() as s:
        assert s.get(Suggestion, sug.id).status == "candidate" and s.get(Suggestion, sug.id).approval is None
    ok = api.post(f"/api/v1/suggestions/{sug.id}/approve", json={"approver": "홍길동"}, headers=hdr(csrf))
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
