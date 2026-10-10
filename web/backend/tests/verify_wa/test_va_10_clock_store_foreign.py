"""TC-VA-144~: 시각 경계(KST/PT), 설정 저장소, 외부 출처 별도 한도(DEF-6-003 수정 확인) — 독립 검증 보강."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from tests.conftest import CORE_ROUTERS, ORIGIN
from tests.verify_wa.helpers import asgi_call, body_json
from ytweb.app import create_app
from ytweb.core import clock as ck
from ytweb.core.ratelimit import RateLimiter, RateLimits
from ytweb.core.settings_store import (DEFAULT_DAILY_APPLY_CAP, delete_web_setting, effective_daily_cap,
                                       get_web_setting, set_web_setting)
from ytweb.db.models import SettingKV

U = timezone.utc
H = [("host", "127.0.0.1:8080")]


@pytest.mark.parametrize("utc,kst", [
    (datetime(2026, 10, 10, 14, 59, 59, 999999, tzinfo=U), date(2026, 10, 10)),
    (datetime(2026, 10, 10, 15, 0, 0, tzinfo=U), date(2026, 10, 11)),
    (datetime(2026, 12, 31, 15, 0, 0, tzinfo=U), date(2027, 1, 1)),
    (datetime(2028, 2, 28, 15, 0, 0, tzinfo=U), date(2028, 2, 29)),   # 윤일
    (datetime(2028, 2, 29, 14, 59, 59, tzinfo=U), date(2028, 2, 29)),
    (datetime(2026, 10, 10, 0, 0, 0, tzinfo=U), date(2026, 10, 10)),
])
def test_kst_today_boundaries(utc, kst):
    """TC-VA-144 [시각] KST 날짜는 UTC 15:00 에 바뀐다(마이크로초 경계·연말·윤일 포함)."""
    assert ck.kst_today(utc) == kst


@pytest.mark.parametrize("utc,pt", [
    (datetime(2026, 7, 1, 6, 59, 59, tzinfo=U), date(2026, 6, 30)),    # PDT(UTC-7): 07:00Z 가 자정
    (datetime(2026, 7, 1, 7, 0, 0, tzinfo=U), date(2026, 7, 1)),
    (datetime(2026, 1, 1, 7, 59, 59, tzinfo=U), date(2025, 12, 31)),   # PST(UTC-8): 08:00Z 가 자정
    (datetime(2026, 1, 1, 8, 0, 0, tzinfo=U), date(2026, 1, 1)),
    (datetime(2026, 3, 8, 7, 59, 59, tzinfo=U), date(2026, 3, 7)),     # 봄 전환일: 전날 자정은 PST(08:00Z)
    (datetime(2026, 3, 8, 9, 59, 59, tzinfo=U), date(2026, 3, 8)),     # 전환(10:00Z) 직전도 아직 3/8
    (datetime(2026, 3, 8, 8, 0, 0, tzinfo=U), date(2026, 3, 8)),
    (datetime(2026, 3, 9, 6, 59, 59, tzinfo=U), date(2026, 3, 8)),     # 전환 후 PDT: 다음 자정은 07:00Z
    (datetime(2026, 3, 9, 7, 0, 0, tzinfo=U), date(2026, 3, 9)),
    (datetime(2026, 11, 1, 6, 59, 59, tzinfo=U), date(2026, 10, 31)),  # 가을 전환일: 자정은 아직 PDT(07:00Z)
    (datetime(2026, 11, 1, 7, 0, 0, tzinfo=U), date(2026, 11, 1)),
    (datetime(2026, 11, 2, 7, 59, 59, tzinfo=U), date(2026, 11, 1)),   # 전환 후 PST: 다음 자정은 08:00Z
    (datetime(2026, 11, 2, 8, 0, 0, tzinfo=U), date(2026, 11, 2)),
])
def test_pt_date_boundaries_incl_dst(utc, pt):
    """TC-VA-145 [시각] 태평양 날짜는 PST/PDT 전환(2026-03-08, 2026-11-01) 전후로 정확히 바뀐다."""
    assert ck.pt_date(utc) == pt


def test_clock_accepts_other_tz_and_rejects_naive():
    """TC-VA-146 [시각] 다른 시간대로 표현된 같은 순간은 같은 날짜, naive 는 ValueError(조용히 로컬 시각으로 해석하지 않음)."""
    kst = timezone(timedelta(hours=9))
    assert ck.kst_today(datetime(2026, 10, 11, 0, 0, tzinfo=kst)) == date(2026, 10, 11)
    assert ck.kst_today(datetime(2026, 10, 10, 23, 59, 59, tzinfo=kst)) == date(2026, 10, 10)
    for fn in (ck.kst_today, ck.pt_date):
        with pytest.raises(ValueError):
            fn(datetime(2026, 10, 10, 12, 0))
    assert ck.utcnow().tzinfo is not None and abs((ck.utcnow() - datetime.now(U)).total_seconds()) < 5


@pytest.mark.parametrize("stored,expected", [
    (1, 1), (20, 20), (7, 7),
    (0, DEFAULT_DAILY_APPLY_CAP), (21, DEFAULT_DAILY_APPLY_CAP), (-1, DEFAULT_DAILY_APPLY_CAP),
    (True, DEFAULT_DAILY_APPLY_CAP), ("5", DEFAULT_DAILY_APPLY_CAP),
    (None, DEFAULT_DAILY_APPLY_CAP), ([5], DEFAULT_DAILY_APPLY_CAP), (10**30, DEFAULT_DAILY_APPLY_CAP),
])
def test_effective_daily_cap_clamps_corrupt_values(db, stored, expected):
    """TC-VA-147 [S-W13] 저장소의 일일 한도가 손상돼도(범위 밖·bool·문자열·null) 안전한 기본값 10 으로 돌아가고, 1/20 경계는 그대로다."""
    if stored is not None:
        set_web_setting(db, "daily_apply_cap", stored, now=datetime(2026, 10, 10, tzinfo=U))
    db.flush()
    assert effective_daily_cap(db, policy=None) == expected  # policy 는 사용하지 않는다(설계: DB 값만)


def test_effective_daily_cap_default_when_missing(db):
    """TC-VA-148 [S-W13] 값이 없으면 기본 10."""
    assert effective_daily_cap(db, policy=None) == 10


def test_settings_store_set_update_delete_and_default(db):
    """TC-VA-149 설정 저장소: 없는 키는 기본값, set 은 삽입→갱신(updated_at 갱신), delete 는 없는 키에도 안전."""
    t1, t2 = datetime(2026, 10, 10, 1, tzinfo=U), datetime(2026, 10, 10, 2, tzinfo=U)
    assert get_web_setting(db, "k") is None and get_web_setting(db, "k", 5) == 5
    set_web_setting(db, "k", {"a": [1]}, now=t1)
    set_web_setting(db, "k", {"a": [2]}, now=t2)
    row = db.get(SettingKV, "k")
    assert row.value == {"a": [2]} and row.updated_at == t2
    assert get_web_setting(db, "k", 5) == {"a": [2]}
    delete_web_setting(db, "k")
    delete_web_setting(db, "k")
    assert get_web_setting(db, "k", "d") == "d"


def test_get_web_setting_returns_stored_falsy_values(db):
    """TC-VA-150 저장된 값이 0/빈 목록/False 여도 기본값으로 바뀌지 않는다(None 과 구분)."""
    for v in (0, [], False, ""):
        set_web_setting(db, "z", v, now=datetime(2026, 10, 10, tzinfo=U))
        assert get_web_setting(db, "z", "DEFAULT") == v


def _app(web_settings, clock, fake_time, **lim):
    return create_app(web_settings, clock=clock, router_modules=CORE_ROUTERS, time_fn=fake_time, rate_limits=RateLimits(**lim))


def test_foreign_requests_have_own_bucket_and_are_still_limited(web_settings, engine, clock, fake_time):
    """TC-VA-151 [S-W13, DEF-6-003 수정] 외부 사이트 요청은 소유자 한도를 쓰지 않지만 자기 창에서는 제한(N+1 번째 429)되고 창이 지나면 풀린다."""
    app = _app(web_settings, clock, fake_time, global_per_min=3, write_per_min=100, auth_per_min=100)
    evil = H + [("origin", "http://evil.com"), ("sec-fetch-site", "cross-site")]
    st = [asgi_call(app, "POST", "/api/v1/auth/session", evil, [b""])["status"] for _ in range(4)]
    assert st == [403, 403, 403, 429]
    for _ in range(3):  # 소유자 한도(3)는 그대로 남아 있다
        assert asgi_call(app, "GET", "/api/v1/auth/me", H + [("sec-fetch-site", "same-origin")])["status"] == 200
    assert asgi_call(app, "GET", "/api/v1/auth/me", H)["status"] == 429
    fake_time.t += 60
    assert asgi_call(app, "POST", "/api/v1/auth/session", evil, [b""])["status"] == 403


@pytest.mark.parametrize("sec,expect_foreign", [
    ("same-origin", False), ("none", False), ("SAME-ORIGIN", False), (" same-origin ", False),
    ("same-site", True), ("cross-site", True), ("", True), ("bogus", True),
])
def test_foreign_classification_by_sec_fetch_site(web_settings, engine, clock, fake_time, sec, expect_foreign):
    """TC-VA-152 외부 출처 분류 경계: 한도 1 로 두고 '소유자 요청 1건 + 대상 요청 1건' 을 보냈을 때, 외부로 분류된 것만 소유자 한도를 안 쓴다."""
    app = _app(web_settings, clock, fake_time, global_per_min=1, write_per_min=100, auth_per_min=100)
    r1 = asgi_call(app, "GET", "/api/v1/auth/me", H + [("sec-fetch-site", sec)])["status"]
    r2 = asgi_call(app, "GET", "/api/v1/auth/me", H)["status"]
    assert r1 == 200
    assert (r2 == 200) == expect_foreign


def test_post_with_bad_origin_is_foreign_even_without_sec_fetch(web_settings, engine, clock, fake_time):
    """TC-VA-153 Sec-Fetch-Site 없이 Origin 만 틀린/없는 상태 변경 요청도 외부 분류 -> 소유자 한도를 쓰지 않는다. 올바른 Origin 은 쓴다."""
    app = _app(web_settings, clock, fake_time, global_per_min=4, write_per_min=100, auth_per_min=100)
    for origin in ([], [("origin", "null")], [("origin", "http://127.0.0.1:9999")]):
        assert asgi_call(app, "POST", "/api/v1/auth/session", H + origin, [b""])["status"] == 403
    st = [asgi_call(app, "POST", "/api/v1/auth/session", H + [("origin", ORIGIN)], [b""])["status"] for _ in range(5)]
    assert st == [200, 200, 200, 200, 429]


def test_ratelimiter_check_foreign_unit():
    """TC-VA-154 RateLimiter.check_foreign: 한도 N 번째까지 0, 다음은 양수 대기, 거부는 기록되지 않아 정확히 창 길이 뒤 풀림."""
    t = [0.0]
    rl = RateLimiter(RateLimits(global_per_min=2), time_fn=lambda: t[0])
    assert rl.check_foreign() == 0 and rl.check_foreign() == 0
    w = rl.check_foreign()
    assert 0 < w <= 60
    t[0] = 59.99
    assert rl.check_foreign() > 0
    t[0] = 60.0
    assert rl.check_foreign() == 0
    assert rl.check("GET", "/api/x") == 0  # 소유자 버킷은 별개


def test_duplicate_or_conflicting_content_length_rejected(app):
    """TC-VA-155 [S-W13] Content-Length 가 두 번 오면(값이 같아도) 400 — 요청 밀수 방어."""
    out = asgi_call(app, "POST", "/api/v1/auth/session", H + [("origin", ORIGIN), ("content-length", "2"), ("content-length", "2")], [b"{}"])
    assert out["status"] == 400 and body_json(out)["code"] == "bad_content_length"


def test_duplicate_host_same_value_rejected_but_health_exempt(app):
    """TC-VA-156 [S-W02] 같은 값의 Host 가 두 번이어도 API 는 거부(정확히 1개만 허용)한다. 헬스 경로는 면제."""
    two = [("host", "127.0.0.1:8080"), ("host", "127.0.0.1:8080")]
    assert asgi_call(app, "GET", "/api/v1/auth/me", two)["status"] == 403
    assert asgi_call(app, "GET", "/healthz", two)["status"] == 200


@pytest.mark.parametrize("cl", ["", " ", "1 2", "\xb2", "\xb9", "0x10", "1e3"])
def test_content_length_non_ascii_digits_rejected(app, cl):
    """TC-VA-157 [S-W13] 빈 값·공백·유니코드 숫자(위첨자 ²·¹ 은 isdigit() 가 True)·16진·지수 표기 Content-Length 는 400(str.isdigit 는 유니코드 숫자도 True 이므로 isascii 병행 필요)."""
    out = asgi_call(app, "GET", "/api/v1/auth/me", H + [("content-length", cl)])
    assert out["status"] == 400


def test_content_length_zero_and_leading_zeros_accepted(app):
    """TC-VA-158 Content-Length '0' 과 '0000000010' 같은 선행 0 은 유효 숫자다(과잉 차단 방지)."""
    assert asgi_call(app, "GET", "/api/v1/auth/me", H + [("content-length", "0")])["status"] == 200
    assert asgi_call(app, "GET", "/api/v1/auth/me", H + [("content-length", "0000000010")], [b"x" * 10])["status"] == 200
