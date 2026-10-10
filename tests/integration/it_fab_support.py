"""F-A(인증·조회)+F-B(후보·필터) 통합 테스트용 지원 코드(7단계, 테스트 전용).

실제 구글/네트워크는 쓰지 않는다. 가짜 OAuth 흐름과 읽기 전용 가짜 YouTube 서비스를 CLI 진입점
(`ytitle.cli.main`) 뒤에 꽂아, 단위 사이의 접점(DB 계약, 쿼터 장부, 설정 계층, 오류/종료 코드, 로그 마스킹)을 본다.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httplib2
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from ytitle import auth, cli
from ytitle.commands import fetch as fetch_cmd
from ytitle.timeutil import FixedClock
from ytitle.youtube_read import YouTubeReader

REPO = Path(__file__).resolve().parents[2]
REAL_DICT = REPO / "config" / "banned_terms.yaml"

FAKE_ACCESS = "ya29.FAKEACCESSTOKENVALUE0123456789"
FAKE_REFRESH = "1//0FAKEREFRESHTOKENVALUE0123456789abcdef"
FAKE_CLIENT_SECRET = "GOCSPX-fakeclientsecret0123456789"
SECRETS = (FAKE_ACCESS, FAKE_REFRESH, FAKE_CLIENT_SECRET, "SECRET-BODY", "SECRETKEY")

SUMMARY = "겨울철 난방 습관을 바꿔 전기요금을 줄이는 방법을 소개합니다"
DESCRIPTION = "겨울철 난방 습관을 바꿔 전기요금을 줄이는 방법을 소개합니다. 보일러 온도와 단열 요령도 알려 드립니다."
GOOD_TITLE = "겨울철 전기요금 줄이는 난방 습관"
FETCH_NOW = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)  # 태평양 시간 2026-10-10 05:00(PDT)


def vid(n: int) -> str:
    return f"vid{n:08d}"


def make_creds(scopes, *, expired: bool = False, refresh: str | None = FAKE_REFRESH) -> Credentials:
    exp = datetime.now(timezone.utc).replace(tzinfo=None) + (timedelta(hours=-1) if expired else timedelta(hours=1))
    return Credentials(token=FAKE_ACCESS, refresh_token=refresh, token_uri="https://oauth2.googleapis.com/token",
                       client_id="cid.apps.googleusercontent.com", client_secret=FAKE_CLIENT_SECRET, scopes=list(scopes), expiry=exp)


class FakeFlow:
    """InstalledAppFlow 대역. 요청받은 권한 범위를 그대로 허용한 토큰을 돌려준다."""

    def __init__(self, creds=None, exc=None) -> None:
        self.creds, self.exc, self.kwargs = creds, exc, None

    def run_local_server(self, **kw):
        self.kwargs = kw
        if self.exc:
            raise self.exc
        return self.creds


def http_error(status: int, reason: str = "", message: str = f"SECRET-BODY {FAKE_ACCESS}") -> HttpError:
    body = {"error": {"code": status, "message": message, "errors": [{"message": message, "domain": "youtube.quota", "reason": reason}]}}
    return HttpError(httplib2.Response({"status": str(status)}), json.dumps(body).encode("utf-8"),
                     uri="https://www.googleapis.com/youtube/v3/videos?key=SECRETKEY")


def video_item(video_id: str, title: str = "원래 제목", description: str = DESCRIPTION, **extra) -> dict:
    return {
        "id": video_id,
        "snippet": {"title": title, "description": description, "categoryId": "26", "liveBroadcastContent": "none", **extra},
        "status": {"privacyStatus": "public", "madeForKids": False},
        "contentDetails": {"duration": "PT5M"},
    }


# ------------------------------------------------------------------ 읽기 전용 가짜 서비스


class _Req:
    def __init__(self, api, key, kwargs) -> None:
        self.api, self.key, self.kwargs = api, key, kwargs

    def execute(self):
        self.api.calls.append((self.key, self.kwargs))
        script = self.api.script.get(self.key)
        if script:
            action = script.pop(0)
            if isinstance(action, BaseException):
                raise action
        return self.api.handle(self.key, self.kwargs)


class _Res:
    def __init__(self, api, name: str) -> None:
        self._api, self._name = api, name

    def __getattr__(self, method: str):
        if (self._name, method) not in self._api.READ_METHODS:
            self._api.forbidden.append(f"{self._name}.{method}")  # 쓰기/그 밖의 호출 시도는 기록하고 막는다
            raise AttributeError(f"허용되지 않은 호출: {self._name}.{method}")
        return lambda **kw: _Req(self._api, f"{self._name}.{method}", kw)


class FakeApi:
    """YouTube Data v3 + Analytics v2 대역. 읽기 메서드 4개만 존재하며 그 밖의 접근은 `forbidden`에 남는다."""

    READ_METHODS = {("channels", "list"), ("playlistItems", "list"), ("videos", "list"), ("reports", "query")}

    def __init__(self, items: list[dict] | None = None, page_size: int = 50) -> None:
        self.items = list(items or [])
        self.page_size = page_size
        self.calls: list[tuple[str, dict]] = []
        self.forbidden: list[str] = []
        self.script: dict[str, list] = {}   # key -> 호출마다 하나씩 소비: 예외면 던지고 None이면 정상 응답

    def fail(self, key: str, *actions) -> None:
        self.script.setdefault(key, []).extend(actions)

    def channels(self):
        return _Res(self, "channels")

    def playlistItems(self):
        return _Res(self, "playlistItems")

    def videos(self):
        return _Res(self, "videos")

    def reports(self):
        return _Res(self, "reports")

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        self.forbidden.append(name)
        raise AttributeError(f"허용되지 않은 서비스: {name}")

    def count(self, key: str) -> int:
        return sum(1 for k, _ in self.calls if k == key)

    def handle(self, key: str, kw: dict):
        if key == "channels.list":
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU_FAKE"}}}]}
        if key == "playlistItems.list":
            start = int(kw["pageToken"][4:]) if kw.get("pageToken") else 0
            chunk = self.items[start : start + self.page_size]
            out: dict = {"items": [{"contentDetails": {"videoId": it["id"]}} for it in chunk]}
            if start + self.page_size < len(self.items):
                out["nextPageToken"] = f"PAGE{start + self.page_size}"
            return out
        if key == "videos.list":
            wanted = kw["id"].split(",")
            by_id = {it["id"]: it for it in self.items}
            return {"items": [by_id[i] for i in wanted if i in by_id]}
        if key == "reports.query":
            ids = kw["filters"].replace("video==", "").split(",")
            names = ["video"] + kw["metrics"].split(",")
            values = {"views": 100, "estimatedMinutesWatched": 12.5, "videoThumbnailImpressions": 1000, "videoThumbnailImpressionsClickRate": 0.05}
            return {"columnHeaders": [{"name": n} for n in names],
                    "rows": [[i] + [values[m] for m in names[1:]] for i in ids if any(it["id"] == i for it in self.items)]}
        raise AssertionError(f"알 수 없는 호출: {key}")


# ------------------------------------------------------------------ 실험실(프로젝트 폴더 + CLI 실행기)


@dataclass
class Result:
    code: int
    out: str
    err: str
    argv: tuple = ()


@dataclass
class Lab:
    root: Path
    monkeypatch: object
    clock: FixedClock = field(default_factory=lambda: FixedClock(FETCH_NOW))
    api: FakeApi = field(default_factory=FakeApi)
    built_with: list = field(default_factory=list)   # build_services가 받은 자격 증명(읽기 토큰에서 로드된 것)
    sleeps: list = field(default_factory=list)       # 재시도 백오프 대기 시간(실제로 자지 않음)
    history: list = field(default_factory=list)      # 지금까지의 모든 실행 결과
    flow_scopes: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self.project = self.root / "proj"
        self.tokens = self.root / "tokens"
        (self.project / "config").mkdir(parents=True)
        (self.project / "secrets").mkdir()
        (self.project / "candidates").mkdir()
        (self.project / "secrets" / "client_secret.json").write_text(json.dumps({"installed": {"client_secret": FAKE_CLIENT_SECRET}}), encoding="utf-8")
        shutil.copy(REAL_DICT, self.project / "config" / "banned_terms.yaml")
        self.env = {"YT_TOKEN_DIR": str(self.tokens)}
        lab = self

        def fake_new_flow(settings, scopes):
            lab.flow_scopes.append(tuple(scopes))
            return FakeFlow(make_creds(scopes))

        def fake_build_services(creds):
            lab.built_with.append(creds)
            return lab.api, lab.api

        class NoSleepReader(YouTubeReader):
            def __init__(self, *a, **k):
                k["sleep"] = lab.sleeps.append
                super().__init__(*a, **k)

        self.monkeypatch.setattr(auth, "new_flow", fake_new_flow)
        self.monkeypatch.setattr(fetch_cmd, "build_services", fake_build_services)
        self.monkeypatch.setattr(fetch_cmd, "YouTubeReader", NoSleepReader)

    # -- 실행
    def run(self, *argv: str, input_text: str = "", env: dict | None = None, project: Path | None = None, base_dir_args: bool = True) -> Result:
        import io

        out, err = io.StringIO(), io.StringIO()
        prefix = ["--base-dir", str(project or self.project)] if base_dir_args else []
        code = cli.main(prefix + list(argv), out=out, err=err, env=self.env if env is None else env, clock=self.clock, input_fn=lambda p: input_text)
        res = Result(code, out.getvalue(), err.getvalue(), tuple(argv))
        self.history.append(res)
        return res

    # -- 준비
    def channel(self, n: int, **kw) -> list[str]:
        self.api.items = [video_item(vid(i), f"원래 제목 {i}", **kw) for i in range(1, n + 1)]
        return [it["id"] for it in self.api.items]

    def login_read(self) -> Result:
        res = self.run("auth", "--read")
        assert res.code == 0, res.err
        return res

    def local_settings(self, text: str) -> None:
        (self.project / "config" / "settings.local.yaml").write_text(text, encoding="utf-8")

    def candidate(self, video_id: str, titles=(GOOD_TITLE,), *, topic="life", summary=SUMMARY, evidence=None, **extra) -> Path:
        d = {"video_id": video_id, "current_title": "겨울 전기요금", "topic": topic, "summary": summary, "source": "human",
             "candidates": [{"title": t, "evidence": evidence if evidence is not None else summary} for t in titles]}
        d.update(extra)
        p = self.project / "candidates" / f"{video_id}.json"
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        return p

    # -- 관찰
    @property
    def db_path(self) -> Path:
        return self.project / "data" / "ytitle.sqlite3"

    def q(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def log_text(self) -> str:
        p = self.project / "data" / "logs" / "ytitle.log"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def data_bytes(self) -> bytes:
        return b"".join(p.read_bytes() for p in sorted((self.project / "data").rglob("*")) if p.is_file())

    def everything_shown(self) -> str:
        """지금까지 화면(표준 출력·오류)에 나온 모든 글자."""
        return "\n".join(r.out + "\n" + r.err for r in self.history)

    def quota_rows(self) -> list[tuple]:
        return [(r["method"], r["units"], r["status"]) for r in self.q("SELECT method, units, status FROM quota_usage ORDER BY id")]

    def token_files(self) -> list[str]:
        return sorted(p.name for p in self.tokens.glob("*")) if self.tokens.exists() else []
