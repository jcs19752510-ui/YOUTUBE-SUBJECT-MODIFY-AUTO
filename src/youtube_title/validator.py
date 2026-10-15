"""제목 후보 검증기(FR-002, FR-004, FR-005, POL-001). 순수 함수 중심이라 네트워크·DB 없이 테스트한다."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from youtube_title.banned_terms import Dictionary
from youtube_title.candidates import CandidateFile
from youtube_title.config import Settings
from youtube_title.textsafe import char_count, normalize_for_match

_TOKEN = re.compile(r"[가-힣A-Za-z0-9]+")
_PARTICLES = ("에서는", "으로는", "에서", "으로", "에게", "까지", "부터", "처럼", "보다", "입니다", "합니다", "하는", "하기", "하면", "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만", "들")
_STOP = {"방법", "가지", "소개", "정리", "추천", "꿀팁", "비법", "이유", "모든", "정말", "이렇게", "알아보", "알려드립니다", "하는법"}
_SYMBOL_RUN = re.compile(r"([!！?？~～★☆♥♡])\1{2,}|[!！?？]{3,}")
EMOJI_RANGES = ((0x1F300, 0x1FAFF), (0x2600, 0x27BF), (0x1F000, 0x1F2FF))


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str            # "block" | "warn"
    message: str


@dataclass(frozen=True)
class CandidateResult:
    title: str
    length: int
    result: str              # "pass" | "warn" | "block"
    findings: tuple[Finding, ...]
    match_ratio: float | None
    evidence_found: bool
    strict: bool


@dataclass(frozen=True)
class FileResult:
    video_id: str
    topic: str | None
    strict: bool
    strict_reasons: tuple[str, ...]
    description_used: bool
    dictionary_version: str
    dictionary_hash: str
    results: tuple[CandidateResult, ...] = field(default_factory=tuple)


def _strip_particle(tok: str) -> str:
    for p in sorted(_PARTICLES, key=len, reverse=True):
        if tok.endswith(p) and len(tok) - len(p) >= 2:
            return tok[: -len(p)]
    return tok


def tokens(text: str) -> list[str]:
    """비교용 핵심 낱말: 2글자 이상, 숫자 포함 낱말 제외, 조사 제거, 일반어 제외."""
    out = []
    for t in _TOKEN.findall(unicodedata.normalize("NFKC", text)):
        if any(ch.isdigit() for ch in t):
            continue
        t = _strip_particle(t)
        if len(t) >= 2 and t not in _STOP:
            out.append(t)
    return out


def key_terms(reference: str, limit: int = 5) -> list[str]:
    c = Counter(tokens(reference))
    order = {t: i for i, t in enumerate(dict.fromkeys(tokens(reference)))}
    return [t for t, _ in sorted(c.items(), key=lambda kv: (-kv[1], order[kv[0]]))[:limit]]


def match_ratio(title: str, reference: str) -> float | None:
    toks = list(dict.fromkeys(tokens(title)))
    if not toks:
        return None
    ref = normalize_for_match(reference)
    hit = sum(1 for t in toks if normalize_for_match(t) in ref)
    return hit / len(toks)


def count_emoji(text: str) -> int:
    return sum(1 for ch in text if any(lo <= ord(ch) <= hi for lo, hi in EMOJI_RANGES))


def detect_strict(cf: CandidateFile, dictionary: Dictionary) -> tuple[bool, tuple[str, ...]]:
    """건강·금융 주제는 엄격 모드(POL-001). topic 미지정이거나 키워드가 보이면 topic과 무관하게 올린다."""
    reasons = []
    if cf.topic in ("health", "finance"):
        reasons.append(f"주제가 {'건강' if cf.topic == 'health' else '금융'}으로 지정됨")
    if cf.topic is None:
        reasons.append("주제 미지정(보수적으로 엄격 모드)")
    hay = normalize_for_match(" ".join([cf.current_title, cf.summary] + [c.title for c in cf.candidates]))
    for raw, norm in dictionary.strict_keywords:
        if norm in hay:
            reasons.append(f"건강·금융 관련 낱말 감지: {raw}")
            break
    return bool(reasons), tuple(reasons)


def _check_title(title: str, cf: CandidateFile, evidence: str, dictionary: Dictionary, s: Settings, reference: str, strict: bool) -> CandidateResult:
    f: list[Finding] = []
    n = char_count(title)
    if not title.strip():
        f.append(Finding("EMPTY", "block", "제목이 비어 있습니다."))
    if any(unicodedata.category(ch) == "Cc" for ch in title):
        f.append(Finding("CHAR_CONTROL", "block", "제목에 줄바꿈·제어 문자가 들어 있습니다."))
    if "<" in title or ">" in title:
        f.append(Finding("CHAR_FORBIDDEN", "block", "제목에는 < 또는 > 를 쓸 수 없습니다(YouTube 규격)."))
    if n > s.hard_max_chars:
        f.append(Finding("LEN_HARD", "block", f"제목이 {n}자로 상한({s.hard_max_chars}자)을 넘습니다."))
    elif n > s.recommended_max_chars:
        f.append(Finding("LEN_REC", "warn", f"제목이 {n}자로 권장 길이({s.recommended_max_chars}자)를 넘습니다."))
    norm_title = normalize_for_match(title)
    for tt in dictionary.types:
        sev = tt.severity
        hit = next((raw for raw, norm in tt.terms if norm in norm_title), None)
        if hit is None:
            hit = next((m.group(0) for p in tt.patterns if (m := p.search(unicodedata.normalize("NFKC", title)))), None)
        if hit is not None:
            f.append(Finding(f"BANNED_{tt.name.upper()}", sev, f"{tt.label} 표현이 있습니다: '{hit}'"))
    w = dictionary.warning
    excl = title.count("!") + title.count("！")
    if excl > w["exclamation_max"]:
        f.append(Finding("EXCLAMATION", "warn", f"느낌표가 {excl}개입니다(최대 {w['exclamation_max']}개)."))
    emo = count_emoji(title)
    if emo > w["emoji_max"]:
        f.append(Finding("EMOJI", "warn", f"이모지가 {emo}개입니다(최대 {w['emoji_max']}개)."))
    if _SYMBOL_RUN.search(title):
        f.append(Finding("SYMBOL_RUN", "warn", "같은 기호가 3번 이상 이어집니다."))
    letters = [c for c in title if c.isascii() and c.isalpha()]
    if len(letters) >= 4 and sum(c.isupper() for c in letters) / len(letters) > w["caps_ratio_max"]:
        f.append(Finding("CAPS", "warn", "영문 대문자 비율이 높습니다."))
    visible = [c for c in title if not c.isspace()]
    if visible and sum(1 for c in visible if not (c.isalnum())) / len(visible) > w["special_ratio_max"]:
        f.append(Finding("SPECIAL_RATIO", "warn", "기호 비율이 높습니다."))
    if title.strip() and title.strip() == cf.current_title.strip():
        f.append(Finding("SAME_AS_CURRENT", "warn", "현재 제목과 같습니다."))
    ratio = match_ratio(title, reference)
    if ratio is None:
        f.append(Finding("MATCH_UNKNOWN", "warn", "제목에서 비교할 낱말을 찾지 못해 영상과의 일치율을 계산하지 못했습니다."))
    elif ratio < s.block_match_ratio:
        f.append(Finding("MATCH_LOW", "block", f"영상 요약·설명과 일치율이 {ratio:.0%}로 매우 낮습니다(기준 {s.block_match_ratio:.0%} 미만)."))
    elif ratio < s.warn_match_ratio:
        f.append(Finding("MATCH_WEAK", "warn", f"영상 요약·설명과 일치율이 {ratio:.0%}로 약합니다(기준 {s.warn_match_ratio:.0%})."))
    evidence_found = bool(evidence.strip()) and normalize_for_match(evidence) in normalize_for_match(reference)
    if not evidence_found:
        f.append(Finding("EVIDENCE_NOT_FOUND", "warn", "일치 근거 문장이 영상 요약·설명에서 확인되지 않습니다."))
    terms = key_terms(reference)
    head = normalize_for_match(title[: s.key_phrase_chars])
    if terms and not any(normalize_for_match(t) in head for t in terms):
        f.append(Finding("KEY_LATE", "warn", f"영상의 핵심어가 제목 앞 {s.key_phrase_chars}자 안에 없습니다."))
    if strict:
        f = [Finding(x.code, "block", x.message + (" (엄격 모드: 경고를 차단으로 처리)" if x.severity == "warn" else "")) if x.severity == "warn" else x for x in f]
    result = "block" if any(x.severity == "block" for x in f) else ("warn" if f else "pass")
    return CandidateResult(title, n, result, tuple(f), ratio, evidence_found, strict)


def validate_file(cf: CandidateFile, dictionary: Dictionary, settings: Settings, *, description: str | None = None) -> FileResult:
    """후보 파일 하나를 검증한다. description은 후보 파일의 description_excerpt나 DB의 설명(없으면 None)."""
    desc = description if description is not None else cf.description_excerpt
    reference = " ".join(x for x in (cf.summary, desc) if x)
    strict, reasons = detect_strict(cf, dictionary)
    results = tuple(_check_title(c.title, cf, c.evidence, dictionary, settings, reference, strict) for c in cf.candidates)
    return FileResult(cf.video_id, cf.topic, strict, reasons, desc is not None, dictionary.version, dictionary.short_hash, results)
