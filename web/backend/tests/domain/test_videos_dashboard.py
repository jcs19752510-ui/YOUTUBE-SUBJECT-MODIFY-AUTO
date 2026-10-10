"""영상 목록·상세, 대시보드(113-122)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from ytweb.core import jobs
from ytweb.core.settings_store import set_web_setting
from ytweb.db.models import Suggestion, Video
from ytweb.domain.batches import apply_one, cancel_batch, create_draft, execute_batch
from ytweb.domain.changes import rollback_change
from ytweb.domain.dashboard import build_dashboard
from ytweb.domain.suggestions import approve
from ytweb.domain.videos import list_videos, video_detail, workflow_maps
from ytweb.core.errors import ProblemError

from tests.domain.helpers import approved, eligible_video_ids, queued_batch, suggest


def _list(db, clock, **kw):
    args = dict(q=None, status=None, excluded=None, sort="video_id", order="asc", page=1, page_size=50)
    args.update(kw)
    return list_videos(db, now=clock(), **args)


def test_tc_wb_113_pagination(seeded, clock):
    items, total = _list(seeded, clock, page_size=25, page=2)
    assert total == 60 and len(items) == 25 and items[0]["video_id"] == "demoVid0026"
    assert len(_list(seeded, clock, page=3, page_size=25)[0]) == 10 and _list(seeded, clock, page=9)[0] == []
    assert len(_list(seeded, clock, page_size=9999)[0]) == 60 and len(_list(seeded, clock, page=-4, page_size=0)[0]) == 1
    assert set(items[0]) == {"video_id", "title", "privacy_status", "duration_sec", "is_short", "excluded", "exclusion_reasons", "workflow_status", "suggestion_count", "last_change_at", "views"}


def test_tc_wb_114_search_is_case_insensitive_and_literal(seeded, clock):
    assert [i["video_id"] for i in _list(seeded, clock, q="DEMOVID0007")[0]] == ["demoVid0007"]
    titled = _list(seeded, clock, q="냉장고")[0]
    assert titled and all("냉장고" in i["title"] for i in titled)
    assert _list(seeded, clock, q="%")[1] == 0 and _list(seeded, clock, q="' OR 1=1 --")[1] == 0   # 와일드카드·SQL 조각은 글자 그대로
    assert _list(seeded, clock, q="  ")[1] == 60


def test_tc_wb_115_excluded_and_status_filters(seeded, clock, env):
    ex, nex = _list(seeded, clock, excluded=True), _list(seeded, clock, excluded=False)
    assert ex[1] + nex[1] == 60 and ex[1] > 0 and all(i["excluded"] and i["exclusion_reasons"] for i in ex[0])
    vid = eligible_video_ids(seeded, 1)[0]
    suggest(seeded, env, clock(), vid, 2)
    assert [i["video_id"] for i in _list(seeded, clock, status="suggested")[0]] == [vid]
    assert _list(seeded, clock, status="none")[1] == 59 and _list(seeded, clock, status="applied")[1] == 0


def test_tc_wb_116_sort_with_missing_values_last(seeded, clock):
    video = seeded.get(Video, "demoVid0003")
    video.views = None
    seeded.flush()
    asc = [i["views"] for i in _list(seeded, clock, sort="views", order="asc", page_size=200)[0]]
    desc = [i["views"] for i in _list(seeded, clock, sort="views", order="desc", page_size=200)[0]]
    assert asc[-1] is None and desc[-1] is None
    assert asc[:-1] == sorted(asc[:-1]) and desc[:-1] == sorted(desc[:-1], reverse=True)
    assert [i["title"] for i in _list(seeded, clock, sort="title", page_size=200)[0]] == sorted(i["title"] for i in _list(seeded, clock, page_size=200)[0])


def test_tc_wb_117_workflow_status_progression(seeded, env, clock, gw):
    vid = eligible_video_ids(seeded, 1)[0]
    st = lambda: workflow_maps(seeded)[0].get(vid, "none")  # noqa: E731
    assert st() == "none"
    sug = suggest(seeded, env, clock(), vid)[0]
    assert st() == "suggested"
    approve(seeded, sug.id, "홍길동", now=clock(), env=env)
    assert st() == "approved"
    batch, _ = create_draft(seeded, [sug.id], None, now=clock(), env=env)
    execute_batch(seeded, batch.id, "실행 1건", now=clock(), env=env)
    assert st() == "queued"
    apply_one(seeded, batch.items[0].id, now=clock(), env=env, gateway=gw)
    assert st() == "applied"
    change = seeded.execute(select(__import__("ytweb.db.models", fromlist=["Change"]).Change)).scalars().first()
    rollback_change(seeded, change.id, vid, "홍길동", now=clock(), env=env, gateway=gw)
    assert st() == "rolled_back"
    items, _ = _list(seeded, clock, q=vid)
    assert items[0]["last_change_at"] is not None and items[0]["suggestion_count"] == 1


def test_tc_wb_118_video_detail_contents(seeded, env, clock, gw):
    vid = eligible_video_ids(seeded, 1)[0]
    suggest(seeded, env, clock(), vid, 2)
    d = video_detail(seeded, vid, now=clock(), env=env)
    assert d["video_id"] == vid and len(d["suggestions"]) == 2 and d["changes"] == []
    assert d["limits"] == {"allowed": True, "reasons": [], "next_allowed_at": None}
    assert d["preserved"]["category_id"] and d["preserved"]["tags"] and d["preserved"]["default_language"] == "ko" and d["preserved"]["description_chars"] > 10
    assert d["description_excerpt"]
    e = None
    with pytest.raises(ProblemError) as e:
        video_detail(seeded, "zzzzzzzzzzz", now=clock(), env=env)
    assert e.value.status == 404


def test_tc_wb_119_dashboard_numbers(seeded, env, clock, gw):
    d = build_dashboard(seeded, clock(), env)
    assert d["mode"] == "demo" and d["live_enabled"] is False and d["google"] == {"mode": "demo", "connected": False}
    assert d["counts"]["videos"] == 60 and d["counts"]["excluded"] > 0 and d["today"] == {"applied": 0, "cap": 10}
    assert d["quota"] == {"used": 0, "limit": 6000, "remaining": 6000, "pt_date": clock().date() - timedelta(days=1)}  # 03:00Z 는 태평양 시간 전날
    assert d["active_job"] is None and d["queue"] == {"pending_items": 0, "next_run_date": None}
    set_web_setting(seeded, "daily_apply_cap", 2, now=clock())
    batch, _, job = queued_batch(seeded, env, clock(), 3)
    d = build_dashboard(seeded, clock(), env)
    assert d["counts"]["queued"] == 3 and d["queue"]["pending_items"] == 3 and str(d["queue"]["next_run_date"]) == "2026-10-10"
    assert d["active_job"]["id"] == job.id and d["today"]["cap"] == 2
    apply_one(seeded, batch.items[0].id, now=clock(), env=env, gateway=gw)
    d = build_dashboard(seeded, clock(), env)
    assert d["today"]["applied"] == 1 and d["counts"]["applied"] == 1 and d["quota"]["used"] == 52 and d["queue"]["pending_items"] == 2


def test_tc_wb_120_dashboard_counts_cancelled_not_pending(seeded, env, clock):
    batch, *_ = queued_batch(seeded, env, clock(), 2)
    cancel_batch(seeded, batch.id, now=clock(), env=env)
    d = build_dashboard(seeded, clock(), env)
    assert d["queue"]["pending_items"] == 0 and d["counts"]["queued"] == 0 and d["counts"]["approved"] == 2


def test_tc_wb_121_expired_approvals_leave_the_approved_count(seeded, env, clock):
    approved(seeded, env, clock(), eligible_video_ids(seeded, 1)[0])
    assert build_dashboard(seeded, clock(), env)["counts"]["approved"] == 1
    assert build_dashboard(seeded, clock() + timedelta(hours=25), env)["counts"]["approved"] == 0
    assert seeded.execute(select(Suggestion.status)).scalar_one() == "expired"
