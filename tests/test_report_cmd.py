import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ytitle import cli, db
from ytitle.commands import report as cmd
from ytitle.report import CAUSAL_NOTE, LIMIT_NOTE
from ytitle.timeutil import FixedClock
from ytitle.ui import footer

VID = "abc123DEF45"
APPLIED = "2026-09-01T03:00:00Z"
HEAD = "Content,Views,Impressions,Impressions click-through rate (%),Watch time (hours)\n"
BEFORE_CSV = HEAD + f'{VID},"2,800","28,000",3.0%,93.3333333\n'
AFTER_CSV = HEAD + f'{VID},"5,600","56,000",4.5%,186.6666667\n'
BEFORE = ["--phase", "before", "--period-start", "2026-08-04", "--period-end", "2026-08-31"]
AFTER = ["--phase", "after", "--period-start", "2026-09-02", "--period-end", "2026-09-29"]


@pytest.fixture
def proj(project):
    (project / "exports").mkdir()
    return project


def go(proj, streams, argv):
    clock = FixedClock(datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    return cli.main(["--base-dir", str(proj)] + argv, out=streams.out, err=streams.err, env={}, clock=clock)


def out(streams):
    return streams.out.getvalue()


def dbconn(proj):
    c = db.connect(proj / "data" / "ytitle.sqlite3")
    db.migrate(c)
    return c


def seed_change(proj, vid=VID, title="현재 제목", prev="이전 제목", new="새 제목", at=APPLIED, ctype="apply", result="success"):
    c = dbconn(proj)
    if title is not None:
        c.execute("INSERT OR IGNORE INTO videos (video_id,title,snippet_json,fetched_at) VALUES (?,?,?,?)", (vid, title, "{}", "x"))
    c.execute(
        "INSERT INTO title_changes (video_id, change_type, previous_title, new_title, result, applied_at, created_at, approver) VALUES (?,?,?,?,?,?,?,?)",
        (vid, ctype, prev, new, result, at, at, "me"),
    )
    c.commit()
    c.close()


def write(proj, name, text, enc="utf-8"):
    p = proj / "exports" / name
    p.write_bytes(text.encode(enc))
    return f"exports/{name}"


def snapshots(proj):
    c = dbconn(proj)
    rows = c.execute("SELECT * FROM metrics_snapshots ORDER BY id").fetchall()
    c.close()
    return rows


def dump_tables(proj, skip=("run_logs", "sqlite_sequence")):
    c = dbconn(proj)
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] not in skip]
    data = {n: c.execute(f"SELECT * FROM {n}").fetchall() for n in names}
    c.close()
    return {k: [tuple(r) for r in v] for k, v in data.items()}


def test_import_csv_saves_rows_and_summarizes(proj, streams):
    """TC-660: `--import-csv`가 CSV를 metrics_snapshots(source=csv)에 저장하고 단계·기간·인코딩을 포함한 요약을 보여 준다. [EVT-008, FR-007]"""
    f = write(proj, "before.csv", BEFORE_CSV)
    assert go(proj, streams, ["report", "--import-csv", f] + BEFORE) == 0
    o = out(streams)
    assert "[report] 모드: 모의 실행(dry-run)" in o and "[완료] CSV 1행 중 1행을 저장했습니다(단계 before, 기간 2026-08-04 ~ 2026-08-31, 인코딩 utf-8)" in o
    r = snapshots(proj)
    assert len(r) == 1 and (r[0]["source"], r[0]["phase"], r[0]["impressions"], r[0]["views"], r[0]["ctr"]) == ("csv", "before", 28000, 2800, 3.0)
    assert r[0]["watch_minutes"] == pytest.approx(5600.0, abs=0.01)
    assert o.rstrip().endswith("법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.")


def test_fetch_fallback_guidance_option_exists(proj, streams):
    """TC-661: fetch의 폴백 안내가 가리키는 `report --import-csv`가 실제로 존재하고 --help에 보인다. [FR-007, EVT-002, EVT-008]"""
    fetch_src = (Path(cmd.__file__).parent / "fetch.py").read_text(encoding="utf-8")
    assert "report --import-csv" in fetch_src
    assert go(proj, streams, ["--help"]) == 0 and "report" in out(streams)
    streams.out.truncate(0), streams.out.seek(0)
    assert go(proj, streams, ["report", "--help"]) == 0
    h = out(streams)
    assert "--import-csv" in h and "--video" in h and "--plain" in h and "--period-start" in h


def test_full_flow_sufficient_data_shows_table_and_disclaimers(proj, streams):
    """TC-662: 변경 전·후 CSV를 가져온 뒤 `--video` 리포트가 전후 표(변화율)를 보여 주고, 단정 금지 한계 문구와 면책 문구가 항상 나온다. [FR-018, SCR-008, POL-002]"""
    seed_change(proj)
    go(proj, streams, ["report", "--import-csv", write(proj, "b.csv", BEFORE_CSV)] + BEFORE)
    streams.out.truncate(0), streams.out.seek(0)
    assert go(proj, streams, ["report", "--import-csv", write(proj, "a.csv", AFTER_CSV), "--video", VID] + AFTER) == 0
    o = out(streams)
    assert f"영상: {VID}  제목: 현재 제목" in o and "이전 제목" in o and "새 제목" in o and "2026-09-01 12:00" in o  # 한국 시간
    assert "[완료] 비교할 수 있는 자료가 충분합니다" in o and "데이터 부족" not in o
    assert re.search(r"노출수\(하루 평균\)\s+1,000\.0\s+2,000\.0\s+\+1,000\.0\s+\+100\.0%", o)
    assert re.search(r"노출 클릭률\(%\)\s+3\.00\s+4\.50\s+\+1\.50\s+\+50\.0%", o)
    assert LIMIT_NOTE in o and CAUSAL_NOTE in o and footer() in o


def test_insufficient_data_shows_label_reasons_and_no_conclusion(proj, streams):
    """TC-663: 변경 후 자료가 없으면 '데이터 부족'과 사유·수집 예정일만 보여 주고 비교 표·결론을 내지 않지만 면책 문구는 나온다. [FR-018, SCR-008, POL-002]"""
    seed_change(proj)
    go(proj, streams, ["report", "--import-csv", write(proj, "b.csv", BEFORE_CSV)] + BEFORE)
    streams.out.truncate(0), streams.out.seek(0)
    assert go(proj, streams, ["report", "--video", VID]) == 0
    o = out(streams)
    assert "[주의] 데이터 부족: 결론을 내릴 수 없어 비교하지 않습니다." in o and "변경 후 지표가 아직 없습니다." in o and "수집 예정일: 2026-09-15" in o
    assert "변화율" not in o and "충분합니다" not in o and "변경 전 자료: 출처 csv" in o
    assert LIMIT_NOTE in o and CAUSAL_NOTE in o and footer() in o
    assert "효과" not in o and "개선되었" not in o and "성공" not in o


def test_baseline_missing_warns_low_reliability(proj, streams):
    """TC-664: 변경 전 기준선이 없으면 신뢰도 낮음 경고를 표시한다. [FR-012, SCR-008]"""
    seed_change(proj)
    go(proj, streams, ["report", "--import-csv", write(proj, "a.csv", AFTER_CSV)] + AFTER)
    streams.out.truncate(0), streams.out.seek(0)
    go(proj, streams, ["report", "--video", VID])
    o = out(streams)
    assert "변경 전 지표(기준선)가 없습니다." in o and "기준선이 없어 이후에 자료가 모여도 신뢰도가 낮습니다" in o and "변경 후 자료: 출처 csv" in o


def test_min_impressions_boundary_through_command(proj, streams):
    """TC-665: 노출수 경계(설정 최소 기준 1,000회)가 명령 출력에도 반영된다: 하루 평균이 아니라 기간 합계 노출수 기준. [FR-014, FR-018, 경계값]"""
    seed_change(proj)
    thin = HEAD + f"{VID},10,999,3.0%,1\n"
    go(proj, streams, ["report", "--import-csv", write(proj, "b.csv", thin)] + BEFORE)
    go(proj, streams, ["report", "--import-csv", write(proj, "a.csv", AFTER_CSV)] + AFTER)
    streams.out.truncate(0), streams.out.seek(0)
    go(proj, streams, ["report", "--video", VID])
    assert "노출수 999회가 최소 기준 1,000회보다 적습니다" in out(streams) and "데이터 부족" in out(streams)
    c = dbconn(proj)
    c.execute("UPDATE metrics_snapshots SET impressions = 1000 WHERE phase='before'")
    c.commit()
    c.close()
    streams.out.truncate(0), streams.out.seek(0)
    go(proj, streams, ["report", "--video", VID])
    assert "충분합니다" in out(streams)


def test_plain_mode_lists_items(proj, streams):
    """TC-666: `--plain`은 표 대신 `항목: 값` 목록으로 출력한다(스크린리더 친화). [UX-007, SCR-008, 04 접근성]"""
    seed_change(proj)
    go(proj, streams, ["report", "--import-csv", write(proj, "b.csv", BEFORE_CSV), "--plain"] + BEFORE)
    go(proj, streams, ["report", "--import-csv", write(proj, "a.csv", AFTER_CSV), "--plain"] + AFTER)
    streams.out.truncate(0), streams.out.seek(0)
    assert go(proj, streams, ["report", "--video", VID, "--plain"]) == 0
    o = out(streams)
    assert "  지표: 노출수(하루 평균)" in o and "  변경 전: 1,000.0" in o and "  변화율: +100.0%" in o and "  새 제목: 새 제목" in o
    assert "------" not in o and "- 항목 1" in o and LIMIT_NOTE in o


def test_skipped_rows_reported_with_counts_and_examples(proj, streams):
    """TC-667: 불량 행은 건너뛰고 이유별 개수와 예시(줄 번호)를 보여 주며 나머지는 저장한다(종료 코드 0). 예시는 10개까지만 보여 준다. [FR-007, 규칙 B]"""
    bad = "".join(f"bad{i},1,1,1%,1\n" for i in range(12))
    f = write(proj, "m.csv", HEAD + f"{VID},10,2000,2%,1\n" + bad + f"{VID},99,9999,9%,9\n")
    assert go(proj, streams, ["report", "--import-csv", f]) == 0
    o = out(streams)
    assert "건너뛴 행 13개" in o and "영상 ID 형식이 올바르지 않습니다" in o and "같은 영상이 파일에 중복" in o and "... 외 3개" in o
    assert "CSV 14행 중 1행을 저장" in o and len(snapshots(proj)) == 1
    assert "인식한 열: video_id=Content" in o and "impressions=Impressions" in o


def test_all_rows_bad_is_error_and_saves_nothing(proj, streams):
    """TC-668: 유효한 행이 하나도 없으면 이유를 보여 주고 오류(종료 코드 1, 다음에 할 일 포함)로 끝나며 DB에 아무것도 저장하지 않는다. [FR-007, NFR-007]"""
    f = write(proj, "x.csv", HEAD + "nope,1,1,1%,1\n")
    assert go(proj, streams, ["report", "--import-csv", f]) == 1
    assert "건너뛴 행 1개" in out(streams) and "가져올 수 있는 행이 하나도 없습니다" in streams.err.getvalue() and "다음에 할 일" in streams.err.getvalue()
    assert snapshots(proj) == []


def test_reimport_is_idempotent_and_warns(proj, streams):
    """TC-669: 같은 CSV를 다시 가져오면 중복 저장하지 않고 알린다. 영상 정보가 DB에 없거나 기간이 없거나 periodic이면 주의 문구를 보여 준다. [FR-007]"""
    f = write(proj, "b.csv", BEFORE_CSV)
    go(proj, streams, ["report", "--import-csv", f])
    o = out(streams)
    assert "DB에 영상 정보가 없는 영상 1개" in o and "집계 기간을 알려 주지 않아" in o and "periodic이면 변경 전후 비교에 쓰이지 않습니다" in o
    streams.out.truncate(0), streams.out.seek(0)
    go(proj, streams, ["report", "--import-csv", f])
    assert "0행을 저장" in out(streams) and "이미 같은 내용이 저장되어 있어 건너뛴 행: 1개" in out(streams) and len(snapshots(proj)) == 1


def test_no_args_without_history_guides_user(proj, streams):
    """TC-670: 옵션 없이 실행했는데 변경 기록이 없으면 안내만 하고 정상 종료한다(빈 상태). [SCR-008, NFR-007]"""
    assert go(proj, streams, ["report"]) == 0
    assert "제목을 바꾼 기록이 없어" in out(streams) and "fetch --metrics --phase before" in out(streams) and LIMIT_NOTE not in out(streams)


def test_no_args_lists_changed_videos_and_truncates(proj, streams):
    """TC-671: 옵션 없이 실행하면 제목을 바꾼 영상을 최근 순으로 보여 주고 20개를 넘으면 `외 N개`로 줄인다. [FR-018]"""
    for i in range(22):
        seed_change(proj, vid=f"vid{i:08d}", at=f"2026-09-{i + 1:02d}T03:00:00Z" if i < 28 else APPLIED)
    assert go(proj, streams, ["report"]) == 0
    o = out(streams)
    assert o.count("영상: vid") == 20 and "외 2개 영상" in o
    assert o.index("영상: vid00000021") < o.index("영상: vid00000020")  # 최근 변경이 먼저
    assert "vid00000000" not in o and LIMIT_NOTE in o


def test_video_without_changes_says_not_comparable(proj, streams):
    """TC-672: 변경 기록이 없는 영상은 비교할 수 없다고 알리고 DB에 제목이 없어도 오류 없이 처리한다. [FR-018]"""
    assert go(proj, streams, ["report", "--video", VID]) == 0
    o = out(streams)
    assert "(DB에 저장된 제목 없음)" in o and "성공한 제목 변경 기록이 없어 비교할 수 없습니다" in o and "데이터 부족" not in o and LIMIT_NOTE in o


@pytest.mark.parametrize(
    "argv,msg",
    [
        (["--video", "bad"], "영상 ID 형식"),
        (["--phase", "before"], "함께만 쓸 수 있습니다"),
        (["--period-start", "2026-01-01"], "함께만 쓸 수 있습니다"),
        (["--period-end", "2026-01-01"], "함께만 쓸 수 있습니다"),
        (["--import-csv", "exports/b.csv", "--period-start", "2026-13-01", "--period-end", "2026-01-02"], "시작일 날짜 형식"),
        (["--import-csv", "exports/b.csv", "--period-start", "2026-01-01", "--period-end", "x"], "종료일 날짜 형식"),
        (["--import-csv", "exports/b.csv", "--period-start", "2026-01-01"], "함께 지정"),
        (["--import-csv", "exports/b.csv", "--period-start", "2026-02-01", "--period-end", "2026-01-01"], "늦습니다"),
        (["--import-csv", "exports/none.csv"], "찾을 수 없습니다"),
        (["--import-csv", "exports/b.txt"], r"\.csv"),
    ],
)
def test_invalid_options_are_input_errors_without_db_write(proj, streams, argv, msg):
    """TC-673: 잘못된 옵션 조합·영상 ID·날짜·파일은 종료 코드 1과 다음에 할 일을 안내하고 지표를 저장하지 않는다. [NFR-007, SEC-016]"""
    write(proj, "b.csv", BEFORE_CSV)
    write(proj, "b.txt", BEFORE_CSV)
    assert go(proj, streams, ["report"] + argv) == 1
    assert re.search(msg, streams.err.getvalue()) and "다음에 할 일" in streams.err.getvalue()
    assert snapshots(proj) == []


def test_import_phase_choices_enforced_by_argparse(proj, streams):
    """TC-674: `--phase`는 before/after/periodic만 받는다(그 밖의 값은 사용법 오류, 종료 코드 2). [EVT-008]"""
    write(proj, "b.csv", BEFORE_CSV)
    assert go(proj, streams, ["report", "--import-csv", "exports/b.csv", "--phase", "weekly"]) == 2


def test_csv_injection_and_ansi_never_reach_screen_raw(proj, streams):
    """TC-675: CSV 안의 수식 문자열·ANSI 이스케이프는 화면에 날것으로 나오지 않는다(앞에 '가 붙고 제어문자 제거). DB 제목의 ANSI도 정화된다. [SEC-016, SEC-019, T-11, T-13]"""
    evil = HEAD + '"=HYPERLINK(""http://evil"",""x"")",1,1,1%,1\n' + '"\x1b[2J@cmd",1,1,1%,1\n' + f"{VID},5,2000,2%,1\n"
    seed_change(proj, title="\x1b[31m빨강\x1b[0m 제목", prev="\x1b[2J이전", new="\x1b]0;해킹\x07새")
    assert go(proj, streams, ["report", "--import-csv", write(proj, "e.csv", evil), "--video", VID, "--phase", "before"]) == 0
    o = out(streams)
    assert "\x1b" not in o and "\x07" not in o
    assert "'=HYPERLINK" in o and "'@cmd" in o and not re.search(r"(?<!')=HYPERLINK", o)
    assert "빨강 제목" in o.replace("[31m", "").replace("[0m", "") or "빨강" in o
    r = snapshots(proj)
    assert len(r) == 1 and r[0]["video_id"] == VID  # 수식 줄은 저장되지 않음


def test_sql_injection_like_values_are_bound(proj, streams):
    """TC-676: CSV 셀·DB 문자열의 SQL 조각은 값으로만 쓰여 테이블이 유지된다(영상 ID 형식 검증 + 바인딩). [SEC-018, T-12]"""
    inj = HEAD + f"x'); DROP TABLE metrics_snapshots;--,1,1,1%,1\n{VID},5,2000,2%,1\n"
    assert go(proj, streams, ["report", "--import-csv", write(proj, "i.csv", inj)]) == 0
    assert len(snapshots(proj)) == 1
    assert go(proj, streams, ["report", "--video", "x'); DROP--"]) == 1  # 형식 검증에서 거부
    assert len(snapshots(proj)) == 1


def test_report_run_is_read_only_except_run_log(proj, streams):
    """TC-677: 리포트(가져오기 없음)는 run_logs 외 어떤 테이블도 바꾸지 않는다(읽기 전용). [FR-018, SEC-001]"""
    seed_change(proj)
    go(proj, streams, ["report", "--import-csv", write(proj, "b.csv", BEFORE_CSV)] + BEFORE)
    before = dump_tables(proj)
    assert go(proj, streams, ["report"]) == 0 and go(proj, streams, ["report", "--video", VID, "--plain"]) == 0
    assert dump_tables(proj) == before


def test_import_does_not_modify_other_tables_or_input_file(proj, streams):
    """TC-678: CSV 가져오기는 metrics_snapshots 외 테이블과 입력 파일을 바꾸지 않는다. [FR-007, SEC-016]"""
    seed_change(proj)
    before = dump_tables(proj)
    f = write(proj, "b.csv", BEFORE_CSV)
    raw = (proj / f).read_bytes()
    go(proj, streams, ["report", "--import-csv", f] + BEFORE)
    after = dump_tables(proj)
    assert {k: v for k, v in after.items() if k != "metrics_snapshots"} == {k: v for k, v in before.items() if k != "metrics_snapshots"}
    assert (proj / f).read_bytes() == raw


def test_cp949_file_imports_through_command(proj, streams):
    """TC-679: CP949(엑셀 한글 저장) CSV도 명령으로 가져오고 인코딩을 알려 준다. [DESIGN 9장 WU-6, NFR-002]"""
    f = write(proj, "k.csv", "콘텐츠,조회수,노출수\n" + f"{VID},10,2000\n", enc="cp949")
    assert go(proj, streams, ["report", "--import-csv", f]) == 0 and "인코딩 cp949" in out(streams)


def test_oversized_csv_rejected_by_command(proj, streams):
    """TC-680: 5MB를 넘는 CSV는 명령에서도 거부되고 아무것도 저장하지 않는다. [SEC-016, T-11]"""
    (proj / "exports" / "big.csv").write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    assert go(proj, streams, ["report", "--import-csv", "exports/big.csv"]) == 1
    assert "너무 큽니다" in streams.err.getvalue() and snapshots(proj) == []


def test_kst_helper_and_number_formats():
    """TC-681: 시각은 한국 시간으로, 해석할 수 없는 값은 정화한 원문으로 표시하고, 숫자 서식은 없음(-)·부호를 처리한다. [04 UX 날짜 규칙]"""
    assert cmd._kst("2026-09-01T15:30:00Z") == "2026-09-02 00:30"
    assert cmd._kst("garbage\x1b[0m") == "garbage"
    assert cmd._num(None) == "-" and cmd._num(1234.5, 0) == "1,234" and cmd._num(0.5, 2) == "0.50"
    assert cmd._signed(None) == "-" and cmd._signed(1.234, 1) == "+1.2" and cmd._signed(-5.0, 1, "%") == "-5.0%" and cmd._signed(0, 1) == "+0.0"
    assert "기간 정보 없음" in cmd._snap_line("전", type("S", (), dict(period_start=None, period_end=None, source="csv", impressions=None, ctr=None, views=None, watch_minutes=None))())


def test_module_has_no_network_or_write_api():
    """TC-682: report 명령 모듈에는 네트워크·YouTube 호출 코드가 없다(이 단위는 읽기 전용 + CSV 읽기 + DB 기록). [SEC-001, SEC-007]"""
    root = Path(cmd.__file__).resolve().parents[1]
    for name in ("report.py", "csv_import.py", "commands/report.py"):
        text = (root / name).read_text(encoding="utf-8")
        for bad in ("googleapiclient", "requests", "urllib", "socket", "videos().update", ".update(body", "build_services", "load_credentials"):
            assert bad not in text, (name, bad)


def test_unrecognized_columns_are_listed_as_ignored(proj, streams):
    """TC-683: 인식하지 못한 열(영상 제목·게시 시간 등)은 무시하고 어떤 열을 무시했는지 알려 준다. [FR-007, EVT-203]"""
    text = "Content,Video title,Video publish time,Views\n" + f'{VID},"=1+1","Jan 1, 2026",10\n'
    assert go(proj, streams, ["report", "--import-csv", write(proj, "e.csv", text)]) == 0
    assert "무시한 열: Video title, Video publish time" in out(streams)
    raw = snapshots(proj)[0]["raw_json"]
    assert "'=1+1" in raw and '"=1+1"' not in raw  # 수식 문자열은 앞에 '가 붙은 값으로만 기록


def test_video_option_supplies_id_for_csv_without_id_column(proj, streams):
    """TC-684: 영상 ID 열이 없는 CSV(한 영상의 합계 줄)는 `--video ID`로 대상 영상을 지정해 가져온다. [FR-007, EVT-008]"""
    f = write(proj, "one.csv", "조회수,노출수\n10,2000\n")
    assert go(proj, streams, ["report", "--import-csv", f, "--video", VID, "--phase", "before"]) == 0
    assert [(r["video_id"], r["views"]) for r in snapshots(proj)] == [(VID, 10)]
    streams.err.truncate(0), streams.err.seek(0)
    assert go(proj, streams, ["report", "--import-csv", f]) == 1 and "영상 ID 열" in streams.err.getvalue()
