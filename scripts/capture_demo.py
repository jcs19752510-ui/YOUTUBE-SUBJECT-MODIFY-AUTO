#!/usr/bin/env python3
"""실제 `youtube_title` CLI를 가짜 데이터로 돌려 실제 출력(stdout/stderr/종료 코드)을 `docs/demo/screens.json`에 저장한다.

실행(저장소 루트에서):
    PYTHONPATH=src python scripts/capture_demo.py [--out docs/demo/screens.json]

원칙
- 출력은 지어내지 않는다: `youtube_title.cli.main()`이 실제로 낸 글자와 종료 코드만 기록한다. 이 스크립트가 하는 일은
  임시 프로젝트 폴더 준비, 가짜 구글 서비스 주입, ANSI 색 제거, 임시 경로를 `<프로젝트>`로 바꾸기뿐이다.
- 실제 네트워크/구글 호출 금지: 소켓 연결을 막고(시도하면 즉시 실패, 시도 횟수는 마지막에 보고), `make_reader`/`make_write_service`를
  가짜 서비스로 교체한다. 토큰·키·영상·채널은 모두 가짜 값이다.
- 결정적: FixedClock(2026-10-10 12:00 UTC)과 고정 가짜 데이터만 쓴다. 두 번 실행하면 같은 JSON이 나와야 한다.
- 명령이 아직 없으면(`available_commands`) 그 항목은 `status: "unimplemented"`로 기록한다. 명령이 바뀌면 다시 실행해 갱신한다.
- 소스(`src/`)는 읽기만 한다. 임시 폴더는 끝나면 지운다.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import io
import json
import os
import re
import shlex
import shutil
import socket
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.environ["COLUMNS"] = "80"          # argparse 도움말 줄 너비 고정(결정성)
os.environ.pop("NO_COLOR", None)

import httplib2  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402

from youtube_title import cli, db as dbmod, live_guard  # noqa: E402
from youtube_title.commands import fetch as fetch_cmd  # noqa: E402
from youtube_title.quota import QuotaManager  # noqa: E402
from youtube_title.timeutil import FixedClock  # noqa: E402
from youtube_title.youtube_read import YouTubeReader  # noqa: E402

NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
PLACEHOLDER = "<프로젝트>"
FAKE_NOTE = "예시(가짜) 데이터: 가상의 '시니어 생활팁' 채널·영상, 가짜 구글 서비스, 고정 시각 2026-10-10 21:00(한국 시간)."

# ───────────────────────────── 네트워크 차단 ─────────────────────────────

NET_ATTEMPTS: list[str] = []


def _blocked(*a, **k):
    NET_ATTEMPTS.append(repr(a)[:80])
    raise OSError("데모 캡처 중에는 네트워크 연결이 차단됩니다(가짜 데이터만 사용)")


@contextlib.contextmanager
def network_blocked():
    saved = (socket.socket.connect, socket.create_connection, socket.getaddrinfo)
    socket.socket.connect = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = saved


# ───────────────────────────── 가짜 구글 ─────────────────────────────

def video_item(vid: str, title: str, desc: str, *, privacy="public", tags=(), duration="PT8M12S", category="26") -> dict:
    sn = {
        "publishedAt": "2025-11-03T09:00:00Z", "channelId": "UCdemoChannel0000000000", "title": title, "description": desc,
        "tags": list(tags), "categoryId": category, "defaultLanguage": "ko", "liveBroadcastContent": "none",
        "localized": {"title": title, "description": desc},
    }
    return {"id": vid, "snippet": sn, "status": {"privacyStatus": privacy, "madeForKids": False}, "contentDetails": {"duration": duration}}


SUM1 = "보일러 외출 모드와 예약 설정으로 겨울철 난방비를 줄이는 방법을 단계별로 소개합니다."
SUM2 = "무릎 관절에 부담을 주지 않는 스트레칭 동작을 5분 길이로 천천히 따라 하는 영상입니다."
SUM3 = "스마트폰 갤러리에서 중복 사진을 찾아 지우고 앨범으로 나누는 방법을 화면과 함께 설명합니다."
SUM4 = "가전제품을 쓰는 순서와 대기전력 차단으로 전기요금을 줄이는 요령을 알려 드립니다."

CATALOG = [
    video_item("demoVid0001", "겨울 난방비", SUM1 + "\n집 구조별 설정 예시도 함께 봅니다.", tags=("난방비", "보일러", "시니어")),
    video_item("demoVid0002", "무릎 스트레칭", SUM2, tags=("스트레칭", "무릎")),
    video_item("demoVid0003", "스마트폰 사진 정리", SUM3, tags=("스마트폰", "사진"), category="28"),
    video_item("demoVid0004", "전기요금 줄이기", SUM4, privacy="unlisted", duration="PT6M40S"),
    video_item("demoVid0005", "경로당 요리", "경로당에서 여럿이 함께 만들 수 있는 간단한 반찬 세 가지를 소개하는 영상입니다.", privacy="private", duration="PT12M5S"),
]


def http_error(status: int, reason: str = "") -> HttpError:
    body = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode() if reason else b"{}"
    return HttpError(httplib2.Response({"status": str(status)}), body)


class _Req:
    def __init__(self, fn):
        self._fn = fn

    def execute(self):
        return self._fn()


class _Resource:
    def __init__(self, fake, name, mode):
        self._f, self._n, self._m = fake, name, mode

    def list(self, **kw):
        if self._m == "write":
            raise AssertionError("쓰기 서비스로 조회하면 안 된다")
        return _Req(lambda: self._f.handle(f"{self._n}.list", kw))

    def update(self, **kw):
        if self._m != "write":
            raise AssertionError("읽기 서비스로 쓰면 안 된다")
        return _Req(lambda: self._f.handle(f"{self._n}.update", kw))

    def query(self, **kw):
        return _Req(lambda: self._f.handle(f"{self._n}.query", kw))


class _Service:
    def __init__(self, fake, mode):
        self._f, self._m = fake, mode

    def __getattr__(self, name):
        if name in ("channels", "playlistItems", "videos", "reports"):
            return lambda: _Resource(self._f, name, self._m)
        raise AttributeError(name)


class FakeGoogle:
    """가짜 YouTube Data / Analytics. 영상 상태와 동작 방식(analytics, network)을 가진다. 깊은 복사가 가능해야 한다."""

    def __init__(self, items=None):
        self.items = {i["id"]: copy.deepcopy(i) for i in (items if items is not None else CATALOG)}
        self.analytics = "full"        # full | reject_impressions
        self.network = "up"            # up | down
        self.updates = 0

    def read_service(self):
        return _Service(self, "read")

    def write_service(self):
        return _Service(self, "write")

    def handle(self, key, kw):
        if self.network == "down":
            raise OSError("fake network down")
        if key == "channels.list":
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUdemoUploads"}}}]}
        if key == "playlistItems.list":
            return {"items": [{"contentDetails": {"videoId": v}} for v in self.items]}
        if key == "videos.list":
            return {"items": [copy.deepcopy(self.items[i]) for i in kw["id"].split(",") if i in self.items]}
        if key == "videos.update":
            body = kw["body"]
            self.items[body["id"]]["snippet"] = copy.deepcopy(body["snippet"])
            self.updates += 1
            return {"id": body["id"], "snippet": copy.deepcopy(body["snippet"])}
        if key == "reports.query":
            metrics = kw["metrics"].split(",")
            if self.analytics == "reject_impressions" and "videoThumbnailImpressions" in metrics:
                raise http_error(400, "badRequest")
            vids = kw["filters"].split("==")[1].split(",")
            rows = []
            for n, v in enumerate(vids):
                if v not in self.items:
                    continue
                base = {"views": 900 + 130 * n, "estimatedMinutesWatched": 3100.5 + 410 * n,
                        "videoThumbnailImpressions": 21000 + 3500 * n, "videoThumbnailImpressionsClickRate": round(3.1 + 0.3 * n, 2)}
                rows.append([v] + [base[m] for m in metrics])
            return {"columnHeaders": [{"name": "video"}] + [{"name": m} for m in metrics], "rows": rows}
        raise AssertionError(f"가짜 서비스가 모르는 호출: {key}")


CURRENT: dict = {"fake": FakeGoogle()}


def _fake_make_reader(ctx):
    fake = CURRENT["fake"]
    quota = QuotaManager(ctx.conn, ctx.settings, ctx.clock)
    return YouTubeReader(fake.read_service(), fake.read_service(), quota, ctx.conn, ctx.settings, ctx.clock, sleep=lambda s: None, run_id=ctx.run_id)


def _fake_make_write_service(settings):
    return CURRENT["fake"].write_service()


@contextlib.contextmanager
def fakes_installed(use_fake_google: bool):
    """교체 지점: fetch.make_reader, live_guard.make_reader, live_guard.make_write_service.
    use_fake_google=False면 진짜 함수가 그대로 돈다(토큰이 없으면 구글 연결 전에 오류 화면)."""
    saved = (fetch_cmd.make_reader, live_guard.make_reader, live_guard.make_write_service)
    if use_fake_google:
        fetch_cmd.make_reader = _fake_make_reader
        live_guard.make_reader = _fake_make_reader
        live_guard.make_write_service = _fake_make_write_service
    try:
        yield
    finally:
        fetch_cmd.make_reader, live_guard.make_reader, live_guard.make_write_service = saved


# ───────────────────────────── 월드(임시 프로젝트) ─────────────────────────────

def ts(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class World:
    def __init__(self, root: Path, name: str, *, local: dict | None = None, settings=None, fake: FakeGoogle | None = None):
        self.name = name
        self.dir = root / name
        for sub in ("config", "candidates", "exports", "tokens"):
            (self.dir / sub).mkdir(parents=True)
        shutil.copy(REPO / "config" / "banned_terms.yaml", self.dir / "config" / "banned_terms.yaml")
        if settings is not None:
            (self.dir / "config" / "settings.yaml").write_text(settings if isinstance(settings, str) else json.dumps(settings), encoding="utf-8")
        elif (REPO / "config" / "settings.yaml").exists():
            shutil.copy(REPO / "config" / "settings.yaml", self.dir / "config" / "settings.yaml")
        if local is not None:
            (self.dir / "config" / "settings.local.yaml").write_text(json.dumps(local), encoding="utf-8")   # JSON은 YAML의 부분집합
        self.fake = fake or FakeGoogle()
        self.use_fake_google = True

    # --- DB 시드(테스트용으로 직접 삽입) ---
    def db(self):
        conn = dbmod.connect(self.dir / "data" / "youtube_title.sqlite3")
        dbmod.migrate(conn)
        return conn

    def seed_video(self, vid: str, *, fetched_hours_ago: float = 1.0):
        item = copy.deepcopy(self.fake.items[vid])
        sn = item["snippet"]
        conn = self.db()
        conn.execute(
            "INSERT OR REPLACE INTO videos (video_id,title,category_id,privacy_status,made_for_kids,live_broadcast_content,duration_sec,description_excerpt,snippet_json,fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (vid, sn["title"], sn["categoryId"], item["status"]["privacyStatus"], 0, "none", 500, sn["description"][:500], json.dumps(sn, ensure_ascii=False), ts(NOW - timedelta(hours=fetched_hours_ago))),
        )
        conn.commit()
        conn.close()

    def seed_change(self, vid: str, *, at: datetime, prev: str, new: str, approver="홍길동"):
        """과거 적용 이력(성공)을 직접 삽입한다. 백업 snippet은 영상의 '원래 제목' 버전."""
        conn = self.db()
        backup = copy.deepcopy(self.fake.items[vid]["snippet"])
        backup["title"] = prev
        backup["localized"] = dict(backup["localized"], title=prev)
        conn.execute(
            "INSERT INTO title_changes (video_id,candidate_id,change_type,previous_title,new_title,backup_snippet_json,approver,approved_at,plan_hash,result,error_code,applied_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, None, "apply", prev, new, json.dumps(backup, ensure_ascii=False), approver, ts(at), "demo-seeded", "success", None, ts(at), ts(at)),
        )
        conn.commit()
        conn.close()

    def seed_metric(self, vid: str, *, impressions: int, period_start: str, phase="after", taken_at: datetime = NOW):
        conn = self.db()
        conn.execute("INSERT INTO metrics_snapshots (video_id,taken_at,phase,source,period_start,period_end,impressions) VALUES (?,?,?,?,?,?,?)", (vid, ts(taken_at), phase, "api", period_start, period_start, impressions))
        conn.commit()
        conn.close()

    def set_video_title(self, vid: str, title: str):
        """DB에 저장된 영상 정보와 가짜 서버의 제목을 바꾼다(이미 적용된 상태를 흉내)."""
        conn = self.db()
        sn = json.loads(conn.execute("SELECT snippet_json FROM videos WHERE video_id=?", (vid,)).fetchone()[0])
        sn["title"] = title
        sn["localized"] = dict(sn["localized"], title=title)
        conn.execute("UPDATE videos SET title=?, snippet_json=? WHERE video_id=?", (title, json.dumps(sn, ensure_ascii=False), vid))
        conn.commit()
        conn.close()
        self.fake.items[vid]["snippet"] = sn

    def candidate_file(self, vid: str, current: str, topic: str | None, summary: str, titles: list[str]):
        data = {"video_id": vid, "current_title": current, "topic": topic, "summary": summary, "source": "human",
                "candidates": [{"title": t, "evidence": summary} for t in titles]}
        (self.dir / "candidates" / f"{vid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    def candidate_id(self, title: str) -> int:
        conn = self.db()
        row = conn.execute("SELECT id FROM title_candidates WHERE candidate_title=? ORDER BY id DESC", (title,)).fetchone()
        conn.close()
        assert row, f"후보를 DB에서 찾지 못함: {title}"
        return int(row[0])


# ───────────────────────────── 실행·기록 ─────────────────────────────

SCREENS: list[dict] = []
CLOCK = FixedClock(NOW)


def available_commands() -> set[str]:
    sub = next(a for a in cli.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
    return set(sub.choices)


def clean(text: str, dirs: list[Path]) -> str:
    text = ANSI.sub("", text)
    for d in sorted({str(x) for x in dirs} | {str(x.resolve()) for x in dirs}, key=len, reverse=True):
        text = text.replace(d, PLACEHOLDER)
    return text


def run_cli(world_dir: Path, argv: list[str], inputs: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    answers = iter(inputs)

    def input_fn(prompt: str = "") -> str:
        """터미널을 흉내 낸다: 질문 글자 뒤에 사용자가 친 값이 같은 줄에 보이고 줄이 바뀐다."""
        try:
            ans = next(answers)
        except StopIteration:
            out.write(prompt + "\n")
            raise EOFError from None
        out.write(prompt + ans + "\n")
        return ans

    code = cli.main(["--base-dir", str(world_dir)] + argv, out=out, err=err, env={"YT_TOKEN_DIR": "tokens"}, clock=CLOCK, input_fn=input_fn)
    return code, out.getvalue(), err.getvalue()


def capture(world: World, sid: str, title: str, argv: list[str], note: str, *, scratch: Path, inputs: list[str] | None = None,
            plain: bool = True, group: str = "", requires: str | None = None, quiet: bool = False) -> dict | None:
    """argv를 실제로 실행해 기록한다. plain=True면 같은 상태의 복사본에서 `--plain` 변형도 실행한다(상태는 기본 실행 쪽만 이어진다)."""
    need = requires or (argv[0] if not argv[0].startswith("-") else None)
    command = "youtube_title " + shlex.join(argv)
    if need and need not in available_commands():
        SCREENS.append({"id": sid, "title": title, "command": command, "exit_code": None, "stdout": "", "stderr": "",
                        "note": f"미구현: `{need}` 명령이 아직 없습니다. {note}", "status": "unimplemented", "variant": "default", "group": group, "world": world.name})
        return None
    pc = po = pe = None
    with fakes_installed(world.use_fake_google):
        if plain and not quiet:
            snap = scratch / f"{world.name}__{sid}__plain"
            shutil.copytree(world.dir, snap)
            real_fake, CURRENT["fake"] = world.fake, copy.deepcopy(world.fake)
            try:
                pc, po, pe = run_cli(snap, argv + ["--plain"], inputs or [])
            finally:
                CURRENT["fake"] = real_fake
        CURRENT["fake"] = world.fake
        code, so, se = run_cli(world.dir, argv, inputs or [])
    if quiet:
        return {"exit_code": code, "stdout": so, "stderr": se}
    if pc is not None:
        shutil.rmtree(snap, ignore_errors=True)
    dirs = [world.dir, scratch]
    pdirs = dirs + ([snap] if pc is not None else [])
    base = {"note": f"{FAKE_NOTE} {note}".strip(), "status": "captured", "group": group, "world": world.name}
    SCREENS.append({"id": sid, "title": title, **base, "command": command, "exit_code": code, "stdout": clean(so, dirs), "stderr": clean(se, dirs), "variant": "default"})
    if pc is not None:
        SCREENS.append({"id": sid + ".plain", "title": title + " (--plain)", **base, "command": command + " --plain", "exit_code": pc, "stdout": clean(po, pdirs), "stderr": clean(pe, pdirs), "variant": "plain"})
    return {"exit_code": code, "stdout": so, "stderr": se}


# ───────────────────────────── 시나리오 ─────────────────────────────

T1_OK = "겨울철 난방비 줄이는 보일러 외출 모드 설정"
T1_FEAR = "이거 안 하면 큰일 나는 겨울 난방비 설정"
T2_OK = "무릎 관절에 부담 적은 스트레칭 5분 따라하기"
T2_MED = "무릎 통증 완치되는 기적의 스트레칭"
T2_WARN = "무릎 스트레칭 5분 루틴 꼭 따라하세요!!!"
T3_LONG = "스마트폰 갤러리에서 중복 사진을 찾아 지우고 앨범으로 나누어 정리하는 방법을 처음부터 끝까지 화면과 함께 자세하게 설명해 드리는 시니어 눈높이 완전 정복 강의 영상 모음집 전편 안내서 특별판"
T3_MISMATCH = "연금 수령액 두 배로 늘리는 방법"
T3_WARN = "스마트폰 갤러리에서 중복 사진을 찾아 지우고 앨범으로 나누어 정리하는 방법 총정리"
T4_MISMATCH = "손주에게 용돈 주는 현명한 방법"
T4_WARN = "전기요금 줄이는 가전 사용 순서 꼭 확인하세요!!!"


def scenario_main(root: Path, scratch: Path) -> None:
    w = World(root, "main")
    w.fake.analytics = "reject_impressions"

    def c(*a, **k):
        return capture(w, *a, scratch=scratch, **k)

    # ① 도움말
    c("help", "전체 도움말", ["--help"], "SCR-001.", group="도움말", plain=False)
    for name in sorted(available_commands()):
        c(f"help-{name}", f"`{name}` 도움말", [name, "--help"], f"{name} 명령의 옵션 설명.", group="도움말", plain=False)

    # ② auth
    c("auth-before", "로그인 상태(로그인 전)", ["auth"], "토큰 파일이 없는 처음 상태.", group="인증")
    c("auth-read-nosecret", "읽기 로그인 시도(구글 비밀 파일 없음)", ["auth", "--read"], "client_secret.json이 없어 브라우저를 열기 전에 안내하고 멈춘다. 네트워크 호출 없음.", group="오류")
    (w.dir / "tokens" / "read_token.json").write_text('{"fake": true}', encoding="utf-8")   # 값은 읽지 않고 존재 여부만 본다
    c("auth-after", "로그인 상태(읽기 로그인 후)", ["auth"], "가짜 읽기 토큰 파일(내용 없는 껍데기)을 만들어 '저장됨'으로 보이게 한 상태. 쓰기 토큰은 없음.", group="인증")

    # ③④ fetch
    c("fetch-noargs", "fetch: 무엇을 조회할지 지정하지 않음", ["fetch"], "옵션 없이 실행.", group="오류")
    c("fetch-badid", "fetch: 영상 ID 형식 오류", ["fetch", "--video", "짧은ID"], "11자 형식이 아닌 ID.", group="오류")
    c("fetch-all", "fetch --all: 채널 전체 영상 조회", ["fetch", "--all"], "가상 영상 5개(공개 3·일부 공개 1·비공개 1).", group="조회")
    c("fetch-metrics", "fetch --metrics: 노출수·CTR 거부 시 폴백 안내", ["fetch", "--metrics"], "가짜 Analytics가 노출수·CTR 지표 요청을 400으로 거부 -> 조회수·시청 시간만 저장하고 CSV 안내를 출력.", group="조회")
    w.fake.analytics = "full"
    c("fetch-metrics-before", "fetch --metrics --phase before: 지표 전부 수집", ["fetch", "--metrics", "--phase", "before"], "가짜 Analytics가 노출수·CTR까지 제공하는 경우(변경 전 기준선 수집).", group="조회")

    # ⑤ validate
    w.candidate_file("demoVid0001", "겨울 난방비", "life", SUM1, [T1_OK, T1_FEAR])
    w.candidate_file("demoVid0002", "무릎 스트레칭", "health", SUM2, [T2_OK, T2_MED, T2_WARN])
    w.candidate_file("demoVid0003", "스마트폰 사진 정리", "life", SUM3, [T3_WARN, T3_LONG])
    w.candidate_file("demoVid0004", "전기요금 줄이기", "life", SUM4, [T4_MISMATCH, T4_WARN])
    c("validate-all", "validate --all: 통과·경고·차단·엄격 모드", ["validate", "--all"],
      "영상 4개의 후보 9개. 공포 조장·의료 효능 단정·영상과 불일치·100자 초과는 차단, 권장 길이 초과·느낌표는 경고, 건강 주제(demoVid0002)는 엄격 모드라 경고도 차단.", group="검증")
    c("validate-one", "validate --file: 후보 파일 하나", ["validate", "--file", "candidates/demoVid0001.json"], "후보 번호는 위 validate --all과 같다(같은 파일 내용이면 갱신).", group="검증")
    (w.dir / "candidates" / "demoVid0005.json").write_text(json.dumps({"video_id": "demoVid0005", "current_title": "경로당 요리", "topic": "life", "summary": "경로당 반찬", "source": "human", "candidates": []}, ensure_ascii=False), encoding="utf-8")
    c("validate-emptylist", "validate --file: 후보가 0개인 파일", ["validate", "--file", "candidates/demoVid0005.json"], "candidates가 빈 목록인 잘못된 파일.", group="오류")
    (w.dir / "candidates" / "demoVid0005.json").unlink()
    (w.dir / "candidates" / "demoVid0006.json").write_text("{ 깨진 json", encoding="utf-8")
    c("validate-badjson", "validate --file: JSON 문법 오류", ["validate", "--file", "candidates/demoVid0006.json"], "JSON 문법이 틀린 후보 파일.", group="오류")
    (w.dir / "candidates" / "demoVid0006.json").unlink()

    ok1, warn3, fear1, ok2 = (w.candidate_id(t) for t in (T1_OK, T4_WARN, T1_FEAR, T2_OK))

    # ⑥ plan
    c("plan-ok", "plan: 통과 후보의 변경 계획(dry-run)", ["plan", "--candidate", str(ok1)], "제한 검사 4개 통과, 계획 해시, 쿼터 예상. 아무것도 바꾸지 않음.", group="계획")
    c("plan-warn", "plan: 경고 후보", ["plan", "--candidate", str(warn3)], "검증에서 경고를 받은 후보도 계획은 볼 수 있다(승인 단계에서 사람이 판단).", group="계획")
    c("plan-strict-pass", "plan: 건강 주제(엄격 모드) 통과 후보", ["plan", "--candidate", str(ok2)], "엄격 모드에서도 문제가 없던 후보.", group="계획")
    c("plan-blocked", "plan: 차단된 후보", ["plan", "--candidate", str(fear1)], "validate에서 차단된 후보로 계획을 만들려는 경우.", group="오류")
    c("plan-missing", "plan: 없는 후보 번호", ["plan", "--candidate", "999"], "존재하지 않는 후보 번호.", group="오류")

    # ⑩ apply (설정이 꺼진 기본 상태)
    c("apply-dry", "apply 모의 실행(기본 설정: 라이브 꺼짐)", ["apply", "--candidate", str(ok1)], "settings.local.yaml이 없는 기본 상태 -> enable_live 꺼짐, 허용 목록 비어 있음, 승인 없음으로 14단계 게이트 중 막힌 곳을 표시.", group="적용")
    c("apply-live-refused", "apply --live 거부(라이브 꺼짐)", ["apply", "--candidate", str(ok1), "--live"], "enable_live가 꺼져 있고 허용 목록이 비어 있어 구글에 연결하기 전에 중단.", group="적용")
    c("approve-wrongid", "approve: 영상 ID를 잘못 입력", ["approve", "--candidate", str(ok1), "--approver", "홍길동"], "영상 ID 대신 엉뚱한 글자를 3번 입력. (입력 줄은 사용자가 친 값이 화면에 보이는 것을 흉내 낸 것)", inputs=["abc", "abc", "abc"], group="오류", plain=False)
    c("purge-dry", "purge: 오래된 기록 정리(삭제할 것 없음)", ["purge", "--before", "2026-01-01"], "정리 대상이 없는 상태.", group="기타")
    c("report-empty", "report: 변경 이력이 없음", ["report"], "제목을 바꾼 기록이 없는 처음 상태.", group="리포트")


def scenario_errors(root: Path, scratch: Path) -> None:
    w = World(root, "err_noauth")
    w.use_fake_google = False
    capture(w, "err-noauth", "fetch --all: 로그인 정보 없음", ["fetch", "--all"], "가짜 교체 없이 실제 make_reader가 돈다. 토큰 파일이 없어 구글 연결 전에 멈춘다(네트워크 호출 없음).", group="오류", scratch=scratch)
    w = World(root, "err_config", settings="quota:\n  daily_limit_units: \"많이\"\n")
    capture(w, "err-config", "설정 값 오류", ["auth"], "settings.yaml의 숫자 항목에 글자를 넣은 경우.", group="오류", scratch=scratch)
    w = World(root, "err_quota", settings={"quota": {"daily_limit_units": 2}})
    capture(w, "err-quota", "fetch --all: 쿼터 부족", ["fetch", "--all"], "하루 상한을 2 units로 낮춘 설정에서 조회가 3번째 호출 전에 막힌다.", group="오류", scratch=scratch)
    w = World(root, "err_net")
    w.fake.network = "down"
    capture(w, "err-network", "fetch --all: 네트워크 오류, 재시도 소진", ["fetch", "--all"], "가짜 서비스가 연결 오류를 내는 상황(재시도 대기 시간은 생략하고 소진까지 실행).", group="오류", scratch=scratch)


def scenario_limits(root: Path, scratch: Path) -> None:
    f = FakeGoogle([video_item("limVid00001", "마트 장보기", SUM1), video_item("limVid00002", "마트 장보기 팁", SUM1), video_item("limVid00003", "마트 장보기 요령", SUM1)])
    w = World(root, "limits", fake=f)
    for v in f.items:
        w.seed_video(v)
    cur = {v: f.items[v]["snippet"]["title"] for v in f.items}
    w.seed_change("limVid00001", at=NOW - timedelta(hours=24), prev="이전 제목 A", new=cur["limVid00001"])          # 72시간 미달
    w.seed_metric("limVid00001", impressions=1500, period_start="2026-10-10", taken_at=NOW)                        # 노출수는 충분(간격만 막힘)
    for days, p, n in ((30, "이전 제목 B1", "이전 제목 B2"), (20, "이전 제목 B2", "이전 제목 B3"), (10, "이전 제목 B3", cur["limVid00002"])):
        w.seed_change("limVid00002", at=NOW - timedelta(days=days), prev=p, new=n)                                   # 3회 도달
    w.seed_change("limVid00003", at=NOW - timedelta(days=10), prev="이전 제목 C", new=cur["limVid00003"])           # 노출수 미달
    w.seed_metric("limVid00003", impressions=300, period_start=(NOW - timedelta(days=9)).date().isoformat(), taken_at=NOW - timedelta(days=1))
    titles = {}
    for v, suffix in (("limVid00001", " 하나"), ("limVid00002", " 둘"), ("limVid00003", " 셋")):
        titles[v] = T1_OK + suffix
        w.candidate_file(v, cur[v], "life", SUM1, [titles[v]])
    capture(w, "limits-validate", "", ["validate", "--all"], "", scratch=scratch, quiet=True)
    for v, sid, label, why in (
        ("limVid00001", "plan-limit-interval", "plan: 최소 간격 72시간 미달", "24시간 전에 이미 한 번 바꾼 영상(DB에 테스트용으로 직접 삽입한 이력, 변경 이후 노출수 1500회는 충분)."),
        ("limVid00002", "plan-limit-count", "plan: 영상별 변경 횟수 상한(3회) 도달", "30·20·10일 전 3회 변경 이력(테스트용 삽입). 시간이 지나도 풀리지 않는다."),
        ("limVid00003", "plan-limit-impressions", "plan: 재변경 최소 노출수 미달", "10일 전 1회 변경, 이후 노출수 300회(필요 1000회)로 삽입."),
    ):
        capture(w, sid, label, ["plan", "--candidate", str(w.candidate_id(titles[v]))], why, group="제한", scratch=scratch)

    f2 = FakeGoogle([video_item(f"dayVid0000{n}", f"장보기 {n}", SUM1) for n in (1, 2, 3, 4)])
    d = World(root, "daily", fake=f2)
    for v in f2.items:
        d.seed_video(v)
    for n, hour in ((1, 7), (2, 8), (3, 9)):
        d.seed_change(f"dayVid0000{n}", at=NOW.replace(hour=hour, minute=30), prev="이전 제목", new=f2.items[f"dayVid0000{n}"]["snippet"]["title"])
    d.candidate_file("dayVid00004", "장보기 4", "life", SUM1, [T1_OK])
    capture(d, "daily-validate", "", ["validate", "--all"], "", scratch=scratch, quiet=True)
    capture(d, "plan-limit-daily", "plan: 하루 적용 건수 상한(3건) 도달", ["plan", "--candidate", str(d.candidate_id(T1_OK))], "오늘(태평양 시간) 다른 영상 3건 적용 이력(테스트용 삽입).", group="제한", scratch=scratch)


def scenario_rollback_refused(root: Path, scratch: Path) -> None:
    w = World(root, "rollback_off")
    w.seed_video("demoVid0001")
    new = T1_OK
    w.seed_change("demoVid0001", at=datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc), prev="겨울 난방비", new=new)
    w.set_video_title("demoVid0001", new)
    capture(w, "rollback-plan", "rollback: 되돌리기 계획(모의 실행)", ["rollback", "--change", "1"], "DB에 테스트용으로 삽입한 적용 이력(2026-09-01, '겨울 난방비' -> 새 제목)을 되돌리는 계획.", group="롤백", scratch=scratch)
    capture(w, "rollback-live-refused", "rollback --live 거부(라이브 꺼짐)", ["rollback", "--change", "1", "--live", "--approver", "홍길동"], "enable_live가 꺼져 있고 허용 목록이 비어 있어 중단.", group="롤백", scratch=scratch)
    capture(w, "rollback-missing", "rollback: 없는 변경 번호", ["rollback", "--change", "99"], "존재하지 않는 변경 번호.", group="오류", scratch=scratch)


def scenario_live(root: Path, scratch: Path) -> None:
    """WU-5 전체 흐름: validate -> approve -> apply(모의) -> apply --live -> rollback. 가짜 서버만 사용, 허용 목록에 가짜 영상 1개."""
    w = World(root, "live", local={"live": {"enable_live": True, "live_allowlist": ["demoVid0001"]}})

    def c(*a, **k):
        return capture(w, *a, scratch=scratch, **k)

    def q(argv):
        return capture(w, "setup", "", argv, "", quiet=True, scratch=scratch)

    q(["fetch", "--all"])
    q(["fetch", "--metrics", "--phase", "before"])
    w.candidate_file("demoVid0001", "겨울 난방비", "life", SUM1, [T1_OK])
    q(["validate", "--all"])
    cid = w.candidate_id(T1_OK)
    c("live-apply-noapproval", "apply --live: 승인 파일 없음", ["apply", "--candidate", str(cid), "--live"], "설정(enable_live·허용 목록)은 통과하지만 사람의 승인 파일이 없어 중단.", group="적용")
    c("live-approve", "approve: 사람의 승인(영상 ID 직접 입력)", ["approve", "--candidate", str(cid), "--approver", "홍길동"], "영상 ID를 화면 그대로 입력해 승인 파일 생성(입력 줄은 사용자가 친 값이 보이는 것을 흉내 낸 것).", inputs=["demoVid0001"], group="적용", plain=False)
    c("live-apply-dry", "apply 모의 실행(승인 후)", ["apply", "--candidate", str(cid)], "설정 켜짐 + 허용 목록 + 승인 완료 상태에서 14단계 게이트 표.", group="적용")
    c("live-apply-wrongid", "apply --live: 영상 ID를 잘못 입력", ["apply", "--candidate", str(cid), "--live"], "마지막 확인에서 영상 ID를 3번 틀리게 입력 -> 구글에 쓰지 않고 중단.", inputs=["abc", "abc", "abc"], group="오류", plain=False)
    c("live-apply", "apply --live: 실제 적용(가짜 서버)", ["apply", "--candidate", str(cid), "--live"], "모든 게이트 통과 후 영상 ID를 직접 입력 -> 가짜 서버의 제목 변경 -> 재조회 사후 검증. 실제 구글에는 아무것도 보내지 않았다.", inputs=["demoVid0001"], group="적용", plain=False)
    c("live-apply-again", "apply --live: 같은 후보 재적용 시도", ["apply", "--candidate", str(cid), "--live"], "이미 적용된 후보를 다시 적용하려는 경우의 출력.", group="오류", plain=False)
    conn = w.db()
    chg = str(conn.execute("SELECT id FROM title_changes WHERE result='success' AND change_type='apply' ORDER BY id DESC").fetchone()[0])
    conn.close()
    c("live-rollback-plan", "rollback: 방금 적용한 변경 되돌리기 계획", ["rollback", "--change", chg], "위 apply --live가 만든 변경(앞선 중단된 시도도 번호를 하나씩 차지한다).", group="롤백")
    c("live-rollback", "rollback --live: 실제 되돌리기(가짜 서버)", ["rollback", "--change", chg, "--live", "--approver", "홍길동"], "확인자 이름 + 영상 ID 직접 입력 후 이전 제목 복원.", inputs=["demoVid0001"], group="롤백", plain=False)
    c("live-report", "report: 적용·롤백 직후(변경 후 지표 없음)", ["report", "--video", "demoVid0001"], "방금 적용·롤백한 영상. 변경 후 지표가 아직 없어 '데이터 부족'.", group="리포트")


HEAD = "Content,Views,Impressions,Impressions click-through rate (%),Watch time (hours)\n"


def scenario_report(root: Path, scratch: Path) -> None:
    w = World(root, "report")
    vid = "demoVid0001"
    w.seed_video(vid)
    w.seed_change(vid, at=datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc), prev="겨울 난방비", new=T1_OK)
    w.set_video_title(vid, T1_OK)

    def c(*a, **k):
        return capture(w, *a, scratch=scratch, **k)

    c("report-insufficient", "report: 데이터 부족", ["report", "--video", vid], "적용 이력(테스트용 삽입)은 있지만 전후 지표가 없다. 기준선 없음 경고 포함.", group="리포트")
    (w.dir / "exports" / "before.csv").write_text(HEAD + f'{vid},"2,800","28,000",3.0%,93.3333333\nnot-an-id,"10","100",1.0%,1\nzzzVid00001,"5","50",2.0%,0.1\n', encoding="utf-8")
    (w.dir / "exports" / "after.csv").write_text(HEAD + f'{vid},"5,600","56,000",4.5%,186.6666667\n', encoding="utf-8")
    c("csv-before", "report --import-csv: 변경 전 CSV 가져오기", ["report", "--import-csv", "exports/before.csv", "--phase", "before", "--period-start", "2026-08-04", "--period-end", "2026-08-31"],
      "Studio 내보내기를 흉내 낸 가짜 CSV. 일부러 잘못된 행(영상 ID 형식 오류)과 DB에 없는 영상 행을 넣어 건너뛰기/경고 출력을 보인다.", group="리포트")
    c("csv-after", "report --import-csv: 변경 후 CSV 가져오기", ["report", "--import-csv", "exports/after.csv", "--phase", "after", "--period-start", "2026-09-02", "--period-end", "2026-09-29"], "가짜 CSV(변경 후 28일).", group="리포트")
    c("report-ok", "report: 비교 가능(자료 충분)", ["report", "--video", vid], "전후 각 28일, 노출수 기준 충족. 원인을 단정하지 않는다는 한계 문구가 항상 출력된다.", group="리포트")
    c("csv-nofile", "report --import-csv: 파일 없음", ["report", "--import-csv", "exports/없음.csv", "--phase", "before"], "존재하지 않는 CSV.", group="오류")


# ───────────────────────────── 진입점 ─────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "docs" / "demo" / "screens.json"), help="저장할 JSON 경로")
    args = ap.parse_args()

    # 표가 긴 경로를 '…'로 자르므로(실제 동작), 경로가 짧은 /tmp 아래에서 돌린다. 길이가 항상 같아 결과가 결정적이다.
    root = Path(tempfile.mkdtemp(prefix="ytd", dir="/tmp" if os.path.isdir("/tmp") else None))
    scratch = root / "_scratch"
    scratch.mkdir()
    try:
        with network_blocked():
            for fn in (scenario_main, scenario_errors, scenario_limits, scenario_rollback_refused, scenario_live, scenario_report):
                fn(root, scratch)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(SCREENS, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {out} (화면 {len(SCREENS)}개), 네트워크 연결 시도 {len(NET_ATTEMPTS)}회(차단됨)")
    for s in SCREENS:
        print(f"{s['id']:30} {s['status']:12} exit={s['exit_code']}  {s['command']}")
    return 0 if not NET_ATTEMPTS else 1


if __name__ == "__main__":
    sys.exit(main())
