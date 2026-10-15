import time
import unicodedata
from pathlib import Path

import pytest

from youtube_title.banned_terms import load_dictionary
from youtube_title.candidates import Candidate, CandidateFile
from youtube_title.config import load_settings
from youtube_title.validator import count_emoji, detect_strict, key_terms, match_ratio, tokens, validate_file

REAL_DICT = Path(__file__).resolve().parent.parent / "config" / "banned_terms.yaml"
GENERIC_SUMMARY = "겨울철 난방비와 전기요금을 줄이는 생활 습관을 설명하는 영상입니다"


@pytest.fixture(scope="module")
def dictionary():
    return load_dictionary(REAL_DICT)


@pytest.fixture
def settings(tmp_path):
    return load_settings(tmp_path, env={})


def cf(title, summary=GENERIC_SUMMARY, evidence=None, topic="life", current="예전 제목입니다", excerpt=None):
    ev = evidence if evidence is not None else summary
    return CandidateFile("abc123DEF45", current, topic, summary, "human", excerpt, (Candidate(title, ev),), "0" * 64, "abc123DEF45.json")


def one(c, dictionary, settings, **kw):
    return validate_file(c, dictionary, settings, **kw).results[0]


def codes(r):
    return {f.code for f in r.findings}


PASS_CASES = [
    ("겨울철 전기요금 줄이는 난방 습관 5가지", "겨울철 난방 습관을 바꿔 전기요금을 줄이는 방법을 소개합니다.", "겨울철 난방 습관을 바꿔 전기요금을 줄이는 방법"),
    ("냉장고 정리 쉽게 하는 요령", "냉장고 칸별로 정리하는 요령을 알려드립니다. 냉장고를 쉽게 정리하는 순서입니다.", "냉장고를 쉽게 정리하는 순서"),
    ("세탁기 곰팡이 냄새 없애는 청소법", "세탁기 고무패킹의 곰팡이를 닦아 냄새를 없애는 청소법입니다", "세탁기 고무패킹의 곰팡이를 닦아 냄새를 없애는 청소법"),
    ("스마트폰 사진 정리하는 간단한 순서", "스마트폰 갤러리에 쌓인 사진을 앨범으로 정리하는 간단한 순서를 설명합니다", "스마트폰 갤러리에 쌓인 사진을 앨범으로 정리하는 간단한 순서"),
    ("베란다 텃밭 상추 키우기 기초", "베란다에서 상추를 키우는 텃밭 기초를 처음부터 설명합니다", "베란다에서 상추를 키우는 텃밭 기초"),
    ("이사 전에 챙길 서류 점검 목록", "이사 전에 챙길 서류를 점검하는 목록을 정리했습니다", "이사 전에 챙길 서류를 점검하는 목록"),
    ("여름철 선풍기 바람 시원하게 쓰는 법", "여름철 선풍기 바람을 시원하게 쓰는 법을 알려드립니다", "여름철 선풍기 바람을 시원하게 쓰는 법"),
    ("제주도 2박 3일 여행 코스 정리", "제주도 2박 3일 여행 코스를 하루씩 정리한 영상입니다", "제주도 2박 3일 여행 코스를 하루씩 정리"),
    ("손주와 함께하는 종이접기 놀이", "손주와 함께 종이접기 놀이를 즐기는 방법입니다", "손주와 함께 종이접기 놀이를 즐기는 방법"),
    ("된장찌개 맛있게 끓이는 순서", "된장찌개를 맛있게 끓이는 순서를 차근차근 보여드립니다", "된장찌개를 맛있게 끓이는 순서"),
    ("겨울 산책 준비물 체크하기", "겨울 산책을 나가기 전 준비물을 체크하는 방법입니다", "겨울 산책을 나가기 전 준비물을 체크하는 방법"),
    ("베개 커버 세탁 주기와 관리법", "베개 커버를 얼마나 자주 세탁해야 하는지 관리법을 설명합니다", "베개 커버를 얼마나 자주 세탁해야 하는지 관리법"),
]


@pytest.mark.parametrize("title,summary,evidence", PASS_CASES)
def test_pass_cases_korean(dictionary, settings, title, summary, evidence):
    """TC-321: 영상과 일치하고 규칙에 맞는 생활 주제 한글 제목 12건이 모두 '통과'이다. [FR-002, FR-004, FR-005]"""
    r = one(cf(title, summary, evidence), dictionary, settings)
    assert r.result == "pass", [(f.code, f.message) for f in r.findings]
    assert r.findings == () and r.evidence_found and r.match_ratio >= 0.5


BLOCK_CASES = [
    ("이거 안 하면 큰일 납니다 겨울철 전기요금", "BANNED_FEAR"), ("의사들이 숨기는 무릎 운동", "BANNED_FEAR"),
    ("당뇨 완치 식단 공개", "BANNED_MEDICAL"), ("혈압 특효 차 만드는 법", "BANNED_MEDICAL"), ("기적의 허리 스트레칭", "BANNED_MEDICAL"),
    ("무릎 통증 직빵 운동", "BANNED_MEDICAL"), ("무조건 수익 나는 적금 고르기", "BANNED_FINANCE"), ("원금 보장 연금 상품 비교", "BANNED_FINANCE"),
    ("수익 보장 투자 방법", "BANNED_FINANCE"), ("속보 연금 개편안 확정", "BANNED_IMPERSONATION"), ("정부 발표 난방비 지원 신청", "BANNED_IMPERSONATION"),
    ("긴급 공지 건강보험 환급", "BANNED_IMPERSONATION"), ("100% 효과 보는 난방비 절약법", "BANNED_SUPERLATIVE"), ("무조건 낫는 허리 운동", "BANNED_SUPERLATIVE"),
    ("당뇨 완 치 되는 식단", "BANNED_MEDICAL"), ("특-효 있는 차 소개", "BANNED_MEDICAL"), ("원 금 보 장 상품 비교", "BANNED_FINANCE"),
    ("완​치 식단", "BANNED_MEDICAL"), ("ＷＨＯ 100％ 안전", "BANNED_SUPERLATIVE"),
    ("가" * 101, "LEN_HARD"), ("<b>난방 절약</b>", "CHAR_FORBIDDEN"), ("난방\n절약 방법", "CHAR_CONTROL"), ("   ", "EMPTY"),
    ("화성 탐사선 착륙 장면", "MATCH_LOW"),
]


@pytest.mark.parametrize("title,code", BLOCK_CASES)
def test_block_cases_korean(dictionary, settings, title, code):
    """TC-322: 공포·의료·금융·사칭·최상급·우회 표기·길이·규격·불일치 위반 제목 24건이 모두 '차단'이고 해당 사유가 나온다. [FR-002, FR-003, FR-004]"""
    r = one(cf(title), dictionary, settings)
    assert r.result == "block" and code in codes(r), [(f.code, f.severity) for f in r.findings]


def test_decomposed_hangul_cannot_bypass(dictionary, settings):
    """TC-323: 자모가 풀어진(NFD) 한글로 쓴 금칙어도 같은 단어로 인식해 차단한다. [FR-003, 우회 표기]"""
    title = unicodedata.normalize("NFD", "당뇨 완치 식단")
    assert title != "당뇨 완치 식단"
    assert "BANNED_MEDICAL" in codes(one(cf(title), dictionary, settings))


def test_length_boundaries_40_41_100_101(dictionary, settings):
    """TC-324: 권장 40자는 경고 없음, 41자는 경고, 상한 100자는 차단 아님(경고), 101자는 차단. [FR-002, NFR-002]"""
    def lens(n):
        return codes(one(cf("난방" + "가" * (n - 2)), dictionary, settings))
    assert "LEN_REC" not in lens(40) and "LEN_HARD" not in lens(40)
    assert "LEN_REC" in lens(41) and "LEN_HARD" not in lens(41)
    assert "LEN_REC" in lens(100) and "LEN_HARD" not in lens(100)
    assert "LEN_HARD" in lens(101)


def test_length_counts_unicode_not_bytes(dictionary, settings):
    """TC-325: 길이는 바이트가 아니라 유니코드 문자 수로 센다(한글 100자는 통과 범위, 이모지·결합 문자 포함). [FR-002, NFR-002]"""
    r = one(cf("가" * 100), dictionary, settings)
    assert r.length == 100 and "LEN_HARD" not in codes(r)
    assert one(cf("é" * 3), dictionary, settings).length == 3


@pytest.mark.parametrize("title,code", [
    ("난방비 줄이는 습관!!", "EXCLAMATION"), ("난방비 줄이는 습관 😀😀😀", "EMOJI"), ("난방비 줄이는 습관???", "SYMBOL_RUN"),
    ("난방비 SAVING TIPS NOW", "CAPS"), ("난방비 ★줄이는★ ♥습관♥ ~~", "SPECIAL_RATIO"),
])
def test_warning_types(dictionary, settings, title, code):
    """TC-326: 과한 느낌표·이모지·반복 기호·대문자·기호 비율은 '경고'(생활 주제)이다. [FR-002]"""
    summary = "난방비 줄이는 습관과 saving tips now를 설명합니다 겨울철 전기요금"
    r = one(cf(title, summary, summary), dictionary, settings)
    assert code in codes(r) and next(f for f in r.findings if f.code == code).severity == "warn"
    assert r.result in ("warn", "block")


def test_single_exclamation_and_two_emoji_are_allowed(dictionary, settings):
    """TC-327: 느낌표 1개, 이모지 2개는 허용 기준 안이라 경고가 없다(경계값). [FR-002]"""
    r = one(cf("난방비 줄이는 습관 😀😀!", GENERIC_SUMMARY, GENERIC_SUMMARY), dictionary, settings)
    assert not {"EXCLAMATION", "EMOJI"} & codes(r)


def test_count_emoji():
    """TC-328: 이모지 개수 세기: 한글·느낌표·물음표는 세지 않고, 이모지와 장식 기호(★ 등)는 보수적으로 센다. [FR-002]"""
    assert count_emoji("한글 제목 ! ?") == 0 and count_emoji("😀🙂") == 2 and count_emoji("★☆") == 2


def test_strict_mode_turns_warnings_into_blocks(dictionary, settings):
    """TC-329: 건강 주제는 같은 경고도 '차단'이 되고 사유에 엄격 모드가 표시된다. [POL-001, FR-005]"""
    life = one(cf("난방비 줄이는 습관!!", GENERIC_SUMMARY, GENERIC_SUMMARY, topic="life"), dictionary, settings)
    health = one(cf("난방비 줄이는 습관!!", GENERIC_SUMMARY, GENERIC_SUMMARY, topic="health"), dictionary, settings)
    assert life.result == "warn" and not life.strict
    assert health.result == "block" and health.strict
    assert any("엄격 모드" in f.message for f in health.findings if f.code == "EXCLAMATION")


@pytest.mark.parametrize("topic", ["health", "finance", None])
def test_strict_reasons_for_topic(dictionary, topic):
    """TC-330: 건강·금융 주제와 주제 미지정은 엄격 모드이다. [POL-001]"""
    strict, reasons = detect_strict(cf("난방 습관", topic=topic), dictionary)
    assert strict and reasons


def test_strict_upgrade_by_keyword_even_if_topic_is_life(dictionary):
    """TC-331: 주제를 '생활'로 적어도 제목·요약에 건강·금융 낱말이 보이면 엄격 모드로 올린다(입력 실수 방지). [POL-001]"""
    strict, reasons = detect_strict(cf("겨울철 혈압 관리 습관", "겨울철 혈압을 관리하는 습관을 설명합니다", topic="life"), dictionary)
    assert strict and any("혈압" in r for r in reasons)
    strict2, _ = detect_strict(cf("난방 습관"), dictionary)
    assert not strict2


def test_evidence_must_exist_in_summary_or_description(dictionary, settings):
    """TC-332: 일치 근거 문장이 요약·설명에서 확인되지 않으면 경고이다. 설명에 있으면 확인된다. [FR-004]"""
    bad = one(cf("난방 습관 줄이기", evidence="영상에 전혀 없는 문장"), dictionary, settings)
    assert "EVIDENCE_NOT_FOUND" in codes(bad) and not bad.evidence_found
    ok = one(cf("난방 습관 줄이기", evidence="보일러 온도를 낮추는 장면", excerpt="영상 초반에 보일러 온도를 낮추는 장면이 나옵니다"), dictionary, settings)
    assert ok.evidence_found


def test_match_ratio_thresholds_boundaries(dictionary, settings):
    """TC-333: 일치율 경계: 50%는 경고 아님, 25%는 경고(차단 아님), 25% 미만은 차단. [FR-004]"""
    summary = "사과 포도"
    assert abs(match_ratio("사과 포도 수박 참외", summary) - 0.5) < 1e-9
    codes_half = codes(one(cf("사과 포도 수박 참외", summary, summary), dictionary, settings))
    assert "MATCH_WEAK" not in codes_half and "MATCH_LOW" not in codes_half
    quarter = codes(one(cf("사과 수박 참외 오이", "사과", "사과"), dictionary, settings))
    assert "MATCH_WEAK" in quarter and "MATCH_LOW" not in quarter
    zero = codes(one(cf("수박 참외 오이 당근", "사과 포도", "사과 포도"), dictionary, settings))
    assert "MATCH_LOW" in zero


def test_match_ratio_unknown_when_no_comparable_words():
    """TC-334: 제목에서 비교할 낱말이 없으면(숫자·일반어뿐) 일치율은 계산하지 않는다. [FR-004]"""
    assert match_ratio("5가지 방법 123", "아무 요약") is None


def test_description_improves_match_and_is_reported(dictionary, settings):
    """TC-335: 영상 설명을 쓰면 일치율에 반영되고 '설명 사용' 여부가 결과에 남는다. 없으면 요약만 사용한다. [FR-004]"""
    c = cf("사과 포도 수박 참외", "사과 포도", "사과 포도")
    without = validate_file(c, dictionary, settings)
    withd = validate_file(c, dictionary, settings, description="수박 참외도 다룹니다")
    assert not without.description_used and withd.description_used
    assert withd.results[0].match_ratio > without.results[0].match_ratio


def test_key_phrase_must_appear_in_first_20_chars(dictionary, settings):
    """TC-336: 영상 핵심어가 제목 앞 20자에 없으면 경고, 있으면 없다. [FR-002]"""
    summary = "난방 난방 난방 습관 전기요금 절약"
    late = "가나다라마바사아자차카타파하 안녕하세요 반갑습니다 난방 습관"
    assert "KEY_LATE" in codes(one(cf(late, summary, summary), dictionary, settings))
    assert "KEY_LATE" not in codes(one(cf("난방 습관으로 전기요금 절약", summary, summary), dictionary, settings))
    assert key_terms(summary)[0] == "난방"


def test_same_title_as_current_warns(dictionary, settings):
    """TC-337: 현재 제목과 똑같은 후보는 경고이다. [FR-002]"""
    c = cf("난방 습관 줄이기", GENERIC_SUMMARY, GENERIC_SUMMARY, current="난방 습관 줄이기")
    assert "SAME_AS_CURRENT" in codes(one(c, dictionary, settings))


def test_known_false_positive_is_visible_and_fixable(tmp_path, settings):
    """TC-338: 정상 낱말('속보' 걷기 운동)이 사칭 금칙어에 걸리는 과차단은 사유가 보이고, 사전에서 빼면 통과한다(알려진 한계). [FR-003, RISK-001]"""
    d = load_dictionary(REAL_DICT)
    summary = "속보 걷기 운동 자세를 설명하는 영상입니다"
    assert "BANNED_IMPERSONATION" in codes(one(cf("속보 걷기 운동 자세", summary, summary), d, settings))
    text = REAL_DICT.read_text(encoding="utf-8").replace("속보, ", "").replace(", 속보", "")
    p = tmp_path / "d.yaml"
    p.write_text(text, encoding="utf-8")
    assert "BANNED_IMPERSONATION" not in codes(one(cf("속보 걷기 운동 자세", summary, summary), load_dictionary(p), settings))


def test_dictionary_severity_warn_type(tmp_path, settings):
    """TC-339: 사전에서 severity를 warn으로 둔 유형은 경고로만 처리된다(생활 주제). [FR-003]"""
    p = tmp_path / "d.yaml"
    p.write_text("version: 2\ntypes:\n  soft:\n    severity: warn\n    terms: [과장 표현]\n", encoding="utf-8")
    r = one(cf("과장 표현 포함 제목 난방", GENERIC_SUMMARY, GENERIC_SUMMARY), load_dictionary(p), settings)
    assert any(f.code == "BANNED_SOFT" and f.severity == "warn" for f in r.findings)


def test_result_carries_dictionary_version_and_hash(dictionary, settings):
    """TC-340: 검증 결과에 사용한 금칙어 사전의 버전과 해시가 담긴다. [SEC-017]"""
    fr = validate_file(cf("난방 습관"), dictionary, settings)
    assert fr.dictionary_version == "1" and fr.dictionary_hash == dictionary.short_hash


def test_tokens_helper_rules():
    """TC-341: 낱말 추출은 숫자 포함 낱말과 일반어(방법·꿀팁 등)를 빼고 조사를 떼어 낸다. [FR-004]"""
    assert tokens("겨울철 전기요금을 줄이는 방법 5가지 꿀팁") == ["겨울철", "전기요금", "줄이"]


def test_performance_100_candidates_within_5_seconds(dictionary, settings):
    """TC-342: 후보 100건 검증이 5초 안에 끝난다. [NFR-005]"""
    start = time.perf_counter()
    for i in range(5):
        cands = tuple(Candidate(f"겨울철 난방 습관 {n}번째 방법 정리", GENERIC_SUMMARY) for n in range(20))
        validate_file(CandidateFile("abc123DEF45", "x", "life", GENERIC_SUMMARY, "human", None, cands, "0" * 64, "a.json"), dictionary, settings)
    assert time.perf_counter() - start < 5.0


def test_validate_does_not_mutate_inputs(dictionary, settings):
    """TC-343: 검증은 입력 객체를 바꾸지 않고 같은 입력에 같은 결과를 낸다(순수성). [FR-005]"""
    c = cf("난방 습관 줄이기")
    a, b = validate_file(c, dictionary, settings), validate_file(c, dictionary, settings)
    assert a == b and c.candidates[0].title == "난방 습관 줄이기"
