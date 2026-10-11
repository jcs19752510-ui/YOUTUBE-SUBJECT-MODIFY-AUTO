"""6단계 독립 검증(W-BE-B) 픽스처. 구현자 tests/domain 의 픽스처를 재사용하고, 시험 논리는 이 폴더에서 새로 쓴다."""
from __future__ import annotations

from tests.domain.conftest import (  # noqa: F401
    DOMAIN_ROUTERS, SEED_COUNT, _reset_default_env, api, csrf, dapp, env, env_free, gw, hdr, policy, seeded,
)


import pytest  # noqa: E402

from ytweb.domain.seed import seed_demo  # noqa: E402


@pytest.fixture
def seeded200(db, clock, env):  # noqa: F811
    """200개 전체 시드(50건 배치 경계 시험용)."""
    seed_demo(db, clock(), env.policy, count=200)
    db.commit()
    return db
