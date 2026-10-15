"""실제 수정 3조건·확인 문구·중복/동시 실행·한도 우회 시도 (가짜 구글, 실제 네트워크 차단)."""
import threading, uuid
from sqlalchemy import select
from tests.verify_m23.conftest import approve_via_api, do_execute, hdr, make_draft
from tests.verify_m23.test_vm_07_live_e2e import tick, prepare, queued
from ytweb.db.models import Change, Batch
from ytweb.domain.batches import run_due_items


def n_put(w): return len(w.fg.put_calls())

def test_not_allowed_video_never_writes(live):
    sid = approve_via_api(live.api, live.csrf, live.ids[1])
    r = make_draft(live.api, live.csrf, [sid]); assert r.status_code == 422
    for i in range(3): tick(live)
    assert live.fg.calls == [] or n_put(live) == 0 and not live.fg.put_calls()

def test_mixed_batch_only_allowed_goes_out(live):
    sids = prepare(live, 2)
    r = make_draft(live.api, live.csrf, sids); bid = r.json()["batch"]["id"]
    assert do_execute(live.api, live.csrf, bid, r.json()["precheck"]["confirm_text"]).status_code == 202
    for _ in range(3): tick(live)
    assert {c.body["id"] for c in live.fg.put_calls()} <= {live.ids[0]}

def test_switch_off_after_execute_no_put(live):
    sids = prepare(live, 1)
    r = make_draft(live.api, live.csrf, sids); bid = r.json()["batch"]["id"]
    ct = r.json()["precheck"]["confirm_text"]
    live.mp.delenv("YTWEB_LIVE_WRITE")
    ex = do_execute(live.api, live.csrf, bid, ct)
    print("switch-off execute", ex.status_code, ex.text[:200])
    for _ in range(3): tick(live)
    assert n_put(live) == 0

def test_switch_turned_off_between_queue_and_tick(live):
    bid, _ = queued(live)
    live.mp.setenv("YTWEB_LIVE_WRITE", "0")
    for _ in range(3): tick(live)
    assert n_put(live) == 0

def test_allowed_list_emptied_between_queue_and_tick(live):
    bid, _ = queued(live)
    live.mp.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", "")
    for _ in range(3): tick(live)
    assert n_put(live) == 0

def test_allowed_list_changed_to_other_video(live):
    bid, _ = queued(live)
    live.mp.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", live.ids[2])
    for _ in range(3): tick(live)
    assert n_put(live) == 0

def test_no_write_token_no_put(live, web_settings):
    sids = prepare(live, 1)
    r = make_draft(live.api, live.csrf, sids); bid = r.json()["batch"]["id"]
    ct = r.json()["precheck"]["confirm_text"]
    for f in web_settings.secrets_dir.glob("*write*"): f.unlink()
    print("token files left", [p.name for p in web_settings.secrets_dir.iterdir()])
    ex = do_execute(live.api, live.csrf, bid, ct); print("no-token execute", ex.status_code, ex.text[:200])
    for _ in range(3): tick(live)
    assert n_put(live) == 0

def test_read_only_token_cannot_write(live, web_settings):
    sids = prepare(live, 1)
    r = make_draft(live.api, live.csrf, sids); bid = r.json()["batch"]["id"]
    for f in web_settings.secrets_dir.glob("*write*"): f.write_text("{}")   # 깨진 토큰
    do_execute(live.api, live.csrf, bid, r.json()["precheck"]["confirm_text"])
    for _ in range(3): tick(live)
    assert n_put(live) == 0

CT = ["실행 1건", "실제 실행 1건 ", " 실제 실행 1건", "실제  실행 1건", "실제 실행 1 건", "실제 실행 １건", "실제 실행 2건", "실제실행1건", "", "실제 실행 1건\n", "실제 실행 1건​", "실제 실행 01건"
      , "Demo"]
def test_confirm_text_tamper(live):
    sids = prepare(live, 1)
    r = make_draft(live.api, live.csrf, sids); bid = r.json()["batch"]["id"]
    bad = []
    for t in CT:
        ex = do_execute(live.api, live.csrf, bid, t)
        if ex.status_code != 422: bad.append((t, ex.status_code))
    assert do_execute(live.api, live.csrf, bid, "실제 실행 1건").status_code == 202   # 정확한 문구만 통과(대조군)
    bad = [b for b in bad]
    assert not bad, bad
    assert n_put(live) == 0              # 변조 문구로는 0건, 대조군 큐잉만 됨(tick 전)

def test_double_execute_same_and_new_idem_key(live):
    bid, _ = queued(live)
    ct = "실제 실행 1건"
    codes = [do_execute(live.api, live.csrf, bid, ct).status_code for _ in range(3)]
    print("re-execute", codes)
    for _ in range(4): tick(live)
    assert n_put(live) == 1, n_put(live)

def test_concurrent_ticks_one_put(live):
    bid, _ = queued(live)
    ts = [threading.Thread(target=lambda: run_due_items(live.factory, live.clock(), live.env)) for _ in range(6)]
    [t.start() for t in ts]; [t.join(60) for t in ts]
    assert n_put(live) == 1, n_put(live)

def test_concurrent_execute_requests(live):
    sids = prepare(live, 1)
    r = make_draft(live.api, live.csrf, sids); bid = r.json()["batch"]["id"]
    res = []
    def go(): res.append(do_execute(live.api, live.csrf, bid, "실제 실행 1건").status_code)
    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]; [t.join(60) for t in ts]
    print("concurrent execute codes", res)
    for _ in range(4): tick(live)
    assert n_put(live) <= 1, n_put(live)

def test_two_batches_same_video(live):
    s1 = prepare(live, 1)
    r1 = make_draft(live.api, live.csrf, s1)
    r2 = make_draft(live.api, live.csrf, s1)
    print("2nd draft same suggestion", r2.status_code, r2.text[:200])
    ok1 = do_execute(live.api, live.csrf, r1.json()["batch"]["id"], "실제 실행 1건").status_code
    if r2.status_code == 201:
        print("exec2", do_execute(live.api, live.csrf, r2.json()["batch"]["id"], "실제 실행 1건").status_code)
    for _ in range(5): tick(live)
    assert n_put(live) <= 1, n_put(live)

def _approve_fresh(w, vid):
    r = w.api.post(f"/api/v1/videos/{vid}/suggestions", json={"count": 5}, headers=hdr(w.csrf))
    assert r.status_code == 201, r.text
    cand = [x for x in r.json() if x["validation_result"] == "pass" and x.get("status", "proposed") in ("candidate",)]
    assert cand, [(x.get("status"), x["validation_result"]) for x in r.json()]
    a = w.api.post(f"/api/v1/suggestions/{cand[0]['id']}/approve", json={"approver": "검수자"}, headers=hdr(w.csrf))
    assert a.status_code == 200, a.text
    return cand[0]["id"]

def test_repeat_changes_72h_and_3_times(live):
    outcomes = []
    for i in range(5):
        try:
            sid = _approve_fresh(live, live.ids[0])
            r = make_draft(live.api, live.csrf, [sid])
            if r.status_code != 201: outcomes.append(("draft", r.status_code, r.json().get("code"), r.json().get("detail", "")[:60])); continue
            ex = do_execute(live.api, live.csrf, r.json()["batch"]["id"], r.json()["precheck"]["confirm_text"])
            outcomes.append(("exec", ex.status_code, ex.json().get("code") if ex.status_code >= 400 else None, r.json()["precheck"].get("warnings", [])[1:2]))
            for _ in range(5): tick(live); live.clock.advance(seconds=20)
        except AssertionError as e:
            outcomes.append(("assert", str(e)[:100]))
        print("after round", i, "puts", n_put(live))
    print("outcomes", outcomes)
    assert n_put(live) <= 3, (outcomes, n_put(live))
