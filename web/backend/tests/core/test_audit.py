"""감사 로그 해시 체인."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, select, update

from tests.conftest import hdr
from ytweb.core import audit
from ytweb.db.models import AuditLog

T0 = datetime(2026, 10, 10, 3, 0, 0, 123456, tzinfo=timezone.utc)


def _fill(db, n=4):
    for i in range(n):
        audit.record(db, actor="owner", action=f"test.act{i}", target_type="thing", target_id=str(i),
                     detail={"한글": "값", "i": i, "nested": {"b": 1, "a": [1, 2]}}, now=T0 + timedelta(seconds=i))
    db.commit()


def test_empty_chain_is_valid(db):
    """TC-WA-073 비어 있는 체인은 유효."""
    assert audit.verify_chain(db) is True


def test_chain_links_and_verifies(db):
    """TC-WA-074 각 행의 prev_hash 는 직전 행의 hash 이고 첫 행은 0*64, verify_chain 은 True."""
    _fill(db)
    rows = db.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
    assert rows[0].prev_hash == "0" * 64
    for a, b in zip(rows, rows[1:]):
        assert b.prev_hash == a.hash
    assert audit.verify_chain(db) is True


def test_hash_formula(db):
    """TC-WA-075 hash = sha256(prev_hash + canonical_json(ts,actor,action,target,detail)) 를 독립 계산과 비교."""
    row = audit.record(db, actor="owner", action="x.y", target_type="video", target_id="abc", detail={"b": 2, "a": "가"}, now=T0)
    body = json.dumps(
        {"ts": "2026-10-10T03:00:00.123456+00:00", "actor": "owner", "action": "x.y",
         "target": {"type": "video", "id": "abc"}, "detail": {"b": 2, "a": "가"}},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    assert row.hash == hashlib.sha256(("0" * 64 + body).encode("utf-8")).hexdigest()


@pytest.mark.parametrize("column,value", [("actor", "mallory"), ("action", "x"), ("detail", {"i": 999}), ("target_id", "zzz")])
def test_tamper_content_detected(db, column, value):
    """TC-WA-076 행 내용(actor/action/detail/target)을 바꾸면 verify_chain 이 False."""
    _fill(db)
    db.execute(update(AuditLog).where(AuditLog.id == 2).values(**{column: value}))
    db.commit()
    assert audit.verify_chain(db) is False


def test_tamper_deleted_row_detected(db):
    """TC-WA-077 중간 행을 지우면 체인이 끊겨 False."""
    _fill(db)
    db.execute(delete(AuditLog).where(AuditLog.id == 2))
    db.commit()
    assert audit.verify_chain(db) is False


def test_tamper_rehash_without_chain_detected(db):
    """TC-WA-078 행 내용과 자기 hash 만 새로 계산해도 다음 행의 prev_hash 와 어긋나 False."""
    _fill(db)
    row = db.get(AuditLog, 2)
    new_detail = {"forged": True}
    new_hash = audit.compute_hash(row.prev_hash, ts=row.ts, actor=row.actor, action=row.action,
                                  target_type=row.target_type, target_id=row.target_id, detail=new_detail)
    db.execute(update(AuditLog).where(AuditLog.id == 2).values(detail=new_detail, hash=new_hash))
    db.commit()
    assert audit.verify_chain(db) is False


def test_tamper_timestamp_detected(db):
    """TC-WA-079 ts 변조도 탐지."""
    _fill(db)
    db.execute(update(AuditLog).where(AuditLog.id == 3).values(ts=T0 + timedelta(days=1)))
    db.commit()
    assert audit.verify_chain(db) is False


def test_record_requires_aware_time(db):
    """TC-WA-080 naive datetime 은 거부."""
    with pytest.raises(ValueError):
        audit.record(db, actor="a", action="b", now=datetime(2026, 1, 1))


def test_same_transaction_chain_continues_before_commit(db):
    """TC-WA-081 같은 트랜잭션에서 연속 기록해도 체인이 이어진다(flush 후 조회)."""
    a = audit.record(db, actor="o", action="a", now=T0)
    b = audit.record(db, actor="o", action="b", now=T0)
    assert b.prev_hash == a.hash
    assert audit.verify_chain(db) is True


def test_api_lists_with_chain_ok_and_pagination(client, csrf):
    """TC-WA-082 GET /audit 은 최신순 항목·total·page·chain_ok=true 를 돌려준다."""
    for cap in (3, 4, 5):
        client.patch("/api/v1/settings", json={"daily_apply_cap": cap}, headers=hdr(csrf))
    j = client.get("/api/v1/audit?page=1&page_size=2").json()
    assert j["total"] == 4 and j["page"] == 1 and j["page_size"] == 2 and j["chain_ok"] is True
    assert [i["action"] for i in j["items"]] == ["settings.update", "settings.update"]
    j2 = client.get("/api/v1/audit?page=2&page_size=2").json()
    assert [i["action"] for i in j2["items"]] == ["settings.update", "session.create"]
    assert j["items"][0]["id"] > j["items"][1]["id"]


@pytest.mark.parametrize("q", ["page_size=201", "page_size=0", "page=0"])
def test_api_pagination_bounds(client, csrf, q):
    """TC-WA-083 page_size 최대 200, page 최소 1 을 벗어나면 422."""
    assert client.get(f"/api/v1/audit?{q}").status_code == 422


def test_api_reports_broken_chain(client, csrf, db):
    """TC-WA-084 변조 후 API 의 chain_ok 는 false."""
    client.patch("/api/v1/settings", json={"daily_apply_cap": 3}, headers=hdr(csrf))
    db.execute(update(AuditLog).where(AuditLog.id == 1).values(actor="mallory"))
    db.commit()
    assert client.get("/api/v1/audit").json()["chain_ok"] is False


def test_audit_is_read_only_via_api(client, csrf):
    """TC-WA-085 감사 로그를 쓰거나 지우는 API 는 없다(POST/PATCH/DELETE → 405)."""
    for m in ("post", "patch", "delete", "put"):
        assert getattr(client, m)("/api/v1/audit", headers=hdr(csrf)).status_code == 405
