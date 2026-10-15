"""TC-VM-800~: PostgreSQL 실측(YTWEB_TEST_PG_URL, 전용 DB ytweb_test_h) — 동시 워커 이중 반영 방지, mode 제약, 대량 동기화, 초안 취소."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.domain.helpers import queued_batch
from tests.verify_m23.conftest import CLIENT_ID, CLIENT_SECRET, eligible_ids, load_fake_videos
from tests.verify_m23.fakegoogle import SCOPE_WRITE
from ytweb.db.models import Batch, BatchItem, Change, Suggestion, Video
from ytweb.domain import live_gateway as lg
from ytweb.domain.batches import run_due_items
from ytweb.domain.live_sync import sync_live
from ytweb.domain.seed import seed_demo
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.live_read import YouTubeReader

pytestmark = pytest.mark.postgres


@pytest.fixture
def pgworld(pgf, env, clock, fg, monkeypatch, tmp_path):
    with pgf() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
        ids = eligible_ids(s, 3)
        load_fake_videos(s, fg)
    cf = tmp_path / "client.json"
    cf.write_text(json.dumps({"installed": {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}}))
    env.secrets_dir.mkdir(parents=True, exist_ok=True)
    oauth.TokenStore(env.secrets_dir / lg.WRITE_TOKEN_FILE).save(
        {"access_token": "AT-WRITE-PG", "refresh_token": "RT-WRITE-PG", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), "scope": SCOPE_WRITE})
    fg.access["AT-WRITE-PG"] = SCOPE_WRITE
    monkeypatch.setenv("YTWEB_SECRETS_DIR", str(env.secrets_dir))
    monkeypatch.setenv("YTWEB_GOOGLE_CLIENT_FILE", str(cf))
    monkeypatch.setenv("YTWEB_LIVE_WRITE", "1")
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", ",".join(ids[:2]))
    return type("PG", (), {"f": pgf, "ids": ids, "fg": fg, "env": env, "clock": clock})


def test_tc_vm_800_concurrent_workers_never_double_put_in_live_mode(pgworld):
    w = pgworld
    with w.f() as s:
        queued_batch(s, w.env, w.clock(), 2)
    w.fg.calls.clear()
    errs = []

    def run():
        try:
            run_due_items(w.f, w.clock(), w.env)
        except Exception as e:                                                   # noqa: BLE001
            errs.append(repr(e))
    ts = [threading.Thread(target=run) for _ in range(4)]
    [t.start() for t in ts]
    [t.join(60) for t in ts]
    assert errs == []
    ids = sorted(c.body["id"] for c in w.fg.put_calls())
    assert ids == sorted(w.ids[:2])                                              # 영상당 정확히 1회
    with w.f() as s:
        rows = s.execute(select(Change)).scalars().all()
        assert len(rows) == 2 and {c.result for c in rows} == {"success"} and {c.mode for c in rows} == {"live"}
        assert {i.status for i in s.execute(select(BatchItem)).scalars()} == {"success"}
    run_due_items(w.f, w.clock(), w.env)
    assert len(w.fg.put_calls()) == 2


def test_tc_vm_801_non_allowed_video_in_pg_batch_zero_google_calls(pgworld):
    w = pgworld
    with w.f() as s:
        from tests.domain.helpers import approved_many, create_draft
        sugs = approved_many(s, w.env, w.clock(), 1, skip=2)               # 3번째 영상(허용 밖)
        with pytest.raises(Exception) as e:
            create_draft(s, [x.id for x in sugs], None, now=w.clock(), env=w.env)
        assert getattr(e.value, "code", "") == "batch_empty"
    assert w.fg.calls == [] or all(c.path == "/token" for c in w.fg.calls)


def test_tc_vm_802_changes_mode_check_constraint_rejects_unknown_value(pgworld):
    w = pgworld
    with w.f() as s:
        s.add(Change(video_id=w.ids[0], change_type="apply", previous_title="a", new_title="b", result="success", mode="bogus", created_at=w.clock()))
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()
        s.add(Change(video_id=w.ids[0], change_type="apply", previous_title="a", new_title="b", result="success", mode="live", created_at=w.clock()))
        s.flush()
        s.rollback()


def test_tc_vm_803_sync_live_120_videos_on_pg_idempotent_and_purges_pristine_demo(pgworld):
    w = pgworld

    class Src:
        def __init__(self):
            self.items = {f"ytv{n:08d}": {"id": f"ytv{n:08d}", "snippet": {"title": f"실제 영상 {n}", "categoryId": "26"}, "contentDetails": {"duration": "PT5M"}, "status": {"privacyStatus": "public"}, "statistics": {"viewCount": str(n)}} for n in range(120)}

        def __call__(self, url, token):
            import urllib.parse
            if "/channels" in url:
                return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "U"}}}]}
            if "/playlistItems" in url:
                q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                ids = list(self.items)
                start = int(q.get("pageToken", ["0"])[0])
                out = {"items": [{"contentDetails": {"videoId": i}} for i in ids[start:start + 50]]}
                if start + 50 < len(ids):
                    out["nextPageToken"] = str(start + 50)
                return out
            ids = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["id"][0].split(",")
            return {"items": [self.items[i] for i in ids]}
    with w.f() as s:
        r = sync_live(s, YouTubeReader(lambda: "T", Src()), w.clock(), w.env.policy)
        s.commit()
        assert r.created == 120 and r.demo_removed == 60 and s.execute(select(Video)).scalars().all().__len__() == 120
    with w.f() as s:
        r2 = sync_live(s, YouTubeReader(lambda: "T", Src()), w.clock(), w.env.policy)
        s.commit()
        assert (r2.created, r2.updated) == (0, 120)


def test_tc_vm_804_draft_cancel_on_pg_releases_suggestions_and_audits(pgworld):
    w = pgworld
    from tests.domain.helpers import approved_many, create_draft
    from ytweb.domain.batches import cancel_batch
    with w.f() as s:
        sugs = approved_many(s, w.env, w.clock(), 1)
        b, pre = create_draft(s, [x.id for x in sugs], None, now=w.clock(), env=w.env)
        s.commit()
        cancel_batch(s, b.id, now=w.clock(), env=w.env)
        s.commit()
        assert s.get(Batch, b.id).status == "cancelled"
        b2, _ = create_draft(s, [x.id for x in sugs], None, now=w.clock(), env=w.env)          # 같은 제안을 다시 담을 수 있음
        s.commit()
        assert b2.id != b.id
