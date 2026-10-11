"""안전 설정만 변경한다. 라이브 허용·허용 영상 목록은 API 로 바꿀 수 없다(읽기 전용 표시)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from youtube_title.config import Settings

from ytweb.config import WebSettings
from ytweb.core import audit
from ytweb.core.deps import (
    get_clock,
    get_policy,
    get_session,
    get_web_settings,
    require_csrf,
    require_session,
)
from ytweb.core.errors import ProblemError
from ytweb.core.pin import (
    check_pin,
    clear_pin,
    pin_required,
    set_pin,
    validate_pin_format,
)
from ytweb.core.sessions import SessionInfo, delete_other_sessions
from ytweb.core.settings_store import (
    DEFAULT_SUGGESTIONS_PER_VIDEO,
    effective_daily_cap,
    get_web_setting,
    set_web_setting,
)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

ALLOWED_KEYS = frozenset({"daily_apply_cap", "suggestions_per_video", "tone", "pin"})
TONE_MAX_ITEMS = 5
TONE_MAX_CHARS = 20


def _int_in(value: Any, key: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ProblemError(422, "validation_error", f"{key} 는 {lo}~{hi} 사이의 정수여야 합니다.", hint=f"{lo}~{hi} 사이의 정수로 입력하세요.")
    return value


def _tone(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > TONE_MAX_ITEMS:
        raise ProblemError(422, "validation_error", f"tone 은 최대 {TONE_MAX_ITEMS}개의 짧은 문자열 목록이어야 합니다.", hint="말투 항목을 줄이고 각 항목을 짧게 입력하세요.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ProblemError(422, "validation_error", "tone 항목은 문자열이어야 합니다.", hint="말투 항목은 글자로만 입력하세요.")
        item = item.strip()
        if not 1 <= len(item) <= TONE_MAX_CHARS or any(ord(c) < 32 for c in item):
            raise ProblemError(422, "validation_error", f"tone 항목은 제어문자 없는 1~{TONE_MAX_CHARS}자여야 합니다.", hint="줄바꿈 등 특수 문자를 빼고 20자 이내로 입력하세요.")
        out.append(item)
    return out


def _view(db: Session, policy: Settings, web: WebSettings) -> dict:
    return {
        "daily_apply_cap": effective_daily_cap(db, policy),
        "suggestions_per_video": get_web_setting(db, "suggestions_per_video", DEFAULT_SUGGESTIONS_PER_VIDEO),
        "tone": get_web_setting(db, "tone", []),
        "pin_enabled": pin_required(db),
        "mode": web.mode,
        "read_only": {
            "enable_live": policy.enable_live,
            "live_allowlist": list(policy.live_allowlist),
            "note": "라이브 반영 허용과 허용 영상 목록은 화면에서 바꿀 수 없습니다.",
        },
    }


@router.get("", dependencies=[Depends(require_session)])
def read_settings(db: Session = Depends(get_session), policy: Settings = Depends(get_policy), web: WebSettings = Depends(get_web_settings)) -> dict:
    return _view(db, policy, web)


@router.patch("")
def update_settings(
    body: dict[str, Any] = Body(...),
    info: SessionInfo = Depends(require_csrf),
    db: Session = Depends(get_session),
    policy: Settings = Depends(get_policy),
    web: WebSettings = Depends(get_web_settings),
    clock: Callable[[], datetime] = Depends(get_clock),
) -> dict:
    forbidden = sorted(k for k in body if k not in ALLOWED_KEYS)
    if forbidden:
        raise ProblemError(400, "setting_not_allowed", "이 설정은 화면에서 변경할 수 없습니다.",
                           detail=f"허용되지 않은 키: {', '.join(k[:40] for k in forbidden[:5])}",
                           hint="변경 가능한 항목: daily_apply_cap, suggestions_per_video, tone, pin")
    if not body:
        raise ProblemError(422, "validation_error", "변경할 설정이 없습니다.", hint="바꿀 항목을 하나 이상 선택하세요.")
    now = clock()

    changes: dict[str, Any] = {}
    if "daily_apply_cap" in body:
        changes["daily_apply_cap"] = _int_in(body["daily_apply_cap"], "daily_apply_cap", 1, 20)
    if "suggestions_per_video" in body:
        changes["suggestions_per_video"] = _int_in(body["suggestions_per_video"], "suggestions_per_video", 1, 5)
    if "tone" in body:
        changes["tone"] = _tone(body["tone"])

    pin_action: str | None = None
    if "pin" in body:
        p = body["pin"]
        if not isinstance(p, dict) or set(p) - {"action", "new_pin", "current_pin"} or p.get("action") not in ("set", "clear"):
            raise ProblemError(422, "validation_error", "pin 은 {action: 'set'|'clear', new_pin?, current_pin?} 형식이어야 합니다.", hint="화면의 PIN 설정 양식을 통해 변경하세요.")
        if p["action"] == "set":
            validate_pin_format(p.get("new_pin"))
        had_pin = pin_required(db)
        if had_pin:
            cur = p.get("current_pin")
            check_pin(db, cur if isinstance(cur, str) else None, now=now)
        if p["action"] == "clear" and not had_pin:
            raise ProblemError(409, "pin_not_set", "설정된 PIN 이 없습니다.", hint="PIN 이 꺼져 있어 해제할 것이 없습니다. 화면을 새로고침하세요.")
        pin_action = "cleared" if p["action"] == "clear" else ("changed" if had_pin else "set")
        if p["action"] == "set":
            set_pin(db, p["new_pin"], now=now)
        else:
            clear_pin(db)
        delete_other_sessions(db, info.session_id)

    for key, value in changes.items():
        set_web_setting(db, key, value, now=now)
    detail: dict[str, Any] = dict(changes)
    if pin_action:
        detail["pin"] = pin_action  # PIN 값은 감사 로그에도 남기지 않는다
    audit.record(db, actor="owner", action="settings.update", target_type="settings", detail=detail, now=now)
    return _view(db, policy, web)
