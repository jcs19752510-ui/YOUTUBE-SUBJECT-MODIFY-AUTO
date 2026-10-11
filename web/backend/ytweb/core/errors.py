"""RFC 9457 problem+json 오류. 핸들러는 app.py 에서 등록한다."""
from __future__ import annotations

from typing import Any

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemError(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str = "", hint: str = "", headers: dict[str, str] | None = None) -> None:
        super().__init__(f"{code}: {title}")
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.hint = hint
        self.headers = headers or {}


def problem_body(status: int, code: str, title: str, detail: str = "", hint: str = "") -> dict[str, Any]:
    return {
        "type": f"urn:ytweb:problem:{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "code": code,
        "hint": hint,
    }
