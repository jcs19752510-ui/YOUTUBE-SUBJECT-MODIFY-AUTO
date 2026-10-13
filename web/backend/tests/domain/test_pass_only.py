"""사용자 요청(2026-10-13): 실제 영상의 AI 제안은 검증을 '통과'한 후보만 저장한다(경고·차단 후보는 만들지 않는다)."""
import pytest

from tests.domain.helpers import SUGGESTER, eligible_video_ids
from ytweb.core.errors import ProblemError
from ytweb.db.models import Suggestion, Video
from ytweb.domain import suggestions as sg
from ytweb.domain.suggestions import generate_for_video


def _live(db, vid):
    v = db.get(Video, vid)
    v.source = "youtube"
    db.flush()
    return v


class _Stub:
    """이름이 mock·rule·gemini 가 아닌 가짜 제안기: 고정 후보 6개."""

    name, model = "stub", "stub-1"

    def suggest(self, brief, *, count, tone):
        from ytweb.ai.base import SuggestionDraft
        return [SuggestionDraft(title=f"[시니어 필수] 후보 {c} 스마트폰 설정 방법 안내까지", evidence="근거 문장입니다", topic="general") for c in "ABCDEF"][:count]


import types

_REAL = sg.validate_title


def _forced(result_for):
    """진짜 검증 결과의 나머지 값은 그대로 두고 판정(result)만 바꾼 가짜."""
    def fake(env, video, title, evidence, topic):
        res, fr = _REAL(env, video, title, evidence, topic)
        return types.SimpleNamespace(result=result_for(title), findings=res.findings, match_ratio=res.match_ratio, strict=res.strict), fr
    return fake


def test_tc_m3_090_live_video_keeps_only_pass_candidates(seeded, env, clock, monkeypatch):
    vid = eligible_video_ids(seeded, 1)[0]
    _live(seeded, vid)
    monkeypatch.setattr(sg, "validate_title", _forced(lambda t: "pass" if any(f"후보 {c} " in t for c in "BDE") else "warn"))
    # 저장 단계의 검증도 같은 가짜를 쓰므로 통과 후보만 저장되는지(경고 후보 A·C·F 는 저장 안 됨)를 본다
    out = generate_for_video(seeded, vid, count=2, tone="friendly", now=clock(), env=env, suggester=_Stub())
    titles = [s.title for s in out]
    assert len(out) == 2 and all(("후보 B " in t or "후보 D " in t or "후보 E " in t) for t in titles)
    assert not any(("후보 A " in s.title or "후보 C " in s.title or "후보 F " in s.title) for s in seeded.query(Suggestion).filter(Suggestion.video_id == vid))


def test_tc_m3_091_when_no_candidate_passes_it_says_so_and_stores_nothing(seeded, env, clock, monkeypatch):
    vid = eligible_video_ids(seeded, 1)[0]
    _live(seeded, vid)
    monkeypatch.setattr(sg, "validate_title", _forced(lambda t: "warn"))
    before = seeded.query(Suggestion).count()
    with pytest.raises(ProblemError) as e:
        generate_for_video(seeded, vid, count=3, tone="friendly", now=clock(), env=env, suggester=_Stub())
    assert e.value.code == "ai_no_pass_candidates" and "다시" in e.value.hint
    assert seeded.query(Suggestion).count() == before


def test_tc_m3_092_demo_video_behavior_unchanged(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    out = generate_for_video(seeded, vid, count=3, tone="friendly", now=clock(), env=env, suggester=SUGGESTER)
    assert len(out) == 3  # 데모는 시연용으로 통과·경고·차단이 섞여 나올 수 있다(기존 동작 유지)
