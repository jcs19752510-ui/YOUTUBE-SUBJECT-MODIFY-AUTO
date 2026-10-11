"""AI 응답 검증(SEC-C03, LLM05)과 전송 전 마스킹(SEC-C06). 모두 순수 함수라 실서비스 어댑터에서도 그대로 쓴다.

검증기(ytitle.validator)가 내용 규칙을 판정하기 전에, 이 단계에서 형식 문제(비어 있음·너무 김·제어/방향 문자·링크/연락처·중복·개수)만 걸러낸다.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ytweb.ai.base import SuggestionDraft

MAX_TITLE_CHARS = 300      # ytitle.candidates 의 제목 길이 상한과 같다(100자 초과는 검증기가 차단 판정)
MAX_EVIDENCE_CHARS = 500
MAX_SUMMARY_CHARS = 500    # AI 로 보내는 설명 요약 상한
TOPICS = ("life", "health", "finance")

_BIDI = frozenset(chr(c) for c in list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)))
_INVISIBLE = frozenset("​‌‍‎‏⁠﻿­")
_WS = frozenset("\r\n\t  \x0b\x0c\x85")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(r"(?<!\d)0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_RRN = re.compile(r"(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)")


def clean_text(value: str, max_len: int | None = None) -> str:
    """제어 문자·방향 제어 문자·보이지 않는 문자를 없애고 줄바꿈을 공백으로 바꿔 한 줄로 만든다."""
    out: list[str] = []
    for ch in unicodedata.normalize("NFC", value):
        if ch in _WS:
            out.append(" ")
        elif ch in _BIDI or ch in _INVISIBLE or unicodedata.category(ch) == "Cc":
            continue
        else:
            out.append(ch)
    text = " ".join("".join(out).split())
    return text if max_len is None else text[:max_len]


def has_contact_or_url(text: str) -> bool:
    return bool(_URL.search(text) or _EMAIL.search(text) or _PHONE.search(text) or _RRN.search(text))


def mask_pii(text: str) -> str:
    """AI 로 보내기 전에 연락처·링크·주민번호 모양을 가린다(개인정보 최소 전송)."""
    text = _URL.sub("[링크]", text)
    text = _EMAIL.sub("[이메일]", text)
    text = _RRN.sub("[번호]", text)
    return _PHONE.sub("[전화번호]", text)


def build_summary(description: str | None) -> str:
    return mask_pii(clean_text(description or "", MAX_SUMMARY_CHARS * 2))[:MAX_SUMMARY_CHARS]


def _dedupe_key(title: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", title).casefold() if unicodedata.category(ch)[0] in ("L", "N"))


@dataclass(frozen=True)
class GuardResult:
    drafts: tuple[SuggestionDraft, ...]
    dropped: tuple[tuple[int, str], ...]  # (원래 순번, 사유 코드)


def _coerce(item: object) -> tuple[object, object, object] | None:
    if isinstance(item, SuggestionDraft):
        return item.title, item.evidence, item.topic
    if isinstance(item, Mapping):
        evidence = item.get("evidence", item.get("reason", ""))
        return item.get("title"), evidence, item.get("topic")
    return None


def sanitize_drafts(raw: object, *, max_count: int) -> GuardResult:
    """AI 응답(신뢰할 수 없는 입력)을 후보로 쓸 수 있는 것만 남긴다. 버린 항목은 사유 코드와 함께 돌려준다."""
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return GuardResult((), ((0, "invalid_response"),))
    kept: list[SuggestionDraft] = []
    dropped: list[tuple[int, str]] = []
    seen: set[str] = set()
    for idx, item in enumerate(raw):
        parts = _coerce(item)
        if parts is None or not isinstance(parts[0], str):
            dropped.append((idx, "invalid_item"))
            continue
        title = clean_text(parts[0])
        if not title:
            dropped.append((idx, "empty"))
        elif len(title) > MAX_TITLE_CHARS:
            dropped.append((idx, "too_long"))
        elif has_contact_or_url(title):
            dropped.append((idx, "contact_or_url"))
        elif (key := _dedupe_key(title)) in seen:
            dropped.append((idx, "duplicate"))
        elif len(kept) >= max_count:
            dropped.append((idx, "over_limit"))
        else:
            seen.add(key)
            evidence = clean_text(parts[1], MAX_EVIDENCE_CHARS) if isinstance(parts[1], str) else ""
            topic = parts[2] if isinstance(parts[2], str) and parts[2] in TOPICS else None
            kept.append(SuggestionDraft(title, evidence, topic))
    return GuardResult(tuple(kept), tuple(dropped))
