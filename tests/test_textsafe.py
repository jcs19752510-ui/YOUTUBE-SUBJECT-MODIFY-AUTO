import pytest

from ytitle.textsafe import char_count, display_width, normalize_for_match, pad_display, sanitize_for_display, truncate_display


def test_sanitize_strips_ansi_and_control_chars():
    """TC-034: ANSI 이스케이프·제어 문자가 제거되어 화면을 속일 수 없다. [SEC-019]"""
    assert sanitize_for_display("\x1b[31m빨강\x1b[0m제목\x07") == "빨강제목"
    assert sanitize_for_display("\x1b]0;창제목\x07본문") == "본문"
    assert sanitize_for_display("줄1\n줄2\r\n줄3\t끝") == "줄1 줄2  줄3 끝"


def test_sanitize_removes_bidi_override_and_handles_none():
    """TC-035: 방향 제어 문자(RLO 등)를 제거하고 None도 안전하게 처리한다. [SEC-019]"""
    assert sanitize_for_display("abc‮def") == "abcdef"
    assert sanitize_for_display(None) == ""
    assert sanitize_for_display(123) == "123"


def test_sanitize_truncates_with_ellipsis():
    """TC-036: 길이 제한 시 말줄임표로 줄인다. [NFR-007]"""
    assert sanitize_for_display("가나다라마", max_len=3) == "가나…"
    assert sanitize_for_display("가나", max_len=3) == "가나"


@pytest.mark.parametrize("text,n", [("", 0), ("겨울철 전기요금", 8), ("é", 1), ("é", 1), ("😀", 1), ("a" * 100, 100)])
def test_char_count_is_unicode_code_points(text, n):
    """TC-037: 글자 수는 유니코드 문자 기준(NFC)이며 한글·결합 문자가 올바르다. [FR-002]"""
    assert char_count(text) == n


@pytest.mark.parametrize("raw", ["완 치", "완-치", "완·치!", "완　치", "ＷＨＯ", "특 효", "특*효"])
def test_normalize_defeats_evasion(raw):
    """TC-038: 띄어쓰기·기호·전각 문자로 숨긴 표기도 같은 형태로 정규화된다. [FR-003, 우회 표기]"""
    assert normalize_for_match(raw) in ("완치", "who", "특효")


def test_normalize_keeps_letters_digits_only():
    """TC-039: 정규화 결과는 문자·숫자만 남고 소문자이다(제로폭 문자 포함 제거). [FR-003]"""
    assert normalize_for_match("A​B 1-2") == "ab12"
    assert normalize_for_match("!!!") == ""


def test_display_width_counts_hangul_as_two():
    """TC-040: 한글·전각은 2칸, 영문·숫자는 1칸, 결합 문자는 0칸으로 센다. [SCR-002, NFR-002]"""
    assert display_width("가") == 2 and display_width("a") == 1 and display_width("é") == 1
    assert pad_display("가", 4) == "가  "
    assert display_width(truncate_display("가나다라마바", 7)) <= 7
    assert truncate_display("abc", 5) == "abc"
