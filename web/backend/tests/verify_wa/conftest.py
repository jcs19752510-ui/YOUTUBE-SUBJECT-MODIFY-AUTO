"""verify_wa 전용 픽스처. 부모 tests/conftest.py 의 app/client/clock/engine 등을 그대로 쓴다."""
from __future__ import annotations

import io
import logging

import pytest

from ytweb.core.logsetup import JsonFormatter


@pytest.fixture
def log_capture():
    """`ytweb` 로거 트리에 JSON 포매터 핸들러를 붙여 로그 원문을 문자열로 모은다(앱이 쓰는 실제 포매터)."""
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("ytweb")
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield buf
    logger.removeHandler(handler)
    logger.setLevel(old_level)
