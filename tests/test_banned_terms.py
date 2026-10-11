from pathlib import Path

import pytest

from youtube_title.banned_terms import load_dictionary
from youtube_title.errors import ConfigError

REAL = Path(__file__).resolve().parent.parent / "config" / "banned_terms.yaml"


def write(tmp_path, text):
    p = tmp_path / "banned_terms.yaml"
    p.write_text(text, encoding="utf-8")
    return p


MIN = "version: 1\ntypes:\n  fear:\n    severity: block\n    terms: [큰일 납니다]\n"


def test_real_dictionary_loads_with_all_five_types():
    """TC-316: 저장소의 금칙어 사전이 읽히고 5가지 차단 유형이 모두 있다. [FR-003]"""
    d = load_dictionary(REAL)
    assert {t.name for t in d.types} == {"fear", "medical", "finance", "impersonation", "superlative"}
    assert all(t.terms or t.patterns for t in d.types) and d.strict_keywords and len(d.short_hash) == 8


def test_hash_is_stable_and_changes_with_content(tmp_path):
    """TC-317: 같은 내용은 같은 해시, 단어를 하나 바꾸면 해시가 달라진다(사전 변경 추적). [SEC-017]"""
    a = load_dictionary(write(tmp_path, MIN))
    b = load_dictionary(write(tmp_path, MIN))
    c = load_dictionary(write(tmp_path, MIN.replace("큰일 납니다", "큰일 납니다, 평생 후회")))
    assert a.sha == b.sha and a.sha != c.sha


@pytest.mark.parametrize("text", [
    "version: 1\ntypes:\n  fear:\n    terms: [큰]\n",                       # 한 글자
    "version: 1\ntypes:\n  fear:\n    terms: ['!!']\n",                     # 정규화하면 빈 문자열
    "version: 1\ntypes:\n  fear:\n    severity: maybe\n    terms: [큰일 납니다]\n",
    "version: 1\ntypes:\n  fear:\n    patterns: ['(unclosed']\n",
    "version: 1\ntypes:\n  fear:\n    patterns: ['" + "a" * 101 + "']\n",
    "version: 1\ntypes: {}\n",
    "version: 1\n",
    "- 목록\n",
    "version: 1\ntypes:\n  fear: 문자열\n",
    "version: 1\ntypes:\n  fear:\n    terms: [큰일 납니다]\nwarning:\n  모르는키: 1\n",
    "version: 1\ntypes:\n  fear:\n    terms: [큰일 납니다]\nwarning:\n  emoji_max: true\n",
    "version: 1\ntypes:\n  fear:\n    terms: [큰일 납니다]\nstrict_keywords: [아]\n",
])
def test_invalid_dictionary_rejected_with_korean_guidance(tmp_path, text):
    """TC-318: 위험하거나 잘못된 사전(너무 짧은 단어, 잘못된 정규식, 알 수 없는 키, 위험한 YAML 태그)은 안내와 함께 거부한다. [FR-003, SEC-016]"""
    with pytest.raises(ConfigError) as ei:
        load_dictionary(write(tmp_path, text))
    assert "banned_terms.yaml" in ei.value.next_step


def test_missing_dictionary(tmp_path):
    """TC-319: 사전 파일이 없으면 위치를 알려 주는 오류가 된다. [NFR-007]"""
    with pytest.raises(ConfigError):
        load_dictionary(tmp_path / "없음.yaml")


def test_warning_defaults_filled(tmp_path):
    """TC-320: warning 항목을 생략해도 기본 경고 기준이 채워지고, 일부만 바꿀 수 있다. [FR-002]"""
    assert load_dictionary(write(tmp_path, MIN)).warning["exclamation_max"] == 1
    d = load_dictionary(write(tmp_path, MIN + "warning:\n  exclamation_max: 0\n"))
    assert d.warning["exclamation_max"] == 0 and d.warning["emoji_max"] == 2


def test_dangerous_yaml_tag_is_not_executed(tmp_path):
    """TC-360: 사전에 숨긴 위험한 YAML 태그는 실행되지 않고(safe_load) 오류로 거부된다. 실행 흔적(표식 폴더)이 남지 않는다. [SEC-016, FR-003]"""
    marker = tmp_path / "pwned"
    with pytest.raises(ConfigError):
        load_dictionary(write(tmp_path, f"version: 1\ntypes: !!python/object/apply:os.mkdir ['{marker.as_posix()}']\n"))
    assert not marker.exists()
