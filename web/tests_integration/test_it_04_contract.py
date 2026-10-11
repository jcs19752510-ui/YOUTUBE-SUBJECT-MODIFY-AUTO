"""IT 그룹 C — 프런트 ↔ 백엔드 계약: openapi.json 대조, 응답 스키마 적합성, API.md 오류 코드 표, 무작위 입력 강건성, W-FE 실서버 시험을 nginx 주소로.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from itlib import (
    REPO, Api, approve_many, approved_suggestion, dc, inside_api_python, psql_app, reset_demo_db, two_pass_suggestions, usable_videos,
)

HERE = Path(__file__).resolve().parent
OPENAPI = json.loads((REPO / "docs/yt/openapi.json").read_text(encoding="utf-8"))
HANGUL = re.compile(r"[가-힣]")


def _validator(schema: dict) -> Draft202012Validator:
    return Draft202012Validator({**schema, "components": OPENAPI["components"]})


def _resp_schema(path: str, method: str, status: str) -> dict | None:
    op = OPENAPI["paths"][path][method]
    r = op["responses"].get(status)
    if not r or "content" not in r:
        return None
    return r["content"].get("application/json", {}).get("schema")


def _check(path_tmpl: str, method: str, status: int, body, errors: list[str], label: str | None = None) -> None:
    sc = _resp_schema(path_tmpl, method, str(status))
    if sc is None or "$ref" not in sc and not sc.get("type"):
        return
    for e in _validator(sc).iter_errors(body):
        errors.append(f"{label or method.upper() + ' ' + path_tmpl} [{status}] {'/'.join(str(p) for p in e.absolute_path)}: {e.message[:140]}")


# ─────────────────────────── openapi.json 이 실제 앱과 같은가 ───────────────────────────

def _diff(a, b, path=""):
    if type(a) is not type(b):
        yield path, a, b
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                yield f"{path}/{k}", "<없음>", b[k]
            elif k not in b:
                yield f"{path}/{k}", a[k], "<없음>"
            else:
                yield from _diff(a[k], b[k], f"{path}/{k}")
    elif a != b:
        yield path, a, b


@pytest.mark.xfail(strict=True, reason="DEF-7-002: docs/yt/openapi.json 이 DEF-VA-005 수정(audit page 상한)을 반영하지 않아 오래됨 — 재생성하면 이 표시를 지운다")
def test_tc_it_400_openapi_json_in_repo_matches_running_app_schema():
    """TC-IT-400: 저장소의 docs/yt/openapi.json 이 실제 컨테이너 안 앱 객체가 만드는 스키마와 같다(경로·메서드·컴포넌트). 검증: EVT-W01~W31, API.md 9장"""
    script = "import json\nfrom ytweb.app import create_app\nprint('OPENAPI ' + json.dumps(create_app().openapi(), sort_keys=True))\n"
    p = inside_api_python(script)
    assert p.returncode == 0, p.stderr[-400:]
    live = json.loads([x for x in p.stdout.splitlines() if x.startswith("OPENAPI ")][-1][8:])
    repo = json.loads(json.dumps(OPENAPI, sort_keys=True))
    ops = lambda d: sorted(f"{m.upper()} {p}" for p, v in d["paths"].items() for m in v)  # noqa: E731
    assert ops(live) == ops(repo)
    assert len(ops(live)) == 31
    assert sorted(live["components"]["schemas"]) == sorted(repo["components"]["schemas"])
    d = list(_diff(live, repo))
    assert not d, "저장소 openapi.json 이 오래됨(앱 객체와 다름): " + " | ".join(f"{p}: 컨테이너={str(a)[:90]} 저장소={str(b)[:90]}" for p, a, b in d[:6])


# ─────────────────────────── 응답이 스키마에 맞는가 ───────────────────────────

def test_tc_it_401_live_responses_conform_to_openapi_schemas(fresh_demo):
    """TC-IT-401: 데모 전체 흐름에서 받은 실제 응답(nginx 경유) 본문이 openapi.json 의 응답 스키마를 만족한다(필수 필드·형식). 스키마 없는 응답(API.md 9장 3번)은
    제외하고 '검사하지 못한 엔드포인트'를 목록으로 남긴다. 검증: W4-3 계약 검증, EVT-W08~W28"""
    a = fresh_demo
    errs: list[str] = []
    checked: set[str] = set()

    def chk(tmpl: str, method: str, r, status: int | None = None):
        assert r.status_code == (status or r.status_code), (tmpl, r.status_code, r.text[:200])
        _check(tmpl, method, r.status_code, r.json(), errs)
        checked.add(f"{method.upper()} {tmpl}")

    chk("/api/v1/dashboard", "get", a.get("/api/v1/dashboard"), 200)
    vs = a.get("/api/v1/videos", params={"page_size": 20})
    chk("/api/v1/videos", "get", vs, 200)
    vid = [v for v in vs.json()["items"] if not v["excluded"]][0]["video_id"]
    chk("/api/v1/videos/{video_id}", "get", a.get(f"/api/v1/videos/{vid}"), 200)
    r = a.post("/api/v1/videos/sync"); chk("/api/v1/videos/sync", "post", r, 202)
    a.wait_job(r.json()["id"])
    chk("/api/v1/jobs/{job_id}", "get", a.get(f"/api/v1/jobs/{r.json()['id']}"), 200)
    r = a.post(f"/api/v1/videos/{vid}/suggestions", json={"count": 3}); chk("/api/v1/videos/{video_id}/suggestions", "post", r, 201)
    two = two_pass_suggestions(a, usable_videos(a, 30))
    ap = []
    for x in two:
        r = a.approve(x["id"]); chk("/api/v1/suggestions/{suggestion_id}/approve", "post", r, 200); ap.append(r.json())
    r = a.post("/api/v1/suggestions/generate", json={"video_ids": [vid], "count": 2}); chk("/api/v1/suggestions/generate", "post", r, 202)
    a.wait_job(r.json()["id"])
    chk("/api/v1/suggestions", "get", a.get("/api/v1/suggestions"), 200)
    sg = a.make_suggestion(usable_videos(a, 3)[2]["video_id"], 1)[0]
    chk("/api/v1/suggestions/{suggestion_id}", "patch", a.patch(f"/api/v1/suggestions/{sg['id']}", json={"title": sg["title"] + "!"}), 200)
    chk("/api/v1/suggestions/{suggestion_id}/reject", "post", a.post(f"/api/v1/suggestions/{sg['id']}/reject"), 200)
    r = a.make_batch([ap[0]["id"]]); chk("/api/v1/batches", "post", r, 201)
    bid = r.json()["batch"]["id"]
    chk("/api/v1/batches", "get", a.get("/api/v1/batches"), 200)
    chk("/api/v1/batches/{batch_id}", "get", a.get(f"/api/v1/batches/{bid}"), 200)
    r = a.execute(bid, 1); chk("/api/v1/batches/{batch_id}/execute", "post", r, 202)
    a.wait_batch(bid)
    other = approved_suggestion(a, usable_videos(a, 6)[5]["video_id"])
    b2 = a.make_batch([other["id"]]).json()["batch"]["id"]
    chk("/api/v1/batches/{batch_id}/cancel", "post", a.post(f"/api/v1/batches/{b2}/cancel"), 200)
    ch = a.get("/api/v1/changes"); chk("/api/v1/changes", "get", ch, 200)
    c0 = ch.json()["items"][0]
    r = a.post(f"/api/v1/changes/{c0['id']}/rollback", json={"typed_video_id": c0["video_id"], "approver": "계약"}, idem=True)
    chk("/api/v1/changes/{change_id}/rollback", "post", r, 201)
    chk("/api/v1/reports/changes", "get", a.get("/api/v1/reports/changes"), 200)
    chk("/api/v1/google/status", "get", a.get("/api/v1/google/status"), 200)
    assert errs == [], "\n".join(errs[:40])
    assert len(checked) >= 20, sorted(checked)
    # 스키마가 없어 검사할 수 없는 응답은 API.md 9장 3번에 기재된 것뿐이어야 한다
    no_schema = sorted(
        f"{m.upper()} {p}" for p, v in OPENAPI["paths"].items() for m, op in v.items()
        if not any(("content" in rr and "$ref" in json.dumps(rr["content"])) for s, rr in op["responses"].items() if s.startswith("2"))
    )
    allowed = {"GET /api/v1/auth/me", "POST /api/v1/auth/session", "DELETE /api/v1/auth/session", "GET /api/v1/settings", "PATCH /api/v1/settings", "GET /api/v1/audit",
               "GET /api/healthz", "GET /healthz", "GET /api/readyz", "GET /readyz", "GET /api/v1/reports/export.csv"}
    assert set(no_schema) <= allowed, set(no_schema) - allowed


# ─────────────────────────── 오류 코드 표(API.md 5~8장) ───────────────────────────

def test_tc_it_402_documented_error_codes_status_hint_and_format(fresh_demo):
    """TC-IT-402: API.md 에 적힌 오류 코드를 실제로 일으켜 상태 코드·`code` 가 문서와 같고, 모든 오류가 problem+json(type=urn:ytweb:problem:<code>, 한국어 title,
    비어 있지 않은 hint, 스택·내부 경로 없음)임을 nginx 경유로 확인한다. 검증: API.md 1-7, S-W09, DEF-VA-011"""
    a = fresh_demo
    vs = usable_videos(a, 6)
    s1 = a.make_suggestion(vs[0]["video_id"], 1)[0]
    ap = approved_suggestion(a, vs[1]["video_id"])
    rej = a.make_suggestion(vs[2]["video_id"], 1)[0]
    assert a.post(f"/api/v1/suggestions/{rej['id']}/reject").status_code == 200
    bid = a.make_batch([ap["id"]]).json()["batch"]["id"]
    done_s = approved_suggestion(a, vs[3]["video_id"])
    b_done = a.make_batch([done_s["id"]]).json()["batch"]["id"]
    assert a.execute(b_done, 1).status_code == 202
    a.wait_batch(b_done)                                   # done_s 는 이제 applied
    ex = [v for v in a.videos() if v["excluded"]][0]["video_id"]
    cases = [
        # (이름, 호출, 기대 상태, 기대 code)
        ("video_not_found", lambda: a.get("/api/v1/videos/demoVid9999"), 404, "video_not_found"),
        ("video_id 형식", lambda: a.get("/api/v1/videos/short"), 422, "validation_error"),
        ("video_excluded", lambda: a.post(f"/api/v1/videos/{ex}/suggestions", json={"count": 1}), 409, "video_excluded"),
        ("count 범위(스키마 단계)", lambda: a.post(f"/api/v1/videos/{vs[0]['video_id']}/suggestions", json={"count": 6}), 422, "validation_error"),
        ("suggestion_not_found(PATCH)", lambda: a.patch("/api/v1/suggestions/999999", json={"title": "가나다 라마바"}), 404, "suggestion_not_found"),
        ("suggestion_not_found(approve)", lambda: a.approve(999999), 404, "suggestion_not_found"),
        ("suggestion_not_found(reject)", lambda: a.post("/api/v1/suggestions/999999/reject"), 404, "suggestion_not_found"),
        ("approver 빈 문자열(스키마 단계)", lambda: a.post(f"/api/v1/suggestions/{s1['id']}/approve", json={"approver": ""}), 422, "validation_error"),
        ("approver_required(공백만)", lambda: a.post(f"/api/v1/suggestions/{s1['id']}/approve", json={"approver": "   "}), 422, "approver_required"),
        ("approver_invalid", lambda: a.post(f"/api/v1/suggestions/{s1['id']}/approve", json={"approver": "가\n나"}), 422, "approver_invalid"),
        ("suggestion_state(재승인)", lambda: a.approve(ap["id"]), 409, "suggestion_state"),
        ("suggestion_state(반려 뒤 승인)", lambda: a.approve(rej["id"]), 409, "suggestion_state"),
        ("title_empty", lambda: a.patch(f"/api/v1/suggestions/{s1['id']}", json={"title": "   "}), 422, "title_empty"),
        ("title_too_long", lambda: a.patch(f"/api/v1/suggestions/{s1['id']}", json={"title": "가" * 301}), 422, "title_too_long"),
        ("suggestion_state(반영된 제안 수정)", lambda: a.patch(f"/api/v1/suggestions/{done_s['id']}", json={"title": done_s["title"] + "?"}), 409, "suggestion_state"),
        ("batch_not_draft(이미 실행)", lambda: a.execute(b_done, 1), 409, "batch_not_draft"),
        ("batch_not_cancellable(끝난 배치)", lambda: a.post(f"/api/v1/batches/{b_done}/cancel"), 409, "batch_not_cancellable"),
        ("batch_not_found", lambda: a.get("/api/v1/batches/999999"), 404, "batch_not_found"),
        ("batch_empty", lambda: a.make_batch([s1["id"]]), 422, "batch_empty"),
        ("batch_too_large", lambda: a.make_batch(list(range(1000, 1051))), 422, "batch_too_large"),
        ("duplicate_suggestion", lambda: a.make_batch([ap["id"], ap["id"]]), 422, "duplicate_suggestion"),
        ("idempotency_key_required", lambda: a.post("/api/v1/batches", json={"suggestion_ids": [1]}), 400, "idempotency_key_required"),
        ("confirm_text_mismatch", lambda: a.execute(bid, 9), 422, "confirm_text_mismatch"),
        ("batch_not_found(execute)", lambda: a.execute(999999, 1), 404, "batch_not_found"),
        ("batch_not_found(cancel)", lambda: a.post("/api/v1/batches/999999/cancel"), 404, "batch_not_found"),
        ("job_not_found", lambda: a.get(f"/api/v1/jobs/{uuid.uuid4()}"), 404, "job_not_found"),
        ("job id 형식", lambda: a.get("/api/v1/jobs/not-a-uuid"), 422, "validation_error"),
        ("change_not_found", lambda: a.post("/api/v1/changes/999999/rollback", json={"typed_video_id": "demoVid0001", "approver": "가"}, idem=True), 404, "change_not_found"),
        ("setting_not_allowed", lambda: a.patch("/api/v1/settings", json={"enable_live": True}), 400, "setting_not_allowed"),
        ("settings validation", lambda: a.patch("/api/v1/settings", json={"daily_apply_cap": 99}), 422, "validation_error"),
        ("reports video_not_found", lambda: a.get("/api/v1/reports/changes", params={"video_id": "demoVid9999"}), 404, "video_not_found"),
        ("changes result 필터 오류", lambda: a.get("/api/v1/changes", params={"result": "weird"}), 422, "validation_error"),
        ("page_size 200 초과", lambda: a.get("/api/v1/videos", params={"page_size": 201}), 422, "validation_error"),
        ("unknown field", lambda: a.post("/api/v1/suggestions/generate", json={"video_ids": ["demoVid0001"], "evil": 1}), 422, "validation_error"),
        ("no handler/404", lambda: a.get("/api/v1/nope"), 404, None),
    ]
    bad = []
    for name, fn, st, code in cases:
        r = fn()
        ok = r.status_code == st
        body = {}
        try:
            body = r.json()
        except Exception:
            ok = False
        if ok and code is not None:
            ok = body.get("code") == code
        if ok:
            ok = (r.headers["content-type"].startswith("application/problem+json") and str(body.get("type", "")).startswith("urn:ytweb:problem:")
                  and bool(HANGUL.search(body.get("title", ""))) and bool(body.get("hint", "").strip()) and body.get("status") == st)
        txt = json.dumps(body, ensure_ascii=False)
        if "Traceback" in txt or "/app/" in txt or "sqlalchemy" in txt.lower() or "File \"" in txt:
            ok = False
        if not ok:
            bad.append((name, r.status_code, txt[:220]))
    assert not bad, "\n".join(map(str, bad))


def test_tc_it_403_malformed_inputs_never_5xx_and_never_leak(fresh_demo):
    """TC-IT-403: 깨진 JSON·잘못된 타입·거대한 정수·널 문자·제어/방향 문자·중첩 폭탄을 변경 엔드포인트에 보내도 5xx 가 나지 않고 problem+json 4xx 만 돌려준다
    (nginx → 백엔드 → DB 전체 경로). 검증: S-W13, S-W09, S-W05"""
    a = fresh_demo
    vid = usable_videos(a, 1)[0]["video_id"]
    s = a.make_suggestion(vid, 1)[0]
    payloads = [
        b"", b"{", b"null", b"[]", b'"x"', b"{" * 5000, b'{"a":' * 2000 + b"1" + b"}" * 2000, b"\xff\xfe", b'{"count": 1e999}', b'{"count": 99999999999999999999999999}',
        b'{"title": "\\u0000abc"}', b'{"title": "\\u202eabc"}', json.dumps({"title": "가" * 100000}).encode(), b'{"video_ids": [null]}', b'{"video_ids": "demoVid0001"}',
        b'{"approver": {"a": 1}}', b'{"suggestion_ids": [1e30]}', b'{"suggestion_ids": ["1; drop table videos"]}', b'{"confirm_text": 5}',
    ]
    targets = [
        ("POST", f"/api/v1/videos/{vid}/suggestions"), ("POST", "/api/v1/suggestions/generate"), ("PATCH", f"/api/v1/suggestions/{s['id']}"),
        ("POST", f"/api/v1/suggestions/{s['id']}/approve"), ("POST", "/api/v1/batches"), ("POST", "/api/v1/batches/1/execute"),
        ("POST", "/api/v1/changes/1/rollback"), ("PATCH", "/api/v1/settings"),
    ]
    bad = []
    n = 0
    for m, path in targets:
        for body in payloads:
            h = {"Content-Type": "application/json", "Origin": "http://127.0.0.1:8080", "X-CSRF-Token": a.csrf, "Idempotency-Key": "it-403-" + uuid.uuid4().hex[:16]}
            a._pace()
            r = a.c.request(m, path, content=body, headers=h)
            n += 1
            txt = r.text
            if r.status_code >= 500 or ("Traceback" in txt) or ("File \"" in txt) or ("/app/" in txt):
                bad.append((m, path, body[:40], r.status_code, txt[:160]))
            elif r.status_code >= 400 and not r.headers.get("content-type", "").startswith(("application/problem+json", "text/html")):
                bad.append((m, path, body[:40], r.status_code, "content-type " + r.headers.get("content-type", "")))
            if n % 100 == 0:
                time.sleep(1.0)   # 백엔드 쓰기 한도(분당 120)를 넘기지 않도록 한 번씩 쉰다
    assert not bad, bad[:8]
    assert psql_app("select count(*) from videos") == "200"      # 주입 문자열이 표를 건드리지 않았다
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True


# ─────────────────────────── W-FE 실서버 시험을 nginx 주소로 ───────────────────────────

@pytest.mark.slow
def test_tc_it_410_frontend_live_contract_suite_against_nginx():
    """TC-IT-410: W-FE 의 실서버 계약 시험(verify/live.verify.test.ts, 21건)을 nginx 주소 http://127.0.0.1:8080(18080 으로 바이트 중계)로, 변경 직후 대기 0ms
    (VF_LIVE_SETTLE_MS=0, DEF-VF-B01 경합 재현 조건)로 돌려 전부 통과한다. 검증: W-FE 계약, DEF-VF-B01, DEF-VF-005"""
    fe = os.environ.get("IT_FE_DIR")
    if not fe or not (Path(fe) / "node_modules").is_dir():
        pytest.skip("IT_FE_DIR(npm ci 한 프런트 사본)가 없음 — 미수행으로 센다")
    reset_demo_db()
    relay = subprocess.Popen([sys.executable, str(HERE / "tools" / "relay.py"), "8080", os.environ.get("IT_PORT", "18080")])
    try:
        time.sleep(1.0)
        env = {**os.environ, "VF_LIVE_API": "http://127.0.0.1:8080", "VF_LIVE_SETTLE_MS": "0"}
        p = subprocess.run(["npx", "vitest", "run", "verify/live.verify.test.ts", "--reporter=default"], cwd=fe, env=env, capture_output=True, text=True, timeout=600)
        out = p.stdout + p.stderr
    finally:
        relay.terminate()
        relay.wait(timeout=10)
    (Path(os.environ.get("IT_LOGDIR", "/tmp")) / "fe_live.log").write_text(out, encoding="utf-8") if os.environ.get("IT_LOGDIR") else None
    assert p.returncode == 0, out[-3000:]
    m = re.search(r"Tests\s+(\d+) passed", out)
    assert m and int(m.group(1)) == 21 and "failed" not in out.split("Tests")[-1].split("\n")[0], out[-1500:]


@pytest.mark.xfail(strict=True, reason="DEF-7-003: API.md 5장·부록은 count 범위 위반을 422 count_invalid 로 적었으나 실제는 스키마 단계의 validation_error(count_invalid 는 HTTP 로 도달 불가)")
def test_tc_it_404_documented_count_invalid_code_is_reachable(fresh_demo):
    """TC-IT-404(결함 고정): 문서화된 `count_invalid`(1~5 아님) 가 실제로 나오는가. 현재는 `validation_error`."""
    a = fresh_demo
    v = usable_videos(a, 1)[0]["video_id"]
    r = a.post(f"/api/v1/videos/{v}/suggestions", json={"count": 6})
    assert r.status_code == 422 and r.json()["code"] == "count_invalid"
