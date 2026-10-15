"""6단계 독립 검증(W-FIX-BE) 픽스처. 구현자 tests/domain 의 픽스처를 재사용하고 시험 논리는 이 폴더에서 새로 쓴다. 시험 번호 TC-VWB-NNN."""
from __future__ import annotations

import uuid

import pytest

from tests.domain.conftest import (  # noqa: F401
    DOMAIN_ROUTERS, SEED_COUNT, _reset_default_env, api, csrf, dapp, env, env_free, gw, hdr, policy, seeded,
)
from tests.domain.helpers import approved_many
from ytweb.domain.common import set_default_env
from ytweb.domain.seed import seed_demo

DISCLAIMER_LITERAL = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."


@pytest.fixture
def data(factory, env, clock):
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    set_default_env(env)
    return factory


def new_key() -> str:
    return str(uuid.uuid4())


def approved_ids(factory, env, clock, n, skip=0):
    with factory() as s:
        ids = [x.id for x in approved_many(s, env, clock(), n, skip)]
        s.commit()
    return ids
