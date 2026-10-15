"""환경변수·비밀 파일에서 읽는 웹 설정. 비밀값은 환경변수 평문이 아니라 `*_FILE` 경로로 받는다(D-06)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

MODES = ("demo",)  # M1은 데모 모드뿐. 'live'는 M3에서 추가한다(DEC-038, WEB_DESIGN §0).


def _read_secret(env: dict[str, str], file_var: str, plain_var: str | None = None) -> str | None:
    path = env.get(file_var)
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return env.get(plain_var) if plain_var else None


def _non_negative_int(env: dict[str, str], name: str, default: int) -> int:
    value = int(env.get(name, str(default)))
    if value < 0:
        raise ValueError(f"{name} 는 0 이상의 정수여야 합니다: {value}")
    return value


@dataclass(frozen=True)
class WebSettings:
    mode: str
    database_url: str
    base_dir: Path                      # 유튜브 제목 코어의 정책 설정(config/settings.yaml)을 찾는 프로젝트 기준 폴더
    secrets_dir: Path                   # 승인 HMAC 키·구글 토큰 등을 두는 폴더(명명 볼륨, 이미지 밖). 감사 기록에는 키가 없다(해시 체인만)
    allowed_hosts: tuple[str, ...]
    port: int = 8080
    session_ttl_hours: int = 12
    session_idle_minutes: int = 30      # 마지막 사용 뒤 이 시간이 지나면 세션 만료(0 이면 유휴 만료 끔, 절대 만료 session_ttl_hours 만 적용)
    admin_login: bool = False           # True 면 아이디·비밀번호 로그인이 필수(익명 세션 발급 금지, DEC-055). compose 기본은 켬. 계정은 웹의 최초 설정 화면에서 만든다(DEC-056)
    enable_docs: bool = False           # /docs 는 개발 프로필에서만
    log_json: bool = True
    extra: dict = field(default_factory=dict)

    @property
    def session_idle_timeout(self) -> timedelta | None:
        return timedelta(minutes=self.session_idle_minutes) if self.session_idle_minutes > 0 else None


def load_web_settings(env: dict[str, str] | None = None) -> WebSettings:
    e = dict(os.environ if env is None else env)
    mode = e.get("YTWEB_MODE", "demo")
    if mode not in MODES:
        raise ValueError(f"지원하지 않는 YTWEB_MODE 입니다: {mode!r} (M1은 demo 만 지원)")
    port = int(e.get("YTWEB_PORT", "8080"))
    hosts = tuple(h.strip() for h in e.get("YTWEB_ALLOWED_HOSTS", f"127.0.0.1:{port},localhost:{port}").split(",") if h.strip())
    url = e.get("YTWEB_DATABASE_URL")
    if not url:
        pw = _read_secret(e, "YTWEB_DB_PASSWORD_FILE")
        if pw is None:
            raise ValueError("YTWEB_DATABASE_URL 또는 YTWEB_DB_PASSWORD_FILE 이 필요합니다.")
        user = e.get("YTWEB_DB_USER", "ytweb_app")
        host = e.get("YTWEB_DB_HOST", "db")
        name = e.get("YTWEB_DB_NAME", "ytweb")
        from sqlalchemy.engine import URL
        url = URL.create("postgresql+psycopg", username=user, password=pw, host=host, port=5432, database=name).render_as_string(hide_password=False)
    admin_login = e.get("YTWEB_ADMIN_LOGIN", "0") == "1"
    return WebSettings(
        mode=mode,
        database_url=url,
        base_dir=Path(e.get("YTWEB_BASE_DIR", "/app")),
        secrets_dir=Path(e.get("YTWEB_SECRETS_DIR", "/var/lib/ytweb/secrets")),
        allowed_hosts=hosts,
        port=port,
        session_ttl_hours=int(e.get("YTWEB_SESSION_TTL_HOURS", "12")),
        session_idle_minutes=_non_negative_int(e, "YTWEB_SESSION_IDLE_MINUTES", 60 if admin_login else 30),
        admin_login=admin_login,
        enable_docs=e.get("YTWEB_ENABLE_DOCS", "0") == "1",
        log_json=e.get("YTWEB_LOG_JSON", "1") == "1",
    )
