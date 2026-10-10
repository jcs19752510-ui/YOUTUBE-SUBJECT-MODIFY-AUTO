"""시드(001-007), AI 가드·모의 제안기(008-013), 모의 게이트웨이(014-017)."""
from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy import func, select

from ytweb.ai import guard
from ytweb.ai.base import SuggestionDraft, VideoBrief
from ytweb.ai.mock import MockSuggester
from ytweb.db.models import Change, MetricsSnapshot, Video
from ytweb.domain.seed import DEFAULT_COUNT, build_video_fields, seed_demo
from ytweb.domain.suggestions import validate_title
from ytweb.youtube.base import GatewayError
from ytweb.youtube.mock import MockYouTubeGateway

from tests.domain.helpers import eligible_video_ids


def _rows(db):
    return [(v.video_id, v.title, v.snippet, v.views, v.privacy_status, v.duration_sec, v.is_short, v.exclusion_reasons) for v in db.execute(select(Video).order_by(Video.video_id)).scalars()]


def test_tc_wb_001_seed_200_videos_with_ratio(db, clock, env):
    result = seed_demo(db, clock(), env.policy)
    db.commit()
    assert (result.created, result.updated, result.total) == (200, 0, DEFAULT_COUNT)
    ids = [v.video_id for v in db.execute(select(Video)).scalars()]
    assert len(set(ids)) == 200 and all(len(i) == 11 for i in ids) and "demoVid0001" in ids
    cats = Counter(v.snippet["tags"][-1] for v in db.execute(select(Video)).scalars())
    assert cats == {"생활": 140, "건강": 40, "금융": 20}  # 70 / 20 / 10 %
    assert len({v.title for v in db.execute(select(Video)).scalars()}) == 200


def test_tc_wb_002_seed_is_idempotent(db, clock, env):
    seed_demo(db, clock(), env.policy)
    db.commit()
    before = _rows(db)
    snaps = db.execute(select(func.count()).select_from(MetricsSnapshot)).scalar_one()
    again = seed_demo(db, clock(), env.policy)
    db.commit()
    assert (again.created, again.updated, again.snapshots_created) == (0, 200, 0)
    assert _rows(db) == before
    assert db.execute(select(func.count()).select_from(Video)).scalar_one() == 200
    assert db.execute(select(func.count()).select_from(MetricsSnapshot)).scalar_one() == snaps


def test_tc_wb_003_seed_is_deterministic(db, clock, env, tmp_path):
    from sqlalchemy.orm import sessionmaker
    from ytweb.db.models import Base
    from ytweb.db.session import make_engine
    seed_demo(db, clock(), env.policy)
    db.commit()
    other_engine = make_engine(f"sqlite:///{tmp_path / 'other.db'}")
    Base.metadata.create_all(other_engine)
    with sessionmaker(other_engine, expire_on_commit=False)() as other:
        seed_demo(other, clock(), env.policy)
        other.commit()
        assert _rows(other) == _rows(db)
    other_engine.dispose()
    assert build_video_fields(7) == build_video_fields(7)


def test_tc_wb_004_seed_has_excluded_kinds_with_reasons(db, clock, env):
    seed_demo(db, clock(), env.policy)
    videos = list(db.execute(select(Video)).scalars())
    joined = " ".join(" ".join(v.exclusion_reasons) for v in videos)
    for needle in ("Shorts", "비공개", "아동용", "예약 라이브"):
        assert needle in joined
    assert all(bool(v.exclusion_reasons) == (v.is_short or v.privacy_status == "private" or v.made_for_kids is True or v.live_broadcast_content == "upcoming") for v in videos)
    assert all(v.is_short == (v.duration_sec <= env.policy.shorts_max_seconds) for v in videos)
    assert 0 < sum(1 for v in videos if v.exclusion_reasons) < 60


def test_tc_wb_005_resync_does_not_revert_changed_video(db, clock, env):
    seed_demo(db, clock(), env.policy, count=20)
    video = db.get(Video, eligible_video_ids(db, 1)[0])
    original = video.title
    video.title = "앱이 바꾼 새 제목"
    video.snippet = {**video.snippet, "title": "앱이 바꾼 새 제목"}
    db.add(Change(video_id=video.video_id, change_type="apply", previous_title=original, new_title="앱이 바꾼 새 제목", result="success", mode="demo", created_at=clock()))
    db.commit()
    seed_demo(db, clock(), env.policy, count=20)
    db.commit()
    assert db.get(Video, video.video_id).title == "앱이 바꾼 새 제목"


def test_tc_wb_006_before_snapshots_are_demo_and_stable(db, clock, env):
    seed_demo(db, clock(), env.policy, count=30)
    db.commit()
    snaps = list(db.execute(select(MetricsSnapshot)).scalars())
    assert snaps and all(s.phase == "before" and s.source == "demo" for s in snaps)
    assert all((s.period_end - s.period_start).days == 29 for s in snaps)
    assert any(s.impressions < 1000 for s in snaps) and any(s.impressions >= 1000 for s in snaps)  # '데이터 부족'과 '충분' 시연이 모두 가능
    first = {s.video_id: (s.impressions, s.period_end) for s in snaps}
    clock.advance(days=5)
    result = seed_demo(db, clock(), env.policy, count=30)
    db.commit()
    assert result.snapshots_created == 0
    assert {s.video_id: (s.impressions, s.period_end) for s in db.execute(select(MetricsSnapshot)).scalars()} == first


def test_tc_wb_007_snippet_mimics_full_youtube_fields(db, clock, env):
    seed_demo(db, clock(), env.policy, count=5)
    v = db.get(Video, "demoVid0001")
    for key in ("description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage", "channelId", "publishedAt", "thumbnails", "localized"):
        assert key in v.snippet
    assert v.snippet["title"] == v.title and v.description_excerpt and v.description_excerpt in " ".join(v.snippet["description"].split())


# ───────────── AI 가드 ─────────────

def test_tc_wb_008_guard_clean_text_removes_hidden_chars():
    dirty = "안녕‮하세요​\x00\x1b[31m\n줄바꿈\t탭﻿  끝"
    assert guard.clean_text(dirty) == "안녕하세요[31m 줄바꿈 탭 끝"
    assert guard.clean_text("가" * 50, 10) == "가" * 10


def test_tc_wb_009_guard_drops_bad_drafts_with_reasons():
    raw = [
        SuggestionDraft("정상 제목", "근거", "life"),
        {"title": "   ", "evidence": "x"},
        {"title": "가" * 301},
        {"title": "문의 010-1234-5678 로 연락"},
        {"title": "링크 https://example.com/x 확인"},
        {"title": "메일 a.b@example.com"},
        {"title": "정상  제목"},          # 공백만 달라도 중복
        {"title": 123},
        "문자열",
        {"title": "두번째 제목"},
        {"title": "세번째 제목"},
    ]
    res = guard.sanitize_drafts(raw, max_count=2)
    assert [d.title for d in res.drafts] == ["정상 제목", "두번째 제목"]
    reasons = dict(res.dropped)
    assert [reasons[i] for i in (1, 2, 3, 4, 5, 6, 7, 8, 10)] == ["empty", "too_long", "contact_or_url", "contact_or_url", "contact_or_url", "duplicate", "invalid_item", "invalid_item", "over_limit"]
    assert guard.sanitize_drafts("그냥 문자열", max_count=3).dropped == ((0, "invalid_response"),)
    assert guard.sanitize_drafts(None, max_count=3).drafts == ()


def test_tc_wb_010_guard_coerces_mapping_and_topic():
    res = guard.sanitize_drafts([{"title": "제목 A", "reason": "이유", "topic": "weird"}, {"title": "제목 B", "evidence": "근거\n줄", "topic": "health"}], max_count=5)
    assert res.drafts[0] == SuggestionDraft("제목 A", "이유", None)
    assert res.drafts[1].evidence == "근거 줄" and res.drafts[1].topic == "health"
    long_ev = guard.sanitize_drafts([{"title": "T", "evidence": "x" * 900}], max_count=1).drafts[0].evidence
    assert len(long_ev) == guard.MAX_EVIDENCE_CHARS


def test_tc_wb_011_mask_pii_and_build_summary():
    text = "문의 010-1234-5678, a@b.com, https://x.kr/p, www.y.com 주민 900101-1234567"
    masked = guard.mask_pii(text)
    for leaked in ("010-1234", "a@b.com", "x.kr", "www.y.com", "1234567"):
        assert leaked not in masked
    assert guard.build_summary(None) == "" and len(guard.build_summary("가" * 2000)) == guard.MAX_SUMMARY_CHARS


def test_tc_wb_012_mock_is_deterministic_and_counts():
    brief = VideoBrief("demoVid0001", "냉장고 정리 이렇게 하세요", "냉장고 정리 하는 순서와 주의할 점을 처음이라도 쉽게 따라 할 수 있게 알려드립니다.")
    m = MockSuggester()
    assert m.suggest(brief, count=5, tone="x") == m.suggest(brief, count=5, tone="y")
    assert [len(m.suggest(brief, count=n, tone="")) for n in (1, 2, 3, 4, 5, 9)] == [1, 2, 3, 4, 5, 5]
    assert all(d.evidence and d.topic == "life" for d in m.suggest(brief, count=5, tone=""))
    bad_kinds = {m.suggest(VideoBrief(f"demoVid{i:04d}", brief.title, brief.summary), count=3, tone="")[2].title for i in range(1, 40)}
    assert len(bad_kinds) > 1  # 영상 ID 해시에 따라 섞는 나쁜 후보의 종류가 달라진다


def test_tc_wb_013_mock_mixes_pass_warn_block_through_real_validator(db, clock, env):
    seed_demo(db, clock(), env.policy)
    m = MockSuggester()
    tally: Counter = Counter()
    for v in db.execute(select(Video)).scalars():
        for slot, d in enumerate(m.suggest(VideoBrief(v.video_id, v.title, v.description_excerpt or ""), count=5, tone="")):
            res, fr = validate_title(env, v, d.title, d.evidence, d.topic)
            tally[(d.topic, slot in (0, 1, 3), res.result)] += 1
    assert tally[("life", True, "pass")] == 3 * 140 and tally[("health", True, "pass")] == 3 * 40 and tally[("finance", True, "pass")] == 3 * 20
    assert tally[("life", False, "warn")] > 0 and tally[("life", False, "block")] > 0
    assert tally[("health", False, "block")] == 2 * 40 and tally[("finance", False, "block")] == 2 * 20  # 엄격 모드: 경고도 차단
    assert tally[("health", False, "warn")] == 0 and tally[("finance", False, "warn")] == 0


# ───────────── 모의 게이트웨이 ─────────────

def test_tc_wb_014_gateway_read_returns_copy(seeded, gw):
    snap = gw.read_snippet("demoVid0001")
    snap["title"] = "변조"
    snap["tags"].append("x")
    assert gw.read_snippet("demoVid0001")["title"] != "변조" and "x" not in gw.read_snippet("demoVid0001")["tags"]
    assert gw.read_snippet("zzzzzzzzzzz") is None


def test_tc_wb_015_gateway_full_body_keeps_everything(seeded, gw, db):
    snap = gw.read_snippet("demoVid0001")
    out = gw.update_snippet("demoVid0001", {"id": "demoVid0001", "snippet": {**snap, "title": "새 제목"}})
    video = db.get(Video, "demoVid0001")
    assert out["title"] == video.title == "새 제목" == video.snippet["localized"]["title"]
    assert {k: v for k, v in video.snippet.items() if k not in ("title", "localized")} == {k: v for k, v in snap.items() if k not in ("title", "localized")}


def test_tc_wb_016_gateway_partial_body_loses_fields_like_youtube(seeded, gw, db):
    snap = gw.read_snippet("demoVid0001")
    partial = {"title": "새 제목", "categoryId": snap["categoryId"]}
    gw.update_snippet("demoVid0001", {"id": "demoVid0001", "snippet": partial})
    after = gw.read_snippet("demoVid0001")
    assert "description" not in after and "tags" not in after and "defaultLanguage" not in after
    assert db.get(Video, "demoVid0001").description_excerpt is None


@pytest.mark.parametrize("body,code", [
    ({"id": "demoVid0001", "snippet": {"categoryId": "26"}}, "invalid_request"),
    ({"id": "demoVid0001", "snippet": {"title": "x"}}, "invalid_request"),
    ({"id": "demoVid0001", "snippet": {"title": " ", "categoryId": "26"}}, "invalid_request"),
    ({"id": "다른영상아이디1", "snippet": {"title": "x", "categoryId": "26"}}, "invalid_request"),
    ({"id": "demoVid0001"}, "invalid_request"),
])
def test_tc_wb_017_gateway_rejects_invalid_body(seeded, gw, body, code):
    with pytest.raises(GatewayError) as e:
        gw.update_snippet("demoVid0001", body)
    assert e.value.code == code and e.value.definite
    with pytest.raises(GatewayError) as e2:
        gw.update_snippet("zzzzzzzzzzz", {"id": "zzzzzzzzzzz", "snippet": {"title": "x", "categoryId": "1"}})
    assert e2.value.code == "video_not_found"
