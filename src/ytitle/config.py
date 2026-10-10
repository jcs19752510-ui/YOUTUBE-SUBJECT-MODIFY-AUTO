"""설정 로더. 정책 값은 YAML, 경로·비밀 위치는 .env(ADR-010).

`live.enable_live`와 `live.live_allowlist`는 settings.local.yaml 에서만 인식한다(SEC-001, SEC-012).
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import yaml
from dotenv import dotenv_values

from ytitle.errors import ConfigError
from ytitle.platform_utils import default_token_dir

DEFAULTS: dict[str, Any] = {
    "quota": {"daily_limit_units": 6000, "warn_ratio": 0.8, "update_cost": 50, "read_cost": 1, "analytics_cost": 1},
    "cadence": {"min_interval_hours": 72, "max_changes_per_video": 3, "min_impressions_before_rechange": 1000, "max_live_changes_per_day": 3},
    "validation": {"key_phrase_chars": 20, "recommended_max_chars": 40, "hard_max_chars": 100, "warn_match_ratio": 0.5, "block_match_ratio": 0.25},
    "sequential_mode": {"enabled": False, "evaluation_window_days": 14},
    "retention": {"logs_days": 365, "history_days": 365},
    "live": {"enable_live": False, "live_allowlist": []},
    "approval": {"ttl_hours": 24},
    "exclusions": {"shorts_max_seconds": 180},
}


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    config_dir: Path
    data_dir: Path
    token_dir: Path
    client_secret_path: Path
    candidates_dir: Path
    approvals_dir: Path
    db_path: Path
    daily_limit_units: int
    warn_ratio: float
    update_cost: int
    read_cost: int
    analytics_cost: int
    min_interval_hours: int
    max_changes_per_video: int
    min_impressions_before_rechange: int
    max_live_changes_per_day: int
    key_phrase_chars: int
    recommended_max_chars: int
    hard_max_chars: int
    warn_match_ratio: float
    block_match_ratio: float
    sequential_enabled: bool
    evaluation_window_days: int
    logs_days: int
    history_days: int
    enable_live: bool
    live_allowlist: tuple[str, ...]
    approval_ttl_hours: int
    shorts_max_seconds: int
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _deep_merge(base: dict, over: Mapping) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, Mapping) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"설정 파일을 읽을 수 없습니다: {path.name}", "YAML 문법(들여쓰기, 따옴표)을 확인하세요.", cause=type(exc).__name__) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"설정 파일의 최상위가 항목 목록이 아닙니다: {path.name}", "파일 맨 위가 `quota:` 같은 항목 이름으로 시작해야 합니다.")
    return data


def _num(cfg: dict, section: str, key: str, kind, lo, hi=None):
    value = cfg[section][key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (kind is int and isinstance(value, float) and value != int(value)):
        raise ConfigError(f"설정 값이 숫자가 아닙니다: {section}.{key} = {value!r}", f"config/settings.yaml 또는 settings.local.yaml의 {section}.{key}를 숫자로 고치세요.")
    value = kind(value)
    if value < lo or (hi is not None and value > hi):
        rng = f"{lo} 이상" + (f" {hi} 이하" if hi is not None else "")
        raise ConfigError(f"설정 값이 허용 범위를 벗어났습니다: {section}.{key} = {value} ({rng} 필요)", "값을 범위 안으로 고치세요.")
    return value


def _bool(cfg: dict, section: str, key: str) -> bool:
    value = cfg[section][key]
    if not isinstance(value, bool):
        raise ConfigError(f"설정 값은 true 또는 false여야 합니다: {section}.{key} = {value!r}", "따옴표 없이 true/false로 쓰세요.")
    return value


def _resolve(raw: str | None, default: Path, base: Path) -> Path:
    if not raw:
        return default
    p = Path(os.path.expandvars(os.path.expanduser(raw)))
    return p if p.is_absolute() else base / p


def load_settings(base_dir: Path | str, env: Mapping[str, str] | None = None) -> Settings:
    base = Path(base_dir).resolve()
    cfg_dir = base / "config"
    warnings: list[str] = []
    env_map = dict(dotenv_values(base / ".env")) if (base / ".env").exists() else {}
    env_map.update({k: v for k, v in (env if env is not None else os.environ).items() if k.startswith("YT_")})

    base_yaml = _read_yaml(cfg_dir / "settings.yaml")
    local_yaml = _read_yaml(cfg_dir / "settings.local.yaml")
    live_in_base = base_yaml.pop("live", None)
    if live_in_base and live_in_base != DEFAULTS["live"]:
        warnings.append("settings.yaml의 live 항목은 무시했습니다. enable_live와 live_allowlist는 settings.local.yaml에서만 적용됩니다.")
    cfg = _deep_merge(DEFAULTS, base_yaml)
    cfg = _deep_merge(cfg, local_yaml)

    for section in DEFAULTS:
        if not isinstance(cfg[section], dict):
            raise ConfigError(f"설정 항목 형식이 잘못되었습니다: {section}", "해당 항목 아래에 `키: 값` 형태로 작성하세요.")

    allow = cfg["live"]["live_allowlist"]
    if not isinstance(allow, list) or not all(isinstance(x, str) for x in allow):
        raise ConfigError("live_allowlist는 영상 ID 문자열 목록이어야 합니다.", "예: live_allowlist: [\"abc123DEF45\"]")

    s = Settings(
        base_dir=base,
        config_dir=cfg_dir,
        data_dir=_resolve(env_map.get("YT_DATA_DIR"), base / "data", base),
        token_dir=_resolve(env_map.get("YT_TOKEN_DIR"), default_token_dir(), base),
        client_secret_path=_resolve(env_map.get("YT_CLIENT_SECRET_PATH"), base / "secrets" / "client_secret.json", base),
        candidates_dir=base / "candidates",
        approvals_dir=base / "approvals",
        db_path=_resolve(env_map.get("YT_DATA_DIR"), base / "data", base) / "ytitle.sqlite3",
        daily_limit_units=_num(cfg, "quota", "daily_limit_units", int, 0),
        warn_ratio=_num(cfg, "quota", "warn_ratio", float, 0.0, 1.0),
        update_cost=_num(cfg, "quota", "update_cost", int, 0),
        read_cost=_num(cfg, "quota", "read_cost", int, 0),
        analytics_cost=_num(cfg, "quota", "analytics_cost", int, 0),
        min_interval_hours=_num(cfg, "cadence", "min_interval_hours", int, 0),
        max_changes_per_video=_num(cfg, "cadence", "max_changes_per_video", int, 1),
        min_impressions_before_rechange=_num(cfg, "cadence", "min_impressions_before_rechange", int, 0),
        max_live_changes_per_day=_num(cfg, "cadence", "max_live_changes_per_day", int, 1),
        key_phrase_chars=_num(cfg, "validation", "key_phrase_chars", int, 1),
        recommended_max_chars=_num(cfg, "validation", "recommended_max_chars", int, 1),
        hard_max_chars=_num(cfg, "validation", "hard_max_chars", int, 1, 100),
        warn_match_ratio=_num(cfg, "validation", "warn_match_ratio", float, 0.0, 1.0),
        block_match_ratio=_num(cfg, "validation", "block_match_ratio", float, 0.0, 1.0),
        sequential_enabled=_bool(cfg, "sequential_mode", "enabled"),
        evaluation_window_days=_num(cfg, "sequential_mode", "evaluation_window_days", int, 1),
        logs_days=_num(cfg, "retention", "logs_days", int, 1),
        history_days=_num(cfg, "retention", "history_days", int, 1),
        enable_live=_bool(cfg, "live", "enable_live"),
        live_allowlist=tuple(allow),
        approval_ttl_hours=_num(cfg, "approval", "ttl_hours", int, 1),
        shorts_max_seconds=_num(cfg, "exclusions", "shorts_max_seconds", int, 1),
        warnings=tuple(warnings),
    )
    if s.key_phrase_chars > s.recommended_max_chars or s.recommended_max_chars > s.hard_max_chars:
        raise ConfigError("제목 길이 설정의 순서가 맞지 않습니다(핵심어 ≤ 권장 ≤ 상한).", "validation 항목의 세 값을 작은 것부터 순서대로 고치세요.")
    if s.block_match_ratio > s.warn_match_ratio:
        raise ConfigError("일치율 설정이 맞지 않습니다(차단 기준이 경고 기준보다 클 수 없음).", "block_match_ratio를 warn_match_ratio 이하로 낮추세요.")
    return s
