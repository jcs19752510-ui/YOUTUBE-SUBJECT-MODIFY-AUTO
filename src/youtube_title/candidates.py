"""제목 후보 파일 읽기와 입력 검증(FR-001, SEC-011, SEC-016). 후보 파일은 신뢰할 수 없는 외부 입력이다."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from youtube_title.errors import InputError

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
MAX_BYTES = 256 * 1024
MAX_CANDIDATES = 20
TOPICS = ("life", "health", "finance")


@dataclass(frozen=True)
class Candidate:
    title: str
    evidence: str


@dataclass(frozen=True)
class CandidateFile:
    video_id: str
    current_title: str
    topic: str | None
    summary: str
    source: str
    description_excerpt: str | None
    candidates: tuple[Candidate, ...]
    sha256: str
    file_name: str


def _str_field(obj: dict, key: str, errors: list[str], *, required=True, max_len=2000, allow_empty=False) -> str | None:
    value = obj.get(key)
    if value is None:
        if required:
            errors.append(f"`{key}` 항목이 없습니다.")
        return None
    if not isinstance(value, str):
        errors.append(f"`{key}`는 글자(문자열)여야 합니다.")
        return None
    if not allow_empty and not value.strip():
        errors.append(f"`{key}`가 비어 있습니다.")
        return None
    if len(value) > max_len:
        errors.append(f"`{key}`가 너무 깁니다({max_len}자 이하).")
        return None
    return value


def resolve_candidate_path(path: Path | str, candidates_dir: Path) -> Path:
    """후보 폴더 안의 파일만 허용한다(경로 조작 방지)."""
    base = Path(candidates_dir).resolve()
    p = Path(path)
    p = (p if p.is_absolute() else Path.cwd() / p).resolve()
    if base != p.parent:
        raise InputError("후보 파일은 candidates 폴더 바로 아래에 있어야 합니다.", f"`{base}` 폴더 안에 `영상ID.json` 이름으로 저장하세요.")
    return p


def load_candidate_file(path: Path | str, candidates_dir: Path) -> CandidateFile:
    p = resolve_candidate_path(path, candidates_dir)
    if p.suffix.lower() != ".json" or not VIDEO_ID_RE.match(p.stem):
        raise InputError(f"후보 파일 이름이 올바르지 않습니다: {p.name}", "영상 ID(11자: 영문·숫자·-·_)에 .json을 붙인 이름이어야 합니다. 예: abc123DEF45.json")
    if not p.exists():
        raise InputError(f"후보 파일을 찾을 수 없습니다: {p.name}", f"`{p.parent}` 폴더에 파일이 있는지 확인하세요.")
    size = p.stat().st_size
    if size > MAX_BYTES:
        raise InputError(f"후보 파일이 너무 큽니다({size // 1024}KB > {MAX_BYTES // 1024}KB).", "후보와 요약을 줄여 다시 저장하세요.")
    raw = p.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8-sig"))  # 윈도 메모장·PowerShell이 붙이는 BOM도 허용
    except UnicodeDecodeError as exc:
        raise InputError("후보 파일이 UTF-8이 아닙니다.", "메모장에서 '다른 이름으로 저장' → 인코딩을 UTF-8로 선택해 저장하세요.") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"후보 파일의 JSON 문법이 틀렸습니다({exc.lineno}줄 {exc.colno}칸).", "따옴표·쉼표·괄호를 확인하세요.") from exc
    if not isinstance(data, dict):
        raise InputError("후보 파일의 맨 바깥이 `{ }` 객체가 아닙니다.", "예시 형식을 확인하세요(docs/yt/DESIGN.md EVT-201).")
    errors: list[str] = []
    video_id = _str_field(data, "video_id", errors, max_len=11)
    if video_id is not None and (not VIDEO_ID_RE.match(video_id) or video_id != p.stem):
        errors.append("`video_id`가 올바르지 않거나 파일 이름과 다릅니다.")
    current = _str_field(data, "current_title", errors, max_len=300)
    topic = data.get("topic")
    if topic is not None and topic not in TOPICS:
        errors.append("`topic`은 life, health, finance 중 하나여야 합니다(비우면 엄격 모드).")
        topic = None
    summary = _str_field(data, "summary", errors, max_len=2000)
    source = _str_field(data, "source", errors, max_len=40)
    excerpt = _str_field(data, "description_excerpt", errors, required=False, max_len=2000, allow_empty=True)
    cands: list[Candidate] = []
    raw_c = data.get("candidates")
    if not isinstance(raw_c, list) or not raw_c:
        errors.append("`candidates`는 비어 있지 않은 목록이어야 합니다.")
    elif len(raw_c) > MAX_CANDIDATES:
        errors.append(f"후보는 최대 {MAX_CANDIDATES}개입니다({len(raw_c)}개).")
    else:
        for i, c in enumerate(raw_c, 1):
            if not isinstance(c, dict):
                errors.append(f"후보 {i}번이 `{{title, evidence}}` 형태가 아닙니다.")
                continue
            sub: list[str] = []
            t = _str_field(c, "title", sub, max_len=300)
            e = _str_field(c, "evidence", sub, max_len=500)
            errors.extend(f"후보 {i}번: {s}" for s in sub)
            if t is not None and e is not None:
                cands.append(Candidate(t, e))
    if errors:
        raise InputError("후보 파일에 고칠 곳이 있습니다:\n  - " + "\n  - ".join(errors), "위 항목을 고친 뒤 다시 실행하세요.")
    return CandidateFile(video_id, current, topic, summary, source, excerpt or None, tuple(cands), hashlib.sha256(raw).hexdigest(), p.name)


def list_candidate_files(candidates_dir: Path) -> list[Path]:
    d = Path(candidates_dir)
    return sorted(p for p in d.glob("*.json") if p.is_file()) if d.exists() else []
