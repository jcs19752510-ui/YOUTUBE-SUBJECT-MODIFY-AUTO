"""규칙 기반 제안기(실제 영상용). AI 서비스가 정해지기 전까지 모의 제안기(mock) 대신 쓴다.

mock 은 검증기 시연을 위해 일부러 차단 후보를 섞는다. 실제 영상에서는 승인할 수 없는 후보를 만들면 안 되므로,
이 제안기는 영상 설명(챕터 등)에 이미 있는 말만 이어 붙여 검증을 통과하는 후보만 만든다. 외부 통신이 없다.
쓸 만한 후보를 만들 수 없으면 빈 목록을 돌려주고, 호출한 쪽이 '직접 수정' 안내를 보여 준다.
"""
from __future__ import annotations

import itertools
import re

from ytweb.ai.base import SuggestionDraft, VideoBrief
from youtube_title.validator import tokens

MIN_CHARS = 45  # 선생님 채널의 제목 길이(예: 49자)에 맞춘 최소 길이(2026-10-12 요청). 설명이 짧아 못 채우면 FALLBACK_MIN 까지 허용
FALLBACK_MIN = 30
MAX_CHARS = 60  # config/settings.yaml 의 recommended_max_chars 와 같아야 경고가 없다
_PREFIX = re.compile(r"^\s*(\[[^\]]{1,12}\])\s*")
# '01:10 통역 앱 설치 및 실행 방법 (공식 앱 사용)' 같은 챕터 줄에서 괄호 앞 구절만 뽑는다.
_CHAPTER = re.compile(r"\d{1,2}:\d{2}\s+([^()\d:]{4,30}?)\s*(?=\(|\d{1,2}:\d{2}|$)")
_HEALTH = ("건강", "혈압", "당뇨", "관절", "무릎", "허리", "콜레스테롤", "기억력", "영양제", "근력", "숙면", "체조", "스트레칭")
_FINANCE = ("연금", "적금", "금리", "보험", "대출", "투자", "주식", "재테크", "펀드", "환급", "예금")


def _topic(text: str) -> str:
    if any(w in text for w in _FINANCE):
        return "finance"
    if any(w in text for w in _HEALTH):
        return "health"
    return "life"


class RuleSuggester:
    name = "rule"
    model: str | None = "rule-1"

    def suggest(self, brief: VideoBrief, *, count: int, tone: str) -> list[SuggestionDraft]:
        ref = brief.summary or ""
        m = _PREFIX.match(brief.title)
        prefix = (m.group(1) + " ") if m else ""
        body = brief.title[m.end():] if m else brief.title
        anchors = [t for t in dict.fromkeys(tokens(body)) if t in ref][:2]  # 현재 제목의 핵심어 중 설명에도 있는 것
        phrases = [p.strip() for p in _CHAPTER.findall(ref)]
        topic = _topic(f"{brief.title} {ref}")
        phrases = [p for p in phrases if len(p) >= 6 and not p.endswith("소개")]  # 도입부 챕터 이름은 제목으로 쓰지 않는다
        combos: list[tuple[str, tuple[str, ...]]] = []
        for a, b in itertools.combinations(phrases, 2):
            combos.append((f"{a}부터 {b}까지", (a, b)))
        for trio in itertools.combinations(phrases, 3):
            combos.append((", ".join(trio), trio))
        combos += [(p, (p,)) for p in phrases]  # 길이를 못 채울 때를 위한 한 구절 후보
        out: list[SuggestionDraft] = []
        seen: set[str] = {brief.title.strip()}
        for floor in (MIN_CHARS, FALLBACK_MIN):
            for body_text, parts in combos:
                missing = [a for a in anchors if a not in parts[0]]
                sep = " " if len(missing) < len(anchors) else ", "  # 구절에 핵심어가 이미 있으면 자연스럽게 이어 붙인다
                title = re.sub(r"\s+", " ", f"{prefix}{' '.join(missing)}{sep if missing else ''}{body_text}").strip()
                if not floor <= len(title) <= MAX_CHARS or title in seen:
                    continue
                seen.add(title)
                out.append(SuggestionDraft(title, parts[0], topic))
                if len(out) >= count:
                    return out
            if out:
                break
        return out
