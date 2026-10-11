import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ytitle import cli
from ytitle.timeutil import FixedClock

REAL_DICT = Path(__file__).resolve().parent.parent / "config" / "banned_terms.yaml"
SUMMARY = "겨울철 난방 습관을 바꿔 전기요금을 줄이는 방법을 소개합니다"


@pytest.fixture
def proj(project):
    shutil.copy(REAL_DICT, project / "config" / "banned_terms.yaml")
    (project / "candidates").mkdir()
    return project


def cfile(proj, vid="abc123DEF45", titles=("겨울철 전기요금 줄이는 난방 습관",), topic="life", summary=SUMMARY, **extra):
    d = {"video_id": vid, "current_title": "겨울 전기요금", "topic": topic, "summary": summary, "source": "human",
         "candidates": [{"title": t, "evidence": summary} for t in titles]}
    d.update(extra)
    p = proj / "candidates" / f"{vid}.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p


def go(proj, streams, argv):
    clock = FixedClock(datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc))
    return cli.main(["--base-dir", str(proj)] + argv, out=streams.out, err=streams.err, env={}, clock=clock)


def rows(proj, sql="SELECT * FROM title_candidates ORDER BY id"):
    c = sqlite3.connect(proj / "data" / "ytitle.sqlite3")
    c.row_factory = sqlite3.Row
    r = c.execute(sql).fetchall()
    c.close()
    return r


def test_validate_file_report_screen(proj, streams):
    """TC-344: `validate --file`이 SCR-002 형식(영상·주제·사전 버전·해시·결과 배지·사유·면책)으로 출력한다. [EVT-003, FR-005, SCR-002, POL-002]"""
    cfile(proj, titles=("겨울철 전기요금 줄이는 난방 습관", "당뇨 완치 식단"))
    assert go(proj, streams, ["validate", "--file", "candidates/abc123DEF45.json"]) == 0
    out = streams.out.getvalue()
    assert "[validate] 모드: 모의 실행(dry-run)" in out and "금칙어 사전: v1 (해시 " in out
    assert "[통과]" in out and "[차단]" in out and "의료 효능 단정 표현" in out and "설명 미사용" in out
    assert "요약: [통과] 1건  [경고] 0건  [차단] 1건" in out and out.rstrip().endswith("법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.")


def test_validate_records_status_and_dictionary_hash(proj, streams):
    """TC-345: 검증 결과가 title_candidates에 상태(filtered/blocked)·사전 해시·사유와 함께 기록된다. [SEC-017, 설계 3-2]"""
    cfile(proj, titles=("겨울철 전기요금 줄이는 난방 습관", "당뇨 완치 식단"))
    go(proj, streams, ["validate", "--file", "candidates/abc123DEF45.json"])
    r = rows(proj)
    assert [(x["status"], x["validation_result"]) for x in r] == [("filtered", "pass"), ("blocked", "block")]
    assert all(len(x["dictionary_hash"]) == 8 and x["file_sha256"] and x["source"] == "human" for x in r)
    assert "BANNED_MEDICAL" in json.loads(r[1]["validation_reasons_json"])[0][0]


def test_rerun_does_not_duplicate_rows(proj, streams):
    """TC-346: 같은 파일을 다시 검증해도 행이 중복되지 않고 갱신된다. [FR-005]"""
    cfile(proj)
    for _ in range(2):
        go(proj, streams, ["validate", "--all"])
    assert len(rows(proj)) == 1


def test_changed_file_creates_new_rows(proj, streams):
    """TC-347: 파일 내용이 바뀌면(해시가 다르면) 새 후보로 기록해 이력이 남는다. [FR-005]"""
    cfile(proj)
    go(proj, streams, ["validate", "--all"])
    cfile(proj, summary=SUMMARY + " 추가 설명")
    go(proj, streams, ["validate", "--all"])
    assert len(rows(proj)) == 2


def test_approved_rows_are_not_reset_by_revalidation(proj, streams):
    """TC-348: 이미 승인(approved) 이후 단계인 후보는 재검증해도 상태·결과가 바뀌지 않는다(상태 머신 보호). [설계 3-2, SEC-006]"""
    cfile(proj)
    go(proj, streams, ["validate", "--all"])
    c = sqlite3.connect(proj / "data" / "ytitle.sqlite3")
    c.execute("UPDATE title_candidates SET status='approved'")
    c.commit()
    c.close()
    go(proj, streams, ["validate", "--all"])
    r = rows(proj)
    assert len(r) == 1 and r[0]["status"] == "approved"


def test_all_processes_every_file_and_summarizes(proj, streams):
    """TC-349: `--all`은 candidates 폴더의 모든 파일을 검사하고 합계를 보여 준다. [EVT-003]"""
    cfile(proj, vid="aaaaaaaaaaa")
    cfile(proj, vid="bbbbbbbbbbb", titles=("무조건 수익 나는 적금",))
    assert go(proj, streams, ["validate", "--all"]) == 0
    assert "요약: [통과] 1건  [경고] 0건  [차단] 1건" in streams.out.getvalue() and len(rows(proj)) == 2


def test_empty_folder_guides_user(proj, streams):
    """TC-350: 후보 파일이 없으면 만드는 방법을 안내하고 정상 종료한다(빈 상태). [SCR-002, NFR-007]"""
    assert go(proj, streams, ["validate", "--all"]) == 0
    assert "검사할 후보 파일이 없습니다" in streams.out.getvalue() and rows(proj) == []


def test_no_option_is_input_error(proj, streams):
    """TC-351: 옵션 없이 실행하면 사용법을 안내하는 오류(종료 코드 1)이다. [NFR-007]"""
    assert go(proj, streams, ["validate"]) == 1
    assert "validate --all" in streams.err.getvalue()


def test_file_outside_folder_rejected_without_db_write(proj, streams, tmp_path):
    """TC-352: candidates 밖의 파일은 종료 코드 1로 거부되고 DB에 아무것도 기록하지 않는다. [SEC-011]"""
    p = cfile(proj)
    outside = tmp_path / "abc123DEF45.json"
    shutil.copy(p, outside)
    assert go(proj, streams, ["validate", "--file", str(outside)]) == 1
    assert "candidates 폴더" in streams.err.getvalue() and rows(proj) == []


def test_invalid_file_stops_with_field_message(proj, streams):
    """TC-353: 필드 오류가 있는 파일은 어느 항목이 문제인지 알려 주고 아무것도 기록하지 않는다. [FR-001, NFR-007]"""
    cfile(proj, summary="")
    assert go(proj, streams, ["validate", "--all"]) == 1
    assert "summary" in streams.err.getvalue() and rows(proj) == []


def test_strict_banner_and_block_for_health(proj, streams):
    """TC-354: 건강 주제는 '엄격 모드' 안내가 나오고 경고급 문제도 차단된다. [POL-001, SCR-002]"""
    cfile(proj, topic="health", summary="겨울철 혈압 관리를 위한 걷기 습관을 설명합니다", titles=("겨울철 혈압 관리 걷기 습관!!",))
    go(proj, streams, ["validate", "--all"])
    out = streams.out.getvalue()
    assert "엄격 모드: 경고도 차단으로 처리합니다" in out and "[차단]" in out
    assert rows(proj)[0]["strict_mode"] == 1 and rows(proj)[0]["status"] == "blocked"


def test_description_from_videos_table_is_used(proj, streams):
    """TC-355: 후보 파일에 설명이 없으면 DB videos 테이블의 설명(WU-2가 채움)을 사용하고, 없으면 '설명 미사용'이다. [FR-004]"""
    cfile(proj, titles=("보일러 온도 낮추는 습관",))
    go(proj, streams, ["validate", "--all"])
    assert "설명 미사용" in streams.out.getvalue()
    c = sqlite3.connect(proj / "data" / "ytitle.sqlite3")
    c.execute("INSERT INTO videos (video_id,title,snippet_json,fetched_at,description_excerpt) VALUES ('abc123DEF45','x','{}','t','보일러 온도를 낮추는 습관을 보여줍니다')")
    c.commit()
    c.close()
    streams.out.truncate(0), streams.out.seek(0)
    go(proj, streams, ["validate", "--all"])
    assert "영상 설명: 사용함" in streams.out.getvalue()


def test_excerpt_in_file_takes_priority_over_db(proj, streams):
    """TC-356: 후보 파일의 description_excerpt가 있으면 그것을 우선 사용한다. [FR-004, EVT-201]"""
    cfile(proj, description_excerpt="보일러 온도를 낮추는 장면이 나옵니다")
    go(proj, streams, ["validate", "--all"])
    assert "영상 설명: 사용함" in streams.out.getvalue()


def test_plain_mode_for_screen_readers(proj, streams):
    """TC-357: `--plain`은 표 대신 항목: 값 목록으로 출력한다(스크린리더 친화). [UX-002, SCR-002]"""
    cfile(proj)
    go(proj, streams, ["validate", "--all", "--plain"])
    out = streams.out.getvalue()
    assert "제목: 겨울철 전기요금 줄이는 난방 습관" in out and "후보번호:" in out and "------" not in out


def test_external_strings_are_sanitized_in_report(proj, streams):
    """TC-358: 제목에 숨긴 ANSI 이스케이프가 리포트 화면에 그대로 나오지 않는다. [SEC-019, T-13]"""
    cfile(proj, titles=("\x1b[2J겨울철 전기요금 줄이는 난방 습관",), current_title="\x1b[31m빨강")
    go(proj, streams, ["validate", "--all"])
    assert "\x1b" not in streams.out.getvalue()


def test_no_write_api_or_network_in_modules():
    """TC-359: 후보 입력·검증 모듈에는 네트워크·YouTube 쓰기 호출 코드가 없다. [SEC-001, SEC-007]"""
    src = Path(__file__).resolve().parent.parent / "src" / "ytitle"
    for name in ("candidates.py", "banned_terms.py", "validator.py", "commands/validate.py"):
        text = (src / name).read_text(encoding="utf-8")
        for bad in ("googleapiclient", "requests", "urllib", "socket", "videos().update", ".update(body"):
            assert bad not in text, (name, bad)
