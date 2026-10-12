"""반영 후 검증 결과 표시(2026-10-12 선생님 PC: 제목은 바뀌었는데 '실패'만 보이고 이유를 알 수 없었음)."""
from __future__ import annotations

from ytweb.domain.batches import apply_one, describe_verify, verify_snippet
from ytweb.domain.serialize import _item_dicts

from tests.verify_wb.vbh import Faulty, changes, queued


def test_describe_verify_handles_old_and_new_formats():
    old = {"ok": False, "checked": True, "title_ok": True, "preserved": {"description": False, "tags": True}}
    assert describe_verify(old) == "설명"  # 항목 이름이 없던 옛 기록도 풀린다
    assert describe_verify({"title_ok": False, "preserved": {"tags": False}}) == "제목, 태그"
    new = {"diff_fields": ["설명"], "diff_detail": {"description": {"before_len": 10, "after_len": 9, "first_diff_at": 4}}}
    assert describe_verify(new, detail=True) == "설명(길이 10→9, 처음 다른 위치 4)" and describe_verify(new) == "설명"
    assert describe_verify({"ok": True}) == ""


def test_title_comparison_ignores_whitespace_collapse_and_unicode_form():
    before = {"title": "a", "description": "d"}
    assert verify_snippet(before, {**before, "title": "가 나 다"}, "가  나   다")["ok"] is True
    assert verify_snippet(before, {**before, "title": "가"}, "가")["ok"] is True  # 자모 조합 형태 차이(NFD→NFC)
    assert verify_snippet(before, {**before, "title": "가 나"}, "가 다")["ok"] is False


def test_failed_item_shows_which_field_differs_in_batch_view(seeded, db, env, clock):
    b, _ = queued(db, env, clock(), 1)
    g = Faulty(db, clock)
    g.on_update = lambda n, body: {**body, "snippet": {**body["snippet"], "description": body["snippet"].get("description", "") + "X"}}
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=g)
    assert out.code == "verify_failed"
    c = changes(db)[0]
    assert c.verify_result["diff_fields"] == ["설명"] and c.verify_result["diff_detail"]["description"]["after_len"] == c.verify_result["diff_detail"]["description"]["before_len"] + 1
    item = _item_dicts(db, list(b.items))[0]
    assert "달라진 항목: 설명(길이" in item["skip_reason"]
    c.verify_result = {"ok": False, "checked": True, "title_ok": True, "preserved": {"description": False}}  # 옛 기록 형식
    db.flush()
    assert "달라진 항목: 설명." in _item_dicts(db, list(b.items))[0]["skip_reason"]
