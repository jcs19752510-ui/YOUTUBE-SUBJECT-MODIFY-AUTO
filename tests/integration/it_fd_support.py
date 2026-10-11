"""F-D 통합 테스트(test_it_fd.py) 공용 도우미(테스트 파일이 아니다).

CLI 진입점(ytitle.cli.main)으로 fetch(WU-2) -> WU-4 이력 -> report(WU-6)를 엮는다.
실제 구글/네트워크 호출은 없다: 가짜 YouTube/Analytics 서비스(읽기 메서드 4개만 존재)와 임시 DB만 쓴다.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httplib2
from googleapiclient.errors import HttpError

from wu4_support import add_candidate, make_settings

from ytitle import cli, db
from ytitle.commands import fetch as fetch_cmd
from ytitle.history import begin_change, begin_rollback, finish_change, plan_rollback
from ytitle.timeutil import FixedClock, utc_iso
from ytitle.updater import create_plan

VID = "abc123DEF45"
VID2 = "xyz789GHI01"
SECRET = "ya29.FAKE-TOKEN-ITFD-123456"
READ_METHODS = {("channels", "list"), ("playlistItems", "list"), ("videos", "list"), ("reports", "query")}
FULL = ("video", "views", "estimatedMinutesWatched", "videoThumbnailImpressions", "videoThumbnailImpressionsClickRate")


def at(y, mo, d, h=12, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


def http_error(status, reason="", message="본문"):
    body = {"error": {"code": status, "message": message, "errors": [{"message": message, "domain": "x", "reason": reason}]}}
    return HttpError(httplib2.Response({"status": str(status)}), json.dumps(body).encode("utf-8"), uri=f"https://www.googleapis.com/x?key=SECRETKEY-{SECRET}")


class _Req:
    def __init__(self, api, key, kw):
        self.api, self.key, self.kw = api, key, kw

    def execute(self):
        self.api.calls.append((self.key, self.kw))
        out = self.api.handlers[self.key](self.kw)
        if isinstance(out, BaseException):
            raise out
        return out


class _Res:
    def __init__(self, api, name):
        self._api, self._name = api, name

    def __getattr__(self, method):
        if (self._name, method) not in READ_METHODS:
            self._api.write_attempts.append(f"{self._name}.{method}")
            raise AttributeError(f"허용되지 않은 호출: {self._name}.{method}")
        return lambda **kw: _Req(self._api, f"{self._name}.{method}", kw)


class Api:
    def __init__(self):
        self.calls, self.handlers, self.write_attempts = [], {}, []

    def on(self, key, handler):
        self.handlers[key] = handler
        return self

    def kwargs(self, key):
        return [kw for k, kw in self.calls if k == key]

    def __getattr__(self, name):
        if name in ("channels", "playlistItems", "videos", "reports"):
            return lambda: _Res(self, name)
        if name.startswith("_"):
            raise AttributeError(name)
        self.write_attempts.append(name)
        raise AttributeError(name)


@dataclass
class Result:
    code: int
    out: str
    err: str

    @property
    def all(self) -> str:
        return self.out + self.err


class World:
    """프로젝트 폴더 하나 + 가짜 구글 서비스 + CLI 실행기."""

    def __init__(self, project: Path, monkeypatch):
        self.project = project
        (project / "exports").mkdir(exist_ok=True)
        self.titles: dict[str, str] = {VID: "현재 제목", VID2: "둘째 영상 제목"}
        self.metrics: dict[str, dict] = {}   # vid -> {views, minutes, impressions, ctr}
        self.reject_ctr = False
        self.analytics_error: BaseException | None = None
        self.kinds: list[str] = []
        self.yt = Api().on("videos.list", self._videos)
        self.an = Api().on("reports.query", self._query)
        monkeypatch.setattr(fetch_cmd.authmod, "load_credentials", lambda kind, settings: self.kinds.append(kind) or "CREDS")
        monkeypatch.setattr(fetch_cmd, "build_services", lambda creds: (self.yt, self.an))

    def _videos(self, kw):
        items = []
        for i in kw["id"].split(","):
            if i in self.titles:
                items.append({"id": i, "snippet": {"title": self.titles[i], "description": "설명", "categoryId": "26", "liveBroadcastContent": "none"},
                              "status": {"privacyStatus": "public", "madeForKids": False}, "contentDetails": {"duration": "PT1M"}})
        return {"items": items}

    def _query(self, kw):
        if self.analytics_error is not None:
            return self.analytics_error
        names = ["video"] + kw["metrics"].split(",")
        if self.reject_ctr and "videoThumbnailImpressions" in kw["metrics"]:
            return http_error(400, "badRequest", "unknown metric")
        col = {"views": "views", "estimatedMinutesWatched": "minutes", "videoThumbnailImpressions": "impressions", "videoThumbnailImpressionsClickRate": "ctr"}
        rows = []
        for v in kw["filters"].replace("video==", "").split(","):
            if v in self.metrics:
                rows.append([v] + [self.metrics[v].get(col[n]) for n in names[1:]])
        return {"columnHeaders": [{"name": n} for n in names], "rows": rows}

    # ---- 실행
    def run(self, argv, now, **kw) -> Result:
        import io
        out, err = io.StringIO(), io.StringIO()
        kw.setdefault("env", {})
        code = cli.main(["--base-dir", str(self.project)] + list(argv), out=out, err=err, clock=FixedClock(now), **kw)
        return Result(code, out.getvalue(), err.getvalue())

    def csv(self, name: str, text: str, enc="utf-8") -> str:
        (self.project / "exports" / name).write_bytes(text.encode(enc))
        return f"exports/{name}"

    def conn(self):
        c = db.connect(self.project / "data" / "ytitle.sqlite3")
        db.migrate(c)
        return c

    def settings(self):
        return make_settings(self.project)

    def log_text(self) -> str:
        p = self.project / "data" / "logs" / "ytitle.log"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    # ---- WU-4 실제 이력 API로 변경/롤백 성공 행 만들기 (DB 계약)
    def apply_change(self, vid, new_title, created: datetime, applied: datetime | None = None) -> int:
        c = self.conn()
        s = self.settings()
        cid = add_candidate(c, vid, new_title, status="approved")
        plan = create_plan(c, s, FixedClock(created), cid)
        chg = begin_change(c, s, plan, approver="홍길동", approved_at=created, run_id="itfd", now=created)
        finish_change(c, chg, "success", applied or created)
        c.close()
        self.titles[vid] = new_title   # 유튜브 쪽 제목이 바뀐 것으로 본다
        return chg

    def rollback_change(self, change_id, when: datetime) -> int:
        self.run(["fetch", "--video", self._vid_of(change_id)], when)  # 최신 snippet 재조회(WU-2)
        c = self.conn()
        s = self.settings()
        plan = plan_rollback(c, s, FixedClock(when), change_id)
        rid = begin_rollback(c, plan, approver="홍길동", typed_video_id=plan.video_id, run_id="itfd", now=when)
        finish_change(c, rid, "success", when)
        c.close()
        self.titles[plan.video_id] = plan.restore_title
        return rid

    def _vid_of(self, change_id):
        c = self.conn()
        v = c.execute("SELECT video_id FROM title_changes WHERE id=?", (change_id,)).fetchone()[0]
        c.close()
        return v


def snaps(world: World, vid=None):
    c = world.conn()
    q = "SELECT * FROM metrics_snapshots" + (" WHERE video_id=?" if vid else "") + " ORDER BY id"
    rows = c.execute(q, (vid,) if vid else ()).fetchall()
    c.close()
    return rows


def dump(world: World, skip=("run_logs", "sqlite_sequence")):
    c = world.conn()
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'") if r[0] not in skip]
    data = {n: [tuple(r) for r in c.execute(f"SELECT * FROM {n}")] for n in names}
    c.close()
    return data


HEAD_EN = "Content,Views,Impressions,Impressions click-through rate (%),Watch time (hours)\n"
HEAD_KO = "콘텐츠,조회수,노출수,노출 클릭률(%),시청 시간(단위: 시간)\n"


def csv_line(vid, views, imps, ctr, hours):
    return f'{vid},"{views:,}","{imps:,}",{ctr}%,{hours}\n'
