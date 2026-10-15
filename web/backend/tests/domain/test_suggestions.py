"""제안 생성·검증 연동·수정·승인·반려·만료·변조 탐지(018-040)."""
from __future__ import annotations

import json
import stat
from datetime import timedelta

import pytest
from sqlalchemy import select

from ytweb.ai.base import SuggestionDraft, TitleSuggestionError
from ytweb.core.errors import ProblemError
from ytweb.db.models import AiRun, Approval, AuditLog, Suggestion, Video
from ytweb.domain.suggestions import (
    ApprovalInvalid, approve, check_approval, edit_title, expire_stale_approvals, generate_for_video, list_suggestions, plan_hash_for, reject,
)
from youtube_title.updater import compute_plan_hash

from tests.domain.helpers import SUGGESTER, eligible_video_ids, suggest


def _gen(db, env, clock, vid, count=5):
    return generate_for_video(db, vid, count=count, tone="friendly", now=clock(), env=env, suggester=SUGGESTER)


def _by(sugs, result):
    return next(s for s in sugs if s.validation_result == result)


def _problem(fn, *a, **kw) -> ProblemError:
    with pytest.raises(ProblemError) as e:
        fn(*a, **kw)
    return e.value


def test_tc_wb_018_generate_validates_and_records_ai_run_without_raw_text(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    sugs = _gen(seeded, env, clock, vid, 3)
    assert len(sugs) == 3 and [s.validation_result for s in sugs][:2] == ["pass", "pass"]
    assert all(s.source == "ai:mock" and s.ai_run_id and s.dictionary_hash for s in sugs)
    assert all(s.status == ("blocked" if s.validation_result == "block" else "candidate") for s in sugs)
    run = seeded.execute(select(AiRun)).scalar_one()
    assert run.status == "ok" and len(run.prompt_hash) == 64 and run.input_chars > 0 and run.provider == "mock"
    blob = json.dumps(run.params, ensure_ascii=False)
    assert not any(s.title in blob for s in sugs) and run.prompt_hash not in sugs[0].title  # 원문 대신 해시·건수만
    audit = seeded.execute(select(AuditLog).where(AuditLog.action == "suggestion.generate")).scalar_one()
    assert audit.target_id == vid and audit.detail["created"] == 3


def test_tc_wb_019_generate_twice_reuses_without_duplicates(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    first = _gen(seeded, env, clock, vid, 3)
    second = _gen(seeded, env, clock, vid, 3)
    assert [s.id for s in first] == [s.id for s in second]
    assert len(seeded.execute(select(Suggestion).where(Suggestion.video_id == vid)).scalars().all()) == 3


def test_tc_wb_020_generate_refuses_excluded_and_unknown_video(seeded, env, clock):
    excluded = next(v.video_id for v in seeded.execute(select(Video)).scalars() if v.exclusion_reasons)
    e = _problem(_gen, seeded, env, clock, excluded)
    assert (e.status, e.code) == (409, "video_excluded") and e.detail and e.hint
    assert _problem(_gen, seeded, env, clock, "zzzzzzzzzzz").status == 404


@pytest.mark.parametrize("count", [0, 6, -1, True, "3"])
def test_tc_wb_021_generate_rejects_bad_count(seeded, env, clock, count):
    e = _problem(generate_for_video, seeded, eligible_video_ids(seeded, 1)[0], count=count, tone="", now=clock(), env=env, suggester=SUGGESTER)
    assert (e.status, e.code) == (422, "count_invalid")


def test_tc_wb_022_ai_failure_is_reported_and_recorded(seeded, env, clock):
    class Boom:
        name, model = "boom", None

        def suggest(self, brief, *, count, tone):
            raise TitleSuggestionError("timeout")

    vid = eligible_video_ids(seeded, 1)[0]
    e = _problem(generate_for_video, seeded, vid, count=3, tone="", now=clock(), env=env, suggester=Boom())
    assert (e.status, e.code) == (502, "ai_unavailable") and "직접" in e.hint
    seeded.rollback()  # 요청이 실패로 끝나도 실패 기록은 이미 확정되어 있어야 한다
    run = seeded.execute(select(AiRun)).scalar_one()
    assert run.status == "failed" and run.error == "timeout"
    assert seeded.execute(select(Suggestion)).first() is None


def test_tc_wb_023_ai_returns_nothing_usable(seeded, env, clock):
    class Junk:
        name, model = "junk", None

        def suggest(self, brief, *, count, tone):
            return [SuggestionDraft("  ", "e", None), SuggestionDraft("전화 010-1111-2222", "e", None)]

    e = _problem(generate_for_video, seeded, eligible_video_ids(seeded, 1)[0], count=3, tone="", now=clock(), env=env, suggester=Junk())
    assert (e.status, e.code) == (502, "ai_no_candidates")
    seeded.rollback()
    assert seeded.execute(select(AiRun)).scalar_one().error == "no_valid_candidates"


def test_tc_wb_024_blocked_candidate_cannot_be_approved(seeded, env, clock):
    sugs = _gen(seeded, env, clock, eligible_video_ids(seeded, 1)[0])
    blocked = _by(sugs, "block")
    assert blocked.status == "blocked"
    e = _problem(approve, seeded, blocked.id, "홍길동", now=clock(), env=env)
    assert (e.status, e.code) == (409, "suggestion_blocked") and e.detail
    assert seeded.execute(select(Approval)).first() is None


def test_tc_wb_025_warning_candidate_can_be_approved_in_life_topic(seeded, env, clock):
    sugs = _gen(seeded, env, clock, eligible_video_ids(seeded, 5)[4], 5)
    warn = _by(sugs, "warn") if any(s.validation_result == "warn" for s in sugs) else None
    if warn is None:  # 이 영상의 나쁜 후보가 차단형이면 경고형이 나오는 다른 영상을 찾는다
        for vid in eligible_video_ids(seeded, 20):
            sugs = _gen(seeded, env, clock, vid, 5)
            if any(s.validation_result == "warn" for s in sugs):
                warn = _by(sugs, "warn")
                break
    assert warn is not None and warn.topic == "life" and not warn.strict_mode
    assert approve(seeded, warn.id, "홍길동", now=clock(), env=env).status == "approved"


def test_tc_wb_026_strict_mode_turns_warnings_into_blocks(seeded, env, clock):
    health = next(v.video_id for v in seeded.execute(select(Video)).scalars() if v.snippet["tags"][-1] == "건강" and not v.exclusion_reasons)
    sugs = _gen(seeded, env, clock, health, 5)
    assert all(s.strict_mode and s.topic == "health" for s in sugs)
    excl = next(s for s in sugs if any(r["code"] == "EXCLAMATION" for r in s.validation_reasons))
    assert excl.validation_result == "block" and "엄격 모드" in next(r["message"] for r in excl.validation_reasons if r["code"] == "EXCLAMATION")
    assert _problem(approve, seeded, excl.id, "홍길동", now=clock(), env=env).code == "suggestion_blocked"
    assert not any(s.validation_result == "warn" for s in sugs)


def test_tc_wb_027_approval_binds_plan_hash_ttl_and_hmac(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    video = seeded.get(Video, sug.video_id)
    out = approve(seeded, sug.id, "  홍길동 ", now=clock(), env=env)
    ap = out.approval
    assert out.status == "approved" and ap.approver == "홍길동"
    assert out.plan_hash == ap.plan_hash == compute_plan_hash(video.video_id, sug.id, video.title, sug.title, video.snippet)
    assert ap.expires_at - ap.approved_at == timedelta(hours=env.policy.approval_ttl_hours) and len(ap.mac) == 64
    key_file = env.secrets_dir / "approval_hmac.key"
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600 and len(bytes.fromhex(key_file.read_text())) == 32
    check_approval(sug, video, env, clock())  # 예외 없음
    entry = seeded.execute(select(AuditLog).where(AuditLog.action == "suggestion.approve")).scalar_one()
    assert entry.detail["approver"] == "홍길동" and "mac" not in json.dumps(entry.detail)


def test_tc_wb_028_approve_refuses_excluded_video(seeded, env, clock):
    video = next(v for v in seeded.execute(select(Video)).scalars() if v.exclusion_reasons)
    sug = Suggestion(video_id=video.video_id, title="새 제목", evidence="e", source="ai:mock", topic="life", validation_result="pass", status="candidate", created_at=clock(), updated_at=clock())
    seeded.add(sug)
    seeded.flush()
    assert _problem(approve, seeded, sug.id, "홍길동", now=clock(), env=env).code == "video_excluded"


def test_tc_wb_029_approve_twice_and_unknown(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    approve(seeded, sug.id, "홍길동", now=clock(), env=env)
    assert _problem(approve, seeded, sug.id, "홍길동", now=clock(), env=env).code == "suggestion_state"
    assert _problem(approve, seeded, 999999, "홍길동", now=clock(), env=env).status == 404


@pytest.mark.parametrize("name", ["", "   ", "가" * 41, "이름\n줄바꿈", "이‮름", None])
def test_tc_wb_030_approver_name_is_validated(seeded, env, clock, name):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    e = _problem(approve, seeded, sug.id, name, now=clock(), env=env)
    assert e.status == 422 and e.code in ("approver_required", "approver_invalid")


def test_tc_wb_031_edit_invalidates_approval_and_revalidates(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    approve(seeded, sug.id, "홍길동", now=clock(), env=env)
    old_ap = seeded.execute(select(Approval)).scalar_one()
    out = edit_title(seeded, sug.id, f"{sug.title} 수정", now=clock(), env=env)
    assert out.status in ("candidate", "blocked") and out.approval is None and out.plan_hash is None
    assert seeded.execute(select(Approval)).first() is None and old_ap.id
    assert out.title.endswith("수정")
    entry = seeded.execute(select(AuditLog).where(AuditLog.action == "suggestion.edit")).scalar_one()
    assert entry.detail["approval_invalidated"] is True


def test_tc_wb_032_edit_to_forbidden_title_becomes_blocked_and_edge_cases(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    s1, s2 = suggest(seeded, env, clock(), vid, 2)
    out = edit_title(seeded, s1.id, "무조건 완치 기적의 100% 비법", now=clock(), env=env)
    assert out.validation_result == "block" and out.status == "blocked"
    assert _problem(edit_title, seeded, s1.id, s2.title, now=clock(), env=env).code == "duplicate_suggestion"
    assert _problem(edit_title, seeded, s1.id, " \n ", now=clock(), env=env).code == "title_empty"
    assert _problem(edit_title, seeded, s1.id, "가" * 301, now=clock(), env=env).code == "title_too_long"
    assert edit_title(seeded, s2.id, s2.title, now=clock(), env=env).status == "candidate"  # 같은 제목이면 변화 없음
    assert edit_title(seeded, s1.id, "제어\x00문자\n포함 제목", now=clock(), env=env).title == "제어문자 포함 제목"


def test_tc_wb_033_edit_and_reject_not_allowed_for_queued_or_applied(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    for status in ("queued", "applied", "rolled_back"):
        sug.status = status
        seeded.flush()
        assert _problem(edit_title, seeded, sug.id, "다른 제목", now=clock(), env=env).code == "suggestion_state"
        assert _problem(reject, seeded, sug.id, now=clock()).code == "suggestion_state"


def test_tc_wb_034_reject_drops_approval(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    approve(seeded, sug.id, "홍길동", now=clock(), env=env)
    out = reject(seeded, sug.id, now=clock())
    assert out.status == "rejected" and out.approval is None and seeded.execute(select(Approval)).first() is None
    assert _problem(approve, seeded, sug.id, "홍길동", now=clock(), env=env).code == "suggestion_state"


def test_tc_wb_035_approval_expires_after_ttl_and_can_be_renewed(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    video = seeded.get(Video, sug.video_id)
    t0 = clock()
    approve(seeded, sug.id, "홍길동", now=t0, env=env)
    ttl = timedelta(hours=env.policy.approval_ttl_hours)
    assert expire_stale_approvals(seeded, t0 + ttl - timedelta(seconds=1)) == 0
    check_approval(sug, video, env, t0 + ttl - timedelta(seconds=1))
    with pytest.raises(ApprovalInvalid) as e:
        check_approval(sug, video, env, t0 + ttl)  # 경계: 만료 시각과 같으면 만료
    assert e.value.code == "approval_expired"
    assert expire_stale_approvals(seeded, t0 + ttl) == 1 and sug.status == "expired"
    renewed = approve(seeded, sug.id, "김철수", now=t0 + ttl, env=env)
    assert renewed.status == "approved" and renewed.approval.approver == "김철수" and len(seeded.execute(select(Approval)).scalars().all()) == 1


def test_tc_wb_036_hmac_detects_tampering(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    video = seeded.get(Video, sug.video_id)
    approve(seeded, sug.id, "홍길동", now=clock(), env=env)
    for field, value in (("expires_at", clock() + timedelta(days=30)), ("approver", "다른사람"), ("plan_hash", "0" * 64)):
        ap = sug.approval
        original = getattr(ap, field)
        setattr(ap, field, value)
        seeded.flush()
        with pytest.raises(ApprovalInvalid) as e:
            check_approval(sug, video, env, clock())
        assert e.value.code == "approval_tampered", field
        setattr(ap, field, original)
    check_approval(sug, video, env, clock())
    (env.secrets_dir / "approval_hmac.key").unlink()  # 키가 없으면 어떤 승인도 믿지 않는다(키를 새로 만들지도 않는다)
    with pytest.raises(ApprovalInvalid) as e:
        check_approval(sug, video, env, clock())
    assert e.value.code == "approval_tampered" and not (env.secrets_dir / "approval_hmac.key").exists()


def test_tc_wb_037_video_change_invalidates_approval(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    video = seeded.get(Video, sug.video_id)
    approve(seeded, sug.id, "홍길동", now=clock(), env=env)
    video.snippet = {**video.snippet, "description": "설명이 바뀜"}
    seeded.flush()
    with pytest.raises(ApprovalInvalid) as e:
        check_approval(sug, video, env, clock())
    assert e.value.code == "plan_mismatch"
    assert plan_hash_for(sug, video) != sug.plan_hash


def test_tc_wb_038_approval_used_and_missing(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    video = seeded.get(Video, sug.video_id)
    with pytest.raises(ApprovalInvalid) as e:
        check_approval(sug, video, env, clock())
    assert e.value.code == "approval_missing"
    approve(seeded, sug.id, "홍길동", now=clock(), env=env)
    sug.approval.used_at = clock()
    with pytest.raises(ApprovalInvalid) as e:
        check_approval(sug, video, env, clock())
    assert e.value.code == "approval_used"


def test_tc_wb_039_approve_rechecks_validation_with_current_dictionary(seeded, env, clock):
    sug = suggest(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])[0]
    sug.title = "무조건 되는 정리법"  # 생성 이후 DB 가 바뀌었다고 가정(사전은 이 제목을 차단)
    seeded.flush()
    e = _problem(approve, seeded, sug.id, "홍길동", now=clock(), env=env)
    assert e.code == "suggestion_blocked" and "다시 검증" in e.title


def test_tc_wb_040_list_suggestions_filters_and_paging(seeded, env, clock):
    for vid in eligible_video_ids(seeded, 3):
        _gen(seeded, env, clock, vid, 5)
    rows, total = list_suggestions(seeded, video_id=None, status=None, result=None, page=1, page_size=4, now=clock())
    assert total == 15 and len(rows) == 4 and rows[0].id > rows[-1].id
    blocked, n = list_suggestions(seeded, video_id=None, status="blocked", result="block", page=1, page_size=200, now=clock())
    assert n == len(blocked) and all(s.status == "blocked" for s in blocked)
    one, n1 = list_suggestions(seeded, video_id=rows[0].video_id, status=None, result=None, page=1, page_size=999, now=clock())
    assert n1 == 5 and all(s.video_id == rows[0].video_id for s in one)
