"""외부 문자열(제목·설명·사유)을 안전하게 다루는 공통 함수(SEC-019, FR-002)."""
import re
import unicodedata

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
# 화면을 속이는 방향 제어 문자(RLO 등)
_BIDI = dict.fromkeys(list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)))


def sanitize_for_display(text: object, max_len: int | None = None) -> str:
    """제어 문자·ANSI 이스케이프·방향 제어 문자를 제거한다. 줄바꿈은 공백으로 바꾼다."""
    s = "" if text is None else str(text)
    s = _ANSI.sub("", s)
    s = s.translate(_BIDI)
    s = "".join(" " if ch in "\r\n\t" else ch for ch in s if ch in "\r\n\t" or unicodedata.category(ch) != "Cc")
    if max_len is not None and len(s) > max_len:
        s = s[: max(0, max_len - 1)] + "…"
    return s


def char_count(text: str) -> int:
    """유니코드 문자 수(NFC 정규화 후 코드 포인트 수). 이모지 조합은 여러 개로 세어 보수적이다."""
    return len(unicodedata.normalize("NFC", text))


def normalize_for_match(text: str) -> str:
    """금칙어 매칭용 정규화: NFKC, 소문자화, 문자·숫자만 남김(공백·기호·제로폭 문자 제거)."""
    s = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in s if unicodedata.category(ch)[0] in ("L", "N"))


def display_width(text: str) -> int:
    """터미널 표시 폭. 한글·전각은 2칸, 결합 문자는 0칸."""
    w = 0
    for ch in text:
        if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def truncate_display(text: str, width: int) -> str:
    if display_width(text) <= width:
        return text
    out, w = [], 0
    for ch in text:
        cw = display_width(ch)
        if w + cw > width - 1:
            break
        out.append(ch)
        w += cw
    return "".join(out) + "…"


def pad_display(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))
