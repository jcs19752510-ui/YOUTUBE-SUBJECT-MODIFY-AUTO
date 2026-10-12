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
