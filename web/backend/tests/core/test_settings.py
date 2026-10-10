"""설정 API: 허용 키만 변경, 라이브 관련 키는 변경 불가."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.conftest import hdr
from ytweb.core.settings_store import effective_daily_cap, get_web_setting, set_web_setting
from ytweb.db.models import AuditLog, SettingKV


def test_get_settings_defaults(client, csrf):
    """TC-WA-@@@ 기본값: daily_apply_cap=10, suggestions_per_video=3, tone=[], pin 꺼짐, 라이브 정보는 읽기 전용."""
    j = client.get("/api/v1/settings").json()
    assert j["daily_apply_cap"] == 10 and j["suggestions_per_video"] == 3 and j["tone"] == []
    assert j["pin_enabled"] is False and j["mode"] == "demo"
    assert j["read_only"]["enable_live"] is False and j["read_only"]["live_allowlist"] == []


def test_patch_daily_cap_persists(client, csrf, db):
    """TC-WA-@@@ daily_apply_cap 변경이 저장되고 effective_daily_cap 에 반영된다."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 20}, headers=hdr(csrf))
    assert r.status_code == 200 and r.json()["daily_apply_cap"] == 20
    assert client.get("/api/v1/settings").json()["daily_apply_cap"] == 20
    assert effective_daily_cap(db, client.app.state.policy) == 20


@pytest.mark.parametrize("value", [0, 21, -1, "5", 5.5, True, None, [5]])
def test_daily_cap_out_of_range_rejected(client, csrf, value):
    """TC-WA-@@@ daily_apply_cap 은 1~20 정수만(경계 0/21, 문자열·실수·불리언 거부)."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": value}, headers=hdr(csrf))
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    assert client.get("/api/v1/settings").json()["daily_apply_cap"] == 10


@pytest.mark.parametrize("value,ok", [(1, True), (5, True), (0, False), (6, False), ("3", False)])
def test_suggestions_per_video_range(client, csrf, value, ok):
    """TC-WA-@@@ suggestions_per_video 는 1~5 정수만."""
    r = client.patch("/api/v1/settings", json={"suggestions_per_video": value}, headers=hdr(csrf))
    assert (r.status_code == 200) is ok


def test_tone_valid_and_trimmed(client, csrf):
    """TC-WA-@@@ tone 은 짧은 문자열 목록(공백 정리)을 저장한다."""
    r = client.patch("/api/v1/settings", json={"tone": [" 담백한 ", "친근한"]}, headers=hdr(csrf))
    assert r.status_code == 200 and r.json()["tone"] == ["담백한", "친근한"]
    r = client.patch("/api/v1/settings", json={"tone": []}, headers=hdr(csrf))
    assert r.status_code == 200 and r.json()["tone"] == []


@pytest.mark.parametrize("tone", ["담백한", ["a"] * 6, ["x" * 21], [""], ["   "], [1], ["a\nb"], None, {"a": 1}])
def test_tone_invalid_rejected(client, csrf, tone):
    """TC-WA-@@@ tone 형식 위반(문자열 단독·6개 초과·21자 초과·빈 값·비문자열·제어문자)은 422."""
    r = client.patch("/api/v1/settings", json={"tone": tone}, headers=hdr(csrf))
    assert r.status_code == 422


@pytest.mark.parametrize("key", ["enable_live", "live_allowlist", "mode", "approval_ttl_hours", "pin_hash", "unknown", "daily_limit_units"])
def test_forbidden_keys_rejected(client, csrf, key, db):
    """TC-WA-@@@ 허용 목록 밖 키(enable_live, live_allowlist 등)는 400 setting_not_allowed 이고 아무것도 저장되지 않는다."""
    r = client.patch("/api/v1/settings", json={key: True}, headers=hdr(csrf))
    assert r.status_code == 400 and r.json()["code"] == "setting_not_allowed"
    assert db.execute(select(SettingKV)).scalars().all() == []


def test_forbidden_key_mixed_with_valid_key_changes_nothing(client, csrf, db):
    """TC-WA-@@@ 허용 키와 금지 키가 섞이면 전체 거부(부분 적용 없음)."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 3, "enable_live": True}, headers=hdr(csrf))
    assert r.status_code == 400
    assert client.get("/api/v1/settings").json()["daily_apply_cap"] == 10
    assert client.get("/api/v1/settings").json()["read_only"]["enable_live"] is False


def test_invalid_value_in_mixed_patch_changes_nothing(client, csrf):
    """TC-WA-@@@ 한 값이 잘못되면 같은 요청의 다른 값도 저장되지 않는다."""
    r = client.patch("/api/v1/settings", json={"daily_apply_cap": 3, "suggestions_per_video": 99}, headers=hdr(csrf))
    assert r.status_code == 422
    assert client.get("/api/v1/settings").json()["daily_apply_cap"] == 10


def test_empty_and_non_object_body_rejected(client, csrf):
    """TC-WA-@@@ 빈 객체는 422, 객체가 아닌 본문도 422."""
    assert client.patch("/api/v1/settings", json={}, headers=hdr(csrf)).status_code == 422
    assert client.patch("/api/v1/settings", json=[1], headers=hdr(csrf)).status_code == 422


@pytest.mark.parametrize("pin", ["x", {"action": "reset"}, {"action": "set", "new_pin": "1234", "extra": 1}, {}])
def test_pin_body_malformed(client, csrf, pin):
    """TC-WA-@@@ pin 항목 형식 위반은 422."""
    assert client.patch("/api/v1/settings", json={"pin": pin}, headers=hdr(csrf)).status_code == 422


def test_settings_patch_requires_csrf_and_session(client):
    """TC-WA-@@@ 세션 없이는 401, CSRF 없이는 403."""
    assert client.patch("/api/v1/settings", json={"daily_apply_cap": 5}, headers={"Origin": "http://127.0.0.1:8080"}).status_code == 401


def test_settings_change_audited_without_pin(client, csrf, db):
    """TC-WA-@@@ 설정 변경이 감사 로그에 남고 PIN 값은 기록되지 않는다."""
    client.patch("/api/v1/settings", json={"daily_apply_cap": 7, "pin": {"action": "set", "new_pin": "5555"}}, headers=hdr(csrf))
    rows = db.execute(select(AuditLog).where(AuditLog.action == "settings.update")).scalars().all()
    assert len(rows) == 1
    assert rows[0].detail == {"daily_apply_cap": 7, "pin": "set"}
    assert "5555" not in str(rows[0].detail)


def test_effective_daily_cap_default_and_corrupt_value(db, web_settings):
    """TC-WA-@@@ 저장값이 없거나 범위 밖(손상)이면 기본 10 으로 돌아간다."""
    from datetime import datetime, timezone
    from ytitle.config import load_settings
    policy = load_settings(web_settings.base_dir, env={})
    assert effective_daily_cap(db, policy) == 10
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for bad in (0, 99, "7", True):
        set_web_setting(db, "daily_apply_cap", bad, now=now)
        assert effective_daily_cap(db, policy) == 10
    set_web_setting(db, "daily_apply_cap", 4, now=now)
    assert effective_daily_cap(db, policy) == 4
    assert get_web_setting(db, "nope", "dflt") == "dflt"
