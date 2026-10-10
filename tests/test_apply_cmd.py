import sqlite3

import pytest
from wu4_support import add_change
from wu5_support import NEW_TITLE, NOW, SNIPPET, VID, World, block_network, cli_run, fill_quota, http_error, patch_services, timedelta, ts

from ytitle import approvals


@pytest.fixture
def w(project, tmp_path, monkeypatch):
    block_network(monkeypatch)
    world = World(project, tmp_path)
    patch_services(monkeypatch, world)
    yield world
    world.close()


def counts(w):
    c = sqlite3.connect(w.settings.db_path)
    out = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("title_changes", "quota_usage", "title_candidates")}
    out["statuses"] = [r[0] for r in c.execute("SELECT status FROM title_candidates ORDER BY id")]
    c.close()
    return out


def run_logs(w):
    c = sqlite3.connect(w.settings.db_path)
    rows = c.execute("SELECT command, mode, exit_code FROM run_logs ORDER BY id").fetchall()
    c.close()
    return rows


def test_dry_run_is_default_and_writes_nothing(w, streams):
    """TC-950: --live 없는 apply는 모의 실행이다: 계획 정보와 14단계 조건 표를 보여 주고, 구글 연결·쓰기 토큰 로드·이력/쿼터 기록·승인 소진이 전혀 없으며 종료 코드 0이다. [EVT-006, SEC-001, FR-008]"""
    before = counts(w)
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid)]) == 0
    out = streams.out.getvalue()
    assert "[apply] 모드: 모의 실행(dry-run)" in out and "현재 제목: 겨울 전기요금" in out and f"새 제목:   {NEW_TITLE}" in out
    assert "그대로 유지되는 항목" in out and "description" in out and "계획 해시:" in out and "교체 제한 검사" in out
    assert "실제 적용 조건(안전 게이트 14단계)" in out and out.count("/14 ") == 14
    for n in (2, 3, 4, 5, 7, 8, 9):
        assert f" {n}/14" in out
    assert "[ 대기 ]" in out and "구글에 연결하지 않았고 아무것도 바꾸지 않았습니다" in out and "apply --candidate" in out and "--live` 를 실행" in out
    assert out.rstrip().endswith("법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.")
    assert counts(w) == before and w.events == [] and w.write_token_loads == 0 and w.server.update_calls == [] and w.approval_file()["used"] is False
    assert run_logs(w) == [("apply", "dry_run", 0)]


def test_dry_run_shows_which_gate_blocks(w, streams):
    """TC-951: 모의 실행은 막는 조건을 단계 번호와 해결 방법으로 보여 주고 종료 코드 3을 낸다(--live 없음 자체는 막힘으로 세지 않음). [EVT-006, SCR-005, SEC-001]"""
    w.set(enable_live=False)
    (w.project / "config" / "settings.local.yaml").write_text("live:\n  enable_live: false\n  live_allowlist: []\n", encoding="utf-8")
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid)]) == 3
    out = streams.out.getvalue()
    assert "[차단]  2/14" in out and "[차단]  3/14" in out and "settings.local.yaml" in out and "막힌 조건 2개: 2단계, 3단계" in out
    assert "다음에 할 일" not in out and w.server.update_calls == [] and counts(w)["title_changes"] == 0


def test_dry_run_missing_approval_and_baseline(w, streams):
    """TC-952: 승인 파일이 없으면 7단계 [차단], 변경 전 지표가 없으면 8단계 [주의]로 안내한다. [FR-012, FR-013]"""
    approvals.approval_path(w.settings, VID, w.cid).unlink()
    w.conn.execute("DELETE FROM metrics_snapshots")
    w.conn.commit()
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid)]) == 3
    out = streams.out.getvalue()
    assert "[차단]  7/14" in out and "승인 파일이 없습니다" in out and "[주의]  8/14" in out and "막힌 조건 1개: 7단계" in out


@pytest.mark.parametrize("argv,code", [([], 2), (["--candidate", "abc"], 2), (["--candidate", "0"], 1), (["--candidate", "-3"], 1), (["--candidate", str(2**63)], 1), (["--candidate", "1", "2"], 2), (["--all"], 2), (["--candidate", "99"], 1)])
def test_candidate_option_rules(w, streams, argv, code):
    """TC-953: --candidate는 필수 정수 1개다(없으면 2, 숫자 아님 2, 0·음수·범위 밖·없는 번호 1). 일괄 적용 옵션(--all, 여러 번호)은 없다. [SEC-020, T-16, EVT-006]"""
    assert cli_run(w, streams, ["apply"] + argv) == code
    assert w.server.update_calls == [] and counts(w)["title_changes"] == 0
    if code == 1:   # 범위 밖 번호는 DB를 조회하기 전에 '후보번호가 올바르지 않습니다'로 거부하고, 범위 안의 없는 번호와 문구가 달라야 한다
        assert ("후보번호가 올바르지 않습니다" in streams.err.getvalue()) == (argv[-1] in ("0", "-3", str(2**63)))


def test_live_apply_end_to_end_via_cli(w, streams):
    """TC-954: apply --candidate N --live: 14단계 통과 후 영상 ID를 직접 입력하면 제목이 바뀌고 SCR-005/006 화면(조건 표·LIVE 경고·결과·롤백 명령)이 나오며 run_logs는 live/0이다. [EVT-006, SCR-005, SCR-006, FR-012]"""
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 0
    out = streams.out.getvalue()
    assert "[apply] 모드: ★실제 적용(LIVE)★" in out and "★ 실제 적용(LIVE) 직전 요약 ★" in out and "조건 확인 결과" in out
    assert len(w.prompts) == 1 and f"'{VID}'를 그대로 입력하세요" in w.prompts[0] and "[완료] 제목 변경을 마쳤습니다" in out and "되돌리려면:" in out
    assert out.rstrip().endswith("법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.")
    assert len(w.server.update_calls) == 1 and w.server.items[VID]["snippet"]["title"] == NEW_TITLE
    assert counts(w)["statuses"] == ["applied"] and run_logs(w) == [("apply", "live", 0)]


def test_live_gate_failure_exit_code_and_message(w, streams):
    """TC-955: 게이트에서 막히면 종료 코드 3, 한국어 오류 블록(다음에 할 일 포함), 호출 0회, aborted 행 1개. [NFR-007, SCR-009, SEC-001]"""
    w.server.items[VID]["snippet"]["title"] = "Studio에서 바꾼 제목"
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 3
    err = streams.err.getvalue()
    assert "[오류 YT-600]" in err and "Studio에서 바뀐 제목을 덮어쓰지 않으려고" in err and "다음에 할 일:" in err
    assert w.server.update_calls == [] and counts(w)["title_changes"] == 1 and "6단계에서 막혀" in streams.out.getvalue()
    assert run_logs(w) == [("apply", "live", 3)]


def test_live_typed_id_mismatch_exits_3(w, streams):
    """TC-956: 영상 ID를 3번 틀리게 입력하면 종료 코드 3, 호출 0회. (확인 문구는 y/n이 아니라 영상 ID) [UX 3장, SEC-001]"""
    w.video_answer = "wrong"
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 3
    out = streams.out.getvalue()
    assert out.count("입력이 일치하지 않습니다") == 3 and "여러 번 일치하지 않아 중단했습니다" in out and w.server.update_calls == [] and len(w.prompts) == 3


def test_live_verification_failure_exit_code_1(w, streams):
    """TC-957: 사후 검증이 실패하면 종료 코드 1과 큰 경보, 롤백 안내를 출력한다(자동 롤백 없음). [SEC-010, SCR-006]"""
    w.server.drop_on_update = ("tags",)
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 1
    out = streams.out.getvalue()
    assert "★ 사후 검증 실패" in out and "tags" in out and "rollback --change" in out and len(w.server.update_calls) == 1


def test_live_api_rejection_exit_code_1(w, streams):
    """TC-958: 구글이 요청을 거절하면 종료 코드 1, 한국어 안내, 이력 failed. [NFR-007, SEC-006]"""
    w.server.update_behaviors = [http_error(400, "invalidValue")]
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 1
    assert "[오류 YT-700]" in streams.err.getvalue() and "제목은 바뀌지 않았습니다" in streams.err.getvalue()
    c = sqlite3.connect(w.settings.db_path)
    assert c.execute("SELECT result FROM title_changes").fetchall() == [("failed",)]
    c.close()


def test_live_unresolved_result_exit_code_1_and_planned(w, streams):
    """TC-959: 호출 결과를 알 수 없으면 종료 코드 1, 이력 planned, 안내(Studio 확인)를 출력한다. [NFR-008]"""
    w.server.update_behaviors = [TimeoutError("t")] * 3
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 1
    assert "결과를 확인하지 못했습니다" in streams.err.getvalue() and counts(w)["title_changes"] == 1
    c = sqlite3.connect(w.settings.db_path)
    assert c.execute("SELECT result FROM title_changes").fetchall() == [("planned",)]
    c.close()


def test_settings_yaml_enable_live_is_ignored_via_cli(project, tmp_path, monkeypatch, streams):
    """TC-960: 명령 수준에서도 settings.yaml의 enable_live는 무시된다: [주의] 안내와 함께 2단계에서 종료 코드 3, 호출 0회. [SEC-001, ADR-010]"""
    block_network(monkeypatch)
    w = World(project, tmp_path)
    patch_services(monkeypatch, w)
    (project / "config" / "settings.local.yaml").unlink()
    (project / "config" / "settings.yaml").write_text(f'live:\n  enable_live: true\n  live_allowlist: ["{VID}"]\n', encoding="utf-8")
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 3
    assert "settings.yaml의 live 항목은 무시했습니다" in streams.err.getvalue() and "2단계에서 막혀" in streams.out.getvalue() and w.server.update_calls == []
    w.close()


def test_blocked_candidate_exit_3_dry_and_live(w, streams):
    """TC-961: 차단된 후보는 모의 실행·실제 적용 모두 종료 코드 3으로 거부한다(live는 aborted PLAN 기록). [POL-001, SEC-001]"""
    w.conn.execute("UPDATE title_candidates SET status='blocked', validation_result='block'")
    w.conn.commit()
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid)]) == 3
    assert counts(w)["title_changes"] == 0
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 3
    assert counts(w)["title_changes"] == 1 and w.server.update_calls == []


def test_apply_help_explains_dry_run_default(w, streams):
    """TC-962: apply --help가 기본이 모의 실행이고 --live가 실제 적용임을 밝힌다. [SCR-001, NFR-007]"""
    assert cli_run(w, streams, ["apply", "--help"]) == 0
    out = streams.out.getvalue()
    assert "모의 실행" in out and "--live" in out and "14단계" in out


def test_external_strings_are_sanitized_on_screen(w, streams):
    """TC-963: 영상 제목·검증 사유에 ANSI/방향 제어 문자가 있어도 apply 화면에 그대로 나오지 않는다. [SEC-019, T-13]"""
    from wu4_support import add_video
    add_video(w.conn, snippet={**SNIPPET, "title": "\x1b[2J\x1b[31m가짜‮제목"}, fetched_at=ts(NOW - timedelta(hours=1)))
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid)]) in (0, 3)
    out = streams.out.getvalue()
    assert "\x1b" not in out and "‮" not in out and "가짜" in out


def test_dry_run_stale_info_is_cautioned(w, streams):
    """TC-964: 영상 정보를 가져온 지 24시간이 넘으면 모의 실행이 [주의]로 fetch를 안내한다. [EVT-004]"""
    from wu4_support import add_video
    add_video(w.conn, fetched_at=ts(NOW - timedelta(hours=30)))
    cli_run(w, streams, ["apply", "--candidate", str(w.cid)])
    assert "24시간이 넘었" in streams.out.getvalue() and "fetch --video" in streams.out.getvalue()


def test_daily_cap_via_cli(w, streams):
    """TC-965: 하루 적용 상한에 닿으면 모의 실행은 5단계 [차단], 실제 적용은 종료 코드 3이다. [SEC-020]"""
    for i in range(3):
        add_change(w.conn, vid=f"other{i}000000", at=NOW - timedelta(hours=1))
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid)]) == 3
    assert "하루 상한" in streams.out.getvalue()
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 3
    assert w.server.update_calls == []


def test_quota_exhausted_via_cli(w, streams):
    """TC-966: 오늘 쿼터가 부족하면 실제 적용은 4단계에서 종료 코드 3으로 막히고 구글 호출이 없다. [SEC-002]"""
    fill_quota(w.conn, w.clock, 6000 - 10)
    assert cli_run(w, streams, ["apply", "--candidate", str(w.cid), "--live"]) == 3
    assert "4단계에서 막혀" in streams.out.getvalue() and w.events == []
