"""터미널 출력 컴포넌트(04_ux_design.md). 상태는 기호+글자로 표시해 색에 의존하지 않는다."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from youtube_title.errors import YtError
from youtube_title.textsafe import display_width, pad_display, sanitize_for_display, truncate_display

DISCLAIMER = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."
BADGES = {"pass": "[통과]", "warn": "[경고]", "block": "[차단]", "caution": "[주의]", "done": "[완료]", "fail": "[실패]"}
_COLORS = {"pass": "32", "done": "32", "warn": "33", "caution": "33", "block": "31", "fail": "31"}


@dataclass(frozen=True)
class UiOptions:
    plain: bool = False
    color: bool = False
    width: int = 80


def badge(kind: str, opts: UiOptions = UiOptions()) -> str:
    text = BADGES[kind]
    if opts.color and kind in _COLORS:
        return f"\x1b[{_COLORS[kind]}m{text}\x1b[0m"
    return text


def title_line(command: str, live: bool) -> str:
    mode = "★실제 적용(LIVE)★" if live else "모의 실행(dry-run)"
    return f"[{command}] 모드: {mode}"


def footer() -> str:
    return DISCLAIMER


def render_table(headers: Sequence[str], rows: Sequence[Sequence[object]], opts: UiOptions = UiOptions()) -> str:
    """한글 폭을 반영해 정렬한다. plain 모드에서는 `항목: 값` 목록으로 출력한다."""
    clean = [[sanitize_for_display(c) for c in r] for r in rows]
    if opts.plain:
        lines: list[str] = []
        for i, r in enumerate(clean, 1):
            lines.append(f"- 항목 {i}")
            lines.extend(f"  {h}: {c}" for h, c in zip(headers, r))
        return "\n".join(lines)
    cols = len(headers)
    widths = [max([display_width(headers[i])] + [display_width(r[i]) for r in clean]) for i in range(cols)]
    sep = 2
    while sum(widths) + sep * (cols - 1) > opts.width and max(widths) > 8:
        widths[widths.index(max(widths))] -= 1
    def line(cells: Sequence[str]) -> str:
        return (" " * sep).join(pad_display(truncate_display(c, w), w) for c, w in zip(cells, widths)).rstrip()
    out = [line(list(headers)), line(["-" * w for w in widths])]
    out.extend(line(r) for r in clean)
    return "\n".join(out)


def error_block(err: YtError) -> str:
    lines = [f"[오류 {err.code}] {sanitize_for_display(err.message)}"]
    if err.cause:
        lines.append(f"원인: {sanitize_for_display(err.cause)}")
    lines.append(f"다음에 할 일: {sanitize_for_display(err.next_step) if err.next_step else '문제가 계속되면 로그(data/logs/youtube-title.log)를 확인하세요.'}")
    return "\n".join(lines)


def progress_steps(steps: Sequence[str], current: int) -> str:
    marks = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨"]
    out = []
    for i, s in enumerate(steps):
        state = "완료" if i < current else ("진행 중" if i == current else "대기")
        out.append(f"{marks[i] if i < len(marks) else i + 1} {s} ({state})")
    return "\n".join(out)


def confirm_by_typing(expected: str, *, input_fn: Callable[[str], str], output_fn: Callable[[str], None], tries: int = 3) -> bool:
    """습관적 Enter를 막기 위해 y/n이 아니라 정해진 문구를 직접 입력받는다(3회 틀리면 중단)."""
    for n in range(tries):
        try:
            answer = input_fn(f"계속하려면 '{expected}'를 그대로 입력하세요 (취소: 빈 줄) > ")
        except EOFError:
            output_fn("입력을 받을 수 없어 취소했습니다.")
            return False
        if answer.strip() == "":
            output_fn("취소했습니다.")
            return False
        if answer.strip() == expected:
            return True
        output_fn(f"입력이 일치하지 않습니다({n + 1}/{tries}).")
    output_fn("여러 번 일치하지 않아 중단했습니다.")
    return False
