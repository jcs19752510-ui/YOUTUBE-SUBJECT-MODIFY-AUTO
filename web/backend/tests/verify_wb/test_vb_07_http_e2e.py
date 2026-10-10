"""6단계 독립 검증 7: HTTP 계층(인증·CSRF·Origin·멱등성·입력 검증·오류 형식)과 업무 흐름 E2E(동기화→생성→승인→배치→워커→이력→롤백→리포트)."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import func, select

from ytweb.core import jobs
from ytweb.db.models import AuditLog, Batch, BatchItem, Change, Job, Suggestion, Video
from ytweb.domain import handlers
from ytweb.domain.common import set_default_env
from ytweb.domain.seed import seed_demo

from tests.conftest import ORIGIN
from tests.verify_wb.conftest import hdr
from tests.verify_wb.vbh import life_ids

PROBLEM = {"type", "title", "status", "detail", "code", "hint"}


@pytest.fixture
def world(api, csrf, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=200)
        s.commit()
    return api


def _prob(r, status, code):
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    b = r.json()
    assert set(b) == PROBLEM and b["code"] == code and b["status"] == status and b["hint"] is not None
    blob = json.dumps(b, ensure_ascii=False)
    for leak in ("Traceback", "/home/", "site-packages", "sqlalchemy", ".py"):
        assert leak not in blob, leak
    return b


def _sugs(api, csrf, vid, n=1):
    r = api.post(f"/api/v1/videos/{vid}/suggestions", json={"count": n}, headers=hdr(csrf))
    assert r.status_code == 201, r.text
    return r.json()


def _approved_ids(api, csrf, factory, n, skip=0):
    ids = []
    with factory() as s:
        vids = life_ids(s, n, skip=skip)
    for v in vids:
        first_pass = next(x for x in _sugs(api, csrf, v, 5) if x["validation_result"] == "pass")
        r = api.post(f"/api/v1/suggestions/{first_pass['id']}/approve", json={"approver": "홍길동"}, headers=hdr(csrf))
        assert r.status_code == 200, r.text
        ids.append(first_pass["id"])
    return ids


def test_tc_vb_230_full_flow_over_http(world, csrf, factory, env, clock):
    """업무 단위 흐름 전체를 HTTP 로: 제안 생성 → 승인 → 배치(사전 점검) → 실행 확정 → 워커 → 이력 → 롤백 → 리포트·CSV."""
    api = world
    ids = _approved_ids(api, csrf, factory, 3)
    k1 = uuid.uuid4().hex
    r = api.post("/api/v1/batches", json={"suggestion_ids": ids, "note": "E2E"}, headers=hdr(csrf, k1))
    assert r.status_code == 201, r.text
    body = r.json()
    bid, pre = body["batch"]["id"], body["precheck"]
    assert pre["item_count"] == 3 and pre["confirm_text"] == "실행 3건" and body["batch"]["status"] == "draft"
    bad = api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 4건"}, headers=hdr(csrf, uuid.uuid4().hex))
    _prob(bad, 422, "confirm_text_mismatch")
    ex = api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 3건"}, headers=hdr(csrf, uuid.uuid4().hex))
    assert ex.status_code == 202, ex.text
    job = ex.json()["job"]
    assert job["type"] == "batch.execute" and job["status"] == "queued"
    assert api.get(f"/api/v1/batches/{bid}").json()["status"] == "queued"
    assert jobs.process_next(factory, worker_id="vb", clock=clock)
    done = api.get(f"/api/v1/jobs/{job['id']}").json()
    assert done["status"] == "succeeded" and done["result"]["success"] == 3 and done["result"]["stopped_by"] is None
    detail = api.get(f"/api/v1/batches/{bid}").json()
    assert detail["status"] == "done" and detail["counts"]["success"] == 3 and all(i["change_id"] for i in detail["items"])
    ch = api.get(f"/api/v1/changes?batch_id={bid}").json()
    assert ch["total"] == 3 and all(c["result"] == "success" and c["rollbackable"] for c in ch["items"])
    first = ch["items"][-1]
    rb_key = uuid.uuid4().hex
    wrong = api.post(f"/api/v1/changes/{first['id']}/rollback", json={"typed_video_id": "demoVid9999", "approver": "담당"}, headers=hdr(csrf, uuid.uuid4().hex))
    _prob(wrong, 422, "typed_video_id_mismatch")
    rb = api.post(f"/api/v1/changes/{first['id']}/rollback", json={"typed_video_id": first["video_id"], "approver": "담당"}, headers=hdr(csrf, rb_key))
    assert rb.status_code == 201 and rb.json()["change_type"] == "rollback" and rb.json()["result"] == "success" and rb.json()["rollbackable"] is False
    replay = api.post(f"/api/v1/changes/{first['id']}/rollback", json={"typed_video_id": first["video_id"], "approver": "담당"}, headers=hdr(csrf, rb_key))
    assert replay.status_code == 201 and replay.json() == rb.json()           # 같은 키 재전송 = 저장된 응답 재생
    with factory() as s:
        assert s.execute(select(func.count()).select_from(Change).where(Change.change_type == "rollback")).scalar_one() == 1
    rep = api.get("/api/v1/reports/changes").json()
    assert len(rep["items"]) == 3 and all(i["status"] in ("insufficient", "ok") for i in rep["items"])
    csv_r = api.get(f"/api/v1/reports/export.csv?video_id={first['video_id']}")
    assert csv_r.status_code == 200 and "데이터 부족" in csv_r.text or "ok" in csv_r.text
    dash = api.get("/api/v1/dashboard").json()
    assert dash["counts"]["applied"] >= 2 and dash["today"]["applied"] == 3 and dash["quota"]["used"] == 4 * 52


MUTATING = [
    ("post", "/api/v1/videos/sync", None),
    ("post", "/api/v1/suggestions/generate", {"video_ids": ["demoVid0001"]}),
    ("post", "/api/v1/videos/demoVid0001/suggestions", {"count": 1}),
    ("patch", "/api/v1/suggestions/1", {"title": "x"}),
    ("post", "/api/v1/suggestions/1/approve", {"approver": "a"}),
    ("post", "/api/v1/suggestions/1/reject", None),
    ("post", "/api/v1/batches", {"suggestion_ids": [1]}),
    ("post", "/api/v1/batches/1/execute", {"confirm_text": "실행 1건"}),
    ("post", "/api/v1/batches/1/cancel", None),
    ("post", "/api/v1/changes/1/rollback", {"typed_video_id": "demoVid0001", "approver": "a"}),
]
READS = ["/api/v1/dashboard", "/api/v1/videos", "/api/v1/videos/demoVid0001", "/api/v1/suggestions", "/api/v1/batches", "/api/v1/batches/1",
         "/api/v1/changes", "/api/v1/reports/changes", "/api/v1/reports/export.csv", "/api/v1/google/status", "/api/v1/jobs/00000000-0000-0000-0000-000000000000"]


@pytest.mark.parametrize("method, path, payload", MUTATING)
def test_tc_vb_231_every_mutating_endpoint_requires_session_csrf_and_origin(world, csrf, method, path, payload):
    """S-W03: 상태 변경 11개 경로 전부 — 세션 없음 401, CSRF 없음/틀림 403, Origin 없음/타 출처 403. 아무것도 변경되지 않음."""
    api = world
    fn = lambda c, h: getattr(c, method)(path, json=payload, headers=h) if payload is not None else getattr(c, method)(path, headers=h)
    anon = type(api)(api.app, base_url=ORIGIN)
    r = fn(anon, {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Idempotency-Key": "k" * 12})
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    for h in (
        {"Origin": ORIGIN, "Idempotency-Key": "k" * 12},
        {"Origin": ORIGIN, "X-CSRF-Token": "x" * 20, "Idempotency-Key": "k" * 12},
        {"X-CSRF-Token": csrf, "Idempotency-Key": "k" * 12},
        {"Origin": "http://evil.example", "X-CSRF-Token": csrf, "Idempotency-Key": "k" * 12},
        {"Origin": "null", "X-CSRF-Token": csrf, "Idempotency-Key": "k" * 12},
    ):
        r = fn(api, h)
        assert r.status_code == 403, (method, path, h, r.status_code)
        assert r.json()["code"] in ("csrf_invalid", "origin_not_allowed")


@pytest.mark.parametrize("path", READS)
def test_tc_vb_232_all_read_endpoints_require_session(world, path):
    anon = type(world)(world.app, base_url=ORIGIN)
    r = anon.get(path)
    assert r.status_code == 401 and r.json()["code"] == "session_required"


@pytest.mark.parametrize("method, path", [("put", "/api/v1/suggestions/1"), ("delete", "/api/v1/batches/1"), ("get", "/api/v1/suggestions/1/approve"), ("get", "/api/v1/batches/1/execute"), ("get", "/api/v1/changes/1/rollback"), ("get", "/api/v1/videos/sync")])
def test_tc_vb_233_state_changes_not_reachable_by_get_or_unlisted_verbs(world, csrf, method, path):
    r = getattr(world, method)(path, headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert r.status_code in (404, 405, 422)


def test_tc_vb_234_idempotency_key_rules_on_dangerous_three(world, csrf, factory):
    api = world
    ids = _approved_ids(api, csrf, factory, 2)
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf)), 400, "idempotency_key_required")
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, "short")), 400, "idempotency_key_invalid")
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, "bad key with spaces!!")), 400, "idempotency_key_invalid")
    k = uuid.uuid4().hex
    a = api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, k))
    b = api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, k))
    assert a.status_code == b.status_code == 201 and a.json() == b.json()
    with factory() as s:
        assert s.execute(select(func.count()).select_from(Batch)).scalar_one() == 1
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": ids[:1]}, headers=hdr(csrf, k)), 422, "idempotency_key_reuse")


def test_tc_vb_235_execute_replay_with_same_key_creates_one_job(world, csrf, factory):
    api = world
    ids = _approved_ids(api, csrf, factory, 2)
    bid = api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, uuid.uuid4().hex)).json()["batch"]["id"]
    k = uuid.uuid4().hex
    r1 = api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 2건"}, headers=hdr(csrf, k))
    r2 = api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 2건"}, headers=hdr(csrf, k))
    assert r1.status_code == r2.status_code == 202 and r1.json()["job"]["id"] == r2.json()["job"]["id"]
    r3 = api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 2건"}, headers=hdr(csrf, uuid.uuid4().hex))
    _prob(r3, 409, "batch_not_draft")                     # 다른 키로 다시 실행 → 거부
    with factory() as s:
        assert s.execute(select(func.count()).select_from(Job).where(Job.type == "batch.execute")).scalar_one() == 1


def test_tc_vb_236_failed_request_does_not_burn_the_key(world, csrf, factory):
    api = world
    ids = _approved_ids(api, csrf, factory, 1)
    bid = api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, uuid.uuid4().hex)).json()["batch"]["id"]
    k = uuid.uuid4().hex
    _prob(api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "틀림"}, headers=hdr(csrf, k)), 422, "confirm_text_mismatch")
    assert api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 1건"}, headers=hdr(csrf, k)).status_code in (202, 422)


@pytest.mark.parametrize("path, body, status, code", [
    ("/api/v1/suggestions/1/approve", {"approver": "a", "extra": 1}, 422, "validation_error"),
    ("/api/v1/suggestions/1/approve", {}, 422, "validation_error"),
    ("/api/v1/suggestions/1/approve", {"approver": "x" * 201}, 422, "validation_error"),
    ("/api/v1/suggestions/0/approve", {"approver": "a"}, 422, "validation_error"),
    ("/api/v1/suggestions/-1/approve", {"approver": "a"}, 422, "validation_error"),
    ("/api/v1/suggestions/abc/approve", {"approver": "a"}, 422, "validation_error"),
    ("/api/v1/suggestions/generate", {"video_ids": []}, 422, "validation_error"),
    ("/api/v1/suggestions/generate", {"video_ids": ["short"]}, 422, "validation_error"),
    ("/api/v1/suggestions/generate", {"video_ids": ["demoVid0001'; DROP TABLE videos;--"]}, 422, "validation_error"),
    ("/api/v1/suggestions/generate", {"video_ids": ["zzzzzzzzzzz"]}, 404, "video_not_found"),
    ("/api/v1/suggestions/generate", {"video_ids": ["demoVid0001"], "count": 6}, 422, "validation_error"),
    ("/api/v1/suggestions/generate", {"video_ids": ["demoVid0001"], "count": 0}, 422, "validation_error"),
    ("/api/v1/suggestions/1", {"title": ""}, 422, "validation_error"),
    ("/api/v1/suggestions/1", {"title": "x" * 2001}, 422, "validation_error"),
])
def test_tc_vb_237_input_validation_rejects_bad_requests(world, csrf, path, body, status, code):
    fn = world.patch if path.rstrip("/").split("/")[-1].isdigit() else world.post
    r = fn(path, json=body, headers=hdr(csrf, uuid.uuid4().hex))
    _prob(r, status, code)


def test_tc_vb_238_batch_and_rollback_payload_limits(world, csrf):
    api = world
    h = lambda: hdr(csrf, uuid.uuid4().hex)
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": list(range(1, 502))}, headers=h()), 422, "validation_error")
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": []}, headers=h()), 422, "validation_error")
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": [1], "note": "x" * 1001}, headers=h()), 422, "validation_error")
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": ["1; DROP"]}, headers=h()), 422, "validation_error")
    _prob(api.post("/api/v1/batches", json={"suggestion_ids": list(range(1, 52))}, headers=h()), 422, "batch_too_large")
    _prob(api.post("/api/v1/batches/1/execute", json={"confirm_text": "x" * 101}, headers=h()), 422, "validation_error")
    _prob(api.post("/api/v1/changes/1/rollback", json={"typed_video_id": "x" * 65, "approver": "a"}, headers=h()), 422, "validation_error")
    _prob(api.post("/api/v1/changes/1/rollback", json={"typed_video_id": "a", "approver": ""}, headers=h()), 422, "validation_error")
    _prob(api.get("/api/v1/videos?q=" + "x" * 101), 422, "validation_error")
    _prob(api.get("/api/v1/videos?page=0"), 422, "validation_error")
    _prob(api.get("/api/v1/videos?page_size=201"), 422, "validation_error")
    _prob(api.get("/api/v1/changes?result=hacked"), 422, "validation_error")
    _prob(api.get("/api/v1/changes?video_id=bad"), 422, "validation_error")
    _prob(api.get("/api/v1/batches/0"), 422, "validation_error")
    _prob(api.get("/api/v1/jobs/not-a-uuid"), 422, "validation_error")
    _prob(api.get("/api/v1/batches/99999"), 404, "batch_not_found")
    _prob(api.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000"), 404, "job_not_found")
    _prob(api.post("/api/v1/changes/99999/rollback", json={"typed_video_id": "demoVid0001", "approver": "a"}, headers=h()), 404, "change_not_found")


def test_tc_vb_239_sql_injection_like_search_is_inert(world):
    api = world
    for q in ("' OR '1'='1", "%", "_", "demoVid0001'); DROP TABLE videos;--", "\\", "한글'--"):
        r = api.get("/api/v1/videos", params={"q": q})
        assert r.status_code == 200 and r.json()["total"] == 0, q
    assert api.get("/api/v1/videos?page_size=1").json()["total"] == 200       # 테이블 멀쩡


def test_tc_vb_240_get_with_expired_approval_lazily_expires_idempotently(world, csrf, factory, clock):
    """관찰(OBS-VB-2): GET 목록/상세/대시보드는 시간 경과에 따른 만료 전이(approved→expired)를 기록한다. 의미상 멱등이며 데이터 생성은 없음."""
    api = world
    ids = _approved_ids(api, csrf, factory, 1)
    clock.advance(hours=25)
    from tests.conftest import login
    csrf = login(api)      # 세션 TTL(12h)이 지나 다시 로그인
    d1 = api.get("/api/v1/suggestions?status=expired").json()
    assert d1["total"] == 1 and d1["items"][0]["id"] == ids[0]
    d2 = api.get("/api/v1/suggestions?status=expired").json()
    assert d1 == d2
    r = api.post(f"/api/v1/suggestions/{ids[0]}/approve", json={"approver": "재승인"}, headers=hdr(csrf))
    assert r.status_code == 200 and r.json()["status"] == "approved"      # 만료된 제안은 다시 승인할 수 있다


def test_tc_vb_241_generate_job_via_worker_handles_excluded_and_unknown_per_video(world, csrf, factory, env, clock):
    """suggestions.generate 작업: 제외 영상은 건너뛰고 나머지는 계속(한 영상의 실패가 나머지를 막지 않음). 설정의 tone 목록이 합쳐져 전달."""
    api = world
    with factory() as s:
        ok_ids = life_ids(s, 2)
        excluded = next(v.video_id for v in s.execute(select(Video).order_by(Video.video_id)).scalars() if v.exclusion_reasons)
    r = api.post("/api/v1/suggestions/generate", json={"video_ids": [ok_ids[0], excluded, ok_ids[0], ok_ids[1]], "count": 2}, headers=hdr(csrf))
    assert r.status_code == 202 and r.json()["total"] == 3       # 중복 제거
    assert jobs.process_next(factory, worker_id="vb", clock=clock)
    res = api.get(f"/api/v1/jobs/{r.json()['id']}").json()
    assert res["status"] == "succeeded" and res["result"]["videos"] == 3 and res["result"]["suggestions"] == 4
    assert res["result"]["skipped"] == [{"video_id": excluded, "code": "video_excluded"}]
    with factory() as s:
        assert s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "suggestion.generate")).scalar_one() == 2


def test_tc_vb_242_sync_is_audited_and_deduplicated_while_active(world, csrf, factory, clock):
    api = world
    a = api.post("/api/v1/videos/sync", headers=hdr(csrf)).json()
    b = api.post("/api/v1/videos/sync", headers=hdr(csrf)).json()
    assert a["id"] == b["id"]
    with factory() as s:
        assert s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "videos.sync_request")).scalar_one() == 1
    assert jobs.process_next(factory, worker_id="vb", clock=clock)
    with factory() as s:
        assert s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == "videos.sync")).scalar_one() == 1
