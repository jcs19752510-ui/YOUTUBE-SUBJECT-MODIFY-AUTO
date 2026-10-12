"""결정적 한국어 모의 제안기. 같은 영상이면 항상 같은 후보를 낸다(영상 ID 해시로 고름).

일부러 경고·차단 후보를 섞어 검증기 동작이 화면에서 보이게 한다: 느낌표 연속, 너무 긴 제목, 효능 단정(건강),
원금 보장(금융), 근거 없는 최상급, 영상과 무관한 제목. 실서비스 연동 코드는 없다(DEC-034 Q-1).
"""
from __future__ import annotations

import hashlib
import re

from ytweb.ai.base import SuggestionDraft, VideoBrief

# 시드(domain/seed.py)가 제목 끝에 붙이는 말투. 제목의 핵심 부분(core)을 뽑을 때만 쓴다.
KNOWN_ENDINGS = ("이렇게 하세요", "총정리", "꼭 알아두세요", "처음부터 끝까지", "따라 해보세요")
HEALTH_WORDS = ("건강", "혈압", "당뇨", "관절", "무릎", "허리", "콜레스테롤", "기억력", "영양제", "근력", "숙면", "체조", "스트레칭")
FINANCE_WORDS = ("연금", "적금", "금리", "보험", "대출", "투자", "주식", "재테크", "펀드", "환급", "예금")

_GOOD = (
    "{c} 처음이라도 쉽게 따라 하는 순서",
    "{c}, 집에서 바로 해보는 순서와 주의할 점",
    "{c} 쉽게 따라 하는 순서 천천히 알려드립니다",
)
_BAD = {
    "excl": "{c} 이거 꼭 보세요!!!",
    "long": "{c} 처음이라도 쉽게 따라 하는 순서와 주의할 점 그리고 집에서 바로 해보는 방법까지 천천히 하나하나 자세하게 알려드립니다",  # 권장 길이(60자)를 확실히 넘겨 경고가 보이게 한다
    "superlative": "{c} 무조건 성공하는 100% 비법",
    "unrelated": "주말 드라마 결말 총정리 화제의 장면",
    "medical": "{c} 이것만 하면 완치 기적의 비법",
    "fear": "{c} 이거 안 하면 큰일 납니다",
    "guarantee": "{c} 원금 보장 확정 수익 비법",
}
_POOLS = {
    "life": ("excl", "long", "superlative", "unrelated"),
    "health": ("medical", "excl", "fear", "unrelated"),
    "finance": ("guarantee", "excl", "unrelated", "superlative"),
}


def _core(title: str) -> str:
    t = re.sub(r"[\s,!?.]+$", "", title.strip())
    for ending in KNOWN_ENDINGS:
        if t.endswith(ending):
            t = t[: -len(ending)].strip()
            break
    return t or title.strip()


def _topic(text: str) -> str:
    if any(w in text for w in FINANCE_WORDS):
        return "finance"
    if any(w in text for w in HEALTH_WORDS):
        return "health"
    return "life"


def _first_sentence(summary: str) -> str:
    m = re.match(r"\s*(.+?[.!?。])(?:\s|$)", summary)
    return (m.group(1) if m else summary).strip()


class MockSuggester:
    name = "mock"
    model: str | None = "mock-1"

    def suggest(self, brief: VideoBrief, *, count: int, tone: str) -> list[SuggestionDraft]:
        h = int(hashlib.sha256(brief.video_id.encode("utf-8")).hexdigest(), 16)
        topic = _topic(f"{brief.title} {brief.summary}")
        core = _core(brief.title)
        pool = _POOLS[topic]
        evidence = _first_sentence(brief.summary) or brief.title
        kinds = [("good", 0), ("good", 1), ("bad", h), ("good", 2), ("bad", h + 1)]
        drafts: list[SuggestionDraft] = []
        for kind, n in kinds[: max(1, min(count, len(kinds)))]:
            if kind == "good":
                drafts.append(SuggestionDraft(_GOOD[n].format(c=core), evidence, topic))
                continue
            key = pool[n % len(pool)]
            ev = "드라마 결말이 궁금하신 분들을 위한 소개 영상입니다." if key == "unrelated" else evidence
            drafts.append(SuggestionDraft(_BAD[key].format(c=core), ev, topic))
        return drafts
