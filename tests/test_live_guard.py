import ast
import copy
import json
import logging
import re
from pathlib import Path

import pytest
from wu4_support import add_candidate, add_change, add_video
from wu5_support import (FAKE_ACCESS, FAKE_REFRESH, NEW_TITLE, NOW, SNIPPET, VID, AppliedThenRaise, World, block_network, fill_quota, http_error, timedelta, ts)

from ytitle import approvals, live_guard
from ytitle import auth as authmod
from ytitle.errors import AuthError, DatabaseError, InputError, QuotaError, SafetyGateError
from ytitle.live_guard import LiveGateError, WriteApiError, apply_live, classify_write_error, compare_after, preview_apply, rollback_live
from ytitle.logging_setup import setup_logging
from ytitle.quota import QuotaManager

SRC = Path(__file__).resolve().parent.parent / "src" / "ytitle"


@pytest.fixture
def w(project, tmp_path, monkeypatch):
    block_network(monkeypatch)
    world = World(project, tmp_path)
    yield world
    world.close()


def go(w):
    return apply_live(w.env(), w.cid)


def assert_blocked_before_write(w, step, *, token_loads=0, seeded=0, candidate="approved"):
    """게이트 실패의 공통 결과: 쓰기 호출 0회, 쓰기 토큰 로드 없음(11단계 제외), 후보 상태 유지, 테스트가 미리 넣은(seeded) 행 말고는 aborted 행 1개만."""
    assert w.server.update_calls == []
    assert w.write_token_loads == token_loads
    rows = w.changes()[seeded:]
    assert [(r["change_type"], r["result"], r["error_code"]) for r in rows] == [("apply", "aborted", f"GATE-{step:02d}")]
    assert w.candidate_status() == candidate
    assert not any(q[0] == "videos.update" for q in w.quota())


# ───────────── 정상 경로 ─────────────

def test_all_gates_pass_calls_update_exactly_once(w):
    """TC-570: 14단계를 모두 통과하면 videos.update를 정확히 1회 호출하고, 이력 success·후보 applied·승인 소진·쿼터 기록이 남는다. [FR-009, FR-012, SEC-001, SEC-010, SEC-014]"""
    result = go(w)
    assert result.ok and result.kind == "apply" and [g.step for g in result.gates] == list(range(1, 13))
    assert len(w.server.update_calls) == 1 and w.server.update_calls[0]["part"] == "snippet"
    rows = w.changes()
    assert [(r["change_type"], r["result"], r["approver"]) for r in rows] == [("apply", "success", "홍길동")]
    assert json.loads(rows[0]["verify_result_json"])["ok"] is True
    assert w.candidate_status() == "applied" and w.approval_file()["used"] is True
    assert w.quota() == [("videos.list", 1, "ok"), ("videos.update", 50, "ok"), ("videos.list", 1, "ok")]
    assert w.server.items[VID]["snippet"]["title"] == NEW_TITLE
    assert "[완료] 제목 변경을 마쳤습니다" in w.output() and f"rollback --change {rows[0]['id']}" in w.output()


def test_write_happens_only_after_human_confirmation_in_documented_order(w):
    """TC-571: 순서: 재조회(6) → 영상 ID 확인(10) → 쓰기 토큰 로드(11) → videos.update(12) → 재조회 검증(13). 쓰기 토큰은 1번만, 사람 확인 뒤에만 읽는다. [SEC-015, SEC-001, FR-012]"""
    go(w)
    kinds = [e[0] for e in w.events]
    assert kinds == ["read_service", "list", "confirm", "write_token", "update", "read_service", "list"]
    assert w.events[2] == ("confirm", VID) and w.write_token_loads == 1


def test_request_body_preserves_every_field_and_backup_is_whole_snippet(w):
    """TC-572: 요청 본문은 description·tags·categoryId 등 snippet 전체를 그대로 두고 제목만 바꾸며, 백업은 적용 직전 snippet 전체다. [FR-009, SEC-005, T-15]"""
    original = copy.deepcopy(w.server.items[VID]["snippet"])
    go(w)
    sent = w.server.update_calls[0]["body"]
    assert sent["id"] == VID and set(sent) == {"id", "snippet"}
    assert {k: v for k, v in sent["snippet"].items() if k != "title"} == {k: v for k, v in original.items() if k != "title"}
    assert sent["snippet"]["title"] == NEW_TITLE and sent["snippet"]["description"] == original["description"] and sent["snippet"]["tags"] == original["tags"] and sent["snippet"]["categoryId"] == "26"
    backup = json.loads(w.changes()[0]["backup_snippet_json"])
    assert backup == original and backup["title"] == original["title"]


def test_body_is_built_from_fresh_snippet_not_stored_copy(w):
    """TC-573: 본문은 저장본이 아니라 6단계에서 다시 조회한 snippet으로 만든다(승인 당시와 같을 때만 통과하므로 결과가 같아도 출처가 다르다). [SEC-009, SEC-005]"""
    seen = []
    real = live_guard.build_write_body

    def spy(video_id, snippet, new_title):
        seen.append(snippet)
        return real(video_id, snippet, new_title)

    w.server.items[VID]["snippet"]["localized"] = dict(w.server.items[VID]["snippet"]["localized"])
    import pytest as _p
    mp = _p.MonkeyPatch()
    mp.setattr(live_guard, "build_write_body", spy)
    try:
        go(w)
    finally:
        mp.undo()
    assert len(seen) == 1 and seen[0] == w.server.items[VID]["snippet"] | {"title": SNIPPET["title"]}


# ───────────── 게이트 하나씩 실패 ─────────────

def _studio_title(w):
    w.server.items[VID]["snippet"]["title"] = "Studio에서 바꾼 제목"


def _studio_desc(w):
    w.server.items[VID]["snippet"]["description"] = "Studio에서 고친 설명"


def _quota_short(w):
    fill_quota(w.conn, w.clock, 6000 - 51)


def _forge(w):
    d = w.approval_file()
    d["approver"] = "도둑"
    approvals.approval_path(w.settings, VID, w.cid).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _expire(w):
    w.clock.advance(timedelta(hours=24))


def _use_up(w):
    approvals.mark_used(w.settings, approvals.load_approval(w.settings, VID, w.cid), NOW)


def _no_approval_file(w):
    approvals.approval_path(w.settings, VID, w.cid).unlink()


def _candidate_not_approved(w):
    w.conn.execute("UPDATE title_candidates SET status='filtered' WHERE id=?", (w.cid,))
    w.conn.commit()


def _other_title_approved(w):
    w.conn.execute("UPDATE title_candidates SET candidate_title='승인 뒤에 바뀐 다른 후보 제목입니다' WHERE id=?", (w.cid,))
    w.conn.commit()


def _no_baseline_blank(w):
    w.conn.execute("DELETE FROM metrics_snapshots")
    w.conn.commit()
    w.baseline_answer = "blank"


def _no_baseline_wrong(w):
    _no_baseline_blank(w)
    w.baseline_answer = "wrong"


def _no_baseline_eof(w):
    _no_baseline_blank(w)
    w.baseline_answer = "eof"


def _drop_description(monkeypatch):
    real = live_guard.build_write_body

    def bad(video_id, snippet, new_title):
        body = real(video_id, snippet, new_title)
        body["snippet"].pop("description")
        return body

    monkeypatch.setattr(live_guard, "build_write_body", bad)


GATE_CASES = [
    pytest.param(2, lambda w, mp: w.set(enable_live=False), "enable_live", id="2-enable_live-off"),
    pytest.param(3, lambda w, mp: w.set(live_allowlist=()), "비어 있어", id="3-allowlist-empty"),
    pytest.param(3, lambda w, mp: w.set(live_allowlist=("zzzzzzzzzzz",)), "allowlist에 없어", id="3-not-in-allowlist"),
    pytest.param(4, lambda w, mp: _quota_short(w), "쿼터", id="4-quota-short"),
    pytest.param(5, lambda w, mp: w.apply_change_row(change_type="apply", result="success", at=NOW - timedelta(hours=1)), "교체 제한", id="5-interval"),
    pytest.param(5, lambda w, mp: [w.apply_change_row(change_type="apply", result="success", at=NOW - timedelta(hours=100 * i)) for i in (1, 2, 3)], "교체 제한", id="5-count"),
    pytest.param(5, lambda w, mp: w.apply_change_row(change_type="apply", result="success", at=NOW - timedelta(hours=100)), "노출수", id="5-impressions-unknown"),
    pytest.param(5, lambda w, mp: [add_change(w.conn, vid=f"other{i}000000", at=NOW - timedelta(hours=1)) for i in range(3)], "하루 상한", id="5-daily-cap"),
    pytest.param(5, lambda w, mp: w.apply_change_row(change_type="apply", result="planned", at=NOW - timedelta(days=10)), "planned", id="5-stale-planned"),
    pytest.param(6, lambda w, mp: _studio_title(w), "구글의 제목이 다릅니다", id="6-title-changed-in-studio"),
    pytest.param(6, lambda w, mp: w.server.items.clear(), "다시 조회하지 못했습니다", id="6-video-gone"),
    pytest.param(6, lambda w, mp: w.server.list_behaviors.extend([http_error(500)] * 3), "재조회", id="6-read-5xx"),
    pytest.param(6, lambda w, mp: w.server.items[VID]["snippet"].pop("categoryId"), "categoryId", id="6-fresh-without-category"),
    pytest.param(7, lambda w, mp: _studio_desc(w), "계획 해시 불일치", id="7-info-changed-since-approval"),
    pytest.param(7, lambda w, mp: _no_approval_file(w), "승인 파일이 없습니다", id="7-no-approval"),
    pytest.param(7, lambda w, mp: _expire(w), "만료", id="7-expired"),
    pytest.param(7, lambda w, mp: _use_up(w), "이미 사용", id="7-already-used"),
    pytest.param(7, lambda w, mp: _forge(w), "인증값", id="7-forged"),
    pytest.param(7, lambda w, mp: _candidate_not_approved(w), "승인 상태가 아닙니다", id="7-candidate-not-approved"),
    pytest.param(7, lambda w, mp: _other_title_approved(w), "새 제목", id="7-other-new-title"),
    pytest.param(8, lambda w, mp: _no_baseline_blank(w), "변경 전 지표 없이", id="8-no-baseline-declined"),
    pytest.param(8, lambda w, mp: _no_baseline_wrong(w), "변경 전 지표 없이", id="8-no-baseline-wrong-typing"),
    pytest.param(8, lambda w, mp: _no_baseline_eof(w), "변경 전 지표 없이", id="8-no-baseline-eof"),
    pytest.param(9, lambda w, mp: _drop_description(mp), "보존하지 않아", id="9-body-loses-description"),
    pytest.param(10, lambda w, mp: setattr(w, "video_answer", "wrong"), "영상 ID 확인", id="10-wrong-id"),
    pytest.param(10, lambda w, mp: setattr(w, "video_answer", "blank"), "영상 ID 확인", id="10-blank"),
    pytest.param(10, lambda w, mp: setattr(w, "video_answer", "eof"), "영상 ID 확인", id="10-eof"),
]


@pytest.mark.parametrize("step,breaker,text", GATE_CASES)
def test_each_gate_failure_stops_before_any_write(w, monkeypatch, step, breaker, text):
    """TC-574: 14단계 중 1~10단계 각각이 실패하면 videos.update 가짜 호출 0회·쓰기 토큰 미로드·승인 미소진이며 aborted 행(GATE-nn) 하나만 남고 종료 코드 3이다. [SEC-001, SEC-002, SEC-004, SEC-009, SEC-012, SEC-014, SEC-020, FR-012]"""
    breaker(w, monkeypatch)
    seeded = len(w.changes())
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == step and exc.value.exit_code == 3 and re.search(text, exc.value.message)
    assert_blocked_before_write(w, step, seeded=seeded, candidate="filtered" if "승인 상태가 아닙니다" in text else "approved")
    path = approvals.approval_path(w.settings, VID, w.cid)
    if path.exists() and "인증값" not in text and "이미 사용" not in text:
        assert w.approval_file()["used"] is False   # 막힌 시도는 승인을 소진하지 않는다
    assert f"{step}단계에서 막혀" in w.output()


def test_step1_requires_live_flag(w):
    """TC-575: 1단계: live_flag가 거짓이면 어떤 조건이 맞아도 중단한다(엔진 수준 방어). 쓰기 0회, aborted GATE-01 기록. [SEC-001]"""
    with pytest.raises(LiveGateError) as exc:
        apply_live(w.env(), w.cid, live_flag=False)
    assert exc.value.step == 1 and "--live" in exc.value.message
    assert_blocked_before_write(w, 1)
    assert w.events == []   # 구글 서비스도 만들지 않았다


@pytest.mark.parametrize("value", [None, 1, "true", "yes"])
def test_enable_live_must_be_boolean_true(w, value):
    """TC-576: enable_live는 불리언 true만 인정한다(문자열 'true'·1 등은 거부). [SEC-001]"""
    w.set(enable_live=value)
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 2


def test_enable_live_in_settings_yaml_is_ignored(project, tmp_path, monkeypatch):
    """TC-577: settings.yaml에 enable_live=true와 허용 목록이 있어도 무시한다(settings.local.yaml에서만 유효): 2단계에서 중단, 쓰기 0회. [SEC-001, SEC-012, ADR-010]"""
    block_network(monkeypatch)
    (project / "config" / "settings.yaml").write_text(f'live:\n  enable_live: true\n  live_allowlist: ["{VID}"]\n', encoding="utf-8")
    w = World(project, tmp_path, enable_live=False, allowlist=())
    (project / "config" / "settings.local.yaml").unlink()
    from ytitle.config import load_settings
    w.settings = load_settings(project, env={"YT_TOKEN_DIR": str(w.tokens)})
    assert w.settings.enable_live is False and w.settings.live_allowlist == () and w.settings.warnings
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 2
    assert_blocked_before_write(w, 2)
    w.close()


def test_gate_order_is_exactly_the_documented_one(w, monkeypatch):
    """TC-578: 여러 조건이 동시에 틀려 있을 때 문서 순서(2→3→…→10)대로 하나씩만 드러난다: 앞 단계를 고칠 때마다 다음 단계에서 멈춘다. [SEC-001, DESIGN 5-2]"""
    w.set(enable_live=False, live_allowlist=())
    fill_quota(w.conn, w.clock, 6000 - 51)
    w.apply_change_row(change_type="apply", result="success", at=NOW - timedelta(hours=1))
    _studio_title(w)
    _no_approval_file(w)
    _no_baseline_wrong(w)
    _drop_description(monkeypatch)
    w.video_answer = "wrong"
    w.write_auth_error = AuthError("토큰 없음", "다시 로그인")

    def stop_step():
        with pytest.raises(LiveGateError) as exc:
            go(w)
        return exc.value.step

    assert stop_step() == 2
    w.set(enable_live=True)
    assert stop_step() == 3
    w.set(live_allowlist=(VID,))
    assert stop_step() == 4
    w.conn.execute("DELETE FROM quota_usage WHERE method='prefill'")
    w.conn.commit()
    assert stop_step() == 5
    w.conn.execute("DELETE FROM title_changes")
    w.conn.commit()
    assert stop_step() == 6
    w.server.items[VID]["snippet"]["title"] = SNIPPET["title"]
    add_video(w.conn, fetched_at=ts(NOW - timedelta(hours=1)))   # 6단계가 갱신해 둔 저장본을 원래대로
    assert stop_step() == 7
    w.approve()
    assert stop_step() == 8
    w.baseline_answer = "ok"
    assert stop_step() == 9
    monkeypatch.undo()
    assert stop_step() == 10
    w.video_answer = "ok"
    assert stop_step() == 11
    assert w.server.update_calls == [] and w.write_token_loads == 1
    w.write_auth_error = None
    # 모두 고치면 마침내 한 번 호출된다
    assert go(w).ok and len(w.server.update_calls) == 1


# ───────────── 쿼터 경계 ─────────────

@pytest.mark.parametrize("used,ok", [(6000 - 52, True), (6000 - 51, False)])
def test_quota_boundary_needs_update_plus_two_reads(w, used, ok):
    """TC-579: 쿼터는 남은 양이 쓰기 50 + 조회 2 = 52 units 이상일 때만 통과한다(52 통과, 51 거부). [SEC-002, FR-015]"""
    fill_quota(w.conn, w.clock, used)
    if ok:
        assert go(w).ok
    else:
        with pytest.raises(LiveGateError) as exc:
            go(w)
        assert exc.value.step == 4 and w.server.update_calls == []


def test_daily_cap_boundary_two_pass(w):
    """TC-580: 하루 live 적용 상한(3) 경계: 오늘 다른 영상에 2건 적용했으면 통과하고 이번이 3건째가 된다(3건이면 5단계 TC-574에서 중단). [SEC-020, T-16]"""
    for i in range(2):
        add_change(w.conn, vid=f"other{i}000000", at=NOW - timedelta(hours=1))
    assert go(w).ok


def test_daily_cap_counts_the_apply_just_made(w):
    """TC-581: 같은 날 3건째 적용이 성공한 뒤에는 4건째가 5단계에서 막힌다. [SEC-020]"""
    for i in range(2):
        add_change(w.conn, vid=f"other{i}000000", at=NOW - timedelta(hours=1))
    assert go(w).ok
    other = "otherVID0001"
    from wu4_support import SNIPPET as SN, add_video
    add_video(w.conn, vid=other, snippet={**SN, "title": "다른 영상 제목"}, fetched_at=ts(NOW - timedelta(minutes=30)))
    cid2 = add_candidate(w.conn, vid=other, title="다른 영상의 새 제목입니다 난방비", status="approved")
    w.set(live_allowlist=(VID, other))
    with pytest.raises(LiveGateError) as exc:
        apply_live(w.env(), cid2)
    assert exc.value.step == 5 and "하루 상한" in exc.value.message
    assert w.server.update_calls and len(w.server.update_calls) == 1


# ───────────── 사후 검증(13~14단계) ─────────────

def test_verification_failure_records_success_with_ok_false_and_never_rolls_back(w):
    """TC-582: 적용 후 설명이 사라졌으면 사후 검증 실패: result=success + verify.ok=false, 경보와 rollback 안내만 하고 자동 롤백(추가 update 호출)은 하지 않는다. [SEC-010, SEC-001, DESIGN 8-5]"""
    w.server.drop_on_update = ("description",)
    result = go(w)
    assert result.ok is False and len(w.server.update_calls) == 1
    rows = w.changes()
    assert [(r["change_type"], r["result"]) for r in rows] == [("apply", "success")]
    v = json.loads(rows[0]["verify_result_json"])
    assert v["ok"] is False and v["preserved"]["description"] is False and v["title_ok"] is True
    out = w.output()
    assert "사후 검증 실패" in out and "description" in out and "자동으로 되돌리지 않았습니다" in out and "rollback --change" in out
    assert w.candidate_status() == "applied"


def test_title_not_reflected_is_a_verification_failure(w):
    """TC-583: 호출은 성공했는데 재조회 제목이 새 제목이 아니면 검증 실패로 기록한다. [SEC-010]"""
    w.server.ignore_update = True
    result = go(w)
    v = json.loads(w.changes()[0]["verify_result_json"])
    assert result.ok is False and v["title_ok"] is False and "제목이 새 제목과 다릅니다" in w.output()


def test_verification_read_failure_is_recorded_not_hidden(w):
    """TC-584: 사후 재조회 자체가 실패하면 검증을 하지 못했다고 기록·경보한다(성공으로 속이지 않음). 호출은 1회뿐이다. [SEC-010]"""
    w.server.list_behaviors = [None, http_error(500), http_error(500), http_error(500)]
    result = go(w)
    v = json.loads(w.changes()[0]["verify_result_json"])
    assert result.ok is False and v["ok"] is False and v["checked"] is False and "검증을 하지 못했습니다" in w.output()
    assert len(w.server.update_calls) == 1 and w.changes()[0]["result"] == "success"


def test_other_changed_fields_are_reported_but_not_a_failure(w):
    """TC-585: 설명·태그·카테고리 외 항목이 달라지면 검증 실패로 보지 않고 이름만 알린다. [SEC-010, 확인 필요]"""
    def tweak(server, body):
        server.items[VID]["snippet"]["thumbnails"] = {"default": {"url": "https://example.invalid/t.jpg"}}

    w.server.update_behaviors = [tweak]
    result = go(w)
    v = json.loads(w.changes()[0]["verify_result_json"])
    assert result.ok and v["other_changed"] == ["thumbnails"] and "thumbnails" in w.output()


def test_compare_after_rules():
    """TC-586: 비교 규칙: 태그 순서가 달라도 변경으로 본다, 양쪽에 없는 선택 항목은 같다고 본다, localized는 무시한다, 제목이 다르면 실패. [SEC-010]"""
    before = {"title": "a", "description": "d", "tags": ["x", "y"], "categoryId": "26", "localized": {"title": "a"}}
    same = compare_after(before, {**before, "title": "b", "localized": {"title": "b"}}, "b")
    assert same["ok"] and same["other_changed"] == [] and same["preserved"]["defaultLanguage"] is True
    assert not compare_after(before, {**before, "title": "b", "tags": ["y", "x"]}, "b")["ok"]
    assert not compare_after(before, {**before, "title": "b", "categoryId": "27"}, "b")["ok"]
    assert not compare_after(before, {**before, "title": "c"}, "b")["ok"]
    assert not compare_after(before, {k: v for k, v in before.items() if k != "tags"} | {"title": "b"}, "b")["ok"]


# ───────────── 12단계 도중 실패 ─────────────

def test_definite_rejection_400_marks_failed_with_one_attempt(w):
    """TC-587: 구글이 400으로 거절하면(처리되지 않음이 분명) 재시도 없이 1회 호출, 이력 failed·쿼터 50 units 차감 유지, 후보는 approved 그대로, 승인은 소진된다. [SEC-003, SEC-006, ADR-008]"""
    w.server.update_behaviors = [http_error(400, "invalidValue")]
    with pytest.raises(WriteApiError) as exc:
        go(w)
    assert exc.value.definite and "HTTP 400 invalidValue" == exc.value.cause
    assert len(w.server.update_calls) == 1 and w.sleeps == []
    assert [(r["result"], r["error_code"]) for r in w.changes()] == [("failed", "HTTP 400 invalidValue")]
    assert ("videos.update", 50, "failed") in w.quota() and w.candidate_status() == "approved" and w.approval_file()["used"] is True
    assert w.server.items[VID]["snippet"]["title"] == SNIPPET["title"]


@pytest.mark.parametrize("status,reason,exc_type", [(403, "quotaExceeded", QuotaError), (403, "dailyLimitExceeded", QuotaError), (401, "", AuthError), (403, "forbidden", AuthError)])
def test_quota_and_auth_rejections_are_not_retried(w, status, reason, exc_type):
    """TC-588: 쿼터 초과(403)·인증 거부(401/403)는 재시도하지 않고 failed로 기록한다(제목은 바뀌지 않음). [SEC-003, SEC-002, SEC-015]"""
    w.server.update_behaviors = [http_error(status, reason)]
    with pytest.raises(exc_type):
        go(w)
    assert len(w.server.update_calls) == 1 and w.changes()[0]["result"] == "failed" and w.candidate_status() == "approved"


def test_429_is_retried_twice_then_failed_as_definite(w):
    """TC-589: 429는 최대 2회 재시도(1초→2초 대기)한 뒤 처리되지 않았음이 분명한 실패(failed)로 기록하며, 시도마다 50 units를 선예약해 차감한다. [SEC-003, NFR-004, ADR-008]"""
    w.server.update_behaviors = [http_error(429)] * 3
    with pytest.raises(WriteApiError) as exc:
        go(w)
    assert exc.value.definite and len(w.server.update_calls) == 3 and w.sleeps == [1.0, 2.0]
    assert [q for q in w.quota() if q[0] == "videos.update"] == [("videos.update", 50, "failed")] * 3
    assert w.changes()[0]["result"] == "failed"


def test_503_then_success_charges_both_attempts(w):
    """TC-590: 503 한 번 뒤 성공하면 1초 대기 후 재시도해 success로 끝나고, 실패한 시도의 쿼터도 차감이 남는다. [SEC-003, ADR-008]"""
    w.server.update_behaviors = [http_error(503)]
    assert go(w).ok
    assert len(w.server.update_calls) == 2 and w.sleeps == [1.0]
    assert [q for q in w.quota() if q[0] == "videos.update"] == [("videos.update", 50, "failed"), ("videos.update", 50, "ok")]
    assert [r["result"] for r in w.changes()] == ["success"]


def test_persistent_5xx_leaves_planned_and_quota_when_state_unknown(w):
    """TC-591: 5xx가 계속되면 반영 여부를 알 수 없으므로 재조회로 확인하고, 새 제목이 아니면 이력을 planned로 남긴다(자동 삭제 없음). 쿼터 150 units 차감 유지, 후보 approved 유지, 안내 출력. [NFR-008, SEC-006, ADR-008]"""
    w.server.update_behaviors = [http_error(503)] * 3
    with pytest.raises(WriteApiError) as exc:
        go(w)
    assert exc.value.definite is False and "Studio에서 현재 제목을 확인" in exc.value.next_step
    rows = w.changes()
    assert [(r["change_type"], r["result"]) for r in rows] == [("apply", "planned")]
    assert [q for q in w.quota() if q[0] == "videos.update"] == [("videos.update", 50, "failed")] * 3
    assert w.candidate_status() == "approved" and len(w.server.update_calls) == 3 and w.sleeps == [1.0, 2.0]
    assert "결과 미확정(planned)" in w.output()
    # 남은 planned는 같은 영상의 다음 시도를 막는다(자동 정리 없음)
    w.approve()
    with pytest.raises(LiveGateError) as exc2:
        go(w)
    assert exc2.value.step == 5 and "planned" in exc2.value.message and [r["result"] for r in w.changes()] == ["planned", "aborted"]


def test_timeout_after_server_applied_is_recovered_by_reread(w):
    """TC-592: 응답이 끊겼지만(타임아웃) 서버에는 반영됐으면, 재조회로 새 제목을 확인해 success로 이어서 검증한다(메모 포함). [SEC-010, NFR-008]"""
    w.server.update_behaviors = [AppliedThenRaise(TimeoutError("timed out"))] * 3
    result = go(w)
    v = json.loads(w.changes()[0]["verify_result_json"])
    assert result.ok and v["note"] and w.changes()[0]["result"] == "success" and w.candidate_status() == "applied"
    assert "재조회로 새 제목이 반영된 것을 확인" in w.output() and len(w.server.update_calls) == 3


def test_timeout_then_unreadable_state_stays_planned(w):
    """TC-593: 타임아웃 뒤 재조회도 실패하면 결과를 알 수 없으므로 planned로 남기고 후보·승인 상태를 되돌리지 않는다. [NFR-008]"""
    w.server.update_behaviors = [TimeoutError("timed out")] * 3
    w.server.list_behaviors = [None] + [http_error(500)] * 6
    with pytest.raises(WriteApiError):
        go(w)
    assert [r["result"] for r in w.changes()] == ["planned"] and w.candidate_status() == "approved"


def test_definite_error_after_an_unknown_attempt_is_still_unknown(w):
    """TC-594: 앞선 시도가 '알 수 없음'(503)이었다면 마지막이 분명한 거절(400)이어도 알 수 없음으로 취급해 planned로 남긴다. [fail-closed]"""
    w.server.update_behaviors = [http_error(503), http_error(400)]
    with pytest.raises(WriteApiError) as exc:
        go(w)
    assert exc.value.definite is False and [r["result"] for r in w.changes()] == ["planned"]


def test_quota_runs_out_during_retry_keeps_state_unknown(w):
    """TC-595: 재시도 선예약이 쿼터 상한에 걸려도(첫 시도가 503) 상태를 알 수 없음으로 취급해 planned로 남기고 호출은 더 하지 않는다. [SEC-002, ADR-008]"""
    w.set(daily_limit_units=100)
    w.server.update_behaviors = [http_error(503)]
    with pytest.raises(WriteApiError):
        go(w)
    assert len(w.server.update_calls) == 1 and [r["result"] for r in w.changes()] == ["planned"]
    assert [q[2] for q in w.quota() if q[0] == "videos.update"] == ["failed"]


def test_unexpected_exception_is_unknown_and_secrets_stay_out(w, tmp_path):
    """TC-596: 예상 못 한 예외(메시지에 토큰 포함)도 반영 여부 불명으로 planned에 남기고, 메시지·로그·DB·화면 어디에도 토큰이 나오지 않는다. [SEC-008, SEC-015]"""
    logger = setup_logging(w.settings.data_dir, "run1")
    env = w.env()
    env.logger = logger
    w.server.update_behaviors = [RuntimeError(f"Authorization: Bearer {FAKE_ACCESS} {FAKE_REFRESH}")]
    with pytest.raises(WriteApiError) as exc:
        apply_live(env, w.cid)
    for h in list(logger.handlers):
        h.flush()
    blob = "\n".join([exc.value.message, exc.value.next_step, exc.value.cause, w.output(), "\n".join(w.conn.iterdump()), (w.settings.data_dir / "logs" / "ytitle.log").read_text(encoding="utf-8"), repr(exc.value.__cause__)])
    assert FAKE_ACCESS not in blob and FAKE_REFRESH not in blob and "RuntimeError" in exc.value.cause
    assert [r["result"] for r in w.changes()] == ["planned"] and len(w.server.update_calls) == 1


def test_keyboard_interrupt_during_update_leaves_planned_and_reraises(w):
    """TC-597: 호출 중 Ctrl+C: 더 호출하지 않고 planned로 남기며 예외를 그대로 올린다. 쿼터 차감은 유지된다. [NFR-008, ADR-008]"""
    w.server.update_behaviors = [KeyboardInterrupt()]
    with pytest.raises(KeyboardInterrupt):
        go(w)
    assert [r["result"] for r in w.changes()] == ["planned"] and ("videos.update", 50, "failed") in w.quota() and len(w.server.update_calls) == 1
    assert "결과 미확정(planned)" in w.output()


def test_keyboard_interrupt_at_confirmation_records_abort(w):
    """TC-598: 영상 ID 입력 중 Ctrl+C: 쓰기 없이 aborted(GATE-10)를 남기고 예외를 그대로 올린다. [NFR-008]"""
    w.video_answer = "interrupt"
    with pytest.raises(KeyboardInterrupt):
        go(w)
    assert_blocked_before_write(w, 10)


# ───────────── 11단계 세부 ─────────────

def test_write_token_failure_aborts_without_consuming_approval(w):
    """TC-599: 쓰기 로그인이 없거나 만료돼 쓰기 토큰을 못 읽으면 11단계에서 중단하고, 승인은 소진하지 않으며 DB에는 aborted만 남는다. [SEC-015, SEC-001]"""
    w.write_auth_error = AuthError("로그인 정보가 없습니다.", "먼저 `python -m ytitle auth --write`를 실행하세요.")
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 11 and "auth --write" in exc.value.next_step
    assert_blocked_before_write(w, 11, token_loads=1)
    assert w.approval_file()["used"] is False


def test_backup_failure_aborts_before_consuming_approval(w):
    """TC-600: DB 사본(백업)을 만들 수 없으면 쓰기 전에 중단하고 승인은 소진하지 않는다. [NFR-010, SEC-006]"""
    (w.settings.data_dir / "backups").write_text("파일이라 폴더를 못 만듦", encoding="utf-8")
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 11 and "백업" in exc.value.message
    assert_blocked_before_write(w, 11, token_loads=1)
    assert w.approval_file()["used"] is False


def test_backup_copy_is_made_before_the_write(w):
    """TC-601: 쓰기 전 DB 사본이 data/backups에 만들어지고, 그 사본에는 아직 이번 변경의 planned 행이 없다. [NFR-010]"""
    go(w)
    copies = list((w.settings.data_dir / "backups").glob("ytitle_*.sqlite3"))
    assert len(copies) == 1
    import sqlite3
    c = sqlite3.connect(copies[0])
    assert c.execute("SELECT COUNT(*) FROM title_changes").fetchone()[0] == 0
    c.close()


def test_history_insert_failure_after_approval_consumed_leaves_no_write(w, monkeypatch):
    """TC-602: planned 행을 만들지 못하면 호출하지 않는다. 승인은 이미 소진되어 새 승인이 필요하다(최대 1회 우선). aborted GATE-11 기록. [SEC-014, NFR-008]"""
    def boom(*a, **k):
        raise DatabaseError("변경 이력을 처리하지 못했습니다.", "DB 확인")

    monkeypatch.setattr(live_guard, "begin_change", boom)
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 11
    assert w.server.update_calls == [] and [(r["result"], r["error_code"]) for r in w.changes()] == [("aborted", "GATE-11")]
    assert w.approval_file()["used"] is True and w.candidate_status() == "approved"
    monkeypatch.undo()
    with pytest.raises(LiveGateError) as again:
        go(w)
    assert again.value.step == 7 and "이미 사용" in again.value.message


def test_approval_consume_failure_aborts_before_history(w, monkeypatch):
    """TC-603: 승인 소진(used=true 기록)에 실패하면 이력 행도 호출도 없이 중단한다. [SEC-014]"""
    def boom(*a, **k):
        raise approvals.ApprovalError("승인 파일이 확인한 뒤에 바뀌었습니다.", "새로 승인")

    monkeypatch.setattr(approvals, "mark_used", boom)
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 11
    assert_blocked_before_write(w, 11, token_loads=1)


def test_quota_reservation_failure_after_planned_marks_aborted(w, monkeypatch):
    """TC-604: planned 행을 만든 뒤 쓰기 쿼터 예약이 거절되면 호출하지 않고 그 행을 aborted(GATE-11)로 끝낸다(중복 aborted 행 없음). [SEC-002, ADR-008]"""
    real = QuotaManager.reserve

    def reserve(self, method, units, run_id):
        if method == "videos.update":
            raise QuotaError("쿼터 부족", "내일")
        return real(self, method, units, run_id)

    monkeypatch.setattr(QuotaManager, "reserve", reserve)
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 11 and w.server.update_calls == []
    assert [(r["result"], r["error_code"]) for r in w.changes()] == [("aborted", "GATE-11")]
    assert w.candidate_status() == "approved"


def test_record_finish_failure_after_success_is_loud(w, monkeypatch):
    """TC-605: 구글에는 반영됐는데 이력을 success로 바꾸지 못하면 경보를 출력하고 오류를 올린다(조용히 넘어가지 않음). [NFR-008]"""
    def boom(*a, **k):
        raise DatabaseError("변경 이력을 처리하지 못했습니다.", "DB 확인")

    monkeypatch.setattr(live_guard, "finish_change", boom)
    with pytest.raises(DatabaseError):
        go(w)
    assert len(w.server.update_calls) == 1 and "변경 기록" in w.output() and [r["result"] for r in w.changes()] == ["planned"]


# ───────────── 계획 단계 실패와 재사용 ─────────────

def test_blocked_candidate_is_refused_and_audited(w):
    """TC-606: 검증에서 차단된 후보는 게이트 이전(계획 단계)에서 거부하고 aborted(PLAN) 행으로 남긴다. 쓰기 0회. [SEC-001, NFR-008]"""
    w.conn.execute("UPDATE title_candidates SET status='blocked', validation_result='block' WHERE id=?", (w.cid,))
    w.conn.commit()
    with pytest.raises(SafetyGateError):
        go(w)
    assert [(r["result"], r["error_code"]) for r in w.changes()] == [("aborted", "PLAN")] and w.server.update_calls == [] and w.events == []


def test_unknown_candidate_is_refused_without_audit(w):
    """TC-607: 없는 후보 번호는 오류로 거부하고(기록할 대상이 없어) 이력을 만들지 않는다. [FR-005]"""
    with pytest.raises(InputError):
        apply_live(w.env(), 999)
    assert w.changes() == [] and w.server.update_calls == []


def test_audit_failure_does_not_mask_the_original_block(w, monkeypatch):
    """TC-608: aborted 기록 자체가 실패해도 원래 중단 사유(게이트 오류)가 가려지지 않는다. [NFR-008]"""
    def boom(*a, **k):
        raise DatabaseError("기록 실패", "확인")

    monkeypatch.setattr(live_guard, "record_aborted", boom)
    w.set(enable_live=False)
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 2
    monkeypatch.undo()
    w.conn.execute("UPDATE title_candidates SET status='blocked', validation_result='block' WHERE id=?", (w.cid,))
    w.conn.commit()
    monkeypatch.setattr(live_guard, "record_aborted", boom)
    with pytest.raises(SafetyGateError):
        go(w)


def test_second_apply_of_the_same_candidate_is_refused(w):
    """TC-609: 적용이 끝난 후보를 같은 승인 파일로 다시 적용할 수 없다(후보가 applied, 승인 used). 두 번째 호출은 쓰기 0회. [SEC-014, T-03]"""
    assert go(w).ok
    with pytest.raises(SafetyGateError):
        go(w)
    assert len(w.server.update_calls) == 1


def test_replayed_unused_approval_copy_cannot_reapply(w):
    """TC-610: 사용 전 승인 파일 사본을 되돌려 놓고 재생해도(인증값은 통과) 후보 상태·이력 때문에 다시 적용되지 않는다. [SEC-014, T-03]"""
    path = approvals.approval_path(w.settings, VID, w.cid)
    copy_before = path.read_text(encoding="utf-8")
    assert go(w).ok
    path.write_text(copy_before, encoding="utf-8")
    assert approvals.load_approval(w.settings, VID, w.cid).used is False
    with pytest.raises(SafetyGateError):
        go(w)
    assert len(w.server.update_calls) == 1


# ───────────── 모의 실행 미리보기 ─────────────

def test_preview_reports_gates_without_any_side_effect(w):
    """TC-611: 모의 실행(preview)은 구글에 연결하지 않고 DB·쿼터·승인 파일에 아무것도 쓰지 않으며, 막는 조건을 알려 준다. [FR-008, SEC-001]"""
    before = (w.changes(), w.quota(), w.approval_file())
    out = preview_apply(w.env(), w.plan())
    assert [o.step for o in out] == list(range(1, 15)) and out[0].status == "block"
    assert {o.step: o.status for o in out} == {1: "block", 2: "pass", 3: "pass", 4: "pass", 5: "pass", 6: "pending", 7: "pass", 8: "pass", 9: "pass", 10: "pending", 11: "pending", 12: "pending", 13: "pending", 14: "pending"}
    assert (w.changes(), w.quota(), w.approval_file()) == before and w.events == [] and w.write_token_loads == 0 and w.server.update_calls == []


def test_preview_shows_each_blocking_gate(w):
    """TC-612: 미리보기는 enable_live 꺼짐·허용 목록·쿼터·제한·승인 문제를 단계별 [차단]으로 보여 주고, 기준선 없음은 경고로 보여 준다. [SEC-001, SEC-012]"""
    w.set(enable_live=False, live_allowlist=())
    fill_quota(w.conn, w.clock, 6000 - 51)
    w.apply_change_row(change_type="apply", result="success", at=NOW - timedelta(hours=1))
    _no_approval_file(w)
    w.conn.execute("DELETE FROM metrics_snapshots")
    w.conn.commit()
    out = {o.step: o for o in preview_apply(w.env(), w.plan())}
    assert [out[n].status for n in (2, 3, 4, 5, 7)] == ["block"] * 5 and out[8].status == "warn" and out[9].status == "pass"
    assert "settings.local.yaml" in out[2].detail and "승인 파일이 없습니다" in out[7].detail


# ───────────── 롤백(live) ─────────────

@pytest.fixture
def applied(w):
    result = go(w)
    assert result.ok
    w.said.clear()
    w.events.clear()
    w.sleeps.clear()
    return result.change_id


def rb(w, chg, approver="홍길동", **kw):
    return rollback_live(w.env(), chg, approver=approver, **kw)


def test_rollback_restores_title_with_same_gates(w, applied):
    """TC-613: 롤백은 같은 엔진으로 이전 제목을 복원한다: 재조회→영상 ID 확인→쓰기 토큰→update 1회→검증, 이력 rollback success, 후보 rolled_back, 승인 파일 없이 확인자만. [FR-011, EVT-007, SEC-006, SEC-015]"""
    result = rb(w, applied)
    assert result.ok and result.kind == "rollback"
    assert [e[0] for e in w.events] == ["read_service", "list", "confirm", "write_token", "update", "read_service", "list"]
    sent = w.server.update_calls[-1]["body"]
    assert sent["id"] == VID and sent["snippet"]["title"] == SNIPPET["title"] and sent["snippet"]["description"] == SNIPPET["description"] and sent["snippet"]["tags"] == SNIPPET["tags"]
    rows = w.changes()
    assert [(r["change_type"], r["result"], r["approver"]) for r in rows] == [("apply", "success", "홍길동"), ("rollback", "success", "홍길동")]
    assert w.candidate_status() == "rolled_back" and w.server.items[VID]["snippet"]["title"] == SNIPPET["title"]
    assert "[완료] 롤백을 마쳤습니다" in w.output() and "해당 없음(롤백)" in w.output()


def test_rollback_is_exempt_from_cadence_limits(w, applied):
    """TC-614: 롤백은 72시간 간격·횟수·노출수·하루 상한을 적용하지 않는다(방금 적용했고 하루 상한에 도달해도 복구 가능). [WU-4 결정, FR-011]"""
    for i in range(3):
        add_change(w.conn, vid=f"other{i}000000", at=NOW - timedelta(minutes=5))
    assert rb(w, applied).ok


@pytest.mark.parametrize("breaker,step,text", [
    (lambda w: w.set(enable_live=False), 2, "enable_live"),
    (lambda w: w.set(live_allowlist=()), 3, "비어 있어"),
    (lambda w: fill_quota(w.conn, w.clock, 6000 - 100), 4, "쿼터"),
    (lambda w: _studio_title(w), 6, "구글의 제목이 다릅니다"),
    (lambda w: _studio_desc(w), 7, "계획 해시 불일치"),
    (lambda w: setattr(w, "video_answer", "wrong"), 10, "영상 ID 확인"),
    (lambda w: setattr(w, "write_auth_error", AuthError("로그인 없음", "로그인")), 11, "로그인"),
])
def test_rollback_gate_failures_write_nothing(w, applied, breaker, step, text):
    """TC-615: 롤백도 enable_live·허용 목록·쿼터·미확정 기록·재조회 제목/계획 해시·영상 ID 확인·쓰기 토큰 실패 시 update 0회, aborted(rollback, GATE-nn)만 남고 후보는 applied 그대로다. [SEC-001, SEC-009, SEC-012, FR-011]"""
    before_calls = len(w.server.update_calls)
    breaker(w)
    with pytest.raises(LiveGateError) as exc:
        rb(w, applied)
    assert exc.value.step == step and re.search(text, exc.value.message)
    assert len(w.server.update_calls) == before_calls
    last = w.changes()[-1]
    assert (last["change_type"], last["result"], last["error_code"]) == ("rollback", "aborted", f"GATE-{step:02d}")
    assert w.candidate_status() == "applied"


def test_rollback_blocked_by_unresolved_planned_row(w, applied):
    """TC-637: 해결되지 않은 planned 행이 있으면 롤백도 5단계에서 중단한다(자동으로 지우지 않음). [orchestrator 결정 3, SEC-006]"""
    w.conn.execute("INSERT INTO title_changes (id, video_id, change_type, previous_title, new_title, result, created_at) VALUES (-5, ?, 'apply', 'a', 'b', 'planned', ?)", (VID, ts(NOW - timedelta(days=9))))
    w.conn.commit()
    with pytest.raises(LiveGateError) as exc:
        rb(w, applied)
    assert exc.value.step == 5 and "planned" in exc.value.message
    assert w.conn.execute("SELECT result FROM title_changes WHERE id=-5").fetchone()[0] == "planned"


def test_rollback_requires_an_approver_name(w, applied):
    """TC-616: 확인자 이름 없이는 롤백하지 않는다(7단계). 이름에 제어 문자가 있어도 거부한다. [NFR-008, SEC-019]"""
    for bad in (None, "", "  ", "홍\x1b[31m길동"):
        with pytest.raises(LiveGateError) as exc:
            rb(w, applied, approver=bad)
        assert exc.value.step == 7
    assert len(w.server.update_calls) == 1


def test_rollback_requires_live_flag(w, applied):
    """TC-617: 엔진에 live_flag가 없으면 롤백도 1단계에서 중단한다. [SEC-001]"""
    with pytest.raises(LiveGateError) as exc:
        rb(w, applied, live_flag=False)
    assert exc.value.step == 1 and len(w.server.update_calls) == 1


def test_rollback_plan_refusals_are_audited(w, applied):
    """TC-618: 롤백 계획을 만들 수 없는 경우(이미 롤백됨·이후 변경 존재)는 거부하고 aborted(PLAN) 행을 남긴다. 없는 변경 번호는 기록 없이 오류. [FR-011, SEC-006]"""
    assert rb(w, applied).ok
    calls = len(w.server.update_calls)
    with pytest.raises(SafetyGateError):
        rb(w, applied)
    assert w.changes()[-1]["error_code"] == "PLAN" and w.changes()[-1]["result"] == "aborted" and w.changes()[-1]["change_type"] == "rollback"
    n = len(w.changes())
    with pytest.raises(InputError):
        rb(w, 9999)
    assert len(w.changes()) == n and len(w.server.update_calls) == calls


def test_rollback_audit_failure_does_not_mask_error(w, applied, monkeypatch):
    """TC-619: 롤백 계획 거부 기록이 실패해도 원래 오류가 그대로 올라온다. [NFR-008]"""
    assert rb(w, applied).ok
    monkeypatch.setattr(live_guard, "record_aborted", lambda *a, **k: (_ for _ in ()).throw(DatabaseError("실패", "확인")))
    with pytest.raises(SafetyGateError):
        rb(w, applied)


def test_rollback_verification_failure_is_recorded_without_auto_retry(w, applied):
    """TC-620: 롤백 후 검증이 실패(제목 미반영)해도 success + ok=false로 기록하고 추가 호출은 하지 않는다. [SEC-010, FR-011]"""
    w.server.ignore_update = True
    result = rb(w, applied)
    assert result.ok is False and len(w.server.update_calls) == 2
    last = w.changes()[-1]
    assert (last["change_type"], last["result"]) == ("rollback", "success") and json.loads(last["verify_result_json"])["ok"] is False
    assert "롤백 호출은 끝났지만 검증이 통과하지 못했습니다" in w.output()


def test_rollback_call_failure_marks_failed_and_keeps_candidate(w, applied):
    """TC-621: 롤백 호출이 400으로 거절되면 rollback 행을 failed로 끝내고 후보는 applied로 둔다(원래 적용 행도 그대로). [FR-011, SEC-006]"""
    w.server.update_behaviors = [http_error(400, "invalidValue")]
    with pytest.raises(WriteApiError):
        rb(w, applied)
    rows = w.changes()
    assert [(r["change_type"], r["result"]) for r in rows] == [("apply", "success"), ("rollback", "failed")] and w.candidate_status() == "applied"


# ───────────── 코드 구조 증명 ─────────────

def _py_files():
    return sorted(p for p in SRC.rglob("*.py"))


def _is_videos_update(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "update" and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "videos"


def test_videos_update_exists_in_exactly_one_place():
    """TC-622: 소스 전체에서 `.videos().update(` 호출은 live_guard.py의 `_send_update` 단 한 곳이다(다른 모듈·다른 표기 없음). [SEC-001, SEC-007]"""
    hits = []
    for p in _py_files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for node in ast.walk(fn):
                if _is_videos_update(node):
                    hits.append((p.name, fn.name))
    assert hits == [("live_guard.py", "_send_update")]


def test_no_other_spelling_of_the_write_call_exists():
    """TC-623: 다른 표기로 쓰기 호출을 숨기지 못한다: `.update(part=`, `videos().update`(줄바꿈 포함), getattr로 'update'를 꺼내는 코드는 live_guard 밖에 없다. [SEC-001, SEC-007]"""
    for p in _py_files():
        text = p.read_text(encoding="utf-8")
        tree = ast.parse(text)
        if p.name != "live_guard.py":
            assert not re.search(r"videos\(\)\s*\.\s*update", text), p.name
            assert not re.search(r"\.update\(\s*part\s*=", text), p.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "eval", "exec", "__import__"):
                if node.func.id != "getattr":
                    raise AssertionError(f"{p.name}: {node.func.id} 사용")
                assert not (len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) and node.args[1].value in ("update", "videos")), p.name
    live_text = (SRC / "live_guard.py").read_text(encoding="utf-8")
    assert len(re.findall(r"\.update\(part=", live_text)) == 1 and len(re.findall(r"_send_update\(", live_text)) == 2   # 정의 1 + 호출 1


def test_write_credentials_are_loaded_in_one_place_only():
    """TC-624: 쓰기 토큰(`load_credentials("write"`)은 live_guard.make_write_service 한 곳에서만 읽고, 다른 곳의 load_credentials는 모두 읽기 토큰이다. [SEC-015]"""
    write_sites = []
    for p in _py_files():
        for fn in [n for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef)]:
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", None)) == "load_credentials":
                    first = node.args[0] if node.args else None
                    kind = first.value if isinstance(first, ast.Constant) else "?"
                    if kind != "read":
                        write_sites.append((p.name, fn.name, kind))
    assert write_sites == [("live_guard.py", "make_write_service", "write")]


def test_no_web_scraping_or_browser_automation_imports():
    """TC-625: 소스에 Studio·웹 접근용 HTTP 라이브러리(requests/urllib/httpx)나 브라우저 자동화(selenium/playwright/pyppeteer)를 import하지 않는다. [SEC-007]"""
    banned = {"requests", "urllib", "urllib3", "httpx", "aiohttp", "selenium", "playwright", "pyppeteer", "mechanize", "socket"}
    for p in _py_files():
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            names = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else ([node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            assert not banned & set(names), (p.name, names)


def test_make_write_service_loads_only_the_write_token(project, tmp_path, monkeypatch):
    """TC-626: make_write_service는 쓰기 토큰 종류("write")만 읽어 그 자격증명으로 서비스를 만든다. make_reader는 읽기 토큰만 쓴다. [SEC-015]"""
    kinds, built = [], []
    sentinel = object()
    monkeypatch.setattr(authmod, "load_credentials", lambda kind, settings, **k: kinds.append(kind) or sentinel)
    import googleapiclient.discovery as disc
    monkeypatch.setattr(disc, "build", lambda *a, **k: built.append((a, k)) or "서비스")
    w = World(project, tmp_path)
    assert live_guard.make_write_service(w.settings) == "서비스" and kinds == ["write"] and built[0][1]["credentials"] is sentinel and built[0][0] == ("youtube", "v3")
    ctx = type("C", (), {"settings": w.settings, "conn": w.conn, "clock": w.clock, "run_id": "r"})()
    reader = live_guard.make_reader(ctx)
    assert kinds == ["write", "read"] and reader is not None
    w.close()


def test_env_from_ctx_wires_lazy_factories(project, tmp_path, monkeypatch):
    """TC-627: env_from_ctx는 서비스를 미리 만들지 않는다(토큰도 읽지 않음). 팩토리를 부를 때에만 읽고, 쓰기 팩토리는 write 토큰을 요청한다. [SEC-015]"""
    kinds = []
    monkeypatch.setattr(authmod, "load_credentials", lambda kind, settings, **k: kinds.append(kind) or (_ for _ in ()).throw(AuthError("없음", "로그인")))
    w = World(project, tmp_path)
    ctx = type("C", (), {"settings": w.settings, "conn": w.conn, "clock": w.clock, "run_id": "r", "say": lambda self, t="": None, "confirm": lambda self, e: True, "ui": None, "logger": logging.getLogger("x")})()
    env = live_guard.env_from_ctx(ctx)
    assert kinds == []
    with pytest.raises(AuthError):
        env.make_write_service()
    with pytest.raises(AuthError):
        env.make_reader()
    assert kinds == ["write", "read"]
    w.close()


def test_no_network_during_gate_tests(w):
    """TC-628: 이 테스트 파일은 소켓·google build()를 막은 채 실행된다: 전체 적용·롤백 시나리오가 가짜 서비스만으로 끝나고 연결 시도가 0건이다. [K-2, SEC-001]"""
    import socket
    assert go(w).ok
    with pytest.raises(AssertionError, match="네트워크"):
        socket.socket().connect(("example.invalid", 80))


# ───────────── 단위: 본문 구성·오류 분류 ─────────────

def test_build_write_body_deep_copies_and_replaces_only_title():
    """TC-629: build_write_body는 snippet을 깊은 복사하고 제목만 바꾼다(원본 불변). [SEC-005, FR-009]"""
    snippet = copy.deepcopy(SNIPPET)
    body = live_guard.build_write_body(VID, snippet, "새")
    assert snippet == SNIPPET and body["snippet"]["title"] == "새" and body["snippet"]["tags"] == SNIPPET["tags"] and body["snippet"]["tags"] is not snippet["tags"]


def test_not_sent_fields_hook_changes_body_and_check_together(w, monkeypatch):
    """TC-630: 12단계 실측 후 읽기 전용 항목을 빼야 하면 NOT_SENT_SNIPPET_FIELDS에 이름만 추가하면 본문과 본문 검사가 함께 바뀐다. [SEC-005, 확인 필요]"""
    assert live_guard.NOT_SENT_SNIPPET_FIELDS == ()
    monkeypatch.setattr(live_guard, "NOT_SENT_SNIPPET_FIELDS", ("publishedAt", "channelId"))
    assert go(w).ok
    sent = w.server.update_calls[0]["body"]["snippet"]
    assert "publishedAt" not in sent and "channelId" not in sent and sent["description"] == SNIPPET["description"]


@pytest.mark.parametrize("mutate,text", [
    (lambda b: b.pop("id"), "구조"),
    (lambda b: b.update(id="zzzzzzzzzzz"), "구조"),
    (lambda b: b.update(extra=1), "구조"),
    (lambda b: b.update(snippet="문자열"), "구조"),
    (lambda b: b["snippet"].update(title="다른"), "제목이 새 제목과 다릅니다"),
    (lambda b: b["snippet"].pop("tags"), "빠진 항목: tags"),
    (lambda b: b["snippet"].update(description="바뀐 설명"), "전부 보존하지 않아"),
    (lambda b: b["snippet"].update(unknown="추가"), "전부 보존하지 않아"),
])
def test_check_body_rejects_unsafe_bodies(mutate, text):
    """TC-631: check_body는 구조 이상·제목 불일치·항목 누락·값 변경·추가 항목이 있는 본문을 거부한다. [SEC-005, T-15]"""
    body = live_guard.build_write_body(VID, SNIPPET, "새")
    mutate(body)
    with pytest.raises(LiveGateError) as exc:
        live_guard.check_body(body, VID, SNIPPET, "새")
    assert exc.value.step == 9 and text in exc.value.message
    live_guard.check_body(live_guard.build_write_body(VID, SNIPPET, "새"), VID, SNIPPET, "새")


def test_check_body_requires_category(monkeypatch):
    """TC-632: categoryId가 없는 본문은 보내지 않는다(전체 보존 대상에서 빠지도록 설정돼도). [SEC-005, T-15]"""
    monkeypatch.setattr(live_guard, "NOT_SENT_SNIPPET_FIELDS", ("categoryId",))
    body = live_guard.build_write_body(VID, SNIPPET, "새")
    with pytest.raises(LiveGateError, match="categoryId"):
        live_guard.check_body(body, VID, SNIPPET, "새")


def test_invalid_new_title_is_rejected_at_step_9(w, monkeypatch):
    """TC-633: 쓰기 직전 새 제목 규격 재검사(길이·< >·제어 문자)에 걸리면 9단계에서 중단한다. [SEC-005, FR-002]"""
    def boom(*a, **k):
        raise InputError("제목에는 < 또는 > 를 쓸 수 없습니다.", "고치세요")

    monkeypatch.setattr(live_guard, "validate_new_title", boom)
    with pytest.raises(LiveGateError) as exc:
        go(w)
    assert exc.value.step == 9
    assert_blocked_before_write(w, 9)


def _http(status, reason=""):
    return classify_write_error(http_error(status, reason))


@pytest.mark.parametrize("exc,kind,retryable,definite", [
    (http_error(403, "quotaExceeded"), QuotaError, None, True),
    (http_error(403, "dailyLimitExceeded"), QuotaError, None, True),
    (http_error(401), AuthError, None, True),
    (http_error(403, "forbidden"), AuthError, None, True),
    (http_error(429), WriteApiError, True, True),
    (http_error(500), WriteApiError, True, False),
    (http_error(503, "backendError"), WriteApiError, True, False),
    (http_error(400, "invalidValue"), WriteApiError, False, True),
    (http_error(404), WriteApiError, False, True),
    (TimeoutError("t"), WriteApiError, True, False),
    (ConnectionResetError("c"), WriteApiError, True, False),
    (RuntimeError("x"), WriteApiError, False, False),
])
def test_classify_write_error(exc, kind, retryable, definite):
    """TC-634: 쓰기 오류 분류: 쿼터/인증은 분명한 거절, 429는 재시도하는 분명한 거절, 5xx·네트워크는 재시도하는 불명, 그 밖의 4xx는 분명한 거절, 모르는 예외는 불명이다. [SEC-003, NFR-004]"""
    err = classify_write_error(exc)
    assert type(err) is kind
    if kind is WriteApiError:
        assert err.retryable is retryable and err.definite is definite
    assert "Bearer" not in err.message + err.next_step


def test_classify_does_not_leak_response_body():
    """TC-635: HTTP 오류 본문에 토큰·긴 문자열이 있어도 메시지·원인에 넣지 않고 상태 코드와 안전한 reason만 남긴다. [SEC-008]"""
    import httplib2
    from googleapiclient.errors import HttpError
    body = json.dumps({"error": {"errors": [{"reason": "bad reason with spaces " + FAKE_ACCESS}], "message": FAKE_ACCESS}}).encode()
    err = classify_write_error(HttpError(httplib2.Response({"status": 400}), body))
    assert FAKE_ACCESS not in err.message + err.next_step + err.cause and err.cause == "HTTP 400"
    odd = classify_write_error(HttpError(httplib2.Response({"status": 400}), b"not json"))
    assert odd.cause == "HTTP 400"
    nonstr = classify_write_error(HttpError(httplib2.Response({"status": 400}), json.dumps({"error": {"errors": [{"reason": 5}]}}).encode()))
    assert nonstr.cause == "HTTP 400"


def test_gate_line_formats_all_statuses():
    """TC-636: 게이트 표시는 상태를 기호+글자로 보여 주고(색 비의존) 외부 문자열의 제어 문자를 제거한다. [SEC-019, UX 3장]"""
    from ytitle.live_guard import GateOutcome, gate_line
    from ytitle.ui import UiOptions
    for status, mark in (("pass", "[통과]"), ("block", "[차단]"), ("warn", "[주의]"), ("pending", "[ 대기 ]"), ("skip", "[해당 없음]")):
        assert mark in gate_line(GateOutcome(7, status, "내용"), UiOptions())
    assert "\x1b" not in gate_line(GateOutcome(7, "pass", "\x1b[31m빨강"), UiOptions())


def test_step7_without_fresh_hash_fails_closed(w):
    """TC-638: 6단계 결과(재조회 snippet·계획 해시)가 없는 채로 7단계가 불리면(게이트 순서가 깨진 경우) 승인을 믿지 않고 중단한다. [SEC-014, 방어적 설계]"""
    run = live_guard._run_from_plan(w.plan(), True)
    with pytest.raises(LiveGateError) as exc:
        live_guard._g7(w.env(), run)
    assert exc.value.step == 7


def test_verification_when_video_disappears_after_write(w):
    """TC-639: 쓰기 직후 재조회에서 영상이 보이지 않으면(삭제·비공개) 검증을 하지 못했다고 기록하고 success(ok=false)로 끝낸다. [SEC-010]"""
    w.server.update_behaviors = [lambda server, body: server.items.clear()]
    result = go(w)
    v = json.loads(w.changes()[0]["verify_result_json"])
    assert result.ok is False and v["checked"] is False and w.changes()[0]["result"] == "success"
