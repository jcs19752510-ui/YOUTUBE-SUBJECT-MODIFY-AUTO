"""WU-5 테스트 공용 도우미(테스트 파일이 아니다). 실제 구글 호출 없이 가짜 서버·임시 DB·임시 폴더만 쓴다."""
from __future__ import annotations

import copy
import json
import logging
import socket
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httplib2
from googleapiclient.errors import HttpError
from wu4_support import NOW, SNIPPET, VID, add_candidate, add_metric, add_video, open_db, ts

from ytitle import approvals
from ytitle.config import load_settings
from ytitle.errors import AuthError
from ytitle.live_guard import LiveEnv
from ytitle.quota import QuotaManager
from ytitle.timeutil import FixedClock
from ytitle.ui import UiOptions, confirm_by_typing
from ytitle.updater import create_plan
from ytitle.youtube_read import YouTubeReader

FAKE_ACCESS = "ya29.FAKEWRITEACCESSTOKEN0123456789abcdef"
FAKE_REFRESH = "1//0FAKEWRITEREFRESHTOKEN0123456789abcdefghij"
NEW_TITLE = "겨울철 전기요금 줄이는 난방 습관"
BASELINE_PHRASE = "지표없이진행"


def http_error(status: int, reason: str = "") -> HttpError:
    body = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode() if reason else b"{}"
    return HttpError(httplib2.Response({"status": status}), body)


class AppliedThenRaise:
    """서버는 변경을 반영했지만 응답이 오지 않은 상황(타임아웃 등)을 흉내 낸다."""

    def __init__(self, exc: BaseException):
        self.exc = exc


class _Req:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class _Videos:
    def __init__(self, server, events, mode):
        self._s, self._e, self._mode = server, events, mode

    def list(self, part=None, id=None):
        if self._mode != "read":
            raise AssertionError("쓰기 서비스로 조회하면 안 된다")
        return _Req(lambda: self._s.do_list(part, id))

    def update(self, part=None, body=None):
        if self._mode != "write":
            raise AssertionError("읽기 서비스로 쓰면 안 된다")
        return _Req(lambda: self._s.do_update(part, body))


class _Service:
    def __init__(self, server, events, mode):
        self._v = _Videos(server, events, mode)

    def videos(self):
        return self._v


class FakeServer:
    """가짜 YouTube. 업데이트는 YouTube처럼 snippet 전체를 본문으로 교체한다(본문에 없는 항목은 사라진다)."""

    def __init__(self, events: list, snippet: dict | None = None, vid: str = VID):
        self.events = events
        self.vid = vid
        self.items = {vid: {"id": vid, "snippet": copy.deepcopy(SNIPPET if snippet is None else snippet), "status": {"privacyStatus": "private", "madeForKids": False}, "contentDetails": {"duration": "PT10M"}}}
        self.update_calls: list[dict] = []
        self.list_calls: list[str] = []
        self.update_behaviors: list = []     # 호출마다 하나씩 소비: None=정상, 예외 인스턴스=raise, callable=(server, body) 후처리
        self.list_behaviors: list = []       # 조회마다 하나씩 소비: None=정상, 예외 인스턴스=raise
        self.drop_on_update: tuple[str, ...] = ()
        self.ignore_update = False

    def read_service(self):
        return _Service(self, self.events, "read")

    def write_service(self):
        return _Service(self, self.events, "write")

    def do_list(self, part, ids):
        self.list_calls.append(ids)
        self.events.append(("list", ids))
        if self.list_behaviors:
            b = self.list_behaviors.pop(0)
            if isinstance(b, BaseException):
                raise b
        return {"items": [copy.deepcopy(self.items[i]) for i in ids.split(",") if i in self.items]}

    def do_update(self, part, body):
        self.update_calls.append(copy.deepcopy({"part": part, "body": body}))
        self.events.append(("update", body["id"]))
        behavior = self.update_behaviors.pop(0) if self.update_behaviors else None
        if isinstance(behavior, BaseException):
            raise behavior
        raise_after = None
        if isinstance(behavior, AppliedThenRaise):
            behavior, raise_after = None, behavior.exc
        if not self.ignore_update:
            snippet = copy.deepcopy(body["snippet"])
            for k in self.drop_on_update:
                snippet.pop(k, None)
            self.items[body["id"]]["snippet"] = snippet
        if callable(behavior):
            behavior(self, body)
        if raise_after is not None:
            raise raise_after
        return {"id": body["id"], "snippet": copy.deepcopy(self.items.get(body["id"], {}).get("snippet"))}


class World:
    """게이트를 모두 통과하는 기본 상태(허용 목록·enable_live·승인·기준선·가짜 서버)를 만든다. 테스트는 여기서 한 가지씩 망가뜨린다."""

    def __init__(self, project, tmp_path, *, enable_live=True, allowlist=(VID,), baseline=True, approve=True, now: datetime = NOW, settings_over=None, candidate_title=NEW_TITLE):
        self.project = project
        self.tokens = tmp_path / "tokens"
        local = {"live": {"enable_live": enable_live, "live_allowlist": list(allowlist)}}
        (project / "config").mkdir(exist_ok=True)
        (project / "config" / "settings.local.yaml").write_text(json.dumps(local), encoding="utf-8")   # JSON은 YAML의 부분집합
        self.settings = load_settings(project, env={"YT_TOKEN_DIR": str(self.tokens)})
        if settings_over:
            self.settings = replace(self.settings, **settings_over)
        self.conn = open_db(self.settings.db_path)
        self.clock = FixedClock(now)
        self.events: list = []
        self.server = FakeServer(self.events)
        add_video(self.conn, fetched_at=ts(now - timedelta(hours=1)))
        self.cid = add_candidate(self.conn, status="filtered", title=candidate_title)
        self.said: list[str] = []
        self.sleeps: list[float] = []
        self.video_answer = "ok"         # ok | wrong | blank | eof
        self.baseline_answer = "ok"
        self.prompts: list[str] = []
        self.write_token_loads = 0
        self.write_auth_error: Exception | None = None
        self.write_service_factory = None
        if baseline:
            add_metric(self.conn, phase="before", impressions=500, period_start="2026-09-01", taken_at=now - timedelta(days=5))
        self.approval = None
        if approve:
            self.approve()

    # ── 준비 ──
    def plan(self):
        return create_plan(self.conn, self.settings, self.clock, self.cid)

    def approve(self, **kw):
        plan = self.plan()
        self.approval = approvals.create_approval(
            self.settings, video_id=plan.video_id, candidate_id=self.cid, new_title=plan.new_title, plan_hash=plan.plan_hash,
            approver=kw.pop("approver", "홍길동"), now=self.clock.now(), ttl_hours=kw.pop("ttl_hours", 24), overwrite=True,
        )
        self.conn.execute("UPDATE title_candidates SET status='approved' WHERE id=?", (self.cid,))
        self.conn.commit()
        return self.approval

    def set(self, **over):
        self.settings = replace(self.settings, **over)

    def apply_change_row(self, **kw):
        from wu4_support import add_change

        return add_change(self.conn, **kw)

    # ── 가짜 협력 객체 ──
    def _input(self, prompt: str) -> str:
        self.prompts.append(prompt)
        expected = prompt.split("'")[1]
        mode = self.baseline_answer if expected == BASELINE_PHRASE else self.video_answer
        if mode == "eof":
            raise EOFError
        if mode == "interrupt":
            raise KeyboardInterrupt
        return {"ok": expected, "wrong": "엉뚱한입력", "blank": ""}[mode]

    def _confirm(self, expected: str) -> bool:
        self.events.append(("confirm", expected))
        return confirm_by_typing(expected, input_fn=self._input, output_fn=self.said.append)

    def _make_reader(self):
        self.events.append(("read_service", None))
        return YouTubeReader(self.server.read_service(), None, QuotaManager(self.conn, self.settings, self.clock), self.conn, self.settings, self.clock, sleep=self.sleeps.append, run_id="run1")

    def _make_write(self):
        self.events.append(("write_token", None))
        self.write_token_loads += 1
        if self.write_auth_error is not None:
            raise self.write_auth_error
        return self.server.write_service()

    def env(self) -> LiveEnv:
        return LiveEnv(
            conn=self.conn, settings=self.settings, clock=self.clock, run_id="run1", say=self.said.append, confirm=self._confirm, ui=UiOptions(),
            logger=logging.getLogger("ytitle.test"), make_reader=self._make_reader, make_write_service=self.write_service_factory or self._make_write, sleep=self.sleeps.append,
        )

    # ── 관찰 ──
    def changes(self):
        return [dict(r) for r in self.conn.execute("SELECT id, change_type, result, error_code, approver, plan_hash, previous_title, new_title, verify_result_json, backup_snippet_json FROM title_changes ORDER BY id")]

    def quota(self):
        return [tuple(r) for r in self.conn.execute("SELECT method, units, status FROM quota_usage ORDER BY id")]

    def candidate_status(self):
        return self.conn.execute("SELECT status FROM title_candidates WHERE id=?", (self.cid,)).fetchone()[0]

    def approval_file(self):
        return json.loads(approvals.approval_path(self.settings, VID, self.cid).read_text(encoding="utf-8"))

    def output(self) -> str:
        return "\n".join(self.said)

    def close(self):
        self.conn.close()


def fill_quota(conn, clock, units: int) -> None:
    """오늘(태평양 시간) 쿼터를 units만큼 이미 쓴 상태로 만든다."""
    from ytitle.timeutil import pt_date, utc_iso

    conn.execute("INSERT INTO quota_usage (pt_date, method, units, called_at, run_id, status) VALUES (?,?,?,?,?,?)", (pt_date(clock.now()).isoformat(), "prefill", units, utc_iso(clock.now()), "pre", "ok"))
    conn.commit()


def block_network(monkeypatch):
    """소켓 연결과 google build()를 막는다. 호출되면 테스트가 실패한다."""
    attempts = []

    def boom(*a, **k):
        attempts.append(a)
        raise AssertionError("네트워크/구글 호출 시도")

    monkeypatch.setattr(socket.socket, "connect", boom)
    import googleapiclient.discovery as disc

    monkeypatch.setattr(disc, "build", boom)
    return attempts


__all__ = ["AppliedThenRaise", "NOW", "SNIPPET", "VID", "World", "FakeServer", "http_error", "fill_quota", "block_network", "AuthError", "timedelta", "timezone", "NEW_TITLE", "BASELINE_PHRASE", "FAKE_ACCESS", "FAKE_REFRESH", "ts"]


def patch_services(monkeypatch, world: World) -> None:
    """CLI 테스트용: live_guard가 만드는 읽기/쓰기 서비스를 가짜 서버로 바꾼다(명령이 쓰는 DB 연결을 그대로 쓴다)."""
    from ytitle import live_guard

    def reader(ctx):
        world.events.append(("read_service", None))
        return YouTubeReader(world.server.read_service(), None, QuotaManager(ctx.conn, ctx.settings, ctx.clock), ctx.conn, ctx.settings, ctx.clock, sleep=world.sleeps.append, run_id=ctx.run_id)

    def writer(settings):
        return world._make_write()

    monkeypatch.setattr(live_guard, "make_reader", reader)
    monkeypatch.setattr(live_guard, "make_write_service", writer)


def cli_run(world: World, streams, argv, *, input_fn=None):
    from ytitle import cli

    return cli.main(["--base-dir", str(world.project)] + argv, out=streams.out, err=streams.err, env={"YT_TOKEN_DIR": str(world.tokens)}, clock=world.clock, input_fn=input_fn or world._input)
