"""Idempotency-Key 규약(WEB_DESIGN §10)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import APIRouter, Depends, Header
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from tests.conftest import ORIGIN, hdr
from ytweb.core.deps import get_clock, get_session, require_csrf
from ytweb.core.errors import ProblemError
from ytweb.core.idempotency import KEY_TTL, run_idempotent
from ytweb.db.models import IdempotencyKey

NOW = datetime(2026, 10, 10, 3, 0, tzinfo=timezone.utc)
KEY = "key-0000-0001"


class Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return 201, {"n": self.calls, "title": "한글"}


def _run(db, h, key=KEY, route="POST /x", request=None, now=NOW, required=True):
    return run_idempotent(db, key=key, route=route, request=request or {"a": 1}, now=now, handler=h, required=required)


def test_missing_key_required(db):
    """TC-WA-@@@ 키가 없으면 400 idempotency_key_required 이고 핸들러는 실행되지 않는다."""
    h = Counter()
    with pytest.raises(ProblemError) as e:
        _run(db, h, key=None)
    assert e.value.status == 400 and e.value.code == "idempotency_key_required" and h.calls == 0
    with pytest.raises(ProblemError):
        _run(db, h, key="")


def test_missing_key_optional_runs_handler(db):
    """TC-WA-@@@ required=False 이면 키 없이도 핸들러가 실행되고 키 행은 만들지 않는다."""
    h = Counter()
    assert _run(db, h, key=None, required=False) == (201, {"n": 1, "title": "한글"})
    assert db.execute(select(func.count()).select_from(IdempotencyKey)).scalar_one() == 0


def test_replay_returns_stored_response_without_rerun(db):
    """TC-WA-@@@ 같은 키+같은 요청은 저장된 응답을 재생하고 핸들러를 다시 실행하지 않는다."""
    h = Counter()
    first = _run(db, h)
    db.commit()
    second = _run(db, h)
    assert first == second == (201, {"n": 1, "title": "한글"}) and h.calls == 1


def test_replay_ignores_request_key_order(db):
    """TC-WA-@@@ 요청 dict 의 키 순서가 달라도 같은 요청으로 본다."""
    h = Counter()
    _run(db, h, request={"a": 1, "b": [1, 2]})
    db.commit()
    _run(db, h, request={"b": [1, 2], "a": 1})
    assert h.calls == 1


def test_same_key_different_request_conflicts(db):
    """TC-WA-@@@ 같은 키로 다른 요청을 보내면 422 idempotency_key_reuse."""
    h = Counter()
    _run(db, h)
    db.commit()
    with pytest.raises(ProblemError) as e:
        _run(db, h, request={"a": 2})
    assert e.value.status == 422 and e.value.code == "idempotency_key_reuse" and h.calls == 1


def test_same_key_different_route_conflicts(db):
    """TC-WA-@@@ 같은 키를 다른 경로에 쓰면 422 idempotency_key_reuse."""
    h = Counter()
    _run(db, h)
    db.commit()
    with pytest.raises(ProblemError) as e:
        _run(db, h, route="POST /y")
    assert e.value.code == "idempotency_key_reuse"


@pytest.mark.parametrize("bad", ["short", "has space 12345", "x" * 81, "한글키한글키한글키", "a;b;c;d;e;f;g"])
def test_invalid_key_format(db, bad):
    """TC-WA-@@@ 키 형식(영문·숫자·._:-, 8~80자) 위반은 400 idempotency_key_invalid."""
    with pytest.raises(ProblemError) as e:
        _run(db, Counter(), key=bad)
    assert e.value.status == 400 and e.value.code == "idempotency_key_invalid"


def test_handler_failure_does_not_consume_key(db):
    """TC-WA-@@@ 핸들러가 실패해 롤백되면 키가 남지 않아 같은 키로 재시도할 수 있다."""
    def boom():
        raise ProblemError(409, "x", "충돌")

    with pytest.raises(ProblemError):
        _run(db, boom)
    db.rollback()
    h = Counter()
    assert _run(db, h)[0] == 201 and h.calls == 1


def test_in_progress_key_conflicts(db):
    """TC-WA-@@@ 응답이 아직 저장되지 않은(처리 중) 키는 409 idempotency_in_progress."""
    db.add(IdempotencyKey(key=KEY, route="POST /x", request_hash=__import__("ytweb.core.canonical", fromlist=["x"]).sha256_hex('{"a":1}'), created_at=NOW))
    db.commit()
    with pytest.raises(ProblemError) as e:
        _run(db, Counter())
    assert e.value.status == 409 and e.value.code == "idempotency_in_progress"


def test_expired_key_is_reusable(db):
    """TC-WA-@@@ 24시간이 지난 키는 만료로 보고 새로 실행한다."""
    h = Counter()
    _run(db, h)
    db.commit()
    later = NOW + KEY_TTL + timedelta(seconds=1)
    assert _run(db, h, now=later, request={"a": 2})[1]["n"] == 2
    assert h.calls == 2


def test_non_json_native_body_is_encoded(db):
    """TC-WA-@@@ datetime 등 직렬화 가능한 값은 JSON 으로 변환돼 저장·재생된다(첫 응답과 재생 응답이 동일)."""
    def h():
        return 200, {"at": NOW}

    first = _run(db, h)
    db.commit()
    assert first == _run(db, h) == (200, {"at": "2026-10-10T03:00:00+00:00"})


def test_http_end_to_end_replay(app, client, csrf):
    """TC-WA-@@@ HTTP 경로에서 같은 Idempotency-Key 재전송은 같은 응답을 재생하고 부작용이 1회뿐."""
    calls = []
    r = APIRouter()

    @r.post("/api/v1/_t/act")
    def act(body: dict, db=Depends(get_session), clock=Depends(get_clock), _=Depends(require_csrf),
            key: str | None = Header(default=None, alias="Idempotency-Key")):
        def handler():
            calls.append(1)
            return 201, {"done": len(calls)}
        status, payload = run_idempotent(db, key=key, route="POST /api/v1/_t/act", request=body, now=clock(), handler=handler)
        from fastapi.responses import JSONResponse
        return JSONResponse(payload, status_code=status)

    app.include_router(r)
    with TestClient(app, base_url=ORIGIN) as c:
        c.cookies.update(client.cookies)
        h = {**hdr(csrf), "Idempotency-Key": "http-key-0001"}
        r1 = c.post("/api/v1/_t/act", json={"x": 1}, headers=h)
        r2 = c.post("/api/v1/_t/act", json={"x": 1}, headers=h)
        r3 = c.post("/api/v1/_t/act", json={"x": 2}, headers=h)
        r4 = c.post("/api/v1/_t/act", json={"x": 1}, headers=hdr(csrf))
    assert r1.status_code == r2.status_code == 201 and r1.json() == r2.json() == {"done": 1}
    assert r3.status_code == 422 and r3.json()["code"] == "idempotency_key_reuse"
    assert r4.status_code == 400 and r4.json()["code"] == "idempotency_key_required"
    assert len(calls) == 1
