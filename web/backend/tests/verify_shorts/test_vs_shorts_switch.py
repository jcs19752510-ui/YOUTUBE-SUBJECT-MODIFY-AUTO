"""독립 검증(오늘 변경): 쇼츠 포함 스위치 YTWEB_INCLUDE_SHORTS. 명세 = '정확히 "1" 일 때만 켜짐, 길이 기반 Shorts 제외만 해제'."""
import pytest
from sqlalchemy import select

from ytweb.db.models import Video
from ytweb.domain.exclusions import exclusion_reasons, include_shorts
from ytweb.domain.live_sync import sync_live
from tests.domain.test_live_sync import NOW, FakeYT, item, reader, vid


@pytest.fixture
def env(web_settings):
    from youtube_title.config import load_settings
    from ytweb.domain.common import Env
    from tests.conftest import REPO_ROOT
    return Env.build(load_settings(REPO_ROOT, env={}), web_settings)


def _v(**kw):
    base = dict(video_id="abcdefghijk", title="t", privacy_status="public", made_for_kids=False, live_broadcast_content="none", duration_sec=165)
    base.update(kw)
    return Video(**base)


def _short(rs):
    return [r for r in rs if r.startswith("Shorts 가능성")]


def test_vs_01_unset_is_off(env, monkeypatch):
    monkeypatch.delenv("YTWEB_INCLUDE_SHORTS", raising=False)
    assert include_shorts() is False and _short(exclusion_reasons(_v(), env.policy))


@pytest.mark.parametrize("val,expected", [("1", True), ("0", False), ("", False), ("true", False), ("TRUE", False), ("yes", False), ("1 ", False), (" 1", False), ("11", False)])
def test_vs_02_value_matrix(env, monkeypatch, val, expected):
    monkeypatch.setenv("YTWEB_INCLUDE_SHORTS", val)
    assert include_shorts() is expected
    assert (_short(exclusion_reasons(_v(), env.policy)) == []) is expected


def test_vs_03_on_keeps_other_exclusions_incl_combos(env, monkeypatch):
    monkeypatch.setenv("YTWEB_INCLUDE_SHORTS", "1")
    assert exclusion_reasons(_v(privacy_status="private"), env.policy) == ["비공개 영상"]
    assert exclusion_reasons(_v(made_for_kids=True), env.policy) == ["아동용 영상"]
    assert exclusion_reasons(_v(duration_sec=None), env.policy) != []
    assert exclusion_reasons(_v(live_broadcast_content="upcoming"), env.policy) != []
    r = exclusion_reasons(_v(privacy_status="private", made_for_kids=True), env.policy)
    assert len(r) == 2 and _short(r) == []


def test_vs_04_boundary_180_and_181(env, monkeypatch):
    lim = env.policy.shorts_max_seconds
    monkeypatch.delenv("YTWEB_INCLUDE_SHORTS", raising=False)
    assert _short(exclusion_reasons(_v(duration_sec=lim), env.policy))
    assert _short(exclusion_reasons(_v(duration_sec=lim + 1), env.policy)) == []
    monkeypatch.setenv("YTWEB_INCLUDE_SHORTS", "1")
    assert exclusion_reasons(_v(duration_sec=lim), env.policy) == []


def test_vs_05_is_short_flag_kept_and_sync_recalculates(db, env, monkeypatch):
    fake = lambda: FakeYT(items=[item(1, dur="PT2M45S"), item(2, dur="PT10M"), item(3, dur="PT2M45S", privacy="private")], pages=[[vid(1), vid(2), vid(3)]])
    monkeypatch.delenv("YTWEB_INCLUDE_SHORTS", raising=False)
    sync_live(db, reader(fake()), NOW, env.policy); db.commit()
    rows = {v.video_id: v for v in db.execute(select(Video)).scalars()}
    assert rows[vid(1)].is_short and rows[vid(1)].exclusion_reasons
    assert not rows[vid(2)].is_short and rows[vid(2)].exclusion_reasons == []
    monkeypatch.setenv("YTWEB_INCLUDE_SHORTS", "1")
    sync_live(db, reader(fake()), NOW, env.policy); db.commit()
    db.expire_all()
    rows = {v.video_id: v for v in db.execute(select(Video)).scalars()}
    assert rows[vid(1)].is_short is True and rows[vid(1)].exclusion_reasons == []  # 표시는 유지, 제외만 해제
    assert rows[vid(3)].is_short is True and rows[vid(3)].exclusion_reasons == ["비공개 영상"]
    monkeypatch.setenv("YTWEB_INCLUDE_SHORTS", "0")
    sync_live(db, reader(fake()), NOW, env.policy); db.commit()
    db.expire_all()
    assert db.get(Video, vid(1)).exclusion_reasons != []  # 끄면 다시 제외


def test_vs_06_live_check_prints_status(monkeypatch, capsys):
    import ytweb.live_check as lc
    src = open(lc.__file__, encoding="utf-8").read()
    assert "YTWEB_INCLUDE_SHORTS=1" in src and "include_shorts()" in src
    for val, word in (("1", "켜짐"), ("0", "꺼짐")):
        monkeypatch.setenv("YTWEB_INCLUDE_SHORTS", val)
        try:
            lc.main()
        except BaseException:
            pass
        out = capsys.readouterr().out
        assert ("[정보] 쇼츠(180초 이하) 영상 제목 변경: " + word) in out, out
