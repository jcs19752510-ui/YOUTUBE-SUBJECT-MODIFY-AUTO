"""OpenAPI 문서에 공통 오류 응답(400·404·409·422, problem+json)을 한 곳에서 덧붙인다.

문서화만 한다: 요청 처리·오류 핸들러·응답 본문은 바꾸지 않는다. 형식은 errors.problem_body 와 같다.
"""
from __future__ import annotations

from typing import Any, Callable

from ytweb.core.errors import PROBLEM_MEDIA_TYPE

PROBLEM_SCHEMA_NAME = "Problem"

PROBLEM_SCHEMA: dict[str, Any] = {
    "title": "Problem",
    "description": "RFC 9457 problem+json 오류 본문(ytweb.core.errors.problem_body). code 는 프로그램이 분기하는 안정 값이다.",
    "type": "object",
    "required": ["type", "title", "status", "detail", "code", "hint"],
    "properties": {
        "type": {"type": "string", "title": "Type", "description": "urn:ytweb:problem:<code>"},
        "title": {"type": "string", "title": "Title"},
        "status": {"type": "integer", "title": "Status"},
        "detail": {"type": "string", "title": "Detail"},
        "code": {"type": "string", "title": "Code"},
        "hint": {"type": "string", "title": "Hint"},
    },
}

COMMON_ERRORS: dict[str, str] = {
    "400": "잘못된 요청(예: Idempotency-Key 누락). problem+json",
    "404": "대상을 찾을 수 없음. problem+json",
    "409": "현재 상태와 충돌. problem+json",
    "422": "요청 값이 올바르지 않음(code: validation_error 등). problem+json",
}

_HTTP_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def add_common_error_responses(schema: dict[str, Any]) -> dict[str, Any]:
    schema.setdefault("components", {}).setdefault("schemas", {})[PROBLEM_SCHEMA_NAME] = PROBLEM_SCHEMA
    ref = {"$ref": f"#/components/schemas/{PROBLEM_SCHEMA_NAME}"}
    for item in schema.get("paths", {}).values():
        for method in _HTTP_METHODS:
            op = item.get(method)
            if not op:
                continue
            responses = op.setdefault("responses", {})
            for status, desc in COMMON_ERRORS.items():
                # 실제 오류는 모두 problem+json 이다. 기본 422(HTTPValidationError, application/json)도 같은 형식으로 바로잡는다.
                responses[status] = {"description": desc, "content": {PROBLEM_MEDIA_TYPE: {"schema": ref}}}
    return schema


def install(app: Any) -> None:
    """app.openapi() 결과에 공통 오류 응답을 덧붙이고 캐시한다."""
    original: Callable[[], dict[str, Any]] = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = add_common_error_responses(original())
        return app.openapi_schema

    app.openapi = openapi
