import shutil
import socket
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from wu4_support import NOW, SNIPPET, VID, add_candidate, add_change, add_video, clock, open_db, ts

from ytitle import cli
from ytitle.banned_terms import load_dictionary
from ytitle.updater import compute_plan_hash

REAL_DICT = Path(__file__).resolve().parent.parent / "config" / "banned_terms.yaml"
DICT_HASH = load_dictionary(REAL_DICT).short_hash


@pytest.fixture
def proj(project):
    shutil.copy(REAL_DICT, project / "config" / "banned_terms.yaml")
    return project


@pytest.fixture
def db(proj):
    c = open_db(proj / "data" / "ytitle.sqlite3")
    yield c
    c.close()


def go(proj, streams, argv):
    return cli.main(["--base-dir", str(proj)] + argv, out=streams.out, err=streams.err, env={}, clock=clock())


def table_count(proj, table):
    c = sqlite3.connect(proj / "data" / "ytitle.sqlite3")
    n = c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    c.close()
    return n


def seed(db, **kw):
    add_video(db)
    return add_candidate(db, dictionary_hash=DICT_HASH, **kw)


@pytest.fixture
def no_network(monkeypatch):
    """네트워크·구글 클라이언트 생성을 시도하면 즉시 실패하게 만든다. 호출 횟수를 센다."""
    calls = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError("네트워크/구글 호출 시도")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    import googleapiclient.discovery as disc
    monkeypatch.setattr(disc, "build", boom)
    return calls


def test_plan_screen_shows_diff_hash_and_checks(proj, db, streams, no_network):
    """TC-500: plan이 SCR-003 형식(제목 줄·변경 전/후·유지 항목·교체 제한 표·쿼터·계획 해시·A/B 안내·면책)을 출력하고 정상 종료한다. [EVT-004, FR-008, SCR-003, RISK-011, POL-002]"""
    cid = seed(db)
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 0
    out = streams.out.getvalue()
    expected = compute_plan_hash(VID, cid, "겨울 전기요금", "겨울철 전기요금 줄이는 난방 습관", SNIPPET)
    assert "[plan] 모드: 모의 실행(dry-run)" in out and f"영상: {VID}  후보번호: {cid}" in out
    assert "현재 제목: 겨울 전기요금" in out and "새 제목:   겨울철 전기요금 줄이는 난방 습관" in out
    assert "검증 결과: [통과]" in out
    for keep in ("categoryId(카테고리 26)", "description(설명 ", "tags(태그 3개)", "defaultLanguage"):
        assert keep in out
    assert "최소 간격" in out and "변경 횟수" in out and "최소 노출수" in out and "하루 적용 건수" in out and out.count("[통과]") >= 5
    assert "약 52 units(쓰기 50 + 조회 2회)" in out and "오늘 남은 양 6000 units" in out
    assert f"계획 해시: {expected}" in out
    assert "공식 A/B 테스트" in out and "아무것도 바꾸지 않았습니다" in out and "다음에 할 일" in out
    assert out.rstrip().endswith("법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.")
    assert no_network == []


def test_plan_writes_nothing_but_run_log(proj, db, streams, no_network):
    """TC-501: plan은 title_changes·쿼터·후보 상태를 전혀 바꾸지 않고(run_logs만 남김) 네트워크/구글 클라이언트를 건드리지 않는다. [EVT-004, SEC-001, K-2]"""
    cid = seed(db)
    before = {t: table_count(proj, t) for t in ("title_changes", "quota_usage", "metrics_snapshots", "videos", "title_candidates")}
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 0
    assert {t: table_count(proj, t) for t in before} == before
    assert table_count(proj, "run_logs") == 1
    c = sqlite3.connect(proj / "data" / "ytitle.sqlite3")
    assert c.execute("SELECT status FROM title_candidates").fetchone()[0] == "filtered" and c.execute("SELECT mode FROM run_logs").fetchone()[0] == "dry_run"
    c.close()
    assert no_network == []


@pytest.mark.parametrize("status,result", [("blocked", "block"), ("filtered", "block")])
def test_plan_refuses_blocked_candidate(proj, db, streams, status, result):
    """TC-502: 차단된 후보는 계획을 출력하지 않고 종료 코드 3으로 거부한다(해시도 출력하지 않음). [FR-005, POL-001, SEC-001]"""
    cid = seed(db, status=status, result=result)
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 3
    assert "차단되어 계획을 만들 수 없습니다" in streams.err.getvalue() and "계획 해시" not in streams.out.getvalue()


def test_plan_input_errors(proj, db, streams):
    """TC-503: 없는 후보·fetch 안 한 영상은 종료 코드 1과 다음 행동 안내이고, 미검증 후보는 3이다. [EVT-004, NFR-007]"""
    assert go(proj, streams, ["plan", "--candidate", "999"]) == 1 and "validate" in streams.err.getvalue()
    cid = add_candidate(db)
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 1 and "fetch --video" in streams.err.getvalue()
    add_video(db)
    cid2 = add_candidate(db, status="candidate", result=None)
    assert go(proj, streams, ["plan", "--candidate", str(cid2)]) == 3


@pytest.mark.parametrize("argv,code", [([], 2), (["--candidate", "abc"], 2), (["--candidate", "0"], 1), (["--candidate", "-3"], 1), (["--candidate", str(2**63)], 1), (["--candidate", "1", "--live"], 2)])
def test_plan_option_validation(proj, db, streams, argv, code):
    """TC-504: --candidate 필수(없으면 2), 숫자 아님 2, 0·음수·SQLite 범위 초과는 1, --live 옵션은 존재하지 않는다(2). [EVT-004, SEC-001]"""
    assert go(proj, streams, ["plan"] + argv) == code


def test_plan_limit_violation_screen(proj, db, streams):
    """TC-505: 72시간 이내 재변경이면 plan이 사유와 가능한 시각을 보여 주고 종료 코드 3이다. [FR-014, SCR-003, SEC-004]"""
    cid = seed(db)
    add_change(db, at=NOW - timedelta(hours=10))
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 3
    out = streams.out.getvalue()
    assert "[차단]" in out and "2026-10-13 11:00 (한국 시간) 이후에 가능" in out and "진행할 수 없습니다" in out and "다음에 할 일" not in out


def test_plan_quota_short_screen(proj, db, streams):
    """TC-506: 오늘 남은 쿼터가 필요량보다 적으면 [차단]과 함께 종료 코드 3이다. [SEC-002, SCR-003]"""
    cid = seed(db)
    (proj / "config" / "settings.yaml").write_text("quota:\n  daily_limit_units: 51\n", encoding="utf-8")
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 3
    out = streams.out.getvalue()
    assert "오늘 남은 양 51 units" in out and "진행할 수 없습니다" in out


def test_plan_notices_stale_dictionary_and_exclusions(proj, db, streams):
    """TC-507: 24시간 넘은 영상 정보·검증 이후 바뀐 금칙어 사전·공식 A/B 비대상 영상·경고 후보를 [주의]로 알린다. [EVT-004, SEC-017, POL-003]"""
    add_video(db, privacy="private", fetched_at=ts(NOW - timedelta(hours=30)))
    cid = add_candidate(db, result="warn", dictionary_hash="00000000", reasons=[["EXCL", "warn", "느낌표 1개"]])
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 0
    out = streams.out.getvalue()
    assert "24시간이 넘었" in out and "금칙어 사전이 검증 이후 바뀌었습니다" in out and f"→ 지금 {DICT_HASH}" in out
    assert "공식 A/B 대상이 아닐 수 있습니다" in out and "비공개 영상" in out and "검증 결과: [경고]  사유: 느낌표 1개" in out and "경고를 받은 제목" in out


def test_plan_dictionary_unreadable_is_flagged(proj, db, streams):
    """TC-508: 금칙어 사전을 읽을 수 없어도 plan은 동작하고 확인하지 못했다고 알린다. [SEC-017]"""
    cid = seed(db)
    (proj / "config" / "banned_terms.yaml").unlink()
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 0
    assert "확인하지 못했습니다" in streams.out.getvalue()


def test_plan_sequential_mode_excludes_video(proj, db, streams):
    """TC-509: 순차 교체 모드를 켜면 비공개 영상은 계획을 거부한다(종료 코드 3). [POL-003, FR-019]"""
    (proj / "config" / "settings.yaml").write_text("sequential_mode:\n  enabled: true\n", encoding="utf-8")
    add_video(db, privacy="private")
    cid = add_candidate(db)
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 3
    assert "비공개" in streams.err.getvalue()


def test_plan_sanitizes_external_strings(proj, db, streams):
    """TC-510: 영상 제목·검증 사유·카테고리·저장 시각의 ANSI 이스케이프·방향 제어 문자가 화면에 그대로 나오지 않는다. [SEC-019, T-13]"""
    evil = {**SNIPPET, "title": "\x1b[2J\x1b[31m가짜 완료‮", "categoryId": "\x1b[1m26"}
    add_video(db, snippet=evil, fetched_at="\x1b[31m엉터리")
    cid = add_candidate(db, dictionary_hash=DICT_HASH, reasons=[["X", "warn", "\x1b[32m사유\x07"]])
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 0
    out = streams.out.getvalue()
    assert "\x1b" not in out and "\x07" not in out and "‮" not in out and "가짜 완료" in out and "엉터리" in out


def test_plan_plain_mode(proj, db, streams):
    """TC-511: `--plain`에서도 교체 제한 결과가 한 줄씩 `[결과] 항목: 내용`으로 나온다(표·구분선 없음, 스크린리더 친화). [UX-003, SCR-003]"""
    cid = seed(db)
    assert go(proj, streams, ["plan", "--candidate", str(cid), "--plain"]) == 0
    out = streams.out.getvalue()
    assert "  [통과] 최소 간격: 이전 변경 기록이 없습니다." in out and "------" not in out


def test_plan_hash_in_output_tracks_snippet(proj, db, streams):
    """TC-512: 영상 정보가 fetch로 갱신되면 같은 후보라도 출력되는 계획 해시가 달라진다. [SEC-014, SEC-009]"""
    cid = seed(db)
    go(proj, streams, ["plan", "--candidate", str(cid)])
    first = [l for l in streams.out.getvalue().splitlines() if l.startswith("계획 해시")][0]
    add_video(db, snippet={**SNIPPET, "tags": ["바뀐태그"]})
    streams.out.truncate(0), streams.out.seek(0)
    go(proj, streams, ["plan", "--candidate", str(cid)])
    second = [l for l in streams.out.getvalue().splitlines() if l.startswith("계획 해시")][0]
    assert first != second


def test_plan_is_discoverable_and_approved_candidate_ok(proj, db, streams):
    """TC-513: plan·rollback이 --help에 자동으로 나타나고, 이미 승인된 후보도 계획을 볼 수 있다. [FR-017, ADR-003]"""
    assert go(proj, streams, ["--help"]) == 0
    out = streams.out.getvalue()
    assert "plan" in out and "rollback" in out
    cid = seed(db, status="approved")
    assert go(proj, streams, ["plan", "--candidate", str(cid)]) == 0
