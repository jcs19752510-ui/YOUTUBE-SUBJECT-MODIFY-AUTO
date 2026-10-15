"""SPEC-1: OpenAPI 에 공통 오류 응답(400/404/409/422, problem+json)이 모든 동작에 있고 실제 응답 형식과 일치하는지."""
from __future__ import annotations

import json
from pathlib import Path

from ytweb.core.errors import PROBLEM_MEDIA_TYPE, problem_body

REPO_ROOT = Path(__file__).resolve().parents[4]
METHODS = ("get", "put", "post", "delete", "patch")


def _schema(web_settings):
    """모든 라우터를 올린 실제 앱의 OpenAPI(core 라우터만 쓰는 client 픽스처는 쓰지 않는다)."""
    from ytweb.app import create_app
    return create_app(web_settings).openapi()


def test_every_operation_documents_problem_errors(web_settings):
    schema = _schema(web_settings)
    ops = [(p, m) for p, item in schema["paths"].items() for m in METHODS if m in item]
    assert len(ops) >= 30
    for path, m in ops:
        responses = schema["paths"][path][m]["responses"]
        for status in ("400", "404", "409", "422"):
            assert status in responses, (path, m, status)
            content = responses[status]["content"]
            assert list(content) == [PROBLEM_MEDIA_TYPE], (path, m, status)
            assert content[PROBLEM_MEDIA_TYPE]["schema"] == {"$ref": "#/components/schemas/Problem"}


def test_problem_schema_matches_problem_body(web_settings):
    prob = _schema(web_settings)["components"]["schemas"]["Problem"]
    body = problem_body(404, "x", "t", "d", "h")
    assert set(prob["properties"]) == set(body) == set(prob["required"])
    assert prob["properties"]["status"]["type"] == "integer"
    assert all(prob["properties"][k]["type"] == "string" for k in body if k != "status")


def test_documented_422_equals_real_422(client):
    """실제 422 응답이 문서의 content-type·필드와 같다(문서만 바꿨고 동작은 그대로)."""
    r = client.post("/api/v1/auth/session", content="not json", headers={"Origin": "http://127.0.0.1:8080", "Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert set(r.json()) == set(problem_body(422, "c", "t"))


def test_saved_openapi_json_is_current(web_settings):
    saved = json.loads((REPO_ROOT / "docs" / "yt" / "openapi.json").read_text(encoding="utf-8"))
    assert saved == _schema(web_settings)
