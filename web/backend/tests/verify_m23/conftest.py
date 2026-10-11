"""M2·M3 독립 검증(6단계) 공용 픽스처. 시험 논리는 이 폴더에서 새로 쓴다. 구현자 시험은 재사용하지 않는다(기반 fixture 만 임포트).
재실행: cd web/backend && YTWEB_TEST_PG_URL=postgresql+psycopg://ytweb_test@127.0.0.1:54329/ytweb_test_h python -m pytest tests/verify_m23 -p no:cacheprovider -o addopts=''"""
from __future__ import annotations

import copy
import json
import socket
import urllib.request
import uuid

import pytest
from sqlalchemy import select

from tests.domain.conftest import (  # noqa: F401
    DOMAIN_ROUTERS, SEED_COUNT, _reset_default_env, api, csrf, dapp, env, env_free, gw, hdr, policy, seeded,
)
from tests.conftest import ORIGIN  # noqa: F401
from tests.verify_m23.fakegoogle import FakeGoogle, RealNetworkAttempt
from ytweb.db.models import Base, Video
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain.seed import seed_demo

CLIENT_ID, CLIENT_SECRET = "cid-123", "csec-456"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """어떤 경우에도 실제 구글로 나가지 않게: urlopen 은 FakeGoogle 로, 이름 해석은 loopback 외 거부."""
    fg = FakeGoogle(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    monkeypatch.setattr(urllib.request, "urlopen", fg.urlopen)
    real = socket.getaddrinfo

    def guarded(host, *a, **k):
        if host not in (None, "", "127.0.0.1", "localhost", "::1", "testserver"):
            raise RealNetworkAttempt(f"이름 해석 시도: {host}")
        return real(host, *a, **k)

    monkeypatch.setattr(socket, "getaddrinfo", guarded)
    return fg


@pytest.fixture
def fg(no_real_network) -> FakeGoogle:
    return no_real_network


@pytest.fixture
def client_file(tmp_path):
    p = tmp_path / "google_client.json"
    p.write_text(json.dumps({"installed": {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}}), encoding="utf-8")
    return p


@pytest.fixture
def gapp(api, client_file, monkeypatch, web_settings):
    """실제 배선(GoogleCtx 기본 생성)을 쓰는 앱: 클라이언트 파일·시크릿 폴더를 환경변수로 가리킨다."""
    monkeypatch.setenv("YTWEB_GOOGLE_CLIENT_FILE", str(client_file))
    monkeypatch.setenv("YTWEB_SECRETS_DIR", str(web_settings.secrets_dir))
    monkeypatch.delenv("YTWEB_LIVE_WRITE", raising=False)
    monkeypatch.delenv("YTWEB_LIVE_ALLOWED_VIDEOS", raising=False)
    return api


def start_flow(api, csrf, which: str = "connect") -> str:
    r = api.post(f"/api/v1/google/{which}", headers=hdr(csrf))
    assert r.status_code == 200, r.text
    return r.json()["auth_url"]


def finish_flow(api, fg: FakeGoogle, auth_url: str, *, extra: str = ""):
    import urllib.parse
    q = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
    code = fg.consent(auth_url)
    return api.get(f"/api/v1/google/callback?code={code}&state={q['state'][0]}{extra}", follow_redirects=False)


def connect_both(api, csrf, fg):
    assert finish_flow(api, fg, start_flow(api, csrf, "connect")).status_code == 303
    assert finish_flow(api, fg, start_flow(api, csrf, "connect-write")).status_code == 303


def eligible_ids(db, n: int, skip: int = 0) -> list[str]:
    rows = db.execute(select(Video).order_by(Video.video_id)).scalars().all()
    ids = [v.video_id for v in rows if not v.exclusion_reasons]
    assert len(ids) >= n + skip
    return ids[skip:skip + n]


def approve_via_api(api, csrf, vid: str) -> int:
    r = api.post(f"/api/v1/videos/{vid}/suggestions", json={"count": 5}, headers=hdr(csrf))
    assert r.status_code == 201, r.text
    sug = next(x for x in r.json() if x["validation_result"] == "pass")
    a = api.post(f"/api/v1/suggestions/{sug['id']}/approve", json={"approver": "검수자"}, headers=hdr(csrf))
    assert a.status_code == 200, a.text
    return sug["id"]


def make_draft(api, csrf, ids):
    return api.post("/api/v1/batches", json={"suggestion_ids": ids, "note": None}, headers=hdr(csrf, uuid.uuid4().hex))


def do_execute(api, csrf, bid, text, key=None):
    return api.post(f"/api/v1/batches/{bid}/execute", json={"confirm_text": text}, headers=hdr(csrf, key or uuid.uuid4().hex))


def load_fake_videos(db, fg: FakeGoogle, ids=None):
    for v in db.execute(select(Video)).scalars():
        if ids is None or v.video_id in ids:
            fg.videos[v.video_id] = copy.deepcopy(v.snippet)


@pytest.fixture
def live(gapp, csrf, fg, factory, env, clock, monkeypatch, tmp_path):
    """실제 수정 3조건을 갖춘 세계: 구글 연결(읽기+쓰기, 실제 로그인 흐름) + YTWEB_LIVE_WRITE=1 + 허용 영상 = 승인 대상 첫 영상 1개."""
    from ytweb.domain import handlers
    from ytweb.domain.common import set_default_env
    set_default_env(env)
    monkeypatch.setattr(handlers, "utcnow", clock)
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=SEED_COUNT)
        s.commit()
    with factory() as s:
        ids = eligible_ids(s, 3)
        load_fake_videos(s, fg)
    connect_both(gapp, csrf, fg)
    monkeypatch.setenv("YTWEB_LIVE_WRITE", "1")
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", ids[0])
    fg.calls.clear()
    return type("Live", (), {"api": gapp, "csrf": csrf, "fg": fg, "ids": ids, "factory": factory, "env": env, "clock": clock, "mp": monkeypatch})


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


# ---- 열린 결함(DEF-VM) 표식: 첫 실행에서 실패한 시험을 '기대값 수정' 없이 strict xfail 로 고정한다. 결함이 고쳐지면 XPASS(strict)로 실패해 이 표를 지우게 만든다.
KNOWN_DEFECTS: dict[str, str] = {}  # 2026-10-11 DEF-VM-001~003·005~010 조치로 모두 해소(표식 제거). 원래 실패는 결과서 web-WU-M23-BE-test.md 에 남아 있다.


def pytest_collection_modifyitems(config, items):
    for it in items:
        for key, ident in KNOWN_DEFECTS.items():
            if key in it.nodeid:
                it.add_marker(pytest.mark.xfail(reason=f"{ident}: 열린 결함(결과서 6절)", strict=True))
                break
