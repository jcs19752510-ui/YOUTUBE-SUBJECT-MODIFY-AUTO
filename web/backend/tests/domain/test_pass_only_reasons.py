"""통과 후보가 없을 때 이유(경고 내용)를 알린다(2026-10-14 선생님 PC: 특정 영상만 계속 '검증을 통과하지 못해 저장하지 않았습니다')."""
from __future__ import annotations

import pytest

from tests.domain.helpers import eligible_video_ids
from ytweb.ai.base import SuggestionDraft
from ytweb.core.errors import ProblemError
from ytweb.db.models import Suggestion, Video
from ytweb.domain.suggestions import generate_for_video


class _BadEvidence:
    name, model = "rule", "t"

    def suggest(self, brief, *, count, tone):
        return [SuggestionDraft("[시니어 필수] 근거가 설명에 없는 전혀 다른 내용의 새 제목 후보입니다", "설명에 없는 문장", "life")]


def test_no_pass_error_lists_the_validation_messages_and_stores_nothing(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    v = seeded.get(Video, vid)
    v.source, v.description_excerpt = "youtube", "00:30 설정 열기 방법 01:10 앱 정리하기 방법"
    seeded.flush()
    before = seeded.query(Suggestion).count()
    with pytest.raises(ProblemError) as e:
        generate_for_video(seeded, vid, count=2, tone="t", now=clock(), env=env, suggester=_BadEvidence())
    assert e.value.code == "ai_no_pass_candidates"
    assert "근거" in e.value.detail or "일치율" in e.value.detail  # 어떤 경고 때문인지 한국어로 보인다
    assert "Gemini" in e.value.hint  # 규칙 제안기이면 연결 안내
    assert seeded.query(Suggestion).count() == before
