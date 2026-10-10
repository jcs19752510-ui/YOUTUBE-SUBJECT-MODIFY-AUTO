"""독립 점검 3: 설정 PATCH 허용 키 · 값 검증 · 멱등성 (S-W03, S-W12, S-W13)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from tests.verify_wa.helpers import ORIGIN, hdr, login
from ytweb.core.errors import ProblemError
from ytweb.core.idempotency import run_idempotent
from ytweb.db.models import IdempotencyKey

SETTINGS = "/api/v1/settings"


def _patch(client, csrf, body, **kw):
    return client.patch(SETTINGS, json=body, headers=hdr(csrf), **kw)


def _kv_count(engine) -> int:
    with engine.connect() as c:
        return c.execute(text("select count(*) from settings_kv")).scalar_one()


def _audit_actions(engine) -> list[str]:
    with engine.connect() as c:
        return [r[0] for r in c.execute(text("select action from audit_log order by id"))]


# ---------------------------------------------------------------- 허용 키 필터

FORBIDDEN_KEYS = [
    "enable_live", "ENABLE_LIVE", "Enable_Live", " enable_live", "enable_live ", "enable_live​", "enable-live",
    "live_allowlist", "LIVE_ALLOWLIST", "live_allowlist[]", "daily_apply_cap ", " daily_apply_cap", "Daily_Apply_Cap",
    "DAILY_APPLY_CAP", "suggestions_per_video\n", "Tone", "TONE", "PIN", "Pin", "pin_hash", "pin_fail", "mode", "read_only",
    "allowed_hosts", "session_ttl_hours", "database_url", "__proto__", "constructor", "$set", "tone.0", "daily_apply_cap.x", "", "0", "none",
    "ｄaily_apply_cap", "daily_apply_cap\u0000",
]


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
def test_non_allowlisted_key_variants_rejected_and_nothing_written(client, engine, key):
    """TC-VA-056 [S-W03] 허용 키 4개 외의 모든 변형(대소문자·공백·제로폭·유사 문자·내부 키 pin_hash 등)은 400 setting_not_allowed 이고 DB/감사에 흔적이 없다."""
    csrf = login(client)
    before_audit = _audit_actions(engine)
    r = _patch(client, csrf, {key: True})
    assert r.status_code == 400 and r.json()["code"] == "setting_not_allowed", (key, r.status_code, r.text)
    assert _kv_count(engine) == 0
    assert _audit_actions(engine) == before_audit


def test_mixed_allowed_and_forbidden_rejects_entire_request(client, engine):
    """TC-VA-057 [S-W03] 허용 키와 금지 키가 섞이면 전체가 거부되어 허용 키 값도 적용되지 않는다."""
    csrf = login(client)
    r = _patch(client, csrf, {"daily_apply_cap": 5, "enable_live": True, "tone": ["a"]})
    assert r.status_code == 400 and "enable_live" in r.json()["detail"]
    assert _kv_count(engine) == 0 and client.get(SETTINGS).json()["daily_apply_cap"] == 10


def test_nested_forbidden_keys_cannot_smuggle_through_allowed_keys(client, engine):
    """TC-VA-058 [S-W03] 허용 키 안에 중첩 객체/배열로 금지 키를 숨겨도 저장되지 않는다(타입 검증에서 422)."""
    csrf = login(client)
    for body in (
        {"tone": [{"enable_live": True}]}, {"daily_apply_cap": {"enable_live": True}}, {"suggestions_per_video": [3]},
        {"tone": {"enable_live": True}}, {"pin": {"action": "set", "new_pin": "1234", "enable_live": True}},
        {"pin": {"action": "set", "new_pin": "1234", "__proto__": {}}},
    ):
        r = _patch(client, csrf, body)
        assert r.status_code == 422, (body, r.status_code, r.text)
    assert _kv_count(engine) == 0
    view = client.get(SETTINGS).json()
    assert view["read_only"]["enable_live"] is False and view["read_only"]["live_allowlist"] == []


def test_duplicate_json_keys_last_wins_but_forbidden_still_detected(client, engine):
    """TC-VA-059 [S-W03] 중복 키 JSON 으로 금지 키를 감춰도(파서가 마지막 값 사용) 금지 키 검사에 걸린다."""
    csrf = login(client)
    raw = '{"enable_live": true, "daily_apply_cap": 5, "enable_live": false}'
    r = client.patch(SETTINGS, content=raw, headers={**hdr(csrf), "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["code"] == "setting_not_allowed"
    assert _kv_count(engine) == 0


@pytest.mark.parametrize("body", ["[]", '"x"', "null", "5", "true", "{}", "", "{", '{"daily_apply_cap":}', "﻿{}"])
def test_non_object_or_empty_body_is_422_or_400_never_500(client, body):
    """TC-VA-060 [S-W13] 객체가 아니거나 빈/깨진 JSON 본문은 4xx(500 아님)이고 problem+json 이다."""
    csrf = login(client)
    r = client.patch(SETTINGS, content=body.encode("utf-8"), headers={**hdr(csrf), "Content-Type": "application/json"})
    assert 400 <= r.status_code < 500, (body, r.status_code)
    assert r.headers["content-type"].startswith("application/problem+json")


def test_wrong_content_type_does_not_apply_change(client):
    """TC-VA-061 [S-W03] text/plain 으로 JSON 문자열을 보내는 '단순 요청' 방식 CSRF 는 값을 바꾸지 못한다."""
    csrf = login(client)
    for ct in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
        r = client.patch(SETTINGS, content=b'{"daily_apply_cap": 3}', headers={**hdr(csrf), "Content-Type": ct})
        assert r.status_code != 200, (ct, r.status_code)
    assert client.get(SETTINGS).json()["daily_apply_cap"] == 10


# ---------------------------------------------------------------- 값 검증 경계

@pytest.mark.parametrize("key,lo,hi", [("daily_apply_cap", 1, 20), ("suggestions_per_video", 1, 5)])
def test_int_setting_boundaries_and_type_confusion(client, key, lo, hi):
    """TC-VA-062 [S-W13] 정수 설정 경계: lo, hi 는 200, lo-1, hi+1 은 422. bool/실수/문자열/null/배열/객체/NaN/거대정수는 422."""
    csrf = login(client)
    for v in (lo, hi):
        r = _patch(client, csrf, {key: v})
        assert r.status_code == 200 and r.json()[key] == v
    for v in (lo - 1, hi + 1, -1, 0 if lo else 1, 10**30, -(10**30), True, False, float(lo), lo + 0.5, str(lo), "", None, [lo], {"v": lo}, "1e1"):
        if v in (lo, hi) and not isinstance(v, bool):
            continue
        r = _patch(client, csrf, {key: v})
        assert r.status_code == 422, (key, v, r.status_code)
    r = client.patch(SETTINGS, content=('{"%s": NaN}' % key).encode(), headers={**hdr(csrf), "Content-Type": "application/json"})
    assert r.status_code == 422
    r = client.patch(SETTINGS, content=('{"%s": Infinity}' % key).encode(), headers={**hdr(csrf), "Content-Type": "application/json"})
    assert r.status_code == 422
    assert client.get(SETTINGS).json()[key] == hi  # 거부된 값은 마지막 정상 값을 건드리지 않음


def test_tone_boundaries_and_sanitization(client):
    """TC-VA-063 [S-W13] tone: 0~5개·항목 1~20자(공백 제거 후)만 허용, 6개/21자/빈/공백뿐/제어문자/비문자열/null 은 422, 앞뒤 공백은 제거되어 저장."""
    csrf = login(client)
    assert _patch(client, csrf, {"tone": []}).json()["tone"] == []
    assert _patch(client, csrf, {"tone": ["a"] * 5}).status_code == 200
    assert _patch(client, csrf, {"tone": ["가" * 20]}).json()["tone"] == ["가" * 20]
    assert _patch(client, csrf, {"tone": ["  친근한  "]}).json()["tone"] == ["친근한"]
    for bad in (["a"] * 6, ["a" * 21], [""], ["   "], ["a\u0000b"], ["a\tb"], ["a\nb"], [1], [None], [["x"]], None, "casual", 5, [True]):
        r = _patch(client, csrf, {"tone": bad})
        assert r.status_code == 422, (bad, r.status_code)
    assert client.get(SETTINGS).json()["tone"] == ["친근한"]


def test_settings_view_never_exposes_pin_hash_or_internal_keys(client):
    """TC-VA-064 [S-W08, S-W09] GET /settings 응답에 pin_hash/pin_fail/세션/내부 키가 없다."""
    csrf = login(client)
    client.patch(SETTINGS, json={"pin": {"action": "set", "new_pin": "2468"}}, headers=hdr(csrf))
    raw = client.get(SETTINGS).text
    for needle in ("scrypt", "pin_hash", "pin_fail", "locked_until", "csrf", "ytw_session"):
        assert needle not in raw
    assert set(client.get(SETTINGS).json()) == {"daily_apply_cap", "suggestions_per_video", "tone", "pin_enabled", "mode", "read_only"}


def test_settings_update_is_audited_without_secrets_and_atomic_with_audit(client, engine, monkeypatch):
    """TC-VA-065 [S-W16] 설정 변경은 감사에 값(비밀 제외)과 함께 남고, 감사 기록이 실패하면 설정 변경도 롤백된다(같은 트랜잭션)."""
    csrf = login(client)
    assert _patch(client, csrf, {"daily_apply_cap": 4}).status_code == 200
    with engine.connect() as c:
        d = c.execute(text("select detail from audit_log where action='settings.update'")).scalar_one()
    assert json.loads(d) == {"daily_apply_cap": 4}

    import ytweb.routers.settings as rs

    def boom(*a, **k):
        raise RuntimeError("audit down")
    monkeypatch.setattr(rs.audit, "record", boom)
    r = client.patch(SETTINGS, json={"daily_apply_cap": 9}, headers=hdr(csrf))
    assert r.status_code == 500 and "audit down" not in r.text
    monkeypatch.undo()
    assert client.get(SETTINGS).json()["daily_apply_cap"] == 4


# ---------------------------------------------------------------- 멱등성(HTTP, 프로브 라우터)

def _post(c, csrf, key, body=None, path="/api/v1/_t/charge"):
    h = hdr(csrf)
    if key is not None:
        h["Idempotency-Key"] = key
    return c.post(path, json=body if body is not None else {"amount": 1}, headers=h)


def test_idem_missing_key_400_and_handler_not_called(pclient):
    """TC-VA-066 [S-W12] 키가 없거나 빈 값이면 400 idempotency_key_required 이고 핸들러는 실행되지 않는다."""
    from tests.verify_wa import probe_routes
    csrf = login(pclient)
    for k in (None, ""):
        r = _post(pclient, csrf, k)
        assert r.status_code == 400 and r.json()["code"] == "idempotency_key_required"
    assert probe_routes.CALLS.get("charge", 0) == 0


@pytest.mark.parametrize("key,ok", [("a" * 7, False), ("a" * 8, True), ("a" * 80, True), ("a" * 81, False), ("abc defgh", False),
                                    ("abc/defgh", False), ("abc;defgh", False), ("ab.cd:ef_g-h", True),
                                    ("../../etc", False), ("A1b2C3d4", True)])
def test_idem_key_format_boundaries(pclient, key, ok):
    """TC-VA-067 [S-W12] 키 형식 경계: 8~80자 [A-Za-z0-9._:-] 만 허용."""
    csrf = login(pclient)
    h = hdr(csrf)
    h["Idempotency-Key"] = key
    r = pclient.post("/api/v1/_t/charge", json={"a": 1}, headers=h)
    assert (r.status_code == 201) is ok, (key, r.status_code, r.text)
    if not ok:
        assert r.status_code == 400 and r.json()["code"] == "idempotency_key_invalid"


def test_idem_same_key_same_body_replays_once(pclient):
    """TC-VA-068 [S-W12] 같은 키+같은 본문 재전송: 핸들러 1회만 실행, 두 번째는 저장된 응답(상태·본문 동일, datetime 직렬화 포함)을 재생."""
    from tests.verify_wa import probe_routes
    csrf = login(pclient)
    r1 = _post(pclient, csrf, "key-aaaa-0001", {"amount": 5, "memo": "한글"})
    r2 = _post(pclient, csrf, "key-aaaa-0001", {"amount": 5, "memo": "한글"})
    assert r1.status_code == r2.status_code == 201
    assert r1.json() == r2.json() and r1.json()["count"] == 1
    assert probe_routes.CALLS["charge"] == 1


def test_idem_key_order_insensitive_but_value_sensitive(pclient):
    """TC-VA-069 [S-W12] 본문 키 순서만 다르면 같은 요청(재생), 값이 1 이라도 다르면 422 idempotency_key_reuse(핸들러 미실행)."""
    from tests.verify_wa import probe_routes
    csrf = login(pclient)
    assert _post(pclient, csrf, "key-order-0001", {"a": 1, "b": 2}).status_code == 201
    assert _post(pclient, csrf, "key-order-0001", {"b": 2, "a": 1}).json()["count"] == 1
    r = _post(pclient, csrf, "key-order-0001", {"a": 1, "b": 3})
    assert r.status_code == 422 and r.json()["code"] == "idempotency_key_reuse"
    for variant in ({"a": 1}, {"a": 1, "b": 2, "c": None}, {"a": "1", "b": 2}, {"a": 1.0, "b": 2}):
        rr = _post(pclient, csrf, "key-order-0001", variant)
        assert rr.status_code == 422, variant
    assert probe_routes.CALLS["charge"] == 1


def test_idem_same_key_different_route_is_reuse_error(pclient):
    """TC-VA-070 [S-W12] 같은 키를 다른 라우트에 쓰면 본문이 같아도 422 이고 두 번째 라우트 핸들러는 실행되지 않는다."""
    from tests.verify_wa import probe_routes
    csrf = login(pclient)
    assert _post(pclient, csrf, "key-route-0001", path="/api/v1/_t/charge").status_code == 201
    r = _post(pclient, csrf, "key-route-0001", path="/api/v1/_t/charge2")
    assert r.status_code == 422 and r.json()["code"] == "idempotency_key_reuse"
    assert probe_routes.CALLS.get("charge2", 0) == 0


def test_idem_different_keys_run_separately_and_keys_are_case_sensitive(pclient):
    """TC-VA-071 [S-W12] 서로 다른 키(대소문자만 다른 것 포함)는 각각 실행된다."""
    from tests.verify_wa import probe_routes
    csrf = login(pclient)
    for k in ("key-case-ABCD", "key-case-abcd", "key-case-abcd2"):
        assert _post(pclient, csrf, k).status_code == 201
    assert probe_routes.CALLS["charge"] == 3


def test_idem_failed_handler_does_not_burn_the_key(pclient):
    """TC-VA-072 [S-W12] 핸들러가 실패(409)하면 키가 저장되지 않아 같은 키로 재시도하면 다시 실행된다."""
    from tests.verify_wa import probe_routes
    csrf = login(pclient)
    probe_routes.FAIL_NEXT["flag"] = True
    r1 = _post(pclient, csrf, "key-retry-0001")
    assert r1.status_code == 409
    r2 = _post(pclient, csrf, "key-retry-0001")
    assert r2.status_code == 201 and r2.json()["count"] == 2
    assert _post(pclient, csrf, "key-retry-0001").json()["count"] == 2  # 이제는 재생


def test_idem_replay_crosses_sessions_characterization(pclient, app):
    """TC-VA-073 [S-W12] (특성화) 멱등성 키는 세션과 무관하게 전역이다: 다른 세션이 같은 키+본문을 보내면 첫 응답이 재생된다(단일 소유자 전제)."""
    from tests.verify_wa import probe_routes
    csrf1 = login(pclient)
    r1 = _post(pclient, csrf1, "key-xsess-0001")
    pclient.cookies.clear()
    csrf2 = login(pclient)
    r2 = _post(pclient, csrf2, "key-xsess-0001")
    assert r1.json() == r2.json() and probe_routes.CALLS["charge"] == 1


def test_idem_requires_csrf_before_key_is_stored(pclient, engine):
    """TC-VA-074 [S-W12, S-W03] CSRF/출처 검증에 실패한 요청은 멱등성 키를 저장하지 않는다."""
    csrf = login(pclient)
    r = pclient.post("/api/v1/_t/charge", json={"a": 1}, headers={"Origin": "http://evil.com", "X-CSRF-Token": csrf, "Idempotency-Key": "key-evil-0001"})
    assert r.status_code == 403
    r = pclient.post("/api/v1/_t/charge", json={"a": 1}, headers={"Origin": ORIGIN, "X-CSRF-Token": "bad", "Idempotency-Key": "key-evil-0002"})
    assert r.status_code == 403
    with engine.connect() as c:
        assert c.execute(text("select count(*) from idempotency_keys")).scalar_one() == 0


# ---------------------------------------------------------------- 멱등성(단위, TTL 경계)

T0 = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)


def test_idem_ttl_boundary_exactly_24h_replays_and_one_microsecond_later_reexecutes(db):
    """TC-VA-075 [S-W12] TTL 경계: 정확히 24시간 경과까지는 재생, 24시간+1µs 에는 새로 실행(만료 키 정리)."""
    calls = []

    def h():
        calls.append(1)
        return 201, {"n": len(calls)}
    run = lambda now: run_idempotent(db, key="ttl-key-0001", route="r", request={"x": 1}, now=now, handler=h)  # noqa: E731
    assert run(T0) == (201, {"n": 1})
    assert run(T0 + timedelta(hours=24)) == (201, {"n": 1})
    assert run(T0 + timedelta(hours=24, microseconds=1)) == (201, {"n": 2})
    assert len(calls) == 2


def test_idem_in_progress_row_blocks_with_409_and_other_request_gets_422(db):
    """TC-VA-076 [S-W12] 처리 중(응답 미저장) 키로 같은 요청이 오면 409 in_progress, 다른 요청이면 422(우선순위: 불일치 먼저)."""
    from ytweb.core.canonical import canonical_json, sha256_hex
    db.add(IdempotencyKey(key="busy-key-0001", route="r", request_hash=sha256_hex(canonical_json({"x": 1})), created_at=T0))
    db.flush()
    with pytest.raises(ProblemError) as e1:
        run_idempotent(db, key="busy-key-0001", route="r", request={"x": 1}, now=T0, handler=lambda: (200, {}))
    assert e1.value.status == 409 and e1.value.code == "idempotency_in_progress"
    with pytest.raises(ProblemError) as e2:
        run_idempotent(db, key="busy-key-0001", route="r", request={"x": 2}, now=T0, handler=lambda: (200, {}))
    assert e2.value.status == 422


def test_idem_not_required_mode_runs_handler_every_time(db):
    """TC-VA-077 [S-W12] required=False 이고 키가 없으면 멱등성 없이 매번 실행(키가 있으면 일반 규칙)."""
    n = []
    for _ in range(3):
        run_idempotent(db, key=None, route="r", request={}, now=T0, handler=lambda: (n.append(1), (200, {}))[1], required=False)
    assert len(n) == 3


@pytest.mark.parametrize("key", ["abcdéfgh", "키키키키키키키키", "abcd\u200befgh", "ａｂｃｄｅｆｇｈ"])
def test_idem_key_non_ascii_rejected_unit(db, key):
    """TC-VA-078 [S-W12] 비ASCII(악센트·한글·제로폭·전각) 키는 400 idempotency_key_invalid (HTTP 헤더로는 못 보내므로 단위 수준에서 확인)."""
    with pytest.raises(ProblemError) as e:
        run_idempotent(db, key=key, route="r", request={}, now=T0, handler=lambda: (200, {}))
    assert e.value.status == 400 and e.value.code == "idempotency_key_invalid"


def test_idem_key_trailing_newline_rejected_unit(db):
    """TC-VA-079 [S-W12] 끝에 줄바꿈이 붙은 키는 형식 위반이어야 한다."""
    with pytest.raises(ProblemError) as e:
        run_idempotent(db, key="abcdefgh\n", route="r", request={}, now=T0, handler=lambda: (200, {}))
    assert e.value.code == "idempotency_key_invalid"
