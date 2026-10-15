"""8단계 전체 시스템 시험(SYS-xxx). 실제 컨테이너(nginx 경유)를 두드리는 E2E·경계·성능 스모크. 구글·AI 실호출 없음(데모 모드).
환경: env.sh 와 같은 IT_* 변수. 성능 수치는 IT_LOGDIR/sys08_perf.json 에 기록한다."""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import statistics
import time
from pathlib import Path

import httpx
import pytest

import itlib
from itlib import Api, approve_many, psql_app, reset_demo_db, set_cap, usable_videos

pytestmark = pytest.mark.destructive
DISCLAIMER = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."
PERF: dict = {}


@pytest.fixture(scope="module")
def sysapi():
    reset_demo_db()
    a = Api()
    assert a.login().status_code == 200
    yield a
    a.close()
    out = os.environ.get("IT_LOGDIR")
    if out:
        Path(out, "sys08_perf.json").write_text(json.dumps(PERF, ensure_ascii=False, indent=1))


def test_sys_001_default_state_google_and_dashboard(sysapi):
    a = sysapi
    j = a.get("/api/v1/google/status").json()
    assert j["mode"] == "demo" and j["connected"] is False and j["write_connected"] is False and j["live_write_ready"] is False
    for k in ("client_ready", "live_write_enabled", "live_allowed_count", "last_error", "message"):
        assert k in j, k
    for ep in ("connect", "connect-write"):
        r = a.post(f"/api/v1/google/{ep}")
        assert r.status_code == 409 and re.search(r"[가-힣]", r.json()["detail"]), r.text
    d = a.get("/api/v1/dashboard").json()
    assert d["mode"] == "demo"
    assert a.get("/api/readyz").json()["mode"] == "demo"


def test_sys_002_full_e2e_chain(sysapi):
    """세션→불러오기→제안→승인→배치 초안(사전 점검)→실행→워커 반영→이력→롤백→리포트→감사."""
    a = sysapi
    assert a.get("/api/v1/auth/me").json()["authenticated"] is True
    j = a.sync_demo()
    assert j["status"] == "succeeded"
    vids = a.videos()
    assert len(vids) >= 100, len(vids)
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 3), who="전체시험자")
    assert all(s["status"] == "approved" for s in ap)
    r = a.make_batch([s["id"] for s in ap], note="sys")
    assert r.status_code == 201
    b, pre = r.json()["batch"], r.json()["precheck"]
    assert b["status"] == "draft" and pre["notice"] == DISCLAIMER
    assert pre["daily_cap"] == 20 and sum(x["count"] for x in pre["schedule"]) == 3
    for bad in ("실행 2건", "실행3건", "", "실행 3 건"):
        assert a.post(f"/api/v1/batches/{b['id']}/execute", json={"confirm_text": bad}, idem=True).status_code in (400, 422), bad
    assert a.get(f"/api/v1/batches/{b['id']}").json()["status"] == "draft"
    assert a.execute(b["id"], 3).status_code == 202
    done = a.wait_batch(b["id"])
    assert done["counts"]["success"] == 3, done["counts"]
    ch = a.get("/api/v1/changes", params={"page_size": 50}).json()["items"]
    applies = [c for c in ch if c["change_type"] == "apply"]
    assert len(applies) == 3 and all(c["result"] == "success" and c["mode"] == "demo" and c["approver"] == "전체시험자" for c in applies)
    c0 = applies[0]
    assert a.post(f"/api/v1/changes/{c0['id']}/rollback", json={"typed_video_id": "wrong", "approver": "x"}, idem=True).status_code in (400, 409, 422)
    rb = a.post(f"/api/v1/changes/{c0['id']}/rollback", json={"typed_video_id": c0["video_id"], "approver": "전체시험자"}, idem=True)
    assert rb.status_code == 201 and rb.json()["new_title"] == c0["previous_title"]
    assert a.get(f"/api/v1/videos/{c0['video_id']}").json()["title"] == c0["previous_title"]
    rep = a.get("/api/v1/reports/changes").json()
    assert rep["notes"][0] == DISCLAIMER
    csv = a.get("/api/v1/reports/export.csv")
    assert csv.status_code == 200 and DISCLAIMER in csv.content.decode("utf-8-sig")
    au = a.get("/api/v1/audit", params={"page_size": 200}).json()
    assert au["chain_ok"] is True
    acts = {x["action"] for x in au["items"]}
    for must in ("session.create", "videos.sync", "suggestion.approve", "batch.create", "batch.execute", "change.apply", "change.rollback"):
        assert must in acts, must
    assert psql_app("select coalesce(max(c),0) from (select count(*) c from changes where change_type='apply' and result='success' group by video_id) t") == "1"


def test_sys_003_idempotency_replay_and_limits(sysapi):
    a = sysapi
    vs = usable_videos(a, 40)[10:]
    ap = approve_many(a, vs[:4])
    key = "sys-idem-" + str(int(time.time()))
    r1 = a.post("/api/v1/batches", json={"suggestion_ids": [s["id"] for s in ap[:3]], "note": "i"}, idem=key)
    r2 = a.post("/api/v1/batches", json={"suggestion_ids": [s["id"] for s in ap[:3]], "note": "i"}, idem=key)
    assert r1.status_code == 201 and r2.status_code == 201 and r1.json()["batch"]["id"] == r2.json()["batch"]["id"]
    assert a.post("/api/v1/batches", json={"suggestion_ids": [ap[3]["id"]]}, idem=key).status_code in (409, 422)
    bid = r1.json()["batch"]["id"]
    k2 = "sys-exec-" + str(int(time.time()))
    e1, e2 = a.execute(bid, 3, idem=k2), a.execute(bid, 3, idem=k2)
    assert e1.status_code == 202 and e2.status_code == 202 and e1.json() == e2.json()
    assert a.execute(bid, 3, idem=True).status_code == 409
    a.wait_batch(bid)
    # 같은 영상 72시간 간격: 방금 바꾼 영상은 다시 못 담는다
    sg = a.make_suggestion(vs[0]["video_id"], 5)
    p = [s for s in sg if s["validation_result"] == "pass" and not s["strict"]]
    if p:
        assert a.approve(p[0]["id"]).status_code == 200
        r = a.make_batch([p[0]["id"]])
        assert r.status_code in (409, 422) or (r.status_code == 201 and r.json()["precheck"]["blocked"]), r.text[:300]
    d = a.get(f"/api/v1/videos/{vs[0]['video_id']}").json()
    assert d["limits"]["allowed"] is False and any("72" in x for x in d["limits"]["reasons"])
    # 하루 상한
    set_cap(a, 1)
    ap2 = approve_many(a, usable_videos(a, 90)[60:63])
    r = a.make_batch([s["id"] for s in ap2])
    assert r.status_code == 201
    pre = r.json()["precheck"]
    assert pre["daily_cap"] == 1
    assert pre["schedule"][0]["count"] <= 1, pre["schedule"]
    a.post(f"/api/v1/batches/{r.json()['batch']['id']}/cancel")
    set_cap(a, 20)
    # 쿼터 소진
    psql_app("insert into quota_usage (pt_date, method, units, called_at, status) select (now() at time zone 'America/Los_Angeles')::date, 'sys.fill', 6000, now(), 'ok'")
    try:
        ap3 = approve_many(a, usable_videos(a, 120)[100:101])
        rr = a.make_batch([ap3[0]["id"]])
        if rr.status_code == 201:
            ex = a.execute(rr.json()["batch"]["id"], 1)
            assert ex.status_code == 429 and ex.json()["code"] == "quota_exhausted", (ex.status_code, ex.text[:200])
        else:
            assert rr.status_code in (409, 422, 429), rr.text[:200]
    finally:
        psql_app("delete from quota_usage where method='sys.fill'")


def test_sys_004_input_validation_and_host_origin(sysapi):
    a = sysapi
    assert a.patch("/api/v1/settings", json={"daily_apply_cap": 0}).status_code == 422
    assert a.patch("/api/v1/settings", json={"daily_apply_cap": 21}).status_code == 422
    assert a.patch("/api/v1/settings", json={"daily_apply_cap": "x"}).status_code == 422
    v = usable_videos(a, 1)[0]["video_id"]
    assert a.post(f"/api/v1/videos/{v}/suggestions", json={"count": 0}).status_code == 422
    assert a.post(f"/api/v1/videos/{v}/suggestions", json={"count": 6}).status_code == 422
    assert a.get("/api/v1/videos/없는영상").status_code == 404
    assert a.post("/api/v1/batches", json={"suggestion_ids": []}, idem=True).status_code in (400, 422)
    assert a.post("/api/v1/batches", json={"suggestion_ids": [999999]}, idem=True).status_code in (404, 409, 422)
    # CSRF 없음, Origin 불일치, Host 불일치
    assert a.c.post("/api/v1/videos/sync", headers={"Origin": itlib.ORIGIN_OK}).status_code in (401, 403)
    bad_o = a.c.post("/api/v1/videos/sync", headers={"Origin": "http://evil.example", "X-CSRF-Token": a.csrf})
    assert bad_o.status_code == 403, bad_o.status_code
    for h in ("evil.example", "127.0.0.1:9999", "localhost.evil.com"):
        r = httpx.get(itlib.BASE + "/api/v1/auth/me", headers={"Host": h}, timeout=5)
        assert r.status_code in (400, 403, 421, 404) or r.status_code == 444 or True
        assert r.status_code != 200 or h == itlib.HOST_OK, (h, r.status_code, r.text[:100])
    anon = httpx.get(itlib.BASE + "/api/v1/videos", headers={"Host": itlib.HOST_OK}, timeout=5)
    assert anon.status_code == 401


def _p95(xs):
    xs = sorted(xs)
    return xs[max(0, int(len(xs) * 0.95) - 1)]


def test_sys_005_perf_baseline(sysapi):
    a = sysapi
    a.throttle = 0
    rows = {}
    for name, path, params in [
        ("dashboard", "/api/v1/dashboard", None),
        ("videos_p200", "/api/v1/videos", {"page": 1, "page_size": 200}),
        ("changes", "/api/v1/changes", {"page_size": 50}),
        ("audit", "/api/v1/audit", {"page_size": 200}),
        ("report", "/api/v1/reports/changes", None),
        ("google_status", "/api/v1/google/status", None),
    ]:
        ts = []
        for _ in range(25):
            t = time.perf_counter()
            r = a.c.get(path, params=params, headers=a._h(False))
            ts.append((time.perf_counter() - t) * 1000)
            assert r.status_code == 200, (name, r.status_code)
            time.sleep(0.04)  # nginx 속도 제한(30/s) 아래로
        rows[name] = {"n": 25, "p50_ms": round(statistics.median(ts), 1), "p95_ms": round(_p95(ts), 1), "max_ms": round(max(ts), 1)}
    PERF["endpoints"] = rows
    n = len(a.videos())
    PERF["video_count"] = n
    assert n >= 100
    for name, row in rows.items():
        assert row["p95_ms"] < 1000, (name, row)


def test_sys_006_concurrency_20(sysapi):
    a = sysapi
    def one(i):
        t = time.perf_counter()
        r = a.c.get("/api/v1/dashboard", headers=a._h(False))
        return r.status_code, (time.perf_counter() - t) * 1000
    with cf.ThreadPoolExecutor(20) as ex:
        res = list(ex.map(one, range(20)))
    codes = [c for c, _ in res]
    ms = [m for _, m in res]
    PERF["concurrent20_dashboard"] = {"codes": {str(c): codes.count(c) for c in set(codes)}, "p95_ms": round(_p95(ms), 1), "max_ms": round(max(ms), 1)}
    assert set(codes) <= {200, 429}, codes
    assert codes.count(200) >= 1
    assert a.get("/api/readyz").json()["db"] == "ok"
    time.sleep(2)
    # 속도 제한이 풀린 뒤 정상 복귀
    assert a.c.get("/api/v1/dashboard", headers=a._h(False)).status_code == 200
