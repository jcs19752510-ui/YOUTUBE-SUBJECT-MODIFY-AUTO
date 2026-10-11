import io
from datetime import datetime, timezone
from pathlib import Path

import pytest

from youtube_title.timeutil import FixedClock


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path_factory, monkeypatch):
    """테스트가 실수로 저장소 폴더에 data/ 등을 만들지 못하게 작업 폴더를 임시 폴더로 옮긴다."""
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    return tmp_path


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc))


class Streams:
    def __init__(self) -> None:
        self.out, self.err = io.StringIO(), io.StringIO()


@pytest.fixture
def streams() -> Streams:
    return Streams()
