"""JSON 로그 + 비밀 마스킹. 로그에는 요청 본문·헤더·쿼리 문자열을 넣지 않는다."""
from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

_SENSITIVE_KEY = r"(?:ytw_session|csrf[-_ ]?token|x-csrf-token|authorization|set-cookie|cookie|passw(?:or)?d|secret|token|pin|api[-_]?key)"
_KV_RE = re.compile(rf"(?i)({_SENSITIVE_KEY}[\"']?\s*[:=]\s*)([\"']?)[^\s\"',;&}}]+")
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_URL_CRED_RE = re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+@")
_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{40,}\b")
_SENSITIVE_FIELD = re.compile(rf"(?i){_SENSITIVE_KEY}")

MASK = "***"


def mask_secrets(text: str) -> str:
    text = _KV_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)
    text = _BEARER_RE.sub(f"Bearer {MASK}", text)
    text = _URL_CRED_RE.sub(f"{MASK}:{MASK}@", text)
    return _LONG_TOKEN_RE.sub(MASK, text)


def _mask_value(key: str, value):
    if _SENSITIVE_FIELD.search(key):
        return MASK
    if isinstance(value, str):
        return mask_secrets(value)
    if isinstance(value, dict):
        return {k: _mask_value(str(k), v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mask_value(key, v) for v in value]
    return value


_STD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": mask_secrets(record.getMessage()),
        }
        for k, v in record.__dict__.items():
            if k not in _STD_ATTRS and not k.startswith("_"):
                data[k] = _mask_value(k, v)
        if record.exc_info:
            data["exc"] = mask_secrets(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False, default=str)


class MaskingTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return mask_secrets(super().format(record))


def setup_logging(*, json_format: bool = True, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("ytweb")
    for h in list(logger.handlers):
        if getattr(h, "_ytweb", False):
            logger.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    handler._ytweb = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter() if json_format else MaskingTextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
