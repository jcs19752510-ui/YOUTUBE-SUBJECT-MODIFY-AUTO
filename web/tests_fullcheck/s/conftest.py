import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
from tests.conftest import *  # noqa: F401,F403  (공용 픽스처 재사용)
