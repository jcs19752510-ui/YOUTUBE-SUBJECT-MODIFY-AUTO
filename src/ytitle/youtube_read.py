"""YouTube 읽기 전용 조회와 Analytics 지표 수집(EVT-101~103, 105, FR-006, FR-007).

이 모듈에는 쓰기 API 호출이 없다. 쓰기는 live_guard 한 곳에서만 한다(SEC-001).
모든 호출은 쿼터를 먼저 예약하고(SEC-002) retry를 거친다(SEC-003).
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Iterable, Iterator

import httplib2
from googleapiclient.errors import HttpError

from ytitle.config import Settings
from ytitle.errors import ApiError, AuthError, DatabaseError, InputError, QuotaError, YtError
from ytitle.quota import RESET_HINT, QuotaManager
from ytitle.retry import call_with_retry
from ytitle.timeutil import utc_iso

VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
BATCH_SIZE = 50
PHASES = ("before", "after", "periodic")

# Analytics 지표 이름은 원문 미확인이다 [확인 필요]. 틀리면 이 상수만 고친다.
METRICS_FULL = ("views", "estimatedMinutesWatched", "videoThumbnailImpressions", "videoThumbnailImpressionsClickRate")
METRICS_BASIC = ("views", "estimatedMinutesWatched")
_METRIC_COLUMNS = {
    "views": "views",
    "estimatedMinutesWatched": "watch_minutes",
    "videoThumbnailImpressions": "impressions",
    "videoThumbnailImpressionsClickRate": "ctr",
}

_QUOTA_REASONS = frozenset({"quotaExceeded", "dailyLimitExceeded"})
_REASON_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
_DURATION_RE = re.compile(r"^P(?:(\d+)D)?(?:(T)(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_RELOGIN = "`python -m ytitle auth --read`로 다시 로그인하세요. 계속되면 03_manual_setup.md의 권한 설정을 확인하세요."


class ReadApiError(ApiError):
    """HTTP 상태를 함께 들고 있는 조회 오류. 지표 폴백 판단에 쓴다."""

    def __init__(self, message: str, next_step: str = "", *, retryable: bool = False, cause: str = "", http_status: int = 0) -> None:
        super().__init__(message, next_step, retryable=retryable, cause=cause)
        self.http_status = http_status


@dataclass
class FetchResult:
    requested: int = 0
    rows: list[dict] = field(default_factory=list)
    skipped: int = 0
    missing: int = 0


@dataclass
class MetricsResult:
    phase: str = "periodic"
    period_start: str = ""
    period_end: str = ""
    requested: int = 0
    rows: list[dict] = field(default_factory=list)
    skipped: int = 0
    missing: int = 0
    impressions_available: bool = True


def build_services(creds):
    """읽기 토큰으로 YouTube Data v3와 Analytics v2 서비스 객체를 만든다."""
    from googleapiclient.discovery import build

    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    return youtube, analytics


def parse_duration(value: Any) -> int | None:
    """ISO8601 `PT#H#M#S`(일 단위 포함)를 초로 바꾼다. 형식이 깨졌으면 None."""
    if not isinstance(value, str):
        return None
    m = _DURATION_RE.fullmatch(value)
    if not m:
        return None
    days, t, hours, minutes, seconds = m.groups()
    if days is None and (t is None or (hours is None and minutes is None and seconds is None)):
        return None
    if t is not None and hours is None and minutes is None and seconds is None:
        return None
    return int(days or 0) * 86400 + int(hours or 0) * 3600 + int(minutes or 0) * 60 + int(seconds or 0)


def _reason(exc: HttpError) -> str:
    try:
        content = exc.content.decode("utf-8", "replace") if isinstance(exc.content, bytes) else str(exc.content)
        reason = json.loads(content)["error"]["errors"][0]["reason"]
    except Exception:
        return ""
    return reason if isinstance(reason, str) and _REASON_RE.match(reason) else ""


def _convert(exc: Exception) -> Exception:
    """외부 예외를 우리 오류로 바꾼다. 응답 본문·토큰은 메시지에 넣지 않고 상태와 reason 코드만 남긴다."""
    if isinstance(exc, YtError):
        return exc
    if isinstance(exc, HttpError):
        status = int(getattr(exc.resp, "status", 0) or 0)
        reason = _reason(exc)
        tag = f"HTTP {status}" + (f" {reason}" if reason else "")
        if status == 403 and reason in _QUOTA_REASONS:
            return QuotaError("구글이 오늘 API 쿼터를 모두 썼다고 응답했습니다.", RESET_HINT, cause=tag)
        if status in (401, 403):
            return AuthError("구글이 로그인 정보나 권한을 받아들이지 않았습니다.", _RELOGIN, cause=tag)
        if status == 429 or status >= 500:
            return ReadApiError("구글 서버가 일시적으로 응답하지 못했습니다.", "잠시 후 다시 실행하세요.", retryable=True, cause=tag, http_status=status)
        return ReadApiError("구글이 요청을 받아들이지 않았습니다.", "같은 오류가 반복되면 로그(data/logs/ytitle.log)를 확인하고 알려 주세요.", cause=tag, http_status=status)
    if isinstance(exc, (OSError, httplib2.HttpLib2Error)):
        return ReadApiError("구글 서버에 연결하지 못했습니다.", "인터넷 연결을 확인하고 다시 실행하세요.", retryable=True, cause=type(exc).__name__)
    return exc


def _dig(obj: Any, *keys: str) -> Any:
    for k in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return obj


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _clean_ids(ids: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for vid in ids:
        if not isinstance(vid, str) or not VIDEO_ID_RE.match(vid):
            raise InputError("영상 ID 형식이 올바르지 않습니다(영문·숫자·-·_ 11자).", "영상 ID를 확인하고 다시 입력하세요.")
        if vid not in seen:
            seen.add(vid)
            out.append(vid)
    return out


def _to_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise InputError("지표 기간 날짜 형식이 올바르지 않습니다.", "YYYY-MM-DD 형식을 쓰세요.") from exc


def _number(value: Any, kind: type) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return kind(value)


class YouTubeReader:
    def __init__(self, youtube, analytics, quota: QuotaManager, conn: sqlite3.Connection, settings: Settings, clock, sleep: Callable[[float], None] = time.sleep, *, run_id: str | None = None) -> None:
        self._youtube = youtube
        self._analytics = analytics
        self.quota = quota
        self._conn = conn
        self._settings = settings
        self._clock = clock
        self._sleep = sleep
        self._run_id = run_id
        self.skipped_playlist_items = 0

    def _call(self, method: str, cost: int, make_request: Callable[[], Any]) -> dict:
        def attempt() -> dict:
            reserve_id = self.quota.reserve(method, cost, self._run_id)
            try:
                response = make_request().execute()
            except BaseException as exc:
                self.quota.mark(reserve_id, "failed")
                if isinstance(exc, Exception):
                    raise _convert(exc) from None
                raise
            self.quota.mark(reserve_id, "ok")
            return response

        response = call_with_retry(attempt, sleep=self._sleep)
        if not isinstance(response, dict):
            raise ApiError("구글 응답 형식이 예상과 다릅니다.", "잠시 후 다시 시도하고, 반복되면 로그를 확인해 알려 주세요.", cause=f"{method} 응답이 객체가 아님")
        return response

    def list_channel_video_ids(self) -> list[str]:
        """업로드 재생목록을 전 페이지 순회해 영상 ID를 모은다(EVT-101, EVT-102)."""
        cost = self._settings.read_cost
        resp = self._call("channels.list", cost, lambda: self._youtube.channels().list(part="contentDetails", mine=True))
        items = resp.get("items")
        uploads = _dig(items[0], "contentDetails", "relatedPlaylists", "uploads") if isinstance(items, list) and items else None
        if not isinstance(uploads, str) or not uploads:
            raise ApiError("채널의 업로드 목록을 찾지 못했습니다.", "읽기 로그인한 계정이 채널 소유 계정인지 확인하세요.", cause="channels.list 응답에 uploads 없음")

        ids: list[str] = []
        seen: set[str] = set()
        tokens: set[str] = set()
        token: str | None = None
        while True:
            params: dict[str, Any] = {"part": "contentDetails", "playlistId": uploads, "maxResults": BATCH_SIZE}
            if token:
                params["pageToken"] = token
            page = self._call("playlistItems.list", cost, lambda p=params: self._youtube.playlistItems().list(**p))
            entries = page.get("items")
            if not isinstance(entries, list):
                raise ApiError("구글 응답 형식이 예상과 다릅니다.", "잠시 후 다시 시도하세요.", cause="playlistItems.list items가 목록이 아님")
            for entry in entries:
                vid = _dig(entry, "contentDetails", "videoId")
                if not isinstance(vid, str) or not VIDEO_ID_RE.match(vid):
                    self.skipped_playlist_items += 1
                elif vid not in seen:
                    seen.add(vid)
                    ids.append(vid)
            token = page.get("nextPageToken")
            if not token:
                return ids
            if not isinstance(token, str) or token in tokens:
                raise ApiError("구글이 같은 페이지를 반복해서 돌려줘 중단했습니다.", "잠시 후 다시 시도하세요.", cause="pageToken 반복")
            tokens.add(token)

    def fetch_videos(self, video_ids: Iterable[str]) -> FetchResult:
        """최대 50개씩 배치로 snippet·상태를 조회해 videos 테이블에 upsert한다(EVT-103)."""
        ids = _clean_ids(video_ids)
        result = FetchResult(requested=len(ids))
        for batch in _chunks(ids, BATCH_SIZE):
            resp = self._call("videos.list", self._settings.read_cost, lambda b=batch: self._youtube.videos().list(part="snippet,status,contentDetails", id=",".join(b)))
            items = resp.get("items")
            if not isinstance(items, list):
                raise ApiError("구글 응답 형식이 예상과 다릅니다.", "잠시 후 다시 시도하세요.", cause="videos.list items가 목록이 아님")
            fetched_at = utc_iso(self._clock.now())
            wanted, got = set(batch), set()
            rows = []
            for item in items:
                row = _normalize_video(item, fetched_at)
                if row is None or row["video_id"] not in wanted or row["video_id"] in got:
                    result.skipped += 1
                    continue
                got.add(row["video_id"])
                rows.append(row)
            self._upsert_videos(rows)
            result.rows.extend(rows)
            result.missing += len(wanted - got)
        return result

    def _upsert_videos(self, rows: list[dict]) -> None:
        try:
            with self._conn:
                for r in rows:
                    self._conn.execute(
                        "INSERT INTO videos (video_id, title, category_id, privacy_status, made_for_kids, live_broadcast_content, "
                        "duration_sec, description_excerpt, snippet_json, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(video_id) DO UPDATE SET title=excluded.title, category_id=excluded.category_id, "
                        "privacy_status=excluded.privacy_status, made_for_kids=excluded.made_for_kids, "
                        "live_broadcast_content=excluded.live_broadcast_content, duration_sec=excluded.duration_sec, "
                        "description_excerpt=excluded.description_excerpt, snippet_json=excluded.snippet_json, fetched_at=excluded.fetched_at",
                        (r["video_id"], r["title"], r["category_id"], r["privacy_status"], r["made_for_kids"], r["live_broadcast_content"],
                         r["duration_sec"], r["description_excerpt"], r["snippet_json"], r["fetched_at"]),
                    )
        except sqlite3.Error as exc:
            raise DatabaseError("조회한 영상 정보를 저장하지 못했습니다.", "data 폴더의 쓰기 권한과 디스크 공간을 확인하세요.", cause=type(exc).__name__) from exc

    def fetch_metrics(self, video_ids: Iterable[str], start_date: date | str, end_date: date | str, phase: str) -> MetricsResult:
        """영상별 지표를 받아 metrics_snapshots에 저장한다(EVT-105). 노출수·CTR 지표가 거부되면 기본 지표로 다시 시도한다."""
        if phase not in PHASES:
            raise InputError(f"지표 단계 값이 올바르지 않습니다: {phase!r}", "before, after, periodic 중 하나를 쓰세요.")
        start, end = _to_date(start_date), _to_date(end_date)
        if start > end:
            raise InputError("지표 기간의 시작일이 종료일보다 늦습니다.", "기간을 확인하세요.")
        ids = _clean_ids(video_ids)
        result = MetricsResult(phase=phase, period_start=start.isoformat(), period_end=end.isoformat(), requested=len(ids))
        for batch in _chunks(ids, BATCH_SIZE):
            metrics = METRICS_FULL if result.impressions_available else METRICS_BASIC
            try:
                resp = self._query(batch, result, metrics)
            except ReadApiError as exc:
                if metrics is not METRICS_FULL or exc.http_status != 400:
                    raise
                result.impressions_available = False
                resp = self._query(batch, result, METRICS_BASIC)
            self._store_metrics(batch, resp, result)
        return result

    def _query(self, batch: list[str], result: MetricsResult, metrics: tuple[str, ...]) -> dict:
        return self._call(
            "reports.query",
            self._settings.analytics_cost,
            lambda: self._analytics.reports().query(
                ids="channel==MINE",
                startDate=result.period_start,
                endDate=result.period_end,
                dimensions="video",
                metrics=",".join(metrics),
                filters="video==" + ",".join(batch),
            ),
        )

    def _store_metrics(self, batch: list[str], resp: dict, result: MetricsResult) -> None:
        headers = resp.get("columnHeaders")
        names = [h.get("name") if isinstance(h, dict) else None for h in headers] if isinstance(headers, list) else None
        if not names or "video" not in names or not all(isinstance(n, str) for n in names):
            raise ApiError("구글 지표 응답 형식이 예상과 다릅니다.", "지표 이름이 바뀌었을 수 있습니다. 로그를 확인하고 알려 주세요.", cause="reports.query columnHeaders 이상")
        rows = resp.get("rows") if resp.get("rows") is not None else []
        if not isinstance(rows, list):
            raise ApiError("구글 지표 응답 형식이 예상과 다릅니다.", "잠시 후 다시 시도하세요.", cause="reports.query rows가 목록이 아님")
        vid_at = names.index("video")
        wanted, got = set(batch), set()
        taken_at = utc_iso(self._clock.now())
        out = []
        for row in rows:
            if not isinstance(row, list) or len(row) != len(names) or not isinstance(row[vid_at], str) or row[vid_at] not in wanted or row[vid_at] in got:
                result.skipped += 1
                continue
            got.add(row[vid_at])
            record = dict(zip(names, row))
            values = {col: None for col in _METRIC_COLUMNS.values()}
            for metric, col in _METRIC_COLUMNS.items():
                if metric in record:
                    values[col] = _number(record[metric], float if col in ("ctr", "watch_minutes") else int)
            out.append({"video_id": row[vid_at], **values, "raw_json": json.dumps(record, ensure_ascii=False)})
        try:
            with self._conn:
                for r in out:
                    self._conn.execute(
                        "INSERT INTO metrics_snapshots (video_id, taken_at, phase, source, period_start, period_end, impressions, ctr, views, watch_minutes, raw_json) "
                        "VALUES (?,?,?,'api',?,?,?,?,?,?,?)",
                        (r["video_id"], taken_at, result.phase, result.period_start, result.period_end, r["impressions"], r["ctr"], r["views"], r["watch_minutes"], r["raw_json"]),
                    )
        except sqlite3.Error as exc:
            raise DatabaseError("지표를 저장하지 못했습니다.", "data 폴더의 쓰기 권한과 디스크 공간을 확인하세요.", cause=type(exc).__name__) from exc
        result.rows.extend(out)
        result.missing += len(wanted - got)


def _normalize_video(item: Any, fetched_at: str) -> dict | None:
    vid = item.get("id") if isinstance(item, dict) else None
    snippet = item.get("snippet") if isinstance(item, dict) else None
    title = snippet.get("title") if isinstance(snippet, dict) else None
    if not isinstance(vid, str) or not vid or not isinstance(title, str) or not title:
        return None
    status = item.get("status") if isinstance(item.get("status"), dict) else {}
    kids = status.get("madeForKids")
    description = snippet.get("description")
    category = snippet.get("categoryId")
    live = snippet.get("liveBroadcastContent")
    privacy = status.get("privacyStatus")
    return {
        "video_id": vid,
        "title": title,
        "category_id": category if isinstance(category, str) else None,
        "privacy_status": privacy if isinstance(privacy, str) else None,
        "made_for_kids": (1 if kids else 0) if isinstance(kids, bool) else None,
        "live_broadcast_content": live if isinstance(live, str) else None,
        "duration_sec": parse_duration(_dig(item, "contentDetails", "duration")),
        "description_excerpt": description[:500] if isinstance(description, str) else None,
        "snippet_json": json.dumps(snippet, ensure_ascii=False),
        "fetched_at": fetched_at,
    }
