"""WU-4 테스트 공용 도우미(테스트 파일이 아니다). 실제 구글 호출 없이 임시 DB와 가짜 데이터만 쓴다."""
from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from ytitle import db as dbmod
from ytitle.config import load_settings
from ytitle.timeutil import FixedClock, utc_iso

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
VID = "abc123DEF45"
SNIPPET = {
    "publishedAt": "2025-01-01T00:00:00Z",
    "channelId": "UCxxxxxxxxxxxxxxxxxxxxxx",
    "title": "겨울 전기요금",
    "description": "보일러 온도를 낮추는 방법\n줄바꿈과 한글 설명입니다.",
    "tags": ["전기요금", "난방", "시니어"],
    "categoryId": "26",
    "defaultLanguage": "ko",
    "liveBroadcastContent": "none",
    "localized": {"title": "겨울 전기요금", "description": "보일러 온도를 낮추는 방법\n줄바꿈과 한글 설명입니다."},
}


def clock(moment: datetime = NOW) -> FixedClock:
    return FixedClock(moment)


def ts(moment: datetime) -> str:
    return utc_iso(moment)


def open_db(path):
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    return conn


def make_settings(project, **over):
    s = load_settings(project, env={})
    return replace(s, **over) if over else s


def add_video(conn, vid=VID, snippet=None, *, fetched_at=None, privacy="public", kids=0, live="none", duration=600, title=None):
    sn = dict(SNIPPET if snippet is None else snippet)
    conn.execute(
        "INSERT OR REPLACE INTO videos (video_id,title,category_id,privacy_status,made_for_kids,live_broadcast_content,duration_sec,description_excerpt,snippet_json,fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (vid, title if title is not None else sn.get("title", "x"), sn.get("categoryId"), privacy, kids, live, duration, (sn.get("description") or "")[:500], json.dumps(sn, ensure_ascii=False), fetched_at or ts(NOW - timedelta(hours=1))),
    )
    conn.commit()


def add_candidate(conn, vid=VID, title="겨울철 전기요금 줄이는 난방 습관", *, status="filtered", result="pass", reasons=None, dictionary_hash="9f2a1c4e"):
    cur = conn.execute(
        "INSERT INTO title_candidates (video_id,candidate_title,evidence,source,topic,strict_mode,validation_result,validation_reasons_json,dictionary_hash,file_name,file_sha256,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (vid, title, "근거", "human", "life", 0, result, json.dumps(reasons or [], ensure_ascii=False), dictionary_hash, f"{vid}.json", "sha", status, ts(NOW), ts(NOW)),
    )
    conn.commit()
    return cur.lastrowid


def add_change(conn, vid=VID, *, change_type="apply", result="success", at=None, cid=None, prev="이전", new="새", backup=None, error=None):
    when = ts(at) if at is not None else None
    cur = conn.execute(
        "INSERT INTO title_changes (video_id,candidate_id,change_type,previous_title,new_title,backup_snippet_json,approver,approved_at,plan_hash,result,error_code,applied_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (vid, cid, change_type, prev, new, backup, "홍길동", when, "h", result, error, when if result == "success" else None, when or ts(NOW)),
    )
    conn.commit()
    return cur.lastrowid


def add_metric(conn, vid=VID, *, impressions, period_start, phase="after", taken_at=None, source="api"):
    conn.execute(
        "INSERT INTO metrics_snapshots (video_id,taken_at,phase,source,period_start,period_end,impressions) VALUES (?,?,?,?,?,?,?)",
        (vid, ts(taken_at or NOW), phase, source, period_start, period_start, impressions),
    )
    conn.commit()
