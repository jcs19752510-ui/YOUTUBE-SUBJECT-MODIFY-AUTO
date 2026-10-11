"""IT 그룹 C — 계약(IT-400~): openapi.json·API.md 와 실제 응답의 차이(필드·상태 코드·오류 코드·사유 코드), 모든 오류의 한국어 hint, 시각·날짜 표기,
페이지네이션·정렬, 감사 로그 해시 체인(변조 탐지), 마이그레이션 0001→0002 업그레이드 후 데이터 보존, 검사 순서.

네이티브 스택과 도커 스택에서 같은 코드가 돈다(마이그레이션 시험은 native_only).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jsonschema import Draft202012Validator

import itlib_b as ib
from itlib_b import (  # noqa: F401  (fresh_demo 는 픽스처)
    ACTIONS_SEEN, NATIVE, OBSERVED, RELAXED, REPO, Api, apply_via_batch, approve_many, approved_suggestion, clone_api, fresh_demo, inside_python, psql_app, psql_owner,
    reset_demo_db, rollback, run_threads, set_cap, two_pass_suggestions, usable_videos, wait_until, worker_start, worker_stop,
)

HERE = Path(__file__).resolve().parent
OPENAPI = json.loads((REPO / "docs/yt/openapi.json").read_text(encoding="utf-8"))
API_MD = (REPO / "docs/yt/API.md").read_text(encoding="utf-8")
HANGUL = re.compile(r"[가-힣]")
native_only = pytest.mark.skipif(not NATIVE, reason="DB 서버·프로세스를 직접 제어하는 시험(도커 스택은 A 트랙)")
KST, PT = ZoneInfo("Asia/Seoul"), ZoneInfo("America/Los_Angeles")


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


@pytest.mark.xfail(strict=True, reason="DEF-7-003(알려진 결함, 이전 세션 발견): docs/yt/openapi.json 이 DEF-VA-005 수정(audit page/page_size 상한)을 반영하지 않아 오래됨 — 재생성하면 이 표시를 지운다")
def test_it_400_openapi_json_in_repo_matches_running_app_schema():
    """IT-400: 저장소의 docs/yt/openapi.json 이 실제 앱 객체가 만드는 스키마와 같다(경로·메서드·컴포넌트·모든 필드). 검증: EVT-W01~W31, API.md 9장
    (알려진 결함 DEF-7-003: 현재 audit 의 page/page_size 상한 두 줄만 다르다. 파일을 재생성하면 XPASS(strict 실패)로 알려 주므로 그때 표시를 지운다.)"""
    script = "import json\nfrom ytweb.app import create_app\nprint('OPENAPI ' + json.dumps(create_app().openapi(), sort_keys=True))\n"
    p = inside_python(script)
    assert p.returncode == 0, p.stderr[-400:]
    live = json.loads([x for x in p.stdout.splitlines() if x.startswith("OPENAPI ")][-1][8:])
    repo = json.loads(json.dumps(OPENAPI, sort_keys=True))
    ops = lambda d: sorted(f"{m.upper()} {p}" for p, v in d["paths"].items() for m in v)  # noqa: E731
    assert ops(live) == ops(repo)
    assert len(ops(live)) == 31
    assert sorted(live["components"]["schemas"]) == sorted(repo["components"]["schemas"])
    d = list(_diff(live, repo))
    assert not d, "저장소 openapi.json 이 오래됨(앱 객체와 다름): " + " | ".join(f"{p}: 앱={str(a)[:90]} 저장소={str(b)[:90]}" for p, a, b in d[:6])


# ─────────────────────────── 응답이 스키마에 맞는가 ───────────────────────────

def test_it_401_live_responses_conform_to_openapi_schemas(fresh_demo):
    """IT-401: 데모 전체 흐름에서 받은 실제 응답 본문이 openapi.json 의 응답 스키마를 만족한다(필수 필드·형식). 스키마 없는 응답(API.md 9장 3번)은
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
    no_schema = sorted(
        f"{m.upper()} {p}" for p, v in OPENAPI["paths"].items() for m, op in v.items()
        if not any(("content" in rr and "$ref" in json.dumps(rr["content"])) for s, rr in op["responses"].items() if s.startswith("2"))
    )
    allowed = {"GET /api/v1/auth/me", "POST /api/v1/auth/session", "DELETE /api/v1/auth/session", "GET /api/v1/settings", "PATCH /api/v1/settings", "GET /api/v1/audit",
               "GET /api/healthz", "GET /healthz", "GET /api/readyz", "GET /readyz", "GET /api/v1/reports/export.csv"}
    assert set(no_schema) <= allowed, set(no_schema) - allowed


# ─────────────────────────── 31개 동작 전부·쿼리 파라미터 열거값 ───────────────────────────

def _enums(schema: dict) -> list:
    out: list = []
    if "enum" in schema:
        out += schema["enum"]
    for k in ("anyOf", "oneOf"):
        for sub in schema.get(k, []):
            out += _enums(sub)
    return out


def test_it_420_every_operation_is_served_with_documented_success_status_and_enum_params(fresh_demo):
    """IT-420: openapi.json 의 31개 동작을 전부 실제로 호출해 문서의 성공 상태 코드가 나오는지 본다(동작 목록이 바뀌면 이 시험이 실패한다). 그리고 쿼리 파라미터의
    열거값(sort·order·status·result)은 전부 200 이고 열거 밖 값은 422 validation_error. 검증: EVT-W01~W31, API.md 5~8장"""
    a = fresh_demo
    set_cap(a, 20)
    vs = usable_videos(a, 8)
    vid = vs[0]["video_id"]
    s_ap = approved_suggestion(a, vid)
    ch = apply_via_batch(a, s_ap["id"])
    s2 = approved_suggestion(a, vs[1]["video_id"])
    b2 = a.make_batch([s2["id"]]).json()["batch"]["id"]
    sg = a.make_suggestion(vs[2]["video_id"], 1)[0]
    job = a.post("/api/v1/videos/sync").json()["id"]
    a.wait_job(job)
    c_out = Api()                                  # 로그아웃 시험용 별도 세션
    assert c_out.login().status_code == 200
    calls = {
        "GET /api/v1/audit": lambda: a.get("/api/v1/audit"),
        "GET /api/v1/auth/me": lambda: a.get("/api/v1/auth/me"),
        "POST /api/v1/auth/session": lambda: Api().login(),
        "DELETE /api/v1/auth/session": lambda: c_out.delete("/api/v1/auth/session"),
        "POST /api/v1/batches": lambda: a.make_batch([approved_suggestion(a, vs[3]["video_id"])["id"]]),
        "GET /api/v1/batches": lambda: a.get("/api/v1/batches"),
        "GET /api/v1/batches/{batch_id}": lambda: a.get(f"/api/v1/batches/{b2}"),
        "POST /api/v1/batches/{batch_id}/execute": lambda: a.execute(b2, 1),
        "POST /api/v1/batches/{batch_id}/cancel": lambda: a.post(f"/api/v1/batches/{a.make_batch([approved_suggestion(a, vs[4]['video_id'])['id']]).json()['batch']['id']}/cancel"),
        "GET /api/v1/changes": lambda: a.get("/api/v1/changes"),
        "POST /api/v1/changes/{change_id}/rollback": lambda: rollback(a, ch),
        "GET /api/v1/dashboard": lambda: a.get("/api/v1/dashboard"),
        "GET /api/v1/google/status": lambda: a.get("/api/v1/google/status"),
        "GET /api/healthz": lambda: a.c.get("/api/healthz"),
        "GET /healthz": lambda: a.c.get("/healthz"),
        "GET /api/readyz": lambda: a.c.get("/api/readyz"),
        "GET /readyz": lambda: a.c.get("/readyz"),
        "GET /api/v1/jobs/{job_id}": lambda: a.get(f"/api/v1/jobs/{job}"),
        "GET /api/v1/reports/changes": lambda: a.get("/api/v1/reports/changes"),
        "GET /api/v1/reports/export.csv": lambda: a.get("/api/v1/reports/export.csv"),
        "GET /api/v1/settings": lambda: a.get("/api/v1/settings"),
        "PATCH /api/v1/settings": lambda: a.patch("/api/v1/settings", json={"tone": ["친근한"]}),
        "POST /api/v1/suggestions/generate": lambda: a.post("/api/v1/suggestions/generate", json={"video_ids": [vs[5]["video_id"]], "count": 1}),
        "GET /api/v1/suggestions": lambda: a.get("/api/v1/suggestions"),
        "PATCH /api/v1/suggestions/{suggestion_id}": lambda: a.patch(f"/api/v1/suggestions/{sg['id']}", json={"title": sg["title"] + " 편"}),
        "POST /api/v1/suggestions/{suggestion_id}/approve": lambda: a.approve(sg["id"]),
        "POST /api/v1/suggestions/{suggestion_id}/reject": lambda: a.post(f"/api/v1/suggestions/{sg['id']}/reject"),
        "GET /api/v1/videos": lambda: a.get("/api/v1/videos"),
        "POST /api/v1/videos/sync": lambda: a.post("/api/v1/videos/sync"),
        "GET /api/v1/videos/{video_id}": lambda: a.get(f"/api/v1/videos/{vid}"),
        "POST /api/v1/videos/{video_id}/suggestions": lambda: a.post(f"/api/v1/videos/{vs[6]['video_id']}/suggestions", json={"count": 1}),
    }
    doc_ops = {f"{m.upper()} {p}": op for p, v in OPENAPI["paths"].items() for m, op in v.items()}
    assert set(calls) == set(doc_ops), (set(calls) ^ set(doc_ops))
    bad = []
    for key, fn in calls.items():
        r = fn()
        want = [int(s) for s in doc_ops[key]["responses"] if s.startswith("2")][0]
        if key in ("GET /healthz", "GET /readyz"):      # 백엔드 라우트는 문서대로 있으나 nginx 가 밖으로는 닫는다(DEF-7-006, W-FIX-INF) → 404
            want = 404
        if r.status_code != want:
            bad.append((key, want, r.status_code, r.text[:160]))
    # 그 사이 ‘수정’한 제안은 반려했으므로 마지막 호출의 상태 충돌은 순서 문제: (approve 이후 reject)
    assert not bad, bad
    # 열거값
    enum_bad = []
    for key, op in doc_ops.items():
        if not key.startswith("GET "):
            continue
        for prm in op.get("parameters", []):
            if prm["in"] != "query":
                continue
            vals = _enums(prm["schema"])
            path = key.split(" ", 1)[1]
            for v in vals:
                r = a.get(path, params={prm["name"]: v, "page_size": 5})
                if r.status_code != 200:
                    enum_bad.append((key, prm["name"], v, r.status_code))
            if vals:
                r = a.get(path, params={prm["name"]: "__nope__"})
                if r.status_code != 422 or r.json().get("code") != "validation_error":
                    enum_bad.append((key, prm["name"], "__nope__", r.status_code))
    assert not enum_bad, enum_bad


# ─────────────────────────── 오류 코드 표(API.md 5~8장) ───────────────────────────

def test_it_402_documented_error_codes_status_hint_and_format(fresh_demo):
    """IT-402: API.md 에 적힌 오류 코드를 실제로 일으켜 상태 코드·`code` 가 문서와 같고, 모든 오류가 problem+json(type=urn:ytweb:problem:<code>, 한국어 title,
    비어 있지 않은 hint, 스택·내부 경로 없음)임을 확인한다. 검증: API.md 1-7, S-W09, DEF-VA-011"""
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
        ("approver 41자", lambda: a.post(f"/api/v1/suggestions/{s1['id']}/approve", json={"approver": "가" * 41}), 422, "approver_invalid"),
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
        ("idempotency_key_invalid", lambda: a.post("/api/v1/batches", json={"suggestion_ids": [1]}, idem="short"), 400, "idempotency_key_invalid"),
        ("confirm_text_mismatch", lambda: a.execute(bid, 9), 422, "confirm_text_mismatch"),
        ("batch_not_found(execute)", lambda: a.execute(999999, 1), 404, "batch_not_found"),
        ("batch_not_found(cancel)", lambda: a.post("/api/v1/batches/999999/cancel"), 404, "batch_not_found"),
        ("job_not_found", lambda: a.get(f"/api/v1/jobs/{uuid.uuid4()}"), 404, "job_not_found"),
        ("job id 형식", lambda: a.get("/api/v1/jobs/not-a-uuid"), 422, "validation_error"),
        ("change_not_found", lambda: a.post("/api/v1/changes/999999/rollback", json={"typed_video_id": "demoVid0001", "approver": "가"}, idem=True), 404, "change_not_found"),
        ("setting_not_allowed", lambda: a.patch("/api/v1/settings", json={"enable_live": True}), 400, "setting_not_allowed"),
        ("settings validation", lambda: a.patch("/api/v1/settings", json={"daily_apply_cap": 99}), 422, "validation_error"),
        ("pin_not_set", lambda: a.patch("/api/v1/settings", json={"pin": {"action": "clear"}}), 409, "pin_not_set"),
        ("reports video_not_found", lambda: a.get("/api/v1/reports/changes", params={"video_id": "demoVid9999"}), 404, "video_not_found"),
        ("changes result 필터 오류", lambda: a.get("/api/v1/changes", params={"result": "weird"}), 422, "validation_error"),
        ("page_size 200 초과", lambda: a.get("/api/v1/videos", params={"page_size": 201}), 422, "validation_error"),
        ("unknown field", lambda: a.post("/api/v1/suggestions/generate", json={"video_ids": ["demoVid0001"], "evil": 1}), 422, "validation_error"),
        ("no handler/404", lambda: a.get("/api/v1/nope"), 404, "not_found"),
        ("405", lambda: a.c.request("PUT", "/api/v1/batches", headers=a._h(True), json={}), 405, "method_not_allowed"),
        ("session_required", lambda: Api().get("/api/v1/dashboard"), 401, "session_required"),
        ("csrf_invalid", lambda: a.post("/api/v1/videos/sync", headers={"X-CSRF-Token": "x" * 40}), 403, "csrf_invalid"),
        ("origin_not_allowed", lambda: a.post("/api/v1/videos/sync", headers={"Origin": "http://evil.example"}), 403, "origin_not_allowed"),
        ("cross_site_request", lambda: a.post("/api/v1/videos/sync", headers={"Sec-Fetch-Site": "cross-site"}), 403, "cross_site_request"),
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


def test_it_403_malformed_inputs_never_5xx_and_never_leak(fresh_demo):
    """IT-403: 깨진 JSON·잘못된 타입·거대한 정수·널 문자·제어/방향 문자·중첩 폭탄을 변경 엔드포인트에 보내도 5xx 가 나지 않고 problem+json 4xx 만 돌려준다
    (프록시 → 백엔드 → DB 전체 경로). 검증: S-W13, S-W09, S-W05"""
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
            h = {"Content-Type": "application/json", "Origin": ib.ORIGIN_OK, "X-CSRF-Token": a.csrf, "Idempotency-Key": "it-403-" + uuid.uuid4().hex[:16]}
            a._pace()
            r = a.c.request(m, path, content=body, headers=h)
            n += 1
            txt = r.text
            if r.status_code >= 500 or ("Traceback" in txt) or ("File \"" in txt) or ("/app/" in txt):
                bad.append((m, path, body[:40], r.status_code, txt[:160]))
            elif r.status_code >= 400 and not r.headers.get("content-type", "").startswith(("application/problem+json", "text/html")):
                bad.append((m, path, body[:40], r.status_code, "content-type " + r.headers.get("content-type", "")))
            if not RELAXED:
                time.sleep(0.55)   # 백엔드 쓰기 한도(분당 120)를 넘기지 않도록
    assert not bad, bad[:8]
    assert psql_app("select count(*) from videos") == "200"      # 주입 문자열이 표를 건드리지 않았다
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True


@pytest.mark.xfail(strict=True, reason="DEF-7-004: API.md 5장·부록은 count 범위 위반을 422 count_invalid 로 적었으나 실제는 스키마 단계의 validation_error(count_invalid 는 HTTP 로 도달 불가)")
def test_it_404_documented_count_invalid_code_is_reachable(fresh_demo):
    """IT-404(결함 고정): 문서화된 `count_invalid`(1~5 아님) 가 실제로 나오는가. 현재는 `validation_error`."""
    a = fresh_demo
    v = usable_videos(a, 1)[0]["video_id"]
    r = a.post(f"/api/v1/videos/{v}/suggestions", json={"count": 6})
    assert r.status_code == 422 and r.json()["code"] == "count_invalid"


# ─────────────────────────── 검사 순서(API.md 1-1) ───────────────────────────

def test_it_430_documented_check_order_origin_session_csrf_validation_idempotency_business(fresh_demo):
    """IT-430: API.md 1-1 의 검사 순서(Host → 크기 → 속도 → 출처 → 세션 → CSRF → 본문 검증 → 멱등성 → 업무 규칙)를 서로 겹치는 오류 두 개씩으로 확인한다.
    출처가 세션보다 먼저라 허용되지 않은 출처에는 세션 유무를 알리지 않는다. 검증: API.md 1-1, SEC-W03/04"""
    a = fresh_demo
    anon = Api()                                             # 세션 없음
    h_bad_origin = {"Origin": "http://evil.example"}
    # 출처 vs 세션: 세션이 없어도 출처 오류가 먼저
    r = anon.c.post("/api/v1/videos/sync", headers=h_bad_origin)
    assert r.status_code == 403 and r.json()["code"] == "origin_not_allowed"
    r = anon.c.post("/api/v1/videos/sync", headers={"Origin": ib.ORIGIN_OK})
    assert r.status_code == 401 and r.json()["code"] == "session_required"          # 출처가 맞으면 그다음 세션
    # 세션 vs CSRF: 세션이 맞고 CSRF 가 틀리면 403 csrf_invalid, 본문이 잘못돼도 CSRF 가 먼저
    r = a.c.post("/api/v1/batches", headers={"Origin": ib.ORIGIN_OK, "X-CSRF-Token": "bad" * 10, "Idempotency-Key": "it-430-order-0001"}, json={"suggestion_ids": "x"})
    assert r.status_code == 403 and r.json()["code"] == "csrf_invalid"
    # CSRF 통과 후: 본문 검증(422) 이 멱등성 키 검사(400)보다 먼저
    r = a.post("/api/v1/batches", json={"suggestion_ids": "x"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error"
    r = a.post("/api/v1/batches", json={"suggestion_ids": [1]})
    assert r.status_code == 400 and r.json()["code"] == "idempotency_key_required"
    # 멱등성(400/422) 이 업무 규칙(404 제안 없음 → batch_empty)보다 먼저
    r = a.post("/api/v1/batches", json={"suggestion_ids": [987654]}, idem="short")
    assert r.status_code == 400 and r.json()["code"] == "idempotency_key_invalid"
    r = a.post("/api/v1/batches", json={"suggestion_ids": [987654]}, idem=True)
    assert r.status_code == 422 and r.json()["code"] == "batch_empty"
    # 업무 오류로 끝난 키는 지워져 같은 키로 다시 시도할 수 있다(API.md 1-6)
    k = "it-430-retry-key-001"
    r1 = a.post("/api/v1/batches", json={"suggestion_ids": [987654]}, idem=k)
    s = approved_suggestion(a, usable_videos(a, 1)[0]["video_id"])
    r2 = a.post("/api/v1/batches", json={"suggestion_ids": [987654]}, idem=k)
    assert r1.status_code == r2.status_code == 422 and r2.json()["code"] == "batch_empty"          # '처리 중' 이나 '키 재사용' 이 아니다
    assert psql_app(f"select count(*) from idempotency_keys where key='{k}'") == "0"
    r3 = a.post("/api/v1/batches", json={"suggestion_ids": [s["id"]]}, idem=k)
    assert r3.status_code == 201                                                                    # 같은 키 + 다른 본문도 이전 실패 뒤에는 새 요청으로 처리


# ─────────────────────────── 응답 필드 집합(스키마가 없는 응답, API.md 9장 3번) ───────────────────────────

def test_it_433_unschemaed_responses_have_documented_fields(fresh_demo):
    """IT-433: openapi.json 에 응답 스키마가 없는 응답(auth/me·auth/session·settings·audit·healthz·readyz·google/status·dashboard)의 필드가 API.md 4·8장과 같다.
    필드 추가는 v1 에서 허용되므로 '문서에 있는 필드가 모두 있고 타입이 맞는가'를 본다. 검증: API.md 3·4·7·8장"""
    a = fresh_demo
    me = a.get("/api/v1/auth/me").json()
    assert set(me) >= {"authenticated", "pin_required", "csrf_token"} and me["authenticated"] is True and isinstance(me["csrf_token"], str)
    anon = Api()
    m2 = anon.get("/api/v1/auth/me").json()
    assert m2 == {"authenticated": False, "pin_required": False, "csrf_token": None}
    c = Api()
    r = c.login()
    assert r.status_code == 200 and set(r.json()) == {"csrf_token"} and "ytw_session" in r.headers.get("set-cookie", "")
    ck = r.headers["set-cookie"].lower()
    assert "httponly" in ck and "samesite=strict" in ck and "path=/api" in ck
    st = a.get("/api/v1/settings").json()
    assert set(st) >= {"daily_apply_cap", "suggestions_per_video", "tone", "pin_enabled", "mode", "read_only"}
    assert set(st["read_only"]) >= {"enable_live", "live_allowlist", "note"} and st["read_only"]["enable_live"] is False and st["mode"] == "demo"
    au = a.get("/api/v1/audit").json()
    assert set(au) >= {"items", "total", "page", "page_size", "chain_ok"} and au["chain_ok"] is True
    assert set(au["items"][0]) >= {"id", "ts", "actor", "action", "target_type", "target_id", "detail", "prev_hash", "hash"}
    assert re.fullmatch(r"[0-9a-f]{64}", au["items"][0]["hash"]) and re.fullmatch(r"[0-9a-f]{64}", au["items"][0]["prev_hash"])
    d = a.get("/api/v1/dashboard").json()
    assert set(d) >= {"mode", "live_enabled", "google", "counts", "today", "quota", "active_job", "queue"}
    assert set(d["counts"]) >= {"videos", "excluded", "suggested", "approved", "queued", "applied"}
    assert set(d["quota"]) >= {"used", "limit", "remaining", "pt_date"} and d["quota"]["limit"] == 6000
    assert set(d["queue"]) >= {"pending_items", "next_run_date"} and set(d["today"]) >= {"applied", "cap"}
    g = a.get("/api/v1/google/status").json()
    assert g == {"mode": "demo", "connected": False, "message": g["message"]} and "시연용" in g["message"]
    for path in ("/api/healthz",):      # 루트 /healthz·/readyz 는 nginx 가 404 로 닫는다 → DEF-7-006 (IT-436)
        r = a.c.get(path)
        assert r.status_code == 200 and r.json() == {"status": "ok"}
    for path in ("/api/readyz",):
        r = a.c.get(path)
        assert r.status_code == 200 and r.json() == {"status": "ok", "db": "ok", "mode": "demo"}
    # 로그아웃: 204, 본문 없음, 같은 쿠키는 이후 401
    r = c.delete("/api/v1/auth/session")
    assert r.status_code == 204 and r.content == b""
    assert c.get("/api/v1/dashboard").status_code == 401


# ─────────────────────────── 시각·날짜 표기 ───────────────────────────

_UTC_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$")


def _walk_ts(obj, path, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "detail":      # 감사 로그의 detail 은 사건별 자유 내용(예: 승인 만료 시각을 Z 표기로 적음) — 엔드포인트 시각 필드가 아니다
                continue
            if isinstance(v, str) and (k.endswith("_at") or k in ("ts", "next_allowed_at")) and v:
                out.append((f"{path}.{k}", v))
            _walk_ts(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_ts(v, path, out)


def test_it_424_timestamps_are_utc_dates_are_kst_or_pt_and_consistent(fresh_demo):
    """IT-424: (a) 모든 시각 필드는 UTC(`Z` 또는 `+00:00`)이고 +09:00·시간대 없는 값이 없다 (b) 같은 엔드포인트 안에서는 표기가 하나로 일관 (c) 날짜 필드는
    scheduled_date/schedule[].date/next_run_date = KST 날짜, quota.pt_date = 태평양 날짜 (d) 승인 유효 시간은 정확히 24시간. 검증: API.md 1-4, W6장"""
    a = fresh_demo
    set_cap(a, 2)
    t_before = datetime.now(timezone.utc)
    ap = approve_many(a, usable_videos(a, 3))
    b = a.make_batch([s["id"] for s in ap])
    pre = b.json()["precheck"]
    bid = b.json()["batch"]["id"]
    worker_stop()
    try:
        ex = a.execute(bid, 3)
        assert ex.status_code == 202
        job_id = ex.json()["job"]["id"]
        endpoints = {
            "suggestions": a.get("/api/v1/suggestions").json(), "batches/id": a.get(f"/api/v1/batches/{bid}").json(), "batches": a.get("/api/v1/batches").json(),
            "audit": a.get("/api/v1/audit").json(), "dashboard": a.get("/api/v1/dashboard").json(),
            "videos/id": a.get(f"/api/v1/videos/{ap[0]['video_id']}").json(),
        }
        dash = endpoints["dashboard"]
        kst_today_ref = [datetime.now(KST).date()]
    finally:
        worker_start()
    ib.wait_until(lambda: a.get(f"/api/v1/batches/{bid}").json()["counts"]["success"] >= 2, 60, what="2건 반영")
    endpoints["changes"] = a.get("/api/v1/changes").json()
    endpoints["jobs"] = a.get(f"/api/v1/jobs/{job_id}").json()
    endpoints["batches/id(after)"] = a.get(f"/api/v1/batches/{bid}").json()
    endpoints["POST /batches"], endpoints["POST execute"] = b.json(), ex.json()
    rbr = rollback(a, endpoints["changes"]["items"][0])
    assert rbr.status_code == 201
    endpoints["POST rollback"] = rbr.json()
    forms: dict[str, set[str]] = {}
    for name, body in endpoints.items():
        out: list = []
        _walk_ts(body, name, out)
        for p, v in out:
            assert _UTC_TS.match(v), f"{p}={v}: UTC 표기가 아님"
            forms.setdefault(name, set()).add("Z" if v.endswith("Z") else "+00:00")
    print("timestamp forms per endpoint:", {k: sorted(v) for k, v in forms.items()})
    mixed = {k: v for k, v in forms.items() if len(v) > 1}
    assert not mixed, f"한 엔드포인트 안에 두 표기가 섞여 있음: {mixed}"
    # API.md 1-4 / 편차 DV-W06: 조회(GET)는 `Z`, 멱등성 처리 응답(배치 생성·실행·롤백)과 감사 ts 는 `+00:00`. 표기가 바뀌면(통일되면) 문서를 고쳐야 하므로 지금 모습을 고정한다.
    got = {k: sorted(v)[0] for k, v in forms.items()}
    want = {"suggestions": "Z", "batches/id": "Z", "batches": "Z", "audit": "+00:00", "videos/id": "Z", "changes": "Z", "batches/id(after)": "Z",
            "jobs": None, "POST /batches": "+00:00", "POST execute": "+00:00", "POST rollback": "+00:00"}
    assert {k: v for k, v in got.items()} == {k: v for k, v in want.items() if v is not None}, (got, want)
    # (c) 날짜
    assert [x["count"] for x in pre["schedule"]] == [2, 1]
    today_kst = {kst_today_ref[0], datetime.now(KST).date()}
    first = date.fromisoformat(pre["schedule"][0]["date"])
    assert first in today_kst, (first, today_kst)
    assert date.fromisoformat(pre["schedule"][1]["date"]) == first + timedelta(days=1)
    items = endpoints["batches/id"]["items"]
    assert sorted({i["scheduled_date"] for i in items}) == [pre["schedule"][0]["date"], pre["schedule"][1]["date"]]
    assert dash["queue"]["next_run_date"] in {first.isoformat(), (first + timedelta(days=1)).isoformat()}
    assert date.fromisoformat(dash["quota"]["pt_date"]) in {datetime.now(PT).date(), (datetime.now(PT) - timedelta(minutes=2)).date()}
    # (d) 승인 24시간
    approved_items = [s for s in endpoints["suggestions"]["items"] if s["approval"]]
    assert len(approved_items) >= 3
    for s in approved_items:
        ap_ = s["approval"]
        d = datetime.fromisoformat(ap_["expires_at"].replace("Z", "+00:00")) - datetime.fromisoformat(ap_["approved_at"].replace("Z", "+00:00"))
        assert d == timedelta(hours=24), d
        assert datetime.fromisoformat(ap_["approved_at"].replace("Z", "+00:00")) >= t_before - timedelta(seconds=1)


# ─────────────────────────── 페이지네이션·정렬 ───────────────────────────

def test_it_425_pagination_and_sorting_are_complete_stable_and_documented(fresh_demo):
    """IT-425: 영상 목록의 모든 정렬 키 x 방향에서 작은 페이지(13)로 끝까지 넘겨도 항목이 빠지거나 겹치지 않고(동률 안정성), 값이 있는 행은 정렬 방향대로,
    null 은 방향과 무관하게 맨 뒤. 목록 전반의 규약: 마지막 페이지 너머는 200+빈 목록, page=0·page_size=0·201 은 422, 최신순(id 내림차순), total 일정, audit page 상한.
    검증: API.md 1-5, EVT-W09/14/19/24/28"""
    a = fresh_demo
    set_cap(a, 20)
    vs = usable_videos(a, 24)
    r = a.post("/api/v1/suggestions/generate", json={"video_ids": [v["video_id"] for v in vs], "count": 3})
    a.wait_job(r.json()["id"])
    ap = []
    for v in vs[:7]:
        ap.append(approved_suggestion(a, v["video_id"]))
    for s in ap[:5]:
        apply_via_batch(a, s["id"])
    all_ids = sorted(v["video_id"] for v in a.videos())
    assert len(all_ids) == 200
    keys = ["title", "views", "duration_sec", "last_change_at", "video_id", "suggestion_count", "workflow_status"]
    problems = []
    for key in keys:
        for order in ("asc", "desc"):
            seen: list[dict] = []
            total0 = None
            for page in range(1, 40):
                d = a.get("/api/v1/videos", params={"sort": key, "order": order, "page": page, "page_size": 13}).json()
                total0 = total0 if total0 is not None else d["total"]
                assert d["total"] == total0 == 200 and d["page"] == page and d["page_size"] == 13
                seen += d["items"]
                if len(d["items"]) < 13:
                    break
            ids = [x["video_id"] for x in seen]
            if sorted(ids) != all_ids:
                problems.append((key, order, "빠지거나 겹침", len(ids), len(set(ids))))
                continue
            vals = [x[key] for x in seen]
            nn = [v for v in vals if v is not None]
            if vals[: len(nn)] != nn:
                problems.append((key, order, "null 이 맨 뒤가 아님"))
            wf_order = ["none", "suggested", "approved", "queued", "applied", "rolled_back"]
            ordered = sorted(nn, key=(wf_order.index if key == "workflow_status" else None), reverse=(order == "desc"))
            if key not in ("title",) and nn != ordered:
                problems.append((key, order, "정렬 방향 위반", nn[:5]))
            if key == "title" and nn != ordered:
                problems.append((key, order, "제목 정렬이 코드포인트 순서와 다름(콜레이션)", nn[:3]))
    assert not problems, problems
    # 목록 공통 규약
    for path in ("/api/v1/videos", "/api/v1/suggestions", "/api/v1/changes", "/api/v1/batches", "/api/v1/audit"):
        far = a.get(path, params={"page": 9999, "page_size": 50})
        assert far.status_code == 200 and far.json()["items"] == [] and far.json()["total"] > 0, path
        assert a.get(path, params={"page": 0}).status_code == 422
        assert a.get(path, params={"page_size": 0}).status_code == 422
        r201 = a.get(path, params={"page_size": 201})
        assert r201.status_code == 422 and r201.json()["code"] == "validation_error", path
        assert a.get(path, params={"page_size": 200}).status_code == 200
    for path in ("/api/v1/suggestions", "/api/v1/changes", "/api/v1/batches", "/api/v1/audit"):
        d = a.get(path, params={"page_size": 200}).json()
        ids = [x["id"] for x in d["items"]]
        assert ids == sorted(ids, reverse=True) and len(ids) == len(set(ids)), path
        half = a.get(path, params={"page_size": 3, "page": 2}).json()
        assert [x["id"] for x in half["items"]] == ids[3:6], path
    assert a.get("/api/v1/audit", params={"page": 1_000_001}).status_code == 422
    # 필터 결과의 total 이 필터를 반영
    for status in ("candidate", "approved", "applied", "blocked"):
        d = a.get("/api/v1/suggestions", params={"status": status, "page_size": 200}).json()
        assert d["total"] == len(d["items"]) and all(x["status"] == status for x in d["items"]), status


# ─────────────────────────── 감사 로그 해시 체인 ───────────────────────────

def test_it_426_audit_chain_detects_tampering_and_app_cannot_modify(fresh_demo):
    """IT-426: 감사 로그를 DB 에서 직접 바꾸면(내용 수정·중간 행 삭제·prev_hash 수정) chain_ok 가 false 가 되고 복원하면 true. 꼬리 삭제는 탐지되지 않는다(문서화된 한계).
    앱 계정은 audit_log 를 UPDATE/DELETE 할 수 없다(권한). 20개 동시 기록 후에도 체인이 갈라지지 않는다. 검증: SEC-W06, API.md 7장, D-07"""
    a = fresh_demo
    ap = approve_many(a, usable_videos(a, 2))
    apply_via_batch(a, ap[0]["id"])
    chain = lambda: a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"]  # noqa: E731
    assert chain() is True
    n = int(psql_app("select count(*) from audit_log"))
    mid = int(psql_app(f"select id from audit_log order by id offset {n // 2} limit 1"))
    # 1) 내용 수정
    orig = psql_owner(f"select detail::text from audit_log where id={mid}")
    psql_owner(f"update audit_log set detail = detail || '{{\"x\": 1}}'::jsonb where id={mid}")
    assert chain() is False
    psql_owner(f"update audit_log set detail = '{orig}'::jsonb where id={mid}")
    assert chain() is True
    # 2) prev_hash 수정
    oph = psql_owner(f"select prev_hash from audit_log where id={mid}")
    psql_owner(f"update audit_log set prev_hash = '{'f' * 64}' where id={mid}")
    assert chain() is False
    psql_owner(f"update audit_log set prev_hash = '{oph}' where id={mid}")
    assert chain() is True
    # 3) 중간 행 삭제 → 복원(원래 행을 그대로 다시 넣는다)
    row = psql_owner(f"select row_to_json(t)::text from (select * from audit_log where id={mid}) t")
    psql_owner(f"delete from audit_log where id={mid}")
    assert chain() is False
    psql_owner("insert into audit_log select * from json_populate_record(null::audit_log, '" + row.replace("'", "''") + "')")
    assert chain() is True
    # 4) 꼬리 삭제는 탐지 못 함(문서화된 한계) — 마지막 행을 지웠다 되돌린다
    last = int(psql_app("select max(id) from audit_log"))
    lrow = psql_owner(f"select row_to_json(t)::text from (select * from audit_log where id={last}) t")
    psql_owner(f"delete from audit_log where id={last}")
    tail_detected = chain() is False
    psql_owner("insert into audit_log select * from json_populate_record(null::audit_log, '" + lrow.replace("'", "''") + "')")
    assert tail_detected is False, "꼬리 삭제가 탐지됨 — API.md 7장/DESIGN W9장의 '탐지 못 한다' 서술을 갱신해야 함"
    assert chain() is True
    # 5) 앱 계정 권한
    for stmt in ("update audit_log set actor='x'", "delete from audit_log", "truncate audit_log"):
        with pytest.raises(Exception) as ei:
            psql_app(stmt)
        assert "permission denied" in str(ei.value).lower() or "권한" in str(ei.value) or "denied" in str(ei.value).lower(), (stmt, str(ei.value)[:200])
    # 6) 동시 기록
    base = a.get("/api/v1/audit", params={"page_size": 1}).json()["total"]

    def go(i):
        c = clone_api(a)
        r = c.patch("/api/v1/settings", json={"suggestions_per_video": 1 + i % 5})
        c.close()
        return r.status_code
    rounds, width = (6, 30) if RELAXED else (2, 20)
    for _ in range(rounds):          # (설정 변경은 같은 설정 행의 잠금으로 이미 줄을 서므로 감사 직렬화를 시험하지 못한다 — 아래 승인·로그인 경합이 본체)
        res = run_threads(width, go)
        assert all(x == 200 for x in res), res
    # 서로 다른 행을 건드리는 동시 쓰기: 서로 다른 제안 40개를 동시에 승인(제안 행 잠금이 서로 겹치지 않음) → 감사 기록이 동시에 이어 붙는다
    j = a.wait_job(a.post("/api/v1/suggestions/generate", json={"video_ids": [v["video_id"] for v in usable_videos(a, 60)[20:60]], "count": 1}).json()["id"])
    assert j["status"] == "succeeded"
    cands = [s for s in a.get("/api/v1/suggestions", params={"status": "candidate", "page_size": 200}).json()["items"] if s["validation_result"] != "block" and not s["strict"]]
    assert len(cands) >= 30, len(cands)
    for k in range(0, 30, 10 if RELAXED else 5):
        chunk = cands[k:k + (10 if RELAXED else 5)]
        res = run_threads(len(chunk), lambda i, chunk=chunk: (lambda c: (c.approve(chunk[i]["id"], f"동시{i}").status_code, c.close()))(clone_api(a))[0])
        assert all(x == 200 for x in res), res
        assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True, "동시 승인 중 감사 체인이 갈라졌다"
    if RELAXED:                                                    # 세션 발급 동시 30건
        res = run_threads(30, lambda i: Api(throttle=0, retry429=False).login().status_code)
        assert all(x == 200 for x in res), res
        assert a.login().status_code == 200                       # 세션은 최대 20개라 방금 30개가 이 클라이언트의 세션을 밀어냈다 — 다시 로그인
    d = a.get("/api/v1/audit", params={"page_size": 200}).json()
    assert d["chain_ok"] is True and d["total"] > base + rounds * width + 30
    hashes = [x["hash"] for x in d["items"]]
    assert len(hashes) == len(set(hashes))
    prev = {x["hash"]: x["prev_hash"] for x in d["items"]}
    assert sum(1 for x in d["items"] if x["prev_hash"] not in {y["hash"] for y in d["items"]}) <= 1      # 목록 맨 끝(가장 오래된 행) 하나만 목록 밖을 가리킨다
    assert len(set(prev.values())) == len(prev), "두 행이 같은 prev_hash 를 가리킴 — 체인이 갈라짐"


# ─────────────────────────── CSV ───────────────────────────

def test_it_428_csv_export_columns_and_filter_match_documented_contract(fresh_demo):
    """IT-428: CSV 내보내기가 API.md 7장의 열 목록·인코딩(UTF-8 BOM)·파일 이름·캐시 금지와 같고, video_id 필터는 그 영상만 담으며, 변경이 없는 영상도 행이 있다(변경 없음).
    검증: API.md EVT-W27, W-013"""
    a = fresh_demo
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 2))
    ch = apply_via_batch(a, ap[0]["id"])
    r = a.get("/api/v1/reports/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].replace(" ", "").lower() == "text/csv;charset=utf-8"
    assert r.headers["content-disposition"] == 'attachment; filename="ytitle-report.csv"' and "no-store" in r.headers["cache-control"]
    assert r.content.startswith(b"\xef\xbb\xbf")
    doc_cols = re.search(r"열: `([^`]+)`", API_MD).group(1).split(",")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert rows[0] == doc_cols, (rows[0], doc_cols)
    blank = rows.index([])                                     # 데이터 행 뒤에 빈 줄, 그 아래에 주의 문구(notes)
    data, notes = rows[1:blank], [x[0] for x in rows[blank + 1:]]
    assert all(len(x) == len(doc_cols) for x in data) and len(data) == 1, data      # 변경이 있는 영상만 행이 된다(전체 보기)
    assert any("원인" in n for n in notes) and any("가상" in n for n in notes) and len(notes) == 4, notes
    row = dict(zip(doc_cols, data[0]))
    assert row["video_id"] == ch["video_id"] and row["new_title"] == ch["new_title"] and row["previous_title"] == ch["previous_title"] and row["status"] in ("insufficient", "ok")
    one = list(csv.reader(io.StringIO(a.get("/api/v1/reports/export.csv", params={"video_id": ch["video_id"]}).content.decode("utf-8-sig"))))
    assert one[0] == doc_cols and one[1][0] == ch["video_id"] and one[2] == []
    none = list(csv.reader(io.StringIO(a.get("/api/v1/reports/export.csv", params={"video_id": ap[1]["video_id"]}).content.decode("utf-8-sig"))))
    assert dict(zip(doc_cols, none[1]))["status"] == "no_change"           # 변경 없는 영상은 영상 ID 를 지정했을 때만 '변경 없음' 행
    assert a.get("/api/v1/reports/export.csv", params={"video_id": "demoVid9999"}).status_code == 404


# ─────────────────────────── 응답 헤더 규약 ───────────────────────────

def test_it_432_response_headers_request_id_no_store_and_unique(fresh_demo):
    """IT-432: 모든 응답(성공·오류·CSV)에 X-Request-Id(32자 16진수, 요청마다 다름), /api 응답에 Cache-Control: no-store 와 CSP default-src 'none'. 중복 헤더 없음.
    (nginx 단계의 보안 헤더 한 벌은 A 트랙이 본다.) 검증: API.md 1-2"""
    a = fresh_demo
    seen = set()
    for path in ("/api/v1/dashboard", "/api/v1/nope", "/api/v1/videos/demoVid9999", "/api/v1/reports/export.csv", "/api/healthz", "/api/readyz"):
        r = a.get(path)
        rid = r.headers.get("x-request-id", "")
        assert re.fullmatch(r"[0-9a-f]{32}", rid) and rid not in seen, (path, rid)
        seen.add(rid)
        assert r.headers.get("cache-control", "").lower().count("no-store") == 1 or "no-store" in r.headers.get("cache-control", ""), path
        assert r.headers.get("content-security-policy", "").startswith("default-src 'none'"), path     # DEF-7-007 수정: nginx 가 /api 에 'none' 정책을 붙인다 (IT-437)
    r = a.c.post("/api/v1/videos/sync", headers={"Origin": "http://evil.example"})
    assert re.fullmatch(r"[0-9a-f]{32}", r.headers.get("x-request-id", ""))


def test_it_436_root_healthz_and_readyz_are_closed_at_nginx_and_api_paths_serve_json():
    """IT-436(DEF-7-006 수정 확인): 브라우저 포트의 루트 /healthz·/readyz 는 SPA HTML 200 이 아니라 404(text/plain)이고,
    상태 확인은 /api/healthz·/api/readyz 가 JSON 으로 준다. (API.md 는 루트 경로도 열린다고 적혀 있어 문서 정정이 필요 — 11단계 대조 항목.)"""
    import httpx
    from itlib import BASE, HOST_OK
    for path in ("/healthz", "/readyz"):
        r = httpx.get(BASE + path, headers={"Host": HOST_OK}, timeout=10)
        assert r.status_code == 404 and r.headers["content-type"].startswith("text/plain") and "<html" not in r.text.lower(), (path, r.status_code)
    for path, want in (("/api/healthz", {"status": "ok"}), ("/api/readyz", {"status": "ok", "db": "ok", "mode": "demo"})):
        r = httpx.get(BASE + path, headers={"Host": HOST_OK}, timeout=10)
        assert r.status_code == 200 and r.headers["content-type"].startswith("application/json") and r.json() == want, (path, r.headers["content-type"])


def test_it_437_api_responses_carry_documented_csp_default_src_none(fresh_demo):
    """IT-437(DEF-7-007 수정 확인): /api 응답의 CSP 가 문서대로 default-src 'none' 이고 한 벌만 나간다."""
    r = fresh_demo.get("/api/v1/dashboard")
    assert r.headers.get_list("content-security-policy") == ["default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"]


# ─────────────────────────── 마이그레이션 0001 → 0002 ───────────────────────────

_TABLES = ["videos", "suggestions", "approvals", "batches", "batch_items", "changes", "ai_runs", "metrics_snapshots", "quota_usage", "audit_log", "settings_kv", "jobs", "idempotency_keys"]


def _table_digest() -> dict[str, str]:
    return {t: psql_owner(f"select count(*) || '|' || coalesce(md5(string_agg(x::text, '~' order by x::text)), '') from {t} x") for t in _TABLES}


@native_only
@pytest.mark.destructive
def test_it_427_migration_0001_to_0002_keeps_data_and_tightens_app_role():
    """IT-427: 0001 스키마에서 실제 업무(동기화·제안·승인·배치·반영·롤백·PIN·감사)를 쌓은 뒤 0002 로 올려도 모든 표의 내용(행 수·내용 해시)과 감사 체인이 그대로이고,
    앱 계정은 alembic_version 을 읽기만 할 수 있게 된다(업그레이드 전에는 변경 가능). 올린 뒤에도 같은 DB 로 업무가 계속 된다. 같은 리비전 재실행은 아무 일도 하지 않는다.
    0002 → 0001 내리기도 되고 권한이 복원된다. 검증: DEF-VA-012/VI-002, NFR-W04, D-07"""
    nat = ib.nat
    nat.proc_stop("worker"); nat.proc_stop("api")
    nat.reset_schema()
    m = nat.migrate("0001")
    assert m.returncode == 0, m.stderr[-500:]
    assert psql_owner("select version_num from alembic_version") == "0001"
    can = lambda p: psql_owner(f"select has_table_privilege('ytweb_app','alembic_version','{p}')")  # noqa: E731
    assert can("UPDATE") == "t" and can("DELETE") == "t", "0001 에서는 앱 계정이 버전표를 바꿀 수 있어야 비교가 의미 있음"
    nat.api_start(RELAXED); nat.worker_start(); nat.wait_api()
    a = Api()
    assert a.login().status_code == 200
    a.sync_demo()
    set_cap(a, 20)
    ap = approve_many(a, usable_videos(a, 5))
    b1 = a.make_batch([s["id"] for s in ap[:3]]).json()["batch"]["id"]
    a.execute(b1, 3)
    a.wait_batch(b1)
    ch = a.get("/api/v1/changes").json()["items"][0]
    assert rollback(a, ch).status_code == 201
    b2 = a.make_batch([ap[3]["id"]]).json()["batch"]["id"]
    a.post(f"/api/v1/batches/{b2}/cancel")
    assert a.patch("/api/v1/settings", json={"pin": {"action": "set", "new_pin": "271828"}}).status_code == 200
    a.patch("/api/v1/settings", json={"pin": {"action": "clear", "current_pin": "271828"}})
    assert a.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    nat.proc_stop("worker"); nat.proc_stop("api")                 # 업그레이드 동안 정지(운영 절차와 같다: migrate 가 먼저 돈다)
    before = _table_digest()
    assert sum(int(v.split("|")[0]) for v in before.values()) > 300
    m2 = nat.migrate("head")
    assert m2.returncode == 0, m2.stderr[-500:]
    assert psql_owner("select version_num from alembic_version") == "0002"
    assert _table_digest() == before, "업그레이드가 데이터를 바꿨다"
    assert can("SELECT") == "t" and can("UPDATE") == "f" and can("DELETE") == "f" and can("INSERT") == "f"
    m3 = nat.migrate("head")
    assert m3.returncode == 0 and _table_digest() == before and psql_owner("select version_num from alembic_version") == "0002"
    nat.api_start(RELAXED); nat.worker_start(); nat.wait_api()
    a2 = Api()
    assert a2.login().status_code == 200
    assert a2.get("/api/v1/audit", params={"page_size": 1}).json()["chain_ok"] is True
    assert {c["id"] for c in a2.get("/api/v1/changes").json()["items"]} >= {ch["id"]}
    left = a2.make_batch([ap[4]["id"]])
    assert left.status_code == 201
    assert a2.execute(left.json()["batch"]["id"], 1).status_code == 202
    assert a2.wait_batch(left.json()["batch"]["id"])["counts"]["success"] == 1
    # 내리기/다시 올리기
    nat.proc_stop("worker"); nat.proc_stop("api")
    d = nat.migrate("0001", down=True)
    assert d.returncode == 0, d.stderr[-400:]
    assert can("UPDATE") == "t"
    u = nat.migrate("head")
    assert u.returncode == 0 and can("UPDATE") == "f"
    nat.api_start(RELAXED); nat.worker_start(); nat.wait_api()
    a.close(); a2.close()


# ─────────────────────────── 사유 코드·감사 action 표 ───────────────────────────

_SKIP_REACHABLE = {"approval_missing", "approval_tampered", "approval_used", "approval_expired", "plan_mismatch", "suggestion_state", "suggestion_blocked", "video_excluded",
                   "pending_change_exists", "limit_interval", "limit_count"}                       # IT-112 가 실제로 일으킨다
_SKIP_UNREACHABLE = {
    "title_invalid": "새 제목은 plan_hash 에 묶여 있어 DB 를 바꾸면 plan_mismatch 가 먼저 나온다(설정 파일의 제목 규격을 승인 뒤에 바꿔야만 도달)",
    "same_as_current": "영상 제목을 바꾸면 plan_hash 가 달라져 plan_mismatch 가 먼저 나온다",
    "limit_impressions": "데모 모드는 재변경 최소 노출수를 0 으로 완화(DEC-042 D1)",
    "limit_daily": "하루 상한만 걸린 경우는 이월(deferred)이고, 다른 한도와 함께 걸리면 그 한도 코드(limit_interval/limit_count)가 먼저 나온다 — 코드가 건너뜀 사유로는 도달하지 않음",
    "quota_exhausted": "워커 틱이 쿼터 52단위 미만이면 항목을 집지 않고 멈춘다(quota_exhausted 는 stopped_by 로만 나옴); 선예약 실패는 다른 소비자와의 경합에서만",
    "title_changed": "모의 유튜브는 앱 DB 의 videos 행과 같은 곳이라 '재조회한 제목 != 저장 제목'은 경합에서만",
    "video_changed": "같은 이유(재조회 snippet 과 저장 snippet 이 항상 같음)",
    "batch_not_active": "스케줄러가 활성 배치의 항목만 집으므로 취소 경합에서만",
    "suggestion_missing": "제안 행은 외래키로 보호되어 삭제되지 않음",
    "cancelled": "취소는 항목 상태(cancelled)로 기록되고 건너뜀 사유 코드로는 skip_reason 에 '[cancelled]' 로 남음 — IT-105 가 확인",
}


def test_it_422_skip_reason_codes_documented_vs_reachable():
    """IT-422: API.md 6장 '건너뜀' 사유 코드 21종이 (a) 이 시험이 일으키는 11종 (b) 도달 불가 사유가 있는 10종으로 빠짐없이 나뉜다 — 문서에 코드가 더해지거나 빠지면
    실패한다. 도달 불가 판단은 코드 읽기와 IT-112 시도에 근거. 검증: API.md 6장, W-010"""
    m = re.search(r"\| 건너뜀\(`skipped`, 아무것도 바꾸지 않음\) \| (.+?) \|", API_MD)
    doc = set(re.findall(r"`([a-z_]+)`", m.group(1)))
    assert len(doc) == 21, doc
    assert doc == _SKIP_REACHABLE | set(_SKIP_UNREACHABLE), (doc ^ (_SKIP_REACHABLE | set(_SKIP_UNREACHABLE)))
    fail = re.search(r"\| 실패\(`failed`, 시도했으나 실패\) \| (.+?) \|", API_MD)
    assert {"read_failed", "video_not_found", "snippet_invalid", "body_invalid", "update_failed", "result_unknown", "internal_error", "verify_failed", "interrupted", "success"} == set(re.findall(r"`([a-z_]+)`", fail.group(1)))


# ─────────────────────────── 변조가 있어야 나오는 오류 코드 ───────────────────────────

@native_only
def test_it_434_tamper_only_error_codes_and_approval_key_handling(fresh_demo):
    """IT-434: API.md 에 적힌 오류 가운데 DB·비밀 파일 변조가 있어야 나오는 것을 직접 일으킨다: video_inconsistent(저장된 영상 정보 불일치), same_as_current(현재 제목과 같음),
    approval_key_unreadable(승인 서명 키 파일이 깨짐 — 500, 키를 덮어쓰지 않음, 기존 승인은 변조로 판정). 키 파일이 없어지면 새 키가 만들어지고 이전 승인은 모두 무효가 된다
    (안전 방향). 승인 ↔ 배치 ↔ 비밀 폴더 경계. 검증: EVT-W16, DEF-VB-03, SEC-W17"""
    nat = ib.nat
    a = fresh_demo
    set_cap(a, 20)
    vs = usable_videos(a, 6)
    # video_inconsistent
    s1 = a.make_suggestion(vs[0]["video_id"], 3)
    cand = [x for x in s1 if x["validation_result"] != "block" and not x["strict"]][0]
    psql_owner(f"update videos set snippet = jsonb_set(snippet,'{{title}}','\"다른 제목\"'::jsonb) where video_id='{vs[0]['video_id']}'")
    r = a.approve(cand["id"])
    assert r.status_code == 409 and r.json()["code"] == "video_inconsistent", r.text[:300]
    # same_as_current: 제안 제목을 현재 영상 제목과 똑같이 고친 뒤 승인
    s2 = a.make_suggestion(vs[1]["video_id"], 3)
    pick = [x for x in s2 if x["validation_result"] != "block" and not x["strict"]][0]
    cur = {v["video_id"]: v["title"] for v in a.videos()}[vs[1]["video_id"]]
    e = a.patch(f"/api/v1/suggestions/{pick['id']}", json={"title": cur})
    if e.status_code == 200 and e.json()["status"] == "candidate":
        r = a.approve(pick["id"])
        assert r.status_code == 409 and r.json()["code"] in ("same_as_current", "suggestion_blocked"), r.text[:300]
    else:
        assert e.status_code in (200, 409) and e.json().get("status") in ("blocked", None) or e.json().get("code") == "duplicate_suggestion", e.text[:300]
    # 승인 서명 키
    ok1 = approved_suggestion(a, vs[2]["video_id"])
    ok2_sugs = [x for x in a.make_suggestion(vs[3]["video_id"], 3) if x["validation_result"] != "block" and not x["strict"]]
    keyfile = nat.APP_SECRETS / "approval_hmac.key"
    good = keyfile.read_bytes()
    try:
        keyfile.write_bytes(b"not-a-hex-key")                              # 깨진 키
        r = a.approve(ok2_sugs[0]["id"])
        assert r.status_code == 500 and r.json()["code"] == "approval_key_unreadable", r.text[:300]
        assert keyfile.read_bytes() == b"not-a-hex-key", "깨진 키를 새 키로 덮어썼다"
        r = a.make_batch([ok1["id"]])                                       # 기존 승인은 믿을 수 없다
        assert r.status_code == 422 and r.json()["code"] == "batch_empty" and ("변조" in r.json()["detail"] or "키" in r.json()["detail"] or "인증" in r.json()["detail"]), r.text[:300]
        keyfile.write_bytes(good)
        assert a.make_batch([ok1["id"]]).status_code == 201                  # 키를 되돌리면 같은 승인이 다시 유효
        keyfile.unlink()                                                    # 키 파일 없음 → 새 키 생성, 이전 승인은 무효
        r = a.approve(ok2_sugs[0]["id"])
        assert r.status_code == 200 and keyfile.exists() and keyfile.read_bytes() != good
        r2 = a.make_batch([ok2_sugs[0]["id"]])
        assert r2.status_code == 201
        draft_old = a.get("/api/v1/batches").json()["items"]
        old_batch = [b_ for b_ in draft_old if b_["id"] != r2.json()["batch"]["id"]][0]["id"]
        r3 = a.execute(old_batch, 1)                                        # 옛 키로 서명된 승인이 담긴 초안은 확정 거부
        assert r3.status_code == 409 and r3.json()["code"] == "precheck_stale" and ("변조" in r3.json()["detail"] or "인증" in r3.json()["detail"]), r3.text[:300]
        assert a.execute(r2.json()["batch"]["id"], 1).status_code == 202
        assert a.wait_batch(r2.json()["batch"]["id"])["counts"]["success"] == 1
    finally:
        keyfile.write_bytes(good) if not keyfile.exists() or keyfile.read_bytes() != good else None


# ─────────────────────────── 백엔드 자체의 속도 제한·진입 검사 ───────────────────────────

@native_only
def test_it_431_backend_rate_limits_and_foreign_origin_budget_and_entry_checks():
    """IT-431: (nginx 없이 백엔드만 — 제품 기본 속도 제한으로 띄운 별도 서버) 세션 발급 분당 10회 초과 → 429 rate_limited + Retry-After, 쓰기 분당 120회 초과 → 429,
    허용되지 않은 출처의 요청은 별도 한도로 세어 소유자의 한도를 소모하지 않는다(소유자는 계속 200). Host 가 허용 목록 밖이면 403 host_not_allowed(헬스 경로는 면제),
    본문 1MB 초과 413 payload_too_large, 잘못된 Content-Length 400. 검증: API.md 1-1, 1-3, SEC-W07"""
    import httpx
    nat = ib.nat
    port = 18091
    nat.api_start(False, port=port, name="api_strict")
    try:
        nat.wait_api(port)
        base = f"http://127.0.0.1:{port}"
        H = {"Host": ib.HOST_OK, "Origin": ib.ORIGIN_OK}
        c = httpx.Client(base_url=base, timeout=20)
        codes = []
        for i in range(12):
            r = c.post("/api/v1/auth/session", json={}, headers=H)
            codes.append((r.status_code, r.json().get("code", ""), r.headers.get("retry-after")))
        assert [x[0] for x in codes[:10]] == [200] * 10 and codes[10][0] == 429 and codes[10][1] == "rate_limited" and int(codes[10][2]) >= 1, codes
        # 이미 받은 세션으로 조회는 계속 된다(세션 발급 한도는 별도)
        csrf = c.post("/api/v1/auth/session", json={}, headers=H)  # 한도 초과 상태(429)여도 아래 쿠키(앞서 받은 것)로 계속
        me = c.get("/api/v1/auth/me", headers={"Host": ib.HOST_OK})
        assert me.status_code == 200 and me.json()["authenticated"] is True
        token = me.json()["csrf_token"]
        # 허용되지 않은 출처는 소유자 한도를 소모하지 않는다
        for i in range(605):               # 출처 불명 요청의 별도 창은 분당 600
            r = c.post("/api/v1/videos/sync", headers={"Host": ib.HOST_OK, "Origin": "http://evil.example", "X-CSRF-Token": token})
            assert r.status_code in (403, 429)
        assert r.status_code == 429 and r.json()["code"] == "rate_limited"
        ok = c.get("/api/v1/dashboard", headers={"Host": ib.HOST_OK})
        assert ok.status_code == 200
        # 쓰기 한도(분당 120): 소유자의 쓰기 요청을 120회 넘게 보내면 429
        w = [c.patch("/api/v1/settings", json={"suggestions_per_video": 3}, headers={**H, "X-CSRF-Token": token}).status_code for _ in range(125)]
        assert w.count(200) <= 120 and 429 in w, (w.count(200), w.count(429))
        # 진입 검사
        h = httpx.Client(base_url=base, timeout=10)
        r = h.get("/api/v1/dashboard", headers={"Host": "evil.example"})
        assert r.status_code == 403 and r.json()["code"] == "host_not_allowed" and r.json()["hint"]
        assert h.get("/api/healthz", headers={"Host": "evil.example"}).status_code == 200            # 헬스 경로는 Host 검사 면제
        big = h.post("/api/v1/suggestions/generate", content=b"x" * (1024 * 1024 + 1), headers={**H, "Content-Type": "application/json", "X-CSRF-Token": token})
        assert big.status_code in (413, 429), big.status_code
        if big.status_code == 429:
            time.sleep(1)
        import socket
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        s.sendall(b"POST /api/v1/auth/session HTTP/1.1\r\nHost: 127.0.0.1:8080\r\nOrigin: http://127.0.0.1:8080\r\nContent-Length: -1\r\nContent-Type: application/json\r\n\r\n")
        data = s.recv(4096).decode("latin-1")
        s.close()
        assert " 400 " in data.split("\r\n")[0] or " 429 " in data.split("\r\n")[0], data[:100]
    finally:
        nat.proc_stop("api_strict")


# ─────────────────────────── 문서에 적힌 오류 코드 전수 대조(세션 전체 관찰) ───────────────────────────

# 이 스택(모의 유튜브·모의 AI·데모 시드)에서는 HTTP 로 도달할 수 없는 문서화된 코드와 그 이유.
_UNREACHABLE_DOC_CODES = {
    "count_invalid": "스키마 단계에서 validation_error 로 먼저 막힘(DEF-7-004)",
    "ai_unavailable": "모의 제안기는 실패하지 않음(M3 실제 AI 연결 전)",
    "ai_no_candidates": "모의 제안기는 항상 후보를 냄",
    "title_invalid": "본문 스키마가 문자열을 강제해 서비스 단계의 형식 오류에 도달하지 않음",
    "gateway_error": "모의 유튜브 게이트웨이는 오류를 내지 않음(M2 이후)",
    "schedule_overflow": "예약 범위 400일 초과는 50건 x 9배치 이상이 필요(하루 상한 1 기준) — 이 시험 규모 밖",
    "already_in_batch": "동시 경합에서만 나오는 보조 코드(순차 요청은 사전 점검이 batch_empty 로 막음) — IT-307 이 경합을 일으키지만 매번 나오지는 않음",
    "pending_change_exists": "롤백 중 진행 중 변경 충돌은 동시 경합에서만(순차에서는 later_change_exists 가 먼저)",
    "idempotency_in_progress": "IT-302/304 가 동시 전송으로 일으키지만 경합 결과라 매번 나오지는 않음",
}
_DOCUMENTED_ERROR_CODES = [
    "origin_not_allowed", "cross_site_request", "pin_invalid", "pin_locked", "rate_limited", "host_not_allowed", "payload_too_large", "csrf_invalid", "session_required",
    "idempotency_key_required", "idempotency_key_invalid", "idempotency_key_reuse", "idempotency_in_progress", "job_not_found", "video_not_found", "video_excluded", "count_invalid",
    "ai_unavailable", "ai_no_candidates", "suggestion_not_found", "suggestion_state", "duplicate_suggestion", "title_empty", "title_too_long", "title_invalid", "suggestion_blocked",
    "same_as_current", "video_inconsistent", "approval_key_unreadable", "approver_required", "approver_invalid", "batch_empty", "batch_too_large", "already_in_batch",
    "schedule_overflow", "batch_not_draft", "confirm_text_mismatch", "precheck_stale", "batch_not_found", "batch_not_cancellable", "change_not_found", "not_rollbackable",
    "typed_video_id_mismatch", "later_change_exists", "backup_invalid", "already_restored", "pending_change_exists", "quota_exhausted", "gateway_error", "setting_not_allowed",
    "validation_error", "pin_not_set",
]


_DOC_MISSING_CODES = {"session_required"}      # DEF-7-005: 서버가 가장 흔하게 내는 401 코드인데 API.md 어디에도 적혀 있지 않다


@pytest.mark.xfail(strict=True, reason="DEF-7-005: API.md 가 401 `session_required`(세션 없음·만료)를 어느 절에도 적지 않았다(서버는 모든 보호 엔드포인트에서 이 코드를 낸다). 문서에 추가하면 XPASS(strict 실패)로 알려 주므로 이 표시와 _DOC_MISSING_CODES 를 지운다")
def test_it_435_api_md_documents_session_required_error_code():
    """IT-435(결함 고정, DEF-7-005): 세션 없이 보호 엔드포인트를 부르면 401 `session_required` 가 나오고(실제), 같은 코드가 API.md 에 적혀 있어야 한다(프런트가 이 코드로 세션 만료 화면을 띄운다).
    검증: API.md 1-7, S-W02"""
    r = Api().get("/api/v1/dashboard")
    assert r.status_code == 401 and r.json()["code"] == "session_required"
    assert "`session_required`" in API_MD


def test_it_421_zz_documented_error_codes_vs_observed_session_wide_and_hints_are_korean():
    """IT-421: (B 트랙 시험 전체를 한 번에 돌린 세션에서만 의미가 있다) (a) API.md 에 적힌 오류 코드(51개)가 모두 문서에 실제로 있다 (b) 서버가 낸 모든 오류 코드는
    API.md 에 적혀 있다(문서에 없는 코드를 내보내면 실패) (c) 문서화된 코드는 이 세션에서 관찰됐거나 도달 불가 사유가 있다 (d) 관찰된 모든 오류 응답에 한국어 title·hint 가 있다
    (e) 오류 본문에 내부 경로·스택이 없다. 검증: API.md 1-7, 5~8장, S-W09"""
    if len(OBSERVED) < 3000:
        pytest.skip("B 트랙 전체 세션(02+03+04 함께)에서만 판정한다 — 관찰 기록이 부족함: %d" % len(OBSERVED))
    for code in _DOCUMENTED_ERROR_CODES:
        if code in _DOC_MISSING_CODES:
            continue          # API.md 에 아직 없는 것으로 확인된 코드는 IT-435 (결함 DEF-7-005 고정)가 따로 본다
        assert f"`{code}`" in API_MD or f"{code}`" in API_MD, f"{code}: 목록과 API.md 가 어긋남"
    errs = [(m, p, st, code, body) for m, p, st, code, body in OBSERVED if st >= 400]
    observed_codes = {code for _, _, _, code, _ in errs if code}
    undocumented = sorted(c for c in observed_codes if f"`{c}`" not in API_MD and c not in ("not_found", "method_not_allowed") and c not in _DOC_MISSING_CODES)
    assert not undocumented, f"서버가 내보냈지만 API.md 에 없는 오류 코드: {undocumented}"
    never = sorted(c for c in _DOCUMENTED_ERROR_CODES if c not in observed_codes and c not in _UNREACHABLE_DOC_CODES)
    assert not never, f"문서에는 있으나 이 세션에서 한 번도 관찰되지 않았고 도달 불가 사유도 없는 코드: {never}"
    bad = []
    for m, p, st, code, body in errs:
        if not isinstance(body, dict):
            continue
        txt = json.dumps(body, ensure_ascii=False)
        if not (HANGUL.search(body.get("title", "")) and HANGUL.search(body.get("hint", ""))):
            bad.append((m, p, st, code, "한국어 title/hint 없음"))
        if "Traceback" in txt or "/app/" in txt or "File \"" in txt or "site-packages" in txt or str(REPO) in txt:
            bad.append((m, p, st, code, "내부 경로·스택 노출"))
        if body.get("code") != code or body.get("status") != st:
            bad.append((m, p, st, code, "본문 code/status 불일치"))
    assert not bad, bad[:10]
    print("observed error codes:", sorted(observed_codes))
    print("documented but unreachable here:", sorted(c for c in _DOCUMENTED_ERROR_CODES if c not in observed_codes))


_DOC_ACTIONS = {"session.create", "session.denied", "session.delete", "settings.update", "videos.sync_request", "videos.sync", "suggestion.generate_request", "suggestion.generate",
                "suggestion.generate_failed", "suggestion.edit", "suggestion.approve", "suggestion.reject", "batch.create", "batch.execute", "batch.cancel", "batch.item.skipped",
                "batch.item.failed", "batch.item.recovered", "change.apply", "change.rollback", "change.rollback_failed"}
_ACTION_UNREACHABLE = {"suggestion.generate_failed": "모의 제안기는 실패하지 않음", "change.rollback_failed": "모의 유튜브 갱신은 실패하지 않음",
                       "batch.item.failed": "데모에서는 재조회·갱신·검증이 실패하지 않아 failed 항목이 만들어지지 않음(복구 경로는 recovered 로 기록)"}


def test_it_423_zz_audit_actions_observed_match_api_md_list():
    """IT-423: (전체 세션에서만) 감사 로그에서 실제로 본 action 이 모두 API.md 7장의 목록에 있고(예외: 6장에 따로 적힌 batch.item.deferred), 문서의 action 은 관찰됐거나
    도달 불가 사유가 있다. 검증: API.md 7장, S-W16"""
    if len(OBSERVED) < 3000:
        pytest.skip("B 트랙 전체 세션에서만 판정 — 관찰 기록 부족: %d" % len(OBSERVED))
    from itlib_b import harvest_actions
    harvest_actions()                       # 마지막 시험이 남긴 DB 의 action 까지 합친다
    seen = set(ACTIONS_SEEN)
    extra = sorted(seen - _DOC_ACTIONS - {"batch.item.deferred"})
    assert not extra, f"API.md 7장 목록에 없는 감사 action: {extra}"
    missing = sorted(a_ for a_ in _DOC_ACTIONS - seen if a_ not in _ACTION_UNREACHABLE)
    assert not missing, f"문서에는 있으나 이 세션에서 본 적 없는 action: {missing}"
    assert "batch.item.deferred" in seen, "이월 감사 action(batch.item.deferred) 관찰 없음"
    assert "`batch.item.deferred`" in API_MD
    print("audit actions seen:", sorted(seen))
