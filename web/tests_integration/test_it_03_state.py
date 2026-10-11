"""IT 그룹 S — 단위 간 경합·상태: 응답 후 commit 수정, 같은 키 재전송, 이중 실행, 워커·DB 재시작, 오래된 running 복구, 컨테이너 재시작 후 보존.
"""
from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path

import pytest

from itlib import (
    Api, approve_many, approved_suggestion, cid, dc, forge_approval_expiry, inside_api_python, psql_app, psql_owner, set_cap, sh,
    usable_videos, wait_healthy, worker_start, worker_stop,
)

HERE = Path(__file__).resolve().parent


# ─────────────────────────── 응답 후 commit(DEF-VF-B01 / DEF-VA-010) ───────────────────────────

@pytest.mark.slow
def test_tc_it_300_session_then_immediate_requests_through_nginx(fresh_demo):
    """TC-IT-300: nginx 경유로 '세션 발급 직후 조회·변경'을 30회 반복해 401/403/404 가 한 번도 없다(수정 전에는 첫 요청이 401 이 되는 경우가 있었음).
    세션 발급 속도 제한(분당 10) 때문에 이 횟수는 시간이 걸린다(약 3분). 많은 횟수의 반복은 TC-IT-301(컨테이너 안, 제한 해제 사본). 검증: DEF-VF-B01, S-W02"""
    bad = []
    for i in range(30):
        a = Api(throttle=0)
        assert a.login().status_code == 200
        r1 = a.get("/api/v1/dashboard")
        r2 = a.patch("/api/v1/settings", json={"suggestions_per_video": 3})
        r3 = a.post("/api/v1/videos/sync")      # 작업 생성 직후
        r4 = a.get(f"/api/v1/jobs/{r3.json()['id']}") if r3.status_code == 202 else r3
        if (r1.status_code, r2.status_code, r3.status_code, r4.status_code) != (200, 200, 202, 200):
            bad.append((i, r1.status_code, r2.status_code, r3.status_code, r4.status_code))
        a.close()
    assert not bad, bad


@pytest.mark.slow
def test_tc_it_301_race_inside_container_many_iterations(fresh_demo):
    """TC-IT-301: 속도 제한만 풀어 둔 제2 서버(같은 이미지·PostgreSQL 17)에서 (a) 세션 발급 직후 조회·변경 (b) 작업 생성 직후 조회 (c) PIN 설정 직후 '현재 PIN
    없는' 변경을 각 300회 반복해 실패 0건. (c) 는 PIN 우회 보안 영향이 있는 경합이다. 검증: DEF-VF-B01/DEF-VA-010, S-W02, SEC-W19"""
    p = inside_api_python((HERE / "inside_race.py").read_text(encoding="utf-8"), timeout=900)
    assert p.returncode == 0, (p.stdout[-800:], p.stderr[-800:])
    line = [x for x in p.stdout.splitlines() if x.startswith("RACE_RESULT ")][-1]
    d = json.loads(line[len("RACE_RESULT "):])
    assert d["n"] >= 300
    assert d["session_then_request_bad_count"] == 0, d
    assert d["job_then_get_bad_count"] == 0, d
    assert d["pin_set_then_change_bad_count"] == 0, d
    assert d["pin_enabled_at_end"] is False


# ─────────────────────────── 멱등성 키 ───────────────────────────

def test_tc_it_302_same_key_concurrent_create_batch_yields_one_batch(fresh_demo):
    """TC-IT-302: 같은 Idempotency-Key 로 배치 생성을 10개 스레드가 동시에 보내도 배치는 1개이며 응답은 201(첫 응답 또는 재생) 또는 409
    idempotency_in_progress 뿐이다. 이후 같은 키 재전송은 같은 배치 id 를 재생한다. 검증: S-W12, API.md 1-6"""
    a = fresh_demo
    ap = approve_many(a, usable_videos(a, 3))
    key = "it-302-concurrent-key-1"
    res: list[tuple[int, dict]] = []
    lock = threading.Lock()
    ck = a.c.cookies.get("ytw_session")

    def go():
        c = Api(throttle=0)
        c.c.cookies.set("ytw_session", ck, domain="127.0.0.1", path="/api")
        c.csrf = a.csrf
        r = c.post("/api/v1/batches", json={"suggestion_ids": [s["id"] for s in ap], "note": "경합"}, idem=key)
        with lock:
            res.append((r.status_code, r.json()))
        c.close()
    ts = [threading.Thread(target=go) for _ in range(10)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert all(c in (201, 409) for c, _ in res), [(c, d.get("code")) for c, d in res]
    assert any(c == 201 for c, _ in res)
    assert all(d.get("code") == "idempotency_in_progress" for c, d in res if c == 409)
    assert a.get("/api/v1/batches").json()["total"] == 1
    again = a.post("/api/v1/batches", json={"suggestion_ids": [s["id"] for s in ap], "note": "경합"}, idem=key)
    assert again.status_code == 201 and again.json()["batch"]["id"] == a.get("/api/v1/batches").json()["items"][0]["id"]
    assert psql_app("select count(*) from batch_items") == "3"


def test_tc_it_303_concurrent_jobs_each_processed_exactly_once(fresh_demo):
    """TC-IT-303: 제안 생성 작업 12개를 동시에 만들면 각 작업이 정확히 한 번(attempts=1)만 처리되고 모두 성공한다(작업 큐 SKIP LOCKED ↔ 도메인 핸들러). 검증: S-W12, NFR-W03, W-004"""
    a = fresh_demo
    vids = usable_videos(a, 12)
    ids: list[str] = []
    lock = threading.Lock()
    ck = a.c.cookies.get("ytw_session")

    def go(v):
        c = Api(throttle=0)
        c.c.cookies.set("ytw_session", ck, domain="127.0.0.1", path="/api")
        c.csrf = a.csrf
        r = c.post("/api/v1/suggestions/generate", json={"video_ids": [v["video_id"]], "count": 2})
        assert r.status_code == 202, r.text
        with lock:
            ids.append(r.json()["id"])
        c.close()
    ts = [threading.Thread(target=go, args=(v,)) for v in vids]
    [t.start() for t in ts]; [t.join() for t in ts]
    for i in ids:
        assert a.wait_job(i)["status"] == "succeeded"
    assert psql_app("select max(attempts), min(attempts), count(*) from jobs where type='suggestions.generate'") == "1|1|12"
    assert psql_app("select count(*) from (select video_id, title from suggestions group by 1,2 having count(*)>1) t") == "0"


# ─────────────────────────── 워커 강제 종료 반복 ───────────────────────────

def _consistency(a: Api, n_items: int, bid: int) -> dict:
    """반영 결과의 일관성 불변식: 영상당 성공 반영 ≤1, 제목은 성공 항목이면 새 제목·아니면 이전 제목, 남은 planned/running 없음."""
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert sum(b["counts"].values()) == n_items, b["counts"]
    assert psql_app("select count(*) from batch_items where status='running'") == "0"
    assert psql_app("select count(*) from changes where result='planned'") == "0"
    assert psql_app("select coalesce(max(c),0) from (select count(*) c from changes where change_type='apply' and result='success' group by video_id) t") in ("0", "1")
    vids = {v["video_id"]: v for v in a.videos()}
    n_ok = 0
    for it in b["items"]:
        if it["status"] == "success":
            n_ok += 1
            assert vids[it["video_id"]]["title"] == it["new_title"], it
        else:
            assert vids[it["video_id"]]["title"] == it["previous_title"], it
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == str(n_ok)
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == 52 * n_ok
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    return b


@pytest.mark.slow
def test_tc_it_310_worker_sigkill_loop_during_batch_no_duplicate_apply(fresh_demo):
    """TC-IT-310: 20건 배치를 처리하는 동안 워커를 SIGKILL 로 6번 죽였다 살린다. 끝나면 모든 항목이 확정(success/failed/skipped)이고, 영상당 반영 1건 이하,
    제목은 항목 결과와 일치, planned/running 잔여 없음, 쿼터는 성공 건수×52 와 일치, 감사 체인 정상(재시작 복구 ↔ 이중 반영 방지). 검증: W-010, NFR-W05, S-W12"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 20))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 20).status_code == 202
    kills = 0
    t0 = time.time()
    while kills < 6 and time.time() - t0 < 60:
        time.sleep(random.uniform(0.15, 0.9))
        wid = cid("worker")
        if wid:
            sh(["docker", "kill", "-s", "KILL", wid])
            kills += 1
        time.sleep(0.5)
        if sh(["docker", "inspect", "-f", "{{.State.Running}}", wid]).stdout.strip() != "true":
            sh(["docker", "start", wid])
    assert kills >= 3
    wid = cid("worker")
    if sh(["docker", "inspect", "-f", "{{.State.Running}}", wid]).stdout.strip() != "true":
        sh(["docker", "start", wid])
    b = a.wait_batch(bid, timeout=180)
    assert b["status"] == "done"
    b = _consistency(a, 20, bid)
    assert b["counts"]["pending"] == 0 and b["counts"]["running"] == 0
    # 복구 경로가 쓰였다면 감사에 recovered/interrupted 가 남는다(쓰이지 않았어도 불변식이 성립해야 한다)
    acts = [x["action"] for x in a.get("/api/v1/audit", params={"page_size": 200}).json()["items"]]
    assert acts.count("change.apply") == b["counts"]["success"] + b["counts"]["failed"] - sum(1 for _ in [] ), acts.count("change.apply")


@pytest.mark.slow
def test_tc_it_311_db_restart_during_batch_and_api_degrades_cleanly(fresh_demo):
    """TC-IT-311: 배치 처리 중 DB 컨테이너를 재시작한다. 그동안 /api/readyz 는 503(degraded), 일반 API 는 스택트레이스 없는 5xx problem+json 이고 nginx 가
    HTML 오류를 섞지 않으며, DB 가 돌아오면 api·worker 가 사람 손 없이 복구되어 배치가 끝나고 영상당 반영은 1건 이하. 검증: NFR-W04/05, S-W09, W-010"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 16))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 16).status_code == 202
    time.sleep(0.4)
    dbid = cid("db")
    p = sh(["docker", "stop", "-t", "10", dbid])
    seen_ready, seen_api = set(), []
    t0 = time.time()
    while time.time() - t0 < 6:
        r = a.c.get("/api/readyz")
        seen_ready.add(r.status_code)
        r2 = a.get("/api/v1/dashboard")
        seen_api.append((r2.status_code, r2.headers.get("content-type", "").split(";")[0], r2.text[:300]))
        time.sleep(0.5)
    sh(["docker", "start", dbid])
    wait_healthy(180)
    assert 503 in seen_ready, seen_ready
    for st, ct, body in seen_api:
        assert st in (500, 503), (st, body)
        assert ct == "application/problem+json", (st, ct, body)
        assert "Traceback" not in body and "psycopg" not in body and "sqlalchemy" not in body.lower() and "/app/" not in body
    # 복구 후 세션이 DB 에 남아 있으므로 같은 쿠키로 계속 쓸 수 있다
    assert a.get("/api/v1/dashboard").status_code == 200
    b = a.wait_batch(bid, timeout=180)
    assert b["status"] == "done"
    _consistency(a, 16, bid)


# ─────────────────────────── 오래된 running 복구 ───────────────────────────

def test_tc_it_320_stale_running_job_requeued_on_worker_start(fresh_demo):
    """TC-IT-320: 워커가 죽어 'running' 으로 남은 오래된 작업(11분 전)은 워커가 다시 뜨면 재큐되어 끝까지 처리된다(시도 2회). 시도 3회를 넘긴 오래된
    작업은 worker_lost 로 실패 처리된다. 검증: NFR-W05, W-010"""
    a = fresh_demo
    worker_stop()
    try:
        psql_app(
            "insert into jobs (id, type, status, payload, progress, total, attempts, run_after, locked_by, locked_at, created_at) values "
            "(gen_random_uuid(), 'videos.sync', 'running', '{}'::jsonb, 0, 0, 1, now() - interval '12 minutes', 'dead-worker:1', now() - interval '11 minutes', now() - interval '12 minutes'),"
            "(gen_random_uuid(), 'videos.sync', 'running', '{}'::jsonb, 0, 0, 3, now() - interval '12 minutes', 'dead-worker:2', now() - interval '11 minutes', now() - interval '12 minutes')"
        )
    finally:
        worker_start()
    t0 = time.time()
    while time.time() - t0 < 60:
        rows = psql_app("select status, attempts, coalesce(error,'') from jobs order by attempts").splitlines()
        if all(not r.startswith(("running", "queued")) for r in rows):
            break
        time.sleep(1)
    rows = psql_app("select status, attempts, coalesce(error,'') from jobs where locked_by like 'dead-worker%' or attempts>=1 order by attempts").splitlines()
    assert any(r.startswith("succeeded|2|") for r in rows), rows
    assert any(r.startswith("failed|") and "worker_lost" in r for r in rows), rows


def test_tc_it_321_stale_running_batch_item_and_planned_change_recovered_on_worker_start(fresh_demo):
    """TC-IT-321: 워커가 반영 도중 죽은 상태를 DB 에 만들어 두고(항목 running) 워커를 시작한다. (a) planned 기록 전에 끊김 → 항목이 pending 으로 돌아가 정상
    반영 (b) planned 기록 후 제목이 이미 바뀜 → 재조회로 success 확정 (c) planned 기록 후 제목이 안 바뀜 → failed[interrupted]·aborted, 제목 불변, 제안은 승인 대기로 복귀.
    어느 경우에도 영상당 반영은 1건 이하. 검증: W-010, NFR-W05, S-W12"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 3))
    worker_stop()
    try:
        bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
        assert a.execute(bid, 3).status_code == 202
        items = a.get(f"/api/v1/batches/{bid}").json()["items"]
        (i_a, i_b, i_c) = items
        # (a) running 으로만 표시(변경 기록 없음)
        psql_app(f"update batch_items set status='running', updated_at = now() - interval '1 minute' where id = {i_a['id']}")
        # (b)(c): planned 변경 기록을 만든다(백업 스니펫은 영상의 현재 snippet)
        for it, applied in ((i_b, True), (i_c, False)):
            psql_app(
                "insert into changes (video_id, suggestion_id, batch_id, change_type, previous_title, new_title, backup_snippet, reason, approver, approved_at, plan_hash, result, mode, created_at) "
                f"select v.video_id, s.id, {bid}, 'apply', v.title, s.title, v.snippet, 'it', a.approver, a.approved_at, a.plan_hash, 'planned', 'demo', now() "
                f"from videos v join suggestions s on s.id = {it['suggestion_id']} join approvals a on a.suggestion_id = s.id where v.video_id = '{it['video_id']}'"
            )
            cid_ = psql_app(f"select id from changes where video_id='{it['video_id']}' and result='planned'")
            psql_app(f"update batch_items set status='running', change_id={cid_}, updated_at = now() - interval '1 minute' where id = {it['id']}")
            psql_app(f"update approvals set used_at = now() where suggestion_id = {it['suggestion_id']}")
            if applied:   # 갱신은 이미 일어났다: 모의 유튜브(videos 표)의 제목과 snippet.title 을 새 제목으로
                psql_app(
                    f"update videos set title = s.title, snippet = jsonb_set(snippet, '{{title}}', to_jsonb(s.title::text)) from suggestions s "
                    f"where s.id = {it['suggestion_id']} and videos.video_id = '{it['video_id']}'"
                )
    finally:
        worker_start()
    b = a.wait_batch(bid, timeout=90)
    st = {x["video_id"]: x for x in b["items"]}
    vids = {v["video_id"]: v for v in a.videos()}
    assert st[i_a["video_id"]]["status"] == "success" and vids[i_a["video_id"]]["title"] == i_a["new_title"]      # (a)
    assert st[i_b["video_id"]]["status"] == "success" and vids[i_b["video_id"]]["title"] == i_b["new_title"]      # (b)
    assert st[i_c["video_id"]]["status"] == "failed" and "interrupted" in st[i_c["video_id"]]["skip_reason"]       # (c)
    assert vids[i_c["video_id"]]["title"] == i_c["previous_title"]
    assert psql_app(f"select result, error_code from changes where video_id='{i_c['video_id']}'") == "aborted|interrupted"
    assert psql_app("select count(*) from changes where result='planned'") == "0"
    assert psql_app("select coalesce(max(c),0) from (select count(*) c from changes where change_type='apply' and result='success' group by video_id) t") == "1"
    sg = {s["id"]: s["status"] for s in a.get("/api/v1/suggestions", params={"page_size": 50}).json()["items"]}
    assert sg[i_c["suggestion_id"]] in ("approved", "expired")
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True


# ─────────────────────────── 여러 워커 ───────────────────────────

@pytest.mark.slow
def test_tc_it_330_three_workers_respect_daily_cap(fresh_demo):
    """TC-IT-330: 워커 3개(정식 1 + api 컨테이너 안 추가 2)가 동시에 같은 배치를 처리해도 하루 상한(3)을 넘기지 않고 영상당 반영 1건, 쿼터 이중 차감 없음.
    검증: NFR-W03(동시 틱에서도 하루 상한 유지), S-W12"""
    a = fresh_demo
    set_cap(a, 3)
    ap = approve_many(a, usable_videos(a, 10))
    worker_stop()          # 추가 워커 2개 + 정식 워커가 같은 순간에 시작하도록
    try:
        bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
        assert a.execute(bid, 10).status_code == 202
    finally:
        pass
    script = '''
import subprocess, sys, time
ps = [subprocess.Popen([sys.executable, "-m", "ytweb.worker"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(2)]
time.sleep(22)
for p in ps: p.terminate()
for p in ps: p.wait(timeout=30)
print("done")
'''
    ev = threading.Thread(target=lambda: time.sleep(1) or worker_start())
    ev.start()
    p = inside_api_python(script, timeout=120)
    ev.join()
    assert "done" in p.stdout, p.stderr[-400:]
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert b["counts"]["success"] == 3 and b["counts"]["failed"] == 0 and b["counts"]["skipped"] == 0, b["counts"]
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == "3"
    assert psql_app("select coalesce(max(c),0) from (select count(*) c from changes group by video_id) t") == "1"
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == 3 * 52


# ─────────────────────────── 컨테이너 재시작 후 보존 ───────────────────────────

@pytest.mark.slow
def test_tc_it_340_data_session_and_approval_key_survive_restart_down_up_recreate(fresh_demo):
    """TC-IT-340: 반영 이력·승인 대기·세션·감사 체인·승인 서명 키(별도 볼륨)가 (1) 전체 재시작 (2) down→up(볼륨 유지) (3) api/worker/web 강제 재생성 뒤에도
    그대로이고, 재시작 전에 받은 승인이 재시작 뒤에도 유효해 반영된다. 검증: NFR-W04, W-016, SEC-W17, D-07"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 3))
    b1 = a.make_batch([ap[0]["id"]]).json()["batch"]["id"]
    assert a.execute(b1, 1).status_code == 202
    a.wait_batch(b1)
    snap0 = psql_owner("select table_name from information_schema.tables where table_schema='public' order by 1")
    counts = dc("exec", "-T", "db", "ytweb-db", "counts").stdout.strip()
    key_sha = dc("exec", "-T", "api", "sha256sum", "/var/lib/ytweb/secrets/approval_hmac.key").stdout.split()[0]
    def same(label: str):
        wait_healthy(240)
        c2 = dc("exec", "-T", "db", "ytweb-db", "counts").stdout.strip()
        assert c2 == counts, (label, counts, c2)
        assert dc("exec", "-T", "api", "sha256sum", "/var/lib/ytweb/secrets/approval_hmac.key").stdout.split()[0] == key_sha, label
        r = a.get("/api/v1/auth/me")
        assert r.json()["authenticated"] is True, label           # 같은 쿠키가 그대로 유효(세션은 DB)
        assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    assert dc("restart", timeout=300).returncode == 0
    same("restart")
    assert dc("down", timeout=300).returncode == 0
    vols = sh(["docker", "volume", "ls", "-q", "--filter", "label=com.docker.compose.project=harness-tmp-int"]).stdout.split()
    assert {v.split("_", 1)[1] for v in vols} == {"pgdata", "backups", "app_secrets"}
    up = dc("up", "-d", "--no-build", timeout=300)
    assert up.returncode == 0, up.stderr[-400:]
    same("down-up")
    assert dc("up", "-d", "--no-build", "--force-recreate", "api", "worker", "web", timeout=300).returncode == 0
    same("recreate")
    # 재시작 전 승인(ap[1])이 지금도 유효해 반영된다
    b2 = a.make_batch([ap[1]["id"]]).json()["batch"]["id"]
    assert a.execute(b2, 1).status_code == 202
    assert a.wait_batch(b2)["counts"]["success"] == 1
    assert snap0 == psql_owner("select table_name from information_schema.tables where table_schema='public' order by 1")
