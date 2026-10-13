"""저장형 XSS 의 서버 쪽: 악성 문자열이 저장·반환되는 모습(JSON 원문 보존, application/json + nosniff, CSP)."""
import pytest
from tests.verify_m23.conftest import hdr

EVIL = ["<script>alert(1)</script>", '"><img src=x onerror=alert(1)>', "<svg onload=alert(1)>", "javascript:alert(1)", "\uff1cscript\uff1e"]

def test_server_side_headers_and_storage(live):
    a, c = live.api, live.csrf
    vid = live.ids[0]
    r = a.post(f"/api/v1/videos/{vid}/suggestions", json={"count": 5}, headers=hdr(c)); assert r.status_code == 201
    sid = r.json()[0]["id"]
    results = {}
    for e in EVIL:
        p = a.patch(f"/api/v1/suggestions/{sid}", json={"title": e}, headers=hdr(c))
        results[("patch", e)] = (p.status_code, p.json().get("code") if p.status_code >= 400 else p.json().get("title") == e)
    for e in EVIL:
        ap = a.post(f"/api/v1/suggestions/{sid}/approve", json={"approver": e}, headers=hdr(c))
        results[("approve", e)] = (ap.status_code, ap.json().get("code") if ap.status_code >= 400 else None)
        if ap.status_code == 200: break
    for k, v in results.items(): print(k, v)
    g = a.get(f"/api/v1/suggestions?video_id={vid}")
    print("GET", g.status_code, g.headers.get("content-type"), g.headers.get("x-content-type-options"), g.headers.get("content-security-policy"))
    assert g.headers["content-type"].startswith("application/json")
    assert g.headers.get("x-content-type-options", "").lower() == "nosniff"
    assert "default-src" in g.headers.get("content-security-policy", "")
    # 원문이 JSON 안에 들어 있어도 content-type 이 json 이므로 실행되지 않는다. 저장된 값이 변형 없이 오는지(이스케이프를 서버가 하지 않는지) 기록
    body = g.text
    print("stored-as-is?", {e: (e in body or e.replace("<", "\\u003c") in body) for e in EVIL})


def test_approver_name_stored_raw_and_returned_as_json(live):
    a, c = live.api, live.csrf
    r = a.post(f"/api/v1/videos/{live.ids[0]}/suggestions", json={"count": 5}, headers=hdr(c))
    cand = [x for x in r.json() if x["validation_result"] == "pass"][0]
    ap = a.post(f"/api/v1/suggestions/{cand['id']}/approve", json={"approver": EVIL[1]}, headers=hdr(c))
    print("approve evil approver", ap.status_code, ap.text[:120])
    assert ap.status_code == 200
    g = a.get(f"/api/v1/suggestions?video_id={live.ids[0]}")
    assert any((x.get("approval") or {}).get("approver") == EVIL[1] for x in g.json()["items"] if isinstance(g.json(), dict)) or EVIL[1] in g.text.replace("\\u003c", "<")
    assert g.headers["content-type"].startswith("application/json")
