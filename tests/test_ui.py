from ytitle.errors import QuotaError, YtError
from ytitle.textsafe import display_width
from ytitle.ui import BADGES, DISCLAIMER, UiOptions, badge, confirm_by_typing, error_block, footer, progress_steps, render_table, title_line


def test_status_badges_are_symbol_plus_text_and_color_optional():
    """TC-041: 상태 배지는 기호+글자이며 색을 꺼도 구분되고, 색을 켜도 글자는 유지된다. [SCR-002, UX-002]"""
    assert {badge(k) for k in BADGES} == set(BADGES.values())
    colored = badge("block", UiOptions(color=True))
    assert "\x1b[" in colored and "[차단]" in colored
    assert "\x1b[" not in badge("block")


def test_title_line_marks_live_clearly():
    """TC-042: 제목 줄이 모의 실행과 실제 적용(LIVE)을 눈에 띄게 구분한다. [UX, SEC-001]"""
    assert "모의 실행(dry-run)" in title_line("plan", False)
    assert "★실제 적용(LIVE)★" in title_line("apply", True)


def test_table_aligns_korean_columns_within_width():
    """TC-043: 한글이 섞인 표가 80열 안에서 열 경계가 맞게 정렬된다. [SCR-002, NFR-002]"""
    out = render_table(["번호", "제목", "결과"], [[1, "전기요금 줄이는 난방 습관 다섯 가지를 알려드립니다 정말로 길게 쓴 제목", "[통과]"], [2, "짧은 제목", "[차단]"]], UiOptions(width=60))
    lines = out.split("\n")
    assert all(display_width(l) <= 60 for l in lines)
    assert "…" in lines[2]
    col = lambda line, mark: display_width(line[: line.index(mark)])
    assert col(lines[2], "[통과]") == col(lines[3], "[차단]") == col(lines[0], "결과")


def test_plain_mode_lists_items_instead_of_table():
    """TC-044: --plain 모드는 표 대신 `항목: 값` 목록으로 출력한다. [SCR-002, UX-002]"""
    out = render_table(["번호", "제목"], [[1, "가나다"]], UiOptions(plain=True))
    assert "번호: 1" in out and "제목: 가나다" in out and "---" not in out


def test_table_sanitizes_external_strings():
    """TC-045: 표에 들어가는 외부 문자열의 제어 문자가 제거된다(승인 요약 위조 방지). [SEC-019]"""
    out = render_table(["제목"], [["\x1b[2J가짜 화면\x1b[0m"]])
    assert "\x1b" not in out and "가짜 화면" in out


def test_error_block_has_what_why_next():
    """TC-046: 오류 블록은 코드·원인·다음에 할 일을 담고 비어 있어도 기본 안내를 준다. [NFR-007]"""
    out = error_block(QuotaError("오늘 사용량을 넘었습니다.", "내일 다시 시도하세요.", cause="한도 초과"))
    assert "YT-300" in out and "원인: 한도 초과" in out and "다음에 할 일: 내일 다시 시도하세요." in out
    assert "로그" in error_block(YtError("알 수 없음"))


def test_confirm_accepts_exact_text_only():
    """TC-047: 확인 문구를 정확히 입력해야 통과하고, 3번 틀리면 중단한다. [SEC-001, 습관적 Enter 방지]"""
    said = []
    assert confirm_by_typing("abc123DEF45", input_fn=lambda p: "abc123DEF45", output_fn=said.append) is True
    answers = iter(["x", "y", "z"])
    assert confirm_by_typing("abc123DEF45", input_fn=lambda p: next(answers), output_fn=said.append) is False
    assert any("중단" in s for s in said)


def test_confirm_cancel_on_blank_and_eof():
    """TC-048: 빈 줄이나 입력 불가(EOF)는 취소로 처리한다. [SEC-001]"""
    said = []
    assert confirm_by_typing("삭제", input_fn=lambda p: "  ", output_fn=said.append) is False

    def eof(_):
        raise EOFError

    assert confirm_by_typing("삭제", input_fn=eof, output_fn=said.append) is False


def test_footer_and_progress():
    """TC-049: 면책 문구가 고정되어 있고 진행 표시가 단계 상태를 보여 준다. [POL-002]"""
    assert footer() == DISCLAIMER and "법률 자문이 아니며" in footer()
    p = progress_steps(["백업", "호출", "검증"], 1)
    assert "① 백업 (완료)" in p and "② 호출 (진행 중)" in p and "③ 검증 (대기)" in p
