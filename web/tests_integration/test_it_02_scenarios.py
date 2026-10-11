"""IT 그룹 E — 사용자 시나리오 End-to-End(IT-100~IT-120). 실제 5개 컨테이너를 nginx 주소로 두드린다.

각 시나리오는 단위 시험이 따로 본 것을 되풀이하지 않고 '단위 사이를 지나는' 값(승인 → 배치 → 워커 → 이력 → 롤백 → 리포트 → 감사)이
서로 맞물리는지를 본다. 시나리오마다 DB 를 초기화한다(reset-demo 경로: web/api/worker 정지 → reset-schema → up).
"""
from __future__ import annotations

import csv
import io
import json
import time
from datetime import date, datetime, timedelta, timezone

import pytest

import itlib_b as ib
from itlib_b import (  # noqa: F401  (fresh_demo 는 픽스처)
    Api, apply_via_batch, approvable_set, approve_many, approved_suggestion, forge_approval_expiry, fresh_demo, mark_video_title, psql_app, psql_owner,
    rollback, server_logs, set_cap, shift_days, shift_hours, two_pass_suggestions, usable_videos, wait_healthy, worker_start, worker_stop,
)

pytestmark = pytest.mark.destructive


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ─────────────────────────── IT-100 전체 정상 흐름 ───────────────────────────

def test_it_100_full_happy_path_demo_to_report(fresh_demo):
    """IT-100: 데모 영상 불러오기 → AI 제안(모의) 생성 → 검증 → 사람 승인(승인자 이름) → 배치·사전 점검 → 확인 문구 실행 → 워커 처리 → 이력
    → 롤백(영상 ID 직접 입력) → 리포트·CSV → 감사 체인. 검증: W-001~W-014, W-017, S-W03, S-W12, S-W16, NFR-W03"""
    a = fresh_demo
    d = a.get("/api/v1/dashboard").json()
    assert d["mode"] == "demo" and d["live_enabled"] is False and d["google"] == {"mode": "demo", "connected": False}
    assert d["counts"]["videos"] == 200 and d["counts"]["excluded"] == 37
    # 영상 목록: 검색·정렬·필터가 nginx 를 지나도 한글·쿼리 보존
    vs = a.videos()
    assert len(vs) == 200 and sum(v["excluded"] for v in vs) == 37
    ok = [v for v in vs if not v["excluded"]]
    pick = ok[:4]
    # 제안 생성은 작업(202) → 워커가 처리 → 폴링
    r = a.post("/api/v1/suggestions/generate", json={"video_ids": [v["video_id"] for v in pick], "count": 2})
    assert r.status_code == 202
    j = a.wait_job(r.json()["id"])
    assert j["status"] == "succeeded" and j["result"]["videos"] == 4, j
    sugs = a.get("/api/v1/suggestions", params={"page_size": 50}).json()["items"]
    assert len(sugs) >= 4 and {s["source"] for s in sugs} == {"ai:mock"}
    assert {s["validation_result"] for s in sugs} <= {"pass", "warn", "block"}
    # 영상별 가장 좋은 제안 승인(차단 제외), 승인자 이름이 이력까지 흘러가는지 본다
    approved = [approved_suggestion(a, v["video_id"], "홍길동") for v in pick[:3]]
    for s in approved:
        assert s["status"] == "approved" and s["plan_hash"] and s["approval"]["approver"] == "홍길동"
        ttl = _parse_ts(s["approval"]["expires_at"]) - _parse_ts(s["approval"]["approved_at"])
        assert timedelta(hours=23, minutes=59) <= ttl <= timedelta(hours=24, minutes=1)
    r = a.make_batch([s["id"] for s in approved], note="IT-100")
    assert r.status_code == 201
    batch, pre = r.json()["batch"], r.json()["precheck"]
    assert batch["status"] == "draft" and pre["item_count"] == 3 and pre["estimated_units"] == 156 and pre["confirm_text"] == "실행 3건"
    assert pre["daily_cap"] == 10 and pre["quota_remaining_units"] == 6000 and sum(x["count"] for x in pre["schedule"]) == 3
    # 새로고침 복구: 단건 조회에도 사전 점검이 그대로 실려 있다(V-19)
    g = a.get(f"/api/v1/batches/{batch['id']}").json()
    assert g["precheck"]["confirm_text"] == "실행 3건" and g["status"] == "draft"
    # 확인 문구 오류는 아무것도 바꾸지 않는다(대소문자·공백·건수 불일치)
    for bad in ("실행 3건 ", "실행3건", "실행 2건", "", "RUN 3"):
        r = a.post(f"/api/v1/batches/{batch['id']}/execute", json={"confirm_text": bad}, idem=True)
        assert r.status_code == 422 and r.json()["code"] == "confirm_text_mismatch", (bad, r.text[:200])
    g = a.get(f"/api/v1/batches/{batch['id']}").json()
    assert g["status"] == "draft" and g["counts"]["pending"] == 3
    # 실행
    r = a.execute(batch["id"], 3)
    assert r.status_code == 202 and r.json()["job"]["type"] == "batch.execute"
    done = a.wait_batch(batch["id"])
    assert done["status"] == "done" and done["counts"]["success"] == 3, done["counts"]
    assert a.wait_job(r.json()["job"]["id"])["status"] == "succeeded"
    # 단위 간 정합: 영상 제목·상태·이력·승인 소진·쿼터·대시보드
    after = {v["video_id"]: v for v in a.videos()}
    chs = a.get("/api/v1/changes", params={"batch_id": batch["id"]}).json()["items"]
    assert len(chs) == 3
    for c in chs:
        assert c["result"] == "success" and c["mode"] == "demo" and c["approver"] == "홍길동" and c["rollbackable"] and c["change_type"] == "apply"
        assert after[c["video_id"]]["title"] == c["new_title"] != c["previous_title"]
        assert after[c["video_id"]]["workflow_status"] == "applied"
    used = psql_app("select count(*) from approvals where used_at is not null")
    assert used == "3"
    d = a.get("/api/v1/dashboard").json()
    assert d["today"]["applied"] == 3 and d["quota"]["used"] == 156 and d["quota"]["remaining"] == 5844 and d["queue"]["pending_items"] == 0
    # 롤백: 틀린 ID → 422(상태 불변), 맞는 ID → 201, 다시 → 409
    c0 = chs[0]
    r = a.post(f"/api/v1/changes/{c0['id']}/rollback", json={"typed_video_id": "demoVid0099", "approver": "홍길동"}, idem=True)
    assert r.status_code == 422 and r.json()["code"] == "typed_video_id_mismatch"
    assert {v["video_id"]: v for v in a.videos()}[c0["video_id"]]["title"] == c0["new_title"]
    r = a.post(f"/api/v1/changes/{c0['id']}/rollback", json={"typed_video_id": c0["video_id"], "approver": "홍길동"}, idem=True)
    assert r.status_code == 201 and r.json()["change_type"] == "rollback" and r.json()["new_title"] == c0["previous_title"]
    assert {v["video_id"]: v for v in a.videos()}[c0["video_id"]]["title"] == c0["previous_title"]
    r = a.post(f"/api/v1/changes/{c0['id']}/rollback", json={"typed_video_id": c0["video_id"], "approver": "홍길동"}, idem=True)
    assert r.status_code == 409
    # 재동기화는 앱이 바꾼 제목을 되돌리지 않는다(BE-B 시드 ↔ 변경 이력)
    snaps0 = psql_app("select count(*) from metrics_snapshots")
    j = a.sync_demo()
    assert j["status"] == "succeeded" and j["result"]["total"] == 200 and j["result"]["created"] == 0 and j["result"]["updated"] == 200
    assert j["result"]["snapshots_created"] == 0 and psql_app("select count(*) from metrics_snapshots") == snaps0, "재동기화가 변경 전 기준선(스냅샷)을 다시 만들었다"
    now = {v["video_id"]: v for v in a.videos()}
    for c in chs[1:]:
        assert now[c["video_id"]]["title"] == c["new_title"]
    # 리포트·CSV
    rep = a.get("/api/v1/reports/changes").json()
    assert any("단정" in n or "원인" in n for n in rep["notes"]) and any("가상" in n for n in rep["notes"])
    by = {x["video_id"]: x for x in rep["items"]}
    assert by[c0["video_id"]]["status"] == "insufficient" and by[c0["video_id"]]["reasons"]   # 롤백이 끼면 결론 없음
    r = a.get("/api/v1/reports/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and 'filename="ytitle-report.csv"' in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert {x["video_id"] for x in rows} >= {c["video_id"] for c in chs}
    # 감사: 단계마다 기록, 행위자 구분, 체인 정상
    au = a.get("/api/v1/audit", params={"page_size": 200}).json()
    acts = [x["action"] for x in au["items"]]
    for must in ("session.create", "videos.sync", "suggestion.approve", "batch.create", "batch.execute", "change.apply", "change.rollback"):
        assert must in acts, (must, sorted(set(acts)))
    assert au["chain_ok"] is True
    actors = {x["actor"] for x in au["items"]}
    assert "worker" in actors and ("owner" in actors or "web" in actors)
    blob = json.dumps(au["items"], ensure_ascii=False)
    assert "pin" not in blob.lower() or '"pin": "' not in blob  # PIN 값은 감사에 없다


# ─────────────────────────── IT-101 차단·경고·제외·수정 경로 ───────────────────────────

def test_it_101_block_warn_strict_excluded_and_edit_paths(fresh_demo):
    """IT-101: 차단 제안은 승인 불가(409), 경고는 승인 가능하고 사전 점검에 경고가 실린다, 엄격 모드(건강·금융)는 경고도 차단,
    제외 영상은 제안 단계에서 409, 승인 후 제목 수정은 승인을 무효로 하며 배치에 담기지 않는다. 검증: W-004, W-005, W-007, W-008, POL"""
    a = fresh_demo
    vs = a.videos()
    ok = [v for v in vs if not v["excluded"]]
    ex = [v for v in vs if v["excluded"]]
    # 제외 영상: 단건 → 409 video_excluded, 일괄 → 작업은 성공하되 result.skipped 에 코드
    r = a.post(f"/api/v1/videos/{ex[0]['video_id']}/suggestions", json={"count": 1})
    assert r.status_code == 409 and r.json()["code"] == "video_excluded"
    r = a.post("/api/v1/suggestions/generate", json={"video_ids": [ex[0]["video_id"], ok[0]["video_id"]], "count": 1})
    j = a.wait_job(r.json()["id"])
    assert j["status"] == "succeeded" and [x["code"] for x in j["result"]["skipped"]] == ["video_excluded"], j
    # 후보 분포 수집(모의 제안기는 결정적)
    seen: dict[tuple, dict] = {}
    for v in ok[:14]:
        for s in a.make_suggestion(v["video_id"], 3):
            seen.setdefault((s["validation_result"], s["strict"]), s)
    assert ("block", False) in seen and ("warn", False) in seen and ("pass", False) in seen, list(seen)
    # 차단: 승인 409, 상태 변하지 않음
    blk = seen[("block", False)]
    r = a.approve(blk["id"])
    assert r.status_code == 409 and r.json()["code"] == "suggestion_blocked"
    assert a.get("/api/v1/suggestions", params={"video_id": blk["video_id"], "status": "blocked"}).json()["total"] >= 1
    # 엄격 모드: block 은 물론 'pass 가 아니면' 승인 불가
    for (res, strict), s in seen.items():
        if strict and res != "pass":
            r = a.approve(s["id"])
            assert r.status_code == 409 and r.json()["code"] == "suggestion_blocked", (res, strict, r.text[:200])
    assert any(strict for (_, strict) in seen), "엄격 모드(건강·금융) 제안이 표본에 없음"
    # 경고: 승인되고, 사전 점검 warnings 에 표시
    w = seen[("warn", False)]
    r = a.approve(w["id"], "경고확인자")
    assert r.status_code == 200 and r.json()["status"] == "approved"
    p = seen[("pass", False)]
    pv = p["video_id"] if p["video_id"] != w["video_id"] else None
    if pv is None:  # 같은 영상이면 다른 영상의 통과 제안을 쓴다
        others = [s for (res, st), s in seen.items() if res == "pass" and s["video_id"] != w["video_id"]]
        p = others[0] if others else approved_suggestion(a, ok[20]["video_id"])
    r = a.approve(p["id"], "승인자2")
    assert r.status_code == 200
    r = a.make_batch([w["id"], p["id"]])
    assert r.status_code == 201
    assert any("경고" in x for x in r.json()["precheck"]["warnings"])
    bid = r.json()["batch"]["id"]
    # 같은 영상의 제안 두 개를 한 배치에 → 하나는 duplicate_video 로 blocked(영상당 한 번에 한 제목)
    two = two_pass_suggestions(a, ok[40:70])
    for x in two:
        assert a.approve(x["id"]).status_code == 200
    r2 = a.make_batch([x["id"] for x in two])
    assert r2.status_code == 201 and r2.json()["precheck"]["item_count"] == 1
    assert [b["code"] for b in r2.json()["precheck"]["blocked"]] == ["duplicate_video"]
    assert a.post(f"/api/v1/batches/{r2.json()['batch']['id']}/cancel").status_code == 200
    # 승인 후 제목 수정 → 승인 무효, 배치 담기 불가, 다시 승인하면 담김
    x = approved_suggestion(a, ok[30]["video_id"])
    r = a.patch(f"/api/v1/suggestions/{x['id']}", json={"title": x["title"] + " 수정"})
    assert r.status_code == 200 and r.json()["approval"] is None and r.json()["status"] in ("candidate", "blocked")
    r = a.make_batch([x["id"]])
    assert r.status_code == 422 and r.json()["code"] == "batch_empty", r.text[:300]
    if r.json().get("detail"):
        assert "승인" in r.json()["detail"] or "상태" in r.json()["detail"]
    # 취소하면 담긴 제안이 승인 대기로 돌아온다
    r = a.post(f"/api/v1/batches/{bid}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    got = {s["id"]: s for s in a.get("/api/v1/suggestions", params={"status": "approved", "page_size": 100}).json()["items"]}
    assert w["id"] in got and p["id"] in got


# ─────────────────────────── IT-102 승인 만료 ───────────────────────────

def test_it_102_approval_expiry_across_units(fresh_demo):
    """IT-102: 승인 24시간 만료 경로. (a) 만료된 승인은 배치에 담기지 않고 제안이 expired 로 바뀐다 (b) 다시 승인하면 새 유효 시간으로 담긴다
    (c) 실행 확정 뒤 승인이 만료돼도(DEC-042 D1: 기준 시각=실행 확정 시각) 이미 확정된 항목은 반영된다. 검증: W-007, W-008, SEC-W17"""
    a = fresh_demo
    ok = usable_videos(a, 3)
    s1, s2, s3 = approve_many(a, ok)
    forge_approval_expiry(s1["id"])
    r = a.make_batch([s1["id"]])
    assert r.status_code == 422 and r.json()["code"] == "batch_empty", r.text[:300]
    # 대시보드·목록 호출이 만료를 확정(expired)한다
    a.get("/api/v1/dashboard")
    got = a.get("/api/v1/suggestions", params={"video_id": s1["video_id"]}).json()["items"]
    assert [x["status"] for x in got if x["id"] == s1["id"]] == ["expired"]
    # 재승인
    r = a.approve(s1["id"], "재승인자")
    assert r.status_code == 200 and r.json()["approval"]["approver"] == "재승인자"
    assert _parse_ts(r.json()["approval"]["expires_at"]) > datetime.now(timezone.utc) + timedelta(hours=23)
    # (c) 워커를 멈추고 실행 확정 → 승인을 만료 시각 이후로 옮김 → 워커 재시작
    worker_stop()
    try:
        r = a.make_batch([s1["id"], s2["id"]])
        assert r.status_code == 201
        bid = r.json()["batch"]["id"]
        forge_approval_expiry(s2["id"], expires_in_seconds=25)      # 지금은 아직 유효(만료까지 25초)
        assert a.execute(bid, 2).status_code == 202                  # 확정 시각 T: 두 승인 모두 유효
        time.sleep(30)                                               # 워커는 멈춰 있고 s2 의 승인은 이 사이에 만료된다
        assert a.get(f"/api/v1/batches/{bid}").json()["counts"]["pending"] == 2
    finally:
        worker_start()
    done = a.wait_batch(bid, timeout=90)
    assert done["counts"]["success"] == 2, done["counts"]       # 기준 시각=확정 시각이라 반영된다(DEC-042 D1/D3 수용 동작)
    # 확정 전(초안)에서 만료되면 실행이 거부된다: precheck_stale
    r = a.make_batch([s3["id"]])
    bid3 = r.json()["batch"]["id"]
    forge_approval_expiry(s3["id"])
    r = a.execute(bid3, 1)
    assert r.status_code == 409 and r.json()["code"] == "precheck_stale", r.text[:300]


# ─────────────────────────── IT-103 하루 한도·이월 ───────────────────────────

def test_it_103_daily_cap_carry_over_and_no_catch_up(fresh_demo):
    """IT-103: 하루 상한(설정 화면 값)이 배치 일정·워커 처리·대시보드에 일관되게 적용된다. 상한 2·항목 5 → 오늘 2건만 반영, 나머지는 예약만 남고
    (놓친 예약 몰아서 실행 금지) 다음 날 계산이 되면 2건씩 이어서 처리. 검증: W-008, W-010, S-W12, NFR-W06(하루 상한)"""
    a = fresh_demo
    set_cap(a, 2)
    ok = usable_videos(a, 5)
    ap = approve_many(a, ok)
    r = a.make_batch([s["id"] for s in ap])
    pre = r.json()["precheck"]
    assert [x["count"] for x in pre["schedule"]] == [2, 2, 1] and pre["daily_cap"] == 2
    bid = r.json()["batch"]["id"]
    assert a.execute(bid, 5).status_code == 202
    t0 = time.time()
    while time.time() - t0 < 40:
        b = a.get(f"/api/v1/batches/{bid}").json()
        if b["counts"]["success"] >= 2:
            break
        time.sleep(0.5)
    assert b["counts"]["success"] == 2
    time.sleep(7)                          # 워커 틱(2초)을 여러 번 지나도 더 처리하지 않는다
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert b["counts"]["success"] == 2 and b["counts"]["pending"] == 3 and b["status"] in ("queued", "running")
    d = a.get("/api/v1/dashboard").json()
    assert d["today"] == {"applied": 2, "cap": 2} and d["queue"]["pending_items"] == 3 and d["queue"]["next_run_date"]
    # 상한을 올리면(오늘 몫이 생기면) 같은 배치의 오늘 도래분이 이어서 처리되는지: 도래분은 오늘 날짜 2건 이후라 아직 예약 전
    set_cap(a, 3)
    time.sleep(5)
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert b["counts"]["success"] == 2, "예정일이 아직 안 된 항목은 상한을 올려도 앞당겨지지 않는다"
    set_cap(a, 2)
    # '다음 날'이 되었다고 치고(예약·이력 하루 당김) → 2건 더
    shift_days(1)
    t0 = time.time()
    while time.time() - t0 < 40:
        b = a.get(f"/api/v1/batches/{bid}").json()
        if b["counts"]["success"] >= 4:
            break
        time.sleep(0.5)
    assert b["counts"]["success"] == 4 and b["counts"]["pending"] == 1
    time.sleep(6)
    assert a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] == 4   # 같은 날 몫(2) 소진 → 마지막 1건은 또 다음 날
    shift_days(1)
    b = a.wait_batch(bid, timeout=60)
    assert b["status"] == "done" and b["counts"] == {"pending": 0, "running": 0, "success": 5, "failed": 0, "skipped": 0, "cancelled": 0}
    # 영상마다 반영은 정확히 한 번
    assert psql_app("select max(c) from (select count(*) c from changes where change_type='apply' and result='success' group by video_id) t") == "1"
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == "5"


def test_it_103b_cap_lowered_after_execute_follows_cap(fresh_demo):
    """IT-103b: 실행 확정 뒤(워커 정지 중) 하루 상한을 낮추면 워커는 낮아진 상한까지만 처리하고 나머지는 대기한다(설정 ↔ 워커 경계). 검증: W-008, W-014"""
    a = fresh_demo
    ok = usable_videos(a, 3)
    ap = approve_many(a, ok)
    worker_stop()
    try:
        bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
        assert a.execute(bid, 3).status_code == 202
        set_cap(a, 1)
    finally:
        worker_start()
    t0 = time.time()
    while time.time() - t0 < 40:
        b = a.get(f"/api/v1/batches/{bid}").json()
        if b["counts"]["success"] >= 1:
            break
        time.sleep(0.5)
    time.sleep(6)
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert b["counts"]["success"] == 1 and b["counts"]["pending"] == 2 and b["counts"]["failed"] == 0 and b["counts"]["skipped"] == 0, b["counts"]
    # 남은 2건은 '오늘 예약' 그대로 대기한다(내일로 이월되지 않는다) — 상한을 다시 올리면 곧바로 이어서 처리된다
    assert {i["scheduled_date"] for i in b["items"] if i["status"] == "pending"} == {x["scheduled_date"] for x in b["items"] if x["status"] == "success"}
    assert not [x for x in a.get("/api/v1/audit", params={"page_size": 200}).json()["items"] if x["action"] == "batch.item.deferred"]
    set_cap(a, 3)
    done = a.wait_batch(bid, timeout=40)
    assert done["counts"]["success"] == 3, done["counts"]


# ─────────────────────────── IT-104 중복 실행 ───────────────────────────

def test_it_104_double_execute_and_idempotency(fresh_demo):
    """IT-104: 배치 이중 실행 방지 — 같은 Idempotency-Key 재전송은 첫 응답 재생(작업 1개), 다른 키로 두 번째 실행은 409 batch_not_draft,
    다른 요청에 같은 키는 422. 동시에 8번 실행해도 실행은 1회이고 영상당 반영 1건. 검증: W-010, S-W12, NFR-W03, API.md 1-6"""
    a = fresh_demo
    set_cap(a, 20)
    ok = usable_videos(a, 6)
    ap = approve_many(a, ok)
    # 배치 생성 멱등: 같은 키 두 번 → 같은 배치 id, 배치 1개
    key = "it-005-create-0001"
    r1 = a.post("/api/v1/batches", json={"suggestion_ids": [s["id"] for s in ap[:3]], "note": "A"}, idem=key)
    r2 = a.post("/api/v1/batches", json={"suggestion_ids": [s["id"] for s in ap[:3]], "note": "A"}, idem=key)
    assert r1.status_code == r2.status_code == 201 and r1.json()["batch"]["id"] == r2.json()["batch"]["id"]
    assert a.get("/api/v1/batches").json()["total"] == 1
    r3 = a.post("/api/v1/batches", json={"suggestion_ids": [ap[3]["id"]], "note": "다른 요청"}, idem=key)
    assert r3.status_code == 422 and r3.json()["code"] == "idempotency_key_reuse"
    assert a.post("/api/v1/batches", json={"suggestion_ids": [ap[3]["id"]]}).json()["code"] == "idempotency_key_required"
    assert a.post("/api/v1/batches", json={"suggestion_ids": [ap[3]["id"]]}, idem="short").json()["code"] == "idempotency_key_invalid"
    bid = r1.json()["batch"]["id"]
    worker_stop()                       # 대기 항목이 그대로 남아 있어야 재전송 결과를 정확히 비교할 수 있다
    try:
        ek = "it-005-exec-0001"
        e1 = a.execute(bid, 3, idem=ek)
        e2 = a.execute(bid, 3, idem=ek)
        assert e1.status_code == 202 and e2.status_code == 202
        assert e1.json()["job"]["id"] == e2.json()["job"]["id"]          # 같은 첫 응답을 재생(작업을 또 만들지 않음)
        assert psql_app("select count(*) from jobs where type='batch.execute'") == "1"
        e3 = a.execute(bid, 3, idem=True)                                 # 다른 키 → 이미 실행됨
        assert e3.status_code == 409 and e3.json()["code"] == "batch_not_draft"
        e4 = a.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": "실행 9건"}, idem=ek)   # 같은 키, 다른 본문
        assert e4.status_code == 422 and e4.json()["code"] == "idempotency_key_reuse"
    finally:
        worker_start()
    done = a.wait_batch(bid)
    assert done["counts"]["success"] == 3
    # 동시 실행: 두 번째 배치를 8개 스레드가 서로 다른 키로 동시에 실행
    import threading
    bid2 = a.make_batch([s["id"] for s in ap[3:]]).json()["batch"]["id"]
    codes: list[tuple[int, str]] = []
    lock = threading.Lock()
    def go(i: int):
        c = Api(throttle=0)
        c.c.cookies.set("ytw_session", a.c.cookies.get("ytw_session"), domain="127.0.0.1", path="/api")
        c.csrf = a.csrf
        r = c.execute(bid2, 3, idem=f"it-005-race-{i:04d}-xxxx")
        with lock:
            codes.append((r.status_code, r.json().get("code", "")))
        c.close()
    ts = [threading.Thread(target=go, args=(i,)) for i in range(8)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert sorted(c for c, _ in codes).count(202) == 1, codes
    assert all(c in (202, 409) for c, _ in codes), codes
    done2 = a.wait_batch(bid2)
    assert done2["counts"]["success"] == 3
    assert psql_app("select count(*) from jobs where type='batch.execute'") == "2"
    assert psql_app("select max(c) from (select count(*) c from changes where change_type='apply' group by video_id) t") == "1"
    assert psql_app("select count(*) from quota_usage where status='ok'") == str(6 * 3)   # 반영 6건 x 3행(52 단위), 이중 차감 없음
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == 6 * 52


# ─────────────────────────── IT-105 중지 ───────────────────────────

def test_it_105_cancel_before_worker_picks_up_and_cancel_states(fresh_demo):
    """IT-105: 실행 확정 후 워커가 처리하기 전에 중지하면 대기 항목이 전부 취소되고 제안이 승인 대기로 돌아오며, 워커가 다시 떠도 반영되지 않는다.
    이미 끝난 배치·취소된 배치의 취소/재실행은 409. 초안 취소도 가능. 검증: W-010, W-008"""
    a = fresh_demo
    ok = usable_videos(a, 5)
    ap = approve_many(a, ok)
    worker_stop()
    try:
        bid = a.make_batch([s["id"] for s in ap[:3]]).json()["batch"]["id"]
        assert a.execute(bid, 3).status_code == 202
        r = a.post(f"/api/v1/batches/{bid}/cancel")
        assert r.status_code == 200 and r.json()["status"] == "cancelled" and r.json()["counts"]["cancelled"] == 3
        assert all("[cancelled]" in (i["skip_reason"] or "") for i in r.json()["items"])
        r = a.execute(bid, 3)
        assert r.status_code == 409 and r.json()["code"] == "batch_not_draft"
        r = a.post(f"/api/v1/batches/{bid}/cancel")
        assert r.status_code == 409 and r.json()["code"] == "batch_not_cancellable"
    finally:
        worker_start()
    time.sleep(6)
    assert psql_app("select count(*) from changes") == "0"
    assert a.get("/api/v1/dashboard").json()["queue"]["pending_items"] == 0
    st = {s["id"]: s["status"] for s in a.get("/api/v1/suggestions", params={"page_size": 100}).json()["items"]}
    assert [st[s["id"]] for s in ap[:3]] == ["approved"] * 3      # 승인이 아직 유효 → approved 로 복귀
    # 초안 취소 + 취소된 제안으로 새 배치 → 반영
    d = a.make_batch([s["id"] for s in ap[3:5]]).json()["batch"]["id"]
    assert a.post(f"/api/v1/batches/{d}/cancel").json()["status"] == "cancelled"
    nb = a.make_batch([s["id"] for s in ap[:3]]).json()
    assert nb["precheck"]["item_count"] == 3
    assert a.execute(nb["batch"]["id"], 3).status_code == 202
    assert a.wait_batch(nb["batch"]["id"])["counts"]["success"] == 3
    r = a.post(f"/api/v1/batches/{nb['batch']['id']}/cancel")
    assert r.status_code == 409 and r.json()["code"] == "batch_not_cancellable"


# ─────────────────────────── IT-106 롤백 불가 사유 ───────────────────────────

def test_it_106_rollback_refusal_reasons(fresh_demo):
    """IT-106: 롤백이 막히는 사유가 단위 경계(이력 ↔ 백업 ↔ 쿼터 ↔ 멱등성)에서 각각 올바른 코드로 나온다: typed_video_id_mismatch, change_not_found,
    not_rollbackable(롤백의 롤백), later_change_exists/already_restored(이중 롤백), backup_invalid(백업 손상), quota_exhausted(429), 키 누락 400.
    모든 거부는 영상 제목을 바꾸지 않는다. 검증: W-011, S-W12"""
    a = fresh_demo
    ok = usable_videos(a, 4)
    ap = approve_many(a, ok)
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    a.execute(bid, 4)
    a.wait_batch(bid)
    chs = a.get("/api/v1/changes").json()["items"]
    byv = {c["video_id"]: c for c in chs}
    def title(v: str) -> str:
        return {x["video_id"]: x for x in a.videos()}[v]["title"]
    c1, c2, c3, c4 = (byv[v["video_id"]] for v in ok)
    rb = lambda c, typed=None, idem=True: a.post(f"/api/v1/changes/{c['id']}/rollback", json={"typed_video_id": typed or c["video_id"], "approver": "복구자"}, idem=idem)  # noqa: E731
    assert rb(c1, idem=False).status_code == 400
    assert rb({"id": 99999, "video_id": "demoVid0001"}).json()["code"] == "change_not_found"
    r = rb(c1, typed="demoVid0200")
    assert r.status_code == 422 and title(c1["video_id"]) == c1["new_title"]
    # 정상 롤백 + 같은 키 재전송 → 같은 응답(롤백 1건)
    k = "it-007-rb-0001-xx"
    r1 = rb(c1, idem=k)
    r2 = rb(c1, idem=k)
    assert r1.status_code == 201 and r2.status_code == 201 and r1.json()["id"] == r2.json()["id"]
    assert psql_app("select count(*) from changes where change_type='rollback'") == "1"
    # 롤백의 롤백, 이미 롤백된 적용의 재롤백
    r = rb({"id": r1.json()["id"], "video_id": c1["video_id"]})
    assert r.status_code == 409 and r.json()["code"] == "not_rollbackable"
    r = rb(c1)
    assert r.status_code == 409 and r.json()["code"] in ("later_change_exists", "already_restored", "not_rollbackable"), r.text[:200]
    assert title(c1["video_id"]) == c1["previous_title"]
    lst = {c["id"]: c for c in a.get("/api/v1/changes").json()["items"]}        # 되돌린 적용·롤백 자신은 더 이상 롤백 대상이 아니다
    assert lst[c1["id"]]["rollbackable"] is False and lst[r1.json()["id"]]["rollbackable"] is False and lst[c2["id"]]["rollbackable"] is True
    # 이미 원래 제목(사용자가 Studio 에서 직접 되돌림) → already_restored, 제목은 그대로, 쿼터 소비 없음
    q0 = a.get("/api/v1/dashboard").json()["quota"]["used"]
    ib.mark_video_title(c4["video_id"], c4["previous_title"])
    r = rb(c4)
    assert r.status_code == 409 and r.json()["code"] == "already_restored", r.text[:200]
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == q0 + 1          # 실제로 호출한 재조회 1회(1단위)만 남고, 호출하지 않은 갱신·검증 예약(51)은 풀린다
    ib.mark_video_title(c4["video_id"], c4["new_title"])
    # 백업 손상 → backup_invalid(제목 불변)
    psql_app(f"update changes set backup_snippet = '{{\"title\": \"x\"}}'::jsonb where id = {c2['id']}")
    r = rb(c2)
    assert r.status_code == 409 and r.json()["code"] == "backup_invalid", r.text[:200]
    assert title(c2["video_id"]) == c2["new_title"]
    # 쿼터 소진(PT 하루 6000 단위) → 429, 제목 불변. 정리 후 같은 요청이 성공(상태 복구)
    psql_app("insert into quota_usage (pt_date, method, units, called_at, status) select (now() at time zone 'America/Los_Angeles')::date, 'it.fill', 6000, now(), 'ok'")
    r = rb(c3)
    assert r.status_code == 429 and r.json()["code"] == "quota_exhausted", r.text[:200]
    assert title(c3["video_id"]) == c3["new_title"]
    psql_app("delete from quota_usage where method = 'it.fill'")
    assert rb(c3).status_code == 201 and title(c3["video_id"]) == c3["previous_title"]
    # 쿼터 경계: 남은 단위가 52 미만(51)이면 거부, 정확히 52 이면 통과(사용 + 필요 == 상한은 허용)
    used = a.get("/api/v1/dashboard").json()["quota"]["used"]
    psql_app(f"insert into quota_usage (pt_date, method, units, called_at, status) select (now() at time zone 'America/Los_Angeles')::date, 'it.fill', {6000 - used - 51}, now(), 'ok'")
    r = rb(c4)
    assert r.status_code == 429 and r.json()["code"] == "quota_exhausted" and title(c4["video_id"]) == c4["new_title"], r.text[:200]
    psql_app("update quota_usage set units = units - 1 where method = 'it.fill'")           # 남은 단위 52
    assert rb(c4).status_code == 201 and title(c4["video_id"]) == c4["previous_title"]
    assert a.get("/api/v1/dashboard").json()["quota"]["remaining"] == 0


# ─────────────────────────── IT-107 CSV 수식 무력화와 리포트 ───────────────────────────

def test_it_107_report_and_csv_formula_neutralized_end_to_end(fresh_demo):
    """IT-107: 사람이 수정한 제목이 `=` `+` `-` `@` 로 시작해도(검증기가 허용함) 반영 → 이력 → CSV 에서 수식으로 실행되지 않게 `'` 접두가 붙는다 — 네 문자 각각.
    변경이 없는 영상은 리포트에 '변경 없음'/'데이터 부족'으로만 나오고 원인을 단정하지 않는다. 검증: W-013, SEC-W21"""
    a = fresh_demo
    set_cap(a, 20)
    vs = usable_videos(a, 5)
    prefixes = ("=", "+", "-", "@")
    picked = {}
    for p, v in zip(prefixes, vs):
        s = [x for x in a.make_suggestion(v["video_id"], 3) if x["validation_result"] != "block" and not x["strict"]][0]
        r = a.patch(f"/api/v1/suggestions/{s['id']}", json={"title": p + "합계 " + s["title"]})
        assert r.status_code == 200 and r.json()["validation_result"] != "block" and r.json()["status"] == "candidate", (p, r.text[:200])
        assert a.approve(r.json()["id"]).status_code == 200
        picked[p] = (v["video_id"], r.json())
    bid = a.make_batch([sg["id"] for _, sg in picked.values()]).json()["batch"]["id"]
    a.execute(bid, 4)
    assert a.wait_batch(bid)["counts"]["success"] == 4
    raw = a.get("/api/v1/reports/export.csv").content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(raw)))
    by = {x["video_id"]: x for x in rows if (x.get("video_id") or "").startswith("demoVid")}
    for p, (vid, sg) in picked.items():
        mine = by[vid]
        assert mine["new_title"].startswith("'" + p) and not mine["new_title"].startswith(p), (p, mine["new_title"])
    for row in rows:
        for cell in row.values():
            assert not (cell or "").startswith(("=", "+", "-", "@", "\t", "\r")) or cell.replace(".", "", 1).lstrip("+-").isdigit()
    vid0 = picked["="][0]
    rep = a.get("/api/v1/reports/changes", params={"video_id": vid0}).json()
    assert rep["items"][0]["status"] in ("insufficient", "ok") and rep["notes"]
    rep2 = a.get("/api/v1/reports/changes", params={"video_id": vs[4]["video_id"]}).json()
    assert rep2["items"][0]["status"] == "no_change"


# ─────────────────────────── IT-108 PIN 생애주기 ───────────────────────────

def test_it_108_pin_lifecycle_sessions_lock_and_revocation(fresh_demo):
    """IT-108: 설정(PIN) ↔ 인증 ↔ 세션 ↔ nginx 속도 제한의 경계. PIN 설정 시 다른 세션이 폐기되고, PIN 없는 로그인은 거부되며, 5회 틀리면 잠금(429
    pin_locked + Retry-After), 잠금 중에는 맞는 PIN 도 거부, 변경·해제는 현재 PIN 필수, PIN 값은 로그·감사에 남지 않는다. 검증: W-014, SEC-W19, SEC-W20, S-W09"""
    a = fresh_demo
    b = Api()                            # 두 번째 세션(다른 브라우저)
    assert b.login().status_code == 200
    r = a.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "424242"}})
    assert r.status_code == 200 and r.json()["pin_enabled"] is True
    assert a.get("/api/v1/dashboard").status_code == 200              # 현재 세션은 유지
    assert b.get("/api/v1/dashboard").status_code == 401              # 다른 세션은 폐기
    c = Api()
    r = c.login()
    assert r.status_code == 401 and r.json()["code"] == "pin_invalid"
    assert c.login("907356").status_code == 401
    r = None
    for _ in range(5):
        r = c.login("818283")
    assert r.status_code == 429 and r.json()["code"] == "pin_locked" and int(r.headers["retry-after"]) >= 60
    r = c.login("424242")                              # 잠금 중에는 맞는 PIN 도 거부
    assert r.status_code == 429 and r.json()["code"] == "pin_locked"
    # 잠금 해제(5분을 기다릴 수 없어 상태 행을 지움: 앱 계정에 UPDATE/DELETE 권한 있음) 후 정상 로그인
    keys = psql_app("select key from settings_kv").splitlines()
    lock_keys = [k for k in keys if "pin" in k and "hash" not in k]
    assert lock_keys, keys
    for k in lock_keys:
        psql_app(f"delete from settings_kv where key = '{k}'")
    r = c.login("424242")      # 세션 발급 분당 제한(전역 10)에 걸릴 수 있어 기다렸다 다시 시도
    assert r.status_code == 200
    # 변경·해제: 현재 PIN 필수
    r = c.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "131313"}})
    assert r.status_code in (401, 422), r.text
    r = c.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "131313", "current_pin": "907356"}})
    assert r.status_code == 401 and r.json()["code"] == "pin_invalid"
    assert c.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "12", "current_pin": "424242"}}).status_code == 422
    r = c.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "131313", "current_pin": "424242"}})
    assert r.status_code == 200
    assert a.get("/api/v1/dashboard").status_code == 401              # 변경하면 다른 세션(이전 a) 폐기
    r = c.patch("/api/v1/settings", json={"pin": {"action": "clear", "current_pin": "131313"}})
    assert r.status_code == 200 and r.json()["pin_enabled"] is False
    d = Api()
    assert d.login().status_code == 200                               # PIN 없이 다시 로그인 가능
    assert d.patch("/api/v1/settings", json={"pin": {"action": "clear"}}).json()["code"] == "pin_not_set"
    # PIN 값은 감사·컨테이너 로그에 없다
    au = json.dumps(d.get("/api/v1/audit", params={"page_size": 200}).json(), ensure_ascii=False)
    for pin in ("424242", "131313", "818283", "907356"):
        assert pin not in au
        assert pin not in server_logs(), pin
    for x in (a, b, c, d):
        x.close()


# ─────────────────────────── IT-109 설정 경계 ───────────────────────────

def test_it_109_settings_allow_list_and_live_cannot_be_enabled(fresh_demo):
    """IT-109: 설정 API 는 4개 키만 받고 enable_live·live_allowlist 같은 키는 전체 거부(400)하며, 범위를 벗어난 값은 422. 설정 변경이 읽기 API 에 즉시 반영된다.
    검증: W-014, SEC-W23, S-W03"""
    a = fresh_demo
    for body in ({"enable_live": True}, {"live_allowlist": ["demoVid0001"]}, {"daily_apply_cap": 5, "enable_live": True}, {"mode": "live"}):
        r = a.patch("/api/v1/settings", json=body)
        assert r.status_code == 400 and r.json()["code"] == "setting_not_allowed", body
    for body in ({"daily_apply_cap": 0}, {"daily_apply_cap": 21}, {"daily_apply_cap": "5"}, {"suggestions_per_video": 6}, {"tone": ["가" * 21]}, {"tone": ["a"] * 6}):
        assert a.patch("/api/v1/settings", json=body).status_code == 422, body
    r = a.patch("/api/v1/settings", json={"daily_apply_cap": 7, "suggestions_per_video": 2, "tone": ["친근한"]})
    assert r.status_code == 200
    g = a.get("/api/v1/settings").json()
    assert (g["daily_apply_cap"], g["suggestions_per_video"], g["tone"]) == (7, 2, ["친근한"])
    assert g["mode"] == "demo" and g["read_only"]["enable_live"] is False and g["read_only"]["live_allowlist"] == []
    assert a.get("/api/v1/dashboard").json()["today"]["cap"] == 7       # 설정 ↔ 대시보드(도메인) 경계
    # DB 에 범위를 벗어난 값이 저장돼 있어도(수동 수정·구버전 잔재) 안전한 기본값(10)으로 읽는다 — 상한 0 이면 반영이 영영 멈추고 99 이면 상한이 사라진다
    for bad in ('99', '0', '"5"', 'true'):
        psql_app(f"update settings_kv set value = '{bad}'::jsonb where key = 'daily_apply_cap'")
        assert a.get("/api/v1/dashboard").json()["today"]["cap"] == 10, bad
        assert a.get("/api/v1/settings").json()["daily_apply_cap"] == 10, bad
    a.patch("/api/v1/settings", json={"daily_apply_cap": 10, "suggestions_per_video": 3, "tone": []})
    assert a.get("/api/v1/google/status").json()["connected"] is False


# ─────────────────────────── IT-110 같은 영상 두 배치 ───────────────────────────

def test_it_110_same_video_in_two_batches_applies_once(fresh_demo):
    """IT-110: 같은 영상의 서로 다른 제안을 두 배치(초안)에 나눠 담고 둘 다 실행해도 영상은 한 번만 바뀐다(두 번째는 건너뜀·제목 불변·쿼터 1건분).
    배치 단위(BE-B)와 이력/한도(BE-B)·워커(BE-A) 사이의 경계. 검증: W-008, W-010, S-W12, NFR-W03"""
    a = fresh_demo
    two = two_pass_suggestions(a, usable_videos(a, 30))
    v = two[0]["video_id"]
    for x in two:
        assert a.approve(x["id"]).status_code == 200
    b1 = a.make_batch([two[0]["id"]]).json()["batch"]["id"]
    b2 = a.make_batch([two[1]["id"]]).json()["batch"]["id"]
    worker_stop()
    try:
        assert a.execute(b1, 1).status_code == 202
        r = a.execute(b2, 1)
        assert r.status_code in (202, 409), r.text[:300]     # 확정 시점에 막으면 409(precheck_stale), 아니면 워커가 건너뜀
    finally:
        worker_start()
    d1 = a.wait_batch(b1)
    d2 = a.wait_batch(b2) if r.status_code == 202 else None
    assert d1["counts"]["success"] == 1
    if d2:
        assert d2["counts"]["success"] == 0 and (d2["counts"]["skipped"] + d2["counts"]["failed"]) == 1, d2["counts"]
        assert d2["items"][0]["skip_reason"].startswith("[")
    assert psql_app(f"select count(*) from changes where video_id='{v}' and change_type='apply' and result='success'") == "1"
    assert {x["video_id"]: x for x in a.videos()}[v]["title"] == two[0]["title"]
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == 52


# ─────────────────────────── IT-111 교체 한도(간격·횟수)와 롤백 ───────────────────────────

def test_it_111_replace_limits_interval_count_and_rollback_exempt(fresh_demo):
    """IT-111: 같은 영상의 교체 한도(72시간 간격·영상당 3회)가 이력(롤백 포함) ↔ 배치 사전 점검 ↔ 영상 상세(limits)에 일관되게 적용된다.
    롤백 자체는 한도를 적용받지 않지만 변경 1회로 센다. 72시간 뒤에는 다시 담긴다. 3회가 차면 시간이 지나도 막힌다. 검증: W-008, W-011, S-W12(교체 한도)"""
    a = fresh_demo
    set_cap(a, 20)
    v, sugs = approvable_set(a, usable_videos(a, 60), 3)
    vid = v["video_id"]
    assert a.get(f"/api/v1/videos/{vid}").json()["limits"]["allowed"] is True
    s1 = a.approve(sugs[0]["id"]).json()
    ch1 = apply_via_batch(a, s1["id"])
    d = a.get(f"/api/v1/videos/{vid}").json()
    assert d["limits"]["allowed"] is False and d["limits"]["next_allowed_at"] and any("72" in x for x in d["limits"]["reasons"]), d["limits"]
    assert _parse_ts(d["limits"]["next_allowed_at"]) > datetime.now(timezone.utc) + timedelta(hours=70)
    r = rollback(a, ch1)                                     # 롤백은 간격 한도를 무시한다(사고 복구가 막히지 않게)
    assert r.status_code == 201 and r.json()["change_type"] == "rollback"
    assert a.approve(sugs[1]["id"]).status_code == 200
    r = a.make_batch([sugs[1]["id"]])                         # 롤백도 변경 1회 → 간격 한도에 걸린다
    assert r.status_code == 422 and r.json()["code"] == "batch_empty" and "72" in r.json()["detail"], r.text[:300]
    shift_hours(70)                                           # 경계: 72시간 직전(롤백으로부터 70시간)에는 아직 막힌다
    r = a.make_batch([sugs[1]["id"]])
    assert r.status_code == 422 and r.json()["code"] == "batch_empty", r.text[:300]
    shift_hours(3)                                            # 73시간 → 통과
    ch2 = apply_via_batch(a, sugs[1]["id"])                   # 두 번째 적용(영상 기준 변경 3회째: 적용·롤백·적용)
    assert {x["video_id"]: x["title"] for x in a.videos()}[vid] == ch2["new_title"]
    assert a.approve(sugs[2]["id"]).status_code == 200
    shift_hours(73)                                           # 간격은 지났지만 횟수(3회)가 찼다
    r = a.make_batch([sugs[2]["id"]])
    assert r.status_code == 422 and r.json()["code"] == "batch_empty", r.text[:300]
    assert "3" in r.json()["detail"] and ("횟수" in r.json()["detail"] or "회" in r.json()["detail"]), r.json()["detail"]
    lim = a.get(f"/api/v1/videos/{vid}").json()["limits"]
    assert lim["allowed"] is False and lim["next_allowed_at"] is None, lim              # 시간이 해결해 주지 않는 한도는 다음 가능 시각이 없다
    assert psql_app(f"select count(*) from changes where video_id='{vid}' and result='success'") == "3"
    # 이후 변경이 있는 옛 변경의 롤백은 거부된다(옛 제목으로 최신 제목을 덮는 사고 방지) — 제목 불변
    r = rollback(a, ch1)
    assert r.status_code == 409 and r.json()["code"] == "later_change_exists", r.text[:300]
    assert {x["video_id"]: x["title"] for x in a.videos()}[vid] == ch2["new_title"]
    chs = {c["id"]: c for c in a.get("/api/v1/changes", params={"video_id": vid}).json()["items"]}
    assert [c["rollbackable"] for c in sorted(chs.values(), key=lambda c: c["id"])] == [False, False, True], chs      # 적용1(이미 되돌림)·롤백·적용2(최신)
    # 롤백은 횟수가 차도 가능(가장 최근 변경이면)
    assert rollback(a, ch2).status_code == 201


# ─────────────────────────── IT-112 워커 쪽 승인·상태 재검증(건너뜀 사유 11종) ───────────────────────────

def _planned_row_sql(video_id: str, suggestion_id: int, batch_id: int, result: str, ago_hours: float) -> str:
    return (
        "insert into changes (video_id, suggestion_id, batch_id, change_type, previous_title, new_title, backup_snippet, reason, approver, approved_at, plan_hash, result, mode, created_at, applied_at) "
        f"select v.video_id, s.id, {batch_id}, 'apply', v.title, s.title, v.snippet, 'it', a.approver, a.approved_at, a.plan_hash, '{result}', 'demo', now() - interval '{ago_hours} hour', "
        f"case when '{result}'='success' then now() - interval '{ago_hours} hour' else null end "
        f"from videos v join suggestions s on s.id = {suggestion_id} join approvals a on a.suggestion_id = s.id where v.video_id = '{video_id}'"
    )


def test_it_112_worker_rechecks_everything_after_execute_confirm(fresh_demo):
    """IT-112: 실행을 확정한 뒤 워커가 처리하기 전에 상태가 어긋나면(승인 삭제·변조·사용·만료, 영상 정보 변경, 제안 상태·판정 변경, 제외 사유 발생,
    미확정 변경 기록, 간격·횟수 한도) 워커는 영상을 바꾸지 않고 항목을 [코드] 사유와 함께 건너뛴다. 11가지를 한 DB 에서 한꺼번에 시험한다
    (승인 ↔ 배치 ↔ 워커 ↔ 한도 ↔ 이력 경계). 검증: W-008, W-010, SEC-W17, S-W12"""
    a = fresh_demo
    set_cap(a, 20)
    cases = ["approval_missing", "approval_tampered", "approval_used", "approval_expired", "plan_mismatch", "suggestion_state", "suggestion_blocked",
             "video_excluded", "pending_change_exists", "limit_interval", "limit_count"]
    vids = usable_videos(a, len(cases) + 1)
    ap = {c: approved_suggestion(a, vids[i]["video_id"]) for i, c in enumerate(cases)}
    ok_sug = approved_suggestion(a, vids[len(cases)]["video_id"])            # 대조군: 아무 이상 없는 항목은 정상 반영
    worker_stop()
    items: dict[str, dict] = {}
    try:
        for c in cases + ["control"]:
            sg = ok_sug if c == "control" else ap[c]
            bid = a.make_batch([sg["id"]]).json()["batch"]["id"]
            assert a.execute(bid, 1).status_code == 202
            items[c] = {"batch": bid, "sug": sg["id"], "video": sg["video_id"], "title": {x["video_id"]: x["title"] for x in a.videos()}[sg["video_id"]]}
        for c in cases:
            S, V, B = items[c]["sug"], items[c]["video"], items[c]["batch"]
            sql = {
                "approval_missing": f"delete from approvals where suggestion_id={S}",
                "approval_tampered": f"update approvals set approver='위조자' where suggestion_id={S}",
                "approval_used": f"update approvals set used_at=now() where suggestion_id={S}",
                "approval_expired": f"update batches set executed_at = executed_at + interval '25 hours' where id={B}",
                "plan_mismatch": f"update videos set snippet = jsonb_set(snippet,'{{description}}','\"바뀐 설명\"'::jsonb) where video_id='{V}'",
                "suggestion_state": f"update suggestions set status='approved' where id={S}",
                "suggestion_blocked": f"update suggestions set validation_result='block' where id={S}",
                "video_excluded": f"update videos set privacy_status='private' where video_id='{V}'",
                "pending_change_exists": _planned_row_sql(V, S, B, "planned", 0),
                "limit_interval": _planned_row_sql(V, S, B, "success", 1),
                "limit_count": "; ".join(_planned_row_sql(V, S, B, "success", h) for h in (100, 200, 300)),
            }[c]
            psql_owner(sql)
    finally:
        worker_start()
    for c in cases + ["control"]:
        b = a.wait_batch(items[c]["batch"], timeout=90)
        it = b["items"][0]
        if c == "control":
            assert it["status"] == "success", it
            continue
        assert it["status"] == "skipped" and it["skip_reason"].startswith(f"[{c}]"), (c, it["status"], it["skip_reason"])
        assert b["status"] == "done" and b["counts"]["skipped"] == 1
        assert psql_app(f"select count(*) from changes where batch_id={items[c]['batch']} and result='success' and applied_at > now() - interval '1 minute' and reason <> 'it'") == "0", c
    titles = {x["video_id"]: x["title"] for x in a.videos()}
    for c in cases:
        assert titles[items[c]["video"]] == items[c]["title"], f"{c}: 건너뛴 항목의 영상 제목이 바뀜"
    assert titles[ok_sug["video_id"]] == ok_sug["title"]
    au = a.get("/api/v1/audit", params={"page_size": 200}).json()
    skipped = [x["detail"]["code"] for x in au["items"] if x["action"] == "batch.item.skipped"]
    assert sorted(skipped) == sorted(cases), skipped
    assert au["chain_ok"] is True
    # 건너뛴 제안은 승인이 아직 쓸 수 있으면 approved, 아니면 expired 로 돌아온다(승인 삭제·변조·사용·만료 등은 expired, 그 밖은 approved 로 복귀하거나 상태 유지)
    st = {s["id"]: s["status"] for s in a.get("/api/v1/suggestions", params={"page_size": 200}).json()["items"]}
    for c in ("approval_missing", "approval_tampered", "approval_used", "approval_expired"):
        assert st[items[c]["sug"]] == "expired", (c, st[items[c]["sug"]])
    assert psql_app("select count(*) from quota_usage where status in ('ok','failed') and units>0") == "3", "쿼터는 정상 반영 1건(3행)만 소비"


# ─────────────────────────── IT-113 일부 반영 뒤 중지 ───────────────────────────

def test_it_113_cancel_after_partial_apply_keeps_applied_and_releases_rest(fresh_demo):
    """IT-113: 하루 상한 2·항목 5 배치에서 2건이 반영된 뒤 중지하면 나머지 3건만 취소되고 제안은 승인 대기로 돌아오며, 다음 날이 되어도 더 반영되지 않는다.
    이미 반영된 2건의 이력·롤백 가능 여부는 그대로. 검증: W-008, W-010, W-011"""
    a = fresh_demo
    set_cap(a, 2)
    ap = approve_many(a, usable_videos(a, 5))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 5).status_code == 202
    from itlib_b import wait_until
    wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 2, 60, what="2건 반영")
    r = a.post(f"/api/v1/batches/{bid}/cancel")
    assert r.status_code == 200 and r.json()["counts"] == {"pending": 0, "running": 0, "success": 2, "failed": 0, "skipped": 0, "cancelled": 3}, r.json()["counts"]
    st = {s["id"]: s["status"] for s in a.get("/api/v1/suggestions", params={"page_size": 100}).json()["items"]}
    done = [x["suggestion_id"] for x in r.json()["items"] if x["status"] == "success"]
    rest = [x["suggestion_id"] for x in r.json()["items"] if x["status"] == "cancelled"]
    assert all(st[i] == "applied" for i in done) and all(st[i] == "approved" for i in rest)
    shift_days(1)
    time.sleep(7)
    assert psql_app("select count(*) from changes where result='success'") == "2"
    d = a.get("/api/v1/dashboard").json()
    assert d["queue"]["pending_items"] == 0 and d["counts"]["applied"] == 2 and d["counts"]["approved"] == 3
    assert all(c["rollbackable"] for c in a.get("/api/v1/changes", params={"batch_id": bid}).json()["items"])
    # 이 시점에서 시늉으로 하루를 당겼으므로 오늘 몫은 비어 있다. 되돌리고(오늘 이미 2건 반영) 새 배치를 만들면 오늘 몫이 없어 모두 내일 이후로 잡힌다
    shift_days(-1)
    nb = a.make_batch(rest)                                   # 돌려받은 제안으로 새 배치
    assert nb.status_code == 201 and nb.json()["precheck"]["item_count"] == 3
    pre = nb.json()["precheck"]
    assert date.fromisoformat(pre["schedule"][0]["date"]) >= datetime.now(timezone(timedelta(hours=9))).date() + timedelta(days=1) - timedelta(days=0), pre["schedule"]
    assert any("상한" in w and "내일" in w for w in pre["warnings"]), pre["warnings"]


# ─────────────────────────── IT-114 사용자가 Studio 에서 먼저 제목을 바꾼 경우 ───────────────────────────

def test_it_114_external_title_change_is_never_overwritten(fresh_demo):
    """IT-114: 승인한 뒤 유튜브(모의) 쪽 제목이 사용자에 의해 바뀌면 (a) 배치 초안 단계 (b) 실행 확정 단계 (c) 확정 뒤 워커 단계 중 어디서든
    덮어쓰지 않는다. 재동기화(videos.sync)도 앱이 바꾼 제목을 되돌리지 않는다. 검증: W-008, W-010, SEC-W17, S-W12"""
    a = fresh_demo
    set_cap(a, 20)
    vs = usable_videos(a, 4)
    s_a, s_b, s_c, s_d = approve_many(a, vs)
    # (a) 초안 전에 바뀜 → 담기지 않음
    mark_video_title(s_a["video_id"], "사용자가 직접 바꾼 제목 A")
    r = a.make_batch([s_a["id"]])
    assert r.status_code == 422 and r.json()["code"] == "batch_empty"
    # (b) 초안 뒤·확정 전에 바뀜 → 확정 거부(precheck_stale), 영상 제목 그대로
    bid_b = a.make_batch([s_b["id"]]).json()["batch"]["id"]
    mark_video_title(s_b["video_id"], "사용자가 직접 바꾼 제목 B")
    r = a.execute(bid_b, 1)
    assert r.status_code == 409 and r.json()["code"] == "precheck_stale", r.text[:300]
    assert a.get(f"/api/v1/batches/{bid_b}").json()["status"] == "draft"
    # (c) 확정 뒤·워커 전에 바뀜 → 워커가 건너뜀
    worker_stop()
    try:
        bid_c = a.make_batch([s_c["id"]]).json()["batch"]["id"]
        assert a.execute(bid_c, 1).status_code == 202
        mark_video_title(s_c["video_id"], "사용자가 직접 바꾼 제목 C")
    finally:
        worker_start()
    b = a.wait_batch(bid_c)
    assert b["counts"]["skipped"] == 1 and b["items"][0]["skip_reason"].startswith(("[plan_mismatch]", "[title_changed]", "[video_changed]")), b["items"]
    titles = {x["video_id"]: x["title"] for x in a.videos()}
    assert titles[s_a["video_id"]].endswith("A") and titles[s_b["video_id"]].endswith("B") and titles[s_c["video_id"]].endswith("C")
    # 재동기화: 앱이 반영한 제목은 유지(d), 사용자가 직접 바꾼 제목도 앱이 건드리지 않은 영상은 시드 기준으로 되돌아간다
    ch = apply_via_batch(a, s_d["id"])
    j = a.sync_demo()
    assert j["status"] == "succeeded"
    titles2 = {x["video_id"]: x["title"] for x in a.videos()}
    assert titles2[s_d["video_id"]] == ch["new_title"]


# ─────────────────────────── IT-115 영상 workflow 상태와 대시보드 집계 ───────────────────────────

def test_it_115_workflow_status_and_dashboard_counts_follow_every_transition(fresh_demo):
    """IT-115: 제안 → 승인 → 배치 대기 → 반영 → 롤백 → 반려 각 단계에서 영상 목록의 workflow_status/필터·영상 상세·대시보드 counts 가 서로 일치한다
    (제안·배치·이력·영상 단위 사이의 파생 상태). 검증: W-002, W-005, W-009, W-012"""
    a = fresh_demo
    set_cap(a, 20)
    v1, v2, v3 = usable_videos(a, 3)
    def ws(v): return {x["video_id"]: x for x in a.videos()}[v["video_id"]]["workflow_status"]
    def cnt(): return a.get("/api/v1/dashboard").json()["counts"]
    assert ws(v1) == "none" and cnt()["suggested"] == 0
    s1 = a.make_suggestion(v1["video_id"], 3)
    assert ws(v1) == "suggested" and cnt()["suggested"] >= 1
    ok = [x for x in s1 if x["validation_result"] != "block" and not x["strict"]][0]
    assert a.approve(ok["id"]).status_code == 200
    assert ws(v1) == "approved" and cnt()["approved"] == 1
    assert [x["video_id"] for x in a.videos(status="approved")] == [v1["video_id"]]
    worker_stop()
    try:
        bid = a.make_batch([ok["id"]]).json()["batch"]["id"]
        assert a.execute(bid, 1).status_code == 202
        assert ws(v1) == "queued" and cnt()["queued"] == 1 and cnt()["approved"] == 0
    finally:
        worker_start()
    a.wait_batch(bid)
    assert ws(v1) == "applied" and cnt()["applied"] == 1 and cnt()["queued"] == 0
    det = a.get(f"/api/v1/videos/{v1['video_id']}").json()
    assert det["changes"][0]["result"] == "success" and {x["id"]: x["status"] for x in det["suggestions"]}[ok["id"]] == "applied"
    ch = a.get("/api/v1/changes", params={"video_id": v1["video_id"]}).json()["items"][0]
    assert rollback(a, ch).status_code == 201
    assert ws(v1) == "rolled_back" and cnt()["applied"] == 0
    assert {x["id"]: x["status"] for x in a.get(f"/api/v1/videos/{v1['video_id']}").json()["suggestions"]}[ok["id"]] == "rolled_back"
    assert [x["video_id"] for x in a.videos(status="rolled_back")] == [v1["video_id"]]
    # 반려
    s2 = a.make_suggestion(v2["video_id"], 1)[0]
    assert a.post(f"/api/v1/suggestions/{s2['id']}/reject").json()["status"] == "rejected"
    assert ws(v2) == "none" or ws(v2) == "suggested"
    # 제외 필터 + 상태 필터 교차
    ex = a.videos(excluded=True)
    assert len(ex) == 37 and all(x["excluded"] for x in ex)
    assert a.get("/api/v1/dashboard").json()["counts"]["excluded"] == 37


# ─────────────────────────── IT-116 설정이 제안 생성의 두 경로에 흐름 ───────────────────────────

def test_it_116_settings_flow_into_sync_and_job_suggestion_paths(fresh_demo):
    """IT-116: 설정 화면의 '영상당 후보 수'와 '말투'가 동기 제안(POST /videos/{id}/suggestions)과 일괄 제안(작업) 두 경로에 똑같이 반영되고 AI 실행 기록(ai_runs)에
    남는다. 명시한 count 는 설정보다 우선하고, 같은 제목은 중복 생성되지 않는다. 설정 단위 ↔ 제안 단위 ↔ 작업 큐 경계. 검증: W-004, W-014, S-W03"""
    a = fresh_demo
    assert a.patch("/api/v1/settings", json={"suggestions_per_video": 2, "tone": ["친근한", "차분한"]}).status_code == 200
    v1, v2, v3 = usable_videos(a, 3)
    r = a.post(f"/api/v1/videos/{v1['video_id']}/suggestions")           # 본문 없음 → 설정값(2)
    assert r.status_code == 201 and len(r.json()) == 2
    j = a.wait_job(a.post("/api/v1/suggestions/generate", json={"video_ids": [v2["video_id"]]}).json()["id"])   # count 생략 → 설정값(2)
    assert j["status"] == "succeeded" and j["result"]["suggestions"] == 2
    r5 = a.post(f"/api/v1/videos/{v3['video_id']}/suggestions", json={"count": 5})                              # 명시 count 가 우선
    assert r5.status_code == 201 and len(r5.json()) == 5
    again = a.post(f"/api/v1/videos/{v3['video_id']}/suggestions", json={"count": 5})
    assert [x["id"] for x in again.json()] == [x["id"] for x in r5.json()], "같은 제목은 새로 만들지 않고 기존 제안을 돌려준다"
    assert psql_app(f"select count(*) from suggestions where video_id='{v3['video_id']}'") == "5"
    tones = psql_app("select distinct params->>'tone' from ai_runs").splitlines()
    assert tones == ["친근한, 차분한"], tones
    assert sorted(psql_app("select (params->>'count') from ai_runs order by id").splitlines()) == ["2", "2", "5", "5"]
    assert a.patch("/api/v1/settings", json={"tone": []}).status_code == 200
    a.post(f"/api/v1/videos/{usable_videos(a, 4)[3]['video_id']}/suggestions", json={"count": 1})
    assert psql_app("select params->>'tone' from ai_runs order by id desc limit 1") == "friendly"    # 비우면 기본 말투


# ─────────────────────────── IT-117 초안에 담긴 뒤 제안이 바뀌면 ───────────────────────────

def test_it_117_edit_or_reject_after_draft_blocks_execute(fresh_demo):
    """IT-117: 배치 초안에 담은 뒤 (a) 제목을 수정하거나 (b) 반려하면 승인이 사라지므로 실행 확정이 409 precheck_stale 로 거부되고 영상은 바뀌지 않는다.
    초안을 취소해도 수정·반려된 제안은 승인 상태로 되돌아오지 않는다(승인이 없으므로). 새로 승인하면 다시 담긴다. 제안 ↔ 배치 ↔ 승인 경계. 검증: W-007, W-008, SEC-W17"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 3))
    titles0 = {v["video_id"]: v["title"] for v in a.videos()}
    b1 = a.make_batch([ap[0]["id"], ap[1]["id"]]).json()["batch"]["id"]
    r = a.patch(f"/api/v1/suggestions/{ap[0]['id']}", json={"title": ap[0]["title"] + " 하나더"})
    assert r.status_code == 200 and r.json()["approval"] is None and r.json()["status"] in ("candidate", "blocked")
    assert a.post(f"/api/v1/suggestions/{ap[1]['id']}/reject").status_code == 200
    r = a.execute(b1, 2)
    assert r.status_code == 409 and r.json()["code"] == "precheck_stale", r.text[:300]
    assert r.json()["detail"].count("#") == 2, r.json()["detail"]              # 두 항목 모두 사유와 함께 보고
    assert a.get(f"/api/v1/batches/{b1}").json()["status"] == "draft"
    assert {v["video_id"]: v["title"] for v in a.videos()} == titles0
    c = a.post(f"/api/v1/batches/{b1}/cancel")
    assert c.status_code == 200
    st = {s["id"]: s["status"] for s in a.get("/api/v1/suggestions", params={"page_size": 100}).json()["items"]}
    assert st[ap[0]["id"]] in ("candidate", "blocked") and st[ap[1]["id"]] == "rejected"
    assert psql_app("select count(*) from batch_items where status in ('pending','running')") == "0"
    # 수정한 제안을 새로 승인 → 새 계획 해시로 정상 반영
    if st[ap[0]["id"]] == "candidate":
        assert a.approve(ap[0]["id"], "재승인").status_code == 200
        ch = apply_via_batch(a, ap[0]["id"])
        assert ch["new_title"].endswith("하나더") and ch["approver"] == "재승인"
    # 대조: 손대지 않은 제안은 영향 없이 반영
    assert apply_via_batch(a, ap[2]["id"])["result"] == "success"


# ─────────────────────────── IT-118 배치 최대 크기 경계 ───────────────────────────

def test_it_118_batch_of_exactly_50_schedules_20_20_10_and_51_is_refused(fresh_demo):
    """IT-118: 배치 한도 50건 경계. 51건은 422 batch_too_large 이고, 정확히 50건은 하루 20건 상한으로 20/20/10 으로 나뉘어 사흘에 걸쳐 모두 한 번씩만 반영된다.
    사전 점검의 단위 수·쿼터 합계가 실제 소비와 같다(2,600). 검증: W-008, W-010, NFR-W03"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 50))
    ids = [s["id"] for s in ap]
    r51 = a.make_batch(ids + [ids[0] + 100000])
    assert r51.status_code == 422 and r51.json()["code"] == "batch_too_large"
    r = a.make_batch(ids)
    assert r.status_code == 201
    pre = r.json()["precheck"]
    assert pre["item_count"] == 50 and pre["estimated_units"] == 50 * 52 and pre["confirm_text"] == "실행 50건"
    assert [x["count"] for x in pre["schedule"]] == [20, 20, 10], pre["schedule"]
    bid = r.json()["batch"]["id"]
    assert a.execute(bid, 50).status_code == 202
    from itlib_b import wait_until
    wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 20, 120, what="첫째 날 20건")
    time.sleep(5)
    assert a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] == 20
    shift_days(1)
    wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 40, 120, what="둘째 날 20건")
    time.sleep(5)
    assert a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] == 40
    shift_days(1)
    done = a.wait_batch(bid, timeout=120)
    assert done["counts"]["success"] == 50 and done["status"] == "done"
    assert psql_app("select count(*) from (select video_id from changes where change_type='apply' and result='success' group by video_id having count(*)>1) t") == "0"
    assert psql_app("select coalesce(sum(units),0) from quota_usage where status='ok'") == str(50 * 52)


# ─────────────────────────── IT-119 쿼터 소진 → 대기 → 초기화 후 이어서 ───────────────────────────

def test_it_119_quota_exhaustion_pauses_processing_and_resumes_after_reset(fresh_demo):
    """IT-119: 오늘 남은 API 쿼터가 반영 1건분(52)과 조금 뿐이면 사전 점검이 경고하고, 워커는 1건만 반영한 뒤 쿼터 부족으로 멈춘다(건너뜀·실패 처리 없이 대기,
    작업 결과 stopped_by=quota_exhausted). 태평양 날짜가 바뀌어 쿼터가 초기화되면 남은 항목이 이어서 처리된다. 쿼터 ↔ 워커 ↔ 배치 경계. 검증: W-008, NFR-W06"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 3))
    psql_app(f"insert into quota_usage (pt_date, method, units, called_at, status) select (now() at time zone 'America/Los_Angeles')::date, 'it.fill', {6000 - 62}, now(), 'ok'")
    r = a.make_batch([s["id"] for s in ap])
    pre = r.json()["precheck"]
    assert pre["quota_remaining_units"] == 62 and any("쿼터" in w for w in pre["warnings"]), pre["warnings"]
    bid = r.json()["batch"]["id"]
    jid = a.execute(bid, 3).json()["job"]["id"]
    from itlib_b import wait_until
    wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 1, 40, what="1건 반영")
    j = a.wait_job(jid, timeout=60)
    assert j["status"] == "succeeded" and j["result"]["stopped_by"] == "quota_exhausted" and j["result"]["success"] == 1, j
    time.sleep(5)
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert b["counts"]["success"] == 1 and b["counts"]["pending"] == 2 and b["counts"]["skipped"] == 0 and b["counts"]["failed"] == 0 and b["status"] in ("queued", "running"), b["counts"]
    d = a.get("/api/v1/dashboard").json()
    assert d["quota"]["remaining"] == 10 and d["queue"]["pending_items"] == 2
    psql_owner("update quota_usage set pt_date = pt_date - 1")           # 태평양 시간 자정이 지나 쿼터가 초기화됨
    done = a.wait_batch(bid, timeout=60)
    assert done["counts"]["success"] == 3
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == 2 * 52          # 초기화 뒤 오늘 쓴 몫(어제 몫으로 옮긴 것 제외)
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == "3"


# ─────────────────────────── IT-120 KST 하루 경계 ───────────────────────────

def test_it_120_kst_day_boundary_for_daily_cap_and_pt_boundary_for_quota(fresh_demo):
    """IT-120: '오늘 반영 건수'는 한국 시간 자정 기준이다 — 반영 시각을 KST 자정 1초 전/정각으로 옮기면 대시보드 today.applied 가 0/1 이 된다. 쿼터의 하루는
    태평양 시간 날짜라 어제 날짜의 쿼터 사용은 오늘 잔여에 영향이 없다. 변경 이력 ↔ 대시보드 ↔ 쿼터 경계. 검증: W-008, API.md 1-4"""
    a = fresh_demo
    set_cap(a, 5)
    s = approved_suggestion(a, usable_videos(a, 1)[0]["video_id"])
    ch = apply_via_batch(a, s["id"])
    kst = timezone(timedelta(hours=9))
    midnight = datetime.now(kst).replace(hour=0, minute=0, second=0, microsecond=0)
    def put(ts):
        psql_owner(f"update changes set applied_at = '{ts.astimezone(timezone.utc).isoformat()}', created_at = '{ts.astimezone(timezone.utc).isoformat()}' where id = {ch['id']}")
    put(midnight - timedelta(seconds=1))
    assert a.get("/api/v1/dashboard").json()["today"]["applied"] == 0
    put(midnight)
    assert a.get("/api/v1/dashboard").json()["today"]["applied"] == 1
    put(midnight + timedelta(days=1) - timedelta(seconds=1))
    assert a.get("/api/v1/dashboard").json()["today"]["applied"] == 1
    # 쿼터: 어제(태평양) 날짜의 큰 사용량은 오늘 잔여에 영향이 없다
    psql_app("insert into quota_usage (pt_date, method, units, called_at, status) select (now() at time zone 'America/Los_Angeles')::date - 1, 'it.fill', 5000, now(), 'ok'")
    q = a.get("/api/v1/dashboard").json()["quota"]
    assert q["used"] == 52 and q["remaining"] == 6000 - 52


# ─────────────────────────── IT-121 기본 하루 상한(10건) 분할 예약 ───────────────────────────

def test_it_121_default_daily_cap_10_splits_25_items_into_10_10_5_and_dashboard_matches(fresh_demo):
    """IT-121: 설정을 건드리지 않은 기본 하루 상한(10건)에서 25건 배치는 사전 점검이 10/10/5 로 나누고, 워커는 첫날 정확히 10건만 반영한 뒤 멈추며(놓친 날을 몰아서 하지 않음),
    날이 바뀔 때마다 10건·5건씩 이어서 모두 한 번씩만 반영한다. 대시보드(오늘 반영·다음 실행일·남은 건수)와 쿼터 소비(52단위×건수)가 매일 실제와 같다.
    실행 확정 뒤 상한을 바꾸는 경우는 IT-103b 가 본다.
    검증: W-008(하루 10건 분할 예약), W-014, NFR-W03"""
    a = fresh_demo
    assert a.get("/api/v1/settings").json()["daily_apply_cap"] == 10         # 기본값 그대로(set_cap 을 부르지 않는다)
    ap = approve_many(a, usable_videos(a, 25))
    r = a.make_batch([s["id"] for s in ap])
    assert r.status_code == 201
    pre = r.json()["precheck"]
    assert pre["item_count"] == 25 and pre["estimated_units"] == 25 * 52 and pre["confirm_text"] == "실행 25건"
    assert [x["count"] for x in pre["schedule"]] == [10, 10, 5], pre["schedule"]
    bid = r.json()["batch"]["id"]
    assert a.execute(bid, 25).status_code == 202
    ib.wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 10, 120, what="첫째 날 10건")
    time.sleep(6)                                                          # 워커 틱이 몇 번 더 돌아도 11번째는 나가지 않는다
    c = a.get(f"/api/v1/batches/{bid}").json()["counts"]
    assert c["success"] == 10 and c["pending"] == 15 and c["failed"] == 0 and c["skipped"] == 0, c
    d = a.get("/api/v1/dashboard").json()
    assert d["today"]["applied"] == 10 and d["queue"]["pending_items"] == 15 and d["quota"]["used"] == 10 * 52, d
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == "10"
    shift_days(1)
    ib.wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 20, 120, what="둘째 날 10건")
    time.sleep(6)
    assert a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] == 20
    shift_days(1)
    done = a.wait_batch(bid, timeout=120)
    assert done["counts"]["success"] == 25 and done["status"] == "done", done["counts"]
    assert psql_app("select count(*) from (select video_id from changes where change_type='apply' and result='success' group by video_id having count(*)>1) t") == "0"
    assert psql_app("select coalesce(sum(units),0) from quota_usage where status='ok'") == str(25 * 52)
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
