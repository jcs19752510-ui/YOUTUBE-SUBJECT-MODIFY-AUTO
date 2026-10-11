"""TC-VFB-070~: 면책·고지 문구의 서버 쪽(DEF-9-007·008): 리포트 notes·CSV·사전 점검 notice."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from ytweb.db.models import Batch
from ytweb.domain import handlers
from ytweb.domain.common import set_default_env
from ytweb.domain.notices import DISCLAIMER
from ytweb.domain.reports import CAUSAL_NOTE, EXTRA_NOTE, LIMIT_NOTE, SOURCE_NOTE
from ytweb.domain.seed import seed_demo

from tests.verify_fix_be.http_helpers import approved_via_api, draft

SPEC = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."     # 기획서(02_planning)·CLI(ui.py) 원문
import os
ROOT = Path(os.environ.get("VFB_REPO_ROOT") or Path(__file__).resolve().parents[4])


@pytest.fixture
def world(api, csrf, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    return api


def test_tc_vfb_070_disclaimer_text_equals_planning_cli_and_frontend_sources():
    assert DISCLAIMER == SPEC
    ui = (ROOT / "src/youtube_title/ui.py").read_text(encoding="utf-8")
    ko = (ROOT / "web/frontend/src/i18n/ko.ts").read_text(encoding="utf-8")
    assert SPEC in ui and SPEC in ko                       # 서버·CLI·화면 세 곳이 같은 문장(분기 시 사용자에게 다른 고지가 나감)


def test_tc_vfb_071_report_api_notes_lead_with_disclaimer_and_keep_existing_notes(world):
    r = world.get("/api/v1/reports/changes")
    assert r.status_code == 200
    assert r.json()["notes"] == [SPEC, LIMIT_NOTE, CAUSAL_NOTE, EXTRA_NOTE, SOURCE_NOTE]
    r2 = world.get("/api/v1/reports/changes?video_id=demoVid0001")
    assert r2.json()["notes"][0] == SPEC


def test_tc_vfb_072_csv_export_contains_disclaimer_row_exactly_once(world):
    r = world.get("/api/v1/reports/export.csv")
    assert r.status_code == 200, r.text
    text = r.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    flat = [c for row in rows for c in row]
    assert flat.count(SPEC) == 1 and text.count(SPEC) == 1
    assert rows[-5][0] == SPEC            # 주석 행 5개의 첫 번째


def test_tc_vfb_073_precheck_notice_in_create_response_and_in_get(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 2)
    r = draft(world, csrf, ids)
    assert r.json()["precheck"]["notice"] == SPEC
    bid = r.json()["batch"]["id"]
    got = world.get(f"/api/v1/batches/{bid}").json()
    assert got["precheck"]["notice"] == SPEC
    lst = world.get("/api/v1/batches").json()["items"][0]
    assert lst["id"] == bid


def test_tc_vfb_074_legacy_precheck_without_notice_reads_back_as_null_not_500(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 1)
    bid = draft(world, csrf, ids).json()["batch"]["id"]
    with factory() as s:
        b = s.get(Batch, bid)
        old = dict(b.precheck); old.pop("notice")
        b.precheck = old
        s.commit()
    r = world.get(f"/api/v1/batches/{bid}")
    assert r.status_code == 200 and r.json()["precheck"]["notice"] is None


def test_tc_vfb_075_notice_is_server_constant_not_user_controllable(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 1)
    r = world.post("/api/v1/batches", json={"suggestion_ids": ids, "note": "<b>내 고지</b>", "notice": "가짜"},
                   headers={"Origin": "http://127.0.0.1:8080", "X-CSRF-Token": csrf, "Idempotency-Key": "k" * 16})
    assert r.status_code in (201, 422)
    if r.status_code == 201:
        assert r.json()["precheck"]["notice"] == SPEC


def test_tc_vfb_076_precheck_keeps_other_warnings_including_ab_test_notice(world, csrf, factory):
    ids = approved_via_api(world, csrf, factory, 1)
    pre = draft(world, csrf, ids).json()["precheck"]
    assert any("A/B" in w for w in pre["warnings"]) and pre["confirm_text"] == "실행 1건"


def test_tc_vfb_077_openapi_declares_notice_and_blocked_batch_id(dapp):
    spec = dapp.openapi()
    props = spec["components"]["schemas"]["PrecheckOut"]["properties"]
    assert "notice" in props
    assert "batch_id" in spec["components"]["schemas"]["BlockedItem"]["properties"]


def test_tc_vfb_078_docs_openapi_json_matches_live_app_for_changed_schemas(dapp):
    doc = json.loads((ROOT / "docs/yt/openapi.json").read_text(encoding="utf-8"))
    live = dapp.openapi()
    for name in ("PrecheckOut", "BlockedItem", "BatchCreateIn"):
        assert doc["components"]["schemas"][name] == live["components"]["schemas"][name], name
    for path in ("/api/v1/batches/{batch_id}", "/api/v1/batches/{batch_id}/cancel", "/api/v1/changes", "/api/v1/suggestions"):
        assert doc["paths"][path] == live["paths"][path], path
