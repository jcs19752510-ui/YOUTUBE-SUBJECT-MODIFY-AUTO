"""도메인 공용 도구: 정책 묶음(Env), 단계 실패 예외, 시간 경계, 입력 정리."""
from __future__ import annotations

import functools
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy.sql import Select
from ytitle.banned_terms import Dictionary, load_dictionary
from ytitle.config import Settings, load_settings
from ytitle.textsafe import sanitize_for_display

from ytweb.config import WebSettings, load_web_settings
from ytweb.core.errors import ProblemError

KST = timezone(timedelta(hours=9))  # 한국은 서머타임이 없어 고정 오프셋과 Asia/Seoul 이 같다
MAX_APPROVER_CHARS = 40
MAX_BATCH_ITEMS = 50
MAX_PAGE_SIZE = 200
VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"


@dataclass(frozen=True)
class Env:
    """도메인 서비스가 읽는 정책·사전·비밀 폴더 묶음. 요청/틱마다 만들어도 가볍다(사전은 파일 변경 때만 다시 읽음)."""

    policy: Settings
    dictionary: Dictionary
    secrets_dir: Path

    @classmethod
    def build(cls, policy: Settings, web: WebSettings) -> "Env":
        return cls(policy, load_dictionary_cached(policy.config_dir / "banned_terms.yaml"), web.secrets_dir)


@functools.lru_cache(maxsize=8)
def _load_dictionary_at(path: str, mtime_ns: int) -> Dictionary:
    return load_dictionary(Path(path))


def load_dictionary_cached(path: Path) -> Dictionary:
    p = Path(path)
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        mtime = -1  # 없는 파일은 load_dictionary 가 한국어 ConfigError 를 낸다(캐시되지 않음)
    return _load_dictionary_at(str(p), mtime)


_default_env: Env | None = None


def default_env() -> Env:
    """워커처럼 요청 컨텍스트가 없을 때 환경변수에서 만든 기본 Env. 한 번만 만든다."""
    global _default_env
    if _default_env is None:
        web = load_web_settings()
        _default_env = Env.build(load_settings(web.base_dir), web)
    return _default_env


def set_default_env(env: Env | None) -> None:
    """테스트·특수 기동에서 기본 Env 를 지정한다."""
    global _default_env
    _default_env = env


class StepFailure(Exception):
    """배치 항목 한 건의 처리 단계 실패. 항목만 skipped/failed 로 끝내고 다른 항목은 계속한다."""

    def __init__(self, code: str, message: str, *, kind: str = "skipped") -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.kind = kind  # "skipped"(아무것도 바꾸지 않음) | "failed"(시도했으나 실패)


def kst_day_bounds(day: date) -> tuple[datetime, datetime]:
    """KST 날짜 하루의 [시작, 끝)을 UTC 로 돌려준다."""
    start = datetime.combine(day, time.min, tzinfo=KST).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def clean_approver(value: object) -> str:
    """승인자 이름: 비어 있지 않고 40자 이하, 제어 문자 없음(화면·감사 로그 위조 방지)."""
    if not isinstance(value, str) or not value.strip():
        raise ProblemError(422, "approver_required", "승인자 이름이 비어 있습니다.", hint="승인하는 사람의 이름을 입력하세요.")
    name = value.strip()
    if len(name) > MAX_APPROVER_CHARS or sanitize_for_display(name) != name:
        raise ProblemError(422, "approver_invalid", f"승인자 이름이 올바르지 않습니다(제어 문자 없이 {MAX_APPROVER_CHARS}자 이하).", hint="짧고 평범한 글자로 이름을 다시 입력하세요.")
    return name


def lock_rows(stmt: Select, session) -> Select:
    """PostgreSQL 에서만 행 잠금(FOR UPDATE)을 건다. SQLite 는 단일 쓰기 잠금이라 필요 없다."""
    if session.get_bind().dialect.name == "postgresql":
        return stmt.with_for_update()
    return stmt


def single_line(text: str, max_len: int) -> str:
    cleaned = " ".join(sanitize_for_display(unicodedata.normalize("NFC", text)).split())
    return cleaned[:max_len]


def clamp_page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(max(1, page_size), MAX_PAGE_SIZE)
