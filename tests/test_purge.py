import sqlite3
from datetime import datetime, timezone

from ytitle import cli, db
from ytitle.timeutil import FixedClock


def seed(project):
    conn = db.connect(project / "data" / "ytitle.sqlite3")
    db.migrate(conn)
    old, new = "2025-01-01T00:00:00Z", "2026-10-01T00:00:00Z"
    conn.execute("INSERT INTO title_candidates (id,video_id,candidate_title,source,strict_mode,status,created_at,updated_at) VALUES (1,'v1','옛 후보','human',0,'applied',?,?)", (old, old))
    conn.execute("INSERT INTO title_candidates (id,video_id,candidate_title,source,strict_mode,status,created_at,updated_at) VALUES (2,'v1','옛 후보2','human',0,'candidate',?,?)", (old, old))
    conn.execute("INSERT INTO title_changes (id,video_id,candidate_id,change_type,previous_title,new_title,result,created_at) VALUES (1,'v1',1,'apply','a','b','success',?)", (old,))
    conn.execute("INSERT INTO title_changes (id,video_id,candidate_id,change_type,previous_title,new_title,result,created_at) VALUES (2,'v2',NULL,'apply','c','d','success',?)", (old,))
    conn.execute("INSERT INTO title_changes (id,video_id,candidate_id,change_type,previous_title,new_title,result,created_at) VALUES (3,'v2',NULL,'apply','d','e','failed',?)", (old,))
    conn.execute("INSERT INTO metrics_snapshots (video_id,taken_at,phase,source) VALUES ('v1',?,'before','api')", (old,))
    conn.execute("INSERT INTO metrics_snapshots (video_id,taken_at,phase,source) VALUES ('v1',?,'after','api')", (new,))
    conn.execute("INSERT INTO quota_usage (pt_date,method,units,called_at,status) VALUES ('2025-01-01','videos.list',1,?,'ok')", (old,))
    conn.commit()
    conn.close()


def go(project, streams, argv, answers=()):
    it = iter(answers)
    clock = FixedClock(datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    return cli.main(["--base-dir", str(project)] + argv, out=streams.out, err=streams.err, env={}, clock=clock, input_fn=lambda p: next(it))


def counts(project):
    c = sqlite3.connect(project / "data" / "ytitle.sqlite3")
    r = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("title_changes", "title_candidates", "metrics_snapshots", "quota_usage")}
    c.close()
    return r


def test_preview_deletes_nothing(project, streams):
    """TC-066: 기본(미리보기)은 대상 건수만 보여 주고 아무것도 지우지 않는다. [NFR-009, SCR-010]"""
    seed(project)
    before = counts(project)
    assert go(project, streams, ["purge", "--before", "2026-06-01"]) == 0
    out = streams.out.getvalue()
    assert counts(project) == before and "미리보기" in out and "title_changes" in out and "법률 자문이 아니며" in out


def test_execute_requires_typed_confirmation(project, streams):
    """TC-067: --execute라도 '삭제'를 직접 입력해야 하고, 입력이 없으면 삭제하지 않는다. [SEC-001 정신, SCR-010]"""
    seed(project)
    before = counts(project)
    assert go(project, streams, ["purge", "--before", "2026-06-01", "--execute"], answers=[""]) == 1
    assert counts(project) == before
    assert not (project / "data" / "backups").exists() or not list((project / "data" / "backups").glob("*"))


def test_execute_deletes_old_rows_but_protects_latest_success_and_backs_up(project, streams):
    """TC-068: 실행하면 DB 사본을 먼저 만들고, 영상별 가장 최근 성공 변경(롤백용)과 그 후보는 보존한다. [NFR-009, SEC-006]"""
    seed(project)
    assert go(project, streams, ["purge", "--before", "2026-06-01", "--execute"], answers=["삭제"]) == 0
    c = sqlite3.connect(project / "data" / "ytitle.sqlite3")
    kept_changes = {r[0] for r in c.execute("SELECT id FROM title_changes")}
    kept_cands = {r[0] for r in c.execute("SELECT id FROM title_candidates")}
    new_metrics = c.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0]
    c.close()
    assert kept_changes == {1, 2}      # v1, v2 각각의 마지막 성공 변경 보존, 실패(3)만 삭제
    assert kept_cands == {1}           # 보존된 변경이 가리키는 후보 1은 유지, 후보 2는 삭제
    assert new_metrics == 1            # 기준일 이후(after) 지표는 유지
    assert len(list((project / "data" / "backups").glob("ytitle_*.sqlite3"))) == 1
    assert "삭제 전 DB 사본" in streams.out.getvalue()


def test_future_date_and_bad_format_rejected(project, streams):
    """TC-069: 미래 날짜와 잘못된 형식은 거부되고 아무것도 지우지 않는다. [NFR-007]"""
    seed(project)
    before = counts(project)
    assert go(project, streams, ["purge", "--before", "2099-01-01", "--execute"], answers=["삭제"]) == 1
    err = streams.err.getvalue()
    assert "YT-500" in err and "미래 날짜" in err
    assert counts(project) == before
    streams.err.truncate(0), streams.err.seek(0)
    assert go(project, streams, ["purge", "--before", "어제", "--execute"], answers=["삭제"]) == 1
    assert "YYYY-MM-DD" in streams.err.getvalue()
    assert counts(project) == before and not (project / "data" / "backups").exists()


def test_nothing_to_delete(project, streams):
    """TC-070: 대상이 없으면 확인 없이 '삭제할 기록이 없습니다'로 끝난다. [SCR-010]"""
    seed(project)
    assert go(project, streams, ["purge", "--before", "2020-01-01", "--execute"]) == 0
    assert "삭제할 기록이 없습니다" in streams.out.getvalue()


def test_run_log_of_current_run_survives_purge(project, streams):
    """TC-071: 지금 실행 중인 명령의 run_logs 행은 삭제 대상에서 제외된다. [FR-020]"""
    seed(project)
    go(project, streams, ["purge", "--before", "2026-10-10", "--execute"], answers=["삭제"])
    c = sqlite3.connect(project / "data" / "ytitle.sqlite3")
    n = c.execute("SELECT COUNT(*) FROM run_logs WHERE command='purge'").fetchone()[0]
    c.close()
    assert n >= 1
