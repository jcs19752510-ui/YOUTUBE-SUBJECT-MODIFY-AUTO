"""6단계 독립 검증 2: 승인 게이트(HMAC·1회용·만료·plan_hash)와 D1(만료 기준 시각)."""
from __future__ import annotations

import hashlib
import hmac
import os
import stat
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from ytweb.core.errors import ProblemError
from ytweb.db.models import Approval, Batch, BatchItem, Suggestion, Video
from ytweb.domain.batches import apply_one, create_draft, execute_batch
from ytweb.domain.suggestions import (
    ApprovalInvalid, KEY_FILE, approve, check_approval, compute_mac, expire_stale_approvals, plan_hash_for,
)
from ytitle.updater import compute_plan_hash

from tests.verify_wb.vbh import Faulty, changes, life_ids, make_sug, queued


def _ap(db, sid):
    db.expire_all()
    return db.get(Suggestion, sid)


def test_tc_vb_050_approval_record_fields_ttl_and_key_file(seeded, db, env, clock):
    """인수3: 승인은 plan_hash·24시간 TTL·HMAC 에 묶인다. 키 파일은 0600, 32바이트 hex."""
    vid = life_ids(db, 1)[0]
    s = make_sug(db, env, clock(), vid)
    t0 = clock()
    approve(db, s.id, "  검수자  ", now=t0, env=env)
    db.commit()
    ap = _ap(db, s.id).approval
    assert ap.approver == "검수자" and ap.approved_at == t0 and ap.expires_at == t0 + timedelta(hours=24)
    assert len(ap.plan_hash) == 64 and ap.plan_hash == s.plan_hash and ap.used_at is None
    video = db.get(Video, vid)
    assert ap.plan_hash == compute_plan_hash(vid, s.id, video.title, s.title, video.snippet)  # 코어 규칙 그대로
    keyp = env.secrets_dir / KEY_FILE
    assert stat.S_IMODE(os.stat(keyp).st_mode) == 0o600
    key = bytes.fromhex(keyp.read_text().strip())
    assert len(key) == 32
    assert hmac.compare_digest(ap.mac, compute_mac(key, suggestion_id=s.id, video_id=vid, plan_hash=ap.plan_hash, approver="검수자", approved_at=t0, expires_at=ap.expires_at))


def test_tc_vb_051_plan_hash_changes_with_every_input(seeded, db, env, clock):
    """plan_hash 입력 필드(영상 ID·제안 ID·이전 제목·새 제목·snippet 전체) 중 하나라도 바뀌면 해시가 달라진다."""
    vid = life_ids(db, 1)[0]
    s = make_sug(db, env, clock(), vid)
    video = db.get(Video, vid)
    base = plan_hash_for(s, video)
    assert base == plan_hash_for(s, video)  # 결정적
    snip = dict(video.snippet)
    variants = {
        "description": {**snip, "description": snip["description"] + "."},
        "tags": {**snip, "tags": snip["tags"] + ["새태그"]},
        "categoryId": {**snip, "categoryId": "99"},
        "defaultLanguage": {**snip, "defaultLanguage": "en"},
        "title": {**snip, "title": snip["title"] + "x"},
    }
    seen = {base}
    for name, sn in variants.items():
        h = plan_hash_for(s, video, sn)
        assert h not in seen, f"snippet.{name} 변경이 plan_hash 에 반영되지 않음"
        seen.add(h)
    s.title = s.title + " 다름"
    assert plan_hash_for(s, video) not in seen              # 새 제목
    s.title = s.title[:-3]
    s2 = make_sug(db, env, clock(), vid, "냉장고 정리 쉽게 따라 하는 순서 천천히 알려드립니다 둘")
    assert plan_hash_for(s2, video) != base                  # 제안 ID/제목


@pytest.mark.parametrize("field, value", [
    ("approver", "다른사람"),
    ("plan_hash", "0" * 64),
    ("approved_at", None),   # +1초
    ("expires_at", None),    # +30일
])
def test_tc_vb_052_hmac_covers_every_field(seeded, db, env, clock, field, value):
    """DB 변조: 승인자·plan_hash·승인/만료 시각 어느 하나라도 바꾸면 approval_tampered. (만료 연장 공격 포함)"""
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    approve(db, s.id, "검수자", now=clock(), env=env)
    db.commit()
    ap = db.get(Approval, s.approval.id)
    if field == "approved_at":
        value = ap.approved_at + timedelta(seconds=1)
    elif field == "expires_at":
        value = ap.expires_at + timedelta(days=30)
    setattr(ap, field, value)
    db.commit()
    db.expire_all()
    s = db.get(Suggestion, s.id)
    with pytest.raises(ApprovalInvalid) as ei:
        check_approval(s, db.get(Video, s.video_id), env, clock())
    assert ei.value.code == "approval_tampered"
    # 배치 단계에서도 담을 수 없다
    with pytest.raises(ProblemError) as e2:
        create_draft(db, [s.id], None, now=clock(), env=env)
    assert e2.value.code == "batch_empty" and "인증값" in (e2.value.detail or "")
    assert db.execute(select(Batch)).first() is None


def test_tc_vb_053_forged_approval_with_valid_looking_mac_fails_without_key(seeded, db, env, clock):
    """키를 모르는 공격자가 approvals 행을 직접 삽입(mac 은 임의 sha256) → 무효."""
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    video = db.get(Video, s.video_id)
    ph = plan_hash_for(s, video)
    s.plan_hash = ph
    t = clock()
    forged = hashlib.sha256(f"{s.id}{ph}".encode()).hexdigest()
    s.approval = Approval(suggestion_id=s.id, plan_hash=ph, approver="공격자", approved_at=t, expires_at=t + timedelta(hours=24), mac=forged)
    s.status = "approved"
    db.commit()
    with pytest.raises(ApprovalInvalid) as ei:
        check_approval(s, video, env, clock())
    assert ei.value.code == "approval_tampered"


def test_tc_vb_054_key_missing_or_corrupt_is_fail_closed_and_not_recreated(seeded, db, env, clock):
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    approve(db, s.id, "검수자", now=clock(), env=env)
    db.commit()
    keyp = env.secrets_dir / KEY_FILE
    good = keyp.read_text()
    video = db.get(Video, s.video_id)
    keyp.unlink()
    with pytest.raises(ApprovalInvalid) as e1:
        check_approval(s, video, env, clock())
    assert e1.value.code == "approval_tampered" and not keyp.exists()  # 검증 경로는 키를 새로 만들지 않는다
    for bad in ("zz-not-hex", "ab" * 16, ""):
        keyp.write_text(bad)
        with pytest.raises(ApprovalInvalid) as e2:
            check_approval(s, video, env, clock())
        assert e2.value.code == "approval_tampered", bad
    keyp.write_text(("ab" * 32))  # 다른 키(길이는 맞음)
    with pytest.raises(ApprovalInvalid):
        check_approval(s, video, env, clock())
    keyp.write_text(good)
    check_approval(s, video, env, clock())  # 원래 키로 복구되면 다시 유효


def test_tc_vb_055_ttl_boundary_exact(seeded, db, env, clock):
    """만료 경계: 만료 시각 1초 전은 유효, 정확히 만료 시각이면 무효(>=). 목록 만료 처리(<=)와 같은 경계."""
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    t0 = clock()
    approve(db, s.id, "검수자", now=t0, env=env)
    db.commit()
    video = db.get(Video, s.video_id)
    exp = s.approval.expires_at
    check_approval(s, video, env, exp - timedelta(seconds=1))
    check_approval(s, video, env, exp - timedelta(microseconds=1))
    with pytest.raises(ApprovalInvalid) as ei:
        check_approval(s, video, env, exp)
    assert ei.value.code == "approval_expired"
    with pytest.raises(ApprovalInvalid):
        check_approval(s, video, env, exp + timedelta(seconds=1))
    assert expire_stale_approvals(db, exp - timedelta(seconds=1)) == 0 and s.status == "approved"
    assert expire_stale_approvals(db, exp) == 1 and s.status == "expired"


def test_tc_vb_056_expired_cannot_be_batched_and_reapproval_replaces(seeded, db, env, clock):
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    approve(db, s.id, "검수자", now=clock(), env=env)
    db.commit()
    clock.advance(hours=24)
    with pytest.raises(ProblemError) as ei:
        create_draft(db, [s.id], None, now=clock(), env=env)
    assert ei.value.code == "batch_empty"
    db.refresh(s)
    assert s.status == "expired"
    old_mac = s.approval.mac
    approve(db, s.id, "다른검수자", now=clock(), env=env)
    db.commit()
    db.refresh(s)
    assert s.status == "approved" and s.approval.mac != old_mac and s.approval.approver == "다른검수자" and s.approval.used_at is None
    assert db.execute(select(Approval).where(Approval.suggestion_id == s.id)).scalars().all().__len__() == 1
    b, pre = create_draft(db, [s.id], None, now=clock(), env=env)
    assert pre["item_count"] == 1


def test_tc_vb_057_approval_is_single_use(seeded, db, env, clock, gw):
    """승인은 1회용: 반영이 승인을 소진(used_at). 같은 승인으로 다시 쓰려 하면 approval_used."""
    b, sugs = queued(db, env, clock(), 1)
    item = b.items[0]
    out = apply_one(db, item.id, now=clock(), env=env, gateway=gw)
    assert out.status == "success"
    db.expire_all()
    s = db.get(Suggestion, sugs[0].id)
    assert s.approval.used_at is not None
    with pytest.raises(ApprovalInvalid) as ei:
        check_approval(s, db.get(Video, s.video_id), env, clock())
    assert ei.value.code == "approval_used"
    # 상태를 강제로 queued 로 되돌려 같은 승인으로 재시도해도 변경은 1건뿐
    s.status = "queued"
    db.execute(update(BatchItem).where(BatchItem.id == item.id).values(status="pending"))
    db.execute(update(Batch).where(Batch.id == b.id).values(status="queued"))
    db.commit()
    out2 = apply_one(db, item.id, now=clock(), env=env, gateway=gw)
    assert out2.status == "skipped" and out2.code == "approval_used"
    assert len(changes(db, s.video_id)) == 1


def test_tc_vb_058_edit_after_approval_invalidates(seeded, db, env, clock):
    """제목 수정 후에는 이전 승인으로 배치에 담을 수 없다."""
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    approve(db, s.id, "검수자", now=clock(), env=env)
    from ytweb.domain.suggestions import edit_title
    edit_title(db, s.id, s.title + " 개정", now=clock(), env=env)
    db.commit()
    with pytest.raises(ProblemError) as ei:
        create_draft(db, [s.id], None, now=clock(), env=env)
    assert ei.value.code == "batch_empty" and "승인된 제안이 아닙니다" in (ei.value.detail or "")


def test_tc_vb_059_video_changed_after_approval_blocks_apply_without_writing(seeded, db, env, clock):
    """영상(설명 등)이 승인 이후 바뀌면 video_changed — 유튜브 쓰기 호출 없음, 승인 소진 없음."""
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id
    v = db.get(Video, vid)
    v.snippet = {**v.snippet, "description": v.snippet["description"] + " 승인 뒤 수정된 설명"}
    db.commit()
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "plan_mismatch") or out.code == "video_changed"
    assert g.updates == 0 and changes(db, vid) == []
    db.expire_all()
    assert db.get(Suggestion, sugs[0].id).approval.used_at is None


def test_tc_vb_060_title_changed_on_youtube_after_approval(seeded, db, env, clock):
    """호출 직전 재조회에서 제목이 승인 때와 다르면 덮어쓰지 않는다(title_changed)."""
    b, sugs = queued(db, env, clock(), 1)
    vid = sugs[0].video_id
    g = Faulty(db, clock)
    g.on_read = lambda n, snap: {**snap, "title": "누군가 바꾼 제목"} if n == 1 else snap
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "title_changed")
    assert g.updates == 0 and changes(db, vid) == []
    assert db.get(Video, vid).title != sugs[0].title


def test_tc_vb_061_fresh_snippet_description_changed_detected_by_plan_hash(seeded, db, env, clock):
    """재조회한 snippet 이 승인 때와 다르면(유튜브 쪽에서 설명 변경) video_changed. DB 사본은 그대로여도 잡혀야 한다."""
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)
    g.on_read = lambda n, snap: {**snap, "description": snap["description"] + " 외부 수정"} if n == 1 else snap
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "video_changed")
    assert g.updates == 0 and changes(db) == []


def test_tc_vb_062_d1_expiry_judged_at_execute_time_multi_day_batch(seeded, db, factory, env, clock, gw):
    """D1(DEC-042 수용): 만료 기준은 배치 실행 확정 시각. 승인 후 23h 에 실행 확정한 배치의 둘째 날(승인 후 46h) 항목도 반영된다.
    반대로 승인 후 24h 에 실행을 확정하면 거부(precheck_stale)."""
    ids = life_ids(db, 4)
    sugs = [make_sug(db, env, clock(), v) for v in ids]
    for s in sugs:
        approve(db, s.id, "검수자", now=clock(), env=env)
    db.commit()
    from ytweb.core.settings_store import set_web_setting
    set_web_setting(db, "daily_apply_cap", 2, now=clock())
    clock.advance(hours=23)
    b, pre = create_draft(db, [s.id for s in sugs], None, now=clock(), env=env)
    b, job = execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    db.commit()
    days = sorted({i.scheduled_date for i in b.items})
    assert len(days) == 2
    clock.advance(hours=23)  # 승인 후 46h(TTL 24h 초과)지만 실행 확정은 승인 후 23h
    from ytweb.domain.batches import run_due_items
    # 두 번째 날 분량이 도래 — 승인 TTL 이 실제 반영 시각에 엄격 적용되면 건너뛰어지겠지만 D1 은 허용
    db.commit()
    res = run_due_items(factory, clock(), env)
    assert (res.success, res.skipped, res.failed) == (2, 0, 0), res   # 하루 상한 2건(놓친 예약도 몰아서 실행하지 않음)
    clock.advance(hours=24)       # 승인 후 70h
    res2 = run_due_items(factory, clock(), env)
    assert (res2.success, res2.skipped, res2.failed) == (2, 0, 0), res2
    # 승인 후 24h 정각에 실행 확정은 거부
    s5 = make_sug(db, env, clock(), life_ids(db, 1, skip=10)[0])
    approve(db, s5.id, "검수자", now=clock(), env=env)
    b5, pre5 = create_draft(db, [s5.id], None, now=clock(), env=env)
    db.commit()
    clock.advance(hours=24)
    with pytest.raises(ProblemError) as ei:
        execute_batch(db, b5.id, pre5["confirm_text"], now=clock(), env=env)
    assert ei.value.code == "precheck_stale" and "expired" in (ei.value.detail or "")
    db.rollback()
    # 경계: 같은 승인이라도 만료 1초 전에 확정하면 통과
    clock.advance(hours=-24)
    s6 = make_sug(db, env, clock(), life_ids(db, 1, skip=11)[0])
    approve(db, s6.id, "검수자", now=clock(), env=env)
    b6, pre6 = create_draft(db, [s6.id], None, now=clock(), env=env)
    db.commit()
    clock.advance(hours=24, seconds=-1)
    b6, _ = execute_batch(db, b6.id, pre6["confirm_text"], now=clock(), env=env)
    assert b6.status == "queued"


def test_tc_vb_063_approve_revalidates_at_approval_time(seeded, db, env, clock):
    """승인 시점 재검증: 후보 생성 뒤 영상 설명이 바뀌어 일치율이 무너지면 승인 거부."""
    vid = life_ids(db, 1)[0]
    s = make_sug(db, env, clock(), vid)
    assert s.validation_result == "pass"
    v = db.get(Video, vid)
    v.description_excerpt = "완전히 다른 주제의 긴 설명입니다 오늘의 날씨와 뉴스."
    db.flush()
    with pytest.raises(ProblemError) as ei:
        approve(db, s.id, "검수자", now=clock(), env=env)
    assert (ei.value.status, ei.value.code) == (409, "suggestion_blocked")
    assert s.approval is None


def test_tc_vb_064_approve_rejects_inconsistent_video_row(seeded, db, env, clock):
    vid = life_ids(db, 1)[0]
    s = make_sug(db, env, clock(), vid)
    v = db.get(Video, vid)
    v.snippet = {**v.snippet, "title": "DB 불일치 제목"}
    db.flush()
    with pytest.raises(ProblemError) as ei:
        approve(db, s.id, "검수자", now=clock(), env=env)
    assert ei.value.code == "video_inconsistent"


def test_tc_vb_065_blocking_suggestion_in_queue_is_never_applied(seeded, db, env, clock):
    """방어 심층: 배치에 담긴 뒤 제안이 차단 판정으로 바뀐(DB 조작) 경우에도 반영 단계에서 막는다."""
    b, sugs = queued(db, env, clock(), 1)
    sugs[0].validation_result = "block"
    db.commit()
    g = Faulty(db, clock)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert (out.status, out.code) == ("skipped", "suggestion_blocked") and g.updates == 0 and g.reads == 0
