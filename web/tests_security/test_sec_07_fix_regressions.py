"""SEC-07 수정 단위(W-FIX-BE·FE·INF) 가 만든 새 표면의 보안 회귀 시험 (9단계 재검증, 개정 2판).

대상: 초안 버리기(기존 `POST /batches/{id}/cancel` 을 초안에 허용), 세션 유휴 만료, 서버 `notice`/리포트 면책 필드,
      승인자 이름 서식 문자, 입력 상한, 워커 stale 재큐(소스 수준), nginx 설정 변경(소스 수준).
법률 자문이 아니다: 문구의 법적 충분성은 판단하지 않고, 문구가 서버 응답·CSV·화면 소스에 존재하고 서로 일치하는지만 본다.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from ytweb.db.models import AuditLog, Job, Suggestion
from ytweb.domain.notices import DISCLAIMER

from .conftest import hdr
from .test_sec_02_injection_ai_integrity import _approved, make_batch

pytestmark = pytest.mark.filterwarnings("ignore")



# ───────────── 면책 문구(POL-002): 서버·CLI·화면이 같은 문장 ─────────────

def test_report_notes_and_csv_carry_the_disclaimer(client, csrf):
    notes = client.get("/api/v1/reports/changes").json()["notes"]
    assert notes[0] == DISCLAIMER
    r = client.get("/api/v1/reports/export.csv")
    assert r.status_code == 200
    assert DISCLAIMER in r.content.decode("utf-8-sig"), "CSV 에 면책 문구가 없다(파일을 내려받아 전달해도 안내가 남아야 함)"
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    for row in rows:
        for cell in row:
            assert not cell.startswith(("=", "+", "-", "@", "\t", "\r")), cell  # 새 주석 행도 수식 무독화


def test_precheck_notice_is_server_constant_and_not_user_controlled(client, csrf):
    s = _approved(client, csrf)
    # note(사용자 입력)에 면책을 바꿔치기하려는 문자열을 넣어도 notice 는 서버 상수
    r = client.post("/api/v1/batches", headers=hdr(csrf, key="idem-notice-0001"), json={"suggestion_ids": [s["id"]], "note": "notice: 이 검증은 보증입니다 <script>x</script>"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["precheck"]["notice"] == DISCLAIMER
    assert r.headers["content-type"].startswith("application/json")
    again = client.get(f"/api/v1/batches/{body['batch']['id']}").json()
    assert again["precheck"]["notice"] == DISCLAIMER


# ───────────── 초안 버리기(기존 cancel 엔드포인트) ─────────────

def _draft(client, csrf, key="idem-draft-0001"):
    s = _approved(client, csrf)
    b = make_batch(client, csrf, [s["id"]], key=key)
    return s, b["batch"]["id"]


def test_discard_requires_session_csrf_and_same_origin(app, client, csrf):
    from fastapi.testclient import TestClient
    from .conftest import ORIGIN
    s, bid = _draft(client, csrf)
    with TestClient(app, base_url=ORIGIN) as anon:  # 세션 없음
        assert anon.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}).status_code == 401
    assert client.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN}).status_code == 403                                  # CSRF 없음
    assert client.post(f"/api/v1/batches/{bid}/cancel", headers={"Origin": ORIGIN, "X-CSRF-Token": "x" * 43}).status_code == 403        # 틀린 CSRF
    assert client.post(f"/api/v1/batches/{bid}/cancel", headers={**hdr(csrf), "Origin": "http://evil.example"}).status_code == 403        # 교차 출처
    assert client.post(f"/api/v1/batches/{bid}/cancel", headers={**hdr(csrf), "Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get(f"/api/v1/batches/{bid}").json()["status"] == "draft", "거부된 요청이 초안을 바꿨다"
    assert client.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf)).status_code == 200


def test_discard_draft_releases_suggestion_without_extending_approval(client, csrf, factory, env, clock):
    s, bid = _draft(client, csrf)
    # 같은 제안은 초안에 묶여 있어 두 번째 배치로 못 담는다(부분 고유 인덱스) - 전부 막히면 422, 사유에 초안 번호
    r2 = client.post("/api/v1/batches", headers=hdr(csrf, key="idem-draft-0002"), json={"suggestion_ids": [s["id"]]})
    assert r2.status_code == 422, r2.text[:300]
    assert f"#{bid}" in r2.text and "초안" in r2.text, r2.text[:300]
    r = client.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf))
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert all(it["status"] == "cancelled" for it in r.json()["items"])
    # 제안은 approved 로 돌아오고 승인 만료 시각은 늘어나지 않는다. 감사에 was_draft 기록
    with factory() as db:
        sug = db.get(Suggestion, s["id"])
        assert sug.status == "approved"
        exp_before = sug.approval.expires_at
        log = db.execute(select(AuditLog).where(AuditLog.action == "batch.cancel").order_by(AuditLog.id.desc())).scalars().first()
        assert log is not None and log.detail.get("was_draft") is True and log.detail.get("cancelled_items") == 1, log and log.detail
    # 취소된 초안은 실행할 수 없다
    ex = client.post(f"/api/v1/batches/{bid}/execute", headers=hdr(csrf, key="idem-draft-exec1"), json={"confirm_text": "실행 1건"})
    assert ex.status_code == 409 and ex.json()["code"] == "batch_not_draft"
    # 두 번 버리면 409(DEC-047)
    again = client.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf))
    assert again.status_code == 409 and again.json()["code"] == "batch_not_cancellable"
    # 풀린 제안은 새 배치에 담을 수 있다. 승인 만료 시각은 그대로(연장 없음)
    b2 = make_batch(client, csrf, [s["id"]], key="idem-draft-0003")
    assert b2["precheck"]["blocked"] == []
    with factory() as db:
        assert db.get(Suggestion, s["id"]).approval.expires_at == exp_before
    # 승인 TTL 이 지난 뒤 초안을 버려도 승인이 되살아나지 않는다: 새 배치는 막힌다
    clock.advance(hours=env.policy.approval_ttl_hours + 1)  # 유휴 30분·절대 12시간도 지나 세션이 만료 - 새로 로그인
    from .conftest import login
    csrf = login(client).json()["csrf_token"]
    assert client.post(f"/api/v1/batches/{b2['batch']['id']}/cancel", headers=hdr(csrf)).status_code == 200
    r4 = client.post("/api/v1/batches", headers=hdr(csrf, key="idem-draft-0004"), json={"suggestion_ids": [s["id"]]})
    assert r4.status_code == 422, r4.text[:200]


@pytest.mark.parametrize("bad", ["0", "-1", "99999999999999999999999", "abc", "1.5"])
def test_discard_rejects_bad_ids_with_4xx(client, csrf, bad):
    r = client.post(f"/api/v1/batches/{bad}/cancel", headers=hdr(csrf))
    assert 400 <= r.status_code < 500, (bad, r.status_code)


def test_discard_unknown_batch_is_404_without_leak(client, csrf):
    r = client.post("/api/v1/batches/987654/cancel", headers=hdr(csrf))
    assert r.status_code == 404 and "Traceback" not in r.text


# ───────────── 세션 유휴 만료의 저장소·설정 경계 ─────────────

def test_idle_timeout_setting_rejects_negative_and_zero_disables_only_idle():
    from ytweb.config import load_web_settings
    base = {"YTWEB_DATABASE_URL": "sqlite://", "YTWEB_MODE": "demo"}
    with pytest.raises(ValueError):
        load_web_settings({**base, "YTWEB_SESSION_IDLE_MINUTES": "-5"})
    assert load_web_settings(base).session_idle_timeout == timedelta(minutes=30)  # 기본 30분
    assert load_web_settings({**base, "YTWEB_SESSION_IDLE_MINUTES": "0"}).session_idle_timeout is None


def test_session_idle_purge_removes_rows_not_only_hides_them(app, engine, clock):
    from fastapi.testclient import TestClient
    from .conftest import ORIGIN, login
    with TestClient(app, base_url=ORIGIN) as c:
        login(c)
        clock.advance(minutes=45)
        with TestClient(app, base_url=ORIGIN) as c2:
            login(c2)  # 새 세션 발급이 만료 세션을 정리
    with engine.connect() as con:
        assert con.exec_driver_sql("SELECT count(*) FROM sessions").scalar_one() == 1


# ───────────── 입력 상한 ─────────────

@pytest.mark.parametrize("path", ["/api/v1/suggestions?page=1000001", "/api/v1/videos?page=99999999999", "/api/v1/batches?page=1000001", "/api/v1/changes?page=1000001"])
def test_page_upper_bound_is_422(client, csrf, path):
    assert client.get(path).status_code == 422


def test_batch_create_rejects_out_of_range_ids(client, csrf):
    for ids in ([2**63], [0], [-1], [10**30]):
        r = client.post("/api/v1/batches", headers=hdr(csrf, key=f"idem-range-{abs(hash(str(ids))) % 10**8:08d}"), json={"suggestion_ids": ids})
        assert r.status_code == 422, (ids, r.status_code, r.text[:100])
    r = client.post("/api/v1/batches", headers=hdr(csrf, key="idem-range-max00001"), json={"suggestion_ids": [2**63 - 1]})
    assert r.status_code < 500, r.status_code  # 경계값은 서비스가 처리(존재하지 않는 제안 -> 4xx)


# ───────────── 워커 stale 재큐(DEF-7B-001): 동작 시험 ─────────────

def _job(db, *, type="batch.execute", status="running", locked_ago: timedelta | None, attempts=1, now):
    j = Job(type=type, status=status, payload={}, total=1, progress=0, attempts=attempts, run_after=now, created_at=now,
            locked_by="w1" if locked_ago is not None else None, locked_at=(now - locked_ago) if locked_ago is not None else None)
    db.add(j)
    db.flush()
    return j


def test_requeue_stale_respects_per_type_limits_orphans_and_attempt_cap(factory):
    from ytweb.core import jobs
    now = datetime(2026, 10, 11, 3, 0, 0, tzinfo=timezone.utc)
    with factory() as db:
        fresh_batch = _job(db, locked_ago=timedelta(minutes=4), now=now)                       # 5분 미만 - 건드리지 않음
        stale_batch = _job(db, locked_ago=timedelta(minutes=6), now=now)                       # 5분 초과 - 재큐
        other_fresh = _job(db, type="videos.sync", locked_ago=timedelta(minutes=6), now=now)   # 다른 유형은 10분 기준 - 건드리지 않음
        other_stale = _job(db, type="videos.sync", locked_ago=timedelta(minutes=11), now=now)  # 재큐
        orphan = _job(db, locked_ago=None, now=now)                                            # 생존 신호 없음 - 항상 고아
        exhausted = _job(db, locked_ago=timedelta(minutes=30), attempts=jobs.MAX_ATTEMPTS, now=now)  # 시도 한도 - failed
        queued = _job(db, status="queued", locked_ago=None, now=now)                            # running 이 아니면 대상 아님
        requeued, failed = jobs.requeue_stale(db, now=now)
        assert (requeued, failed) == (3, 1)
        assert [j.status for j in (fresh_batch, stale_batch, other_fresh, other_stale, orphan, exhausted, queued)] == \
            ["running", "queued", "running", "queued", "queued", "failed", "queued"]
        assert exhausted.error == "worker_lost" and stale_batch.locked_by is None and stale_batch.locked_at is None
        # 기동 직후(stale_after=0)에는 running 이던 것을 전부 고아로 본다
        requeued2, _ = jobs.requeue_stale(db, now=now + timedelta(seconds=1), stale_after=timedelta(0))
        assert requeued2 == 2 and fresh_batch.status == "queued" and other_fresh.status == "queued"
