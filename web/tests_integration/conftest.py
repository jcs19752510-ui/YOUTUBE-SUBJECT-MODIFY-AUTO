"""7단계 통합 시험 공통 설정. 스택(compose 프로젝트 harness-tmp-int)은 미리 떠 있어야 한다(README/결과서 3절)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import itlib  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: 수 분 걸리는 시험(속도 제한 때문에 일부러 천천히 반복)")
    config.addinivalue_line("markers", "destructive: DB 를 초기화하거나 컨테이너를 재시작한다")


@pytest.fixture(scope="session", autouse=True)
def _stack_ready():
    if not os.environ.get("IT_STACK_DIR") or not os.environ.get("DOCKER_HOST"):
        pytest.exit("IT_STACK_DIR, DOCKER_HOST 환경변수가 필요합니다(결과서 3절).", returncode=3)
    itlib.wait_healthy(120)


_OWNER: dict = {}


@pytest.fixture()
def owner():
    """로그인된 소유자 클라이언트. 시험마다 새로 로그인하면 세션 발급 속도 제한(분당 10, 전역)에 걸리므로 세션을 재사용하고,
    서버가 세션을 잃었을 때(DB 초기화·PIN 변경 등)만 다시 로그인한다."""
    a = _OWNER.get("api")
    if a is not None:
        r = a.get("/api/v1/auth/me")
        if r.status_code == 200 and r.json().get("authenticated"):
            a.csrf = r.json()["csrf_token"]
            return a
        a.close()
    a = itlib.Api()
    r = a.login()
    assert r.status_code == 200, r.text
    _OWNER["api"] = a
    return a


@pytest.fixture(scope="module")
def owner_m():
    a = itlib.Api()
    r = a.login()
    assert r.status_code == 200, r.text
    yield a
    a.close()


@pytest.fixture()
def fresh_demo():
    """빈 DB → 로그인 → 데모 영상 불러오기까지 끝낸 클라이언트."""
    itlib.reset_demo_db()
    a = itlib.Api()
    assert a.login().status_code == 200
    j = a.sync_demo()
    assert j["status"] == "succeeded"
    yield a
    a.close()
