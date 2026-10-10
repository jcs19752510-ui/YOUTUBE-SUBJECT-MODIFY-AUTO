import socket
import sqlite3
from datetime import timedelta

import pytest
from wu4_support import NOW, SNIPPET, add_candidate, add_change, add_video, clock, make_settings, open_db, ts

from ytitle import cli
from ytitle.history import begin_change, finish_change, plan_rollback
from ytitle.updater import create_plan


@pytest.fixture
def db(project):
    c = open_db(project / "data" / "ytitle.sqlite3")
    yield c
    c.close()


def go(proj, streams, argv):
    return cli.main(["--base-dir", str(proj)] + argv, out=streams.out, err=streams.err, env={}, clock=clock())


def counts(proj):
    c = sqlite3.connect(proj / "data" / "ytitle.sqlite3")
    out = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("title_changes", "quota_usage", "title_candidates")}
    out["statuses"] = [r[0] for r in c.execute("SELECT status FROM title_candidates ORDER BY id")]
    out["results"] = [r[0] for r in c.execute("SELECT result FROM title_changes ORDER BY id")]
    c.close()
    return out


def applied(db, project):
    """승인·적용 성공까지 끝낸 상태(DB 처리만). 변경 번호를 돌려준다."""
    s = make_settings(project)
    add_video(db)
    cid = add_candidate(db, status="approved")
    plan = create_plan(db, s, clock(), cid)
    chg = begin_change(db, s, plan, approver="홍길동", approved_at=NOW, run_id="r", now=NOW)
    finish_change(db, chg, "success", NOW)
    add_video(db, snippet={**SNIPPET, "title": plan.new_title}, fetched_at=ts(NOW))
    return chg, plan


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError("네트워크/구글 호출 시도")

    monkeypatch.setattr(socket.socket, "connect", boom)
    import googleapiclient.discovery as disc
    monkeypatch.setattr(disc, "build", boom)
    return calls


def test_rollback_plan_screen(project, db, streams, no_network):
    """TC-520: rollback --change N은 현재/복원 제목·유지 항목·계획 해시·A/B 안내를 보여 주고 DB와 네트워크를 건드리지 않는다. [EVT-007, FR-011, SCR-005 계획부]"""
    chg, plan = applied(db, project)
    before = counts(project)
    assert go(project, streams, ["rollback", "--change", str(chg)]) == 0
    out = streams.out.getvalue()
    rp = plan_rollback(db, make_settings(project), clock(), chg)
    assert "[rollback] 모드: 모의 실행(dry-run)" in out and f"되돌릴 변경번호: {chg}" in out
    assert f"현재 제목:      {plan.new_title}" in out and "복원할 제목:    겨울 전기요금" in out
    assert "description" in out and "tags" in out and "categoryId" in out and f"계획 해시: {rp.plan_hash}" in out
    assert "공식 A/B 테스트" in out and out.rstrip().endswith("법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.")
    assert counts(project) == before and no_network == []


def test_rollback_live_is_stub_and_writes_nothing(project, db, streams, no_network):
    """TC-521: --live를 줘도 '아직 활성화되지 않았습니다'로 거부(종료 코드 3)하고, 쓰기 호출 0건·이력 변화 0건이다. [DESIGN 1-3 WU-4, SEC-001]"""
    chg, plan = applied(db, project)
    before = counts(project)
    assert go(project, streams, ["rollback", "--change", str(chg), "--live"]) == 3
    assert "아직 활성화되지 않았습니다" in streams.err.getvalue() and "[rollback]" in streams.out.getvalue()
    assert counts(project) == before and no_network == []


def test_rollback_refusals(project, db, streams):
    """TC-522: 없는 변경은 1, 실패한 변경·이미 롤백 대상이 아닌 변경은 3, 옵션 누락 2, 번호 범위 밖 1. [EVT-007, NFR-007]"""
    assert go(project, streams, ["rollback", "--change", "99"]) == 1
    failed = add_change(db, result="failed", at=NOW, error="YT-700")
    assert go(project, streams, ["rollback", "--change", str(failed)]) == 3
    assert go(project, streams, ["rollback"]) == 2
    for bad in ("0", "-1", str(2**63)):
        assert go(project, streams, ["rollback", "--change", bad]) == 1


def test_rollback_after_rollback_is_refused(project, db, streams):
    """TC-523: 이미 롤백이 기록된 변경은 다시 롤백할 수 없다(이후 변경 존재). [FR-011]"""
    chg, plan = applied(db, project)
    add_change(db, change_type="rollback", at=NOW + timedelta(hours=1), prev=plan.new_title, new=plan.previous_title)
    assert go(project, streams, ["rollback", "--change", str(chg)]) == 3
    assert "이후에" in streams.err.getvalue()


def test_rollback_cautions(project, db, streams):
    """TC-524: 적용 이후 다른 항목·제목이 바뀌었거나 영상 정보가 오래됐으면 [주의]로 알린다. [SEC-009, SEC-005]"""
    chg, plan = applied(db, project)
    add_video(db, snippet={**SNIPPET, "title": "Studio에서 또 바꾼 제목", "description": "고친 설명"}, fetched_at=ts(NOW - timedelta(hours=30)))
    assert go(project, streams, ["rollback", "--change", str(chg)]) == 0
    out = streams.out.getvalue()
    assert "적용 이후 제목 외 항목이 달라졌습니다" in out and "description" in out
    assert "지금 제목이 우리가 적용한 제목과 다릅니다" in out and "24시간이 넘었" in out


def test_rollback_sanitizes_external_strings(project, db, streams):
    """TC-525: 제목·항목 이름·저장 시각의 ANSI/방향 제어 문자가 화면에 나오지 않는다. [SEC-019, T-13]"""
    chg, plan = applied(db, project)
    add_video(db, snippet={**SNIPPET, "title": "\x1b[2J\x1b[31m가짜‮", "\x1b[1m이상한키": "x"}, fetched_at="\x1b[31m엉터리")
    assert go(project, streams, ["rollback", "--change", str(chg)]) == 0
    out = streams.out.getvalue()
    assert "\x1b" not in out and "‮" not in out and "가짜" in out


def test_rollback_help_mentions_inactive_live(project, streams):
    """TC-526: rollback 도움말이 실제 복원(--live)이 아직 비활성임을 밝힌다. [NFR-007, SCR-001]"""
    assert go(project, streams, ["rollback", "--help"]) == 0
    assert "활성화" in streams.out.getvalue()
