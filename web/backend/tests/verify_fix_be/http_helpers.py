"""HTTP 수준 시험 공용 도구(W-FIX-BE 독립 검증)."""
from __future__ import annotations

import uuid

from tests.verify_fix_be.conftest import hdr, life_ids


def approved_via_api(api, csrf, factory, n: int, skip: int = 0) -> list[int]:
    with factory() as s:
        vids = life_ids(s, n, skip)
    ids = []
    for v in vids:
        r = api.post(f"/api/v1/videos/{v}/suggestions", json={"count": 5}, headers=hdr(csrf))
        assert r.status_code == 201, r.text
        sug = next(x for x in r.json() if x["validation_result"] == "pass")
        a = api.post(f"/api/v1/suggestions/{sug['id']}/approve", json={"approver": "검수자"}, headers=hdr(csrf))
        assert a.status_code == 200, a.text
        ids.append(sug["id"])
    return ids


def draft(api, csrf, ids, note=None):
    return api.post("/api/v1/batches", json={"suggestion_ids": ids, "note": note}, headers=hdr(csrf, uuid.uuid4().hex))


def cancel(api, csrf, bid):
    return api.post(f"/api/v1/batches/{bid}/cancel", headers=hdr(csrf))


def execute(api, csrf, bid, text):
    return api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": text}, headers=hdr(csrf, uuid.uuid4().hex))
