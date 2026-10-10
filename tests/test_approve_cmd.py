import json
import sqlite3

import pytest
from wu4_support import SNIPPET, add_change, add_video
from wu5_support import NEW_TITLE, NOW, VID, World, block_network, cli_run, patch_services, timedelta, ts

from ytitle import approvals
from ytitle.commands import approve as approve_cmd
from ytitle.errors import SafetyGateError


@pytest.fixture
def w(project, tmp_path, monkeypatch):
    block_network(monkeypatch)
    world = World(project, tmp_path, approve=False)
    patch_services(monkeypatch, world)
    yield world
    world.close()


def status(w):
    c = sqlite3.connect(w.settings.db_path)
    s = c.execute("SELECT status FROM title_candidates WHERE id=?", (w.cid,)).fetchone()[0]
    c.close()
    return s


def apath(w):
    return approvals.approval_path(w.settings, VID, w.cid)


def appr(w, streams, *extra, name="홍길동", **kw):
    return cli_run(w, streams, ["approve", "--candidate", str(w.cid), "--approver", name, *extra], **kw)


def test_approve_creates_bound_file_after_typing_video_id(w, streams):
    """TC-670: approve는 계획 요약을 보여 주고 영상 ID를 직접 입력해야 승인 파일(계획 해시·만료·미사용)을 만들며 후보를 approved로 바꾼다. 구글 연결 없음. [EVT-005, FR-013, SCR-004, SEC-014]"""
    assert appr(w, streams) == 0
    out = streams.out.getvalue()
    plan = w.plan()
    assert "[approve] 모드: 모의 실행(dry-run)" in out and f"새 제목:   {NEW_TITLE}" in out and f"계획 해시: {plan.plan_hash}" in out and "교체 제한 검사" in out
    assert "[완료] 승인했습니다. 승인자: 홍길동" in out and "만료: " in out and "(한국 시간)" in out and str(apath(w)) in out and "apply --candidate" in out
    assert len(w.prompts) == 1 and f"'{VID}'" in w.prompts[0]
    d = json.loads(apath(w).read_text(encoding="utf-8"))
    assert d["plan_hash"] == plan.plan_hash and d["new_title"] == NEW_TITLE and d["approver"] == "홍길동" and d["used"] is False and d["candidate_id"] == w.cid
    assert status(w) == "approved" and w.events == [] and w.write_token_loads == 0 and w.server.update_calls == []
    assert approvals.load_approval(w.settings, VID, w.cid).expires_at == NOW + timedelta(hours=24)


@pytest.mark.parametrize("mode", ["wrong", "blank", "eof"])
def test_wrong_confirmation_creates_nothing(w, streams, mode):
    """TC-671: 영상 ID 확인이 틀리거나 비었거나 입력이 끊기면 종료 코드 3, 승인 파일 없음, 후보 상태 그대로. [UX 3장, SEC-014]"""
    w.video_answer = mode
    assert appr(w, streams) == 3
    assert not apath(w).exists() and status(w) == "filtered" and "승인 파일을 만들지 않았습니다" in streams.err.getvalue()


def test_not_ready_plan_is_not_approved(w, streams):
    """TC-672: 교체 제한을 지금 통과하지 못하는 계획은 승인하지 않는다(질문 없이 종료 코드 3). [FR-014, SEC-004]"""
    add_change(w.conn, at=NOW - timedelta(hours=1))
    assert appr(w, streams) == 3
    assert "승인하지 않았습니다" in streams.out.getvalue() and w.prompts == [] and not apath(w).exists() and status(w) == "filtered"


def test_unapprovable_candidates(w, streams):
    """TC-673: 없는 후보는 1, 차단된 후보·이미 적용된 후보는 3으로 거부한다. [POL-001, 설계 3-2]"""
    assert cli_run(w, streams, ["approve", "--candidate", "99", "--approver", "a"]) == 1
    for st, res in (("blocked", "block"), ("applied", "pass")):
        w.conn.execute("UPDATE title_candidates SET status=?, validation_result=?", (st, res))
        w.conn.commit()
        assert appr(w, streams) == 3 and not apath(w).exists()


def test_existing_active_approval_needs_overwrite_confirmation(w, streams):
    """TC-674: 이미 유효한 승인이 있으면 '덮어쓰기'를 직접 입력해야 새로 승인한다. 거절하면 기존 승인이 그대로 남는다. [SCR-004]"""
    assert appr(w, streams) == 0
    first = apath(w).read_text(encoding="utf-8")
    answers = iter(["아니오", ""])
    assert appr(w, streams, name="김철수", input_fn=lambda p: next(answers)) == 3
    assert apath(w).read_text(encoding="utf-8") == first and "이미 유효한 승인 파일" in streams.out.getvalue()
    w.clock.advance(timedelta(minutes=1))
    seq = iter(["덮어쓰기", VID])
    assert appr(w, streams, name="김철수", input_fn=lambda p: next(seq)) == 0
    assert approvals.load_approval(w.settings, VID, w.cid).approver == "김철수" and status(w) == "approved"


def test_reapprove_when_already_approved_keeps_status_and_replaces_expired(w, streams):
    """TC-675: 후보가 이미 approved이고 이전 승인이 만료됐으면 질문 없이 새로 승인하고 상태는 approved 그대로다. [FR-013]"""
    assert appr(w, streams) == 0
    w.clock.advance(timedelta(hours=25))
    add_video(w.conn, fetched_at=ts(w.clock.now() - timedelta(hours=1)))
    assert appr(w, streams) == 0
    assert len(w.prompts) == 2 and status(w) == "approved" and approvals.load_approval(w.settings, VID, w.cid).approved_at == w.clock.now().replace(microsecond=0)


@pytest.mark.parametrize("extra,code", [(["--ttl-hours", "1"], 0), (["--ttl-hours", "24"], 0), (["--ttl-hours", "0"], 1), (["--ttl-hours", "25"], 1), (["--ttl-hours", "x"], 2)])
def test_ttl_option(w, streams, extra, code):
    """TC-676: --ttl-hours는 1 이상 설정값(24) 이하만 가능하다(범위 밖 1, 숫자 아님 2). 잘못된 값이면 승인 파일을 만들지 않는다. [FR-013, 설정 approval.ttl_hours]"""
    assert appr(w, streams, *extra) == code
    if code:
        assert not apath(w).exists()
    elif extra[1] == "1":
        assert approvals.load_approval(w.settings, VID, w.cid).expires_at == NOW + timedelta(hours=1)


@pytest.mark.parametrize("name,code", [("", 1), ("   ", 1), ("홍\x1b[31m길동", 1), ("a" * 41, 1), ("홍길동", 0)])
def test_approver_validation(w, streams, name, code):
    """TC-677: 승인자 이름은 필수이며 비거나 제어 문자·41자 이상이면 거부한다(옵션 누락은 2). [NFR-008, SEC-019]"""
    assert appr(w, streams, name=name) == code
    assert apath(w).exists() == (code == 0) and (w.prompts == []) == (code != 0)   # 이름이 틀리면 입력을 받기 전에 거부
    if code == 0:
        return
    assert cli_run(w, streams, ["approve", "--candidate", str(w.cid)]) == 2


@pytest.mark.parametrize("bad", ["0", "-1", str(2**63)])
def test_candidate_range(w, streams, bad):
    """TC-678: 후보번호 범위 밖은 종료 코드 1이다. [EVT-005]"""
    assert cli_run(w, streams, ["approve", "--candidate", bad, "--approver", "a"]) == 1


def test_state_transition_failure_removes_the_file(w, streams, monkeypatch):
    """TC-679: 후보 상태 전이에 실패하면 방금 만든 승인 파일을 지워 'approved 상태 없는 승인 파일'을 남기지 않는다. [SEC-014, 설계 3-2]"""
    def boom(*a, **k):
        raise SafetyGateError("전이 불가", "확인")

    monkeypatch.setattr(approve_cmd, "transition_candidate", boom)
    assert appr(w, streams) == 3
    assert not apath(w).exists() and status(w) == "filtered"


def test_warn_and_stale_cautions_and_sanitizing(w, streams):
    """TC-680: 경고 판정 후보·오래된 영상 정보는 [주의]로 알리고, 제목의 제어 문자는 화면에 나오지 않는다. [POL-001, SEC-019, EVT-004]"""
    add_video(w.conn, snippet={**SNIPPET, "title": "\x1b[31m빨간‮제목"}, fetched_at=ts(NOW - timedelta(hours=30)))
    w.conn.execute("UPDATE title_candidates SET validation_result='warn', validation_reasons_json=?", (json.dumps([["X", "warn", "느낌표 과다\x1b[0m"], ["Y", "warn", "다른 사유"]], ensure_ascii=False),))
    w.conn.commit()
    assert appr(w, streams) == 0
    out = streams.out.getvalue()
    assert "경고를 받은 제목" in out and "느낌표 과다" in out and "24시간이 넘었" in out and "\x1b" not in out and "‮" not in out


def test_full_flow_approve_then_apply_live(w, streams):
    """TC-681: 전체 흐름: approve로 승인 → apply 모의 실행(7단계 통과) → apply --live로 적용 → 승인은 소진되어 다시 apply하면 3. [FR-012, FR-013, SEC-014]"""
    assert appr(w, streams) == 0
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid)]) == 0
    assert "[통과]  7/14" in streams.out.getvalue()
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 0
    assert status(w) == "applied" and len(w.server.update_calls) == 1
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 3
    assert len(w.server.update_calls) == 1


def test_approve_help(w, streams):
    """TC-682: approve --help가 승인자·유효 시간 옵션과 1회용·만료 성격을 설명한다. [SCR-001]"""
    assert cli_run(w, streams, ["approve", "--help"]) == 0
    out = streams.out.getvalue()
    assert "--approver" in out and "--ttl-hours" in out and "한 번만" in out
