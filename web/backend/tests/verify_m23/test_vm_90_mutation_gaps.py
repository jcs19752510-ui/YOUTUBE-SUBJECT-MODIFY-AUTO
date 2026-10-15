"""조치 후 변이 점검(부록 C)에서 survived 로 나온 시험 공백을 메우는 시험. 소스는 수정하지 않는다."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import InterfaceError, OperationalError

from tests.domain.helpers import eligible_video_ids, queued_batch
from tests.domain.test_live_guard import live_env  # noqa: F401
from ytweb.db.models import AuditLog, BatchItem, Change
from ytweb.domain import live_gateway as lg
from ytweb.domain.batches import apply_one
from ytweb.youtube.mock import MockYouTubeGateway


def _item(s, batch):
    return s.execute(select(BatchItem).where(BatchItem.batch_id == batch.id)).scalars().one()


def test_tc_vm_901_mode_changed_demo_confirmed_then_live_gateway_is_refused_with_code(seeded, live_env, clock):
    batch, _, _ = queued_batch(seeded, live_env, clock(), 1)  # 허용 목록 없음 = 데모로 확정
    it = _item(seeded, batch)
    live = lg.SyncedLiveGateway(seeded, MockYouTubeGateway(seeded, clock=clock), clock())
    out = apply_one(seeded, it.id, now=clock(), env=live_env, gateway=live)
    assert out.status == "skipped" and out.code == "live_mode_changed"
    assert seeded.query(Change).count() == 0


def test_tc_vm_902_mode_changed_live_confirmed_then_mock_gateway_is_refused_with_code(seeded, live_env, clock, monkeypatch):
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", eligible_video_ids(seeded, 1)[0])
    batch, _, _ = queued_batch(seeded, live_env, clock(), 1)  # 실제 모드로 확정
    it = _item(seeded, batch)
    out = apply_one(seeded, it.id, now=clock(), env=live_env, gateway=MockYouTubeGateway(seeded, clock=clock))
    assert out.status == "skipped" and out.code == "live_mode_changed"
    assert seeded.query(Change).count() == 0


class _RaisingRead(MockYouTubeGateway):
    def __init__(self, *a, exc, **kw):
        super().__init__(*a, **kw)
        self._exc = exc

    def read_snippet(self, video_id):
        raise self._exc


def test_tc_vm_903_interface_error_also_returns_item_to_pending(seeded, env, clock):
    batch, _, _ = queued_batch(seeded, env, clock(), 1)
    it = _item(seeded, batch)
    gw = _RaisingRead(seeded, clock=clock, exc=InterfaceError("SELECT 1", {}, Exception("connection already closed")))
    out = apply_one(seeded, it.id, now=clock(), env=env, gateway=gw)
    assert (out.status, out.code) == ("deferred", "db_unavailable")
    seeded.expire_all()
    assert seeded.get(BatchItem, it.id).status == "pending"


class _RaisingWrite(MockYouTubeGateway):
    def update_snippet(self, video_id, body):
        raise OperationalError("UPDATE", {}, Exception("server closed the connection unexpectedly"))


def test_tc_vm_904_db_error_after_planned_record_is_not_silently_returned_to_pending(seeded, env, clock):
    """planned 기록 뒤(쓰기 시도 후) DB 오류는 '쓰기 전'이 아니므로 대기로 되돌리면 이중 반영 위험 — 되돌리지 않는다."""
    batch, _, _ = queued_batch(seeded, env, clock(), 1)
    it = _item(seeded, batch)
    out = apply_one(seeded, it.id, now=clock(), env=env, gateway=_RaisingWrite(seeded, clock=clock))
    assert out.code != "db_unavailable" and out.status != "deferred"
    seeded.expire_all()
    assert seeded.get(BatchItem, it.id).status != "pending"


def _live_applied(seeded, live_env, clock, monkeypatch):
    monkeypatch.setenv("YTWEB_LIVE_ALLOWED_VIDEOS", eligible_video_ids(seeded, 1)[0])
    batch, _, _ = queued_batch(seeded, live_env, clock(), 1)
    it = _item(seeded, batch)
    live = lg.SyncedLiveGateway(seeded, MockYouTubeGateway(seeded, clock=clock), clock())
    assert apply_one(seeded, it.id, now=clock(), env=live_env, gateway=live).status == "success"
    return seeded.query(Change).one(), live


def _rollback(seeded, live_env, clock, change, live):
    from ytweb.core.errors import ProblemError
    from ytweb.domain.changes import rollback_change
    try:
        rollback_change(seeded, change.id, change.video_id, "홍길동", now=clock(), env=live_env, gateway=live)
    except ProblemError as e:
        return e
    return None


def test_tc_vm_905_live_rollback_refused_when_studio_changed_description_after_apply(seeded, live_env, clock, monkeypatch):
    from ytweb.db.models import Video
    change, live = _live_applied(seeded, live_env, clock, monkeypatch)
    v = seeded.get(Video, change.video_id)
    v.snippet = {**v.snippet, "description": "Studio 에서 나중에 고친 설명"}
    seeded.flush()
    e = _rollback(seeded, live_env, clock, change, live)
    assert e is not None and e.code == "live_changed_since_apply" and "description" in str(e.detail)


def test_tc_vm_906_live_rollback_refused_when_studio_changed_title_after_apply(seeded, live_env, clock, monkeypatch):
    from ytweb.db.models import Video
    change, live = _live_applied(seeded, live_env, clock, monkeypatch)
    v = seeded.get(Video, change.video_id)
    v.snippet = {**v.snippet, "title": "Studio 에서 나중에 고친 제목"}
    v.title = "Studio 에서 나중에 고친 제목"
    seeded.flush()
    e = _rollback(seeded, live_env, clock, change, live)
    assert e is not None and e.code == "live_changed_since_apply" and "title" in str(e.detail)


def test_tc_vm_907_live_rollback_succeeds_when_nothing_changed_since_apply(seeded, live_env, clock, monkeypatch):
    change, live = _live_applied(seeded, live_env, clock, monkeypatch)
    assert _rollback(seeded, live_env, clock, change, live) is None


def test_tc_vm_908_google_state_mode_and_connected_depend_on_client_file_and_token(env, tmp_path, monkeypatch):
    import json
    from datetime import datetime, timedelta, timezone
    from ytweb.domain.dashboard import google_state
    from ytweb.youtube import google_oauth as oauth
    client = tmp_path / "c.json"
    monkeypatch.setenv("YTWEB_GOOGLE_CLIENT_FILE", str(client))
    st = google_state(env)  # 클라이언트 파일 없음, 토큰 없음
    assert st["mode"] == "demo" and st["connected"] is False
    client.write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    st = google_state(env)  # 파일 있음, 토큰 없음
    assert st["mode"] == "read" and st["connected"] is False
    oauth.TokenStore(env.secrets_dir / "google_token.json").save(
        {"access_token": "A", "refresh_token": "R", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    assert google_state(env)["connected"] is True
    client.unlink()  # 토큰만 남고 클라이언트 파일 없음
    st = google_state(env)
    assert st["mode"] == "demo" and st["connected"] is False


def test_tc_vm_909_is_fresh_rejects_naive_timestamp_and_keeps_aware_future():
    from datetime import datetime, timedelta, timezone
    from ytweb.youtube.google_oauth import TokenStore
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert TokenStore.is_fresh({"expires_at": (now + timedelta(hours=1)).replace(tzinfo=None).isoformat()}, now) is False
    assert TokenStore.is_fresh({"expires_at": (now + timedelta(hours=1)).isoformat()}, now) is True


def test_tc_vm_910_urllib_opener_does_not_follow_redirects():
    import urllib.request
    from ytweb.youtube import google_oauth as oauth
    req = urllib.request.Request("https://example.invalid/", headers={"Authorization": "Bearer X"})
    assert oauth._NoRedirect().redirect_request(req, None, 302, "Found", {}, "https://evil.invalid/") is None
    opener = getattr(urllib.request, "_opener", None)
    assert opener is not None and any(isinstance(h, oauth._NoRedirect) for h in opener.handlers)


def test_tc_vm_911_unknown_state_callback_writes_no_audit_row(gapp, csrf, fg, db):
    from sqlalchemy import func
    before = db.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    assert gapp.get("/api/v1/google/callback?code=C&state=unknown-state", follow_redirects=False).status_code == 303
    db.expire_all()
    assert db.execute(select(func.count()).select_from(AuditLog)).scalar_one() == before
