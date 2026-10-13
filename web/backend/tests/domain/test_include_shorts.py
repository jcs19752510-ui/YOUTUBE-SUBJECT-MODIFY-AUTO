"""쇼츠 포함 스위치(YTWEB_INCLUDE_SHORTS=1): 길이 기반 'Shorts 가능성' 제외만 풀리고 다른 제외 사유는 유지된다."""
from ytweb.db.models import Video
from ytweb.domain.exclusions import exclusion_reasons


def _v(**kw):
    base = dict(video_id="abcdefghijk", title="t", privacy_status="public", made_for_kids=False, live_broadcast_content="none", duration_sec=165)
    base.update(kw)
    return Video(**base)


def test_tc_m3_080_default_excludes_shorts(env, monkeypatch):
    monkeypatch.delenv("YTWEB_INCLUDE_SHORTS", raising=False)
    assert any(r.startswith("Shorts 가능성") for r in exclusion_reasons(_v(), env.policy))


def test_tc_m3_081_switch_on_allows_shorts_but_keeps_other_reasons(env, monkeypatch):
    monkeypatch.setenv("YTWEB_INCLUDE_SHORTS", "1")
    assert exclusion_reasons(_v(), env.policy) == []
    assert exclusion_reasons(_v(privacy_status="private"), env.policy) == ["비공개 영상"]
    assert exclusion_reasons(_v(made_for_kids=True), env.policy) == ["아동용 영상"]
    assert any("길이를 알 수 없어" in r for r in exclusion_reasons(_v(duration_sec=None), env.policy))  # 길이 불명은 계속 제외
    monkeypatch.setenv("YTWEB_INCLUDE_SHORTS", "0")
    assert exclusion_reasons(_v(), env.policy) != []
