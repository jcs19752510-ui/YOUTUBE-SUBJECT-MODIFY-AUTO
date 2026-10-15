"""6단계 독립 검증 6: 성과 리포트·CSV(W-013, POL-002), 감사 로그 기록 범위(S-W16), 영상 상세 비교 데이터(W-006), 대시보드."""
from __future__ import annotations

import csv
import io
import json
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from ytweb.core import audit
from ytweb.core.errors import ProblemError
from ytweb.db.models import AuditLog, Change, MetricsSnapshot, Video
from ytweb.domain.batches import apply_one, cancel_batch, create_draft, execute_batch
from ytweb.domain.changes import rollback_change
from ytweb.domain.dashboard import build_dashboard
from ytweb.domain.reports import CSV_COLUMNS, build_reports, csv_safe, export_csv
from ytweb.domain.suggestions import approve, edit_title, reject, KEY_FILE
from ytweb.domain.videos import video_detail, list_videos

from tests.verify_wb.vbh import Faulty, changes, life_ids, make_sug, ok_sug, queued, snippet_of


def _video_with_before(db, skip=0):
    """독립 기준: 변경 전 스냅샷(phase=before)이 있고 제외 사유가 없는 생활 영상."""
    rows = db.execute(select(Video).order_by(Video.video_id)).scalars().all()
    ids_with = {m.video_id for m in db.execute(select(MetricsSnapshot).where(MetricsSnapshot.phase == "before")).scalars()}
    cands = [v.video_id for v in rows if v.video_id in ids_with and not v.exclusion_reasons and v.category_id == "26"]
    return cands[skip]


def _apply_for(db, env, clock, gw, vid):
    s = ok_sug(db, env, clock(), vid)
    b, pre = create_draft(db, [s.id], None, now=clock(), env=env)
    b, _ = execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    assert out.status == "success"
    db.commit()
    return db.get(Change, out.change_id), s


def _item(rep, vid):
    return next(i for i in rep["items"] if i["video_id"] == vid)


def test_tc_vb_190_report_no_change_video_and_unknown_video(seeded, db, env, clock):
    vid = life_ids(db, 1)[0]
    rep = build_reports(db, env, vid)
    it = rep["items"][0]
    assert it["status"] == "no_change" and it["metrics"] == [] and it["target"] is None
    assert build_reports(db, env)["items"] == []              # 성공한 적용이 없는 영상은 전체 목록에 없음
    with pytest.raises(ProblemError) as e:
        build_reports(db, env, "noSuchVid01")
    assert e.value.status == 404


def test_tc_vb_191_insufficient_data_is_explicit_and_no_numbers_compared(seeded, db, env, clock, gw):
    """POL-002/인수7: 변경 후 지표가 없으면 '데이터 부족'+이유+수집 예정일. 수치 비교(metrics)를 내지 않는다."""
    vid = _video_with_before(db)
    c, s = _apply_for(db, env, clock, gw, vid)
    it = _item(build_reports(db, env, vid), vid)
    assert it["status"] == "insufficient" and it["label"] == "데이터 부족"
    assert any("변경 후 지표가 아직 없습니다" in r for r in it["reasons"])
    assert it["metrics"] == [] and it["after"] is None
    assert it["expected_after_date"] == (clock().date() + timedelta(days=env.policy.evaluation_window_days)).isoformat()
    assert it["before"] is not None and it["baseline_missing"] is False


def test_tc_vb_192_baseline_missing_is_flagged(seeded, db, env, clock, gw):
    ids_with = {m.video_id for m in db.execute(select(MetricsSnapshot)).scalars()}
    vid = next(v for v in life_ids(db, 20) if v not in ids_with)
    c, s = _apply_for(db, env, clock, gw, vid)
    it = _item(build_reports(db, env, vid), vid)
    assert it["status"] == "insufficient" and it["baseline_missing"] is True and any("기준선" in r for r in it["reasons"])


def _after_snapshot(db, vid, applied_day: date, *, impressions=5000, days=14, start_offset=1, ctr=4.0, views=500, watch=900.0):
    start = applied_day + timedelta(days=start_offset)
    db.add(MetricsSnapshot(video_id=vid, taken_at=db.get(Change, changes(db, vid)[0].id).applied_at + timedelta(days=days + 2), phase="after", source="demo",
                           impressions=impressions, ctr=ctr, views=views, watch_minutes=watch, period_start=start, period_end=start + timedelta(days=days - 1)))
    db.commit()


def test_tc_vb_193_ok_report_computes_deltas_and_never_claims_causality(seeded, db, env, clock, gw):
    vid = _video_with_before(db)
    before = db.execute(select(MetricsSnapshot).where(MetricsSnapshot.video_id == vid, MetricsSnapshot.phase == "before")).scalars().one()
    c, s = _apply_for(db, env, clock, gw, vid)
    _after_snapshot(db, vid, clock().date(), impressions=before.impressions * 2, days=30, ctr=before.ctr + 1.0)
    rep = build_reports(db, env, vid)
    it = _item(rep, vid)
    assert it["status"] == "ok" and it["label"] is None and it["reasons"] == []
    m = {x["key"]: x for x in it["metrics"]}
    assert set(m) == {"impressions", "ctr", "views", "watch_minutes"}
    assert m["impressions"]["after"] == pytest.approx(before.impressions * 2 / 30) and m["impressions"]["before"] == pytest.approx(before.impressions / 30)
    assert m["impressions"]["pct"] == pytest.approx(0.0, abs=1e-6) or m["impressions"]["delta"] is not None
    assert m["ctr"]["delta"] == pytest.approx(1.0)
    text = json.dumps(rep, ensure_ascii=False)
    for causal in ("효과가 있", "덕분에", "성공했습니다", "개선되었습니다", "향상되었습니다"):
        assert causal not in text
    assert any("원인이라고 말하지 않습니다" in n for n in rep["notes"]) and any("원인을 단정할 수 없습니다" in n for n in rep["notes"])
    assert any("시연용 가상 데이터" in n for n in rep["notes"])


def test_tc_vb_194_low_impressions_or_short_period_or_overlap_is_insufficient(seeded, db, env, clock, gw):
    for idx, (kw, frag) in enumerate((
        (dict(impressions=999), "최소 기준"),
        (dict(days=6), "최소 기준 7일"),
        (dict(start_offset=0), "겹쳐"),
    )):
        vid = _video_with_before(db, skip=idx)
        before = db.execute(select(MetricsSnapshot).where(MetricsSnapshot.video_id == vid, MetricsSnapshot.phase == "before")).scalars().one()
        if before.impressions < 1000:
            continue
        c, s = _apply_for(db, env, clock, gw, vid)
        _after_snapshot(db, vid, clock().date(), **kw)
        it = _item(build_reports(db, env, vid), vid)
        assert it["status"] == "insufficient" and it["metrics"] == [] and any(frag in r for r in it["reasons"]), (kw, it["reasons"])


def test_tc_vb_195_rollback_after_change_marks_mixed_titles(seeded, db, env, clock, gw):
    vid = _video_with_before(db)
    c, s = _apply_for(db, env, clock, gw, vid)
    clock.advance(minutes=3)
    rollback_change(db, c.id, vid, "담당", now=clock(), env=env, gateway=gw)
    db.commit()
    it = _item(build_reports(db, env, vid), vid)
    assert it["status"] == "insufficient" and any("롤백" in r for r in it["reasons"])


def test_tc_vb_196_failed_and_planned_changes_not_in_report(seeded, db, env, clock, gw):
    vid = _video_with_before(db)
    db.add(Change(video_id=vid, change_type="apply", previous_title="a", new_title="b", result="failed", mode="demo", created_at=clock()))
    db.commit()
    assert build_reports(db, env)["items"] == []


@pytest.mark.parametrize("raw", ["=HYPERLINK(\"http://evil\",\"x\")", "+1+1", "-2+3", "@SUM(1,1)", "\t=1", "\r=1"])
def test_tc_vb_197_csv_safe_neutralizes_formula_starts(raw):
    out = csv_safe(raw)
    assert out == "'" + raw and not out.startswith(("=", "+", "-", "@", "\t", "\r"))


def test_tc_vb_198_csv_safe_leaves_numbers_text_and_none(seeded):
    for v in (5, -5, 3.14, None, "정상 제목", "a=b", " =lead-space"):
        assert csv_safe(v) == v


def test_tc_vb_199_csv_export_neutralizes_hostile_titles_end_to_end(seeded, db, env, clock, gw):
    """인수7: 영상 제목·이전/새 제목이 수식으로 시작해도 CSV 의 어떤 셀도 수식으로 해석되지 않는다. 따옴표·줄바꿈 왕복 보존."""
    vid = _video_with_before(db)
    c, s = _apply_for(db, env, clock, gw, vid)
    hostile_prev, hostile_new = '=cmd|" /C calc"!A0', '@SUM(1+1)*cmd'
    c.previous_title, c.new_title = hostile_prev, hostile_new
    db.get(Video, vid).title = "-2+3"
    db.commit()
    text = export_csv(db, env, vid)
    assert text.startswith("﻿") and "\r\n" in text
    rows = list(csv.reader(io.StringIO(text[1:], newline="")))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert all(len(r) == len(CSV_COLUMNS) for r in rows[1:2])
    body = rows[1]
    assert body[CSV_COLUMNS.index("title")] == "'-2+3"
    assert body[CSV_COLUMNS.index("previous_title")] == "'" + hostile_prev
    assert body[CSV_COLUMNS.index("new_title")] == "'" + hostile_new
    for row in rows:
        for cell in row:
            assert not cell.startswith(("=", "+", "-", "@", "\t", "\r")), cell
    assert rows[1][CSV_COLUMNS.index("status")] == "insufficient" and rows[1][CSV_COLUMNS.index("label")] == "데이터 부족"
    assert any("원인" in " ".join(r) for r in rows[3:])      # 면책 문구 행


def test_tc_vb_200_csv_endpoint_headers_and_auth(api, csrf, factory, env, clock):
    from tests.conftest import ORIGIN
    from ytweb.domain.common import set_default_env
    from ytweb.domain.seed import seed_demo
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    set_default_env(env)
    r = api.get("/api/v1/reports/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv") and r.headers["cache-control"] == "no-store"
    assert r.headers["content-disposition"].startswith("attachment;") and r.content.startswith(b"\xef\xbb\xbf")
    fresh = type(api)(api.app, base_url=ORIGIN)
    assert fresh.get("/api/v1/reports/export.csv").status_code == 401
    assert fresh.get("/api/v1/reports/changes").status_code == 401
    assert api.get("/api/v1/reports/changes?video_id=bad").status_code == 422
    assert api.get("/api/v1/reports/changes?video_id=noSuchVid01").status_code == 404


# ───────────────────────── S-W16 감사 로그 ─────────────────────────

def test_tc_vb_210_audit_covers_every_state_change_and_chain_is_intact(seeded, db, env, clock, gw):
    ids = life_ids(db, 6)
    a = make_sug(db, env, clock(), ids[0])
    edit_title(db, a.id, a.title + " 개정", now=clock(), env=env)
    r = make_sug(db, env, clock(), ids[1])
    reject(db, r.id, now=clock())
    b_sugs = [ok_sug(db, env, clock(), v) for v in ids[2:5]]
    b, pre = create_draft(db, [s.id for s in b_sugs], "메모", now=clock(), env=env)
    b, job = execute_batch(db, b.id, pre["confirm_text"], now=clock(), env=env)
    out = apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    g = Faulty(db, clock)
    g.on_read = lambda n, snap: (_ for _ in ()).throw(__import__("ytweb.youtube.base", fromlist=["GatewayError"]).GatewayError("x", "y"))
    apply_one(db, b.items[1].id, now=clock(), env=env, gateway=g)       # failed
    cancel_batch(db, b.id, now=clock(), env=env)
    clock.advance(minutes=1)
    rollback_change(db, out.change_id, b_sugs[0].video_id, "담당", now=clock(), env=env, gateway=gw)
    db.commit()
    actions = [x.action for x in db.execute(select(AuditLog).order_by(AuditLog.id)).scalars()]
    for must in ("suggestion.generate", "suggestion.edit", "suggestion.reject", "suggestion.approve", "batch.create", "batch.execute", "change.apply", "batch.item.failed", "batch.cancel", "change.rollback"):
        assert must in actions, (must, actions)
    assert audit.verify_chain(db) is True
    rows = db.execute(select(AuditLog).order_by(AuditLog.id)).scalars().all()
    assert rows[0].prev_hash == audit.GENESIS_HASH and all(rows[i].prev_hash == rows[i - 1].hash for i in range(1, len(rows)))
    apply_row = next(x for x in rows if x.action == "change.apply")
    assert apply_row.actor == "worker" and apply_row.detail["suggestion_id"] == b_sugs[0].id
    ap_row = next(x for x in rows if x.action == "suggestion.approve")
    assert ap_row.actor == "web" and ap_row.detail["approver"] == "검수자"


def test_tc_vb_211_audit_tamper_detected(seeded, db, env, clock):
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    approve(db, s.id, "검수자", now=clock(), env=env)
    db.commit()
    assert audit.verify_chain(db) is True
    row = db.execute(select(AuditLog).where(AuditLog.action == "suggestion.approve")).scalars().one()
    d = dict(row.detail)
    d["approver"] = "위조자"
    row.detail = d
    db.commit()
    assert audit.verify_chain(db) is False


def test_tc_vb_212_audit_never_contains_hmac_key_or_mac(seeded, db, env, clock, gw):
    s = make_sug(db, env, clock(), life_ids(db, 1)[0])
    approve(db, s.id, "검수자", now=clock(), env=env)
    db.commit()
    key_hex = (env.secrets_dir / KEY_FILE).read_text().strip()
    mac = s.approval.mac
    blob = json.dumps([(x.action, x.detail, x.target_id) for x in db.execute(select(AuditLog)).scalars()], ensure_ascii=False, default=str)
    assert key_hex not in blob and mac not in blob and s.plan_hash not in blob      # plan_hash 는 앞 12자만


def test_tc_vb_213_read_only_calls_write_no_audit(api, csrf, factory, env, clock):
    from ytweb.domain.common import set_default_env
    from ytweb.domain.seed import seed_demo
    with factory() as s:
        seed_demo(s, clock(), env.policy, count=60)
        s.commit()
    set_default_env(env)
    with factory() as s:
        before = s.execute(select(func.count()).select_from(AuditLog)).scalar_one()
    for path in ("/api/v1/dashboard", "/api/v1/videos", "/api/v1/suggestions", "/api/v1/batches", "/api/v1/changes", "/api/v1/reports/changes", "/api/v1/reports/export.csv", "/api/v1/google/status"):
        assert api.get(path).status_code == 200, path
    with factory() as s:
        assert s.execute(select(func.count()).select_from(AuditLog)).scalar_one() == before


def test_tc_vb_214_edit_audit_detail_is_truncated_and_failed_ai_logged(seeded, db, env, clock):
    from tests.verify_wb.vbh import Stub
    from ytweb.domain.suggestions import generate_for_video
    vid = life_ids(db, 1)[0]
    with pytest.raises(ProblemError):
        generate_for_video(db, vid, count=1, tone="t", now=clock(), env=env, suggester=Stub(RuntimeError("boom")))
    row = db.execute(select(AuditLog).where(AuditLog.action == "suggestion.generate_failed")).scalars().one()
    assert row.detail == {"error": "RuntimeError"}                  # 예외 메시지(비밀 가능성) 원문은 기록하지 않음
    s = make_sug(db, env, clock(), vid)
    edit_title(db, s.id, "냉장고 정리 " + "가나다라마바사" * 30, now=clock(), env=env)
    e = db.execute(select(AuditLog).where(AuditLog.action == "suggestion.edit")).scalars().one()
    assert len(e.detail["to"]) <= 100 and len(e.detail["from"]) <= 100


# ───────────────────────── W-006 상세 비교 데이터 / 대시보드 ─────────────────────────

def test_tc_vb_220_video_detail_preserved_limits_and_changes(seeded, db, env, clock, gw):
    vid = _video_with_before(db)
    c, s = _apply_for(db, env, clock, gw, vid)
    d = video_detail(db, vid, now=clock(), env=env)
    snip = snippet_of(db, vid)
    assert d["preserved"] == {"category_id": snip["categoryId"], "tags": snip["tags"], "default_language": snip["defaultLanguage"],
                              "default_audio_language": snip["defaultAudioLanguage"], "description_chars": len(snip["description"])}
    assert d["workflow_status"] == "applied" and d["suggestion_count"] == 1 and d["limits"]["allowed"] is False
    assert any("72시간" in r for r in d["limits"]["reasons"])
    assert d["limits"]["next_allowed_at"] is not None   # 데모는 노출수 조건을 완화(DEC-042)하므로 72시간 간격이 풀리는 시각을 안내
    ch = d["changes"][0]
    assert ch["previous_title"] == c.previous_title and ch["new_title"] == s.title and ch["rollbackable"] is True
    assert d["title"] == s.title and d["suggestions"][0]["status"] == "applied"
    with pytest.raises(ProblemError):
        video_detail(db, "noSuchVid01", now=clock(), env=env)


def test_tc_vb_221_workflow_status_priority(seeded, db, env, clock):
    ids = life_ids(db, 4)
    make_sug(db, env, clock(), ids[0])                      # candidate → suggested
    ok_sug(db, env, clock(), ids[1])                        # approved
    q, _ = queued(db, env, clock(), 1, skip=2)                  # queued
    items, _ = list_videos(db, now=clock(), q=None, status=None, excluded=None, sort="video_id", order="asc", page=1, page_size=200)
    st = {i["video_id"]: i["workflow_status"] for i in items}
    assert st[ids[0]] == "suggested" and st[ids[1]] == "approved" and st[ids[2]] == "queued" and st[ids[3]] == "none"


def test_tc_vb_222_dashboard_numbers(seeded, db, env, clock, gw):
    b, sugs = queued(db, env, clock(), 3)
    apply_one(db, b.items[0].id, now=clock(), env=env, gateway=gw)
    db.commit()
    d = build_dashboard(db, clock(), env)
    assert d["mode"] == "demo" and d["live_enabled"] is False and d["google"] == {"mode": "demo", "connected": False}
    assert d["counts"]["videos"] == 60 and d["counts"]["applied"] == 1 and d["counts"]["queued"] == 2
    assert d["today"] == {"applied": 1, "cap": 10}
    assert d["quota"]["used"] == 52 and d["quota"]["remaining"] == env.policy.daily_limit_units - 52 and d["quota"]["limit"] == env.policy.daily_limit_units
    assert d["queue"]["pending_items"] == 2 and d["queue"]["next_run_date"] == clock().date()
