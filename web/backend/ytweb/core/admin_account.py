"""관리자 계정(1명) 로그인: 웹 최초 설정으로 계정 생성(DEC-056), 아이디·비밀번호 검증, 연속 실패 잠금(DEC-055).

비밀번호는 scrypt 해시만 DB 에 둔다. 실패 횟수·잠금은 소유자 1명 전역 카운터(PIN 과 같은 방식)이며,
아이디가 없든 비밀번호가 틀리든 같은 오류 문구·같은 처리 시간(더미 해시 검증)으로 계정 존재 여부를 숨긴다.
"""
from __future__ import annotations

import hmac
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from ytweb.core.errors import ProblemError
from ytweb.core.pin import hash_pin, verify_pin_hash
from ytweb.core.settings_store import get_web_setting, set_web_setting
from ytweb.db.models import AdminAccount, SessionRow, SettingKV

log = logging.getLogger("ytweb.admin")

FAIL_KEY = "admin_login_fail"
MAX_FAILURES = 5
BASE_LOCK = timedelta(minutes=5)
MAX_LOCK = timedelta(hours=1)
LOGIN_ID_RE = re.compile(r"[A-Za-z0-9]{4,20}")
PASSWORD_MIN, PASSWORD_MAX = 8, 64
_ADVISORY_LOCK_KEY = 7_340_003  # 실패 횟수 갱신(읽기-수정-쓰기)을 직렬화(PIN 과 다른 키)
INVALID_MESSAGE = "아이디 또는 비밀번호가 올바르지 않습니다."

_dummy_hash: str | None = None


def _dummy() -> str:
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_pin("dummy-password-for-timing")
    return _dummy_hash


def validate_credentials_format(login_id: str, password: str) -> str | None:
    """형식이 맞으면 None, 아니면 사유(비밀번호 값은 사유에 넣지 않는다)."""
    if not LOGIN_ID_RE.fullmatch(login_id or ""):
        return "아이디는 영문·숫자 4~20자여야 합니다."
    if not isinstance(password, str) or not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        return f"비밀번호는 {PASSWORD_MIN}~{PASSWORD_MAX}자여야 합니다."
    return None


def has_admin(db: Session) -> bool:
    return db.scalars(select(AdminAccount.login_id).limit(1)).first() is not None


def create_admin(db: Session, login_id: str, password: str, *, now: datetime) -> AdminAccount:
    """웹 최초 설정(DEC-056): 계정이 하나도 없을 때만 만든다. 이미 있으면 409 setup_closed(영구히 닫힘).
    PostgreSQL 에서는 advisory lock 으로 동시 최초 설정 요청 중 하나만 성공하게 한다."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY + 1})
    if has_admin(db):
        raise ProblemError(409, "setup_closed", "이미 관리자 계정이 있습니다.", hint="로그인 화면에서 아이디와 비밀번호로 로그인하세요.")
    reason = validate_credentials_format(login_id, password)
    if reason:
        raise ProblemError(422, "setup_invalid", reason, hint="아이디는 영문·숫자 4~20자, 비밀번호는 8~64자로 입력하세요.")
    account = AdminAccount(login_id=login_id, password_hash=hash_pin(password), created_at=now, updated_at=now, last_login_at=now)
    db.add(account)
    db.flush()
    return account


def reset_admin(db: Session) -> int:
    """비밀번호를 잊었을 때(reset-admin 스크립트): 계정·세션·실패 잠금을 지운다. 지운 계정 수를 돌려준다."""
    n = db.execute(delete(AdminAccount)).rowcount or 0
    db.execute(delete(SessionRow))
    obj = db.get(SettingKV, FAIL_KEY)
    if obj is not None:
        db.delete(obj)
    db.flush()
    return n


def admin_login_id(db: Session) -> str | None:
    return db.scalars(select(AdminAccount.login_id).limit(1)).first()


def _state(db: Session) -> dict:
    st = get_web_setting(db, FAIL_KEY) or {}
    return {"count": int(st.get("count", 0)), "lockouts": int(st.get("lockouts", 0)), "locked_until": st.get("locked_until")}


def _locked(until: datetime, now: datetime) -> ProblemError:
    wait = max(1, int((until - now).total_seconds()))
    minutes = (wait + 59) // 60
    return ProblemError(429, "login_locked", "로그인 실패가 많아 잠시 잠겼습니다.",
                        hint=f"약 {minutes}분 뒤에 다시 시도하세요.", headers={"Retry-After": str(wait)})


def authenticate(db: Session, login_id: str, password: str, *, now: datetime) -> AdminAccount:
    """성공하면 계정을 돌려준다. 실패 기록은 이 함수가 commit 한다(예외 롤백 전에). 실패 사유는 항상 같은 문구."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY})
        obj = db.get(SettingKV, FAIL_KEY)
        if obj is not None:
            db.refresh(obj)
    account = db.scalars(select(AdminAccount)).first()
    if account is None:
        raise ProblemError(409, "login_not_configured", "관리자 계정이 아직 설정되지 않았습니다.",
                           hint="PC 에서 web\\scripts\\set-admin.bat 을 실행해 아이디와 비밀번호를 만드세요.")
    st = _state(db)
    if st["locked_until"]:
        until = datetime.fromisoformat(st["locked_until"])
        if until > now:
            raise _locked(until, now)
    id_ok = hmac.compare_digest(login_id.encode(), account.login_id.encode())
    pw_ok = verify_pin_hash(password, account.password_hash if id_ok else _dummy())  # 아이디가 틀려도 같은 시간 소요
    if id_ok and pw_ok:
        set_web_setting(db, FAIL_KEY, {"count": 0, "lockouts": 0, "locked_until": None}, now=now)
        account.last_login_at = now
        return account
    st["count"] += 1
    if st["count"] >= MAX_FAILURES:
        st["locked_until"] = (now + min(BASE_LOCK * (2 ** st["lockouts"]), MAX_LOCK)).isoformat()
        st["lockouts"] += 1
        st["count"] = 0
    set_web_setting(db, FAIL_KEY, st, now=now)
    db.commit()
    if st["locked_until"] and datetime.fromisoformat(st["locked_until"]) > now:
        raise _locked(datetime.fromisoformat(st["locked_until"]), now)
    raise ProblemError(401, "login_invalid", INVALID_MESSAGE, hint="입력한 값을 다시 확인하세요. 연속으로 틀리면 잠깁니다.")
