"""실제(youtube) 영상의 AI 제안: 승인 불가 후보 없음·충분한 길이·다시 눌러도 새 후보(DEF-LIVE-001/002, 선생님 PC 2026-10-12)."""
from __future__ import annotations

from sqlalchemy import select

from ytweb.db.models import Suggestion, Video
from ytweb.domain.suggestions import generate_for_video

from tests.domain.helpers import SUGGESTER, eligible_video_ids

DESC = (
    "00:00 해외여행에서 통역이 필요한 순간 소개 (통역 걱정 끝) 01:10 통역 앱 설치 및 실행 방법 (공식 앱 사용) "
    "02:20 언어 선택하는 방법 (한국어 ↔ 현지어 설정) 03:30 말로 바로 번역하는 방법 (마이크 버튼 누르기) "
    "04:40 상대방 음성 번역 듣는 방법 (자동 재생 확인) 05:50 화면 보여주며 번역하는 방법 (텍스트 크기 표시)"
)
TITLE = "[시니어 필수] 해외여행 스마트폰 통역 설정법! 영어·일본어 말만 하면 다 되는 공짜 앱"


def _live_video(db, seeded_vid):
    v = db.get(Video, seeded_vid)
    v.source, v.title, v.description_excerpt = "youtube", TITLE, DESC
    db.flush()
    return v.video_id


def _gen(db, env, clock, vid, count):
    return generate_for_video(db, vid, count=count, tone="friendly", now=clock(), env=env, suggester=SUGGESTER)


def test_live_video_gets_only_approvable_candidates_of_sufficient_length(seeded, env, clock):
    vid = _live_video(seeded, eligible_video_ids(seeded, 1)[0])
    sugs = _gen(seeded, env, clock, vid, 3)
    assert len(sugs) == 3
    for s in sugs:
        assert s.source == "ai:rule" and s.validation_result == "pass" and s.status == "candidate", (s.title, s.validation_reasons)
        assert 45 <= len(s.title) <= 60, s.title


def test_pressing_again_gives_new_candidates_not_the_same_ones(seeded, env, clock):
    vid = _live_video(seeded, eligible_video_ids(seeded, 1)[0])
    first = {s.title for s in _gen(seeded, env, clock, vid, 3)}
    second = {s.title for s in _gen(seeded, env, clock, vid, 3)}
    assert len(first) == 3 and len(second) == 3 and not first & second
    titles = [t for (t,) in seeded.execute(select(Suggestion.title).where(Suggestion.video_id == vid))]
    assert len(titles) == len(set(titles)) == 6


def test_demo_video_still_uses_mock_with_deliberate_bad_candidates(seeded, env, clock):
    vid = eligible_video_ids(seeded, 1)[0]
    sugs = _gen(seeded, env, clock, vid, 5)
    assert all(s.source == "ai:mock" for s in sugs) and any(s.validation_result == "block" for s in sugs)


def test_live_video_uses_gemini_when_key_present_and_gemini_failure_is_reported(seeded, env, clock, monkeypatch, tmp_path):
    import json
    import urllib.error

    from ytweb.ai import gemini as G
    from ytweb.core.errors import ProblemError

    key = tmp_path / "k"
    key.write_text("FAKEKEY", encoding="utf-8")
    monkeypatch.setenv("YTWEB_GEMINI_KEY_FILE", str(key))
    vid = _live_video(seeded, eligible_video_ids(seeded, 1)[0])

    class R:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            items = [{"title": "[시니어 필수] 해외여행 통역 앱 설치 및 실행 방법과 언어 선택하는 방법", "evidence": "통역 앱 설치 및 실행 방법", "topic": "life"}]
            return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({"candidates": items}, ensure_ascii=False)}]}}]}).encode()

    monkeypatch.setattr(G.urllib.request, "urlopen", lambda req, timeout=None: R())
    sugs = _gen(seeded, env, clock, vid, 1)
    assert len(sugs) == 1 and sugs[0].source == "ai:gemini" and sugs[0].validation_result == "pass"

    def down(req, timeout=None):
        raise urllib.error.URLError("x")

    monkeypatch.setattr(G.urllib.request, "urlopen", down)
    with __import__("pytest").raises(ProblemError) as e:
        _gen(seeded, env, clock, vid, 1)
    assert e.value.status == 502 and e.value.code == "ai_unavailable"


def test_gemini_branch_tells_model_existing_titles_and_filters_duplicates(seeded, env, clock):
    """변이 g(Gemini 분기 제거)를 잡는 시험: 이미 만든 제목은 모델에 알려 주고, 모델이 같은 제목을 또 내도 걸러낸다."""
    from ytweb.ai.base import SuggestionDraft

    vid = _live_video(seeded, eligible_video_ids(seeded, 1)[0])
    seen = {}

    class FakeGemini:
        name, model = "gemini", "fake"

        def __init__(self, avoid=()):
            self.avoid = tuple(avoid)

        def with_avoid(self, titles):
            seen["avoid"] = set(titles)
            return FakeGemini(titles)

        def suggest(self, brief, *, count, tone):
            return [SuggestionDraft("[시니어 필수] 해외여행 통역 앱 설치 및 실행 방법과 언어 선택하는 방법", "통역 앱 설치 및 실행 방법", "life"),
                    SuggestionDraft("[시니어 필수] 해외여행 통역, 말로 바로 번역하는 방법과 상대방 음성 번역 듣는 방법", "말로 바로 번역하는 방법", "life")]

    first = generate_for_video(seeded, vid, count=2, tone="t", now=clock(), env=env, suggester=FakeGemini())
    assert len(first) == 2 and seen["avoid"] == set()
    from ytweb.core.errors import ProblemError

    with __import__("pytest").raises(ProblemError) as e:  # 모델이 같은 제목만 또 내면 새 후보가 없다고 알린다(중복 저장 안 함)
        generate_for_video(seeded, vid, count=2, tone="t", now=clock(), env=env, suggester=FakeGemini())
    assert e.value.code == "ai_no_candidates"
    assert seen["avoid"] == {s.title for s in first}
    titles = [t for (t,) in seeded.execute(select(Suggestion.title).where(Suggestion.video_id == vid))]
    assert len(titles) == len(set(titles)) == 2


def test_rule_suggester_no_candidates_tells_to_connect_gemini(seeded, env, clock):
    """챕터가 없는 영상(쇼츠 등)에서 규칙 기반 제안기가 후보를 못 만들면, 이유와 Gemini 연결 방법을 한국어로 알린다(2026-10-14)."""
    from ytweb.ai.rule import RuleSuggester
    from ytweb.core.errors import ProblemError
    from ytweb.db.models import Video

    vid = eligible_video_ids(seeded, 1)[0]
    v = seeded.get(Video, vid)
    v.source, v.description_excerpt = "youtube", "#shorts"
    seeded.flush()
    with __import__("pytest").raises(ProblemError) as e:
        generate_for_video(seeded, vid, count=2, tone="t", now=clock(), env=env, suggester=RuleSuggester())
    assert e.value.code == "ai_no_candidates" and "Gemini" in e.value.title and "gemini-on.bat" in e.value.hint
