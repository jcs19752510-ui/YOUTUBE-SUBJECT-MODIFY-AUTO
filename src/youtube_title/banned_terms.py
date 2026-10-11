"""금칙어 사전 읽기(FR-003, SEC-016, SEC-017). yaml.safe_load만 사용한다."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from youtube_title.errors import ConfigError
from youtube_title.textsafe import normalize_for_match

TYPE_LABELS = {"fear": "공포 조장", "medical": "의료 효능 단정", "finance": "금융 수익·원금 보장", "impersonation": "공공기관·뉴스 사칭 오인", "superlative": "근거 없는 최상급·100% 단정"}
WARNING_DEFAULTS = {"exclamation_max": 1, "emoji_max": 2, "symbol_run_min": 3, "caps_ratio_max": 0.6, "special_ratio_max": 0.3}


@dataclass(frozen=True)
class TermType:
    name: str
    severity: str
    terms: tuple[tuple[str, str], ...]          # (원문, 정규화된 형태)
    patterns: tuple[re.Pattern, ...]

    @property
    def label(self) -> str:
        return TYPE_LABELS.get(self.name, self.name)


@dataclass(frozen=True)
class Dictionary:
    version: str
    sha: str
    types: tuple[TermType, ...]
    warning: dict
    strict_keywords: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def short_hash(self) -> str:
        return self.sha[:8]


def _err(msg: str) -> ConfigError:
    return ConfigError(f"금칙어 사전 오류: {msg}", "config/banned_terms.yaml을 고친 뒤 다시 실행하세요.")


def load_dictionary(path: Path | str) -> Dictionary:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"금칙어 사전을 찾을 수 없습니다: {p.name}", "config/banned_terms.yaml 파일이 있는지 확인하세요.")
    try:
        raw_text = p.read_text(encoding="utf-8")
        data = yaml.safe_load(raw_text)
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        raise ConfigError("금칙어 사전을 읽을 수 없습니다.", "config/banned_terms.yaml의 YAML 문법(들여쓰기·따옴표)과 UTF-8 저장 여부를 확인하세요.", cause=type(exc).__name__) from exc
    if not isinstance(data, dict) or not isinstance(data.get("types"), dict) or not data["types"]:
        raise _err("`types` 항목이 없거나 비어 있습니다.")
    types: list[TermType] = []
    for name, spec in data["types"].items():
        if not isinstance(spec, dict):
            raise _err(f"`{name}` 형식이 잘못되었습니다.")
        severity = spec.get("severity", "block")
        if severity not in ("block", "warn"):
            raise _err(f"`{name}`의 severity는 block 또는 warn이어야 합니다.")
        terms = []
        for t in spec.get("terms") or []:
            if not isinstance(t, str) or len(normalize_for_match(t)) < 2:
                raise _err(f"`{name}`의 금칙어 `{t}`는 글자 2개 이상의 문자열이어야 합니다(너무 짧으면 정상 제목까지 막습니다).")
            terms.append((t, normalize_for_match(t)))
        pats = []
        for pt in spec.get("patterns") or []:
            if not isinstance(pt, str) or len(pt) > 100:
                raise _err(f"`{name}`의 패턴은 100자 이하 문자열이어야 합니다.")
            try:
                pats.append(re.compile(pt))
            except re.error as exc:
                raise _err(f"`{name}`의 패턴 `{pt}`가 올바른 정규식이 아닙니다.") from exc
        types.append(TermType(name, severity, tuple(terms), tuple(pats)))
    warning = dict(WARNING_DEFAULTS)
    w = data.get("warning") or {}
    if not isinstance(w, dict) or any(k not in WARNING_DEFAULTS or isinstance(v, bool) or not isinstance(v, (int, float)) for k, v in w.items()):
        raise _err("`warning` 항목은 알려진 키와 숫자 값만 허용합니다.")
    warning.update(w)
    kws = []
    for k in data.get("strict_keywords") or []:
        if not isinstance(k, str) or len(normalize_for_match(k)) < 2:
            raise _err(f"`strict_keywords`의 `{k}`는 글자 2개 이상의 문자열이어야 합니다.")
        kws.append((k, normalize_for_match(k)))
    canon = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return Dictionary(str(data.get("version", "?")), hashlib.sha256(canon.encode("utf-8")).hexdigest(), tuple(types), warning, tuple(kws))
