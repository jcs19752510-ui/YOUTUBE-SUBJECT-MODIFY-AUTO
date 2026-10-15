"""TC-VM-500~: domain/live_gateway.py (M3 단위 2·4) 독립 검증 — 3조건 선택표, 허용 목록 파싱, 확인 문구, 차단 사유, DB 동기화."""
from __future__ import annotations

import itertools
import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from tests.verify_m23.fakegoogle import SCOPE_WRITE
from ytweb.db.models import Video
from ytweb.domain import live_gateway as lg
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.base import GatewayError
from ytweb.youtube.mock import MockYouTubeGateway

HANGUL = re.compile("[가-힣]")
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
VID = "abcdefghijk"


def setup_world(tmp_path, *, token=True, client=True, flag="1", allowed=VID, token_content=None):
    sd = tmp_path / "sec"
    sd.mkdir(exist_ok=True)
    cf = tmp_path / "client.json"
    if client:
        cf.write_text(json.dumps({"installed": {"client_id": "i", "client_secret": "s"}}))
    if token:
        oauth.TokenStore(sd / lg.WRITE_TOKEN_FILE).save(token_content or {"access_token": "A", "refresh_token": "R", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    env = {"YTWEB_GOOGLE_CLIENT_FILE": str(cf)}
    if flag is not None:
        env["YTWEB_LIVE_WRITE"] = flag
    if allowed is not None:
        env["YTWEB_LIVE_ALLOWED_VIDEOS"] = allowed
    return sd, env


@pytest.mark.parametrize("token,client,flag,allowed", list(itertools.product([True, False], [True, False], ["1", "0", None], [VID, "", None])))
def test_tc_vm_500_selection_truth_table_live_only_when_all_conditions_hold(db, tmp_path, token, client, flag, allowed):
    sd, env = setup_world(tmp_path, token=token, client=client, flag=flag, allowed=allowed)
    expect_live = token and client and flag == "1" and allowed == VID
    g = lg.select_gateway(db, NOW, sd, env)
    assert isinstance(g, lg.SyncedLiveGateway) is expect_live
    assert isinstance(g, MockYouTubeGateway) is (not expect_live)
    assert lg.live_mode(sd, env) is expect_live and lg.is_live(g) is expect_live


@pytest.mark.parametrize("flag", ["true", "TRUE", "yes", "on", "01", " 1", "1 ", "2", "", "０", "-1", "enabled"])
def test_tc_vm_501_only_exact_string_1_enables_live(db, tmp_path, flag):
    sd, env = setup_world(tmp_path, flag=flag)
    assert lg.live_write_enabled(env) is False and isinstance(lg.select_gateway(db, NOW, sd, env), MockYouTubeGateway)


@pytest.mark.parametrize("raw,exp", [
    ("a", {"a"}), (" a , b ", {"a", "b"}), ("a,,b,", {"a", "b"}), (",", set()), ("   ", set()), ("", set()), ("a,a", {"a"}), ("a b", {"a b"}), ("a;b", {"a;b"}), ("A,a", {"A", "a"}),
])
def test_tc_vm_502_allowed_videos_parsing(raw, exp):
    assert lg.allowed_videos({"YTWEB_LIVE_ALLOWED_VIDEOS": raw}) == exp


def test_tc_vm_503_allowed_defaults_to_empty_when_unset():
    assert lg.allowed_videos({}) == frozenset()


@pytest.mark.parametrize("content", [{"access_token": "A"}, {"refresh_token": ""}, {"refresh_token": None}])
def test_tc_vm_504_token_file_without_refresh_token_is_not_connected_so_mock(db, tmp_path, content):
    sd, env = setup_world(tmp_path, token_content=content)
    assert isinstance(lg.select_gateway(db, NOW, sd, env), MockYouTubeGateway)


def test_tc_vm_505_corrupt_token_file_falls_back_to_mock(db, tmp_path):
    sd, env = setup_world(tmp_path)
    (sd / lg.WRITE_TOKEN_FILE).write_text("{broken")
    assert isinstance(lg.select_gateway(db, NOW, sd, env), MockYouTubeGateway)


def test_tc_vm_506_read_token_file_alone_never_enables_write(db, tmp_path):
    sd, env = setup_world(tmp_path, token=False)
    oauth.TokenStore(sd / "google_token.json").save({"access_token": "A", "refresh_token": "R", "expires_at": "x"})
    assert isinstance(lg.select_gateway(db, NOW, sd, env), MockYouTubeGateway) and lg.live_mode(sd, env) is False


def test_tc_vm_507_write_gateway_reads_only_the_write_token_file(db, tmp_path):
    sd, env = setup_world(tmp_path, token_content={"access_token": "WRITE-A", "refresh_token": "R", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    oauth.TokenStore(sd / "google_token.json").save({"access_token": "READ-A", "refresh_token": "R", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()})
    assert lg.write_access(sd, env).access_token() == "WRITE-A"


# ---------- 확인 문구 ----------
@pytest.mark.parametrize("n", [0, 1, 2, 9, 10, 50, 100])
def test_tc_vm_510_confirm_text_demo_vs_live(n):
    assert lg.confirm_text(n, False) == f"실행 {n}건" and lg.confirm_text(n, True) == f"실제 실행 {n}건"
    assert lg.confirm_text(n, False) != lg.confirm_text(n, True)
    assert not lg.confirm_text(n, True).startswith(lg.confirm_text(n, False))       # 데모 문구가 실제 문구의 접두어가 아님(부분일치 오인 방지)


# ---------- 차단 사유 ----------
def test_tc_vm_520_not_allowed_reason_only_in_live_mode_and_only_for_other_ids(tmp_path):
    sd, env = setup_world(tmp_path)
    assert lg.not_allowed_reason(VID, sd, env) is None
    r = lg.not_allowed_reason("zzzzzzzzzzz", sd, env)
    assert r and HANGUL.search(r) and "YTWEB_LIVE_ALLOWED_VIDEOS" in r
    for bad in ("", " " + VID, VID.upper(), VID[:-1]):
        assert lg.not_allowed_reason(bad, sd, env), bad


def test_tc_vm_521_not_allowed_reason_is_none_in_demo_mode_for_any_video(tmp_path):
    sd, env = setup_world(tmp_path, flag="0")
    assert lg.not_allowed_reason("zzzzzzzzzzz", sd, env) is None
    (tmp_path / "b").mkdir()
    sd2, env2 = setup_world(tmp_path / "b", token=False)             # 별도 폴더: 쓰기 토큰 없음(플래그 1, 허용 목록 있음)
    assert lg.not_allowed_reason("zzzzzzzzzzz", sd2, env2) is None


# ---------- SyncedLiveGateway ----------
class FakeLive:
    def __init__(self, out=None, err=None):
        self.out, self.err, self.n = out, err, 0

    def read_snippet(self, v):
        return {"title": "x"}

    def update_snippet(self, v, b):
        self.n += 1
        if self.err:
            raise self.err
        return self.out


def test_tc_vm_530_confirmed_update_mirrors_all_fields_into_videos_row(seeded):
    v = seeded.execute(select(Video).order_by(Video.video_id)).scalars().first()
    out = {"title": "동기화된 새 제목", "categoryId": "99", "description": "  새   설명 "}
    lg.SyncedLiveGateway(seeded, FakeLive(out=out), NOW).update_snippet(v.video_id, {})
    seeded.refresh(v)
    assert v.title == "동기화된 새 제목" and v.category_id == "99" and v.snippet == out and v.description_excerpt == "새 설명" and v.fetched_at == NOW
    out["title"] = "MUTATED"
    assert v.snippet["title"] == "동기화된 새 제목"                                   # 깊은 복사


@pytest.mark.parametrize("definite", [True, False])
def test_tc_vm_531_error_leaves_db_row_untouched_and_keeps_definite(seeded, definite):
    v = seeded.execute(select(Video).order_by(Video.video_id)).scalars().first()
    snap = (v.title, v.category_id, dict(v.snippet))
    with pytest.raises(GatewayError) as e:
        lg.SyncedLiveGateway(seeded, FakeLive(err=GatewayError("c", "m", definite=definite)), NOW).update_snippet(v.video_id, {})
    assert e.value.definite is definite
    seeded.refresh(v)
    assert (v.title, v.category_id, dict(v.snippet)) == snap


def test_tc_vm_532_video_missing_in_db_does_not_crash(db):
    out = {"title": "새 제목입니다", "categoryId": "22"}
    assert lg.SyncedLiveGateway(db, FakeLive(out=out), NOW).update_snippet("nosuchvid00", {}) == out


def test_tc_vm_533_missing_categoryid_in_response_keeps_previous_category(seeded):
    v = seeded.execute(select(Video).order_by(Video.video_id)).scalars().first()
    prev = v.category_id
    lg.SyncedLiveGateway(seeded, FakeLive(out={"title": "새 제목입니다"}), NOW).update_snippet(v.video_id, {})
    seeded.refresh(v)
    assert v.category_id == prev
