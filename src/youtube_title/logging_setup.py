"""로깅과 비밀 마스킹(SEC-008, NFR-011). 로그·예외 메시지 모두 같은 마스킹을 거친다."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

_PATTERNS = [
    re.compile(r"ya29\.[A-Za-z0-9_\-\.]+"),
    re.compile(r"1//[A-Za-z0-9_\-]{20,}"),
    re.compile(r"GOCSPX-[A-Za-z0-9_\-]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.=]+"),
    re.compile(r"(?i)(\"?(?:client_secret|refresh_token|access_token|id_token|api_key)\"?\s*[:=]\s*)\"?[^\s\",}]+\"?"),
    re.compile(r"[A-Za-z0-9_\-]{40,}"),
]
MASK = "[가려짐]"


def mask(text: str) -> str:
    out = str(text)
    for pat in _PATTERNS[:4]:
        out = pat.sub(MASK, out)
    out = _PATTERNS[4].sub(lambda m: m.group(1) + MASK, out)
    out = _PATTERNS[5].sub(MASK, out)
    return out


class MaskingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return mask(super().format(record))


def setup_logging(data_dir: Path, run_id: str, *, level: int = logging.INFO, console: bool = False) -> logging.Logger:
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("youtube_title")
    logger.setLevel(level)
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    fmt = MaskingFormatter("%(asctime)s %(levelname)s [" + run_id + "] %(message)s")
    fh = RotatingFileHandler(log_dir / "youtube-title.log", maxBytes=5 * 1024 * 1024, backupCount=10, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.setLevel(logging.WARNING)
        logger.addHandler(ch)
    logger.propagate = False
    return logger
