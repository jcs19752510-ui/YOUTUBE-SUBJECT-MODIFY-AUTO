"""TC-VM-900~: W-FIX-BE(면책·고지, 초안 취소 C-2, Medium 수정) 독립 검증 + 오류 응답 한국어 hint 일괄 점검."""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from tests.verify_m23.conftest import approve_via_api, do_execute, eligible_ids, hdr, make_draft
from ytweb.core import audit, jobs
from ytweb.db.models import AuditLog, Batch, BatchItem, Job, Suggestion
from ytweb.domain import handlers
from ytweb.domain.common import set_default_env
from ytweb.domain.notices import DISCLAIMER
from ytweb.domain.seed import seed_demo

HANGUL = re.compile("[가-힣]")
SPEC = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."


@pytest.fixture
def world(api, csrf, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
        ids = eligible_ids(s, 4)
    return type("W", (), {"api": api, "csrf": csrf, "factory": factory, "env": env, "clock": clock, "ids": ids})


def test_tc_vm_900_disclaimer_text_exact_in_precheck_report_and_csv(world):
    assert DISCLAIMER == SPEC
    sid = approve_via_api(world.api, world.csrf, world.ids[0])
    j = make_draft(world.api, world.csrf, [sid]).json()
    assert j["precheck"]["notice"] == SPEC
    assert world.api.get(f"/api/v1/batches/{j['batch']['id']}").json()["precheck"]["notice"] == SPEC     # 저장된 사전 점검에도 보존
    notes = world.api.get("/api/v1/reports/changes").json()["notes"]
    assert notes[0] == SPEC and len(notes) == 5
    text = world.api.get("/api/v1/reports/export.csv").content.decode("utf-8-sig")
    assert text.count(SPEC) == 1 and any(SPEC in c for row in csv.reader(io.StringIO(text)) for c in row)


def test_tc_vm_901_precheck_always_warns_about_ab_test_and_notice_not_null(world):
    sid = approve_via_api(world.api, world.csrf, world.ids[0])
    pre = make_draft(world.api, world.csrf, [sid]).json()["precheck"]
    assert any("A/B" in w for w in pre["warnings"]) and pre["notice"]


def test_tc_vm_910_cancel_draft_cancels_items_frees_suggestions_audits_was_draft(world):
    sids = [approve_via_api(world.api, world.csrf, v) for v in world.ids[:2]]
    bid = make_draft(world.api, world.csrf, sids).json()["batch"]["id"]
    r = world.api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(world.csrf))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert {i["status"] for i in r.json()["items"]} == {"cancelled"}
    with world.factory() as s:
        assert {x.status for x in s.execute(select(Suggestion).where(Suggestion.id.in_(sids))).scalars()} == {"approved"}
        ev = [a for a in s.execute(select(AuditLog)).scalars() if a.action == "batch.cancel"]
        assert len(ev) == 1 and ev[0].detail["was_draft"] is True and ev[0].detail["cancelled_items"] == 2
        assert audit.verify_chain(s)
        reasons = [i.skip_reason for i in s.execute(select(BatchItem)).scalars()]
        assert all("초안" in x for x in reasons)
    assert make_draft(world.api, world.csrf, sids).status_code == 201                                # 다시 담기 가능


def test_tc_vm_911_second_cancel_and_cancel_of_cancelled_then_execute_are_409_with_hint(world):
    sid = approve_via_api(world.api, world.csrf, world.ids[0])
    j = make_draft(world.api, world.csrf, [sid]).json()
    bid = j["batch"]["id"]
    assert world.api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(world.csrf)).status_code == 200
    r = world.api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(world.csrf))
    assert r.status_code == 409 and HANGUL.search(r.json()["hint"])
    e = do_execute(world.api, world.csrf, bid, j["precheck"]["confirm_text"])
    assert e.status_code == 409 and e.json()["code"] == "batch_not_draft" and HANGUL.search(e.json()["hint"])


def test_tc_vm_912_cancel_unknown_batch_404_and_requires_csrf(world):
    assert world.api.post("/api/v1/batches/99999/cancel", headers=hdr(world.csrf)).status_code == 404
    sid = approve_via_api(world.api, world.csrf, world.ids[0])
    bid = make_draft(world.api, world.csrf, [sid]).json()["batch"]["id"]
    assert world.api.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": "http://127.0.0.1:8080"}).status_code in (401, 403)
    assert world.api.get(f"/api/v1/batches/{bid}").json()["status"] == "draft"


def test_tc_vm_913_cancelling_one_draft_leaves_another_draft_intact(world):
    s1, s2 = (approve_via_api(world.api, world.csrf, v) for v in world.ids[:2])
    b1 = make_draft(world.api, world.csrf, [s1]).json()["batch"]["id"]
    b2 = make_draft(world.api, world.csrf, [s2]).json()["batch"]["id"]
    world.api.post(f"/api/v1/batches/{b1}/cancel", headers=hdr(world.csrf))
    got = world.api.get(f"/api/v1/batches/{b2}").json()
    assert got["status"] == "draft" and {i["status"] for i in got["items"]} == {"pending"}


def test_tc_vm_920_changes_filter_rejects_unknown_result_value_with_422_and_accepts_known(world):
    for ok in ("planned", "success", "failed", "aborted"):
        assert world.api.get(f"/api/v1/changes?result={ok}").status_code == 200
    for bad in ("bogus", "SUCCESS", "", "success;drop"):
        r = world.api.get(f"/api/v1/changes?result={bad}")
        assert r.status_code == 422 and "bogus" not in r.text and "drop" not in r.text


def test_tc_vm_921_stale_batch_job_requeue_boundary_5_minutes(factory, clock):
    with factory() as s:
        j = jobs.enqueue(s, type="batch.execute", payload={"batch_id": 1}, now=clock())
        j.status, j.locked_by, j.locked_at, j.attempts = "running", "w", clock() - timedelta(minutes=5) + timedelta(seconds=1), 1
        s.commit()
        assert jobs.requeue_stale(s, now=clock())[0] == 0                       # 4분 59초: 아직 살아 있음
        j.locked_at = clock() - timedelta(minutes=5)
        s.commit()
        assert jobs.requeue_stale(s, now=clock())[0] == 0                       # 정확히 5분: 경계는 '초과'일 때만 고아
        j.locked_at = clock() - timedelta(minutes=5, seconds=1)
        s.commit()
        assert jobs.requeue_stale(s, now=clock())[0] == 1


# ---------- 오류 응답 hint 일괄 ----------
def test_tc_vm_930_error_responses_across_new_endpoints_all_have_korean_title_and_hint(gapp, csrf, client_file, fg):
    """connect/connect-write(파일 없음), callback 크기 초과, 세션 없음, CSRF 없음 등 — 사용자가 다음 행동을 알 수 있는 한국어 hint 가 있는가."""
    client_file.unlink()
    rs = {
        "connect_missing": gapp.post("/api/v1/google/connect", headers=hdr(csrf)),
        "connect_write_missing": gapp.post("/api/v1/google/connect-write", headers=hdr(csrf)),
        "callback_too_long": gapp.get("/api/v1/google/callback?code=" + "a" * 2049 + "&state=x", follow_redirects=False),
        "no_csrf": gapp.post("/api/v1/google/connect", headers={"Origin": "http://127.0.0.1:8080"}),
    }
    miss = {k: (r.status_code, r.text[:160]) for k, r in rs.items() if r.status_code >= 400 and not (HANGUL.search(r.json().get("hint", "") if r.headers.get("content-type", "").startswith("application") else ""))}
    assert miss == {}, miss
