"""W-FIX-BE 독립 검증(6단계) 픽스처. 구현자 tests/domain 픽스처를 재사용하고 시험 논리는 이 폴더에서 새로 쓴다.
재실행: cd web/backend && YTWEB_TEST_PG_URL=postgresql+psycopg://…/ytweb_test_a python -m pytest tests/verify_fix_be -p no:cacheprovider"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.domain.conftest import (  # noqa: F401
    DOMAIN_ROUTERS, SEED_COUNT, _reset_default_env, api, csrf, dapp, env, env_free, gw, hdr, policy, seeded,
)
from tests.conftest import ORIGIN  # noqa: F401
from ytweb.db.models import Base, Video
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain.seed import seed_demo


@pytest.fixture
def pgf(pg_url):
    engine = make_engine(pg_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()
    cleanup = make_engine(pg_url)
    Base.metadata.drop_all(cleanup)
    cleanup.dispose()


@pytest.fixture
def pg(pgf, env, clock):
    with pgf() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    return pgf


def life_ids(db, n: int, skip: int = 0) -> list[str]:
    rows = db.execute(select(Video).order_by(Video.video_id)).scalars().all()
    ids = [v.video_id for v in rows if not v.exclusion_reasons and v.category_id == "26"]
    assert len(ids) >= n + skip
    return ids[skip:skip + n]
