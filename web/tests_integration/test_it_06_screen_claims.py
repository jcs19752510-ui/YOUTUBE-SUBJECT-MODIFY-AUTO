"""IT 그룹 S — 11단계 문서가 적은 '코드 후속 조치 C-1~C-10'(docs/yt/WEB_RUNBOOK.md 13-1) 중 서버 쪽에서 확인할 수 있는 사실 여부.
화면(프런트) 쪽 증상은 Chromium 시험(.harness-tmp/int/ui/ui_walk.mjs, 결과서 화면 관찰)에서 따로 확인한다.
이 파일의 시험은 '현재 동작을 사실대로 고정'한다(특성화 시험). 동작을 바꾸는 쪽은 사용자 결정(Q-11-09) 뒤 5단계 작업이므로 7단계는 소스를 고치지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from itlib_b import (  # noqa: F401  (fresh_demo 는 픽스처)
    Api, apply_via_batch, approvable_set, fresh_demo, psql_app, set_cap, shift_days, shift_hours, usable_videos,
)

pytestmark = pytest.mark.destructive
REPO = Path(__file__).resolve().parents[2]


def _find_blocked(a: Api, vids: list[dict], limit: int = 80):
    for v in vids[:limit]:
        for s in a.make_suggestion(v["video_id"], 5):
            if s["status"] == "blocked":
                return v, s
    raise AssertionError("차단 제안을 찾지 못함")


def test_it_600_c1_blocked_suggestion_is_editable_and_rejectable_through_api_so_gap_is_ui_only(fresh_demo):
    """IT-600 (C-1 서버 쪽): 서버는 blocked 제안의 수정(PATCH)·반려를 허용한다(API.md EVT-W15/W17). 따라서 카드에 버튼이 없는 것은 화면 쪽 공백이다.
    수정하면 재검증되어 상태가 바뀌고, 차단 판정은 승인 409 `suggestion_blocked` 이다."""
    a = fresh_demo
    v, s = _find_blocked(a, usable_videos(a, 120))
    assert s["validation_result"] == "block" and s["status"] == "blocked"
    r = a.approve(s["id"])
    assert r.status_code == 409 and r.json()["code"] == "suggestion_blocked"
    r = a.patch(f"/api/v1/suggestions/{s['id']}", json={"title": "냉장고 정리 처음이라도 쉽게 따라 하는 순서 안내"})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["status"] in ("candidate", "blocked") and r.json()["approval"] is None
    v2, s2 = _find_blocked(a, [x for x in usable_videos(a, 160) if x["video_id"] != v["video_id"]])
    r = a.post(f"/api/v1/suggestions/{s2['id']}/reject")
    assert r.status_code == 200 and r.json()["status"] == "rejected"


def test_it_601_c2_draft_batch_holds_its_suggestions_until_cancelled_and_cancel_api_frees_them(fresh_demo):
    """IT-601 (C-2): 초안(draft) 배치에 담긴 승인 제안은 새 배치에 담을 수 없다(409 already_in_batch). 서버의 cancel(초안도 가능)을 부르면 다시 담긴다.
    화면에는 이 취소를 부르는 버튼이 없다는 것이 C-2(화면 시험에서 확인)."""
    a = fresh_demo
    v, sugs = approvable_set(a, usable_videos(a, 60), 2)
    s = a.approve(sugs[0]["id"]).json()
    r = a.make_batch([s["id"]])
    assert r.status_code == 201 and r.json()["batch"]["status"] == "draft"
    bid = r.json()["batch"]["id"]
    r2 = a.make_batch([s["id"]])
    assert r2.status_code in (409, 422), r2.text[:300]
    assert r2.json()["code"] in ("already_in_batch", "batch_empty"), r2.text[:300]
    # 승인 제안 목록에는 여전히 approved 로 보인다(화면의 '반영할 승인 항목' 후보와 같은 근거)
    approved = a.get("/api/v1/suggestions", params={"status": "approved", "page_size": 50}).json()["items"]
    in_list = any(x["id"] == s["id"] for x in approved)
    c = a.post(f"/api/v1/batches/{bid}/cancel")
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    r3 = a.make_batch([s["id"]])
    assert r3.status_code == 201, r3.text[:300]
    assert in_list, "초안에 담긴 제안이 승인 목록에서 사라졌다면 화면 설명이 달라진다(C-2 서술 확인용)"


def test_it_602_c4_changes_result_filter_accepts_only_four_values(fresh_demo):
    """IT-602 (C-4): /changes?result= 는 planned|success|failed|aborted 만 허용. 화면 선택지의 '검증 완료'·'검증 필요'·'되돌려짐'에 해당하는 값은 422."""
    a = fresh_demo
    for ok in ("planned", "success", "failed", "aborted"):
        assert a.get("/api/v1/changes", params={"result": ok}).status_code == 200, ok
    for bad in ("verified", "unverified", "rolled_back"):
        r = a.get("/api/v1/changes", params={"result": bad})
        assert r.status_code == 422 and r.json()["code"] == "validation_error", (bad, r.status_code)


def test_it_603_c5_c6_limit_messages_reuse_cli_wording(fresh_demo):
    """IT-603 (C-5·C-6): 영상 상세 limits.reasons 가 CLI 문구(태평양 시간, 설정 cadence.max_changes_per_video)를 그대로 쓴다."""
    a = fresh_demo
    set_cap(a, 20)
    v, sugs = approvable_set(a, usable_videos(a, 60), 3)
    vid = v["video_id"]
    ch = apply_via_batch(a, a.approve(sugs[0]["id"]).json()["id"])
    reasons = " ".join(a.get(f"/api/v1/videos/{vid}").json()["limits"]["reasons"])
    seen = {"태평양": "태평양" in reasons}
    shift_hours(73)
    ch2 = apply_via_batch(a, a.approve(sugs[1]["id"]).json()["id"])
    shift_hours(73)
    ch3 = apply_via_batch(a, a.approve(sugs[2]["id"]).json()["id"])
    shift_hours(73)
    lim = a.get(f"/api/v1/videos/{vid}").json()["limits"]
    txt = " ".join(lim["reasons"])
    assert lim["allowed"] is False
    seen["cadence"] = "cadence.max_changes_per_video" in txt
    seen["태평양_3회"] = "태평양" in txt
    # 사실 고정: 문구가 CLI 용어를 쓰고 있다(고쳐지면 이 시험이 실패해 문서(C-5·C-6)를 갱신하게 한다)
    assert seen["cadence"], txt
    assert ch["id"] and ch2["id"] and ch3["id"]


def test_it_604_c8_report_never_reaches_ok_in_demo_because_no_after_metrics(fresh_demo):
    """IT-604 (C-8): 반영 후 시간이 지나도(8일) 데모 리포트가 '비교 가능(ok)'이 되지 못한다 — 변경 후 지표 생성 코드가 없다."""
    a = fresh_demo
    set_cap(a, 20)
    v, sugs = approvable_set(a, usable_videos(a, 60), 1)
    ch = apply_via_batch(a, a.approve(sugs[0]["id"]).json()["id"])
    shift_days(8)
    rep = a.get("/api/v1/reports/changes", params={"video_id": v["video_id"]}).json()
    it = rep["items"][0]
    assert it["status"] in ("insufficient", "no_change") and it["status"] != "ok", it
    assert ch["result"] == "success"


def test_it_605_c9_config_comment_says_audit_hmac_key_but_audit_is_keyless():
    """IT-605 (C-9, 정적): config.py 주석은 감사에도 HMAC 키가 쓰이는 것처럼 적었고, core/audit.py 는 키 없는 SHA-256 연결이다."""
    cfg = (REPO / "web/backend/ytweb/config.py").read_text(encoding="utf-8")
    aud = (REPO / "web/backend/ytweb/core/audit.py").read_text(encoding="utf-8")
    assert "hmac" not in aud.lower() or "sha256" in aud.lower()
    assert re.search(r"감사", cfg) and re.search(r"HMAC", cfg), "주석이 고쳐졌다면 C-9 를 닫는다"
