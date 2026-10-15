"""규칙 J: 사람이 AI 제안을 고치면 출처에 '+edited'가 붙어 AI 원문과 구분된다(두 번 고쳐도 한 번만)."""
from __future__ import annotations

from tests.domain.helpers import eligible_video_ids, suggest
from ytweb.domain.suggestions import edit_title


def test_tc_m3_060_edit_marks_source_edited_once(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    sug = suggest(seeded, env, clock(), vid, 1)[0]
    assert sug.source.startswith("ai:") and not sug.source.endswith("+edited")
    original = sug.source
    edit_title(seeded, sug.id, "사람이 직접 고친 제목 하나", now=clock(), env=env)
    assert sug.source == original + "+edited"
    edit_title(seeded, sug.id, "사람이 다시 고친 제목 둘", now=clock(), env=env)
    assert sug.source == original + "+edited"
