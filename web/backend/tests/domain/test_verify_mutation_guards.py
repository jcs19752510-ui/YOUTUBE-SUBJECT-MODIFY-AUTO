"""반영 후 검증(batches.verify_snippet 등)의 사용자 관점 동작을 고정하는 시험. 변이 점검에서 살아남은 변이를 잡기 위해 추가했다.
기준: 유튜브가 저장하며 바꾸는 겉모습(줄바꿈·끝 공백·태그 순서·연속 공백)은 같게, 내용이 바뀐 것은 다르게 본다."""
import pytest

from ytweb.domain.batches import _canon_title, _diff_detail, describe_verify, verify_failure_text, verify_snippet
from ytweb.domain.serialize import _failure_reason


class _It:
    def __init__(self, status="failed", reason="[verify_failed] x"):
        self.status, self.skip_reason = status, reason


class _Ch:
    def __init__(self, vr):
        self.verify_result = vr


def _base(**kw):
    b = {"title": "옛", "description": "a\nb", "tags": ["x", "y"], "categoryId": "22", "defaultLanguage": "ko", "defaultAudioLanguage": "ko"}
    b.update(kw)
    return b


def _ok(before, after, title="새"):
    return verify_snippet(before, dict(after, title=title), title)


def test_crlf_and_lone_cr_are_same_as_lf():
    assert _ok(_base(description="a\nb"), _base(description="a\r\nb"))["ok"]
    assert _ok(_base(description="a\nb"), _base(description="a\rb"))["ok"]
    assert not _ok(_base(description="ab"), _base(description="a\r\nb"))["ok"]


def test_trailing_spaces_per_line_and_outer_blank_ignored_but_inner_text_kept():
    assert _ok(_base(description="a\nb"), _base(description="a  \nb\t"))["ok"]
    assert _ok(_base(description="a\nb"), _base(description="\n a\nb \n\n".replace(" a", "a")))["ok"]
    assert not _ok(_base(description="a b"), _base(description="a  b"))["ok"]
    assert not _ok(_base(description="a\nb"), _base(description="a\nc"))["ok"]
    assert _ok(_base(description="a"), _base(description="  a"))["ok"]


def test_missing_none_and_empty_description_equal():
    assert _ok({"title": "옛"}, {"title": "옛", "description": ""})["ok"]
    assert _ok({"title": "옛", "description": None}, {"title": "옛"})["ok"]
    assert not _ok({"title": "옛"}, {"title": "옛", "description": "내용"})["ok"]
    assert not _ok({"title": "옛", "description": "내용"}, {"title": "옛"})["ok"]
    assert not _ok({"title": "옛", "description": 5}, {"title": "옛", "description": "5"})["ok"]


def test_tags_order_ignored_whitespace_trimmed_blank_dropped_content_matters():
    assert _ok(_base(tags=["x", "y"]), _base(tags=["y", "x"]))["ok"]
    assert _ok(_base(tags=["x", "y"]), _base(tags=[" x", "y "]))["ok"]
    assert _ok(_base(tags=["x", "y"]), _base(tags=["x", "", "  ", "y"]))["ok"]
    assert not _ok(_base(tags=["x", "y"]), _base(tags=["x"]))["ok"]
    assert not _ok(_base(tags=["x", "y"]), _base(tags=["x", "z"]))["ok"]
    assert _ok({"title": "옛"}, {"title": "옛", "tags": []})["ok"]
    assert not _ok({"title": "옛"}, {"title": "옛", "tags": ["x"]})["ok"]
    assert _ok({"title": "옛", "tags": "bad"}, {"title": "옛", "tags": []})["ok"]
    assert not _ok({"title": "옛", "tags": ["x"]}, {"title": "옛", "tags": "bad"})["ok"]
    assert _ok({"title": "옛", "tags": [1, "x"]}, {"title": "옛", "tags": ["x"]})["ok"]


@pytest.mark.parametrize("field", ["defaultLanguage", "defaultAudioLanguage"])
def test_language_autofill_ok_but_change_or_removal_not(field):
    assert _ok({"title": "옛"}, {"title": "옛", field: "ko"})["ok"]
    assert not _ok({"title": "옛", field: "en"}, {"title": "옛", field: "ko"})["ok"]
    assert not _ok({"title": "옛", field: "en"}, {"title": "옛"})["ok"]
    r = _ok({"title": "옛", field: "en"}, {"title": "옛", field: "ko"})
    assert r["preserved"][field] is False and r["diff_fields"]


def test_category_change_detected_and_equal_ok():
    assert _ok(_base(), _base())["ok"]
    r = _ok(_base(), _base(categoryId="10"))
    assert not r["ok"] and r["diff_fields"] == ["카테고리"] and r["preserved"]["categoryId"] is False
    assert not _ok({"title": "옛"}, {"title": "옛", "categoryId": "10"})["ok"]


def test_refetch_failure_is_not_ok_and_not_checked():
    r = verify_snippet(_base(), None, "새")
    assert r["ok"] is False and r["checked"] is False and r["reason"]


def test_title_must_match_but_whitespace_and_unicode_form_ignored():
    b = _base()
    assert verify_snippet(b, dict(b, title="새  제목"), "새 제목")["title_ok"] is True
    assert verify_snippet(b, dict(b, title=" 새 제목 "), "새 제목")["ok"] is True
    assert verify_snippet(b, dict(b, title="새\t제목"), "새 제목")["ok"] is True
    nfd = "새 제목"  # 조합형(NFD)
    assert verify_snippet(b, dict(b, title=nfd), "새 제목")["ok"] is True
    assert _canon_title("새") == "새"
    r = verify_snippet(b, dict(b, title="다른"), "새 제목")
    assert r["ok"] is False and r["title_ok"] is False and r["diff_fields"] == ["제목"]
    assert verify_snippet(b, dict(b, title="새제목"), "새 제목")["title_ok"] is False
    assert verify_snippet(b, {k: v for k, v in b.items() if k != "title"}, "새")["title_ok"] is False
    assert _canon_title(None) == "" and _canon_title(3) == ""


def test_title_ok_but_preserved_changed_is_not_ok_and_both_listed():
    b = _base()
    r = verify_snippet(b, dict(b, title="새", categoryId="9"), "새")
    assert r["title_ok"] is True and r["ok"] is False and r["diff_fields"] == ["카테고리"]
    r2 = verify_snippet(b, dict(b, title="딴", categoryId="9", description="z"), "새")
    assert r2["diff_fields"] == ["제목", "설명", "카테고리"]


def test_other_changed_lists_unexpected_fields_but_ignores_title_and_localized():
    b = _base()
    r = verify_snippet(b, dict(b, title="새", localized={"a": 1}, foo=1), "새")
    assert r["other_changed"] == ["foo"]
    assert verify_snippet(dict(b, localized={"a": 1}), dict(b, title="새", localized={"a": 2}), "새")["other_changed"] == []
    assert verify_snippet(dict(b, foo=1), dict(b, title="새", foo=2), "새")["other_changed"] == ["foo"]


def test_diff_detail_positions_and_codes():
    d = _diff_detail("abc", "abd")
    assert d == {"before_len": 3, "after_len": 3, "first_diff_at": 2, "before_char": ord("c"), "after_char": ord("d")}
    d = _diff_detail("ab", "abc")
    assert d["first_diff_at"] == 2 and d["before_char"] is None and d["after_char"] == ord("c")
    d = _diff_detail("abc", "ab")
    assert d["first_diff_at"] == 2 and d["before_char"] == ord("c") and d["after_char"] is None
    d = _diff_detail(None, "a")
    assert d["before_len"] == 0 and d["after_len"] == 1 and d["first_diff_at"] == 0 and d["before_char"] is None
    d = _diff_detail("a", None)
    assert d["after_len"] == 0 and d["after_char"] is None and d["before_char"] == ord("a")
    assert _diff_detail("x", "x")["first_diff_at"] == 1


def test_describe_verify_names_and_details():
    v = verify_snippet(_base(description="abc"), _base(description="abd", title="새"), "새")
    assert describe_verify(v) == "설명"
    assert describe_verify(v, detail=True) == "설명(길이 3→3, 처음 다른 위치 2)"
    assert describe_verify({"title_ok": False}) == "제목"
    assert describe_verify({"title_ok": True}) == ""
    assert describe_verify({}) == ""
    assert describe_verify({"preserved": {"tags": False, "categoryId": True}}) == "태그"
    assert describe_verify({"diff_fields": ["제목", "설명"]}, detail=True) == "제목, 설명"  # 상세 정보가 없으면 이름만
    assert describe_verify({"diff_fields": ["설명"], "diff_detail": {"description": {"before_len": 1, "after_len": 2, "first_diff_at": 0}}}) == "설명"
    assert describe_verify({"title_ok": False, "preserved": {"description": False, "tags": False}}) == "제목, 설명, 태그"


def test_verify_failure_text_with_and_without_names():
    t = verify_failure_text({"diff_fields": ["설명", "태그"]})
    assert t.startswith("[verify_failed]") and "달라진 항목: 설명, 태그." in t and "롤백" in t
    t2 = verify_failure_text({})
    assert "제목 또는 보존 항목이 맞지 않습니다." in t2 and "달라진 항목" not in t2


def test_failure_reason_expands_only_verify_failed_failed_items_with_result():
    vr = verify_snippet(_base(description="abc"), _base(description="abd", title="새"), "새")
    txt = _failure_reason(_It(), _Ch(vr))
    assert txt.startswith("[verify_failed] 반영은 됐지만") and "설명(길이 3→3, 처음 다른 위치 2)" in txt and "롤백" in txt
    assert _failure_reason(_It(status="skipped"), _Ch(vr)) == "[verify_failed] x"
    assert _failure_reason(_It(reason="[other] y"), _Ch(vr)) == "[other] y"
    assert _failure_reason(_It(), None) == "[verify_failed] x"
    assert _failure_reason(_It(), _Ch(None)) == "[verify_failed] x"
    assert _failure_reason(_It(), _Ch({})) == "[verify_failed] x"
    assert _failure_reason(_It(), _Ch({"title_ok": True})) == "[verify_failed] x"  # 달라진 항목 이름이 없으면 원문 그대로
    assert _failure_reason(_It(reason=None), None) is None
    assert _failure_reason(_It(status="success", reason=None), _Ch(vr)) is None
