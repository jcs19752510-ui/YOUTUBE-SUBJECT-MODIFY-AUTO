"""7단계 통합 재시험(개정 2판) 신규 시나리오 — M2(구글 읽기 연동)·M3(수정 게이트웨이)·수정 단위(W-FIX-*) 이후의 단위 간 경계.
기본 compose(구글 연결 파일 없음)의 실제 컨테이너를 nginx 경유로 두드린다. 실제 구글에는 접속하지 않는다(컨테이너는 internal 망뿐이다).
ID 는 결과서 개정 2판의 IT-I2-NNN 과 같다.
"""
from __future__ import annotations

import json
import re
import time

import pytest

from itlib import (
    Api, approve_many, approved_suggestion, counts, dc, dexec, psql_app, reset_demo_db, set_cap, sh, cid,
    usable_videos, wait_healthy, worker_start, worker_stop,
)

pytestmark = pytest.mark.destructive
DISCLAIMER = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."


@pytest.fixture()
def fd():
    reset_demo_db()
    a = Api()
    assert a.login().status_code == 200
    j = a.sync_demo()
    assert j["status"] == "succeeded"
    yield a
    a.close()


def _audit_actions(a: Api) -> list[str]:
    return [x["action"] for x in a.get("/api/v1/audit", params={"page_size": 200}).json()["items"]]


def _no_double_apply() -> None:
    assert psql_app("select coalesce(max(c),0) from (select count(*) c from changes where change_type='apply' and result='success' group by video_id) t") in ("0", "1")
    assert psql_app("select count(*) from changes where result='planned'") == "0"


# ───────────────────────── 상태 필드 ─────────────────────────

def test_it_i2_001_google_status_and_dashboard_fields_in_default_compose(fd):
    """구글 연결 파일이 없는 기본 compose: /google/status 와 /dashboard 의 상태 필드가 서로 일치하고 모두 '데모·미연결·쓰기 불가'다."""
    a = fd
    g = a.get("/api/v1/google/status")
    assert g.status_code == 200, g.text
    j = g.json()
    assert j["mode"] == "demo" and j["connected"] is False and j["client_ready"] is False
    assert j["write_connected"] is False and j["live_write_enabled"] is False and j["live_allowed_count"] == 0 and j["live_write_ready"] is False
    assert j["last_error"] is None
    assert "데모 모드" in j["message"] and "google_client.json" in j["message"]
    d = a.get("/api/v1/dashboard").json()
    assert d["mode"] == "demo" and d["live_enabled"] is False
    assert d["google"].get("connected") is False, d["google"]
    assert d["google"].get("mode") in ("demo", None), d["google"]
    # 같은 사실이 두 곳에서 어긋나지 않는다
    assert (d["google"].get("write_connected", False)) == j["write_connected"]
    # readyz 도 mode=demo
    assert a.get("/api/readyz").json()["mode"] == "demo"
    # 쓰기 스위치/허용 영상 관련 환경변수가 컨테이너에 없다
    env = dexec("api", "sh", "-c", "env | grep -c '^YTWEB_LIVE' || true").stdout.strip()
    assert env == "0", env
    gc = dexec("api", "sh", "-c", "ls /run/secrets/").stdout.split()
    assert "google_client" not in gc and gc == ["db_app_password"], gc
    tok = dexec("api", "sh", "-c", "ls /var/lib/ytweb/secrets/").stdout.split()
    assert not [t for t in tok if "google" in t], tok


def test_it_i2_002_connect_endpoints_are_409_korean_without_client_file_and_change_nothing(fd):
    a = fd
    before = _audit_actions(a)
    for ep in ("connect", "connect-write"):
        r = a.post(f"/api/v1/google/{ep}")
        assert r.status_code == 409, (ep, r.status_code, r.text)
        j = r.json()
        assert j["code"].startswith("google_client_"), j
        text = json.dumps(j, ensure_ascii=False)
        assert re.search(r"[가-힣]", j.get("detail", "")) and re.search(r"[가-힣]", j.get("title", "")), j
        assert "Traceback" not in text and "FileNotFoundError" not in text and "/run/secrets" not in text, text
        assert j.get("hint") and "google_client.json" in j["hint"]
        assert "auth_url" not in text and "accounts.google.com" not in text
    after = _audit_actions(a)
    assert not any(x.startswith("google.connect") for x in after) and len(after) == len(before)
    # CSRF/Origin 없는 호출은 구글 파일 문제보다 먼저 거부된다
    r = a.c.post("/api/v1/google/connect", headers={"Origin": "http://evil.example"})
    assert r.status_code in (401, 403), r.status_code
    # disconnect 는 연결이 없어도 안전하게 성공
    r = a.post("/api/v1/google/disconnect")
    assert r.status_code == 200 and r.json() == {"connected": False}
    # 상태는 그대로
    assert a.get("/api/v1/google/status").json()["connected"] is False


def test_it_i2_003_callback_without_valid_state_never_stores_token_and_returns_to_home(fd):
    a = fd
    for q in ("", "?state=abcdefabcdef&code=zzz", "?state=abc&error=access_denied", "?code=x"):
        r = a.c.get("/api/v1/google/callback" + q, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/#/", (q, r.status_code, r.headers)
        assert "no-store" in r.headers.get("cache-control", "")
    tok = dexec("api", "sh", "-c", "ls /var/lib/ytweb/secrets/").stdout.split()
    assert not [t for t in tok if "google" in t], tok
    st = a.get("/api/v1/google/status").json()
    assert st["connected"] is False and st["write_connected"] is False
    # 오류 안내는 한 번만 한국어로 보이고 사라진다(두 번째 조회는 None)
    assert st["last_error"] is None or re.search(r"[가-힣]", st["last_error"])
    assert a.get("/api/v1/google/status").json()["last_error"] is None
    # 세션 없이도 콜백은 303 (브라우저 이동용) — 인증 쿠키 없는 호출
    import httpx
    from itlib import BASE, HOST_OK
    r = httpx.get(BASE + "/api/v1/google/callback?state=x&code=y", headers={"Host": HOST_OK}, follow_redirects=False)
    assert r.status_code == 303


def test_it_i2_004_demo_cannot_be_switched_to_live_by_settings_and_api_has_no_internet(fd):
    a = fd
    for k in ("enable_live", "live_allowlist", "live_write", "mode"):
        r = a.patch("/api/v1/settings", json={k: True if k != "live_allowlist" else ["abcdefghijk"]})
        assert r.status_code in (400, 422), (k, r.status_code)
    assert a.get("/api/v1/dashboard").json()["live_enabled"] is False
    # 컨테이너에서 인터넷으로 나가는 길이 없다(internal 망) — api 와 worker 모두 (실제 구글로 갈 수 없음을 구조로 확인)
    for svc in ("api", "worker"):
        p = dexec(svc, "python", "-c", "import socket;socket.setdefaulttimeout(4);socket.create_connection(('oauth2.googleapis.com',443))")
        assert p.returncode != 0, svc


# ───────────────────────── 면책·AI 고지 ─────────────────────────

def test_it_i2_010_disclaimer_fields_flow_from_precheck_to_stored_batch_and_report(fd):
    a = fd
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 2))
    r = a.make_batch([s["id"] for s in ap])
    assert r.status_code == 201
    pre = r.json()["precheck"]
    assert pre["notice"] == DISCLAIMER
    bid = r.json()["batch"]["id"]
    # 저장된 배치 조회에서도 같은 고지가 따라온다(단위 간: 생성 → 저장 → 재조회)
    assert a.get(f"/api/v1/batches/{bid}").json()["precheck"]["notice"] == DISCLAIMER
    assert a.execute(bid, 2).status_code == 202
    a.wait_batch(bid)
    rep = a.get("/api/v1/reports/changes").json()
    assert rep["notes"][0] == DISCLAIMER, rep["notes"]
    assert any("원인" in n for n in rep["notes"])
    csv = a.get("/api/v1/reports/export.csv")
    assert csv.status_code == 200
    assert DISCLAIMER in csv.content.decode("utf-8-sig"), csv.text[:300]


# ───────────────────────── C-1 / C-2 ─────────────────────────

def _blocked_suggestion(a: Api):
    for v in usable_videos(a, 120):
        for s in a.make_suggestion(v["video_id"], 5):
            if s["status"] == "blocked":
                return v, s
    raise AssertionError("차단 제안 없음")


def test_it_i2_020_c1_blocked_suggestion_actions_through_real_api(fd):
    a = fd
    v, s = _blocked_suggestion(a)
    assert s["validation_result"] == "block"
    assert a.approve(s["id"]).status_code == 409
    r = a.patch(f"/api/v1/suggestions/{s['id']}", json={"title": "냉장고 정리 처음이라도 쉽게 따라 하는 순서 안내"})
    assert r.status_code == 200 and r.json()["approval"] is None and r.json()["status"] in ("candidate", "blocked")
    # 수정으로 통과한 제안은 승인 → 배치까지 간다(차단 → 수정 → 승인 → 배치의 단위 간 흐름)
    if r.json()["status"] == "candidate":
        assert a.approve(s["id"]).status_code == 200
        assert a.make_batch([s["id"]]).status_code == 201
    for vv in usable_videos(a, 160)[1:]:
        if vv["video_id"] == v["video_id"]:
            continue
        cand = [x for x in a.make_suggestion(vv["video_id"], 5) if x["status"] == "blocked"]
        if cand:
            rr = a.post(f"/api/v1/suggestions/{cand[0]['id']}/reject")
            assert rr.status_code == 200 and rr.json()["status"] == "rejected"
            break
    else:
        pytest.fail("두 번째 차단 제안 없음")


def test_it_i2_021_c2_cancel_draft_batch_then_reuse_same_suggestions(fd):
    a = fd
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 3))
    ids = [s["id"] for s in ap]
    b1 = a.make_batch(ids)
    assert b1.status_code == 201 and b1.json()["batch"]["status"] == "draft"
    bid = b1.json()["batch"]["id"]
    # 같은 제안으로 새 초안 → 사전 점검에서 막힘 + 어느 배치가 붙잡고 있는지 알려 줌(blocked[].batch_id)
    b2 = a.make_batch(ids)
    assert b2.status_code in (409, 422), b2.text[:300]
    if b2.status_code == 201:
        pytest.fail("중복 담김")
    blocked = b2.json().get("blocked") or b2.json().get("extra", {}).get("blocked")
    # 세부 응답이 문제 JSON 에 없을 수 있으므로 점검 API 형태를 모두 허용하되, 있으면 batch_id 가 초안 번호여야 한다
    if blocked:
        assert all(x.get("code") == "already_in_batch" and x.get("batch_id") == bid for x in blocked), blocked
    # 초안 취소 → 제안은 승인 상태 그대로, 새 배치에 다시 담김
    c = a.post(f"/api/v1/batches/{bid}/cancel")
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    sg = {x["id"]: x["status"] for x in a.get("/api/v1/suggestions", params={"page_size": 50}).json()["items"]}
    assert all(sg[i] == "approved" for i in ids), sg
    # 취소한 초안을 다시 취소/실행 → 409
    assert a.post(f"/api/v1/batches/{bid}/cancel").status_code == 409
    assert a.execute(bid, 3).status_code == 409
    b3 = a.make_batch(ids)
    assert b3.status_code == 201, b3.text[:300]
    nb = b3.json()["batch"]["id"]
    assert nb != bid and b3.json()["precheck"]["blocked"] == []
    assert a.execute(nb, 3).status_code == 202
    done = a.wait_batch(nb)
    assert done["counts"]["success"] == 3
    # 끝난 배치는 취소 불가, 없는 배치는 404
    assert a.post(f"/api/v1/batches/{nb}/cancel").status_code == 409
    assert a.post("/api/v1/batches/999999/cancel").status_code == 404
    _no_double_apply()
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == "3"
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    acts = _audit_actions(a)
    assert acts.count("batch.cancel") >= 1


def test_it_i2_022_c2_cancel_leaves_other_drafts_and_unapproved_untouched(fd):
    """초안 두 개 중 하나만 취소해도 다른 초안의 제안은 계속 붙잡혀 있고(이중 담김 불가), 취소된 쪽 제안만 풀린다."""
    a = fd
    ap = approve_many(a, usable_videos(a, 4))
    b1 = a.make_batch([ap[0]["id"], ap[1]["id"]]).json()["batch"]["id"]
    b2 = a.make_batch([ap[2]["id"], ap[3]["id"]]).json()["batch"]["id"]
    assert a.post(f"/api/v1/batches/{b1}/cancel").status_code == 200
    assert a.make_batch([ap[2]["id"]]).status_code in (409, 422)      # b2 가 여전히 붙잡음
    assert a.make_batch([ap[0]["id"]]).status_code == 201             # b1 쪽은 풀림
    assert a.get(f"/api/v1/batches/{b2}").json()["status"] == "draft"


# ───────────────────────── 7B-001: 워커 비정상 종료 후 작업 종료 ─────────────────────────

def test_it_i2_030_job_row_closed_after_worker_sigkill_mid_batch_docker(fd):
    """DEF-7B-001 재현(도커 스택): 20건 배치 처리 중 워커를 SIGKILL → 컨테이너 재시작 정책으로 되살아남 → 배치 done, 작업 종료, 대시보드 active_job 없음."""
    a = fd
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 20))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    jid = a.execute(bid, 20).json()["job"]["id"]
    t0 = time.time()
    while time.time() - t0 < 40:
        if a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 2:
            break
        time.sleep(0.05)
    w = cid("worker")
    sh(["docker", "kill", "-s", "KILL", w])
    time.sleep(0.5)
    # `docker kill` 은 엔진이 수동 중지로 취급해 재시작 정책이 동작하지 않는다(첫 실행에서 확인) -> 시험이 직접 시작한다(기존 itlib_b.worker_kill_and_restart 와 같은 방식)
    if sh(["docker", "inspect", "-f", "{{.State.Running}}", w]).stdout.strip() != "true":
        assert sh(["docker", "start", w]).returncode == 0
    b = a.wait_batch(bid, timeout=150)
    assert b["status"] == "done"
    assert b["counts"]["success"] + b["counts"]["failed"] == 20, b["counts"]
    t0 = time.time()
    st = None
    while time.time() - t0 < 40:
        st = a.get(f"/api/v1/jobs/{jid}").json()["status"]
        if st in ("succeeded", "failed"):
            break
        time.sleep(1)
    assert st in ("succeeded", "failed"), st
    assert a.get("/api/v1/dashboard").json()["active_job"] is None
    _no_double_apply()
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True


# ───────────────────────── 재시작 중 이중 반영 없음 ─────────────────────────

def _run_batch_with_disruption(fd, disrupt, n=20):
    a = fd
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, n))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, n).status_code == 202
    t0 = time.time()
    while time.time() - t0 < 40:
        if a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 2:
            break
        time.sleep(0.05)
    disrupt()
    wait_healthy(150)
    b = a.wait_batch(bid, timeout=180)
    assert b["status"] == "done"
    assert b["counts"]["success"] + b["counts"]["failed"] + b["counts"]["skipped"] == n, b["counts"]
    assert b["counts"]["failed"] == 0 and b["counts"]["skipped"] == 0, b["counts"]
    _no_double_apply()
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == str(n)
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    return a, bid


def test_it_i2_040_api_container_restart_mid_batch_no_double_apply(fd):
    def d():
        p = dc("restart", "-t", "20", "api")
        assert p.returncode == 0, p.stderr[-300:]
    _run_batch_with_disruption(fd, d)


def test_it_i2_041_worker_sigterm_restart_mid_batch_no_double_apply(fd):
    def d():
        p = dc("restart", "-t", "40", "worker")
        assert p.returncode == 0, p.stderr[-300:]
    _run_batch_with_disruption(fd, d)


def test_it_i2_042_db_container_restart_mid_batch_no_double_apply(fd):
    def d():
        p = dc("restart", "-t", "60", "db")
        assert p.returncode == 0, p.stderr[-300:]
    _run_batch_with_disruption(fd, d)


def test_it_i2_043_web_restart_does_not_affect_state_and_all_up_after_full_down_up(fd):
    """web(nginx) 재시작 + 전체 중지·재기동(down 없이 stop/start) 뒤에도 데이터·세션 쿠키 서명 키가 살아 있다."""
    a = fd
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 3))
    sid = ap[0]["id"]
    assert dc("restart", "web").returncode == 0
    wait_healthy(60)
    assert a.get("/api/v1/auth/me").json()["authenticated"] is True
    p = dc("stop", "-t", "40", "web", "api", "worker", "db")
    assert p.returncode == 0
    p = dc("up", "-d", "--no-build")
    assert p.returncode == 0, p.stderr[-400:]
    wait_healthy(180)
    a2 = Api()
    assert a2.login().status_code == 200
    s = {x["id"]: x for x in a2.get("/api/v1/suggestions", params={"page_size": 50}).json()["items"]}
    assert s[sid]["status"] == "approved"           # 승인 서명 키(볼륨)가 재기동 뒤에도 살아 있어 승인이 유효
    bid = a2.make_batch([sid]).json()["batch"]["id"]
    assert a2.execute(bid, 1).status_code == 202
    assert a2.wait_batch(bid)["counts"]["success"] == 1
    a2.close()
    _no_double_apply()


# ───────────────────────── 대시보드 필드 ─────────────────────────

def test_it_i2_050_dashboard_counts_follow_cancel_and_apply(fd):
    a = fd
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 2))
    d0 = a.get("/api/v1/dashboard").json()
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    a.post(f"/api/v1/batches/{bid}/cancel")
    d1 = a.get("/api/v1/dashboard").json()
    assert d1["counts"] == d0["counts"], (d0["counts"], d1["counts"])      # 초안 취소는 집계를 바꾸지 않는다
    assert d1["today"]["applied"] == 0 and d1["mode"] == "demo"
    for key in ("mode", "live_enabled", "google", "counts", "today", "quota", "active_job", "queue"):
        assert key in d1
