"""HTTP 계약: 경로·요청·응답 형태, 인증/CSRF, 멱등성, 오류 형식(122-140)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from ytweb.core import jobs
from ytweb.db.models import Batch, Change, Video
from ytweb.domain import handlers
from ytweb.domain.batches import apply_one
from ytweb.domain.common import set_default_env
from ytweb.domain.seed import seed_demo
from ytweb.youtube.mock import MockYouTubeGateway

from tests.conftest import ORIGIN
from tests.domain.conftest import hdr
from tests.domain.helpers import approved_many, eligible_video_ids, queued_batch

PROBLEM_KEYS = {"type", "title", "status", "detail", "code", "hint"}
EXPECTED_PATHS = {
    ("get", "/api/v1/dashboard"), ("get", "/api/v1/videos"), ("get", "/api/v1/videos/{video_id}"), ("post", "/api/v1/videos/sync"),
    ("post", "/api/v1/videos/{video_id}/suggestions"), ("post", "/api/v1/suggestions/generate"), ("get", "/api/v1/suggestions"),
    ("patch", "/api/v1/suggestions/{suggestion_id}"), ("post", "/api/v1/suggestions/{suggestion_id}/approve"), ("post", "/api/v1/suggestions/{suggestion_id}/reject"),
    ("post", "/api/v1/batches"), ("get", "/api/v1/batches"), ("get", "/api/v1/batches/{batch_id}"), ("post", "/api/v1/batches/{batch_id}/execute"),
    ("post", "/api/v1/batches/{batch_id}/cancel"), ("get", "/api/v1/jobs/{job_id}"), ("get", "/api/v1/changes"), ("post", "/api/v1/changes/{change_id}/rollback"),
    ("get", "/api/v1/reports/changes"), ("get", "/api/v1/reports/export.csv"), ("get", "/api/v1/google/status"),
}


@pytest.fixture
def data(factory, env, clock):
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    set_default_env(env)
    return factory


def _ok(r, status=200):
    assert r.status_code == status, r.text
    return r.json()


def _problem(r, status, code):
    assert r.status_code == status, r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert set(body) == PROBLEM_KEYS and body["code"] == code and body["status"] == status
    return body


def _vid(factory, n=0):
    with factory() as s:
        return eligible_video_ids(s, n + 1)[n]


def _suggest(api, csrf, vid, count=3):
    return _ok(api.post(f"/api/v1/videos/{vid}/suggestions", json={"count": count}, headers=hdr(csrf)), 201)


def test_tc_wb_122_openapi_exposes_contract_paths(dapp):
    schema = dapp.openapi()
    have = {(m, p) for p, ops in schema["paths"].items() for m in ops}
    assert EXPECTED_PATHS <= have
    assert schema["components"]["schemas"]["SuggestionOut"]["properties"].keys() >= {"id", "video_id", "title", "evidence", "source", "topic", "strict", "validation_result", "reasons", "length", "match_ratio", "status", "plan_hash", "approval", "created_at"}
    assert schema["components"]["schemas"]["PrecheckOut"]["properties"].keys() == {"item_count", "estimated_units", "daily_cap", "quota_remaining_units", "schedule", "warnings", "blocked", "confirm_text", "notice"}


def test_tc_wb_123_auth_and_csrf_are_enforced(api, csrf, data):
    fresh = type(api)(api.app, base_url=ORIGIN)
    _problem(fresh.get("/api/v1/dashboard"), 401, "session_required")
    _problem(fresh.get("/api/v1/videos"), 401, "session_required")
    _problem(api.post("/api/v1/videos/sync", headers={"Origin": ORIGIN}), 403, "csrf_invalid")
    _problem(api.post("/api/v1/batches", json={"suggestion_ids": [1]}, headers={"X-CSRF-Token": csrf}), 403, "origin_not_allowed")
    _problem(api.post("/api/v1/suggestions/1/approve", json={"approver": "a"}, headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong-token"}), 403, "csrf_invalid")


def test_tc_wb_124_sync_job_runs_via_worker_and_is_deduplicated(api, csrf, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    job = _ok(api.post("/api/v1/videos/sync", headers=hdr(csrf)), 202)
    assert set(job) == {"id", "type", "status", "progress", "total", "error", "result"} and job["type"] == "videos.sync" and job["status"] == "queued"
    assert _ok(api.post("/api/v1/videos/sync", headers=hdr(csrf)), 202)["id"] == job["id"]
    assert jobs.process_next(factory, worker_id="t", clock=clock)
    done = _ok(api.get(f"/api/v1/jobs/{job['id']}"))
    assert done["status"] == "succeeded" and done["result"]["created"] == 200 and done["progress"] == 200
    page = _ok(api.get("/api/v1/videos?page_size=200"))
    assert (page["total"], page["page"], page["page_size"], len(page["items"])) == (200, 1, 200, 200)


def test_tc_wb_125_videos_list_detail_and_errors(api, csrf, data):
    vid = _vid(data)
    page = _ok(api.get("/api/v1/videos?q=냉장고&sort=views&order=desc&page_size=5"))
    assert set(page) == {"items", "total", "page", "page_size"} and page["items"] and all("냉장고" in i["title"] for i in page["items"])
    assert _ok(api.get("/api/v1/videos?excluded=true"))["total"] > 0
    detail = _ok(api.get(f"/api/v1/videos/{vid}"))
    assert detail["video_id"] == vid and {"description_excerpt", "suggestions", "changes", "limits", "workflow_status"} <= set(detail) and detail["limits"]["allowed"] is True
    _problem(api.get("/api/v1/videos/zzzzzzzzzzz"), 404, "video_not_found")
    _problem(api.get("/api/v1/videos/짧은ID"), 422, "validation_error")
    _problem(api.get("/api/v1/videos?sort=password"), 422, "validation_error")
    _problem(api.get("/api/v1/videos?page_size=500"), 422, "validation_error")


def test_tc_wb_126_create_suggestions_and_error_shape(api, csrf, data):
    vid = _vid(data)
    sugs = _suggest(api, csrf, vid, 5)
    assert len(sugs) == 5 and {s["validation_result"] for s in sugs} >= {"pass", "block"}
    first = sugs[0]
    assert first["status"] == "candidate" and first["source"] == "ai:mock" and first["approval"] is None and first["length"] == len(first["title"]) and first["reasons"] == []
    default = _ok(api.post(f"/api/v1/videos/{_vid(data, 1)}/suggestions", headers=hdr(csrf)), 201)    # 본문 없이: 설정 기본 3개
    assert len(default) == 3
    with data() as s:
        excluded = next(v.video_id for v in s.execute(select(Video)).scalars() if v.exclusion_reasons)
    body = _problem(api.post(f"/api/v1/videos/{excluded}/suggestions", json={}, headers=hdr(csrf)), 409, "video_excluded")
    assert body["hint"] and body["detail"]
    _problem(api.post(f"/api/v1/videos/{vid}/suggestions", json={"count": 9}, headers=hdr(csrf)), 422, "validation_error")
    _problem(api.post(f"/api/v1/videos/{vid}/suggestions", json={"count": 2, "evil": 1}, headers=hdr(csrf)), 422, "validation_error")


def test_tc_wb_127_edit_approve_reject_over_http(api, csrf, data):
    sugs = _suggest(api, csrf, _vid(data), 5)
    good = sugs[0]
    blocked = next(s for s in sugs if s["validation_result"] == "block")
    _problem(api.post(f"/api/v1/suggestions/{blocked['id']}/approve", json={"approver": "홍길동"}, headers=hdr(csrf)), 409, "suggestion_blocked")
    ok = _ok(api.post(f"/api/v1/suggestions/{good['id']}/approve", json={"approver": "홍길동"}, headers=hdr(csrf)))
    assert ok["status"] == "approved" and ok["approval"]["approver"] == "홍길동" and ok["plan_hash"] and ok["approval"]["expires_at"] > ok["approval"]["approved_at"]
    edited = _ok(api.patch(f"/api/v1/suggestions/{good['id']}", json={"title": good["title"] + " 개정"}, headers=hdr(csrf)))
    assert edited["status"] in ("candidate", "blocked") and edited["approval"] is None and edited["plan_hash"] is None
    rej = _ok(api.post(f"/api/v1/suggestions/{good['id']}/reject", headers=hdr(csrf)))
    assert rej["status"] == "rejected"
    _problem(api.patch(f"/api/v1/suggestions/{good['id']}", json={"title": ""}, headers=hdr(csrf)), 422, "validation_error")
    _problem(api.post("/api/v1/suggestions/987654/approve", json={"approver": "a"}, headers=hdr(csrf)), 404, "suggestion_not_found")
    _problem(api.post(f"/api/v1/suggestions/{good['id']}/approve", json={"approver": "홍길동"}, headers=hdr(csrf)), 409, "suggestion_state")
    listing = _ok(api.get(f"/api/v1/suggestions?video_id={good['video_id']}&status=rejected&result=pass"))
    assert listing["total"] == 1 and listing["items"][0]["id"] == good["id"]
    _problem(api.get("/api/v1/suggestions?status=hacked"), 422, "validation_error")


def test_tc_wb_128_bulk_generate_job(api, csrf, data, factory, clock, monkeypatch):
    monkeypatch.setattr(handlers, "utcnow", clock)
    ids = [_vid(data, 0), _vid(data, 1)]
    job = _ok(api.post("/api/v1/suggestions/generate", json={"video_ids": ids + ids, "count": 2}, headers=hdr(csrf)), 202)
    assert job["type"] == "suggestions.generate" and job["total"] == 2        # 중복 영상 ID 는 하나로
    jobs.process_next(factory, worker_id="t", clock=clock)
    done = _ok(api.get(f"/api/v1/jobs/{job['id']}"))
    assert done["status"] == "succeeded" and done["result"]["suggestions"] == 4 and done["progress"] == 2
    assert _ok(api.get("/api/v1/suggestions"))["total"] == 4
    _problem(api.post("/api/v1/suggestions/generate", json={"video_ids": ["zzzzzzzzzzz"]}, headers=hdr(csrf)), 404, "video_not_found")
    _problem(api.post("/api/v1/suggestions/generate", json={"video_ids": ["../etc/passwd"]}, headers=hdr(csrf)), 422, "validation_error")
    _problem(api.post("/api/v1/suggestions/generate", json={"video_ids": []}, headers=hdr(csrf)), 422, "validation_error")


def _approved_ids(data, env, clock, n, skip=0):
    with data() as s:
        ids = [x.id for x in approved_many(s, env, clock(), n, skip)]
        s.commit()
    return ids


def test_tc_wb_129_create_batch_requires_key_and_replays(api, csrf, data, env, clock):
    ids = _approved_ids(data, env, clock, 3)
    _problem(api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf)), 400, "idempotency_key_required")
    key = str(uuid.uuid4())
    out = _ok(api.post("/api/v1/batches", json={"suggestion_ids": ids, "note": "테스트"}, headers=hdr(csrf, key)), 201)
    assert set(out) == {"batch", "precheck"} and out["precheck"]["confirm_text"] == "실행 3건" and out["batch"]["status"] == "draft" and out["batch"]["counts"]["pending"] == 3
    assert set(out["batch"]["items"][0]) == {"id", "suggestion_id", "video_id", "video_title", "previous_title", "new_title", "seq", "scheduled_date", "status", "skip_reason", "change_id", "processed_at"}
    again = _ok(api.post("/api/v1/batches", json={"suggestion_ids": ids, "note": "테스트"}, headers=hdr(csrf, key)), 201)
    assert again == out
    with data() as s:
        assert s.execute(select(func.count()).select_from(Batch)).scalar_one() == 1
    _problem(api.post("/api/v1/batches", json={"suggestion_ids": ids[:1]}, headers=hdr(csrf, key)), 422, "idempotency_key_reuse")
    _problem(api.post("/api/v1/batches", json={"suggestion_ids": list(range(1, 52))}, headers=hdr(csrf, str(uuid.uuid4()))), 422, "batch_too_large")
    _problem(api.post("/api/v1/batches", json={"suggestion_ids": [ids[0], ids[0]]}, headers=hdr(csrf, str(uuid.uuid4()))), 422, "duplicate_suggestion")


def test_tc_wb_130_execute_confirm_idempotency_and_cancel(api, csrf, data, env, clock):
    ids = _approved_ids(data, env, clock, 2)
    created = _ok(api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, str(uuid.uuid4()))), 201)
    bid, key = created["batch"]["id"], str(uuid.uuid4())
    _problem(api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 1건"}, headers=hdr(csrf, key)), 422, "confirm_text_mismatch")
    _problem(api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 2건"}, headers=hdr(csrf)), 400, "idempotency_key_required")
    ran = _ok(api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 2건"}, headers=hdr(csrf, key)), 202)   # 실패한 시도의 키를 다시 쓸 수 있다
    assert set(ran) == {"batch", "job"} and ran["batch"]["status"] == "queued" and ran["job"]["type"] == "batch.execute" and ran["job"]["total"] == 2
    assert {i["scheduled_date"] for i in ran["batch"]["items"]} == {"2026-10-10"}
    assert _ok(api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 2건"}, headers=hdr(csrf, key)), 202) == ran
    _problem(api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 2건"}, headers=hdr(csrf, str(uuid.uuid4()))), 409, "batch_not_draft")
    cancelled = _ok(api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf)))
    assert cancelled["status"] == "cancelled" and cancelled["counts"]["cancelled"] == 2
    _problem(api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf)), 409, "batch_not_cancellable")
    _problem(api.post("/api/v1/batches/99999/cancel", headers=hdr(csrf)), 404, "batch_not_found")


def test_tc_wb_131_batch_list_and_detail(api, csrf, data, env, clock):
    ids = _approved_ids(data, env, clock, 2)
    created = _ok(api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, str(uuid.uuid4()))), 201)
    bid = created["batch"]["id"]
    page = _ok(api.get("/api/v1/batches"))
    assert page["total"] == 1 and page["items"][0]["id"] == bid and page["items"][0]["items"] == [] and page["items"][0]["counts"]["pending"] == 2
    detail = _ok(api.get(f"/api/v1/batches/{bid}"))
    assert len(detail["items"]) == 2 and detail["items"][0]["video_title"]
    assert detail["precheck"] == created["precheck"] and page["items"][0]["precheck"] is None   # 새로고침 후 사전 점검 표 복구용
    _problem(api.get("/api/v1/batches/99999"), 404, "batch_not_found")
    _problem(api.get("/api/v1/batches/abc"), 422, "validation_error")


def _applied_change(data, env, clock):
    with data() as s:
        batch, sugs, _ = queued_batch(s, env, clock(), 1)
        out = apply_one(s, batch.items[0].id, now=clock(), env=env, gateway=MockYouTubeGateway(s, clock))
        s.commit()
        return out.change_id, sugs[0].video_id, batch.id


def test_tc_wb_132_changes_list_and_rollback_over_http(api, csrf, data, env, clock):
    cid, vid, bid = _applied_change(data, env, clock)
    page = _ok(api.get(f"/api/v1/changes?video_id={vid}&batch_id={bid}&result=success"))
    row = page["items"][0]
    assert set(row) == {"id", "video_id", "video_title", "change_type", "previous_title", "new_title", "result", "mode", "approver", "applied_at", "verified_at", "error_code", "rollbackable", "batch_id"}
    assert row["rollbackable"] is True and row["mode"] == "demo" and row["video_title"] == row["new_title"]
    key = str(uuid.uuid4())
    _problem(api.post(f"/api/v1/changes/{cid}/rollback", json={"typed_video_id": vid, "approver": "홍길동"}, headers=hdr(csrf)), 400, "idempotency_key_required")
    _problem(api.post(f"/api/v1/changes/{cid}/rollback", json={"typed_video_id": "demoVid9999", "approver": "홍길동"}, headers=hdr(csrf, key)), 422, "typed_video_id_mismatch")
    rb = _ok(api.post(f"/api/v1/changes/{cid}/rollback", json={"typed_video_id": vid, "approver": "홍길동"}, headers=hdr(csrf, key)), 201)
    assert rb["change_type"] == "rollback" and rb["result"] == "success" and rb["new_title"] == row["previous_title"] and rb["rollbackable"] is False
    assert _ok(api.post(f"/api/v1/changes/{cid}/rollback", json={"typed_video_id": vid, "approver": "홍길동"}, headers=hdr(csrf, key)), 201) == rb
    _problem(api.post(f"/api/v1/changes/{cid}/rollback", json={"typed_video_id": vid, "approver": "홍길동"}, headers=hdr(csrf, str(uuid.uuid4()))), 409, "later_change_exists")
    assert _ok(api.get("/api/v1/changes"))["total"] == 2
    with data() as s:
        assert s.execute(select(func.count()).select_from(Change).where(Change.change_type == "rollback")).scalar_one() == 1


def test_tc_wb_133_reports_and_csv_download(api, csrf, data, env, clock):
    cid, vid, _ = _applied_change(data, env, clock)
    rep = _ok(api.get("/api/v1/reports/changes"))
    assert set(rep) == {"items", "notes"} and rep["items"][0]["video_id"] == vid and rep["items"][0]["status"] == "insufficient" and rep["items"][0]["label"] == "데이터 부족"
    assert any("원인이라고 말하지 않습니다" in n for n in rep["notes"])
    assert _ok(api.get(f"/api/v1/reports/changes?video_id={_vid(data, 5)}"))["items"][0]["status"] == "no_change"
    r = api.get("/api/v1/reports/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"] and r.headers["cache-control"] == "no-store"
    assert r.content.startswith("﻿".encode()) and vid.encode() in r.content
    _problem(api.get("/api/v1/reports/changes?video_id=zzzzzzzzzzz"), 404, "video_not_found")
    _problem(api.get("/api/v1/reports/export.csv?video_id=bad"), 422, "validation_error")


def test_tc_wb_134_dashboard_and_google_status(api, csrf, data):
    d = _ok(api.get("/api/v1/dashboard"))
    assert d["mode"] == "demo" and d["live_enabled"] is False and set(d) == {"mode", "live_enabled", "google", "counts", "today", "quota", "active_job", "queue"}
    assert set(d["counts"]) == {"videos", "excluded", "suggested", "approved", "queued", "applied"} and d["today"]["cap"] == 10 and d["quota"]["limit"] == 6000
    g = _ok(api.get("/api/v1/google/status"))
    assert g["mode"] == "demo" and g["connected"] is False and g["message"]


def test_tc_wb_135_jobs_endpoint_errors(api, csrf):
    _problem(api.get(f"/api/v1/jobs/{uuid.uuid4()}"), 404, "job_not_found")
    _problem(api.get("/api/v1/jobs/not-a-uuid"), 422, "validation_error")


def test_tc_wb_136_state_changes_are_audited(api, csrf, data, env, clock):
    sug = _suggest(api, csrf, _vid(data), 1)[0]
    _ok(api.post(f"/api/v1/suggestions/{sug['id']}/approve", json={"approver": "홍길동"}, headers=hdr(csrf)))
    audit = _ok(api.get("/api/v1/audit"))
    actions = [e["action"] for e in audit["items"]]
    assert {"suggestion.generate", "suggestion.approve"} <= set(actions) and audit["chain_ok"] is True
    blob = str(audit)
    assert "approval_hmac" not in blob and sug["plan_hash"] is None
