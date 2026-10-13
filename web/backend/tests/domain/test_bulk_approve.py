"""일괄 승인·영상 찾기(TC-BA-001~). 계약: docs/harness/bulk-approve/CONTRACT.md. 기존 approve() 를 건마다 그대로 호출한다."""
from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from ytweb.core import audit
from ytweb.core.errors import ProblemError
from ytweb.db.models import Approval, AuditLog, Suggestion, Video
from ytweb.domain import suggestions as sg
from ytweb.domain.suggestions import approve, approve_batch, check_approval, generate_for_video, resolve_videos

from tests.domain.conftest import ORIGIN, hdr
from tests.domain.helpers import SUGGESTER, eligible_video_ids, suggest

URL = "/api/v1/suggestions/approve-batch"
RES = "/api/v1/suggestions/resolve-videos"


def _gen(db, env, clock, vid, count=5):
    return generate_for_video(db, vid, count=count, tone="friendly", now=clock(), env=env, suggester=SUGGESTER)


def passes(db, env, clock, n, skip=0):
    """서로 다른 영상의 pass 제안 n개."""
    return [suggest(db, env, clock(), vid, 1)[0] for vid in eligible_video_ids(db, n + skip)[skip:]]


def find_result(db, env, clock, result, n=1, start=0):
    """영상 20개 안에서 지정 판정의 제안을 n개 찾는다(영상 start 부터)."""
    out = []
    for vid in eligible_video_ids(db, 40)[start:]:
        for s in _gen(db, env, clock, vid, 5):
            if s.validation_result == result and not s.strict_mode and s.status in ("candidate", "blocked"):
                out.append(s)
                break
        if len(out) >= n:
            return out
    pytest.fail(f"{result} 제안을 {n}개 찾지 못함")


def ids(sugs):
    return [s.id for s in sugs]


def call(db, env, clock, sids, ack=(), approver="홍길동"):
    return approve_batch(db, sids, approver, list(ack), now=clock(), env=env)


def problem(fn, *a, **kw) -> ProblemError:
    with pytest.raises(ProblemError) as e:
        fn(*a, **kw)
    return e.value


def n_approvals(db):
    return db.execute(select(func.count()).select_from(Approval)).scalar_one()


def n_audit(db, action):
    return db.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action)).scalar_one()


# ───────── approve-batch 서비스 ─────────

def test_tc_ba_001_normal_n(seeded, env, clock):
    sugs = passes(seeded, env, clock, 5)
    r = call(seeded, env, clock, ids(sugs))
    assert r["counts"] == {"requested": 5, "approved": 5, "skipped": 0} and r["skipped"] == []
    assert [a["suggestion_id"] for a in r["approved"]] == ids(sugs)
    assert all(s.status == "approved" and s.approval.approver == "홍길동" for s in sugs)


def test_tc_ba_002_fifty_ok(seeded, env, clock):
    sugs = passes(seeded, env, clock, 50)
    r = call(seeded, env, clock, ids(sugs))
    assert r["counts"]["approved"] == 50 and n_approvals(seeded) == 50


def test_tc_ba_003_fifty_one_422(seeded, env, clock):
    sugs = passes(seeded, env, clock, 3)
    e = problem(call, seeded, env, clock, ids(sugs) + list(range(1000, 1048)))
    assert (e.status, e.code) == (422, "bulk_too_many") and "50건" in e.title
    assert n_approvals(seeded) == 0


def test_tc_ba_004_empty_422(seeded, env, clock):
    e = problem(call, seeded, env, clock, [])
    assert (e.status, e.code) == (422, "bulk_empty")


def test_tc_ba_005_duplicate_id_422(seeded, env, clock):
    s = passes(seeded, env, clock, 1)[0]
    e = problem(call, seeded, env, clock, [s.id, s.id])
    assert (e.status, e.code) == (422, "duplicate_suggestion") and n_approvals(seeded) == 0


def test_tc_ba_006_unknown_id_skipped_others_approved(seeded, env, clock):
    a, b = passes(seeded, env, clock, 2)
    r = call(seeded, env, clock, [a.id, 999999, b.id])
    assert r["counts"] == {"requested": 3, "approved": 2, "skipped": 1}
    assert r["skipped"] == [{"suggestion_id": 999999, "video_id": None, "code": "suggestion_not_found", "reason": "제안을 찾을 수 없습니다."}]


def test_tc_ba_007_blocked_skipped_partial_success(seeded, env, clock):
    blk = find_result(seeded, env, clock, "block")[0]
    good = passes(seeded, env, clock, 2, skip=30)
    r = call(seeded, env, clock, [good[0].id, blk.id, good[1].id])
    assert r["counts"] == {"requested": 3, "approved": 2, "skipped": 1}
    sk = r["skipped"][0]
    assert sk["suggestion_id"] == blk.id and sk["code"] == "suggestion_blocked" and sk["video_id"] == blk.video_id and sk["reason"]
    assert seeded.get(Suggestion, blk.id).approval is None and good[0].status == good[1].status == "approved"


def test_tc_ba_008_excluded_video_skipped_and_rolled_back(seeded, env, clock):
    video = next(v for v in seeded.execute(select(Video)).scalars() if v.exclusion_reasons)
    ex = Suggestion(video_id=video.video_id, title="새 제목입니다", evidence="e", source="ai:mock", topic="life", validation_result="pass", status="candidate", created_at=clock(), updated_at=clock())
    seeded.add(ex)
    seeded.flush()
    good = passes(seeded, env, clock, 1)[0]
    r = call(seeded, env, clock, [ex.id, good.id])
    assert r["counts"]["approved"] == 1 and r["skipped"][0]["code"] == "video_excluded"
    assert ex.status == "candidate" and ex.approval is None


def test_tc_ba_009_same_as_current_skipped_and_validation_rolled_back(seeded, env, clock):
    video = seeded.get(Video, eligible_video_ids(seeded, 1)[0])
    s = Suggestion(video_id=video.video_id, title=video.title, evidence="e", source="manual", topic="life", validation_result="pass", status="candidate", created_at=clock(), updated_at=clock(), validation_reasons=[])
    seeded.add(s)
    seeded.flush()
    stamp = s.updated_at
    clock.advance(minutes=5)
    r = call(seeded, env, clock, [s.id], ack=[s.id])  # 첫 실행: ack 없이 호출해 warning_not_acknowledged 가 먼저 나옴(재검증이 warn) -> 확인 목록에 넣어 same_as_current 경로를 시험
    assert r["skipped"][0]["code"] == "same_as_current" and r["counts"]["approved"] == 0
    assert s.status == "candidate" and s.approval is None and s.updated_at == stamp  # _apply_validation 의 변경이 SAVEPOINT 로 되돌려졌다
    assert s.dictionary_hash is None


def test_tc_ba_010_same_video_two_suggestions_first_only(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    a, b = _gen(seeded, env, clock, vid, 2)
    r = call(seeded, env, clock, [b.id, a.id])
    assert [x["suggestion_id"] for x in r["approved"]] == [b.id]
    assert r["skipped"][0]["suggestion_id"] == a.id and r["skipped"][0]["code"] == "duplicate_video_in_request"
    assert a.status == "candidate" and a.approval is None


def test_tc_ba_011_warning_unacknowledged_skipped_no_signature(seeded, env, clock):
    w = find_result(seeded, env, clock, "warn")[0]
    before = n_approvals(seeded)
    r = call(seeded, env, clock, [w.id])
    assert r["skipped"][0]["code"] == "warning_not_acknowledged" and "확인 체크" in r["skipped"][0]["reason"]
    assert n_approvals(seeded) == before and w.approval is None and w.plan_hash is None and w.status == "candidate"
    assert n_audit(seeded, "suggestion.approve") == 0


def test_tc_ba_012_warning_acknowledged_approved(seeded, env, clock):
    w = find_result(seeded, env, clock, "warn")[0]
    r = call(seeded, env, clock, [w.id], ack=[w.id])
    assert r["counts"]["approved"] == 1 and w.status == "approved"


def test_tc_ba_013_ack_only_applies_to_listed_ids(seeded, env, clock):
    w1, w2 = find_result(seeded, env, clock, "warn", n=2)
    r = call(seeded, env, clock, [w1.id, w2.id], ack=[w1.id])
    assert [a["suggestion_id"] for a in r["approved"]] == [w1.id] and r["skipped"][0]["suggestion_id"] == w2.id


def test_tc_ba_014_revalidation_pass_to_warn_requires_ack(seeded, env, clock, monkeypatch):
    s = passes(seeded, env, clock, 1)[0]
    assert s.validation_result == "pass"
    real = sg.validate_title

    def warn_now(*a, **kw):
        res, fr = real(*a, **kw)
        return dataclasses.replace(res, result="warn"), fr

    monkeypatch.setattr(sg, "validate_title", warn_now)
    r = call(seeded, env, clock, [s.id])  # 화면에서는 pass 였지만 승인 시점 재검증이 warn
    assert r["skipped"][0]["code"] == "warning_not_acknowledged" and s.validation_result == "pass" and s.approval is None
    r2 = call(seeded, env, clock, [s.id], ack=[s.id])
    assert r2["counts"]["approved"] == 1 and s.validation_result == "warn"


def test_tc_ba_015_single_approve_unchanged_ack_none(seeded, env, clock):
    w = find_result(seeded, env, clock, "warn")[0]
    assert approve(seeded, w.id, "홍길동", now=clock(), env=env).status == "approved"  # ack_warning=None: 경고도 기존처럼 승인


def test_tc_ba_016_audit_per_item_plus_summary_chain_valid(seeded, env, clock):
    sugs = passes(seeded, env, clock, 3)
    call(seeded, env, clock, ids(sugs) + [999999])
    assert n_audit(seeded, "suggestion.approve") == 3
    row = seeded.execute(select(AuditLog).where(AuditLog.action == "suggestion.approve_batch")).scalar_one()
    assert row.detail == {"approver": "홍길동", "requested": 4, "approved": 3, "skipped": 1}
    assert audit.verify_chain(seeded)


def test_tc_ba_017_audit_chain_valid_after_skips(seeded, env, clock):
    blk = find_result(seeded, env, clock, "block")[0]
    good = passes(seeded, env, clock, 2, skip=30)
    call(seeded, env, clock, [good[0].id, blk.id, good[1].id])
    assert n_audit(seeded, "suggestion.approve") == 2 and audit.verify_chain(seeded)


def test_tc_ba_018_mac_valid_per_item(seeded, env, clock):
    sugs = passes(seeded, env, clock, 4)
    call(seeded, env, clock, ids(sugs))
    for s in sugs:
        check_approval(s, seeded.get(Video, s.video_id), env, clock())  # 예외 없음 = MAC·계획 해시 유효
    assert len({s.approval.mac for s in sugs}) == 4


def test_tc_ba_019_invalid_approver_rejected_before_any_change(seeded, env, clock):
    s = passes(seeded, env, clock, 1)[0]
    e = problem(call, seeded, env, clock, [s.id], approver="   ")
    assert e.status in (400, 422) and n_approvals(seeded) == 0


# ───────── approve-batch HTTP ─────────

def _post(api, csrf, body, key="bulk-key-0001"):
    return api.post(URL, json=body, headers=hdr(csrf, key))


def test_tc_ba_021_http_ok_and_state(seeded, api, csrf, env, clock):
    sugs = passes(seeded, env, clock, 3)
    seeded.commit()
    r = _post(api, csrf, {"approver": "홍길동", "suggestion_ids": ids(sugs), "acknowledged_warning_ids": []})
    assert r.status_code == 200, r.text
    assert r.json()["counts"] == {"requested": 3, "approved": 3, "skipped": 0}
    seeded.expire_all()
    assert all(seeded.get(Suggestion, i).status == "approved" for i in ids(sugs))


def test_tc_ba_022_http_validation_errors(seeded, api, csrf):
    assert _post(api, csrf, {"approver": "a", "suggestion_ids": []}).json()["code"] == "bulk_empty"
    r = _post(api, csrf, {"approver": "a", "suggestion_ids": list(range(1, 52))}, key="bulk-key-0002")
    assert r.status_code == 422 and r.json()["code"] == "bulk_too_many"
    r = _post(api, csrf, {"approver": "a", "suggestion_ids": [1, 1]}, key="bulk-key-0003")
    assert r.status_code == 422 and r.json()["code"] == "duplicate_suggestion"
    assert _post(api, csrf, {"approver": "a", "suggestion_ids": [1], "x": 1}, key="bulk-key-0004").status_code == 422


def test_tc_ba_023_http_csrf_and_session(seeded, api, dapp):
    from fastapi.testclient import TestClient
    with TestClient(dapp, base_url=ORIGIN) as anon:
        assert anon.post(URL, json={"approver": "a", "suggestion_ids": [1]}, headers={"Origin": ORIGIN, "Idempotency-Key": "bulk-key-0005"}).status_code == 401
        assert anon.post(RES, json={"video_ids": ["aaaaaaaaaaa"]}, headers={"Origin": ORIGIN}).status_code == 401
    # 로그인은 했지만 CSRF 토큰 없음
    login_resp = api.post("/api/v1/auth/session", headers={"Origin": ORIGIN})
    assert login_resp.status_code == 200
    r = api.post(URL, json={"approver": "a", "suggestion_ids": [1]}, headers={"Origin": ORIGIN, "Idempotency-Key": "bulk-key-0006"})
    assert r.status_code == 403
    assert api.post(RES, json={"video_ids": ["aaaaaaaaaaa"]}, headers={"Origin": ORIGIN}).status_code == 403


def test_tc_ba_024_http_idempotent_replay(seeded, api, csrf, env, clock):
    sugs = passes(seeded, env, clock, 2)
    seeded.commit()
    body = {"approver": "홍길동", "suggestion_ids": ids(sugs), "acknowledged_warning_ids": []}
    r1 = _post(api, csrf, body)
    r2 = _post(api, csrf, body)
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    seeded.expire_all()
    assert n_approvals(seeded) == 2 and n_audit(seeded, "suggestion.approve_batch") == 1
    r3 = _post(api, csrf, {**body, "approver": "다른사람"})
    assert r3.status_code == 422 and r3.json()["code"] == "idempotency_key_reuse"
    assert api.post(URL, json=body, headers=hdr(csrf)).json()["code"] == "idempotency_key_required"


def test_tc_ba_025_http_same_request_new_key_no_double_approval(seeded, api, csrf, env, clock):
    s = passes(seeded, env, clock, 1)[0]
    seeded.commit()
    body = {"approver": "홍길동", "suggestion_ids": [s.id]}
    assert _post(api, csrf, body, "bulk-key-0010").json()["counts"]["approved"] == 1
    r = _post(api, csrf, body, "bulk-key-0011").json()
    assert r["counts"]["approved"] == 0 and r["skipped"][0]["code"] == "suggestion_state"
    seeded.expire_all()
    assert n_approvals(seeded) == 1


def test_tc_ba_026_http_failed_request_key_reusable(seeded, api, csrf):
    r = _post(api, csrf, {"approver": "a", "suggestion_ids": []}, "bulk-key-0012")
    assert r.status_code == 422
    r = _post(api, csrf, {"approver": "a", "suggestion_ids": []}, "bulk-key-0012")
    assert r.status_code == 422 and r.json()["code"] == "bulk_empty"  # in_progress 로 막히지 않음


# ───────── resolve-videos ─────────

def test_tc_ba_030_resolve_not_found_excluded_zero_one_many(seeded, env, clock):
    vids = eligible_video_ids(seeded, 4)
    excluded = next(v for v in seeded.execute(select(Video)).scalars() if v.exclusion_reasons)
    one = suggest(seeded, env, clock(), vids[0], 1)[0]
    many = _gen(seeded, env, clock, vids[1], 3)
    rows = resolve_videos(seeded, [vids[2], "zzzzzzzzzzz", excluded.video_id, vids[0], vids[1]], env=env)
    by = {r["video_id"]: r for r in rows}
    assert [r["video_id"] for r in rows] == [vids[2], "zzzzzzzzzzz", excluded.video_id, vids[0], vids[1]]  # 입력 순서
    assert by["zzzzzzzzzzz"] == {"video_id": "zzzzzzzzzzz", "found": False, "video_title": None, "excluded_reasons": [], "candidates": []}
    assert by[vids[2]]["found"] and by[vids[2]]["candidates"] == [] and by[vids[2]]["video_title"]
    assert by[excluded.video_id]["excluded_reasons"]
    assert [s.id for s in by[vids[0]]["candidates"]] == [one.id]
    assert [s.id for s in by[vids[1]]["candidates"]] == sorted(ids(many), reverse=True) or len(by[vids[1]]["candidates"]) >= 2


def test_tc_ba_031_resolve_status_filter_and_order(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    sugs = _gen(seeded, env, clock, vid, 5)
    blocked = [s for s in sugs if s.status == "blocked"]
    rej = next(s for s in sugs if s.status == "candidate")
    rej.status = "rejected"
    seeded.flush()
    got = resolve_videos(seeded, [vid], env=env)[0]["candidates"]
    assert all(s.status in ("candidate", "expired", "approved") for s in got)
    assert not {s.id for s in blocked} & {s.id for s in got} and rej.id not in {s.id for s in got}
    assert [s.id for s in got] == sorted((s.id for s in got), reverse=True)


def test_tc_ba_032_resolve_dedup_keeps_order(seeded, env, clock):
    a, b = eligible_video_ids(seeded, 2)
    rows = resolve_videos(seeded, [b, a, b, a], env=env)
    assert [r["video_id"] for r in rows] == [b, a]


def test_tc_ba_033_resolve_limits(seeded, env):
    vids = [f"{i:011d}" for i in range(51)]
    assert problem(resolve_videos, seeded, vids, env=env).code == "bulk_too_many"
    assert resolve_videos(seeded, vids[:50], env=env)[0]["found"] is False
    assert problem(resolve_videos, seeded, [], env=env).code == "bulk_empty"
    assert len(resolve_videos(seeded, vids[:1] * 60, env=env)) == 1  # 중복 제거 후 1개는 허용


def test_tc_ba_034_resolve_read_only(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    s = suggest(seeded, env, clock(), vid, 1)[0]
    approve(seeded, s.id, "홍길동", now=clock(), env=env)
    clock.advance(hours=5)  # 승인 만료 시각 이후: 목록 조회라면 expired 로 바꾸는 상황
    seeded.commit()
    snap = lambda: (seeded.execute(select(Suggestion.id, Suggestion.status, Suggestion.updated_at)).all(), n_audit(seeded, "suggestion.approve"), seeded.execute(select(func.count()).select_from(AuditLog)).scalar_one())
    before = snap()
    resolve_videos(seeded, [vid], env=env)
    assert not seeded.dirty and not seeded.new and not seeded.deleted
    assert snap() == before  # 롤백 전(같은 트랜잭션 안)에서도 변경이 없다
    seeded.rollback()
    assert snap() == before


def test_tc_ba_035_resolve_http(seeded, api, csrf, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    s = suggest(seeded, env, clock(), vid, 1)[0]
    seeded.commit()
    r = api.post(RES, json={"video_ids": [vid, "zzzzzzzzzzz"]}, headers=hdr(csrf))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items[0]["candidates"][0]["id"] == s.id and items[0]["candidates"][0]["title"] == s.title and items[1]["found"] is False
    r = api.post(RES, json={"video_ids": [f"{i:011d}" for i in range(51)]}, headers=hdr(csrf))
    assert r.status_code == 422 and r.json()["code"] == "bulk_too_many"
    assert api.post(RES, json={"video_ids": ["short"]}, headers=hdr(csrf)).status_code == 422
    assert api.post(RES, json={"video_ids": []}, headers=hdr(csrf)).json()["code"] == "bulk_empty"


# ───────── PostgreSQL 전용(실제 트랜잭션·SAVEPOINT·잠금) ─────────

@pytest.fixture
def pgfac(pg_url, env, clock):
    from ytweb.db.models import Base
    from ytweb.db.session import make_engine, make_session_factory
    from ytweb.domain.seed import seed_demo
    engine = make_engine(pg_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    fac = make_session_factory(engine)
    with fac() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    yield fac
    engine.dispose()
    cleanup = make_engine(pg_url)
    Base.metadata.drop_all(cleanup)
    cleanup.dispose()


@pytest.mark.postgres
def test_tc_ba_020_pg_unexpected_exception_no_partial_commit(pgfac, env, clock, monkeypatch):
    with pgfac() as s:
        sid = ids(passes(s, env, clock, 2))
        s.commit()
    real = sg.compute_mac
    calls = []

    def boom(*x, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real(*x, **kw)

    monkeypatch.setattr(sg, "compute_mac", boom)
    with pgfac() as s:
        with pytest.raises(RuntimeError):
            call(s, env, clock, sid)
        s.rollback()  # get_session 이 하는 일
    with pgfac() as s:
        assert n_approvals(s) == 0 and n_audit(s, "suggestion.approve") == 0 and n_audit(s, "suggestion.approve_batch") == 0


@pytest.mark.postgres
def test_tc_ba_020b_pg_skipped_item_rolled_back_others_committed(pgfac, env, clock):
    with pgfac() as s:
        blk = find_result(s, env, clock, "block")[0]
        good = passes(s, env, clock, 2, skip=30)
        order = [good[0].id, blk.id, good[1].id]
        blk_id = blk.id
        s.commit()
    with pgfac() as s:
        r = call(s, env, clock, order)
        s.commit()
    assert r["counts"] == {"requested": 3, "approved": 2, "skipped": 1}
    with pgfac() as s:
        assert n_approvals(s) == 2 and s.get(Suggestion, blk_id).approval is None and audit.verify_chain(s)


# ───────── 동시성(PostgreSQL 전용) ─────────

@pytest.mark.postgres
def test_tc_ba_040_concurrent_batches_no_double_approval(pgfac, env, clock):
    fac = pgfac
    with fac() as s:
        sid = ids(passes(s, env, clock, 10))
        s.commit()

    def run(order):
        with fac() as s2:
            r = approve_batch(s2, order, "홍길동", [], now=clock(), env=env)
            s2.commit()
            return r

    with ThreadPoolExecutor(2) as ex:
        f1, f2 = ex.submit(run, sid), ex.submit(run, list(reversed(sid)))
        r1, r2 = f1.result(timeout=60), f2.result(timeout=60)
    assert r1["counts"]["approved"] + r2["counts"]["approved"] == 10  # 각 제안은 정확히 한 번만 승인
    with fac() as s3:
        assert n_approvals(s3) == 10 and n_audit(s3, "suggestion.approve") == 10 and audit.verify_chain(s3)
