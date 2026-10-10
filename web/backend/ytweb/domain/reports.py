"""성과 비교 리포트와 CSV(W-013). 계산은 ytitle.report.build_report 를 그대로 쓴다(데이터 부족 판정·원인 단정 금지 규칙 포함)."""
from __future__ import annotations

import csv
import dataclasses
import io
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ytitle.report import CAUSAL_NOTE, INSUFFICIENT_LABEL, LIMIT_NOTE, Rules, Snapshot, VideoReport, build_report
from ytitle.report import Change as ReportChange
from ytitle.timeutil import utc_iso

from ytweb.core.errors import ProblemError
from ytweb.db.models import Change, MetricsSnapshot, Video
from ytweb.domain.common import Env

MAX_REPORT_VIDEOS = 200
EXTRA_NOTE = "데이터가 부족하면 결론을 내지 않고 '데이터 부족'과 그 이유만 표시합니다. 표의 숫자는 참고용입니다."
SOURCE_NOTE = "데모 모드의 성과 수치는 시연용 가상 데이터입니다."
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> object:
    """CSV 수식 주입 방지: 문자열이 = + - @ 탭 CR 로 시작하면 앞에 작은따옴표를 붙여 엑셀이 수식으로 읽지 못하게 한다. 숫자는 그대로."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def _changes_for(session: Session, video_id: str) -> tuple[ReportChange, ...]:
    rows = session.execute(select(Change).where(Change.video_id == video_id, Change.result == "success").order_by(func.coalesce(Change.applied_at, Change.created_at), Change.id)).scalars()
    return tuple(ReportChange(c.id, c.change_type, c.previous_title, c.new_title, utc_iso(c.applied_at or c.created_at), c.result, c.approver) for c in rows)


def _snapshots_for(session: Session, video_id: str) -> tuple[Snapshot, ...]:
    rows = session.execute(select(MetricsSnapshot).where(MetricsSnapshot.video_id == video_id).order_by(MetricsSnapshot.taken_at, MetricsSnapshot.id)).scalars()
    iso = lambda d: d.isoformat() if isinstance(d, date) else None  # noqa: E731
    return tuple(Snapshot(m.id, utc_iso(m.taken_at), m.phase, m.source, iso(m.period_start), iso(m.period_end), m.impressions, m.ctr, m.views, m.watch_minutes) for m in rows)


def _report_dict(r: VideoReport) -> dict:
    return {
        "video_id": r.video_id,
        "title": r.title,
        "status": r.status,
        "label": INSUFFICIENT_LABEL if r.status == "insufficient" else None,
        "baseline_missing": r.baseline_missing,
        "reasons": list(r.reasons),
        "notes": list(r.notes),
        "changes": [dataclasses.asdict(c) for c in r.changes],
        "target": dataclasses.asdict(r.target) if r.target else None,
        "before": dataclasses.asdict(r.before) if r.before else None,
        "after": dataclasses.asdict(r.after) if r.after else None,
        "metrics": [dataclasses.asdict(m) for m in r.metrics],
        "expected_after_date": r.expected_after_date,
    }


def build_reports(session: Session, env: Env, video_id: str | None = None) -> dict:
    rules = Rules.from_settings(env.policy)
    if video_id is not None:
        video = session.get(Video, video_id)
        if video is None:
            raise ProblemError(404, "video_not_found", "영상을 찾을 수 없습니다.", hint="영상 ID를 확인하세요.")
        ids = [video_id]
    else:
        ids = list(session.execute(
            select(Change.video_id).where(Change.result == "success", Change.change_type == "apply").group_by(Change.video_id)
            .order_by(func.max(func.coalesce(Change.applied_at, Change.created_at)).desc(), Change.video_id).limit(MAX_REPORT_VIDEOS)
        ).scalars())
    titles = dict(session.execute(select(Video.video_id, Video.title).where(Video.video_id.in_(ids))).all()) if ids else {}
    items = [_report_dict(build_report(vid, titles.get(vid), _changes_for(session, vid), _snapshots_for(session, vid), rules)) for vid in ids]
    return {"items": items, "notes": [LIMIT_NOTE, CAUSAL_NOTE, EXTRA_NOTE, SOURCE_NOTE]}


CSV_COLUMNS = (
    "video_id", "title", "status", "label", "changed_at", "previous_title", "new_title",
    "before_period", "before_impressions", "before_ctr", "before_views", "before_watch_minutes",
    "after_period", "after_impressions", "after_ctr", "after_views", "after_watch_minutes", "reasons", "note",
)


def _period(s: dict | None) -> str:
    return f"{s['period_start']}~{s['period_end']}" if s and s.get("period_start") and s.get("period_end") else ""


def _metric_cells(snap: dict | None) -> list:
    return [("" if snap is None or snap.get(k) is None else snap[k]) for k in ("impressions", "ctr", "views", "watch_minutes")]


def export_csv(session: Session, env: Env, video_id: str | None = None) -> str:
    data = build_reports(session, env, video_id)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for it in data["items"]:
        t, b, a = it["target"], it["before"], it["after"]
        row = [
            it["video_id"], it["title"] or "", it["status"], it["label"] or "", t["at"] if t else "", t["previous_title"] if t else "", t["new_title"] if t else "",
            _period(b), *_metric_cells(b), _period(a), *_metric_cells(a), " | ".join(it["reasons"]), " | ".join(it["notes"]),
        ]
        writer.writerow([csv_safe(v) for v in row])
    writer.writerow([])
    for note in data["notes"]:
        writer.writerow([csv_safe(note)])
    return "﻿" + buf.getvalue()  # 엑셀이 한글을 깨뜨리지 않게 BOM 을 붙인다
