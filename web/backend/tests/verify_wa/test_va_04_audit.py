"""독립 점검 4: 감사 해시 체인 (S-W16)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from tests.verify_wa.helpers import hdr, login
from ytweb.core import audit
from ytweb.db.models import AuditLog

T0 = datetime(2026, 10, 10, 3, 0, 0, 123456, tzinfo=timezone.utc)
GENESIS = "0" * 64


def ref_hash(prev: str, ts: datetime, actor, action, ttype, tid, detail) -> str:
    """명세(단위 노트 3-8)에서 독립적으로 다시 쓴 기준 구현. 구현 코드의 함수를 호출하지 않는다."""
    body = json.dumps(
        {"ts": ts.astimezone(timezone.utc).isoformat(timespec="microseconds"), "actor": actor, "action": action,
         "target": {"type": ttype, "id": tid}, "detail": detail},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256((prev + body).encode("utf-8")).hexdigest()


def seed(db, n=6):
    rows = []
    for i in range(n):
        rows.append(audit.record(db, actor="owner", action=f"act.{i}", target_type="video" if i % 2 else None,
                                 target_id=f"id{i}" if i % 2 else None, detail={"i": i, "z": {"b": [1, 2], "a": "한글🙂"}},
                                 now=T0 + timedelta(seconds=i)))
    db.commit()
    return [r.id for r in rows]


def test_chain_matches_independent_reference_implementation(db):
    """TC-VA-@@@ [S-W16] 저장된 해시가 명세로 독립 재구현한 sha256(prev+정규 JSON) 값과 모두 일치하고 첫 prev 는 0*64 이다(유니코드·중첩·None 포함)."""
    seed(db, 6)
    prev = GENESIS
    rows = db.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
    assert len(rows) == 6
    for r in rows:
        assert r.prev_hash == prev
        assert r.hash == ref_hash(prev, r.ts, r.actor, r.action, r.target_type, r.target_id, r.detail)
        prev = r.hash
    assert audit.verify_chain(db) is True


def test_empty_log_verifies_true(db):
    """TC-VA-@@@ [S-W16] 빈 로그는 체인 유효(True)로 본다(초기 상태)."""
    assert audit.verify_chain(db) is True


def test_non_utc_timezone_hashes_same_as_utc_and_naive_rejected(db):
    """TC-VA-@@@ [S-W16] 시각은 UTC 로 정규화되어 해시되고(KST 입력도 같은 해시), naive datetime 은 ValueError."""
    kst = timezone(timedelta(hours=9))
    a = audit.record(db, actor="o", action="x", detail={}, now=T0)
    b_prev = a.hash
    b = audit.record(db, actor="o", action="y", detail={}, now=T0.astimezone(kst))
    assert b.hash == ref_hash(b_prev, T0, "o", "y", None, None, {})
    with pytest.raises(ValueError):
        audit.record(db, actor="o", action="z", detail={}, now=datetime(2026, 1, 1))


def _mutate(db, fn):
    fn(db)
    db.commit()
    db.expire_all()


def _row(db, idx):
    return db.execute(select(AuditLog).order_by(AuditLog.id).offset(idx).limit(1)).scalar_one()


def _flip(h: str) -> str:
    return ("0" if h[0] != "0" else "1") + h[1:]


def m_actor(db): _row(db, 2).actor = "attacker"
def m_action(db): _row(db, 2).action = "act.forged"
def m_detail(db): r = _row(db, 2); r.detail = {**r.detail, "i": 999}
def m_detail_nested(db): r = _row(db, 2); d = json.loads(json.dumps(r.detail)); d["z"]["b"] = [1, 2, 3]; r.detail = d
def m_ts_1us(db): r = _row(db, 2); r.ts = r.ts + timedelta(microseconds=1)
def m_ttype(db): _row(db, 1).target_type = "other"
def m_tid_none_to_x(db): _row(db, 2).target_id = "x"
def m_hash(db): r = _row(db, 3); r.hash = _flip(r.hash)
def m_prev(db): r = _row(db, 3); r.prev_hash = _flip(r.prev_hash)
def m_genesis(db): r = _row(db, 0); r.prev_hash = "1" * 64
def m_delete_middle(db): db.delete(_row(db, 2))
def m_delete_first(db): db.delete(_row(db, 0))
def m_delete_two_middle(db): db.delete(_row(db, 2)); db.delete(_row(db, 3))


def m_reorder(db):
    a, b = _row(db, 2), _row(db, 3)
    ida, idb = a.id, b.id
    db.execute(text("update audit_log set id = -1 where id = :a"), {"a": ida})
    db.execute(text("update audit_log set id = :a where id = :b"), {"a": ida, "b": idb})
    db.execute(text("update audit_log set id = :b where id = -1"), {"b": idb})


def m_forged_append_bad_link(db):
    db.add(AuditLog(ts=T0 + timedelta(hours=1), actor="x", action="forged", detail={}, prev_hash="f" * 64, hash="e" * 64))


def m_rewrite_row_keep_next_prev(db):
    """행 3의 내용을 바꾸고 그 행의 해시만 올바르게 다시 계산(다음 행 prev_hash 는 그대로)."""
    r = _row(db, 3)
    r.actor = "attacker"
    r.hash = ref_hash(r.prev_hash, r.ts, r.actor, r.action, r.target_type, r.target_id, r.detail)


def m_rewrite_row_fix_next_prev_only(db):
    """행 3의 내용+해시를 고치고, 다음 행의 prev_hash 도 새 해시로 맞춘다(다음 행 해시는 그대로) -> 해시가 prev 를 포함해야만 탐지된다."""
    r, nxt = _row(db, 3), _row(db, 4)
    r.actor = "attacker"
    r.hash = ref_hash(r.prev_hash, r.ts, r.actor, r.action, r.target_type, r.target_id, r.detail)
    nxt.prev_hash = r.hash


MUTATIONS = [m_actor, m_action, m_detail, m_detail_nested, m_ts_1us, m_ttype, m_tid_none_to_x, m_hash, m_prev, m_genesis,
             m_delete_middle, m_delete_first, m_delete_two_middle, m_reorder, m_forged_append_bad_link,
             m_rewrite_row_keep_next_prev, m_rewrite_row_fix_next_prev_only]


@pytest.mark.parametrize("mut", MUTATIONS, ids=lambda f: f.__name__)
def test_tamper_detected_by_verify_and_api(db, client, mut):
    """TC-VA-@@@ [S-W16] 변조 17종(내용 수정·1µs 시각 변경·해시/prev 변경·중간/첫 행 삭제·순서 바꾸기·위조 행 추가·해시 재계산 위장)은 verify_chain=False, API chain_ok=false."""
    seed(db, 6)
    login(client)
    assert client.get("/api/v1/audit").json()["chain_ok"] is True  # 로그인 행이 이어 붙은 뒤에도 유효
    db.expire_all()
    assert audit.verify_chain(db) is True  # 변조 전 유효성부터 확인
    _mutate(db, mut)
    assert audit.verify_chain(db) is False, mut.__name__
    assert client.get("/api/v1/audit").json()["chain_ok"] is False


def test_known_limits_tail_truncation_and_full_rewrite_are_not_detected(db):
    """TC-VA-@@@ [S-W16] (알려진 제한 특성화) 꼬리 절단·전체 삭제·키 없는 해시로 처음부터 다시 쓴 체인은 verify_chain 으로 탐지되지 않는다 -> DB 권한(UPDATE/DELETE/TRUNCATE 회수)이 유일한 방어선."""
    ids = seed(db, 6)
    db.delete(_row(db, 5))  # 마지막 행 삭제
    db.commit()
    assert audit.verify_chain(db) is True  # 탐지 불가(문서화된 제한)
    for _ in range(3):
        n = db.execute(text("select count(*) from audit_log")).scalar_one()
        db.delete(_row(db, n - 1))
        db.flush()
    db.commit()
    assert db.execute(text("select count(*) from audit_log")).scalar_one() == 2
    assert audit.verify_chain(db) is True
    # 위조 행을 올바른 해시로 이어 붙이면(INSERT 권한만 있으면 가능) 정상으로 보인다: 해시는 키가 없다.
    last = _row(db, 1)
    forged = AuditLog(ts=T0 + timedelta(days=1), actor="attacker", action="forged", detail={}, prev_hash=last.hash,
                      hash=ref_hash(last.hash, T0 + timedelta(days=1), "attacker", "forged", None, None, {}))
    db.add(forged)
    db.commit()
    assert audit.verify_chain(db) is True
    db.execute(text("delete from audit_log"))
    db.commit()
    assert audit.verify_chain(db) is True
    assert ids


def test_audit_api_requires_session_and_paginates_newest_first(client, db):
    """TC-VA-@@@ [S-W16] 감사 조회는 세션 필수(401). 페이지 경계: page_size 1·200 허용, 0·201 은 422, 범위 밖 page 는 빈 목록, 최신순."""
    assert client.get("/api/v1/audit").status_code == 401
    login(client)
    seed(db, 7)
    r = client.get("/api/v1/audit", params={"page": 1, "page_size": 3}).json()
    assert r["page"] == 1 and r["page_size"] == 3 and len(r["items"]) == 3
    ids = [i["id"] for i in r["items"]]
    assert ids == sorted(ids, reverse=True)
    total = r["total"]
    assert client.get("/api/v1/audit", params={"page_size": 200}).status_code == 200
    for bad in ({"page_size": 0}, {"page_size": 201}, {"page": 0}, {"page": -1}, {"page": "x"}, {"page_size": "1 OR 1=1"}, {"page": "1;DROP TABLE audit_log"}):
        assert client.get("/api/v1/audit", params=bad).status_code == 422, bad
    far = client.get("/api/v1/audit", params={"page": 10_000, "page_size": 200}).json()
    assert far["items"] == [] and far["total"] == total
    with db.get_bind().connect() as c:
        assert c.execute(text("select count(*) from audit_log")).scalar_one() == total  # 주입 시도가 테이블을 건드리지 않음


@pytest.mark.xfail(strict=True, reason="DEF-6-005: page 상한이 없어 offset 이 64비트를 넘으면 DB 오류로 500 (SQLite OverflowError / PostgreSQL bigint 범위 오류)")
@pytest.mark.parametrize("page", [10**18, 2**63])
def test_audit_huge_page_does_not_500(client, page):
    """TC-VA-@@@ [S-W13] 매우 큰 page 값은 빈 목록(200) 또는 422 여야 하며 500 이면 안 된다."""
    login(client)
    r = client.get("/api/v1/audit", params={"page": page, "page_size": 200})
    assert r.status_code in (200, 422)


def test_security_events_land_in_audit_with_expected_actions(client, db):
    """TC-VA-@@@ [S-W16] 로그인·로그아웃·설정변경·로그인 거부가 순서대로 감사에 남고 체인이 유효하다."""
    csrf = login(client)
    client.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "2468"}}, headers=hdr(csrf))
    client.delete("/api/v1/auth/session", headers=hdr(csrf))
    client.post("/api/v1/auth/session", json={"pin": "0000"}, headers={"Origin": "http://127.0.0.1:8080"})
    acts = [a for (a,) in db.execute(select(AuditLog.action).order_by(AuditLog.id))]
    assert acts == ["session.create", "settings.update", "session.delete", "session.denied"]
    assert audit.verify_chain(db) is True
