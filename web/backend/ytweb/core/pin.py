"""선택형 PIN: scrypt+솔트 저장, 연속 실패 시 잠금(소유자 1명 전제의 전역 카운터)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ytweb.core.errors import ProblemError
from ytweb.core.settings_store import delete_web_setting, get_web_setting, set_web_setting

PIN_KEY = "pin_hash"
FAIL_KEY = "pin_fail"
MAX_FAILURES = 5
BASE_LOCK = timedelta(minutes=5)
MAX_LOCK = timedelta(hours=1)
_PIN_RE = re.compile(r"^[0-9]{4,12}$")
_N, _R, _P = 2**14, 8, 1


def validate_pin_format(pin: str) -> None:
    if not isinstance(pin, str) or not _PIN_RE.match(pin):
        raise ProblemError(422, "pin_invalid", "PIN 은 숫자 4~12자리여야 합니다.")


def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(pin.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return "scrypt${}${}${}${}${}".format(_N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_pin_hash(pin: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(pin.encode(), salt=base64.b64decode(salt_b64), n=int(n), r=int(r), p=int(p), dklen=len(expected))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def pin_required(db: Session) -> bool:
    return get_web_setting(db, PIN_KEY) is not None


def set_pin(db: Session, pin: str, *, now: datetime) -> None:
    validate_pin_format(pin)
    set_web_setting(db, PIN_KEY, hash_pin(pin), now=now)


def clear_pin(db: Session) -> None:
    delete_web_setting(db, PIN_KEY)
    delete_web_setting(db, FAIL_KEY)


def _fail_state(db: Session) -> dict:
    st = get_web_setting(db, FAIL_KEY) or {}
    return {"count": int(st.get("count", 0)), "lockouts": int(st.get("lockouts", 0)), "locked_until": st.get("locked_until")}


def _locked_error(until: datetime, now: datetime) -> ProblemError:
    wait = max(1, int((until - now).total_seconds()))
    return ProblemError(429, "pin_locked", "PIN 입력 실패가 많아 잠시 잠겼습니다.",
                        hint=f"{wait}초 후에 다시 시도하세요.", headers={"Retry-After": str(wait)})


def check_pin(db: Session, pin: str | None, *, now: datetime) -> None:
    """PIN 이 설정돼 있으면 검증한다. 실패 기록은 호출자가 commit 해야 남는다(예외로 롤백되기 전에)."""
    stored = get_web_setting(db, PIN_KEY)
    if stored is None:
        return
    st = _fail_state(db)
    if st["locked_until"]:
        until = datetime.fromisoformat(st["locked_until"])
        if until > now:
            raise _locked_error(until, now)
    if pin is not None and isinstance(pin, str) and verify_pin_hash(pin, stored):
        set_web_setting(db, FAIL_KEY, {"count": 0, "lockouts": 0, "locked_until": None}, now=now)
        return
    st["count"] += 1
    if st["count"] >= MAX_FAILURES:
        lock = min(BASE_LOCK * (2 ** st["lockouts"]), MAX_LOCK)
        st["lockouts"] += 1
        st["count"] = 0
        st["locked_until"] = (now + lock).isoformat()
    set_web_setting(db, FAIL_KEY, st, now=now)
    db.commit()
    if st["locked_until"] and datetime.fromisoformat(st["locked_until"]) > now:
        raise _locked_error(datetime.fromisoformat(st["locked_until"]), now)
    raise ProblemError(401, "pin_invalid", "PIN 이 올바르지 않습니다.")
