"""IT 그룹 S — 단위 간 경합·상태(IT-300~): 응답 후 commit 수정(DEF-VF-B01/VA-010), 같은 키 재전송·다른 본문 재사용, 배치 이중·동시 실행, 승인 1회용·동시 승인,
PIN 잠금 동시 시도(DEF-VA-009), 워커·DB 재시작 중 중복 반영 방지, 오래된 running 복구, 재시작 뒤 데이터 보존.

네이티브 스택(IT_B_NATIVE=1)과 도커 스택에서 같은 코드가 돈다. 프로세스를 직접 죽이는 일부(native_only)는 도커 스택에서 건너뛴다(A 트랙이 컨테이너 단위로 본다).
"""
from __future__ import annotations

import json
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import itlib_b as ib
from itlib_b import (  # noqa: F401  (fresh_demo 는 픽스처)
    NATIVE, RELAXED, Api, approve_many, approved_suggestion, approval_key_sha, clone_api, counts, db_kill9_and_start, db_start, db_stop, forge_approval_expiry,
    fresh_demo, inside_python, psql_app, psql_owner, rollback, run_extra_workers, run_threads, server_logs, set_cap, shift_days, usable_videos,
    wait_healthy, wait_until, worker_kill_and_restart, worker_start, worker_stop,
)

HERE = Path(__file__).resolve().parent
native_only = pytest.mark.skipif(not NATIVE, reason="프로세스·DB 를 직접 죽이는 시험(도커 스택은 A 트랙이 컨테이너 단위로 확인)")


# ─────────────────────────── 응답 후 commit(DEF-VF-B01 / DEF-VA-010) ───────────────────────────

@pytest.mark.slow
def test_it_300_session_then_immediate_requests_30_times(fresh_demo):
    """IT-300: '세션 발급 직후 조회·변경·작업 생성·작업 조회'를 30회 반복해 401/403/404 가 한 번도 없다(수정 전에는 첫 요청이 401 이 되는 경우가 있었음).
    속도 제한을 거는 스택에서는 세션 발급 분당 10회 때문에 시간이 걸린다. 많은 횟수의 반복은 IT-301/316. 검증: DEF-VF-B01, S-W02"""
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
def test_it_301_race_second_server_many_iterations(fresh_demo):
    """IT-301: 속도 제한만 풀어 둔 제2 서버(같은 코드·같은 DB)에서 (a) 세션 발급 직후 조회·변경 (b) 작업 생성 직후 조회 (c) PIN 설정 직후 '현재 PIN 없는' 변경을
    각 300회 반복해 실패 0건. (c) 는 PIN 우회 보안 영향이 있는 경합이다. A 트랙의 inside_race.py 를 그대로 실행한다. 검증: DEF-VF-B01/DEF-VA-010, S-W02, SEC-W19"""
    p = inside_python((HERE / "inside_race.py").read_text(encoding="utf-8"), timeout=900)
    assert p.returncode == 0, (p.stdout[-800:], p.stderr[-800:])
    line = [x for x in p.stdout.splitlines() if x.startswith("RACE_RESULT ")][-1]
    d = json.loads(line[len("RACE_RESULT "):])
    assert d["n"] >= 300
    assert d["session_then_request_bad_count"] == 0, d
    assert d["job_then_get_bad_count"] == 0, d
    assert d["pin_set_then_change_bad_count"] == 0, d
    assert d["pin_enabled_at_end"] is False


@pytest.mark.skipif(not RELAXED, reason="속도 제한이 없는 스택에서만 수백 회 반복 가능")
@pytest.mark.slow
def test_it_316_http_burst_after_commit_400_iterations(fresh_demo):
    """IT-316: 실제 HTTP(별도 연결)로 '응답을 받자마자 다음 요청'을 400회: (a) 설정 변경 직후 읽기 (b) 승인 직후 목록 (c) 배치 생성 직후 단건 조회 (d) 작업 생성 직후 조회.
    응답 후 commit 수정(DEF-VA-010)이 되돌아가면 한 번이라도 옛 값이 읽힌다. 검증: DEF-VA-010, NFR-W03"""
    a = fresh_demo
    set_cap(a, 20)
    bad: list = []
    vids = usable_videos(a, 4)
    for i in range(400):
        cap = 1 + (i % 20)
        c1 = clone_api(a)                                   # 요청마다 새 연결(브라우저의 병렬 연결과 같은 효과)
        c1.patch("/api/v1/settings", json={"daily_apply_cap": cap})
        c2 = clone_api(a)
        got = c2.get("/api/v1/settings").json()["daily_apply_cap"]
        if got != cap:
            bad.append(("settings", i, cap, got))
        r = clone_api(a).post("/api/v1/videos/sync")
        r2 = clone_api(a).get(f"/api/v1/jobs/{r.json()['id']}")
        if r.status_code != 202 or r2.status_code != 200:
            bad.append(("job", i, r.status_code, r2.status_code))
        for x in (c1, c2):
            x.close()
    s = a.make_suggestion(vids[0]["video_id"], 3)
    ok = [x for x in s if x["validation_result"] != "block" and not x["strict"]][0]
    for i in range(50):
        r = clone_api(a).approve(ok["id"]) if i == 0 else None
    seen = clone_api(a).get("/api/v1/suggestions", params={"video_id": vids[0]["video_id"]}).json()["items"]
    if {x["id"]: x["status"] for x in seen}[ok["id"]] != "approved":
        bad.append(("approve", ok["id"]))
    rb = clone_api(a).make_batch([ok["id"]])
    if clone_api(a).get(f"/api/v1/batches/{rb.json()['batch']['id']}").status_code != 200:
        bad.append(("batch", rb.status_code))
    assert not bad, bad[:10]


# ─────────────────────────── 멱등성 키 ───────────────────────────

def test_it_302_same_key_concurrent_create_batch_yields_one_batch(fresh_demo):
    """IT-302: 같은 Idempotency-Key 로 배치 생성을 10개 스레드가 동시에 보내도 배치는 1개이며 응답은 201(첫 응답 또는 재생) 또는 409
    idempotency_in_progress 뿐이다. 이후 같은 키 재전송은 같은 배치 id 를 재생한다. 검증: S-W12, API.md 1-6"""
    a = fresh_demo
    ap = approve_many(a, usable_videos(a, 3))
    key = "it-302-concurrent-key-1"
    body = {"suggestion_ids": [s["id"] for s in ap], "note": "경합"}

    def go(_i):
        c = clone_api(a)
        r = c.post("/api/v1/batches", json=body, idem=key)
        c.close()
        return r.status_code, r.json()
    res = run_threads(10, go)
    assert all(isinstance(x, tuple) for x in res), res
    assert all(c in (201, 409) for c, _ in res), [(c, d.get("code")) for c, d in res]
    assert any(c == 201 for c, _ in res)
    assert all(d.get("code") == "idempotency_in_progress" for c, d in res if c == 409)
    assert a.get("/api/v1/batches").json()["total"] == 1
    again = a.post("/api/v1/batches", json=body, idem=key)
    assert again.status_code == 201 and again.json()["batch"]["id"] == a.get("/api/v1/batches").json()["items"][0]["id"]
    assert psql_app("select count(*) from batch_items") == "3"


def test_it_304_idempotency_key_reuse_with_other_body_ttl_and_worker_purge(fresh_demo):
    """IT-304: 같은 키에 다른 본문(배치 생성·실행·롤백 각각)은 422 idempotency_key_reuse 이고 첫 요청의 효과는 그대로. 키 보관 24시간이 지나면(행을 옛날로 옮겨 시늉)
    같은 키로 새 요청이 처리되고, 48시간이 지난 키는 워커가 시작될 때 정리된다(멱등성 ↔ 워커 유지보수 경계). 동시 8건(같은 키·다른 본문)은 정확히 1건만 처리.
    검증: S-W12, API.md 1-6"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 6))
    k = "it-304-key-batch-0001"
    r1 = a.post("/api/v1/batches", json={"suggestion_ids": [ap[0]["id"]], "note": "첫째"}, idem=k)
    assert r1.status_code == 201
    r2 = a.post("/api/v1/batches", json={"suggestion_ids": [ap[1]["id"]], "note": "첫째"}, idem=k)          # 같은 키·다른 제안
    r3 = a.post("/api/v1/batches", json={"suggestion_ids": [ap[0]["id"]], "note": "둘째"}, idem=k)          # 같은 키·다른 메모
    assert r2.status_code == r3.status_code == 422 and r2.json()["code"] == r3.json()["code"] == "idempotency_key_reuse"
    assert a.get("/api/v1/batches").json()["total"] == 1
    assert a.get(f"/api/v1/suggestions", params={"status": "approved"}).json()["total"] == 6
    # 경로가 다르면 같은 키도 다른 요청: 실행에 쓴 키를 롤백에 쓰면 재사용 오류
    bid = r1.json()["batch"]["id"]
    ke = "it-304-key-exec-0001"
    assert a.execute(bid, 1, idem=ke).status_code == 202
    a.wait_batch(bid)
    ch = a.get("/api/v1/changes").json()["items"][0]
    bad = a.post(f"/api/v1/changes/{ch['id']}/rollback", json={"typed_video_id": ch["video_id"], "approver": "가"}, idem=ke)
    assert bad.status_code == 422 and bad.json()["code"] == "idempotency_key_reuse"
    assert psql_app("select count(*) from changes where change_type='rollback'") == "0"
    # 동시 8건: 같은 키, 서로 다른 메모 → 처리는 1건
    kc = "it-304-key-race-0001"
    def go(i):
        c = clone_api(a)
        r = c.post("/api/v1/batches", json={"suggestion_ids": [ap[2]["id"]], "note": f"경합{i}"}, idem=kc)
        c.close()
        return r.status_code, r.json().get("code", "")
    res = run_threads(8, go)
    assert all(isinstance(x, tuple) for x in res), res
    assert sorted(c for c, _ in res).count(201) == 1, res
    assert all((c, code) in ((201, ""), (409, "idempotency_in_progress"), (422, "idempotency_key_reuse")) for c, code in res), res
    assert psql_app(f"select count(*) from batch_items where suggestion_id={ap[2]['id']}") == "1"
    # 24시간 보관: 키를 25시간 전으로 옮기면 같은 키로 새 요청이 처리된다
    psql_owner(f"update idempotency_keys set created_at = created_at - interval '25 hours' where key = '{k}'")
    r4 = a.post("/api/v1/batches", json={"suggestion_ids": [ap[3]["id"]], "note": "새 요청"}, idem=k)
    assert r4.status_code == 201 and r4.json()["batch"]["id"] != r1.json()["batch"]["id"]
    # 48시간 보관 정리: 워커가 시작될 때 지운다
    psql_owner(f"update idempotency_keys set created_at = created_at - interval '49 hours' where key = '{ke}'")
    assert psql_app(f"select count(*) from idempotency_keys where key='{ke}'") == "1"
    worker_stop()
    worker_start()
    wait_until(lambda: psql_app(f"select count(*) from idempotency_keys where key='{ke}'") == "0", 30, what="워커의 오래된 키 정리")
    assert psql_app(f"select count(*) from idempotency_keys where key='{k}'") == "1"      # 25시간 된 키는 (새 요청의 행으로) 남아 있다


def test_it_303_concurrent_jobs_each_processed_exactly_once(fresh_demo):
    """IT-303: 제안 생성 작업 12개를 동시에 만들면 각 작업이 정확히 한 번(attempts=1)만 처리되고 모두 성공한다(작업 큐 SKIP LOCKED ↔ 도메인 핸들러). 검증: S-W12, NFR-W03, W-004"""
    a = fresh_demo
    vids = usable_videos(a, 12)

    def go(i):
        c = clone_api(a)
        r = c.post("/api/v1/suggestions/generate", json={"video_ids": [vids[i]["video_id"]], "count": 2})
        c.close()
        assert r.status_code == 202, r.text
        return r.json()["id"]
    ids = run_threads(12, go)
    assert all(isinstance(i, str) for i in ids), ids
    for i in ids:
        assert a.wait_job(i)["status"] == "succeeded"
    assert psql_app("select max(attempts), min(attempts), count(*) from jobs where type='suggestions.generate'") == "1|1|12"
    assert psql_app("select count(*) from (select video_id, title from suggestions group by 1,2 having count(*)>1) t") == "0"


def test_it_317_sync_taps_are_deduplicated_into_one_job(fresh_demo):
    """IT-317: 영상 불러오기를 연타(워커가 아직 처리 전)하면 새 작업을 만들지 않고 진행 중인 같은 작업을 돌려준다(API.md EVT-W11). 동시 6건도 작업은 1개이며,
    끝난 뒤의 새 요청은 새 작업. 검증: W-001, S-W12"""
    a = fresh_demo
    worker_stop()
    try:
        r1 = a.post("/api/v1/videos/sync")
        r2 = a.post("/api/v1/videos/sync")
        assert r1.status_code == r2.status_code == 202 and r1.json()["id"] == r2.json()["id"]
        res = run_threads(6, lambda i: clone_api(a).post("/api/v1/videos/sync").json()["id"])
        assert set(res) == {r1.json()["id"]}, res
        assert psql_app("select count(*) from jobs where type='videos.sync' and status='queued'") == "1"
    finally:
        worker_start()
    a.wait_job(r1.json()["id"])
    r3 = a.post("/api/v1/videos/sync")
    assert r3.status_code == 202 and r3.json()["id"] != r1.json()["id"]
    a.wait_job(r3.json()["id"])


@pytest.mark.skipif(not RELAXED, reason="세션을 20개 넘게 만들려면 세션 발급 속도 제한(분당 10)을 푼 스택이 필요")
def test_it_350_session_cap_ttl_and_worker_purge(fresh_demo):
    """IT-350: 세션은 최대 20개(22번째 로그인이 오래된 것부터 밀어냄 — 밀려난 쿠키는 즉시 401), 쿠키 Max-Age=12시간, 만료된 세션은 다음 요청에서 401 이 되고
    행이 지워지며, 만료 행이 남아 있으면 워커 유지보수가 정리한다(세션 ↔ 워커 경계). 검증: S-W02, API.md 1-1, 3장"""
    a = fresh_demo
    clients = [a]
    for _ in range(21):
        c = Api()
        r = c.login()
        assert r.status_code == 200
        clients.append(c)
    assert "max-age=43200" in r.headers["set-cookie"].lower()
    assert psql_app("select count(*) from sessions") == "20"
    codes = [c.get("/api/v1/dashboard").status_code for c in clients]
    assert codes[:2] == [401, 401] and codes[2:] == [200] * 20, codes
    last = clients[-1]
    psql_owner("update sessions set expires_at = now() - interval '1 second' where id <> (select id from sessions order by created_at desc limit 1)")
    assert last.get("/api/v1/dashboard").status_code == 200
    expired_probe = clients[5]
    assert expired_probe.get("/api/v1/dashboard").status_code == 401
    assert expired_probe.get("/api/v1/auth/me").json()["authenticated"] is False
    left = int(psql_app("select count(*) from sessions"))
    assert left < 20                                              # 방금 본 만료 행은 지워졌다
    worker_stop()
    worker_start()                                                # 기동 직후 유지보수가 나머지 만료 행을 정리
    wait_until(lambda: psql_app("select count(*) from sessions") == "1", 30, what="워커의 만료 세션 정리")
    assert last.get("/api/v1/dashboard").status_code == 200


# ─────────────────────────── 승인 1회용·동시성 ───────────────────────────

def test_it_306_approval_is_single_use_and_concurrent_approve_reject_is_consistent(fresh_demo):
    """IT-306: (a) 같은 제안을 8개 스레드가 동시에 승인해도 승인은 1개(나머지 409 suggestion_state), 감사 기록도 1건. (b) 승인과 반려를 동시에 보내도
    최종 상태는 '승인(approvals 행 있음)' 또는 '반려(approvals 행 없음)' 중 하나로 일관(12쌍 반복). (c) 반영이 끝난 제안은 다시 승인·수정·반려할 수 없고,
    DB 에서 상태만 approved 로 되돌려도 사용된 승인(used_at)은 배치에 담기지 않는다(approval_used). 검증: SEC-W17, W-007, S-W12"""
    a = fresh_demo
    set_cap(a, 20)
    vids = usable_videos(a, 20)
    sug = a.make_suggestion(vids[0]["video_id"], 3)
    ok = [x for x in sug if x["validation_result"] != "block" and not x["strict"]][0]

    def go(i):
        c = clone_api(a)
        r = c.approve(ok["id"], f"동시승인{i}")
        c.close()
        return r.status_code, r.json().get("code", "")
    res = run_threads(8, go)
    assert all(isinstance(x, tuple) for x in res), res
    assert sorted(c for c, _ in res).count(200) == 1 and all(code == "suggestion_state" for c, code in res if c != 200), res
    assert psql_app(f"select count(*) from approvals where suggestion_id={ok['id']}") == "1"
    assert sum(1 for x in a.get("/api/v1/audit", params={"page_size": 200}).json()["items"] if x["action"] == "suggestion.approve") == 1
    # (b) 승인 ↔ 반려 동시
    for k in range(12):
        s = [x for x in a.make_suggestion(vids[1 + k]["video_id"], 1)][0]
        if s["status"] != "candidate":
            continue
        def go2(i, sid=s["id"]):
            c = clone_api(a)
            r = c.approve(sid) if i == 0 else c.post(f"/api/v1/suggestions/{sid}/reject")
            c.close()
            return r.status_code
        res2 = run_threads(2, go2)
        st = a.get("/api/v1/suggestions", params={"video_id": s["video_id"]}).json()["items"]
        cur = {x["id"]: x for x in st}[s["id"]]
        has_ap = psql_app(f"select count(*) from approvals where suggestion_id={s['id']}")
        assert (cur["status"] == "approved" and has_ap == "1" and cur["approval"]) or (cur["status"] == "rejected" and has_ap == "0" and cur["approval"] is None), (cur["status"], has_ap, res2)
    # (c) 사용된 승인
    ch = ib.apply_via_batch(a, ok["id"])
    for call in (lambda: a.approve(ok["id"]), lambda: a.post(f"/api/v1/suggestions/{ok['id']}/reject"), lambda: a.patch(f"/api/v1/suggestions/{ok['id']}", json={"title": ok["title"] + " 수정"})):
        r = call()
        assert r.status_code == 409 and r.json()["code"] == "suggestion_state", r.text[:200]
    psql_owner(f"update suggestions set status='approved' where id={ok['id']}")
    r = a.make_batch([ok["id"]])
    assert r.status_code == 422 and r.json()["code"] == "batch_empty" and ("이미 사용" in r.json()["detail"] or "1회용" in r.json()["detail"]), r.text[:300]
    assert psql_app(f"select count(*) from changes where video_id='{ch['video_id']}' and change_type='apply' and result='success'") == "1"


def test_it_307_same_suggestion_in_concurrent_batches_and_same_video_concurrent_execute(fresh_demo):
    """IT-307: (a) 같은 제안을 8개 스레드가 서로 다른 키로 동시에 배치에 담으면 항목은 1개만 생긴다(부분 유일 인덱스 ↔ 사전 점검). (b) 같은 영상의 서로 다른 제안을
    각각 담은 두 배치를 동시에 실행 확정해도(워커 정지 중) 영상은 한 번만 바뀐다. 검증: W-008, W-010, S-W12, NFR-W03"""
    a = fresh_demo
    set_cap(a, 20)
    s0 = approved_suggestion(a, usable_videos(a, 1)[0]["video_id"])
    b0 = a.make_batch([s0["id"]])                              # 순차: 이미 초안에 담긴 제안은 두 번째 초안에 담기지 않는다(사전 점검 단계에서 막힘)
    assert b0.status_code == 201
    dup = a.make_batch([s0["id"]])
    assert dup.status_code == 422 and dup.json()["code"] == "batch_empty" and "이미" in dup.json()["detail"], dup.text[:300]
    assert a.post(f"/api/v1/batches/{b0.json()['batch']['id']}/cancel").status_code == 200

    def go(i):
        c = clone_api(a)
        r = c.make_batch([s0["id"]], note=f"동시{i}")
        c.close()
        return r.status_code, r.json().get("code", "")
    res = run_threads(8, go)
    assert all(isinstance(x, tuple) for x in res), res
    assert sorted(c for c, _ in res).count(201) == 1, res
    assert all(c in (201, 409, 422) for c, _ in res), res
    assert psql_app(f"select count(*) from batch_items where suggestion_id={s0['id']} and status in ('pending','running')") == "1"
    assert psql_app("select count(*) from batches") == "2", "실패한 요청이 빈 배치를 남기지 않는다(취소된 1개 + 새 초안 1개)"
    # (b)
    two = ib.two_pass_suggestions(a, usable_videos(a, 40)[5:], 2)
    for x in two:
        assert a.approve(x["id"]).status_code == 200
    b1 = a.make_batch([two[0]["id"]]).json()["batch"]["id"]
    b2 = a.make_batch([two[1]["id"]]).json()["batch"]["id"]
    worker_stop()
    try:
        def go2(i):
            c = clone_api(a)
            r = c.execute([b1, b2][i], 1)
            c.close()
            return r.status_code
        res2 = run_threads(2, go2)
        assert all(c in (202, 409) for c in res2), res2
    finally:
        worker_start()
    executed = [b for b, c in zip((b1, b2), res2) if c == 202]
    for b in executed:
        a.wait_batch(b, timeout=90)
    v = two[0]["video_id"]
    assert psql_app(f"select count(*) from changes where video_id='{v}' and change_type='apply' and result='success'") == "1"
    assert psql_app("select count(*) from changes where result='planned'") == "0"


def test_it_309_concurrent_rollback_applies_once(fresh_demo):
    """IT-309: 같은 변경을 8개 스레드가 서로 다른 키로 동시에 롤백하면 롤백은 1건만 만들어지고 영상 제목은 원래 제목, 쿼터는 롤백 1회분(52)만 더 쓰며,
    나머지는 409(later_change_exists·pending_change_exists·already_restored 등)이다. 검증: W-011, S-W12, NFR-W03"""
    a = fresh_demo
    set_cap(a, 20)
    s = approved_suggestion(a, usable_videos(a, 1)[0]["video_id"])
    ch = ib.apply_via_batch(a, s["id"])
    q0 = a.get("/api/v1/dashboard").json()["quota"]["used"]

    def go(i):
        c = clone_api(a)
        r = rollback(c, ch, who=f"복구자{i}")
        c.close()
        return r.status_code, r.json().get("code", "")
    res = run_threads(8, go)
    assert all(isinstance(x, tuple) for x in res), res
    assert sorted(c for c, _ in res).count(201) == 1, res
    assert all(c in (201, 409) for c, _ in res), res
    assert psql_app("select count(*) from changes where change_type='rollback'") == "1"
    assert psql_app("select count(*) from changes where result='planned'") == "0"
    assert {v["video_id"]: v["title"] for v in a.videos()}[ch["video_id"]] == ch["previous_title"]
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == q0 + 52
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True


# ─────────────────────────── PIN 잠금 동시 시도(DEF-VA-009) ───────────────────────────

def test_it_305_pin_lock_concurrent_guesses_cannot_exceed_five(fresh_demo):
    """IT-305: PIN 을 설정한 뒤 틀린 PIN 을 동시에 10번 보내면 실패 카운터 갱신이 서로 덮어쓰이지 않아 정확히 4번만 pin_invalid(401)이고 5번째부터 pin_locked(429)다
    (DEF-VA-009: 동시 추측으로 잠금 무력화). 잠금 중에는 맞는 PIN 도 거부, 감사 로그에 session.denied 가 남고 PIN 값은 없다. 검증: SEC-W19, SEC-W20, S-W09"""
    a = fresh_demo
    assert a.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "615243"}}).status_code == 200
    ib.strict_window_clear()
    n = 10

    def go(i):
        c = Api(throttle=0, retry429=False)
        r = c.c.post("/api/v1/auth/session", json={"pin": f"{100000 + i * 7}"}, headers={"Origin": ib.ORIGIN_OK})
        c.close()
        try:
            return r.status_code, r.json().get("code", "")
        except Exception:
            return r.status_code, ""
    res = run_threads(n, go)
    assert all(isinstance(x, tuple) for x in res), res
    codes = [code for _, code in res]
    if "rate_limited" in codes:
        pytest.skip("세션 발급 속도 제한이 먼저 걸림 — 제한을 푼 스택에서 확인")
    assert codes.count("pin_invalid") == 4 and codes.count("pin_locked") == n - 4, codes
    fail = json.loads(psql_app("select value::text from settings_kv where key = 'pin_fail'"))
    assert fail["lockouts"] == 1 and fail["count"] == 0 and fail["locked_until"], fail
    c = Api(retry429=False)
    r = c.login("615243")
    assert r.status_code == 429 and r.json()["code"] == "pin_locked" and int(r.headers["retry-after"]) >= 60
    # 두 번째 잠금은 두 배(10분)로 늘어난다 — 잠금 시각을 과거로 돌려 풀고 다시 5회 틀린다
    psql_owner("update settings_kv set value = jsonb_set(value, '{locked_until}', to_jsonb((now() - interval '1 minute')::text)) where key = 'pin_fail'")
    codes2 = [Api(retry429=False).login(f"11111{i}").json().get("code") for i in range(5)] if RELAXED else []
    if RELAXED:
        assert codes2 == ["pin_invalid"] * 4 + ["pin_locked"], codes2
        r = Api(retry429=False).login("615243")
        assert r.status_code == 429 and 590 <= int(r.headers["retry-after"]) <= 601, r.headers.get("retry-after")
    audit = a.get("/api/v1/audit", params={"page_size": 200}).json()
    assert sum(1 for x in audit["items"] if x["action"] == "session.denied") == n + 1 + (6 if RELAXED else 0)      # 동시 추측 n건 + 잠금 중 올바른 PIN 1건(+ 2차 잠금 6건)
    assert "615243" not in json.dumps(audit["items"]) and "615243" not in server_logs()
    assert audit["chain_ok"] is True


# ─────────────────────────── 워커·DB·API 재시작 ───────────────────────────

def _consistency(a: Api, n_items: int, bid: int) -> dict:
    """반영 결과의 일관성 불변식: 영상당 성공 반영 ≤1, 제목은 성공 항목이면 새 제목·아니면 이전 제목, 남은 planned/running 없음, 쿼터는 성공 건수 이상·중단된 건수까지."""
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert sum(b["counts"].values()) == n_items, b["counts"]
    assert psql_app("select count(*) from batch_items where status='running'") == "0"
    assert psql_app("select count(*) from changes where result='planned'") == "0"
    assert ib.count_success_per_video_max() in ("0", "1")
    vids = {v["video_id"]: v for v in a.videos()}
    n_ok = 0
    for it in b["items"]:
        if it["status"] == "success":
            n_ok += 1
            assert vids[it["video_id"]]["title"] == it["new_title"], it
        else:
            assert vids[it["video_id"]]["title"] == it["previous_title"], it
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == str(n_ok)
    aborted = int(psql_app("select count(*) from changes where result='aborted'"))
    used = a.get("/api/v1/dashboard").json()["quota"]["used"]
    assert 52 * n_ok <= used <= 52 * (n_ok + aborted + 1), (used, n_ok, aborted)   # 쓰기 직전에 끊긴 항목의 선예약(52)은 보수적으로 남을 수 있다
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    return b


@pytest.mark.slow
def test_it_310_worker_sigkill_loop_during_batch_no_duplicate_apply(fresh_demo):
    """IT-310: 20건 배치를 처리하는 동안 워커를 SIGKILL 로 6번 죽였다 살린다. 끝나면 모든 항목이 확정이고, 영상당 반영 1건 이하, 제목은 항목 결과와 일치,
    planned/running 잔여 없음, 쿼터는 성공 건수×52 이상(끊긴 항목 선예약 허용), 감사 체인 정상(재시작 복구 ↔ 이중 반영 방지). 검증: W-010, NFR-W05, S-W12"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 20))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 20).status_code == 202
    kills = 0
    t0 = time.time()
    while kills < 6 and time.time() - t0 < 60:
        time.sleep(random.uniform(0.1, 0.8))
        worker_kill_and_restart()
        kills += 1
        time.sleep(0.4)
        if a.get(f"/api/v1/batches/{bid}").json()["status"] == "done":
            break
    b = a.wait_batch(bid, timeout=180)
    assert b["status"] == "done"
    b = _consistency(a, 20, bid)
    assert b["counts"]["pending"] == 0 and b["counts"]["running"] == 0
    acts = [x["action"] for x in a.get("/api/v1/audit", params={"page_size": 200}).json()["items"]]
    n_recovered = acts.count("batch.item.recovered")                # 재시작 복구로 확정된 반영은 change.apply 가 아니라 recovered 로 남는다(DEF-7B-002 참고)
    assert b["counts"]["success"] - n_recovered <= acts.count("change.apply") <= b["counts"]["success"], (acts.count("change.apply"), n_recovered, b["counts"])


@native_only
@pytest.mark.slow
def test_it_312_db_sigkill_during_batch_recovers_without_duplicate_apply(fresh_demo):
    """IT-312: 배치 처리 중 PostgreSQL 을 SIGKILL(전원 차단 시늉)했다가 충돌 복구로 다시 띄운다. API 는 그동안 5xx problem+json, DB 가 돌아오면 사람 손 없이 이어서
    끝나고(죽은 워커는 재시작 정책으로 되살림) 영상당 반영 1건 이하·승인 소진·감사 체인 정상. 검증: NFR-W04/05, S-W09, W-010"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 16))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 16).status_code == 202
    time.sleep(0.5)
    ib.nat.pg_kill9()
    codes = []
    for _ in range(4):
        r = a.get("/api/v1/dashboard")
        codes.append((r.status_code, r.headers.get("content-type", "").split(";")[0], r.text[:200]))
        time.sleep(0.4)
    died = db_start()
    for st, ct, body in codes:
        assert st in (500, 503) and ct == "application/problem+json", (st, ct, body)
        assert "Traceback" not in body and "psycopg" not in body
    b = a.wait_batch(bid, timeout=180)
    assert b["status"] == "done"
    _consistency(a, 16, bid)
    print("worker_died_during_db_outage", died)


@pytest.mark.slow
def test_it_311_db_restart_during_batch_and_api_degrades_cleanly(fresh_demo):
    """IT-311: 배치 처리 중 DB 를 중지했다가 시작한다. 그동안 /api/readyz 는 503(degraded), 일반 API 는 스택트레이스 없는 5xx problem+json 이고,
    DB 가 돌아오면 api·worker 가 사람 손 없이 복구되어 배치가 끝나고 영상당 반영은 1건 이하. 검증: NFR-W04/05, S-W09, W-010"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 16))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 16).status_code == 202
    time.sleep(0.4)
    db_stop()
    seen_ready, seen_api = set(), []
    t0 = time.time()
    while time.time() - t0 < 6:
        r = a.c.get("/api/readyz")
        seen_ready.add(r.status_code)
        r2 = a.get("/api/v1/dashboard")
        seen_api.append((r2.status_code, r2.headers.get("content-type", "").split(";")[0], r2.text[:300]))
        time.sleep(0.5)
    died = db_start()
    wait_healthy(180)
    assert 503 in seen_ready, seen_ready
    for st, ct, body in seen_api:
        assert st in (500, 503), (st, body)
        assert ct == "application/problem+json", (st, ct, body)
        assert "Traceback" not in body and "psycopg" not in body and "sqlalchemy" not in body.lower() and "/app/" not in body
    assert a.get("/api/v1/dashboard").status_code == 200      # 세션은 DB 에 있으므로 같은 쿠키로 계속 쓴다
    b = a.wait_batch(bid, timeout=180)
    assert b["status"] == "done"
    _consistency(a, 16, bid)
    print("worker_died_during_db_outage", died)


def test_it_313_api_restart_keeps_session_and_idempotent_replay(fresh_demo):
    """IT-313: API 서버를 재시작해도 (a) 같은 쿠키·CSRF 가 그대로 유효(세션은 DB) (b) 재시작 전에 쓴 Idempotency-Key 의 재전송이 첫 응답을 그대로 재생(키는 DB)
    (c) 진행 중이던 배치 작업은 워커가 계속 처리. 검증: NFR-W04, S-W12, API.md 1-6"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 4))
    k = "it-313-key-create-0001"
    body = {"suggestion_ids": [s["id"] for s in ap], "note": "재시작"}
    r1 = a.post("/api/v1/batches", json=body, idem=k)
    assert r1.status_code == 201
    bid = r1.json()["batch"]["id"]
    ke = "it-313-key-exec-00001"
    e1 = a.execute(bid, 4, idem=ke)
    assert e1.status_code == 202
    ib.api_restart()
    me = a.get("/api/v1/auth/me")
    assert me.status_code == 200 and me.json()["authenticated"] is True and me.json()["csrf_token"] == a.csrf
    r2 = a.post("/api/v1/batches", json=body, idem=k)
    assert r2.status_code == 201 and r2.json() == r1.json()
    e2 = a.execute(bid, 4, idem=ke)
    assert e2.status_code == 202 and e2.json()["job"]["id"] == e1.json()["job"]["id"]
    done = a.wait_batch(bid)
    assert done["counts"]["success"] == 4
    assert psql_app("select count(*) from jobs where type='batch.execute'") == "1"


@native_only
def test_it_314_worker_sigterm_finishes_current_item_and_leaves_nothing_running(fresh_demo):
    """IT-314: 배치 처리 중 워커에 SIGTERM(정상 종료 요청)을 보내면 현재 항목은 마치고 멈춘다 — running 항목·planned 변경이 남지 않고, 워커를 다시 띄우면 남은 항목만
    이어서 처리하며 영상당 반영 1건. 검증: NFR-W05, W-010, S-W12"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 14))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 14).status_code == 202
    wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 1, 30, step=0.05, what="첫 반영")
    ib.nat.proc_stop("worker")                                # SIGTERM → 현재 항목까지만
    assert psql_app("select count(*) from batch_items where status='running'") == "0"
    assert psql_app("select count(*) from changes where result='planned'") == "0"
    mid = a.get(f"/api/v1/batches/{bid}").json()["counts"]
    worker_start()
    b = a.wait_batch(bid, timeout=120)
    assert b["counts"]["success"] == 14 and mid["success"] <= 14
    assert ib.count_success_per_video_max() == "1"
    _consistency(a, 14, bid)


@native_only
@pytest.mark.xfail(strict=True, reason="DEF-7B-001: 워커가 배치 처리 도중 비정상 종료하면 batch.execute 작업이 running(진행 3/20)으로 최대 10분 이상 남아 대시보드 active_job 이 계속 '진행 중'으로 보인다(항목은 스케줄러 틱이 끝내므로 배치는 done) — 워커 기동 시 이전 워커가 잡은 작업을 즉시 재큐하지 않음")
def test_it_318_job_row_is_closed_after_worker_crash_when_batch_finishes(fresh_demo):
    """IT-318(결함 고정, DEF-7B-001): 배치 처리 도중 워커를 SIGKILL 하고 다시 띄워 배치가 done 이 된 뒤 30초 안에 그 batch.execute 작업이 종료 상태가 되고
    대시보드 active_job 이 비는가. 현재는 작업이 running 으로 남는다(10분 뒤 stale 재큐). 검증: NFR-W05, W-010, 대시보드 진행 표시"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 20))
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    jid = a.execute(bid, 20).json()["job"]["id"]
    wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 2, 30, 0.02, what="일부 반영")
    worker_kill_and_restart()
    assert a.wait_batch(bid, timeout=120)["status"] == "done"
    wait_until(lambda: a.get(f"/api/v1/jobs/{jid}").json()["status"] in ("succeeded", "failed"), 30, what="작업 종료")
    assert a.get("/api/v1/dashboard").json()["active_job"] is None


# ─────────────────────────── 오래된 running 복구 ───────────────────────────

def test_it_320_stale_running_job_requeued_on_worker_start(fresh_demo):
    """IT-320: 워커가 죽어 'running' 으로 남은 오래된 작업(11분 전)은 워커가 다시 뜨면 재큐되어 끝까지 처리된다(시도 2회). 시도 3회를 넘긴 오래된
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


def test_it_321_stale_running_batch_item_and_planned_change_recovered_on_worker_start(fresh_demo):
    """IT-321: 워커가 반영 도중 죽은 상태를 DB 에 만들어 두고(항목 running) 워커를 시작한다. (a) planned 기록 전에 끊김 → 항목이 pending 으로 돌아가 정상
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
        psql_app(f"update batch_items set status='running', updated_at = now() - interval '1 minute' where id = {i_a['id']}")
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
    acts = [x["action"] for x in a.get("/api/v1/audit", params={"page_size": 200}).json()["items"]]
    assert acts.count("batch.item.recovered") >= 2


def test_it_322_recovery_is_not_triggered_for_fresh_running_items_and_unknown_result_is_reported(fresh_demo):
    """IT-322: (a) 방금(10분 안) running 이 된 항목은 워커 틱이 복구하지 않는다(다른 워커가 처리 중일 수 있으므로) — 단 워커 기동 직후에는 즉시 복구 대상.
    (b) planned 기록이 있고 영상 제목이 이전도 새 제목도 아닌(다른 사람이 바꿈) 항목은 failed[result_unknown] 으로 남고 영상 제목을 건드리지 않는다.
    검증: NFR-W05, W-010, SEC-W17"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 2))
    worker_stop()
    try:
        bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
        assert a.execute(bid, 2).status_code == 202
        items = a.get(f"/api/v1/batches/{bid}").json()["items"]
        it = items[1]
        psql_app(
            "insert into changes (video_id, suggestion_id, batch_id, change_type, previous_title, new_title, backup_snippet, reason, approver, approved_at, plan_hash, result, mode, created_at) "
            f"select v.video_id, s.id, {bid}, 'apply', v.title, s.title, v.snippet, 'it', a.approver, a.approved_at, a.plan_hash, 'planned', 'demo', now() "
            f"from videos v join suggestions s on s.id = {it['suggestion_id']} join approvals a on a.suggestion_id = s.id where v.video_id = '{it['video_id']}'"
        )
        cid_ = psql_app(f"select id from changes where video_id='{it['video_id']}' and result='planned'")
        psql_app(f"update batch_items set status='running', change_id={cid_}, updated_at = now() - interval '1 minute' where id = {it['id']}")
        psql_app(f"update approvals set used_at = now() where suggestion_id = {it['suggestion_id']}")
        ib.mark_video_title(it["video_id"], "제3자가 바꾼 제목")
    finally:
        worker_start()
    b = wait_until(lambda: (lambda x: x if x["counts"]["running"] == 0 and x["counts"]["pending"] == 0 else None)(a.get(f"/api/v1/batches/{bid}").json()), 90, what="종료")
    by = {x["id"]: x for x in b["items"]}
    assert by[items[0]["id"]]["status"] == "success"
    assert by[it["id"]]["status"] == "failed" and by[it["id"]]["skip_reason"].startswith("[result_unknown]"), by[it["id"]]
    assert {v["video_id"]: v["title"] for v in a.videos()}[it["video_id"]] == "제3자가 바꾼 제목"


@pytest.mark.xfail(strict=True, reason="DEF-7B-002: 재시작 복구로 success 확정된 반영은 감사 로그에 batch.item.recovered(항목 번호·상태만)만 남고 change.apply(변경 ID·영상 ID·제안 ID)가 없다 — 추가 전용 감사 기록만으로는 어느 영상이 어떻게 바뀌었는지 복원할 수 없다(changes 표는 앱 계정이 수정 가능)")
def test_it_323_recovered_apply_is_traceable_in_append_only_audit(fresh_demo):
    """IT-323(결함 고정, DEF-7B-002): 워커가 갱신 직후(planned 기록 후, 검증 전) 죽어 재시작 복구가 success 로 확정한 반영도 정상 반영처럼 감사 로그에 변경 ID 와 영상 ID 가
    남는가. 현재는 batch.item.recovered 에 {status: success} 만 남는다. 검증: W-016, SEC-W06(감사 추적), NFR-W05"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 1))
    worker_stop()
    try:
        bid = a.make_batch([ap[0]["id"]]).json()["batch"]["id"]
        assert a.execute(bid, 1).status_code == 202
        it = a.get(f"/api/v1/batches/{bid}").json()["items"][0]
        psql_app(
            "insert into changes (video_id, suggestion_id, batch_id, change_type, previous_title, new_title, backup_snippet, reason, approver, approved_at, plan_hash, result, mode, created_at) "
            f"select v.video_id, s.id, {bid}, 'apply', v.title, s.title, v.snippet, 'it', a.approver, a.approved_at, a.plan_hash, 'planned', 'demo', now() "
            f"from videos v join suggestions s on s.id = {it['suggestion_id']} join approvals a on a.suggestion_id = s.id where v.video_id = '{it['video_id']}'"
        )
        cid_ = psql_app(f"select id from changes where video_id='{it['video_id']}' and result='planned'")
        psql_app(f"update batch_items set status='running', change_id={cid_}, updated_at = now() - interval '1 minute' where id = {it['id']}")
        psql_app(f"update approvals set used_at = now() where suggestion_id = {it['suggestion_id']}")
        psql_app(f"update videos set title = s.title, snippet = jsonb_set(snippet, '{{title}}', to_jsonb(s.title::text)) from suggestions s where s.id = {it['suggestion_id']} and videos.video_id = '{it['video_id']}'")
    finally:
        worker_start()
    b = a.wait_batch(bid, timeout=60)
    assert b["counts"]["success"] == 1
    items = a.get("/api/v1/audit", params={"page_size": 200}).json()["items"]
    blob = json.dumps([x for x in items if x["action"] in ("change.apply", "batch.item.recovered")], ensure_ascii=False)
    assert it["video_id"] in blob and any(x["target_type"] == "change" and x["target_id"] == cid_ for x in items if x["action"] in ("change.apply", "batch.item.recovered")), blob


# ─────────────────────────── 여러 워커 ───────────────────────────

@pytest.mark.slow
def test_it_330_three_workers_respect_daily_cap(fresh_demo):
    """IT-330: 워커 3개(정식 1 + 추가 2)가 동시에 같은 배치를 처리해도 하루 상한(3)을 넘기지 않고 영상당 반영 1건, 쿼터 이중 차감 없음.
    경합으로 오늘 몫을 넘긴 항목은 건너뛰지 않고 다음 날로 이월된다(DEF-VB-01). 검증: NFR-W03(동시 틱에서도 하루 상한 유지), S-W12"""
    a = fresh_demo
    set_cap(a, 3)
    ap = approve_many(a, usable_videos(a, 10))
    worker_stop()
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 10).status_code == 202
    ev = threading.Thread(target=lambda: time.sleep(1) or worker_start())
    ev.start()
    run_extra_workers(2, 22)
    ev.join()
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert b["counts"]["success"] == 3 and b["counts"]["failed"] == 0 and b["counts"]["skipped"] == 0, b["counts"]
    assert psql_app("select count(*) from changes where change_type='apply' and result='success'") == "3"
    assert psql_app("select coalesce(max(c),0) from (select count(*) c from changes group by video_id) t") == "1"
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == 3 * 52
    deferred = [x for x in a.get("/api/v1/audit", params={"page_size": 200}).json()["items"] if x["action"] == "batch.item.deferred"]
    print("deferred_events", len(deferred))
    assert psql_app("select count(*) from batch_items where status='pending' and scheduled_date is null") == "0"
    shift_days(1)                                   # 다음 날: 이월분 포함 3건 더, 그다음 날 3건, 마지막 1건
    wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 6, 90, what="둘째 날 3건")
    shift_days(1)
    wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 9, 90, what="셋째 날 3건")
    shift_days(1)
    done = a.wait_batch(bid, timeout=90)
    assert done["counts"]["success"] == 10 and done["counts"]["skipped"] == 0 and done["counts"]["failed"] == 0, done["counts"]
    assert ib.count_success_per_video_max() == "1"


@pytest.mark.slow
def test_it_331_overdue_items_beyond_cap_with_many_workers_are_deferred_not_skipped(fresh_demo):
    """IT-331: 하루 상한 3, 10건 배치에서 예약이 이틀 밀려(워커가 꺼져 있던 시늉) 오늘 도래분이 9건이 된 상태로 워커 7개가 동시에 시작해도 오늘은 3건만 반영되고
    (놓친 예약을 몰아서 실행하지 않음), 오늘 몫을 넘긴 시도는 건너뜀·실패가 아니라 다음 날로 이월(감사 batch.item.deferred, 예정일=내일)된다. 이후 날마다 3건씩 이어서 모두 한 번씩만 반영.
    검증: W-008(초과분 다음 날), NFR-W03, DEF-VB-01, DEC-042"""
    a = fresh_demo
    set_cap(a, 3)
    ap = approve_many(a, usable_videos(a, 10))
    worker_stop()
    bid = a.make_batch([s["id"] for s in ap]).json()["batch"]["id"]
    assert a.execute(bid, 10).status_code == 202
    shift_days(2)
    today = "(now() at time zone 'Asia/Seoul')::date"
    assert psql_app(f"select count(*) from batch_items where status='pending' and scheduled_date <= {today}") == "9"
    nxt = a.get("/api/v1/dashboard").json()["queue"]
    assert nxt["pending_items"] == 10 and nxt["next_run_date"] == psql_app(f"select {today}"), nxt      # 밀린 예약이 있어도 '다음 실행일'은 과거가 아니라 오늘
    ev = threading.Thread(target=lambda: time.sleep(0.5) or worker_start())
    ev.start()
    run_extra_workers(6, 25)
    ev.join()
    b = a.get(f"/api/v1/batches/{bid}").json()
    assert b["counts"]["success"] == 3 and b["counts"]["failed"] == 0 and b["counts"]["skipped"] == 0, b["counts"]
    assert ib.count_success_per_video_max() == "1"
    ev_def = [x for x in a.get("/api/v1/audit", params={"page_size": 200}).json()["items"] if x["action"] == "batch.item.deferred"]
    print("deferred_events", len(ev_def))
    assert ev_def, "7개 워커가 3건 몫을 두고 경쟁했는데 이월이 한 번도 일어나지 않음(시험이 경합을 만들지 못했거나 이월 로직 변경)"
    assert all(x["detail"]["code"] == "limit_daily" for x in ev_def)
    moved = int(psql_app(f"select count(*) from batch_items where status='pending' and scheduled_date = {today} + 1"))
    assert moved >= len(ev_def) - 0 or moved >= 1
    assert a.get("/api/v1/dashboard").json()["quota"]["used"] == 3 * 52
    for day in range(2, 6):
        shift_days(1)
        try:
            ib.wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= min(10, 3 * day), 60, what=f"{day}일째")
        except TimeoutError:
            break
        time.sleep(4)
    done = a.wait_batch(bid, timeout=60)
    assert done["counts"]["success"] == 10 and done["counts"]["skipped"] == 0 and done["counts"]["failed"] == 0, done["counts"]
    assert ib.count_success_per_video_max() == "1"


# ─────────────────────────── 재시작 뒤 보존 ───────────────────────────

@pytest.mark.slow
def test_it_340_data_session_and_approval_key_survive_restarts(fresh_demo):
    """IT-340: 반영 이력·승인 대기·세션·감사 체인·승인 서명 키가 여러 재시작 방식(네이티브: 정상 정지/시작, 전체 SIGKILL; 도커: restart, down→up, 재생성) 뒤에도
    그대로이고, 재시작 전에 받은 승인이 재시작 뒤에도 유효해 반영된다. 검증: NFR-W04, W-016, SEC-W17, D-07"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 4))
    b1 = a.make_batch([ap[0]["id"]]).json()["batch"]["id"]
    assert a.execute(b1, 1).status_code == 202
    a.wait_batch(b1)
    snap0 = psql_owner("select table_name from information_schema.tables where table_schema='public' order by 1")
    c0 = counts()
    key_sha = approval_key_sha()
    for i, (label, fn) in enumerate(ib.restart_cycles()):
        fn()
        wait_healthy(240)
        assert counts() == c0, (label, c0, counts())
        assert approval_key_sha() == key_sha, label
        r = a.get("/api/v1/auth/me")
        assert r.json()["authenticated"] is True, label           # 같은 쿠키가 그대로 유효(세션은 DB)
        assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True, label
        assert psql_app("select count(*) from batch_items where status='running'") == "0", label
    b2 = a.make_batch([ap[1]["id"]]).json()["batch"]["id"]            # 재시작 전(승인 시점)의 승인이 지금도 유효
    assert a.execute(b2, 1).status_code == 202
    assert a.wait_batch(b2)["counts"]["success"] == 1
    assert snap0 == psql_owner("select table_name from information_schema.tables where table_schema='public' order by 1")
