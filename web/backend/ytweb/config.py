"""환경변수·비밀 파일에서 읽는 웹 설정. 비밀값은 환경변수 평문이 아니라 `*_FILE` 경로로 받는다(D-06)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MODES = ("demo",)  # M1은 데모 모드뿐. 'live'는 M3에서 추가한다(DEC-038, WEB_DESIGN §0).


def _read_secret(file_var: str, plain_var: str | None = None) -> str | None:
    path = os.environ.get(file_var)
    if path:
        return Path(path).read_text(encoding="utf-8").strip()
    return os.environ.get(plain_var) if plain_var else None


@dataclass(frozen=True)
class WebSettings:
    mode: str
    database_url: str
    base_dir: Path                      # ytitle 정책 설정(config/settings.yaml)을 찾는 프로젝트 기준 폴더
    secrets_dir: Path                   # 승인·감사 HMAC 키 등을 두는 폴더(명명 볼륨, 이미지 밖)
    allowed_hosts: tuple[str, ...]
    port: int = 8080
    session_ttl_hours: int = 12
    enable_docs: bool = False           # /docs 는 개발 프로필에서만
    log_json: bool = True
    extra: dict = field(default_factory=dict)


def load_web_settings(env: dict[str, str] | None = None) -> WebSettings:
    e = dict(os.environ if env is None else env)
    mode = e.get("YTWEB_MODE", "demo")
    if mode not in MODES:
        raise ValueError(f"지원하지 않는 YTWEB_MODE 입니다: {mode!r} (M1은 demo 만 지원)")
    port = int(e.get("YTWEB_PORT", "8080"))
    hosts = tuple(h.strip() for h in e.get("YTWEB_ALLOWED_HOSTS", f"127.0.0.1:{port},localhost:{port}").split(",") if h.strip())
    url = e.get("YTWEB_DATABASE_URL")
    if not url:
        pw = _read_secret("YTWEB_DB_PASSWORD_FILE") if "YTWEB_DB_PASSWORD_FILE" in e else None
        if pw is None:
            raise ValueError("YTWEB_DATABASE_URL 또는 YTWEB_DB_PASSWORD_FILE 이 필요합니다.")
        user = e.get("YTWEB_DB_USER", "ytweb_app")
        host = e.get("YTWEB_DB_HOST", "db")
        name = e.get("YTWEB_DB_NAME", "ytweb")
        from urllib.parse import quote
        url = f"postgresql+psycopg://{quote(user)}:{quote(pw)}@{host}:5432/{quote(name)}"
    return WebSettings(
        mode=mode,
        database_url=url,
        base_dir=Path(e.get("YTWEB_BASE_DIR", "/app")),
        secrets_dir=Path(e.get("YTWEB_SECRETS_DIR", "/var/lib/ytweb/secrets")),
        allowed_hosts=hosts,
        port=port,
        session_ttl_hours=int(e.get("YTWEB_SESSION_TTL_HOURS", "12")),
        enable_docs=e.get("YTWEB_ENABLE_DOCS", "0") == "1",
        log_json=e.get("YTWEB_LOG_JSON", "1") == "1",
    )
