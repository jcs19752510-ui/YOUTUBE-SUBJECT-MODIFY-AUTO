"""SEC-05 규칙 I(규제 민감 도메인)·규칙 J(AI 투명성) 문구가 실제 화면 소스·빌드 번들에 있는가 (9단계).

대상 요구: POL-002(면책), POL-006(AI 생성 고지), POL-008(AI 한계·표시광고 규정 확인), POL-013(Studio A/B 확인), 그리고 이미 구현된 POL-001·005·014.
- 개정 2판(2026-10-11): W-FIX-FE·BE 가 문구를 넣어 이 파일의 `xfail(strict)` 8건이 XPASS 로 바뀌었고(DEF-9-007·008 닫힘),
  표식을 제거해 회귀 방지 시험으로 바꿨다. 문구를 지우면 다시 실패한다.
- 번들 시험(`bundle_*`)은 YTWEB_SEC_LIVE_PORT 의 임시 스택(이미지에 빌드된 번들)을 대상으로 한다.
법률 자문이 아니다: 문구의 법적 충분성은 판단하지 않는다. 이 시험은 '기획서가 정한 문구가 화면에 존재·연결되는가'만 본다.
"""
from __future__ import annotations

import http.client
import os
import re
from pathlib import Path

import pytest

REPO = Path(os.environ.get("YTWEB_SEC_ROOT", Path(__file__).resolve().parents[2]))
SRC = REPO / "web" / "frontend" / "src"
KO = SRC / "i18n" / "ko.ts"
PAGES = SRC / "pages"
LAYOUT = SRC / "app" / "Layout.tsx"
LIVE_PORT = os.environ.get("YTWEB_SEC_LIVE_PORT")

DEF_007 = "DEF-9-007 / POL-002: 면책 문구('법률 자문이 아니며 최종 책임은 채널 소유자')가 화면에 없다(규칙 I, Critical). 고치면 이 표식을 지운다."
DEF_008A = "DEF-9-008 / POL-006: 'AI가 생성한 제안' 고지 문장이 화면에 없다(규칙 J, High). 고치면 이 표식을 지운다."
DEF_008B = "DEF-9-008 / POL-008: AI 한계·건강/금융 표시광고 규정 확인 안내가 화면에 없다(규칙 I·J, High). 고치면 이 표식을 지운다."
DEF_008C = "DEF-9-008 / POL-013: 반영 확인 단계에 'A/B 테스트 중이 아님' 확인이 없다(사전 점검 경고 한 줄뿐). 고치면 이 표식을 지운다."


def _ko() -> str:
    return KO.read_text(encoding="utf-8")


def _page_sources() -> dict[str, str]:
    out = {p.name: p.read_text(encoding="utf-8") for p in PAGES.glob("*.tsx") if not p.name.endswith(".test.tsx")}
    out[LAYOUT.name] = LAYOUT.read_text(encoding="utf-8")
    return out


def _keys_with(text_re: str) -> list[str]:
    """ko.ts 에서 문구가 text_re 에 맞는 속성 이름들."""
    keys = []
    for m in re.finditer(r"""(?m)^\s*(?:(\w+)|'([^']+)')\s*:\s*(?:\([^)]*\)\s*=>\s*)?(?:`|'|")(.*)$""", _ko()):
        if re.search(text_re, m.group(3)):
            keys.append(m.group(1) or m.group(2))
    return keys


def _used_in(key: str, names: list[str]) -> list[str]:
    srcs = _page_sources()
    return [n for n in names if n in srcs and re.search(r"\.(?:\w+\.)*" + re.escape(key) + r"\b", srcs[n])]


# ---------------------------------------------------------------- 이미 구현된 것(통과해야 함: 회귀 방지)

def test_demo_badge_is_always_rendered_in_layout():
    """POL-005: 데모 모드 상시 표시(구현됨)."""
    assert "demoBadge" in LAYOUT.read_text(encoding="utf-8")
    assert "아무것도 전송되지 않습니다" in _ko()


def test_ai_label_and_strict_mode_hint_exist_on_suggestion_card():
    """POL-001/006 일부: 'AI 제안' 배지와 엄격 모드 안내는 있다(고지 '문장'은 없음 = DEF-9-008)."""
    ko, card = _ko(), (PAGES / "SuggestionCard.tsx").read_text(encoding="utf-8")
    assert re.search(r"ai:\s*'AI 제안'", ko)
    assert "ko.suggestion.ai" in card and "ko.suggestion.strictHint" in card
    assert "민감 주제는 경고도 차단" in ko


def test_ab_warning_exists_only_as_preflight_warning_line():
    """POL-013 부분: 서버 사전 점검 경고 한 줄(구현됨). 확인 문구에는 없음 → 아래 xfail."""
    batches = (REPO / "web" / "backend" / "ytweb" / "domain" / "batches.py").read_text(encoding="utf-8")
    assert "A/B 테스트가 진행 중이 아닌지 확인하세요" in batches


# ---------------------------------------------------------------- 있어야 하지만 없는 것(DEF-9-007·008)

def test_disclaimer_text_exists_in_ko_ts():
    ko = _ko()
    assert "법률 자문이 아니" in ko and "최종 책임" in ko and "채널 소유자" in ko


def test_disclaimer_is_rendered_globally_or_on_all_result_screens():
    """문구는 (a) 전 화면 공통 Layout 에 있거나 (b) 영상 상세(검증 결과)·배치 상세(사전 점검)·리포트 전부에 연결돼야 한다."""
    keys = _keys_with(r"법률 자문")
    assert keys, "ko.ts 에 면책 문구 속성이 없다"
    k = keys[0]
    glob_ok = bool(_used_in(k, [LAYOUT.name]))
    per_page = all(_used_in(k, [n]) for n in ("VideoDetailPage.tsx", "BatchDetailPage.tsx", "ReportsPage.tsx"))
    assert glob_ok or per_page


def test_ai_generated_notice_sentence_exists_and_is_on_suggestion_card():
    keys = _keys_with(r"AI가 (?:생성|만든)")
    assert keys, "ko.ts 에 'AI가 생성한 제안입니다' 류 고지 문장이 없다"
    assert _used_in(keys[0], ["SuggestionCard.tsx", "VideoDetailPage.tsx"])


def test_ai_limit_and_advertising_rule_notice_exists_and_is_on_suggestion_card():
    keys = _keys_with(r"(?=.*표시[·ㆍ]?\s?광고)(?=.*(?:보장하지|적합성))")
    assert keys, "ko.ts 에 '사실·법령 적합성 비보장 / 건강·금융 표시광고 규정 확인' 안내가 없다"
    assert _used_in(keys[0], ["SuggestionCard.tsx", "VideoDetailPage.tsx"])


def test_batch_execute_confirmation_mentions_ab_test():
    ko = _ko()
    assert re.search(r"A/B\s*테스트\s*중이\s*아", ko)
    assert _used_in(_keys_with(r"A/B")[0], ["BatchDetailPage.tsx"])


# ---------------------------------------------------------------- 번들(이미지에 실제로 들어간 화면 코드)

def _bundle() -> str:
    c = http.client.HTTPConnection("127.0.0.1", int(LIVE_PORT), timeout=10)
    c.request("GET", "/", headers={"Host": "127.0.0.1:8080"})
    html = c.getresponse().read().decode("utf-8", "replace")
    m = re.search(r'/assets/index-[^"\']+\.js', html)
    assert m, "index.html 에서 번들 경로를 찾지 못함"
    c.request("GET", m.group(0), headers={"Host": "127.0.0.1:8080"})
    return c.getresponse().read().decode("utf-8", "replace")


live = pytest.mark.skipif(not LIVE_PORT, reason="YTWEB_SEC_LIVE_PORT 가 없어 번들 시험을 건너뜀")


@live
def test_bundle_contains_demo_badge_and_ai_label():
    b = _bundle()
    assert "데모 모드" in b and "AI 제안" in b


@live
def test_bundle_contains_disclaimer():
    assert "법률 자문이 아니" in _bundle()


@live
def test_bundle_contains_ai_generated_notice():
    assert re.search(r"AI가 (?:생성|만든)", _bundle())


@live
def test_bundle_contains_advertising_rule_notice():
    assert re.search(r"표시[·ㆍ]?\s?광고", _bundle())
