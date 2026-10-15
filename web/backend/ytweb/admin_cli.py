"""관리자 계정 운영 명령. `python -m ytweb.admin_cli reset` — 비밀번호를 잊었을 때 계정·세션·실패 잠금을 지운다(DEC-056).

값(비밀번호)을 다루지 않는다. 지운 뒤에는 브라우저에서 새 관리자 계정을 만든다(웹 최초 설정 화면).
"""
from __future__ import annotations

import sys

from ytweb.config import load_web_settings
from ytweb.core import admin_account, audit
from ytweb.core.clock import utcnow
from ytweb.db.session import make_engine, make_session_factory


def reset() -> int:
    settings = load_web_settings()
    engine = make_engine(settings.database_url)
    try:
        with make_session_factory(engine)() as db:
            removed = admin_account.reset_admin(db)
            audit.record(db, actor="cli", action="admin.reset", target_type="admin", detail={"removed": removed}, now=utcnow())
            db.commit()
    finally:
        engine.dispose()
    print(f"관리자 계정을 초기화했습니다(삭제된 계정 {removed}개). 브라우저에서 새 관리자 계정을 만드세요.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["reset"]:
        return reset()
    print("사용법: python -m ytweb.admin_cli reset", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
