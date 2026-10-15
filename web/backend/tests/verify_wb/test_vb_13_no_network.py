"""6단계 독립 검증 13: 데모 모드는 전 흐름에서 외부 호출 0건(런타임 소켓 차단으로 실증). 정적 임포트 점검(TC-VB-09x)을 보완한다."""
from __future__ import annotations

import socket

import pytest

from ytweb.ai.factory import get_suggester
from ytweb.domain.batches import create_draft, execute_batch, run_due_items
from ytweb.domain.changes import rollback_change
from ytweb.domain.dashboard import build_dashboard
from ytweb.domain.reports import build_reports, export_csv
from ytweb.domain.suggestions import approve, generate_for_video
from ytweb.domain.videos import list_videos, video_detail
from ytweb.youtube.mock import MockYouTubeGateway

from tests.verify_wb.vbh import changes, life_ids


def test_tc_vb_340_full_demo_flow_makes_zero_network_attempts(seeded, db, factory, env, clock, monkeypatch):
    attempts: list[str] = []

    def deny(name):
        def f(*a, **k):
            attempts.append(name)
            raise OSError(f"network blocked: {name}")
        return f

    monkeypatch.setattr(socket.socket, "connect", deny("connect"))
    monkeypatch.setattr(socket.socket, "connect_ex", deny("connect_ex"))
    monkeypatch.setattr(socket, "create_connection", deny("create_connection"))
    monkeypatch.setattr(socket, "getaddrinfo", deny("getaddrinfo"))
    monkeypatch.setattr(socket, "gethostbyname", deny("gethostbyname"))

    suggester = get_suggester("demo")
    vid = life_ids(db, 1)[0]
    sug = generate_for_video(db, vid, count=3, tone="친근한", now=clock(), env=env, suggester=suggester)
    passed = next(s for s in sug if s.validation_result == "pass")
    approve(db, passed.id, "검수자", now=clock(), env=env)
    b, pre = create_draft(db, [passed.id], None, now=clock(), env=env)
    execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    db.commit()
    res = run_due_items(factory, clock(), env)
    assert res.success == 1
    db.expire_all()
    c = changes(db)[0]
    rollback_change(db, c.id, c.video_id, "담당", now=clock(), env=env, gateway=MockYouTubeGateway(db, clock))
    db.commit()
    build_reports(db, env)
    export_csv(db, env)
    build_dashboard(db, clock(), env)
    list_videos(db, now=clock(), q=None, status=None, excluded=None, sort="title", order="asc", page=1, page_size=50)
    video_detail(db, vid, now=clock(), env=env)
    assert attempts == []
    # 대조: 차단 장치가 실제로 동작함(이 시험이 공허하지 않다는 증거)
    with pytest.raises(OSError):
        socket.getaddrinfo("example.invalid", 80)
    assert attempts == ["getaddrinfo"]
