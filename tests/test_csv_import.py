import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ytitle import csv_import as ci
from ytitle import db
from ytitle.errors import DatabaseError, InputError

NOW = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
V1, V2, V3 = "abc123DEF45", "bbbbbbbbbbb", "ccccccccccc"

EN = (
    "Content,Video title,Video publish time,Duration,Views,Watch time (hours),Subscribers,Impressions,Impressions click-through rate (%)\n"
    f'Total,,,,"9,999",10.5,3,"120,000",4.1\n'
    f'{V1},겨울철 전기요금,"Jan 1, 2026",600,"1,234",2.5,1,"30,000",3.2%\n'
)
KO = (
    "콘텐츠,동영상 제목,조회수,시청 시간(단위: 시간),노출수,노출 클릭률(%)\n"
    f'{V1},겨울철 전기요금,"1,234",2.5,"30,000",3.2%\n'
)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.migrate(c)
    yield c
    c.close()


def parse(text, **kw):
    return ci.parse_csv_bytes(text.encode("utf-8"), **kw)


def test_english_studio_headers_are_recognized():
    """TC-600: 영문 Studio 머리글(Content/Views/Watch time (hours)/Impressions/CTR)을 인식하고 합계 행·모르는 열은 건너뛰며 시간은 분으로 바꾼다. [FR-007, EVT-203]"""
    r = parse(EN)
    assert len(r.rows) == 1 and r.data_rows == 2
    row = r.rows[0]
    assert (row.video_id, row.views, row.impressions, row.ctr, row.watch_minutes) == (V1, 1234, 30000, 3.2, 150.0)
    assert set(r.columns) == {"video_id", "views", "watch_hours", "impressions", "ctr"}
    assert "Video title" in r.ignored_columns and "Subscribers" in r.ignored_columns
    assert [(i.line, i.reason) for i in r.issues] == [(2, "합계 행이라 건너뜀")]


def test_korean_studio_headers_are_recognized():
    """TC-601: 한글 머리글(콘텐츠/조회수/시청 시간(단위: 시간)/노출수/노출 클릭률(%))을 인식한다. [FR-007, EVT-203]"""
    r = parse(KO)
    assert [(x.video_id, x.views, x.impressions, x.ctr, x.watch_minutes) for x in r.rows] == [(V1, 1234, 30000, 3.2, 150.0)]
    assert r.issues == []


@pytest.mark.parametrize("header", ["Video ID,Impressions", "VIDEO_ID , impressions", "동영상 ID,노출 수", "영상 ID,노출", "video,Impressions", "content,IMPRESSIONS"])
def test_header_alias_spelling_variants(header):
    """TC-602: 대소문자·공백·밑줄 같은 표기 차이가 있어도 별칭으로 인식한다. [EVT-203]"""
    r = parse(f"{header}\n{V1},1000\n")
    assert [(x.video_id, x.impressions) for x in r.rows] == [(V1, 1000)]


@pytest.mark.parametrize("ctr_header", ["CTR", "Click-through rate", "Impressions click-through rate (%)", "노출 클릭률(%)", "노출 클릭률", "클릭률"])
def test_ctr_header_aliases(ctr_header):
    """TC-685: 클릭률 열의 한글/영문 별칭을 모두 인식한다. [EVT-203]"""
    assert parse(f"콘텐츠,{ctr_header}\n {V1} ,2.5%\n").rows[0].ctr == 2.5  # 영상 ID 앞뒤 공백도 허용


def test_minutes_header_preferred_over_hours():
    """TC-603: 분 단위 열과 시간 단위 열이 함께 있으면 분 단위를 쓰고 시간 열은 무시한다(단위를 추측하지 않음). [FR-007]"""
    r = parse(f"Content,Watch time (minutes),Watch time (hours),Views\n{V1},90,1.5,10\n")
    assert r.rows[0].watch_minutes == 90.0 and "Watch time (hours)" in r.ignored_columns


def test_bare_watch_time_column_is_not_guessed():
    """TC-604: 단위를 알 수 없는 `시청 시간` 단독 열은 추측하지 않고 무시한다. [FR-007, 규칙 A]"""
    r = parse(f"콘텐츠,시청 시간,조회수\n{V1},99,10\n")
    assert r.rows[0].watch_minutes is None and "시청 시간" in r.ignored_columns


def test_utf8_bom_is_accepted():
    """TC-605: UTF-8 BOM(utf-8-sig)이 붙은 파일도 머리글을 올바르게 읽는다. [NFR-002, EVT-203]"""
    r = ci.parse_csv_bytes(b"\xef\xbb\xbf" + KO.encode("utf-8"))
    assert r.encoding == "utf-8" and r.columns["video_id"] == "콘텐츠" and len(r.rows) == 1


def test_cp949_and_utf16_files_are_accepted():
    """TC-606: 엑셀 한글 저장(CP949)과 UTF-16(BOM) 파일도 읽는다. [NFR-002, DESIGN 9장 WU-6]"""
    r = ci.parse_csv_bytes(KO.encode("cp949"))
    assert r.encoding == "cp949" and len(r.rows) == 1 and r.rows[0].views == 1234
    r = ci.parse_csv_bytes(KO.encode("utf-16"))
    assert r.encoding == "utf-16" and len(r.rows) == 1


def test_undecodable_and_binary_files_rejected():
    """TC-607: 인코딩을 알 수 없거나 바이너리인 파일은 안내와 함께 거부한다. [SEC-016, T-11]"""
    with pytest.raises(InputError, match="인코딩"):
        ci.parse_csv_bytes(b"\x81\x20\xfd\xfc")  # UTF-8도 CP949도 아님
    with pytest.raises(InputError, match="바이너리"):
        ci.parse_csv_bytes(b"PK\x03\x04\x00\x00abc")
    with pytest.raises(InputError, match="UTF-16"):
        ci.parse_csv_bytes(b"\xff\xfe\x00")  # 홀수 바이트의 깨진 UTF-16


@pytest.mark.parametrize(
    "text,kind,expected",
    [
        ("1,234", "int", 1234), ("1234", "int", 1234), ("0", "int", 0), ("1000000000000", "int", 10**12), ("1000000000", "float", 1e9), ("1,234,567", "int", 1234567),
        ("3.2%", "percent", 3.2), ("3.2 %", "percent", 3.2), ("3.2", "percent", 3.2), ("100%", "percent", 100.0), ("0%", "percent", 0.0),
        ("2.5", "float", 2.5), ("1,000.25", "float", 1000.25), (" 1,000 ", "int", 1000),
        ("", "int", None), ("-", "int", None), ("N/A", "float", None), ("null", "percent", None), ("—", "int", None),
    ],
)
def test_parse_number_accepts_common_formats(text, kind, expected):
    """TC-608: 쉼표 천단위·퍼센트·빈 값 표기(-, N/A)를 올바르게 읽는다. [FR-007]"""
    assert ci.parse_number(text, kind) == (expected, "")


@pytest.mark.parametrize(
    "text,kind,why",
    [
        ("=1+1", "int", "수식"), ("+5", "int", "수식"), ("-5", "int", "수식"), ("@SUM(A1)", "float", "수식"),
        ("1e5", "float", "숫자 형식"), ("NaN", "float", "숫자 형식"), ("inf", "float", "숫자 형식"), ("0x10", "int", "숫자 형식"),
        ("1,23", "int", "숫자 형식"), ("1.5", "int", "정수"), ("5%", "int", "숫자 형식"), ("abc", "float", "숫자 형식"), ("٣", "int", "숫자 형식"),
        ("100.5%", "percent", "100%"), ("1,000,000,000,001", "int", "너무 큽니다"), ("1000000000001", "int", "너무 큽니다"), ("1000000001", "float", "너무 큽니다"),
    ],
)
def test_parse_number_rejects_formulas_and_garbage(text, kind, why):
    """TC-609: 수식처럼 보이는 값·지수 표기·NaN·무한대·범위 밖 값은 읽지 않고 이유를 돌려준다. [SEC-016, T-11]"""
    value, reason = ci.parse_number(text, kind)
    assert value is None and why in reason


def test_bad_rows_are_skipped_and_reported_together():
    """TC-610: 불량 행(영상 ID 형식·숫자 형식·열 개수·지표 없음·중복)은 건너뛰고 이유를 모아 알리며 정상 행은 계속 읽는다. [FR-007, 규칙 B]"""
    text = (
        "Content,Views,Impressions,CTR\n"
        f"{V1},10,1000,1.5%\n"          # 2: 정상
        "short,10,1000,1.5%\n"          # 3: ID 형식
        f"{V2},abc,1000,1.5%\n"         # 4: 숫자 형식
        f"{V2},10,1000\n"               # 5: 열 개수
        f"{V3},,,\n"                    # 6: 지표 없음
        f"{V1},99,9999,2%\n"            # 7: 중복
        "\n"                            # 빈 줄은 세지 않음
        f"{V2},20,2000,200%\n"          # 9: 클릭률 100% 초과
        f"{V3},30,3000,2%\n"            # 정상
        f"{V2},1,1,1%,extra\n"          # 11: 열이 머리글보다 많음
    )
    r = parse(text)
    assert [x.video_id for x in r.rows] == [V1, V3] and r.data_rows == 9
    assert [(i.line, i.reason) for i in r.issues] == [
        (3, "영상 ID 형식이 올바르지 않습니다"), (4, "Views 값: 숫자 형식이 아닙니다"), (5, "열 개수가 머리글과 다릅니다"), (6, "지표 값이 하나도 없습니다"),
        (7, "같은 영상이 파일에 중복되어 첫 줄만 사용합니다"), (9, "CTR 값: 클릭률이 100%를 넘습니다"), (11, "열 개수가 머리글과 다릅니다"),
    ]
    assert r.rows[0].views == 10  # 중복 행(99)이 아니라 첫 줄 값


def test_injection_strings_are_values_only_and_neutralized():
    """TC-611: `=+-@`로 시작하는 문자열은 수식으로 해석되지 않고 값으로만 남으며, 화면용 문자열은 앞에 `'`가 붙고 제어문자가 제거된다. [SEC-016, T-11, SEC-019]"""
    evil = '=HYPERLINK("http://evil/x","click")'
    text = f'Content,Video title,Views\n"{evil.replace(chr(34), chr(34) * 2)}",x,1\n{V1},"=cmd|\' /C calc\'!A0\x1b[31m",5\n+SUM(A1),y,2\n'
    r = parse(text)
    assert len(r.rows) == 1 and r.rows[0].video_id == V1 and r.rows[0].views == 5
    assert r.issues[0].detail.startswith("'=") and r.issues[1].detail.startswith("'+")
    cell = r.rows[0].raw["Video title"]
    assert cell.startswith("'=cmd") and "\x1b" not in cell  # 값으로만 저장(수식 아님), 제어문자 제거
    assert ci.neutralize_formula("=1") == "'=1" and ci.neutralize_formula("@a") == "'@a" and ci.neutralize_formula("\tx") == "'\tx"
    assert ci.neutralize_formula("abc") == "abc" and ci.neutralize_formula("") == ""
    assert ci.safe_cell("-\x1b[31m빨강\r\n", 50) == "'-빨강  "


@pytest.mark.parametrize("vid", ["a" * 10, "a" * 12])
def test_video_id_must_be_exactly_eleven_characters(vid):
    """TC-687: 영상 ID 열 값이 10자·12자이면 형식 오류로 건너뛰고(정확히 11자만 허용) 저장 대상에서 뺀다. [FR-007, SEC-016]"""
    r = parse(f"Content,Views\n{vid},10\n{V1},20\n")
    assert [x.video_id for x in r.rows] == [V1]
    assert [i.reason for i in r.issues] == ["영상 ID 형식이 올바르지 않습니다"]


def test_read_is_capped_even_if_file_grows_after_size_check(tmp_path, monkeypatch):
    """TC-688: 크기 검사 뒤에 파일이 커져도 상한(5MB)+1바이트까지만 읽고 거부한다(메모리 보호). [SEC-016, NFR-002]"""
    big = tmp_path / "grow.csv"
    big.write_bytes(b"a" * (ci.MAX_BYTES + 1024 * 1024))
    real_stat = Path.stat

    class FakeStat:
        def __init__(self, st):
            self.st_mode, self.st_size = st.st_mode, 100

    monkeypatch.setattr(Path, "stat", lambda self, *a, **k: FakeStat(real_stat(self)) if self == big else real_stat(self, *a, **k))
    with pytest.raises(InputError) as exc:
        ci.read_csv_file(big, tmp_path)
    assert f"({ci.MAX_BYTES // 1024}KB > {ci.MAX_BYTES // 1024}KB)" in exc.value.message


def test_file_size_limit_rejected(tmp_path):
    """TC-612: 5MB를 넘는 CSV는 읽기 전(파일 크기)·파싱 전(바이트 수) 모두에서 거부한다. [SEC-016, T-11]"""
    big = tmp_path / "big.csv"
    big.write_bytes(b"a," * (ci.MAX_BYTES // 2 + 1))
    assert big.stat().st_size > ci.MAX_BYTES
    with pytest.raises(InputError, match="너무 큽니다"):
        ci.read_csv_file(big, tmp_path)
    with pytest.raises(InputError, match="너무 큽니다"):
        ci.parse_csv_bytes(b"x" * (ci.MAX_BYTES + 1))
    ok = tmp_path / "edge.csv"  # 딱 상한 크기는 허용
    ok.write_bytes(b"Content,Views\n" + b"\n" * (ci.MAX_BYTES - 14))
    assert ci.parse_csv_bytes(ok.read_bytes()).rows == []
    assert ok.stat().st_size == ci.MAX_BYTES and ci.read_csv_file(ok, tmp_path).rows == []


def test_file_grows_while_reading_is_still_capped(tmp_path, monkeypatch):
    """TC-613: stat 이후 파일이 커져도 읽는 양은 상한+1바이트까지만이라 상한 초과로 거부된다(검사-사용 시점 틈 방어). [SEC-016, T-11]"""
    p = tmp_path / "grow.csv"
    p.write_text("Content,Views\n", encoding="utf-8")
    real_stat = Path.stat

    class FakeStat:
        st_size = 10

        def __getattr__(self, name):
            return getattr(real_stat(p), name)

    monkeypatch.setattr(Path, "stat", lambda self, **kw: FakeStat() if self == p else real_stat(self, **kw))
    p.write_bytes(b"x" * (ci.MAX_BYTES + 10))
    with pytest.raises(InputError, match="너무 큽니다"):
        ci.read_csv_file(p, tmp_path)


def test_row_count_limit_rejected():
    """TC-614: 데이터 행이 상한(10,000)을 넘으면 거부하고, 정확히 상한이면 허용한다. [SEC-016, T-11]"""
    head = "Content,Views\n"
    lines = "".join(f"{V1},1\n" for _ in range(ci.MAX_ROWS))
    r = parse(head + lines)
    assert r.data_rows == ci.MAX_ROWS
    with pytest.raises(InputError, match="행이 너무 많습니다"):
        parse(head + lines + f"{V2},1\n")


def test_header_errors_are_reported_at_once():
    """TC-615: 머리글 문제(영상 ID 열 없음 + 지표 열 없음 + 중복 열)를 한 번에 모아 알린다. [규칙 B, NFR-007]"""
    with pytest.raises(InputError) as e:
        parse("Foo,Bar\n1,2\n")
    assert "영상 ID 열" in e.value.message and "지표 열" in e.value.message and "--video" in e.value.message
    with pytest.raises(InputError) as e:
        parse(f"Content,Views,조회수\n{V1},1,2\n")
    assert "같은 의미의 열이 둘 이상" in e.value.message and "Views" in e.value.message


def test_header_cells_with_control_chars_are_sanitized_in_errors():
    """TC-616: 오류 메시지에 들어가는 머리글 이름도 정화된다(ANSI 제거, 수식 문자 무력화). [SEC-019, T-13]"""
    with pytest.raises(InputError) as e:
        parse("\x1b[2J=Views,Views,\x1b[2J=Views\n")
    assert "\x1b" not in e.value.message and "같은 의미" not in e.value.message  # 첫 열은 별칭이 아니므로 중복이 아님
    with pytest.raises(InputError) as e:
        parse("Views,\x1b조회수\n")
    assert "\x1b" not in e.value.message and "같은 의미" in e.value.message


def test_no_id_column_requires_single_row_with_default_video():
    """TC-617: 영상 ID 열이 없는 파일은 `--video` 기본 영상으로 한 줄만 가져오고, 둘째 줄부터는 건너뛴다. [FR-007]"""
    r = parse("조회수,노출수\n10,1000\n20,2000\n", default_video_id=V1)
    assert [(x.video_id, x.views) for x in r.rows] == [(V1, 10)]
    assert "한 줄만" in r.issues[0].reason and r.issues[0].line == 3


def test_default_video_id_is_validated():
    """TC-618: 기본 영상 ID도 형식을 검증한다. [SEC-016]"""
    with pytest.raises(InputError, match="영상 ID 형식"):
        parse("조회수\n10\n", default_video_id="bad id")


@pytest.mark.parametrize("delim", [";", "\t"])
def test_other_delimiters_are_detected(delim):
    """TC-619: 세미콜론·탭으로 구분된 파일도 읽는다. [EVT-203]"""
    r = parse(delim.join(["Content", "Views"]) + "\n" + delim.join([V1, "5"]) + "\n")
    assert [(x.video_id, x.views) for x in r.rows] == [(V1, 5)]


def test_empty_and_header_only_files():
    """TC-620: 빈 파일은 거부하고, 머리글만 있는 파일은 행 0개로 정상 처리한다. [FR-007]"""
    with pytest.raises(InputError, match="비어 있습니다"):
        parse("\n \n")
    with pytest.raises(InputError, match="비어 있습니다"):
        ci.parse_csv_bytes(b"")
    r = parse("Content,Views\n")
    assert r.rows == [] and r.data_rows == 0 and r.issues == []


def test_malformed_csv_oversized_field_is_input_error():
    """TC-621: 필드 하나가 지나치게 큰 CSV는 예외 대신 한국어 안내(InputError)로 거부한다. [SEC-016, T-11]"""
    with pytest.raises(InputError, match="CSV 형식"):
        parse("Content,Views\n" + V1 + "," + "9" * 200_000 + "\n")


def test_parse_does_not_modify_input_file(tmp_path):
    """TC-622: 읽기는 입력 파일을 바꾸지 않는다(내용 해시·수정 시각 동일). [SEC-016]"""
    p = tmp_path / "in.csv"
    p.write_text(EN, encoding="utf-8")
    before = (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
    ci.read_csv_file(p, tmp_path)
    assert (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) == before


def test_read_file_resolves_relative_to_base_dir_and_checks_type(tmp_path, monkeypatch):
    """TC-623: 상대 경로는 base_dir 기준으로 읽고, .csv가 아니거나 없거나 폴더이면 안내와 함께 거부한다. [EVT-008, SEC-016]"""
    (tmp_path / "exports").mkdir()
    (tmp_path / "exports" / "a.csv").write_text(KO, encoding="utf-8")
    r = ci.read_csv_file("exports/a.csv", tmp_path)  # cwd는 임시 폴더(conftest)이므로 base_dir 기준이 아니면 실패한다
    assert len(r.rows) == 1
    assert len(ci.read_csv_file(tmp_path / "exports" / "A.CSV".lower(), tmp_path / "elsewhere").rows) == 1  # 절대 경로
    (tmp_path / "x.txt").write_text(KO, encoding="utf-8")
    with pytest.raises(InputError, match=r"\.csv"):
        ci.read_csv_file("x.txt", tmp_path)
    with pytest.raises(InputError, match="찾을 수 없습니다"):
        ci.read_csv_file("none.csv", tmp_path)
    (tmp_path / "dir.csv").mkdir()
    with pytest.raises(InputError, match="찾을 수 없습니다"):
        ci.read_csv_file("dir.csv", tmp_path)

    def boom(self, *a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "open", boom)
    with pytest.raises(InputError, match="읽을 수 없습니다") as e:
        ci.read_csv_file("exports/a.csv", tmp_path)
    assert e.value.cause == "PermissionError"


def test_store_rows_saves_csv_source_with_binding(conn):
    """TC-624: 행을 metrics_snapshots에 source='csv'로 저장하고, 악의적 문자열도 값으로만 들어가 테이블이 유지된다(SQL 바인딩). [FR-007, SEC-018, T-12]"""
    conn.execute("INSERT INTO videos (video_id,title,snippet_json,fetched_at) VALUES (?,?,?,?)", (V1, "t", "{}", "x"))
    conn.commit()
    row = ci.CsvRow(2, V1, 1000, 3.2, 50, 12.5, {"Video title": "'); DROP TABLE metrics_snapshots;--"})
    res = ci.store_rows(conn, [row], phase="before", period_start="2026-08-04", period_end="2026-08-31", now=NOW)
    assert (res.inserted, res.duplicates, res.unknown_videos) == (1, 0, 0)
    r = conn.execute("SELECT * FROM metrics_snapshots").fetchone()
    assert (r["video_id"], r["phase"], r["source"], r["period_start"], r["period_end"], r["impressions"], r["ctr"], r["views"], r["watch_minutes"]) == (V1, "before", "csv", "2026-08-04", "2026-08-31", 1000, 3.2, 50, 12.5)
    assert r["taken_at"] == "2026-10-10T12:00:00Z" and "DROP TABLE" in json.loads(r["raw_json"])["cells"]["Video title"]
    assert conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0] == 1


def test_store_rows_is_idempotent_and_counts_unknown_videos(conn):
    """TC-625: 같은 내용을 다시 가져와도 중복 저장하지 않고(NULL 값 포함), DB에 영상 정보가 없는 영상 수를 센다. [FR-007]"""
    rows = [ci.CsvRow(2, V1, 1000, None, None, None, {}), ci.CsvRow(3, V2, None, 2.0, 5, None, {})]
    kw = dict(phase="after", period_start=None, period_end=None, now=NOW)
    first = ci.store_rows(conn, rows, **kw)
    assert (first.inserted, first.duplicates, first.unknown_videos) == (2, 0, 2)
    second = ci.store_rows(conn, rows, **kw)
    assert (second.inserted, second.duplicates) == (0, 2)
    third = ci.store_rows(conn, rows, phase="before", period_start=None, period_end=None, now=NOW)  # 단계가 다르면 별개 자료
    assert third.inserted == 2 and conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0] == 4


def test_store_rows_validates_arguments_and_writes_nothing(conn):
    """TC-626: 잘못된 단계·한쪽만 있는 기간·거꾸로 된 기간은 거부하고 DB에 아무것도 쓰지 않는다. [FR-007]"""
    row = [ci.CsvRow(2, V1, 1, None, None, None, {})]
    with pytest.raises(InputError, match="단계"):
        ci.store_rows(conn, row, phase="x", period_start=None, period_end=None, now=NOW)
    with pytest.raises(InputError, match="함께"):
        ci.store_rows(conn, row, phase="before", period_start="2026-01-01", period_end=None, now=NOW)
    with pytest.raises(InputError, match="늦습니다"):
        ci.store_rows(conn, row, phase="before", period_start="2026-02-01", period_end="2026-01-01", now=NOW)
    assert conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0] == 0
    ci.store_rows(conn, row, phase="before", period_start="2026-01-01", period_end="2026-01-01", now=NOW)  # 하루짜리 기간은 허용(경계)
    assert conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0] == 1


def test_store_rows_is_atomic_on_db_error(conn):
    """TC-627: 저장 도중 DB 오류가 나면 이미 넣은 행도 취소(전부 또는 전무)하고 한국어 DatabaseError로 알린다. [FR-007, 규칙 K]"""
    conn.execute("CREATE TRIGGER boom BEFORE INSERT ON metrics_snapshots WHEN NEW.views = 99 BEGIN SELECT RAISE(ABORT, 'x'); END")
    rows = [ci.CsvRow(2, V1, 1, None, 1, None, {}), ci.CsvRow(3, V2, 1, None, 99, None, {})]
    with pytest.raises(DatabaseError, match="전부 취소"):
        ci.store_rows(conn, rows, phase="before", period_start=None, period_end=None, now=NOW)
    assert conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0] == 0


def test_parse_day_validation():
    """TC-628: 날짜는 YYYY-MM-DD만 허용하고 없는 날짜·다른 형식·유니코드 숫자는 거부한다. [NFR-007]"""
    assert ci.parse_day(" 2026-02-28 ", "시작일") == "2026-02-28"
    for bad in ("2026-02-30", "2026/01/01", "20260101", "2026-1-1", "", "٢٠٢٦-٠١-٠١"):
        with pytest.raises(InputError, match="시작일 날짜 형식"):
            ci.parse_day(bad, "시작일")


def test_module_has_no_network_or_eval():
    """TC-629: CSV 모듈에는 네트워크·코드 실행(eval/exec/pickle 등) 코드가 없다. [SEC-016, SEC-007, T-11]"""
    text = (Path(ci.__file__)).read_text(encoding="utf-8")
    for bad in ("googleapiclient", "requests", "urllib", "socket", "eval(", "exec(", "pickle", "subprocess", "os.system", "yaml.load("):
        assert bad not in text, bad
