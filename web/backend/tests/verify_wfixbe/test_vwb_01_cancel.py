"""TC-VWB-001~: 초안 취소(DEF-7-009) 독립 시험 — HTTP 경계(권한·CSRF·출처), 없는 id, 이중 취소, 취소 후 재사용, blocked[] 형태, 감사."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from tests.conftest import ORIGIN
from tests.verify_wfixbe.conftest import approved_ids, hdr, new_key
from ytweb.core import audit
from ytweb.db.models import AuditLog, Batch, BatchItem, Change, Suggestion
from ytweb.domain.batches import run_due_items


def _draft(api, csrf, ids):
    r = api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, new_key()))
    assert r.status_code == 201, r.text
    return r.json()


def _audit_count(factory, action):
    with factory() as s:
        return s.execute(select(func.count()).select_from(AuditLog).where(AuditLog.action == action)).scalar_one()


def test_tc_vwb_001_cancel_requires_session_origin_and_csrf_and_changes_nothing(api, data, env, clock, factory):
    ids = approved_ids(data, env, clock, 2)
    from tests.conftest import login
    csrf = login(api)
    bid = _draft(api, csrf, ids)["batch"]["id"]
    # 출처 없음 / 틀린 출처 / CSRF 없음 / CSRF 틀림 → 모두 403 이고 초안은 그대로
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers={"X-CSRF-Token": csrf})
    assert (r.status_code, r.json()["code"]) == (403, "origin_not_allowed")
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": "http://evil.example", "X-CSRF-Token": csrf})
    assert (r.status_code, r.json()["code"]) == (403, "origin_not_allowed")
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN})
    assert (r.status_code, r.json()["code"]) == (403, "csrf_invalid")
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf + "x"})
    assert (r.status_code, r.json()["code"]) == (403, "csrf_invalid")
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site"})
    assert (r.status_code, r.json()["code"]) == (403, "cross_site_request")
    assert _audit_count(factory, "batch.cancel") == 0
    with factory() as s:
        assert s.get(Batch, bid).status == "draft" and {i.status for i in s.get(Batch, bid).items} == {"pending"}
    # 세션 없음 → 401 session_required (쿠키 없는 새 클라이언트)
    api.cookies.clear()
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert (r.status_code, r.json()["code"]) == (401, "session_required")
    with factory() as s:
        assert s.get(Batch, bid).status == "draft"


@pytest.mark.parametrize("path_id,status,code", [
    (987654, 404, "batch_not_found"), (2**63 - 1, 404, "batch_not_found"),
    (0, 422, "validation_error"), (-1, 422, "validation_error"), ("abc", 422, "validation_error"), ("1.5", 422, "validation_error"),
    (2**63, 422, "validation_error"),
])
def test_tc_vwb_002_cancel_unknown_or_malformed_id(api, csrf, path_id, status, code):
    r = api.post(f"/api/v1/batches/{path_id}/cancel", headers=hdr(csrf))
    assert (r.status_code, r.json()["code"]) == (status, code), r.text[:200]
    assert r.json().get("hint")


def test_tc_vwb_003_http_discard_response_audit_and_suggestion_state(api, csrf, data, env, clock, factory):
    ids = approved_ids(data, env, clock, 3)
    bid = _draft(api, csrf, ids)["batch"]["id"]
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == bid and body["status"] == "cancelled"
    assert body["counts"] == {"pending": 0, "running": 0, "success": 0, "failed": 0, "skipped": 0, "cancelled": 3}
    assert {i["skip_reason"] for i in body["items"]} == {"[cancelled] 사용자가 초안을 버렸습니다."}
    assert {i["status"] for i in body["items"]} == {"cancelled"}
    for sid in ids:
        sg = [x for x in api.get("/api/v1/suggestions", params={"status": "approved"}).json()["items"] if x["id"] == sid]
        assert len(sg) == 1
    au = api.get("/api/v1/audit").json()
    cancel = [x for x in au["items"] if x["action"] == "batch.cancel"]
    assert len(cancel) == 1 and cancel[0]["detail"] == {"cancelled_items": 3, "was_draft": True} and cancel[0]["target_id"] == str(bid)
    assert au.get("chain_ok", True) is True
    with factory() as s:
        assert audit.verify_chain(s)
        assert s.execute(select(func.count()).select_from(Change)).scalar_one() == 0


def test_tc_vwb_004_second_cancel_is_409_and_leaves_state_and_audit_untouched(api, csrf, data, env, clock, factory):
    ids = approved_ids(data, env, clock, 2)
    bid = _draft(api, csrf, ids)["batch"]["id"]
    assert api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf)).status_code == 200
    n_audit = _audit_count(factory, "batch.cancel")
    total = api.get("/api/v1/audit", params={"page_size": 200}).json()["total"]
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf, new_key()))   # 멱등 키를 보내도 무시된다
    assert (r.status_code, r.json()["code"]) == (409, "batch_not_cancellable") and r.json().get("hint")
    assert _audit_count(factory, "batch.cancel") == n_audit == 1
    assert api.get("/api/v1/audit", params={"page_size": 200}).json()["total"] == total
    got = api.get(f"/api/v1/batches/{bid}").json()
    assert got["status"] == "cancelled" and got["counts"]["cancelled"] == 2


def test_tc_vwb_005_cancelled_draft_cannot_be_executed_and_suggestions_reusable_end_to_end(api, csrf, data, env, clock, factory):
    ids = approved_ids(data, env, clock, 2)
    first = _draft(api, csrf, ids)
    bid = first["batch"]["id"]
    api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf))
    r = api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": first["precheck"]["confirm_text"]}, headers=hdr(csrf, new_key()))
    assert (r.status_code, r.json()["code"]) == (409, "batch_not_draft")
    second = _draft(api, csrf, ids)
    assert second["batch"]["id"] != bid and second["precheck"]["blocked"] == [] and second["precheck"]["item_count"] == 2
    ex = api.post(f"/api/v1/batches/{second['batch']['id']}/execute", json={"confirm_text": second["precheck"]["confirm_text"]}, headers=hdr(csrf, new_key()))
    assert ex.status_code == 202
    assert run_due_items(data, clock(), env).success == 2
    with data() as s:
        assert s.execute(select(func.count()).select_from(Change).where(Change.result == "success")).scalar_one() == 2
        assert {s.get(Suggestion, i).status for i in ids} == {"applied"}
        # 취소된 첫 배치의 항목은 반영과 무관하게 cancelled 로 남는다
        assert {i.status for i in s.get(Batch, bid).items} == {"cancelled"}


def test_tc_vwb_006_blocked_entries_shape_batch_id_only_for_already_in_batch(api, csrf, data, env, clock):
    a, b, c = approved_ids(data, env, clock, 3)
    held = _draft(api, csrf, [a])["batch"]["id"]
    with data() as s:   # c 는 승인 취소(거절) 상태로 만들어 다른 사유로 막는다
        s.get(Suggestion, c).status = "rejected"
        s.commit()
    out = _draft(api, csrf, [a, b, c, ])
    blocked = {x["suggestion_id"]: x for x in out["precheck"]["blocked"]}
    assert set(blocked) == {a, c} and out["precheck"]["item_count"] == 1
    assert set(blocked[a]) == {"suggestion_id", "reason", "code", "batch_id"}
    assert blocked[a]["code"] == "already_in_batch" and blocked[a]["batch_id"] == held
    assert blocked[a]["reason"].startswith(f"초안 배치 #{held}에 이미 담겨 있습니다")
    assert set(blocked[c]) == {"suggestion_id", "reason", "code"} and blocked[c]["code"] == "not_approved"
    # 저장된 사전 점검(GET)에도 같은 형태가 남는다
    got = api.get(f"/api/v1/batches/{out['batch']['id']}").json()["precheck"]
    norm = [{k: v for k, v in x.items() if not (k == "batch_id" and v is None)} for x in got["blocked"]]   # GET 은 response_model 때문에 batch_id:null 이 붙는다(DEF-6-001)
    assert norm == out["precheck"]["blocked"]


@pytest.mark.xfail(strict=True, reason="DEF-6-001: GET /batches/{id} 의 precheck.blocked[] 는 already_in_batch 가 아닌 항목에도 batch_id:null 을 싣는다(API.md: already_in_batch 일 때만 있다)")
def test_tc_vwb_011_get_batch_blocked_batch_id_absent_unless_already_in_batch(api, csrf, data, env, clock):
    a, b, c = approved_ids(data, env, clock, 3)
    with data() as s:
        s.get(Suggestion, c).status = "rejected"
        s.commit()
    out = _draft(api, csrf, [a, b, c])
    got = api.get(f"/api/v1/batches/{out['batch']['id']}").json()["precheck"]
    assert got["blocked"] == out["precheck"]["blocked"] and all("batch_id" not in x for x in got["blocked"])


def test_tc_vwb_007_cancel_after_execute_keeps_processed_item_and_cancels_the_rest(api, csrf, data, env, clock, factory):
    from ytweb.core.settings_store import set_web_setting
    with data() as s:
        set_web_setting(s, "daily_apply_cap", 1, now=clock())
        s.commit()
    ids = approved_ids(data, env, clock, 3)
    d = _draft(api, csrf, ids)
    bid = d["batch"]["id"]
    assert api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": d["precheck"]["confirm_text"]}, headers=hdr(csrf, new_key())).status_code == 202
    assert run_due_items(data, clock(), env).success == 1        # 오늘 몫 1건만 반영, 나머지 2건은 내일 이후
    r = api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf))
    assert r.status_code == 200 and r.json()["counts"]["success"] == 1 and r.json()["counts"]["cancelled"] == 2
    au = [x for x in api.get("/api/v1/audit").json()["items"] if x["action"] == "batch.cancel"]
    assert au[0]["detail"] == {"cancelled_items": 2, "was_draft": False}
    with data() as s:
        sts = sorted(s.get(Suggestion, i).status for i in ids)
        assert sts == ["applied", "approved", "approved"]
        assert s.execute(select(func.count()).select_from(Change)).scalar_one() == 1
    clock.advance(days=2)
    assert run_due_items(data, clock(), env).processed == 0       # 취소된 배치의 항목은 더는 반영되지 않는다
    from tests.conftest import login
    csrf = login(api)                                             # 이틀 건너뛰는 동안 유휴 만료됐으므로 다시 로그인
    # 이미 끝난(done/cancelled) 배치의 취소는 409
    assert api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf)).status_code == 409


def test_tc_vwb_008_cancel_touches_only_its_own_batch(api, csrf, data, env, clock, factory):
    ids = approved_ids(data, env, clock, 4)
    b1 = _draft(api, csrf, ids[:2])["batch"]["id"]
    b2 = _draft(api, csrf, ids[2:])["batch"]["id"]
    api.post(f"/api/v1/batches/{b1}/cancel", headers=hdr(csrf))
    with factory() as s:
        assert s.get(Batch, b2).status == "draft" and {i.status for i in s.get(Batch, b2).items} == {"pending"}
        assert s.execute(select(func.count()).select_from(BatchItem).where(BatchItem.status == "cancelled")).scalar_one() == 2


def test_tc_vwb_009_draft_cancel_after_approval_expiry_turns_suggestion_expired_lazily(api, csrf, data, env, clock, factory):
    ids = approved_ids(data, env, clock, 1)
    bid = _draft(api, csrf, ids)["batch"]["id"]
    clock.advance(hours=env.policy.approval_ttl_hours + 1)
    from tests.conftest import login
    csrf = login(api)
    assert api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf)).status_code == 200
    # API.md: "승인이 아직 유효하면 approved, 아니면 expired" — 초안은 queued 가 아니었으므로 지연 만료(조회 시)로 expired 가 된다
    items = api.get("/api/v1/suggestions", params={"video_id": None} if False else {}).json()["items"]
    assert [x["status"] for x in items if x["id"] == ids[0]] == ["expired"]
    out = api.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=hdr(csrf, new_key()))
    assert out.status_code == 422 and out.json()["code"] == "batch_empty"       # 만료된 승인은 새 배치에 담기지 않는다


def test_tc_vwb_010_cancel_draft_of_one_item_leaves_no_active_holder(api, csrf, data, env, clock, factory):
    from ytweb.domain.batches import _active_holder
    ids = approved_ids(data, env, clock, 1)
    bid = _draft(api, csrf, ids)["batch"]["id"]
    with factory() as s:
        assert _active_holder(s, ids[0]) == (bid, "draft")
    api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf))
    with factory() as s:
        assert _active_holder(s, ids[0]) is None
