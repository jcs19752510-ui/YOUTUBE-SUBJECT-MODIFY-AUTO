"""실제 수정 준비 점검(읽기 전용) 시험."""
import json
from datetime import datetime, timedelta, timezone

from ytweb import live_check
from ytweb.domain import live_gateway as lg
from ytweb.youtube import google_oauth as oauth


def _tok():
    return {"access_token": "a", "refresh_token": "r", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}


def test_tc_m3_070_nothing_ready(tmp_path):
    items, ready = live_check.check({"YTWEB_GOOGLE_CLIENT_FILE": str(tmp_path / "none.json")}, tmp_path)
    assert not ready and [ok for ok, _ in items] == [False] * 5 and all("→" in m for _, m in items)


def test_tc_m3_071_all_ready_and_partial(tmp_path):
    c = tmp_path / "c.json"
    c.write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    oauth.TokenStore(tmp_path / "google_token.json").save(_tok())
    oauth.TokenStore(tmp_path / lg.WRITE_TOKEN_FILE).save(_tok())
    env = {"YTWEB_GOOGLE_CLIENT_FILE": str(c), "YTWEB_LIVE_WRITE": "1", "YTWEB_LIVE_ALLOWED_VIDEOS": "abcdefghijk"}
    items, ready = live_check.check(env, tmp_path)
    assert ready and all(ok for ok, _ in items)
    items2, ready2 = live_check.check({**env, "YTWEB_LIVE_WRITE": "0"}, tmp_path)
    assert not ready2 and [ok for ok, _ in items2] == [True, True, True, False, True]
