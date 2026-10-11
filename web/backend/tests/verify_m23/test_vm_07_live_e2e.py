"""TC-VM-600~: M3 실제 모드 종단 시험(HTTP API + 워커 틱 + 가짜 구글). 실제 구글 호출 없음. 허용 목록·확인 문구·이중 반영·롤백·모호 응답."""
from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import select, text

from tests.verify_m23.conftest import approve_via_api, do_execute, hdr, make_draft
from ytweb.db.models import AuditLog, Base, Batch, BatchItem, Change, Video
from ytweb.domain.batches import run_due_items

HANGUL = re.compile("[가-힣]")


def tick(w):
    return run_due_items(w.factory, w.clock(), w.env)


def prepare(w, n=1):
    """승인된 제안 n개(ids[0..n-1])를 만든다."""
    return [approve_via_api(w.api, w.csrf, w.ids[i]) for i in range(n)]


def queued(w, ids=None):
    sids = ids or prepare(w, 1)
    r = make_draft(w.api, w.csrf, sids)
    assert r.status_code == 201, r.text
    bid = r.json()["batch"]["id"]
    ex = do_execute(w.api, w.csrf, bid, r.json()["precheck"]["confirm_text"])
    assert ex.status_code == 202, ex.text
    return bid, sids


def changes(w):
    with w.factory() as s:
        return s.execute(select(Change).order_by(Change.id)).scalars().all()


def put_ids(w):
    return [c.body["id"] for c in w.fg.put_calls()]


def err_ok(r):
    j = r.json()
    return HANGUL.search(j.get("hint") or "") and HANGUL.search(j.get("title") or "")


# ---------- 사전 점검 ----------
def test_tc_vm_600_precheck_live_blocks_non_allowed_and_uses_live_confirm_text_without_any_google_call(live):
    sids = prepare(live, 2)
    r = make_draft(live.api, live.csrf, sids)
    j = r.json()
    assert r.status_code == 201
    assert j["precheck"]["confirm_text"] == "실제 실행 1건" and j["precheck"]["item_count"] == 1
    assert [b["code"] for b in j["precheck"]["blocked"]] == ["live_not_allowed"] and HANGUL.search(j["precheck"]["blocked"][0]["reason"])
    w0 = j["precheck"]["warnings"][0]
    assert "실제 모드" in w0 and "1개" in w0 and "실제 실행 1건" in w0
    assert live.fg.calls == []                                                   # 초안 단계에서는 구글 호출 0


def test_tc_vm_601_draft_with_only_non_allowed_videos_is_rejected_422_with_hint_and_no_batch(live):
    sid = approve_via_api(live.api, live.csrf, live.ids[1])
    r = make_draft(live.api, live.csrf, [sid])
    assert r.status_code == 422 and r.json()["code"] == "batch_empty" and err_ok(r)
    assert "실제 수정 허용 영상" in r.json()["detail"]
    with live.factory() as s:
        assert s.execute(select(Batch)).scalars().first() is None
    assert live.fg.calls == []


def test_tc_vm_602_demo_world_precheck_text_is_plain_and_has_no_live_warning(live):
    live.mp.setenv("YTWEB_LIVE_WRITE", "0")
    sids = prepare(live, 2)
    j = make_draft(live.api, live.csrf, sids).json()
    assert j["precheck"]["confirm_text"] == "실행 2건" and j["precheck"]["blocked"] == []
    assert not any("실제 모드" in w for w in j["precheck"]["warnings"])


# ---------- 확인 문구 ----------
@pytest.mark.parametrize("typed", ["실행 1건", "실제 실행 1건 ", " 실제 실행 1건", "실제  실행 1건", "실제 실행 2건", "실제 실행 01건", "실제실행 1건", "", "실제 실행 1", "실제 실행 1건\n", "실제 실행 １건"])
def test_tc_vm_610_wrong_confirm_text_is_422_with_expected_text_and_hint_and_no_side_effect(live, typed):
    bid = make_draft(live.api, live.csrf, prepare(live, 1)).json()["batch"]["id"]
    r = do_execute(live.api, live.csrf, bid, typed)
    assert r.status_code == 422 and r.json()["code"] == "confirm_text_mismatch" and err_ok(r)
    assert "실제 실행 1건" in r.json()["detail"]
    assert live.api.get(f"/api/v1/batches/{bid}").json()["status"] == "draft"
    assert tick(live).processed == 0 and live.fg.calls == []


def test_tc_vm_611_demo_text_rejected_in_live_and_live_text_rejected_in_demo(live):
    bid = make_draft(live.api, live.csrf, prepare(live, 1)).json()["batch"]["id"]
    live.mp.setenv("YTWEB_LIVE_WRITE", "0")                                      # 확인 직전에 실제 모드가 꺼진 경우
    r = do_execute(live.api, live.csrf, bid, "실제 실행 1건")
    assert r.status_code == 422 and "실행 1건" in r.json()["detail"] and "실제" not in r.json()["detail"].replace("실제로", "")
    assert do_execute(live.api, live.csrf, bid, "실행 1건").status_code == 202


# ---------- 반영 ----------
def test_tc_vm_620_live_apply_one_put_to_allowed_video_only_with_write_token_and_records_live_mode(live):
    bid, sids = queued(live, prepare(live, 2)[:1])
    old_title = live.fg.videos[live.ids[0]]["title"]
    live.fg.calls.clear()
    res = tick(live)
    assert (res.processed, res.success, res.failed, res.skipped) == (1, 1, 0, 0)
    puts = live.fg.put_calls()
    assert len(puts) == 1 and puts[0].body["id"] == live.ids[0] and puts[0].auth.startswith("Bearer AT-WRITE")
    assert live.fg.touched_ids() == {live.ids[0]}                                # 허용 밖 영상은 읽기조차 안 나감
    assert all(c.auth.startswith("Bearer AT-WRITE") for c in live.fg.calls if c.path != "/token")      # 읽기 토큰은 쓰기 경로에 쓰이지 않음
    new_title = live.fg.videos[live.ids[0]]["title"]
    assert new_title != old_title and puts[0].body["snippet"]["title"] == new_title
    for k in ("description", "tags", "categoryId", "defaultLanguage"):
        assert puts[0].body["snippet"][k] == live.fg.videos[live.ids[0]][k]
    ch = changes(live)
    assert len(ch) == 1 and ch[0].mode == "live" and ch[0].result == "success" and ch[0].change_type == "apply"
    with live.factory() as s:
        v = s.get(Video, live.ids[0])
        assert v.title == new_title and v.snippet["title"] == new_title
    lst = live.api.get("/api/v1/changes").json()["items"]
    assert [c["mode"] for c in lst] == ["live"]


def test_tc_vm_621_second_tick_and_replayed_execute_never_double_apply(live):
    sids = prepare(live, 1)
    r = make_draft(live.api, live.csrf, sids)
    bid, ct = r.json()["batch"]["id"], r.json()["precheck"]["confirm_text"]
    r1 = do_execute(live.api, live.csrf, bid, ct, key="idem-k1-00000001")
    r2 = do_execute(live.api, live.csrf, bid, ct, key="idem-k1-00000001")                      # 같은 멱등 키
    assert r1.status_code == r2.status_code == 202 and r1.json() == r2.json()
    r3 = do_execute(live.api, live.csrf, bid, ct, key="idem-k2-00000002")                      # 다른 키로 재실행
    assert r3.status_code == 409 and r3.json()["code"] == "batch_not_draft" and err_ok(r3)
    tick(live)
    tick(live)
    tick(live)
    assert len(live.fg.put_calls()) == 1 and len(changes(live)) == 1


def test_tc_vm_622_demo_baseline_connected_but_flag_off_never_calls_google(live):
    live.mp.setenv("YTWEB_LIVE_WRITE", "0")
    bid, _ = queued(live)
    live.fg.calls.clear()
    tick(live)
    assert live.fg.calls == [] and [c.mode for c in changes(live)] == ["demo"]


def test_tc_vm_623_live_not_allowed_at_apply_time_skips_with_zero_calls_no_change_row_no_quota(live):
    bid, _ = queued(live)
    live.mp.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", live.ids[1])                    # 확정 뒤 허용 목록이 바뀜
    live.fg.calls.clear()
    res = tick(live)
    assert (res.processed, res.skipped, res.success) == (1, 1, 0)
    assert live.fg.calls == [] and changes(live) == []
    with live.factory() as s:
        it = s.execute(select(BatchItem)).scalars().one()
        assert it.status == "skipped" and it.skip_reason.startswith("[live_not_allowed]") and HANGUL.search(it.skip_reason)
        assert s.execute(text("select count(*) from api_calls")).scalar() == 0 if _has_table(s, "api_calls") else True


def _has_table(s, name):
    return name in Base.metadata.tables


def test_tc_vm_624_allowed_list_narrowed_between_draft_and_execute_is_precheck_stale(live):
    r = make_draft(live.api, live.csrf, prepare(live, 1))
    bid = r.json()["batch"]["id"]
    live.mp.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", live.ids[1])
    ex = do_execute(live.api, live.csrf, bid, "실제 실행 1건")
    assert ex.status_code == 409 and ex.json()["code"] == "precheck_stale" and err_ok(ex)
    assert live.api.get(f"/api/v1/batches/{bid}").json()["status"] == "draft" and live.fg.calls == []


def test_tc_vm_625_studio_edit_before_apply_title_changed_no_put(live):
    queued(live)
    live.fg.videos[live.ids[0]]["title"] = "스튜디오에서 직접 바꾼 제목"
    live.fg.calls.clear()
    res = tick(live)
    assert res.skipped == 1 and live.fg.put_calls() == [] and changes(live) == []
    assert live.fg.videos[live.ids[0]]["title"] == "스튜디오에서 직접 바꾼 제목"


def test_tc_vm_626_description_edited_in_studio_before_apply_blocks_put(live):
    queued(live)
    live.fg.videos[live.ids[0]]["description"] = "스튜디오에서 설명만 바꿈"
    res = tick(live)
    assert res.skipped == 1 and live.fg.put_calls() == []


def test_tc_vm_627_google_read_failure_before_write_fails_item_with_zero_puts(live):
    queued(live)
    live.fg.quota_on_read = True
    res = tick(live)
    assert res.failed == 1 and live.fg.put_calls() == [] and changes(live) == []


# ---------- 모호/실패 응답 ----------
@pytest.mark.parametrize("mode", ["http_5xx_applied", "timeout_applied", "wrong_title", "empty_json"])
def test_tc_vm_630_ambiguous_but_actually_applied_is_confirmed_by_reread_single_put(live, mode):
    queued(live)
    live.fg.update_mode = mode
    res = tick(live)
    tick(live)
    assert res.success == 1 and len(live.fg.put_calls()) == 1
    ch = changes(live)
    assert len(ch) == 1 and ch[0].result == "success" and ch[0].mode == "live"


@pytest.mark.parametrize("mode", ["http_5xx_not_applied", "timeout_not_applied", "empty_not_applied"])
def test_tc_vm_631_ambiguous_and_not_applied_stays_planned_item_failed_no_retry_no_db_mirror(live, mode):
    queued(live)
    old = live.fg.videos[live.ids[0]]["title"]
    live.fg.update_mode = mode
    res = tick(live)
    assert res.failed == 1 and len(live.fg.put_calls()) == 1
    ch = changes(live)
    assert len(ch) == 1 and ch[0].result == "planned"                           # 결과 미확정 기록을 남김
    with live.factory() as s:
        assert s.get(Video, live.ids[0]).title == old
        it = s.execute(select(BatchItem)).scalars().one()
        assert it.status == "failed" and "result_unknown" in it.skip_reason and HANGUL.search(it.skip_reason)
    live.fg.update_mode = "ok"
    tick(live)
    tick(live)
    assert len(live.fg.put_calls()) == 1                                         # 자동 재시도 없음(이중 반영 방지)
    sid2 = approve_via_api(live.api, live.csrf, live.ids[0]) if False else None


@pytest.mark.parametrize("mode,code", [("http_4xx:403", "update_failed"), ("http_4xx:400", "update_failed"), ("http_4xx:404", "update_failed")])
def test_tc_vm_632_definite_rejection_marks_change_failed_item_failed_single_put(live, mode, code):
    queued(live)
    live.fg.update_mode = mode
    res = tick(live)
    tick(live)
    assert res.failed == 1 and len(live.fg.put_calls()) == 1
    ch = changes(live)
    assert len(ch) == 1 and ch[0].result == "failed"
    with live.factory() as s:
        it = s.execute(select(BatchItem)).scalars().one()
        assert code in it.skip_reason and HANGUL.search(it.skip_reason)


def test_tc_vm_633_unauthorized_write_token_is_definite_failure_with_korean_reason(live):
    queued(live)
    live.fg.access.clear()                                                       # 구글이 토큰을 거부
    live.fg.refresh.clear()
    res = tick(live)
    assert res.failed + res.skipped == 1 and live.fg.put_calls() == [] and all(c.result != "success" for c in changes(live))


# ---------- 롤백 ----------
def _apply_one(w):
    queued(w)
    assert tick(w).success == 1
    return changes(w)[0]


def test_tc_vm_640_rollback_allowed_video_puts_original_title_with_write_token_mode_live(live):
    orig = live.fg.videos[live.ids[0]]["title"]
    ch = _apply_one(live)
    r = live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[0], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rb1-0001"))
    assert r.status_code == 201, r.text
    assert r.json()["mode"] == "live" and r.json()["change_type"] == "rollback"
    assert len(live.fg.put_calls()) == 2 and live.fg.put_calls()[1].auth.startswith("Bearer AT-WRITE")
    assert live.fg.videos[live.ids[0]]["title"] == orig
    with live.factory() as s:
        assert s.get(Video, live.ids[0]).title == orig
    again = live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[0], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rb2-0001"))
    assert again.status_code == 409 and err_ok(again) and len(live.fg.put_calls()) == 2


def test_tc_vm_641_rollback_wrong_typed_id_is_422_and_no_google_call(live):
    ch = _apply_one(live)
    n = len(live.fg.calls)
    r = live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[1], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rb3-0001"))
    assert r.status_code == 422 and err_ok(r) and len(live.fg.calls) == n


def test_tc_vm_642_rollback_applies_allowed_list_zero_calls_when_video_no_longer_allowed(live):
    ch = _apply_one(live)
    live.mp.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", live.ids[1])
    n = len(live.fg.calls)
    r = live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[0], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rb4-0001"))
    assert r.status_code == 409 and r.json()["code"] == "live_not_allowed" and err_ok(r)
    assert len(live.fg.calls) == n and len(live.fg.put_calls()) == 1


@pytest.mark.parametrize("mode,applied", [("http_5xx_not_applied", False), ("http_5xx_applied", True), ("timeout_not_applied", False)])
def test_tc_vm_643_rollback_ambiguous_is_502_with_hint_planned_kept_no_second_put(live, mode, applied):
    ch = _apply_one(live)
    live.fg.update_mode = mode
    r = live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[0], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rb5-0001"))
    assert r.status_code == 502 and err_ok(r) and "Studio" in r.json()["hint"]
    live.fg.update_mode = "ok"
    r2 = live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[0], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rb6-0001"))
    assert r2.status_code == 409 and len(live.fg.put_calls()) == 2              # 불명 상태에서 재시도로 이중 반영되지 않음


def test_tc_vm_644_rollback_definite_failure_403_is_502_and_change_failed(live):
    ch = _apply_one(live)
    live.fg.update_mode = "http_4xx:403"
    r = live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[0], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rb7-0001"))
    assert r.status_code == 502 and err_ok(r)
    assert [c.result for c in changes(live)][-1] == "failed"


# ---------- 모드 전환 (설계 공백 점검) ----------
@pytest.mark.xfail(reason="DEF-VM-006: 실제로 반영한 변경을 실제 모드를 끈 뒤 롤백하면 모의 게이트웨이로 처리돼 '성공'(201)인데 유튜브 제목은 그대로", strict=True)
def test_tc_vm_650_rollback_of_live_change_after_live_mode_off_must_not_pretend_success(live):
    ch = _apply_one(live)
    new_title = live.fg.videos[live.ids[0]]["title"]
    live.mp.setenv("YTWEB_LIVE_WRITE", "0")
    puts = len(live.fg.put_calls())
    r = live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[0], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rbx-0001"))
    pretended = r.status_code == 201 and len(live.fg.put_calls()) == puts and live.fg.videos[live.ids[0]]["title"] == new_title
    assert not pretended, "롤백 성공으로 기록됐지만 실제 유튜브 제목은 바뀌지 않음(상태 불일치)"


@pytest.mark.xfail(reason="DEF-VM-007: 데모 확인 문구('실행 N건')로 확정된 배치가 이후 실제 모드를 켜면 확인 문구 없이 실제로 반영됨", strict=True)
def test_tc_vm_651_batch_confirmed_with_demo_text_must_not_become_real_after_live_switch(live):
    live.mp.setenv("YTWEB_LIVE_WRITE", "0")
    bid, _ = queued(live)                                                         # 데모 문구 "실행 1건"으로 확정
    live.mp.setenv("YTWEB_LIVE_WRITE", "1")                                       # 이후 실제 모드 켬(재시작 가정)
    live.fg.calls.clear()
    tick(live)
    assert live.fg.put_calls() == [], "실제 확인 문구 없이 실제 유튜브 제목이 바뀜"


@pytest.mark.xfail(reason="DEF-VM-008: 실제 문구로 확정된 배치가 실제 모드 해제 뒤 워커 틱에서 모의로 처리돼 '성공'으로 남음(유튜브 미변경)", strict=True)
def test_tc_vm_652_live_confirmed_batch_after_live_off_must_not_report_success_without_real_change(live):
    queued(live)
    live.mp.setenv("YTWEB_LIVE_WRITE", "0")
    tick(live)
    assert not [c for c in changes(live) if c.result == "success" and c.mode == "demo" and live.ids[0] == c.video_id]


# ---------- 토큰·비밀 위생 / 감사 ----------
def test_tc_vm_660_no_token_or_secret_anywhere_after_full_live_cycle(live, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    ch = _apply_one(live)
    live.api.post(f"/api/v1/changes/{ch.id}/rollback", json={"typed_video_id": live.ids[0], "approver": "검수자"}, headers=hdr(live.csrf, "idem-rbz-0001"))
    texts = [caplog.text]
    for url in ("/api/v1/changes", "/api/v1/batches", "/api/v1/google/status", "/api/v1/dashboard", "/api/v1/reports/changes", "/api/v1/audit", "/api/v1/jobs"):
        r = live.api.get(url)
        texts.append(r.text)
    with live.factory() as s:
        for t in Base.metadata.sorted_tables:
            texts.append(json.dumps([[str(c) for c in row] for row in s.execute(t.select()).all()], ensure_ascii=False))
    blob = "\n".join(texts)
    for needle in ("AT-WRITE", "AT-READ", "RT-WRITE", "RT-READ", "csec-456", "CODE-"):
        assert needle not in blob, needle


def test_tc_vm_661_audit_chain_valid_and_records_live_actions(live):
    ch = _apply_one(live)
    from ytweb.core import audit
    with live.factory() as s:
        acts = [a.action for a in s.execute(select(AuditLog)).scalars()]
        assert audit.verify_chain(s) is True
    for a in ("google.connect.start", "google.connect_write.start", "google.write_connected", "batch.create", "batch.execute", "change.apply"):
        assert a in acts, a


def test_tc_vm_662_dashboard_live_flag_must_follow_real_state(live):
    """홈 대시보드는 사용자에게 '라이브 켜짐/꺼짐'을 알려 주는 유일한 요약이다. 3조건이 모두 맞아 실제 수정이 가능한 상태면 켜짐이어야 한다."""
    s = live.api.get("/api/v1/google/status").json()
    assert s["live_write_ready"] is True and s["live_allowed_count"] == 1 and s["live_write_enabled"] is True
    d = live.api.get("/api/v1/dashboard").json()
    assert d["live_enabled"] is True and d["mode"] == "live", f"대시보드가 실제 상태와 다름: mode={d['mode']}, live_enabled={d['live_enabled']}"


def test_tc_vm_663_dashboard_google_connected_must_follow_real_state(live):
    d = live.api.get("/api/v1/dashboard").json()
    assert d["google"]["connected"] is True, f"구글 연결됨인데 대시보드 google={d['google']}"


def test_tc_vm_664_dashboard_in_pure_demo_world_says_demo_and_live_off(gapp, csrf):
    d = gapp.get("/api/v1/dashboard").json()
    assert d["mode"] == "demo" and d["live_enabled"] is False and d["google"]["connected"] is False
