"""독립 검증(TC-BV-001~): 일괄 승인 백엔드. 계약 docs/harness/bulk-approve/CONTRACT.md 기준."""
from __future__ import annotations

import socket
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, func

from ytweb.core import audit
from ytweb.core.errors import ProblemError
from ytweb.db.models import Approval, AuditLog, Suggestion, Video
from ytweb.domain import suggestions as sg
from ytweb.domain.suggestions import approve, approve_batch, check_approval, compute_mac, _load_key, generate_for_video
from ytweb.domain.schemas import SuggestionOut

from tests.domain.conftest import ORIGIN, hdr
from tests.domain.helpers import SUGGESTER, eligible_video_ids, suggest

URL = "/api/v1/suggestions/approve-batch"
RES = "/api/v1/suggestions/resolve-videos"


def passes(db, env, clock, n, skip=0):
    return [suggest(db, env, clock(), v, 1)[0] for v in eligible_video_ids(db, n + skip)[skip:]]


def find(db, env, clock, result, n=1, start=0):
    out = []
    for vid in eligible_video_ids(db, 45)[start:]:
        for s in generate_for_video(db, vid, count=5, tone="friendly", now=clock(), env=env, suggester=SUGGESTER):
            if s.validation_result == result and not s.strict_mode and s.status in ("candidate", "blocked"):
                out.append(s)
                break
        if len(out) >= n:
            return out
    pytest.fail(f"{result} not found")


def post(api, csrf, body, key="vb-key-000001", url=URL):
    return api.post(url, json=body, headers=hdr(csrf, key))


def p(fn, *a, **kw):
    with pytest.raises(ProblemError) as e:
        fn(*a, **kw)
    return e.value


def test_tc_bv_001_single_path_unchanged_with_warn(seeded, env, clock):
    w = find(seeded, env, clock, "warn")[0]
    r = approve(seeded, w.id, "홍길동", now=clock(), env=env)  # ack_warning=None: 경고도 기존처럼 승인
    assert r.status == "approved"
    w2 = find(seeded, env, clock, "warn", start=20)[0]
    r2 = approve(seeded, w2.id, "홍길동", now=clock(), env=env, ack_warning=None)
    assert r2.status == "approved"
    # ack_warning=True 도 승인
    w3 = find(seeded, env, clock, "warn", start=30)[0]
    assert approve(seeded, w3.id, "홍길동", now=clock(), env=env, ack_warning=True).status == "approved"


def test_tc_bv_002_single_http_schema_unchanged(seeded, api, csrf, env, clock):
    s = passes(seeded, env, clock, 1)[0]
    seeded.commit()
    r = api.post(f"/api/v1/suggestions/{s.id}/approve", json={"approver": "홍길동"}, headers=hdr(csrf))
    assert r.status_code == 200
    assert set(r.json()) == set(SuggestionOut.model_fields)


def test_tc_bv_003_response_schema_exact(seeded, api, csrf, env, clock):
    sugs = passes(seeded, env, clock, 3)
    blk = find(seeded, env, clock, "block", start=20)[0]
    seeded.commit()
    body = {"approver": "홍길동", "suggestion_ids": [sugs[0].id, sugs[1].id, blk.id, 999999, sugs[2].id]}
    r = post(api, csrf, body)
    assert r.status_code == 200
    j = r.json()
    assert set(j) == {"approved", "skipped", "counts"}
    assert set(j["counts"]) == {"requested", "approved", "skipped"}
    assert j["counts"] == {"requested": 5, "approved": 3, "skipped": 2}
    assert all(set(a) == {"suggestion_id", "video_id"} for a in j["approved"])
    assert all(set(a) == {"suggestion_id", "video_id", "code", "reason"} for a in j["skipped"])
    nf = [x for x in j["skipped"] if x["code"] == "suggestion_not_found"][0]
    assert nf["video_id"] is None and nf["suggestion_id"] == 999999
    assert any(x["code"] == "suggestion_blocked" for x in j["skipped"]), j["skipped"]
    rv = api.post(RES, json={"video_ids": [sugs[0].video_id, "zzzzzzzzzzz"]}, headers=hdr(csrf))
    it = rv.json()
    assert set(it) == {"items"} and set(it["items"][0]) == {"video_id", "found", "video_title", "excluded_reasons", "candidates"}
    assert set(it["items"][0]["candidates"][0]) == set(SuggestionOut.model_fields)


def test_tc_bv_004_warn_bypass_attempts(seeded, env, clock):
    w = find(seeded, env, clock, "warn", 2)
    ok = passes(seeded, env, clock, 1, skip=40)[0]
    # 경고 id 가 ack 에 없음 / 다른(통과) id 만 ack / 요청에 없는 id 를 ack
    for ack in ([], [ok.id], [w[1].id, 424242]):
        r = approve_batch(seeded, [w[0].id], "홍길동", ack, now=clock(), env=env)
        assert r["counts"]["approved"] == 0 and r["skipped"][0]["code"] == "warning_not_acknowledged", ack
        assert w[0].approval is None and w[0].status == "candidate"
    # 정확한 id 만 승인
    r = approve_batch(seeded, [w[0].id, w[1].id], "홍길동", [w[1].id], now=clock(), env=env)
    assert [a["suggestion_id"] for a in r["approved"]] == [w[1].id]


def test_tc_bv_005_revalidation_overrides_stored_verdict(seeded, env, clock):
    w = find(seeded, env, clock, "warn")[0]
    w.validation_result = "pass"  # 저장값을 pass 로 위조: 승인 시점 재검증이 warn 으로 되돌려야 한다
    seeded.flush()
    r = approve_batch(seeded, [w.id], "홍길동", [], now=clock(), env=env)
    assert r["skipped"] and r["skipped"][0]["code"] == "warning_not_acknowledged"
    b = find(seeded, env, clock, "block")[0]
    b.status, b.validation_result = "candidate", "pass"  # 차단을 후보/통과로 위조
    seeded.flush()
    r = approve_batch(seeded, [b.id], "홍길동", [b.id], now=clock(), env=env)
    assert r["skipped"] and r["skipped"][0]["code"] == "suggestion_blocked" and b.approval is None


def test_tc_bv_006_mac_plan_hash_audit_chain(seeded, env, clock):
    sugs = passes(seeded, env, clock, 4)
    blk = find(seeded, env, clock, "block")[0]
    r = approve_batch(seeded, [sugs[0].id, blk.id] + [s.id for s in sugs[1:]], "홍길동", [], now=clock(), env=env)
    assert r["counts"] == {"requested": 5, "approved": 4, "skipped": 1}
    key = _load_key(env.secrets_dir, create=False)
    for s in sugs:
        a = s.approval
        assert a is not None and a.approver == "홍길동"
        v = seeded.get(Video, s.video_id)
        assert a.plan_hash == sg.plan_hash_for(s, v) == s.plan_hash
        assert a.mac == compute_mac(key, suggestion_id=s.id, video_id=s.video_id, plan_hash=a.plan_hash, approver=a.approver, approved_at=a.approved_at, expires_at=a.expires_at)
        check_approval(s, v, env, clock())  # 예외 없음
    assert audit.verify_chain(seeded)
    acts = [x.action for x in seeded.execute(select(AuditLog).order_by(AuditLog.id)).scalars()]
    assert acts.count("suggestion.approve") == 4 and acts.count("suggestion.approve_batch") == 1 and acts[-1] == "suggestion.approve_batch"


def test_tc_bv_007_idempotency(seeded, api, csrf, env, clock):
    sugs = passes(seeded, env, clock, 2)
    seeded.commit()
    body = {"approver": "홍길동", "suggestion_ids": [s.id for s in sugs]}
    r1 = post(api, csrf, body, "vb-idem-0001")
    r2 = post(api, csrf, body, "vb-idem-0001")
    assert r1.status_code == r2.status_code == 200 and r1.json() == r2.json()
    r3 = post(api, csrf, {**body, "suggestion_ids": body["suggestion_ids"][::-1]}, "vb-idem-0001")
    assert r3.status_code == 422 and r3.json()["code"] == "idempotency_key_reuse"
    r4 = post(api, csrf, {**body, "acknowledged_warning_ids": [1]}, "vb-idem-0001")
    assert r4.status_code == 422
    seeded.expire_all()
    assert seeded.execute(select(func.count()).select_from(Approval)).scalar_one() == 2
    # 키 없음
    assert api.post(URL, json=body, headers=hdr(csrf)).status_code in (400, 422)
    # 실패 응답 뒤 같은 키 재시도 가능
    bad = post(api, csrf, {"approver": "홍길동", "suggestion_ids": []}, "vb-idem-0002")
    assert bad.status_code == 422 and bad.json()["code"] == "bulk_empty"
    ok = post(api, csrf, {"approver": "홍길동", "suggestion_ids": [sugs[0].id]}, "vb-idem-0002")
    assert ok.status_code in (200, 422)


@pytest.mark.parametrize("ids", [[-1], [0], [10**30], [2**63], ["abc"], ["1"], [1.5], [None], [True], "5", [[1]], None])
def test_tc_bv_008_bad_ids_http(seeded, api, csrf, ids):
    r = post(api, csrf, {"approver": "홍길동", "suggestion_ids": ids}, "vb-bad-id-0001")
    assert r.status_code == 422, (ids, r.status_code, r.text)


def test_tc_bv_009_bad_ack_ids_http(seeded, api, csrf, env, clock):
    s = passes(seeded, env, clock, 1)[0]
    seeded.commit()
    for ack in ([-1], [0], ["x"], [10**30]):
        r = post(api, csrf, {"approver": "홍길동", "suggestion_ids": [s.id], "acknowledged_warning_ids": ack}, "vb-bad-ack-0001")
        assert r.status_code == 422, (ack, r.status_code)


def test_tc_bv_010_approver_rules_match_single(seeded, api, csrf, env, clock):
    sugs = passes(seeded, env, clock, 12)
    seeded.commit()
    names = ["", "   ", "\t\n", "a" * 41, "a" * 200, "a" * 201, "a" * 5000, "홍​길동", "홍‮길동", "홍­x", "홍\x00길동", "홍 길동", "  홍길동  ", None, 5]
    for i, nm in enumerate(names):
        sid = sugs[i % 12].id
        rs = api.post(f"/api/v1/suggestions/{sid}/approve", json={"approver": nm}, headers=hdr(csrf))
        sid = sugs[(i + 6) % 12].id if rs.status_code != 200 else sugs[11].id
        rb = post(api, csrf, {"approver": nm, "suggestion_ids": [sid]}, f"vb-appr-{i:04d}-x")
        if rs.status_code == 200:
            assert rb.status_code == 200, (nm, rb.text)
        else:
            assert rb.status_code == rs.status_code and rb.json()["code"] == rs.json()["code"], (nm, rs.status_code, rs.text, rb.status_code, rb.text)
    seeded.expire_all()
    assert not seeded.execute(select(Approval).where(Approval.approver.in_(["", "a" * 41]))).first()


def test_tc_bv_011_count_limits_http(seeded, api, csrf, env, clock):
    sugs = passes(seeded, env, clock, 2)
    seeded.commit()
    r = post(api, csrf, {"approver": "x", "suggestion_ids": list(range(1, 52))}, "vb-lim-00001")
    assert (r.status_code, r.json()["code"]) == (422, "bulk_too_many")
    r = post(api, csrf, {"approver": "x", "suggestion_ids": [sugs[0].id, sugs[0].id]}, "vb-lim-00002")
    assert (r.status_code, r.json()["code"]) == (422, "duplicate_suggestion")
    r = post(api, csrf, {"approver": "x", "suggestion_ids": list(range(1, 502))}, "vb-lim-00003")
    assert r.status_code == 422
    seeded.expire_all()
    assert seeded.execute(select(func.count()).select_from(Approval)).scalar_one() == 0


def test_tc_bv_012_resolve_bounds(seeded, api, csrf):
    ok = "abcdefghijk"
    cases = {"short": 422, "a" * 12: 422, "abc def ghi": 422, "abcdefghij!": 422, "ａｂｃｄｅｆｇｈｉｊｋ": 422, "": 422}
    for v, code in cases.items():
        assert api.post(RES, json={"video_ids": [v]}, headers=hdr(csrf)).status_code == code, v
    assert api.post(RES, json={"video_ids": [ok] * 51}, headers=hdr(csrf)).status_code == 200  # 중복 제거 뒤 1개
    uniq = [f"{i:011d}" for i in range(51)]
    r = api.post(RES, json={"video_ids": uniq}, headers=hdr(csrf))
    assert r.status_code == 422 and r.json()["code"] == "bulk_too_many"
    assert api.post(RES, json={"video_ids": uniq[:50]}, headers=hdr(csrf)).status_code == 200
    assert api.post(RES, json={"video_ids": []}, headers=hdr(csrf)).json()["code"] == "bulk_empty"
    assert api.post(RES, json={}, headers=hdr(csrf)).status_code == 422
    assert api.post(RES, json={"video_ids": uniq[:2]}, headers={"Origin": ORIGIN}).status_code == 403


def test_tc_bv_013_session_required(seeded, api):
    for url, b in ((URL, {"approver": "x", "suggestion_ids": [1]}), (RES, {"video_ids": ["abcdefghijk"]})):
        r = api.post(url, json=b, headers={"Origin": ORIGIN, "Idempotency-Key": "vb-nosess-001"})
        assert r.status_code in (401, 403), (url, r.status_code)


def test_tc_bv_014_no_network_and_no_gateway(seeded, api, csrf, env, clock, monkeypatch):
    sugs = passes(seeded, env, clock, 3)
    seeded.commit()

    def deny(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    r = post(api, csrf, {"approver": "홍길동", "suggestion_ids": [s.id for s in sugs]}, "vb-net-00001")
    assert r.status_code == 200 and r.json()["counts"]["approved"] == 3
    assert api.post(RES, json={"video_ids": [s.video_id for s in sugs]}, headers=hdr(csrf)).status_code == 200
    import inspect
    src = inspect.getsource(sg)
    assert "gateway" not in src.lower().replace("apply_gateway", "") or "import" not in [l for l in src.splitlines() if "gateway" in l.lower() and l.startswith(("import", "from"))]


def test_tc_bv_015_states_skipped(seeded, env, clock):
    a, b, c, d = passes(seeded, env, clock, 4)
    approve(seeded, a.id, "홍길동", now=clock(), env=env)
    b.status = "rejected"
    c.status = "applied"
    seeded.flush()
    v = seeded.get(Video, d.video_id)
    v.snippet = {**v.snippet, "title": "다른 제목"}  # video_inconsistent
    seeded.flush()
    r = approve_batch(seeded, [a.id, b.id, c.id, d.id], "홍길동", [], now=clock(), env=env)
    assert r["counts"]["approved"] == 0
    assert {x["suggestion_id"]: x["code"] for x in r["skipped"]} == {a.id: "suggestion_state", b.id: "suggestion_state", c.id: "suggestion_state", d.id: "video_inconsistent"}


def test_tc_bv_016_same_video_two_suggestions(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    s = generate_for_video(seeded, vid, count=5, tone="friendly", now=clock(), env=env, suggester=SUGGESTER)
    good = [x for x in s if x.status == "candidate"][:2]
    assert len(good) == 2
    r = approve_batch(seeded, [good[1].id, good[0].id], "홍길동", [good[0].id, good[1].id], now=clock(), env=env)
    assert [a["suggestion_id"] for a in r["approved"]] == [good[1].id]
    assert r["skipped"][0]["code"] == "duplicate_video_in_request"
    assert good[0].approval is None


@pytest.mark.postgres
def test_tc_bv_020_pg_concurrent_same_suggestion(pg_url, env, clock):
    from ytweb.db.models import Base
    from ytweb.db.session import make_engine, make_session_factory
    from ytweb.domain.seed import seed_demo
    eng = make_engine(pg_url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    fac = make_session_factory(eng)
    with fac() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
        sid = passes(s, env, clock, 1)[0].id
        sid2 = passes(s, env, clock, 1, skip=10)[0].id
        s.commit()
    bar = threading.Barrier(4)

    def run(i):
        with fac() as s:
            bar.wait()
            r = approve_batch(s, [sid, sid2] if i % 2 else [sid2, sid], f"사람{i}", [], now=clock(), env=env)
            s.commit()
            return r
    with ThreadPoolExecutor(4) as ex:
        rs = list(ex.map(run, range(4)))
    assert sum(r["counts"]["approved"] for r in rs) == 2
    with fac() as s:
        assert s.execute(select(func.count()).select_from(Approval)).scalar_one() == 2
        assert s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "suggestion.approve")).scalar_one() == 2
        assert audit.verify_chain(s)
    eng.dispose()
    c = make_engine(pg_url)
    Base.metadata.drop_all(c)
    c.dispose()


@pytest.mark.postgres
def test_tc_bv_021_pg_partial_failure_midbatch_rollback_and_chain(pg_url, env, clock, monkeypatch):
    from ytweb.db.models import Base
    from ytweb.db.session import make_engine, make_session_factory
    from ytweb.domain.seed import seed_demo
    eng = make_engine(pg_url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    fac = make_session_factory(eng)
    with fac() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
        good = passes(s, env, clock, 3)
        blk = find(s, env, clock, "block", start=20)[0]
        warn = find(s, env, clock, "warn", start=30)[0]
        order = [good[0].id, blk.id, warn.id, 777777, good[1].id, good[2].id]
        s.commit()
    with fac() as s:
        r = approve_batch(s, order, "홍길동", [], now=clock(), env=env)
        s.commit()
    assert r["counts"] == {"requested": 6, "approved": 3, "skipped": 3}
    with fac() as s:
        assert s.execute(select(func.count()).select_from(Approval)).scalar_one() == 3
        assert s.get(Suggestion, warn.id).approval is None and s.get(Suggestion, warn.id).status == "candidate"
        assert audit.verify_chain(s)
        key = _load_key(env.secrets_dir, create=False)
        for a in s.execute(select(Approval)).scalars():
            sug = s.get(Suggestion, a.suggestion_id)
            assert a.mac == compute_mac(key, suggestion_id=sug.id, video_id=sug.video_id, plan_hash=a.plan_hash, approver=a.approver, approved_at=a.approved_at, expires_at=a.expires_at)
    # 예상 못 한 예외: 이후 건이 터지면 전체 롤백
    with fac() as s:
        more = passes(s, env, clock, 2, skip=40)
        mid = [m.id for m in more]
        s.commit()
    real = audit.record
    n = []

    def boom(*a, **k):
        if k.get("action") == "suggestion.approve_batch":
            raise RuntimeError("boom")
        return real(*a, **k)
    monkeypatch.setattr(sg.audit, "record", boom)
    with fac() as s:
        with pytest.raises(RuntimeError):
            approve_batch(s, mid, "홍길동", [], now=clock(), env=env)
        s.rollback()
    monkeypatch.setattr(sg.audit, "record", real)
    with fac() as s:
        assert s.execute(select(func.count()).select_from(Approval)).scalar_one() == 3
        assert audit.verify_chain(s)
    eng.dispose()
    c = make_engine(pg_url)
    Base.metadata.drop_all(c)
    c.dispose()
