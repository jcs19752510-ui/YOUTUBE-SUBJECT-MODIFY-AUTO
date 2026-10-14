"""실제 영상용 규칙 기반 제안기: 승인 불가 후보를 만들지 않는다(2026-10-12 선생님 PC 실측 결함 DEF-LIVE-001)."""
from pathlib import Path

import youtube_title.banned_terms as B
import youtube_title.config as C
import youtube_title.validator as V
from ytweb.ai.base import VideoBrief
from ytweb.ai.rule import RuleSuggester

ROOT = Path(__file__).resolve().parents[3]
REF = (
    "00:00 해외여행에서 통역이 필요한 순간 소개 (통역 걱정 끝) 01:10 통역 앱 설치 및 실행 방법 (공식 앱 사용) "
    "02:20 언어 선택하는 방법 (한국어 ↔ 현지어 설정) 03:30 말로 바로 번역하는 방법 (마이크 버튼 누르기) "
    "04:40 상대방 음성 번역 듣는 방법 (자동 재생 확인) 05:50 화면 보여주며 번역하는 방법 (텍스트 크기 표시)"
)
TITLE = "[시니어 필수] 해외여행 스마트폰 통역 설정법! 영어·일본어 말만 하면 다 되는 공짜 앱"


def _check(title: str, evidence: str, topic: str) -> str:
    s, dic = C.load_settings(str(ROOT)), B.load_dictionary(str(ROOT / "config" / "banned_terms.yaml"))
    cf = type("CF", (), {"current_title": TITLE, "topic": topic, "summary": REF, "candidates": []})()
    strict, _ = V.detect_strict(cf, dic)
    return V._check_title(title, cf, evidence, dic, s, REF, strict).result


def test_every_candidate_passes_validator():
    drafts = RuleSuggester().suggest(VideoBrief("o06Yj-yJCIY", TITLE, REF), count=5, tone="x")
    assert len(drafts) == 5
    for d in drafts:
        assert 45 <= len(d.title) <= 60 and d.title != TITLE  # 선생님 요청: 예시 제목(49자) 정도의 길이
        assert _check(d.title, d.evidence, d.topic) == "pass", d.title


def test_no_candidates_when_description_has_no_chapters():
    assert RuleSuggester().suggest(VideoBrief("x", TITLE, "설명이 없습니다"), count=3, tone="x") == []


def test_intro_chapter_not_used_as_title():
    drafts = RuleSuggester().suggest(VideoBrief("o06Yj-yJCIY", TITLE, REF), count=5, tone="x")
    assert all("순간 소개" not in d.title for d in drafts)  # 도입부 챕터 이름이 어디에도 들어가지 않는다


def test_many_distinct_candidates_for_repeated_requests():
    drafts = RuleSuggester().suggest(VideoBrief("o06Yj-yJCIY", TITLE, REF), count=30, tone="x")
    assert len({d.title for d in drafts}) == len(drafts) >= 10
    assert all(45 <= len(d.title) <= 60 and "순간 소개" not in d.title for d in drafts)


def test_too_short_titles_are_not_offered():
    short_ref = "01:00 앱 설치 방법 (공식 앱 사용)"  # 만들 수 있는 제목이 30자에 못 미치면 내놓지 않는다
    assert RuleSuggester().suggest(VideoBrief("x", TITLE, short_ref), count=3, tone="x") == []


SHORT_TITLE = "[시니어 필독2]삼성폰 주인도 놀란 기적의 AI! 길 가다 모르는 건 동그라미만 치면 다 알려주는 서클서치"


def _validate(title, evidence, topic, current, ref):
    s, dic = C.load_settings(str(ROOT)), B.load_dictionary(str(ROOT / "config" / "banned_terms.yaml"))
    cf = type("CF", (), {"current_title": current, "topic": topic, "summary": ref, "candidates": []})()
    strict, _ = V.detect_strict(cf, dic)
    return V._check_title(title, cf, evidence, dic, s, ref, strict).result


def test_no_chapters_short_makes_shortened_passing_candidates():
    """챕터·설명이 없는 쇼츠(2026-10-14 선생님 요청: 긴 영상과 같은 흐름으로 제안): 현재 제목 구절을 원래 순서로 일부만 남긴 후보를 만들고 모두 검증을 통과한다."""
    out = RuleSuggester().suggest(VideoBrief("vid00000001", SHORT_TITLE, ""), count=3, tone="친근")
    assert out, "후보가 있어야 한다"
    for d in out:
        assert d.title.startswith("[시니어 필독2] ") and d.title != SHORT_TITLE and 30 <= len(d.title) <= 60
        assert d.evidence in SHORT_TITLE and d.title[len("[시니어 필독2] "):] in SHORT_TITLE.replace("! ", " ")
        assert _validate(d.title, d.evidence, d.topic, SHORT_TITLE, SHORT_TITLE) == "pass", d.title


def test_description_without_chapters_uses_description_clauses_only():
    desc = "통화 내용을 그대로 저장해 주는 녹음 기능 설정 방법. 대학병원 처방 지시사항을 다시 듣고 싶을 때 바로 확인. 쇼츠로 짧게 정리"
    out = RuleSuggester().suggest(VideoBrief("vid00000001", SHORT_TITLE, desc), count=3, tone="친근")
    assert out and all(d.evidence in desc for d in out)
