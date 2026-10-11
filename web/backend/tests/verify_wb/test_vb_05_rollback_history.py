"""6단계 독립 검증 5: 롤백(W-011)과 변경 이력(W-012). 인수6: 영상 ID 직접 입력·이후 변경 없음일 때만, 백업 snippet 전체 복원 + 재조회 검증."""
from __future__ import annotations

import copy
from datetime import timedelta

import pytest
from sqlalchemy import select

from ytweb.core.errors import ProblemError
from ytweb.db.models import AuditLog, Change, Suggestion, Video
from ytweb.domain.batches import apply_one
from ytweb.domain.changes import list_changes, rollback_change
from ytweb.youtube.base import GatewayError

from tests.verify_wb.vbh import Faulty, add_change, changes, life_ids, queued, quota_units, snippet_of, fill_quota


def _applied(db, env, clock, gw, skip=0, n=1):
    b, sugs = queued(db, env, clock(), n, skip=skip)
    out = []
    for it, s in zip(b.items, sugs):
        r = apply_one(db, it.id, now=clock(), env=env, gateway=gw)
        assert r.status == "success", r
        out.append((db.get(Change, r.change_id), s))
    return out


def _rb(db, env, clock, gw, change, typed=None, approver="롤백담당"):
    return rollback_change(db, change.id, typed if typed is not None else change.video_id, approver, now=clock(), env=env, gateway=gw)


def test_tc_vb_160_rollback_restores_full_backup_snippet_and_verifies(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    vid = c.video_id
    backup = copy.deepcopy(c.backup_snippet)
    assert snippet_of(db, vid)["title"] == s.title
    clock.advance(minutes=5)
    rb = _rb(db, env, clock, gw, c)
    db.commit()
    assert snippet_of(db, vid) == backup                            # snippet 전체가 원래대로
    assert rb.change_type == "rollback" and rb.result == "success" and rb.error_code is None and rb.mode == "demo"
    assert rb.previous_title == s.title and rb.new_title == backup["title"] and rb.approver == "롤백담당"
    assert rb.verify_result["ok"] is True and rb.verified_at == clock() and rb.reason.endswith(f"#{c.id}")
    db.expire_all()
    assert db.get(Suggestion, s.id).status == "rolled_back"
    assert db.get(Video, vid).title == backup["title"]
    assert db.execute(select(AuditLog).where(AuditLog.action == "change.rollback")).scalars().one().detail["target_change"] == c.id


def test_tc_vb_161_rollback_recovers_description_lost_by_bad_update(seeded, db, env, clock):
    """인수5/6: 반영 중 설명이 사라진(verify_failed) 경우 롤백이 설명까지 되살린다."""
    b, sugs = queued(db, env, clock(), 1)
    g = Faulty(db, clock)
    g.on_update = lambda n, body: {**body, "snippet": {k: v for k, v in body["snippet"].items() if k not in ("description", "tags")}}
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert out.code == "verify_failed"
    c = db.get(Change, out.change_id)
    assert "description" not in snippet_of(db, c.video_id)
    from ytweb.youtube.mock import MockYouTubeGateway
    rb = _rb(db, env, clock, MockYouTubeGateway(db, clock), c)
    after = snippet_of(db, c.video_id)
    assert after == c.backup_snippet and after["description"] and after["tags"] and rb.verify_result["ok"] is True


@pytest.mark.parametrize("typed", ["", " ", "DEMOVID0001", "wrongVid000", "demoVid0001 ", " demoVid0001", "demoVid000", "demoVid00011", "demoVid0001\n"])
def test_tc_vb_162_typed_video_id_must_match_exactly(seeded, db, env, clock, gw, typed):
    [(c, s)] = _applied(db, env, clock, gw)
    c_vid = c.video_id
    # 실제 영상 ID 와 다른 입력은 모두 거부(우연히 같은 값이면 건너뜀)
    if typed == c_vid:
        pytest.skip("same")
    before_units = quota_units(db)
    g = Faulty(db, clock)
    with pytest.raises(ProblemError) as e:
        _rb(db, env, clock, g, c, typed=typed)
    assert (e.value.status, e.value.code) == (422, "typed_video_id_mismatch")
    assert g.reads == g.updates == 0 and quota_units(db) == before_units and len(changes(db)) == 1
    assert snippet_of(db, c_vid)["title"] == s.title


def test_tc_vb_163_only_successful_apply_can_be_rolled_back(seeded, db, env, clock, gw):
    vid = life_ids(db, 1)[0]
    rows = {r: add_change(db, vid, clock() - timedelta(days=30 + i), result=r)[0] for i, r in enumerate(("failed", "aborted", "planned"))}
    db.commit()
    for r, ch in rows.items():
        with pytest.raises(ProblemError) as e:
            _rb(db, env, clock, gw, ch)
        assert (e.value.status, e.value.code) == (409, "not_rollbackable"), r
    with pytest.raises(ProblemError) as e404:
        rollback_change(db, 999999, vid, "x", now=clock(), env=env, gateway=gw)
    assert e404.value.status == 404


def test_tc_vb_164_rollback_of_rollback_row_is_rejected(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    rb = _rb(db, env, clock, gw, c)
    db.commit()
    with pytest.raises(ProblemError) as e:
        _rb(db, env, clock, gw, rb)
    assert e.value.code == "not_rollbackable"


def test_tc_vb_165_later_change_blocks_rollback_and_double_rollback(seeded, db, env_free, clock, gw):
    """롤백 이후 변경 거부: 그 변경 이후 같은 영상의 다른 변경(success/planned)이 있으면 거부. 이중 롤백도 거부."""
    env = env_free
    [(c1, s1)] = _applied(db, env, clock, gw)
    vid = c1.video_id
    clock.advance(hours=73)
    # 같은 영상에 두 번째 제안을 반영
    from tests.verify_wb.vbh import make_sug
    from ytweb.domain.batches import create_draft, execute_batch
    from ytweb.domain.suggestions import approve
    s2 = make_sug(db, env, clock(), vid, "냉장고 정리 쉽게 따라 하는 순서 천천히 알려드립니다 후속")
    approve(db, s2.id, "검수자", now=clock(), env=env)
    b2, pre2 = create_draft(db, [s2.id], None, now=clock(), env=env)
    b2, _ = execute_batch(db, b2.id, pre2["confirm_text"], now=clock(), env=env)
    r2 = apply_one(db, b2.items[0].id, now=clock(), env=env, gateway=gw)
    assert r2.status == "success"
    c2 = db.get(Change, r2.change_id)
    g = Faulty(db, clock)
    with pytest.raises(ProblemError) as e:
        _rb(db, env, clock, g, c1)
    assert (e.value.status, e.value.code) == (409, "later_change_exists") and f"#{c2.id}" in e.value.title
    assert g.reads == g.updates == 0
    _rb(db, env, clock, gw, c2)             # 최신 변경은 롤백 가능
    db.commit()
    assert snippet_of(db, vid)["title"] == c2.previous_title
    with pytest.raises(ProblemError) as e2:       # 같은 변경 이중 롤백
        _rb(db, env, clock, gw, c2)
    assert e2.value.code == "later_change_exists"
    with pytest.raises(ProblemError) as e3:       # 이미 롤백된 최신 이전 변경도 이후(롤백 포함) 변경이 있어 불가
        _rb(db, env, clock, gw, c1)
    assert e3.value.code == "later_change_exists"
    assert len([c for c in changes(db, vid) if c.change_type == "rollback"]) == 1


def test_tc_vb_166_failed_or_aborted_later_change_does_not_block(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    add_change(db, c.video_id, clock() + timedelta(minutes=1), result="failed")
    add_change(db, c.video_id, clock() + timedelta(minutes=2), result="aborted")
    db.commit()
    rb = _rb(db, env, clock, gw, c)
    assert rb.result == "success"


def test_tc_vb_167_planned_later_change_blocks_rollback(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    db.add(Change(video_id=c.video_id, change_type="apply", previous_title="a", new_title="b", result="planned", mode="demo", created_at=clock() + timedelta(minutes=1)))
    db.commit()
    with pytest.raises(ProblemError) as e:
        _rb(db, env, clock, gw, c)
    assert e.value.code == "later_change_exists"


def test_tc_vb_168_rollback_not_blocked_by_72h_interval_or_daily_cap(seeded, db, env, clock, gw):
    """사고 복구가 막히지 않도록 교체 한도는 롤백에 적용하지 않는다(쿼터는 쓴다)."""
    from tests.verify_wb.vbh import set_cap
    set_cap(db, clock, 1)
    [(c, s)] = _applied(db, env, clock, gw)         # 오늘 상한 1건 소진, 직전 변경 직후
    rb = _rb(db, env, clock, gw, c)
    assert rb.result == "success"
    assert quota_units(db) == 104                   # 반영 52 + 롤백 52


@pytest.mark.parametrize("remaining, ok", [(51, False), (52, True), (0, False)])
def test_tc_vb_169_rollback_requires_quota_and_reserves_before_calls(seeded, db, env, clock, gw, remaining, ok):
    [(c, s)] = _applied(db, env, clock, gw)
    fill_quota(db, clock(), env.policy.daily_limit_units - quota_units(db) - remaining)
    g = Faulty(db, clock)
    units = quota_units(db)
    if ok:
        assert _rb(db, env, clock, g, c).result == "success"
        return
    with pytest.raises(ProblemError) as e:
        _rb(db, env, clock, g, c)
    assert (e.value.status, e.value.code) == (429, "quota_exhausted")
    assert g.reads == g.updates == 0 and quota_units(db) == units and snippet_of(db, c.video_id)["title"] == s.title
    assert not [x for x in changes(db) if x.change_type == "rollback"]


def test_tc_vb_170_backup_integrity_checks(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    good = copy.deepcopy(c.backup_snippet)
    for mutate in (lambda b: {**b, "title": "다른 제목"}, lambda b: {k: v for k, v in b.items() if k != "categoryId"}, lambda b: {**b, "categoryId": ""}):
        c.backup_snippet = mutate(good)
        db.flush()
        g = Faulty(db, clock)
        with pytest.raises(ProblemError) as e:
            _rb(db, env, clock, g, c)
        assert e.value.code == "backup_invalid" and g.updates == 0
    c.backup_snippet = None
    db.flush()
    with pytest.raises(ProblemError) as e2:
        _rb(db, env, clock, gw, c)
    assert e2.value.code == "backup_invalid"
    assert snippet_of(db, c.video_id)["title"] == s.title


def test_tc_vb_171_backup_with_forbidden_title_not_restored(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    bad = {**c.backup_snippet, "title": "<script>x</script>"}
    c.backup_snippet, c.previous_title = bad, bad["title"]
    db.flush()
    with pytest.raises(ProblemError) as e:
        _rb(db, env, clock, gw, c)
    assert e.value.code == "backup_invalid"


def test_tc_vb_172_already_restored_externally(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    v = db.get(Video, c.video_id)
    v.title = c.previous_title
    v.snippet = {**v.snippet, "title": c.previous_title}
    db.commit()
    g = Faulty(db, clock)
    with pytest.raises(ProblemError) as e:
        _rb(db, env, clock, g, c)
    assert (e.value.status, e.value.code) == (409, "already_restored") and g.updates == 0


def test_tc_vb_173_rollback_gateway_failures(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    g = Faulty(db, clock)
    g.on_read = lambda n, snap: (_ for _ in ()).throw(GatewayError("net", "x"))
    with pytest.raises(ProblemError) as e:
        _rb(db, env, clock, g, c)
    assert e.value.status == 502 and not [x for x in changes(db) if x.change_type == "rollback"]
    # 결과 불명 → planned 로 남기고 후속 롤백/반영 차단
    g2 = Faulty(db, clock)
    g2.update_snippet = lambda vid, body: (_ for _ in ()).throw(GatewayError("timeout", "응답 없음", definite=False))   # type: ignore[method-assign]
    with pytest.raises(ProblemError) as e2:
        _rb(db, env, clock, g2, c)
    assert e2.value.status == 502
    rbs = [x for x in changes(db) if x.change_type == "rollback"]
    assert len(rbs) == 1 and rbs[0].result == "planned"
    with pytest.raises(ProblemError) as e3:
        _rb(db, env, clock, gw, c)
    assert e3.value.code == "later_change_exists"       # planned 롤백이 있으면 중복 롤백 불가


def test_tc_vb_174_rollback_update_definite_failure_marks_failed(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    g = Faulty(db, clock)
    g.on_update = lambda n, body: (_ for _ in ()).throw(GatewayError("forbidden", "권한", definite=True))
    with pytest.raises(ProblemError):
        _rb(db, env, clock, g, c)
    rb = [x for x in changes(db) if x.change_type == "rollback"][0]
    assert rb.result == "failed" and rb.error_code == "forbidden"
    assert _rb(db, env, clock, gw, c).result == "success"      # 실패한 시도는 이후 재시도를 막지 않는다


def test_tc_vb_175_rollback_verification_failure_flagged(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    g = Faulty(db, clock)
    g.on_update = lambda n, body: {**body, "snippet": {k: v for k, v in body["snippet"].items() if k != "description"}}
    rb = _rb(db, env, clock, g, c)
    assert rb.result == "success" and rb.error_code == "verify_failed" and rb.verify_result["ok"] is False


def test_tc_vb_176_changed_since_backup_is_reported(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    v = db.get(Video, c.video_id)
    v.snippet = {**v.snippet, "description": "반영 뒤 사람이 고친 설명"}
    db.commit()
    rb = _rb(db, env, clock, gw, c)
    assert "description" in rb.verify_result["changed_since_backup"]
    assert snippet_of(db, c.video_id)["description"] == c.backup_snippet["description"]


def test_tc_vb_177_rollback_approver_validated(seeded, db, env, clock, gw):
    [(c, s)] = _applied(db, env, clock, gw)
    for name in ("", "  ", "x" * 41, "a\nb"):
        with pytest.raises(ProblemError) as e:
            _rb(db, env, clock, gw, c, approver=name)
        assert e.value.status == 422
    assert len([x for x in changes(db) if x.change_type == "rollback"]) == 0


def test_tc_vb_178_after_rollback_next_change_is_governed_by_interval_count(seeded, db, env_free, clock, gw):
    """롤백도 '변경'으로 간격/횟수에 산입된다(안전한 쪽). 롤백 직후 재변경은 72시간 간격에 막힌다."""
    env = env_free
    [(c, s)] = _applied(db, env, clock, gw)
    _rb(db, env, clock, gw, c)
    from ytweb.domain.limits_quota import check_video_limits
    rep = check_video_limits(db, c.video_id, clock(), env.policy, 10)
    assert {x.code: x.passed for x in rep.checks}["INTERVAL"] is False
    assert rep.checks[1].message.startswith("이 영상의 변경 2회")
    assert {x.code: x.passed for x in check_video_limits(db, c.video_id, clock() + timedelta(hours=72), env.policy, 10).checks}["INTERVAL"] is True


# ───────────────────────── 이력(W-012) ─────────────────────────

def test_tc_vb_180_history_listing_filters_paging_and_rollbackable(seeded, db, env, clock, gw):
    res = _applied(db, env, clock, gw, n=3)
    (c1, _), (c2, _), (c3, _) = res
    _rb(db, env, clock, gw, c3)
    db.commit()
    pairs, rb, total = list_changes(db, video_id=None, batch_id=None, result=None, page=1, page_size=50)
    assert total == 4 and [p[0].id for p in pairs] == sorted((p[0].id for p in pairs), reverse=True)
    assert rb[c1.id] is True and rb[c2.id] is True and rb[c3.id] is False        # 롤백된 변경은 더 롤백 불가
    assert all(isinstance(t, str) for _, t in pairs)
    only_vid, _, n = list_changes(db, video_id=c1.video_id, batch_id=None, result=None, page=1, page_size=50)
    assert n == 1 and only_vid[0][0].id == c1.id
    _, _, n_b = list_changes(db, video_id=None, batch_id=c1.batch_id, result="success", page=1, page_size=50)
    assert n_b == 3
    _, _, n_none = list_changes(db, video_id=None, batch_id=None, result="planned", page=1, page_size=50)
    assert n_none == 0
    p2, _, t = list_changes(db, video_id=None, batch_id=None, result=None, page=2, page_size=3)
    assert len(p2) == 1 and t == 4
    p0, _, _ = list_changes(db, video_id=None, batch_id=None, result=None, page=-5, page_size=10_000)   # 범위 보정(page≥1, size≤200)
    assert len(p0) == 4


def test_tc_vb_181_history_records_who_what_which_candidate(seeded, db, env, clock, gw):
    """W-012: 언제·무엇을·어떤 AI 후보로·누가 승인."""
    [(c, s)] = _applied(db, env, clock, gw)
    db.expire_all()
    s = db.get(Suggestion, s.id)
    assert c.suggestion_id == s.id and s.source == "ai:mock" and s.ai_run_id is not None
    assert c.approver == "검수자" and c.approved_at is not None and c.applied_at is not None and c.new_title == s.title
