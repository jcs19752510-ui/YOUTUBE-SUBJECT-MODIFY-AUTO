"""관리자 계정 운영 명령(DEC-058). 비밀번호 원문은 파일·환경 변수·명령줄 인수 어디에도 남기지 않는다.

  python -m ytweb.admin_cli register   아이디 입력 + 비밀번호를 화면에 보이지 않게 두 번 입력 → DB 에 해시만 저장
  python -m ytweb.admin_cli status     REGISTERED 또는 NONE 한 줄만 출력(값 없음)

register 는 사람이 직접 입력하는 터미널(TTY)에서만 실행된다(파이프·인수로 비밀번호를 넘기는 경로 차단).
"""
from __future__ import annotations

import getpass
import sys

from ytweb.config import load_web_settings
from ytweb.core import admin_account, audit
from ytweb.core.clock import utcnow
from ytweb.db.session import make_engine, make_session_factory


def _session_factory():
    engine = make_engine(load_web_settings().database_url)
    return engine, make_session_factory(engine)


def register() -> int:
    if not sys.stdin.isatty():
        print("오류: 사람이 직접 입력하는 터미널에서만 실행할 수 있습니다(비밀번호를 파이프·인수로 넘기지 마세요).", file=sys.stderr)
        return 2
    login_id = input("관리자 아이디(영문·숫자 4~20자): ").strip()
    password = getpass.getpass("비밀번호(8~64자, 입력해도 화면에 보이지 않습니다): ")
    again = getpass.getpass("비밀번호 확인: ")
    if password != again:
        print("오류: 두 비밀번호가 같지 않습니다. 다시 실행하세요.", file=sys.stderr)
        return 1
    reason = admin_account.validate_credentials_format(login_id, password)
    if reason:
        print(f"오류: {reason} 다시 실행하세요.", file=sys.stderr)
        return 1
    engine, factory = _session_factory()
    try:
        with factory() as db:
            status = admin_account.register_admin(db, login_id, password, now=utcnow())
            audit.record(db, actor="cli", action="admin.register", target_type="admin", detail={"result": status}, now=utcnow())
            db.commit()
    finally:
        engine.dispose()
    print("관리자 계정을 등록했습니다." if status == "created" else "관리자 계정을 새 값으로 바꿨습니다(이전 로그인은 모두 끝났습니다).")
    print("브라우저에서 http://127.0.0.1:8080 에 접속해 로그인하세요.")
    return 0


def status() -> int:
    engine, factory = _session_factory()
    try:
        with factory() as db:
            print("REGISTERED" if admin_account.has_admin(db) else "NONE")
    finally:
        engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["register"]:
        return register()
    if args == ["status"]:
        return status()
    print("사용법: python -m ytweb.admin_cli register | status", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
