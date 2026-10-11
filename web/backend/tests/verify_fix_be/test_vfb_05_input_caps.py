"""TC-VFB-090~: 입력 상한(DEF-9-001) — 큰 정수 ID·쪽 번호는 4xx, 경계값은 정상 처리, 순서(인증 먼저)·비에코."""
from __future__ import annotations

import json
import uuid

import pytest

from ytweb.domain import handlers
from ytweb.domain.common import set_default_env
from ytweb.domain.schemas import MAX_ID, MAX_PAGE
from ytweb.domain.seed import seed_demo

from tests.conftest import ORIGIN
from tests.verify_fix_be.conftest import hdr

BIG = 10**30


@pytest.fixture
def world(api, csrf, factory, env, clock, monkeypatch):
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=30)
        s.commit()
    return api


def _h(csrf, idem=True):
    return hdr(csrf, uuid.uuid4().hex if idem else None)


PATH_ENDPOINTS = [
    ("get", "/api/v1/batches/{}", None), ("post", "/api/v1/batches/{}/execute", {"confirm_text": "실행 1건"}), ("post", "/api/v1/batches/{}/cancel", None),
    ("patch", "/api/v1/suggestions/{}", {"title": "새 제목입니다"}), ("post", "/api/v1/suggestions/{}/approve", {"approver": "검수자"}),
    ("post", "/api/v1/suggestions/{}/reject", None), ("post", "/api/v1/changes/{}/rollback", {"typed_video_id": "demoVid0001", "approver": "검수자"}),
]


def _call(api, csrf, method, url, body):
    kw = {"headers": _h(csrf)}
    if body is not None:
        kw["json"] = body
    return getattr(api, method)(url, **kw)


@pytest.mark.parametrize("method,url,body", PATH_ENDPOINTS)
@pytest.mark.parametrize("bad", [MAX_ID + 1, 2**64, BIG, 0, -1])
def test_tc_vfb_090_out_of_range_path_ids_are_422_never_500(world, csrf, method, url, body, bad):
    r = _call(world, csrf, method, url.format(bad), body)
    assert r.status_code == 422, (r.status_code, r.text[:200])
    assert r.json()["code"] == "validation_error"


@pytest.mark.parametrize("method,url,body", PATH_ENDPOINTS)
def test_tc_vfb_091_max_id_exactly_is_a_normal_404(world, csrf, method, url, body):
    """경계: 2**63-1 은 허용 범위이므로 DB 에서 '없음'(404)이어야 한다(422 도 500 도 아님)."""
    r = _call(world, csrf, method, url.format(MAX_ID), body)
    assert r.status_code == 404, (r.status_code, r.text[:200])


@pytest.mark.parametrize("url", ["/api/v1/batches", "/api/v1/changes", "/api/v1/suggestions", "/api/v1/videos", "/api/v1/audit"])
def test_tc_vfb_092_page_boundaries(world, url):
    assert world.get(f"{url}?page={MAX_PAGE}").status_code == 200
    r = world.get(f"{url}?page={MAX_PAGE + 1}")
    assert r.status_code == 422
    for bad in (BIG, 2**63, 0, -1, "abc", "1.5"):
        assert world.get(f"{url}?page={bad}").status_code == 422, bad
    assert world.get(f"{url}?page_size=200").status_code == 200
    assert world.get(f"{url}?page_size=201").status_code == 422


def test_tc_vfb_093_changes_batch_id_filter_boundary(world):
    assert world.get(f"/api/v1/changes?batch_id={MAX_ID}").status_code == 200
    assert world.get(f"/api/v1/changes?batch_id={MAX_ID + 1}").status_code == 422
    assert world.get(f"/api/v1/changes?batch_id={BIG}").status_code == 422
    assert world.get("/api/v1/changes?batch_id=0").status_code == 422


@pytest.mark.parametrize("ids,code", [
    ([MAX_ID + 1], 422), ([BIG], 422), ([0], 422), ([-5], 422), (["a"], 422), ([1.5], 422), ([None], 422), ([], 422), ("1", 422),
    ([1, MAX_ID + 1], 422), ([MAX_ID], 422),
])
def test_tc_vfb_094_batch_create_body_ids(world, csrf, ids, code):
    r = world.post("/api/v1/batches", json={"suggestion_ids": ids}, headers=_h(csrf))
    assert r.status_code == code, (ids, r.status_code, r.text[:200])
    assert r.json()["code"] in ("validation_error", "batch_empty")


def test_tc_vfb_095_max_id_in_body_is_valid_input_and_reported_as_not_found_not_500(world, csrf):
    r = world.post("/api/v1/batches", json={"suggestion_ids": [MAX_ID]}, headers=_h(csrf))
    assert r.status_code == 422 and r.json()["code"] == "batch_empty" and "찾을 수 없" in r.json()["detail"]


def test_tc_vfb_096_too_many_ids_still_rejected_by_size_limit(world, csrf):
    r = world.post("/api/v1/batches", json={"suggestion_ids": list(range(1, 502))}, headers=_h(csrf))
    assert r.status_code == 422
    r = world.post("/api/v1/batches", json={"suggestion_ids": list(range(1, 52))}, headers=_h(csrf))
    assert r.status_code == 422 and r.json()["code"] == "batch_too_large"


def test_tc_vfb_097_unauthenticated_oversized_id_is_401_not_a_validation_oracle(world, csrf):
    world.cookies.clear()
    r = world.get(f"/api/v1/batches/{BIG}")
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    r = world.post(f"/api/v1/batches/{BIG}/cancel", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf})
    assert r.status_code == 401


def test_tc_vfb_098_validation_error_does_not_echo_input_and_has_no_internals(world, csrf):
    r = world.get(f"/api/v1/batches/{BIG}")
    blob = json.dumps(r.json(), ensure_ascii=False)
    assert str(BIG) not in blob
    for leak in ("Traceback", "sqlalchemy", "OverflowError", "DataError", "site-packages", "psycopg"):
        assert leak not in blob


def test_tc_vfb_099_suggestion_count_and_settings_huge_numbers_are_4xx(world, csrf):
    r = world.post("/api/v1/videos/demoVid0001/suggestions", json={"count": BIG}, headers=_h(csrf))
    assert 400 <= r.status_code < 500
    r = world.post("/api/v1/videos/demoVid0001/suggestions", json={"count": -(10**30)}, headers=_h(csrf))
    assert 400 <= r.status_code < 500
    r = world.patch("/api/v1/settings", json={"daily_apply_cap": BIG}, headers=hdr(csrf))
    assert 400 <= r.status_code < 500


@pytest.mark.parametrize("val", ["true", "false"])
def test_tc_vfb_100_boolean_ids_not_accepted_as_ints(world, csrf, val):
    r = world.post("/api/v1/batches", content=f'{{"suggestion_ids": [{val}]}}', headers={**_h(csrf), "Content-Type": "application/json"})
    assert r.status_code == 422


def test_tc_vfb_101_server_still_alive_after_probe_storm(world, csrf):
    for u in (f"/api/v1/batches/{BIG}", f"/api/v1/suggestions/{BIG}", f"/api/v1/changes?page={BIG}", f"/api/v1/changes?batch_id={BIG}"):
        for _ in range(3):
            assert world.get(u).status_code in (404, 405, 422)
    assert world.get("/api/v1/batches").status_code == 200


@pytest.mark.postgres
def test_tc_vfb_102_postgres_boundaries_no_500(pg, env, clock, monkeypatch, tmp_path):
    """PostgreSQL(bigint) 실측: 2**63-1 은 404/200, 2**63 은 422, 큰 쪽 번호는 422, 어느 쪽도 500 이 아니다."""
    from fastapi.testclient import TestClient
    from tests.conftest import CORE_ROUTERS, REPO_ROOT, login
    from tests.domain.conftest import DOMAIN_ROUTERS
    from ytweb.app import create_app
    from ytweb.config import WebSettings
    from ytweb.core.ratelimit import RateLimits
    import os
    set_default_env(env)
    url = os.environ["YTWEB_TEST_PG_URL"]
    ws = WebSettings(mode="demo", database_url=url, base_dir=REPO_ROOT, secrets_dir=tmp_path / "secrets",
                     allowed_hosts=("127.0.0.1:8080", "localhost:8080"))
    monkeypatch.setenv("YTWEB_AUTO_CREATE", "0")
    monkeypatch.delenv("YTWEB_STATIC_DIR", raising=False)
    app = create_app(ws, clock=clock, router_modules=CORE_ROUTERS + DOMAIN_ROUTERS, rate_limits=RateLimits(global_per_min=100_000, write_per_min=100_000, auth_per_min=100_000))
    with TestClient(app, base_url=ORIGIN) as c:
        t = login(c)
        assert c.get(f"/api/v1/batches/{MAX_ID}").status_code == 404
        assert c.get(f"/api/v1/batches/{MAX_ID + 1}").status_code == 422
        assert c.post(f"/api/v1/batches/{MAX_ID}/cancel", headers=hdr(t)).status_code == 404
        assert c.post(f"/api/v1/batches/{MAX_ID + 1}/cancel", headers=hdr(t)).status_code == 422
        assert c.post(f"/api/v1/suggestions/{MAX_ID}/reject", headers=hdr(t)).status_code == 404
        assert c.post(f"/api/v1/changes/{MAX_ID}/rollback", json={"typed_video_id": "demoVid0001", "approver": "검수자"}, headers=hdr(t, uuid.uuid4().hex)).status_code == 404
        assert c.get(f"/api/v1/changes?batch_id={MAX_ID}").status_code == 200
        assert c.get(f"/api/v1/changes?batch_id={MAX_ID + 1}").status_code == 422
        for p in ("changes", "batches", "suggestions", "videos", "audit"):
            assert c.get(f"/api/v1/{p}?page={MAX_PAGE}").status_code == 200, p
            assert c.get(f"/api/v1/{p}?page={MAX_PAGE + 1}").status_code == 422, p
        r = c.post("/api/v1/batches", json={"suggestion_ids": [MAX_ID]}, headers=hdr(t, uuid.uuid4().hex))
        assert r.status_code == 422 and r.json()["code"] == "batch_empty"
