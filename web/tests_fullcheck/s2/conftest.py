import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))
from tests.conftest import *  # noqa: F401,F403
from tests.verify_m23.conftest import *  # noqa: F401,F403
