import json
import re
from datetime import timedelta
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httplib2
import pytest
from googleapiclient.errors import HttpError

import youtube_title
from youtube_title import cli, db
from youtube_title import youtube_read as yr
from youtube_title.commands import fetch as fetch_cmd
from youtube_title.config import load_settings
from youtube_title.errors import ApiError, AuthError, InputError, QuotaError
from youtube_title.quota import QuotaManager
from youtube_title.youtube_read import YouTubeReader, parse_duration

SECRET = "ya29.FAKE-TOKEN-123"
READ_METHODS = {("channels", "list"), ("playlistItems", "list"), ("videos", "list"), ("reports", "query")}


def vid(n):
    return f"vid{n:08d}"


def http_error(status, reason="", message=f"SECRET-BODY {SECRET}"):
    body = {"error": {"code": status, "message": message, "errors": [{"message": message, "domain": "youtube.quota", "reason": reason}]}}
    return HttpError(httplib2.Response({"status": str(status)}), json.dumps(body).encode("utf-8"), uri="https://www.googleapis.com/youtube/v3/videos?key=SECRETKEY")


class _Req:
    def __init__(self, api, key, kwargs):
        self.api, self.key, self.kwargs = api, key, kwargs

    def execute(self):
        self.api.calls.append((self.key, self.kwargs))
        out = self.api.handlers[self.key](self.kwargs)
        if isinstance(out, BaseException):
            raise out
        return out


class _Resource:
    def __init__(self, api, name):
        self._api, self._name = api, name

    def __getattr__(self, method):
        if (self._name, method) not in READ_METHODS:
            raise AttributeError(f"허용되지 않은 호출: {self._name}.{method}")
        return lambda **kw: _Req(self._api, f"{self._name}.{method}", kw)


class Api:
    """googleapiclient 서비스 객체를 흉내 낸다. 읽기 메서드 4개만 존재하고 그 밖의 메서드는 AttributeError."""

    def __init__(self):
        self.calls, self.handlers = [], {}

    def on(self, key, handler):
        self.handlers[key] = handler
        return self

    def seq(self, key, *items):
        queue = list(items)
        return self.on(key, lambda kw: queue.pop(0) if len(queue) > 1 else queue[0])

    def count(self, key):
        return sum(1 for k, _ in self.calls if k == key)

    def kwargs(self, key):
        return [kw for k, kw in self.calls if k == key]

    def channels(self):
        return _Resource(self, "channels")

    def playlistItems(self):
        return _Resource(self, "playlistItems")

    def videos(self):
        return _Resource(self, "videos")

    def reports(self):
        return _Resource(self, "reports")


def video_item(video_id, title="제목", **snippet_extra):
    return {
        "id": video_id,
        "snippet": {"title": title, "description": "설명", "categoryId": "26", "liveBroadcastContent": "none", **snippet_extra},
        "status": {"privacyStatus": "public", "madeForKids": False},
        "contentDetails": {"duration": "PT1M"},
    }


def echo_videos(kw):
    return {"items": [video_item(i, f"제목 {i}") for i in kw["id"].split(",")]}


def build(project, clock, yt=None, an=None, **overrides):
    settings = replace(load_settings(project, env={}), **overrides)
    conn = db.connect(":memory:")
    db.migrate(conn)
    yt = yt or Api().on("videos.list", echo_videos)
    an = an or Api()
    quota = QuotaManager(conn, settings, clock)
    sleeps = []
    reader = YouTubeReader(yt, an, quota, conn, settings, clock, sleep=sleeps.append, run_id="run-test")
    return SimpleNamespace(reader=reader, conn=conn, quota=quota, yt=yt, an=an, sleeps=sleeps, settings=settings)


def quota_rows(conn):
    return [(r["method"], r["units"], r["status"]) for r in conn.execute("SELECT method, units, status FROM quota_usage ORDER BY id")]


def video_rows(conn):
    return {r["video_id"]: dict(r) for r in conn.execute("SELECT * FROM videos")}


def metrics_response(rows, names=("video", "views", "estimatedMinutesWatched", "videoThumbnailImpressions", "videoThumbnailImpressionsClickRate")):
    return {"columnHeaders": [{"name": n, "columnType": "X", "dataType": "STRING"} for n in names], "rows": rows}


# ---------------------------------------------------------------- 채널 영상 목록


def test_list_ids_walks_all_pages(project, clock):
    """TC-220: 업로드 재생목록을 전 페이지(50/50/7) 순회해 순서대로 ID를 모으고 호출마다 쿼터를 예약한다. [FR-006, SEC-002]"""
    yt = Api()
    yt.on("channels.list", lambda kw: {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUplay"}}}]})
    pages = {
        None: {"items": [{"contentDetails": {"videoId": vid(i)}} for i in range(0, 50)], "nextPageToken": "T1"},
        "T1": {"items": [{"contentDetails": {"videoId": vid(i)}} for i in range(50, 100)], "nextPageToken": "T2"},
        "T2": {"items": [{"contentDetails": {"videoId": vid(i)}} for i in range(100, 107)]},
    }
    yt.on("playlistItems.list", lambda kw: pages[kw.get("pageToken")])
    e = build(project, clock, yt)
    ids = e.reader.list_channel_video_ids()
    assert ids == [vid(i) for i in range(107)]
    assert yt.kwargs("channels.list") == [{"part": "contentDetails", "mine": True}]
    base = {"part": "contentDetails", "playlistId": "UUplay", "maxResults": 50}
    assert yt.kwargs("playlistItems.list") == [base, {**base, "pageToken": "T1"}, {**base, "pageToken": "T2"}]
    assert quota_rows(e.conn) == [("channels.list", 1, "ok")] + [("playlistItems.list", 1, "ok")] * 3


@pytest.mark.parametrize("resp", [{}, {"items": []}, {"items": "x"}, {"items": [{}]}, {"items": [{"contentDetails": {"relatedPlaylists": {}}}]}, {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": ""}}}]}])
def test_list_ids_channel_contract_violation(project, clock, resp):
    """TC-221: 채널 응답에 업로드 재생목록이 없으면 ApiError이고 재생목록 호출은 하지 않는다. [FR-006, NFR-007]"""
    yt = Api().on("channels.list", lambda kw: resp)
    e = build(project, clock, yt)
    with pytest.raises(ApiError) as ei:
        e.reader.list_channel_video_ids()
    assert ei.value.code == "YT-700" and ei.value.next_step
    assert yt.count("playlistItems.list") == 0


def test_list_ids_skips_invalid_and_duplicate_entries(project, clock):
    """TC-222: 재생목록 항목 중 형식이 틀린 ID는 건너뛰어 개수로 세고 중복은 한 번만 담는다. 목록이 아니면 ApiError. [FR-006]"""
    yt = Api().on("channels.list", lambda kw: {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "U"}}}]})
    yt.seq(
        "playlistItems.list",
        {"items": [{"contentDetails": {"videoId": vid(1)}}, {"contentDetails": {"videoId": "bad id"}}, {}, {"contentDetails": {"videoId": 5}}, {"contentDetails": {"videoId": vid(1)}}, {"contentDetails": {"videoId": vid(2)}}]},
    )
    e = build(project, clock, yt)
    assert e.reader.list_channel_video_ids() == [vid(1), vid(2)]
    assert e.reader.skipped_playlist_items == 3
    yt2 = Api().on("channels.list", lambda kw: {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "U"}}}]}).on("playlistItems.list", lambda kw: {"items": None})
    with pytest.raises(ApiError):
        build(project, clock, yt2).reader.list_channel_video_ids()


def test_list_ids_stops_on_repeated_page_token(project, clock):
    """TC-223: 같은 pageToken이 반복되면 무한 순회하지 않고 ApiError로 중단한다. [FR-006, SEC-002]"""
    yt = Api().on("channels.list", lambda kw: {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "U"}}}]})
    yt.on("playlistItems.list", lambda kw: {"items": [], "nextPageToken": "SAME"})
    e = build(project, clock, yt)
    with pytest.raises(ApiError):
        e.reader.list_channel_video_ids()
    assert yt.count("playlistItems.list") == 2


# ---------------------------------------------------------------- videos.list 배치와 정규화


def test_fetch_videos_splits_120_ids_into_50_50_20(project, clock):
    """TC-224: 영상 ID 120개는 videos.list 3번(50/50/20)으로 나눠 조회하고 모두 저장하며 호출마다 1 unit을 예약한다. [FR-006, SEC-002]"""
    e = build(project, clock)
    ids = [vid(i) for i in range(120)]
    res = e.reader.fetch_videos(ids)
    calls = e.yt.kwargs("videos.list")
    assert [len(c["id"].split(",")) for c in calls] == [50, 50, 20]
    assert [c["id"] for c in calls] == [",".join(ids[:50]), ",".join(ids[50:100]), ",".join(ids[100:])]
    assert all(c["part"] == "snippet,status,contentDetails" for c in calls)
    assert len(video_rows(e.conn)) == 120 and len(res.rows) == 120 and res.skipped == 0 and res.missing == 0
    assert quota_rows(e.conn) == [("videos.list", 1, "ok")] * 3


@pytest.mark.parametrize("n,sizes", [(1, [1]), (50, [50]), (51, [50, 1]), (100, [50, 50]), (101, [50, 50, 1])])
def test_batch_boundaries(project, clock, n, sizes):
    """TC-225: 배치 경계(1/50/51/100/101개)에서 한 번에 50개를 넘기지 않는다. [FR-006]"""
    e = build(project, clock)
    e.reader.fetch_videos([vid(i) for i in range(n)])
    assert [len(c["id"].split(",")) for c in e.yt.kwargs("videos.list")] == sizes


def test_fetch_videos_empty_makes_no_call(project, clock):
    """TC-226: 조회할 ID가 없으면 API를 부르지 않고 쿼터도 쓰지 않는다. [FR-006, SEC-002]"""
    e = build(project, clock)
    res = e.reader.fetch_videos([])
    assert res.requested == 0 and res.rows == [] and e.yt.calls == [] and quota_rows(e.conn) == []


def test_fetch_videos_normalizes_korean_row(project, clock):
    """TC-227: 응답을 videos 행으로 정규화한다(한글 제목·설명, 카테고리, 공개 상태, 아동용, 길이, 조회 시각). [FR-006, SEC-018]"""
    item = {
        "id": "abcDEF12345",
        "snippet": {"title": "시니어 걷기 건강 팁", "description": "하루 30분 걷기 설명 🚶", "categoryId": "26", "liveBroadcastContent": "none", "tags": ["걷기", "건강"], "publishedAt": "2026-01-01T00:00:00Z"},
        "status": {"privacyStatus": "unlisted", "madeForKids": True},
        "contentDetails": {"duration": "PT1H2M3S"},
    }
    e = build(project, clock, Api().on("videos.list", lambda kw: {"items": [item]}))
    e.reader.fetch_videos(["abcDEF12345"])
    row = video_rows(e.conn)["abcDEF12345"]
    assert {k: v for k, v in row.items() if k != "snippet_json"} == {
        "video_id": "abcDEF12345", "title": "시니어 걷기 건강 팁", "category_id": "26", "privacy_status": "unlisted", "made_for_kids": 1,
        "live_broadcast_content": "none", "duration_sec": 3723, "description_excerpt": "하루 30분 걷기 설명 🚶", "fetched_at": "2026-10-10T12:00:00Z",
    }
    assert json.loads(row["snippet_json"]) == item["snippet"]
    assert "시니어 걷기 건강 팁" in row["snippet_json"] and "\\u" not in row["snippet_json"]


@pytest.mark.parametrize(
    "text,seconds",
    [("PT1H2M3S", 3723), ("PT45S", 45), ("PT10M", 600), ("PT1H", 3600), ("PT0S", 0), ("P0D", 0), ("P1DT2H", 93600), ("P1D", 86400),
     ("PT", None), ("P", None), ("P1DT", None), ("1H2M", None), ("pt5s", None), ("", None), ("PT-5S", None), ("PT5S\n", None), ("PT1H2M3SX", None), ("garbage", None), (None, None), (123, None)],
)
def test_parse_duration_boundaries(text, seconds):
    """TC-228: ISO8601 길이 파싱 경계값(PT1H2M3S, PT45S, P0D)과 깨진 값은 None이다. [FR-006]"""
    assert parse_duration(text) == seconds


def test_description_excerpt_is_first_500_chars_and_bad_duration_is_null(project, clock):
    """TC-229: 설명은 앞 500자만 저장되고(전체는 snippet_json에 보존) 깨진 길이는 NULL이어도 영상은 저장된다. [FR-006, NFR-009]"""
    long_desc = "가" * 600
    item = video_item("abcDEF12345", description=long_desc)
    item["contentDetails"]["duration"] = "엉터리"
    e = build(project, clock, Api().on("videos.list", lambda kw: {"items": [item]}))
    e.reader.fetch_videos(["abcDEF12345"])
    row = video_rows(e.conn)["abcDEF12345"]
    assert row["description_excerpt"] == "가" * 500 and row["duration_sec"] is None
    assert json.loads(row["snippet_json"])["description"] == long_desc


@pytest.mark.parametrize(
    "status,privacy,kids",
    [({"privacyStatus": "public", "madeForKids": True}, "public", 1), ({"privacyStatus": "private", "madeForKids": False}, "private", 0),
     ({"privacyStatus": "public"}, "public", None), ({"madeForKids": "yes"}, None, None), (None, None, None), ({}, None, None)],
)
def test_privacy_and_kids_mapping(project, clock, status, privacy, kids):
    """TC-230: status의 공개 상태와 madeForKids(true→1, false→0, 없거나 불린이 아님→NULL) 변환. [FR-006]"""
    item = video_item("abcDEF12345")
    item["status"] = status
    if status is None:
        del item["status"]
    e = build(project, clock, Api().on("videos.list", lambda kw: {"items": [item]}))
    e.reader.fetch_videos(["abcDEF12345"])
    row = video_rows(e.conn)["abcDEF12345"]
    assert (row["privacy_status"], row["made_for_kids"]) == (privacy, kids)


@pytest.mark.parametrize("resp", [{}, {"items": None}, {"items": "x"}, {"items": {"a": 1}}])
def test_fetch_videos_items_contract_violation(project, clock, resp):
    """TC-231: 응답의 items가 없거나 목록이 아니면 ApiError이고 DB에 저장하지 않는다. [FR-006, NFR-007]"""
    e = build(project, clock, Api().on("videos.list", lambda kw: resp))
    with pytest.raises(ApiError) as ei:
        e.reader.fetch_videos(["abcDEF12345"])
    assert ei.value.next_step and video_rows(e.conn) == {}


def test_fetch_videos_skips_malformed_items_and_counts(project, clock):
    """TC-232: id·제목이 없거나 요청하지 않은 ID·중복 항목은 건너뛰어 개수를 세고 정상 항목만 저장한다. [FR-006]"""
    ok1, ok2 = vid(1), vid(2)
    no_title = video_item(vid(3))
    del no_title["snippet"]["title"]
    no_id = video_item(vid(4))
    del no_id["id"]
    items = [video_item(ok1), "문자열", None, no_title, no_id, video_item(vid(5), title=""), video_item("other000000"), video_item(ok1), video_item(ok2)]
    e = build(project, clock, Api().on("videos.list", lambda kw: {"items": items}))
    res = e.reader.fetch_videos([ok1, ok2, vid(3), vid(4), vid(5), vid(6)])
    assert sorted(video_rows(e.conn)) == [ok1, ok2]
    assert res.skipped == 7 and res.missing == 4 and res.requested == 6 and [r["video_id"] for r in res.rows] == [ok1, ok2]


def test_fetch_videos_upserts_existing_row(project, clock):
    """TC-233: 같은 영상을 다시 조회하면 행이 늘지 않고 제목·조회 시각이 최신으로 갱신된다. [FR-006]"""
    titles = iter(["처음 제목", "바뀐 제목"])
    e = build(project, clock, Api().on("videos.list", lambda kw: {"items": [video_item("abcDEF12345", next(titles))]}))
    e.reader.fetch_videos(["abcDEF12345"])
    clock.advance(timedelta(hours=1))
    e.reader.fetch_videos(["abcDEF12345"])
    rows = video_rows(e.conn)
    assert len(rows) == 1 and rows["abcDEF12345"]["title"] == "바뀐 제목" and rows["abcDEF12345"]["fetched_at"] == "2026-10-10T13:00:00Z"


def test_malicious_title_is_stored_as_plain_value(project, clock):
    """TC-234: SQL 조각·ANSI 이스케이프가 든 제목도 값 그대로 저장되고 테이블은 멀쩡하다. [SEC-018, SEC-019]"""
    evil = "x'); DROP TABLE videos;--\x1b[31m빨강"
    e = build(project, clock, Api().on("videos.list", lambda kw: {"items": [video_item("abcDEF12345", evil)]}))
    e.reader.fetch_videos(["abcDEF12345"])
    assert video_rows(e.conn)["abcDEF12345"]["title"] == evil


@pytest.mark.parametrize("bad", ["short", "abc def ghi", "abcdefghij!", "x" * 12, "", None, 123])
def test_fetch_videos_rejects_invalid_ids(project, clock, bad):
    """TC-235: 형식이 틀린 영상 ID가 하나라도 있으면 InputError이고 API를 전혀 부르지 않는다. [FR-006, SEC-002]"""
    e = build(project, clock)
    with pytest.raises(InputError):
        e.reader.fetch_videos([vid(1), bad])
    assert e.yt.calls == [] and quota_rows(e.conn) == []


def test_fetch_videos_dedupes_requested_ids(project, clock):
    """TC-236: 요청 ID 중복은 한 번만 조회해 쿼터를 아낀다. [FR-006, SEC-002]"""
    e = build(project, clock)
    res = e.reader.fetch_videos([vid(1), vid(1), vid(2)])
    assert e.yt.kwargs("videos.list")[0]["id"] == f"{vid(1)},{vid(2)}" and res.requested == 2


# ---------------------------------------------------------------- Analytics 지표


def test_fetch_metrics_saves_snapshot(project, clock):
    """TC-240: 지표 조회 요청 모양(채널·기간·차원·지표·필터)과 metrics_snapshots 저장(단계, 출처 api, 기간, 값, 원본)을 확인한다. [FR-007, SEC-002]"""
    an = Api().on("reports.query", lambda kw: metrics_response([[vid(1), 100, 55.5, 2000, 4.5], [vid(2), 7, 1.0, 40, 0.0]]))
    e = build(project, clock, an=an)
    res = e.reader.fetch_metrics([vid(1), vid(2)], "2026-09-12", "2026-10-09", "before")
    assert an.kwargs("reports.query") == [{
        "ids": "channel==MINE", "startDate": "2026-09-12", "endDate": "2026-10-09", "dimensions": "video",
        "metrics": "views,estimatedMinutesWatched,videoThumbnailImpressions,videoThumbnailImpressionsClickRate", "filters": f"video=={vid(1)},{vid(2)}",
    }]
    rows = [dict(r) for r in e.conn.execute("SELECT * FROM metrics_snapshots ORDER BY id")]
    assert len(rows) == 2 and res.impressions_available is True
    r = rows[0]
    assert (r["video_id"], r["phase"], r["source"], r["period_start"], r["period_end"]) == (vid(1), "before", "api", "2026-09-12", "2026-10-09")
    assert (r["views"], r["watch_minutes"], r["impressions"], r["ctr"], r["taken_at"]) == (100, 55.5, 2000, 4.5, "2026-10-10T12:00:00Z")
    assert json.loads(r["raw_json"])["video"] == vid(1)
    assert quota_rows(e.conn) == [("reports.query", 1, "ok")]


def test_fetch_metrics_falls_back_when_impressions_rejected(project, clock):
    """TC-241: 노출수·CTR 지표가 400으로 거부되면 views,estimatedMinutesWatched만으로 재시도하고 impressions_available=False로 알린다. [FR-007, SEC-002]"""
    def handler(kw):
        if "videoThumbnailImpressions" in kw["metrics"]:
            return http_error(400, "badRequest")
        return metrics_response([[vid(1), 10, 2.5]], names=("video", "views", "estimatedMinutesWatched"))

    an = Api().on("reports.query", handler)
    e = build(project, clock, an=an)
    res = e.reader.fetch_metrics([vid(1)], "2026-09-12", "2026-10-09", "periodic")
    assert [kw["metrics"] for kw in an.kwargs("reports.query")] == ["views,estimatedMinutesWatched,videoThumbnailImpressions,videoThumbnailImpressionsClickRate", "views,estimatedMinutesWatched"]
    assert res.impressions_available is False and len(res.rows) == 1
    r = e.conn.execute("SELECT * FROM metrics_snapshots").fetchone()
    assert (r["views"], r["watch_minutes"], r["impressions"], r["ctr"]) == (10, 2.5, None, None)
    assert quota_rows(e.conn) == [("reports.query", 1, "failed"), ("reports.query", 1, "ok")]
    assert e.sleeps == []


@pytest.mark.parametrize("status,reason,exc_type", [(403, "quotaExceeded", QuotaError), (403, "forbidden", AuthError), (404, "notFound", ApiError), (500, "backendError", ApiError)])
def test_fetch_metrics_no_fallback_except_400(project, clock, status, reason, exc_type):
    """TC-242: 400이 아닌 오류(쿼터·권한·404·5xx)는 기본 지표로 폴백하지 않고 그대로 변환된 오류를 낸다. [FR-007]"""
    an = Api().on("reports.query", lambda kw: http_error(status, reason))
    e = build(project, clock, an=an)
    with pytest.raises(exc_type):
        e.reader.fetch_metrics([vid(1)], "2026-09-12", "2026-10-09", "periodic")
    assert all("videoThumbnailImpressions" in kw["metrics"] for kw in an.kwargs("reports.query"))
    assert e.conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0] == 0


@pytest.mark.parametrize(
    "ids,start,end,phase",
    [([vid(1)], "2026-09-12", "2026-10-09", "monthly"), ([vid(1)], "2026-10-09", "2026-09-12", "before"), ([vid(1)], "2026/09/12", "2026-10-09", "before"), (["bad"], "2026-09-12", "2026-10-09", "after")],
)
def test_fetch_metrics_input_validation(project, clock, ids, start, end, phase):
    """TC-243: 잘못된 단계·날짜 순서·날짜 형식·영상 ID는 InputError이고 API를 부르지 않는다. [FR-007, SEC-002]"""
    e = build(project, clock)
    with pytest.raises(InputError):
        e.reader.fetch_metrics(ids, start, end, phase)
    assert e.an.calls == [] and quota_rows(e.conn) == []


@pytest.mark.parametrize(
    "resp",
    [{}, {"rows": []}, {"columnHeaders": "x", "rows": []}, {"columnHeaders": [], "rows": []}, {"columnHeaders": [{"name": "views"}], "rows": []}, {"columnHeaders": [{"x": 1}, {"name": "video"}], "rows": []}, metrics_response("x")],
)
def test_fetch_metrics_contract_violation(project, clock, resp):
    """TC-244: 지표 응답의 열 머리글이 없거나 video 열이 없거나 rows가 목록이 아니면 ApiError이고 저장하지 않는다. [FR-007, NFR-007]"""
    e = build(project, clock, an=Api().on("reports.query", lambda kw: resp))
    with pytest.raises(ApiError):
        e.reader.fetch_metrics([vid(1)], "2026-09-12", "2026-10-09", "periodic")
    assert e.conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0] == 0


def test_fetch_metrics_skips_bad_rows_and_counts_missing(project, clock):
    """TC-245: 열 수가 다른 행·요청하지 않은 영상·중복 행은 건너뛰고, 지표가 없는 영상은 missing으로 센다. 숫자가 아닌 값은 NULL. [FR-007]"""
    rows = [[vid(1), 5, 1.0, 10, 0.5], [vid(1), 6, 1.0, 10, 0.5], [vid(2), 1], [vid(9), 1, 1, 1, 1], [vid(3), "x", None, True, float("nan")], "행", [["list"], 1, 1, 1, 1]]
    e = build(project, clock, an=Api().on("reports.query", lambda kw: metrics_response(rows)))
    res = e.reader.fetch_metrics([vid(1), vid(2), vid(3), vid(4)], "2026-09-12", "2026-10-09", "after")
    assert res.skipped == 5 and res.missing == 2 and len(res.rows) == 2
    got = {r["video_id"]: dict(r) for r in e.conn.execute("SELECT * FROM metrics_snapshots")}
    assert got[vid(1)]["views"] == 5
    assert (got[vid(3)]["views"], got[vid(3)]["watch_minutes"], got[vid(3)]["impressions"], got[vid(3)]["ctr"]) == (None, None, None, None)


def test_fetch_metrics_no_rows_means_no_data(project, clock):
    """TC-246: rows가 없는 응답(기간 내 데이터 없음)은 오류가 아니라 missing으로 센다. [FR-007]"""
    e = build(project, clock, an=Api().on("reports.query", lambda kw: {"columnHeaders": [{"name": "video"}, {"name": "views"}]}))
    res = e.reader.fetch_metrics([vid(1)], "2026-09-12", "2026-10-09", "periodic")
    assert res.missing == 1 and res.rows == [] and e.conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0] == 0


def test_fetch_metrics_batches_ids_and_keeps_fallback_for_later_batches(project, clock):
    """TC-247: 지표 조회도 50개씩 나누고, 첫 배치에서 폴백이 일어나면 이후 배치는 거부될 지표를 다시 시도하지 않는다. [FR-007, SEC-002]"""
    def handler(kw):
        if "videoThumbnailImpressions" in kw["metrics"]:
            return http_error(400, "badRequest")
        ids = kw["filters"].removeprefix("video==").split(",")
        return metrics_response([[i, 1, 1.0] for i in ids], names=("video", "views", "estimatedMinutesWatched"))

    an = Api().on("reports.query", handler)
    e = build(project, clock, an=an)
    res = e.reader.fetch_metrics([vid(i) for i in range(120)], "2026-09-12", "2026-10-09", "periodic")
    calls = an.kwargs("reports.query")
    assert [len(c["filters"].removeprefix("video==").split(",")) for c in calls] == [50, 50, 50, 20]
    assert [c["metrics"].count(",") for c in calls] == [3, 1, 1, 1]
    assert len(res.rows) == 120 and res.impressions_available is False


# ---------------------------------------------------------------- 오류 변환·재시도


def run_videos(e):
    return e.reader.fetch_videos([vid(1)])


@pytest.mark.parametrize("reason", ["quotaExceeded", "dailyLimitExceeded"])
def test_quota_exceeded_http_error_is_quota_error_without_retry(project, clock, reason):
    """TC-250: 403 quotaExceeded/dailyLimitExceeded는 QuotaError(YT-300)로 바뀌고 재시도 0회이며 차감은 유지된다. [SEC-002, SEC-003, NFR-003]"""
    yt = Api().on("videos.list", lambda kw: http_error(403, reason))
    e = build(project, clock, yt)
    with pytest.raises(QuotaError) as ei:
        run_videos(e)
    assert ei.value.code == "YT-300" and "태평양" in ei.value.next_step and reason in ei.value.cause
    assert yt.count("videos.list") == 1 and e.sleeps == []
    assert quota_rows(e.conn) == [("videos.list", 1, "failed")]


@pytest.mark.parametrize("status,reason", [(401, "authError"), (403, "forbidden"), (403, "insufficientPermissions"), (403, "")])
def test_auth_http_error_is_auth_error_without_retry(project, clock, status, reason):
    """TC-251: 401과 쿼터가 아닌 403은 AuthError(YT-400)로 바뀌고 재시도 0회이며 재로그인을 안내한다. [SEC-003, FR-016, NFR-007]"""
    yt = Api().on("videos.list", lambda kw: http_error(status, reason))
    e = build(project, clock, yt)
    with pytest.raises(AuthError) as ei:
        run_videos(e)
    assert ei.value.code == "YT-400" and "auth --read" in ei.value.next_step
    assert yt.count("videos.list") == 1 and e.sleeps == []


def test_503_then_success_retries_once_and_charges_both_attempts(project, clock):
    """TC-252: 503 뒤 성공하면 1초 대기 후 재시도해 결과를 얻고, 시도마다 쿼터를 예약한다(failed 1 + ok 1). [NFR-004, SEC-003, SEC-002]"""
    yt = Api().seq("videos.list", http_error(503, "backendError"), {"items": [video_item(vid(1))]})
    e = build(project, clock, yt)
    res = run_videos(e)
    assert len(res.rows) == 1 and yt.count("videos.list") == 2 and e.sleeps == [1.0]
    assert quota_rows(e.conn) == [("videos.list", 1, "failed"), ("videos.list", 1, "ok")] and e.quota.used_today() == 2


def test_persistent_503_stops_after_two_retries(project, clock):
    """TC-253: 503이 계속되면 최대 2회 재시도(총 3회, 대기 1초·2초) 뒤 재시도 가능 표시의 ApiError로 끝난다. [NFR-004, SEC-003]"""
    yt = Api().on("videos.list", lambda kw: http_error(503, "backendError"))
    e = build(project, clock, yt)
    with pytest.raises(ApiError) as ei:
        run_videos(e)
    assert ei.value.retryable is True and ei.value.code == "YT-700" and "503" in ei.value.cause
    assert yt.count("videos.list") == 3 and e.sleeps == [1.0, 2.0]
    assert quota_rows(e.conn) == [("videos.list", 1, "failed")] * 3


def test_404_is_non_retryable_api_error(project, clock):
    """TC-254: 404 같은 그 밖의 4xx는 재시도하지 않는 ApiError(retryable=False)이고 호출은 1회뿐이다. [SEC-003, NFR-004]"""
    yt = Api().on("videos.list", lambda kw: http_error(404, "notFound"))
    e = build(project, clock, yt)
    with pytest.raises(ApiError) as ei:
        run_videos(e)
    assert ei.value.retryable is False and "404" in ei.value.cause
    assert yt.count("videos.list") == 1 and e.sleeps == []


@pytest.mark.parametrize("failure", [http_error(429, "rateLimitExceeded"), http_error(500), http_error(502), ConnectionResetError("reset"), TimeoutError("t"), httplib2.ServerNotFoundError("dns")])
def test_transient_failures_are_retryable(project, clock, failure):
    """TC-255: 429·5xx·연결 끊김·시간 초과·DNS 실패는 재시도 가능 ApiError로 바뀌어 총 3회 시도한다. [NFR-004, SEC-003]"""
    yt = Api().on("videos.list", lambda kw: failure)
    e = build(project, clock, yt)
    with pytest.raises(ApiError) as ei:
        run_videos(e)
    assert ei.value.retryable is True and yt.count("videos.list") == 3 and e.sleeps == [1.0, 2.0]


@pytest.mark.parametrize(
    "failure",
    [http_error(403, "quotaExceeded"), http_error(401, "authError"), http_error(503), http_error(404, "notFound"), http_error(400, "badRequest"), ConnectionError(f"Bearer {SECRET}")],
)
def test_error_messages_never_include_body_or_token(project, clock, failure):
    """TC-256: 변환된 오류의 메시지·다음 할 일·원인·문자열 표현 어디에도 응답 본문, 요청 주소의 키, 토큰이 없다. [SEC-008, NFR-007]"""
    yt = Api().on("videos.list", lambda kw: failure)
    e = build(project, clock, yt)
    with pytest.raises((QuotaError, AuthError, ApiError)) as ei:
        run_videos(e)
    err = ei.value
    text = " ".join([str(err), err.message, err.next_step, err.cause])
    for leaked in ("ya29", "SECRET-BODY", "SECRETKEY", "Bearer", "googleapis.com"):
        assert leaked not in text
    assert err.__cause__ is None


def test_local_quota_exhaustion_blocks_api_call(project, clock):
    """TC-257: 로컬 쿼터 상한에 닿으면 API를 부르기 전에 QuotaError로 막고 이후 호출은 0회이다(선예약). [SEC-002, FR-015, NFR-003]"""
    e = build(project, clock, daily_limit_units=1)
    with pytest.raises(QuotaError):
        e.reader.fetch_videos([vid(i) for i in range(60)])
    assert e.yt.count("videos.list") == 1
    assert quota_rows(e.conn) == [("videos.list", 1, "ok")]
    assert len(video_rows(e.conn)) == 50


def test_zero_quota_blocks_even_first_call(project, clock):
    """TC-258: 오늘 남은 쿼터가 비용보다 적으면 첫 호출부터 막힌다(API 호출 0회, DB 불변). [SEC-002, FR-015]"""
    e = build(project, clock, daily_limit_units=5, analytics_cost=6)
    with pytest.raises(QuotaError):
        e.reader.fetch_metrics([vid(1)], "2026-09-12", "2026-10-09", "periodic")
    assert e.an.calls == [] and quota_rows(e.conn) == []


def test_failure_in_later_batch_keeps_earlier_batch_and_charges(project, clock):
    """TC-259: 두 번째 배치가 계속 실패해도 첫 배치 저장분은 남고, 실패한 시도의 쿼터 차감도 유지된다. [FR-006, ADR-008]"""
    calls = {"n": 0}

    def handler(kw):
        calls["n"] += 1
        return echo_videos(kw) if calls["n"] == 1 else http_error(500)

    e = build(project, clock, Api().on("videos.list", handler))
    with pytest.raises(ApiError):
        e.reader.fetch_videos([vid(i) for i in range(60)])
    assert len(video_rows(e.conn)) == 50
    assert quota_rows(e.conn) == [("videos.list", 1, "ok")] + [("videos.list", 1, "failed")] * 3


def test_keyboard_interrupt_marks_reservation_failed(project, clock):
    """TC-260: 호출 중 사용자가 중단(Ctrl+C)해도 예약은 failed로 표시돼 차감이 남고 예외는 그대로 전달된다. [ADR-008, SEC-002]"""
    e = build(project, clock, Api().on("videos.list", lambda kw: KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        run_videos(e)
    assert quota_rows(e.conn) == [("videos.list", 1, "failed")]


def test_non_dict_response_is_contract_error(project, clock):
    """TC-261: 응답이 객체가 아니면 ApiError로 처리하고 저장하지 않는다. [FR-006, NFR-007]"""
    e = build(project, clock, Api().on("videos.list", lambda kw: ["x"]))
    with pytest.raises(ApiError):
        run_videos(e)
    assert video_rows(e.conn) == {}


@pytest.mark.parametrize("content", [b"<html>Bad Gateway</html>", b"", b'{"error": {"errors": [{"reason": "x y; DROP"}]}}', b'{"error": {"errors": [{"reason": 5}]}}', b'{"error": []}'])
def test_unparseable_error_body_gives_status_only_cause(project, clock, content):
    """TC-265: 본문이 JSON이 아니거나 reason이 이상해도 오류 변환은 상태 코드만 담아 정상 동작한다(본문은 버림). [SEC-008, NFR-007]"""
    err = HttpError(httplib2.Response({"status": "403"}), content)
    e = build(project, clock, Api().on("videos.list", lambda kw: err))
    with pytest.raises(AuthError) as ei:
        run_videos(e)
    assert ei.value.cause == "HTTP 403"


def test_unknown_exception_propagates_without_retry_and_charges(project, clock):
    """TC-266: 예상 밖의 예외(ValueError)는 변환·재시도 없이 그대로 전달되고 예약은 failed로 남는다. [SEC-003, ADR-008]"""
    yt = Api().on("videos.list", lambda kw: ValueError("boom"))
    e = build(project, clock, yt)
    with pytest.raises(ValueError):
        run_videos(e)
    assert yt.count("videos.list") == 1 and quota_rows(e.conn) == [("videos.list", 1, "failed")]


def test_fetch_metrics_accepts_date_objects(project, clock):
    """TC-267: 지표 기간은 date·datetime 객체로도 줄 수 있고 ISO 날짜 문자열로 요청된다. [FR-007]"""
    import datetime as dt

    an = Api().on("reports.query", lambda kw: metrics_response([]))
    e = build(project, clock, an=an)
    res = e.reader.fetch_metrics([vid(1)], dt.date(2026, 9, 12), dt.datetime(2026, 10, 9, 15, 0), "after")
    q = an.kwargs("reports.query")[0]
    assert (q["startDate"], q["endDate"]) == ("2026-09-12", "2026-10-09") and res.period_end == "2026-10-09"


def test_database_write_failure_becomes_database_error(project, clock):
    """TC-268: 영상·지표 저장 중 DB 오류는 한국어 DatabaseError(YT-200)로 바뀐다. [FR-006, FR-007, NFR-007]"""
    from youtube_title.errors import DatabaseError

    e = build(project, clock, an=Api().on("reports.query", lambda kw: metrics_response([[vid(1), 1, 1.0, 1, 1.0]])))
    e.conn.execute("DROP TABLE videos")
    e.conn.execute("DROP TABLE metrics_snapshots")
    with pytest.raises(DatabaseError) as ei:
        run_videos(e)
    assert ei.value.code == "YT-200" and ei.value.next_step
    with pytest.raises(DatabaseError):
        e.reader.fetch_metrics([vid(1)], "2026-09-12", "2026-10-09", "periodic")


# ---------------------------------------------------------------- 읽기 전용 보장


SRC = Path(youtube_title.__file__).parent
WRITE_CALL = re.compile(r"\.(update|insert|delete|patch|rate|setThumbnail|upload|batchUpdate)\s*\(")


@pytest.mark.parametrize("rel", ["youtube_read.py", "quota.py", "commands/fetch.py"])
def test_source_has_no_write_api_calls(rel):
    """TC-262: 조회 모듈 소스에 .update( .insert( .delete( 같은 쓰기 호출과 쓰기 토큰 로드, 웹 접근 코드가 없다. [SEC-001, SEC-007, FR-006]"""
    text = (SRC / rel).read_text(encoding="utf-8")
    assert WRITE_CALL.search(text) is None
    assert 'load_credentials("write"' not in text and "force-ssl" not in text and "WRITE_SCOPES" not in text
    assert "requests" not in text and "urllib" not in text and "selenium" not in text and "playwright" not in text


def test_fake_service_exposes_only_read_methods(project, clock):
    """TC-263: 가짜 서비스는 읽기 메서드만 가지므로, 리더가 쓰기 메서드를 부르면 테스트가 실패한다(그 보호 장치 자체를 확인). [SEC-001]"""
    api = Api()
    for resource in (api.videos(), api.channels(), api.playlistItems()):
        with pytest.raises(AttributeError):
            resource.update
        with pytest.raises(AttributeError):
            resource.insert
        with pytest.raises(AttributeError):
            resource.delete
    e = build(project, clock)
    e.reader.fetch_videos([vid(1), vid(2)])
    assert {k for k, _ in e.yt.calls} == {"videos.list"}


def test_build_services_uses_pinned_versions_without_discovery_cache(monkeypatch):
    """TC-264: build_services가 YouTube v3와 Analytics v2를 자격 증명과 함께, 디스커버리 캐시 없이 만든다. [FR-006, FR-007]"""
    import googleapiclient.discovery as disc

    calls = []
    monkeypatch.setattr(disc, "build", lambda *a, **kw: calls.append((a, kw)) or f"svc{len(calls)}")
    creds = object()
    assert yr.build_services(creds) == ("svc1", "svc2")
    assert calls == [(("youtube", "v3"), {"credentials": creds, "cache_discovery": False}), (("youtubeAnalytics", "v2"), {"credentials": creds, "cache_discovery": False})]


# ---------------------------------------------------------------- CLI 통합


def run_cli(project, argv, streams, clock, **kw):
    kw.setdefault("env", {})
    return cli.main(["--base-dir", str(project)] + argv, out=streams.out, err=streams.err, clock=clock, **kw)


def install_reader(monkeypatch, yt, an=None):
    built = []

    def fake_make_reader(ctx):
        quota = QuotaManager(ctx.conn, ctx.settings, ctx.clock)
        built.append(ctx.run_id)
        return YouTubeReader(yt, an or Api(), quota, ctx.conn, ctx.settings, ctx.clock, sleep=lambda s: None, run_id=ctx.run_id)

    monkeypatch.setattr(fetch_cmd, "make_reader", fake_make_reader)
    return built


def forbid_reader(monkeypatch):
    def boom(ctx):
        raise AssertionError("리더를 만들면 안 되는 경로입니다")

    monkeypatch.setattr(fetch_cmd, "make_reader", boom)


def open_db(project):
    return db.connect(project / "data" / "youtube_title.sqlite3")


def channel_api(n_videos=3, kids=()):
    yt = Api()
    yt.on("channels.list", lambda kw: {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "U"}}}]})
    yt.on("playlistItems.list", lambda kw: {"items": [{"contentDetails": {"videoId": vid(i)}} for i in range(n_videos)]})

    def videos(kw):
        items = []
        for i in kw["id"].split(","):
            it = video_item(i, f"제목 {i}")
            it["status"] = {"privacyStatus": ["public", "private", "unlisted"][int(i[-1]) % 3], "madeForKids": i in kids}
            items.append(it)
        return {"items": items}

    return yt.on("videos.list", videos)


def test_cli_no_option_is_input_error(project, streams, clock, monkeypatch):
    """TC-270: fetch에 옵션이 없으면 종료 코드 1과 안내(--all/--video/--metrics)를 내고 API 준비도 하지 않는다. [EVT-002, NFR-007]"""
    forbid_reader(monkeypatch)
    assert run_cli(project, ["fetch"], streams, clock) == 1
    err = streams.err.getvalue()
    assert "YT-500" in err and "--all" in err and "--video" in err and "--metrics" in err and "다음에 할 일" in err


@pytest.mark.parametrize("bad", ["short", "abc def ghi", "x" * 12, "abcdefghij!", "'; DROP TABLE videos;--", "한글영상아이디열한개"])
def test_cli_rejects_invalid_video_id(project, streams, clock, monkeypatch, bad):
    """TC-271: 잘못된 영상 ID는 종료 코드 1로 거부하고 로그인·API 준비 없이 끝난다(한 개라도 틀리면 전체 거부). [FR-006, SEC-011]"""
    forbid_reader(monkeypatch)
    assert run_cli(project, ["fetch", "--video", vid(1), "--video", bad], streams, clock) == 1
    assert "YT-500" in streams.err.getvalue() and "11" in streams.err.getvalue()


def test_cli_all_and_video_are_exclusive(project, streams, clock, monkeypatch):
    """TC-272: --all과 --video를 함께 쓰면 사용법 오류(종료 코드 2)이고 아무것도 조회하지 않는다. [EVT-002]"""
    forbid_reader(monkeypatch)
    assert run_cli(project, ["fetch", "--all", "--video", vid(1)], streams, clock) == 2


@pytest.mark.parametrize("days", ["0", "366", "-1", "abc", "2.5"])
def test_cli_days_range(project, streams, clock, monkeypatch, days):
    """TC-273: --days가 1~365 밖이거나 숫자가 아니면 사용법 오류(종료 코드 2)이다. [FR-007]"""
    forbid_reader(monkeypatch)
    assert run_cli(project, ["fetch", "--metrics", f"--days={days}"], streams, clock) == 2


def test_cli_invalid_phase(project, streams, clock, monkeypatch):
    """TC-274: --phase는 before/after/periodic만 받는다(그 밖의 값은 종료 코드 2). [FR-007]"""
    forbid_reader(monkeypatch)
    assert run_cli(project, ["fetch", "--metrics", "--phase", "weekly"], streams, clock) == 2


def test_cli_all_prints_scr007_summary(project, streams, clock, monkeypatch):
    """TC-275: fetch --all이 영상·공개 구분·아동용·쿼터 사용량·면책 문구를 출력하고 DB에 저장하며 실행 기록을 남긴다. [FR-006, SCR-007, FR-015, POL-002]"""
    yt = channel_api(3, kids={vid(0)})
    install_reader(monkeypatch, yt)
    assert run_cli(project, ["fetch", "--all"], streams, clock) == 0
    out = streams.out.getvalue()
    assert out.splitlines()[0] == "[fetch] 모드: 모의 실행(dry-run)"
    assert "영상 3개" in out and "쿼터 사용량" in out and "3 / 6000" in out and "남음 5997" in out
    assert re.search(r"공개\s+1\b", out) and re.search(r"비공개\s+1\b", out) and re.search(r"아동용\s+1\b", out)
    assert vid(0) in out and "제목 " + vid(1) in out
    assert out.rstrip().splitlines()[-1] == "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."
    conn = open_db(project)
    assert sorted(video_rows(conn)) == [vid(0), vid(1), vid(2)]
    assert conn.execute("SELECT SUM(units) FROM quota_usage").fetchone()[0] == 3
    run = conn.execute("SELECT command, mode, exit_code FROM run_logs").fetchone()
    assert tuple(run) == ("fetch", "dry_run", 0)
    assert "metrics" not in [k for k, _ in yt.calls]


def test_cli_video_option_repeated_fetches_only_those(project, streams, clock, monkeypatch):
    """TC-276: --video를 여러 번 주면 그 영상만 조회하고 채널 목록 API는 부르지 않는다. [FR-006]"""
    yt = channel_api()
    install_reader(monkeypatch, yt)
    assert run_cli(project, ["fetch", "--video", vid(7), "--video", vid(8)], streams, clock) == 0
    assert yt.count("channels.list") == 0 and yt.count("playlistItems.list") == 0
    assert yt.kwargs("videos.list")[0]["id"] == f"{vid(7)},{vid(8)}"
    assert "영상 2개" in streams.out.getvalue()


def test_cli_metrics_only_uses_stored_videos_and_period(project, streams, clock, monkeypatch):
    """TC-277: --metrics 단독은 저장된 영상만 대상으로 영상 API 없이 지표를 모으고, 기간(어제까지 N일)·단계가 요청에 반영된다. [FR-007, SCR-007]"""
    yt = channel_api()
    an = Api().on("reports.query", lambda kw: metrics_response([[i, 3, 1.5, 100, 2.5] for i in kw["filters"].removeprefix("video==").split(",")]))
    install_reader(monkeypatch, yt, an)
    assert run_cli(project, ["fetch", "--video", vid(1), "--video", vid(2)], streams, clock) == 0
    yt.calls.clear()
    streams.out.truncate(0), streams.out.seek(0)
    assert run_cli(project, ["fetch", "--metrics", "--phase", "before", "--days", "7"], streams, clock) == 0
    assert yt.calls == []
    q = an.kwargs("reports.query")[0]
    assert (q["startDate"], q["endDate"]) == ("2026-10-03", "2026-10-09") and q["filters"] == f"video=={vid(1)},{vid(2)}"
    out = streams.out.getvalue()
    assert "지표 수집" in out and "before" in out and "2026-10-03 ~ 2026-10-09" in out and "report --import-csv" not in out
    conn = open_db(project)
    assert [r[0] for r in conn.execute("SELECT phase FROM metrics_snapshots")] == ["before", "before"]


def test_cli_metrics_default_phase_and_days(project, streams, clock, monkeypatch):
    """TC-278: --all --metrics는 기본 단계 periodic, 기본 28일 기간으로 방금 조회한 영상의 지표를 모은다. [FR-007]"""
    yt = channel_api(2)
    an = Api().on("reports.query", lambda kw: metrics_response([]))
    install_reader(monkeypatch, yt, an)
    assert run_cli(project, ["fetch", "--all", "--metrics"], streams, clock) == 0
    q = an.kwargs("reports.query")[0]
    assert (q["startDate"], q["endDate"]) == ("2026-09-12", "2026-10-09")
    assert "periodic" in streams.out.getvalue() and "지표가 없는 영상: 2개" in streams.out.getvalue()


def test_cli_metrics_without_stored_videos_is_error(project, streams, clock, monkeypatch):
    """TC-279: 저장된 영상이 없을 때 --metrics 단독은 종료 코드 1과 `fetch --all` 안내이며 API를 부르지 않는다. [FR-007, NFR-007]"""
    an = Api()
    install_reader(monkeypatch, channel_api(), an)
    assert run_cli(project, ["fetch", "--metrics"], streams, clock) == 1
    assert "fetch --all" in streams.err.getvalue() and an.calls == []


def test_cli_metrics_fallback_guides_csv_import(project, streams, clock, monkeypatch):
    """TC-280: 노출수·CTR 지표가 거부돼 폴백되면 종료 코드 0으로 끝나되 Studio CSV 가져오기(report --import-csv)를 안내한다. [FR-007, SCR-007]"""
    def handler(kw):
        if "videoThumbnailImpressions" in kw["metrics"]:
            return http_error(400, "badRequest")
        return metrics_response([[vid(1), 4, 2.0]], names=("video", "views", "estimatedMinutesWatched"))

    install_reader(monkeypatch, channel_api(), Api().on("reports.query", handler))
    assert run_cli(project, ["fetch", "--video", vid(1), "--metrics"], streams, clock) == 0
    out = streams.out.getvalue()
    assert "report --import-csv" in out and "Studio" in out
    assert "2 / 6000" not in out and "3 / 6000" in out  # videos.list 1 + 실패한 지표 1 + 폴백 지표 1


def test_cli_sanitizes_control_characters_in_titles(project, streams, clock, monkeypatch):
    """TC-281: 제목의 ANSI 이스케이프·줄바꿈은 화면에 그대로 나오지 않는다(DB에는 값 그대로 저장). [SEC-019]"""
    evil = "\x1b[31m빨강\x1b[0m\r\n가짜 줄\x1b]0;창제목\x07"
    yt = Api().on("videos.list", lambda kw: {"items": [video_item(vid(1), evil)]})
    install_reader(monkeypatch, yt)
    assert run_cli(project, ["fetch", "--video", vid(1)], streams, clock) == 0
    out = streams.out.getvalue()
    assert "\x1b" not in out and "\x07" not in out and "빨강" in out
    assert video_rows(open_db(project))[vid(1)]["title"] == evil


def test_cli_plain_mode_lists_items(project, streams, clock, monkeypatch):
    """TC-282: --plain이면 표 대신 `항목: 값` 목록으로 영상을 출력한다. [SCR-007, NFR-007]"""
    install_reader(monkeypatch, channel_api(1))
    assert run_cli(project, ["fetch", "--all", "--plain"], streams, clock) == 0
    assert "영상 ID: " + vid(0) in streams.out.getvalue()


def test_cli_quota_exhausted_stops_with_reset_guidance(project, streams, clock, monkeypatch):
    """TC-283: 쿼터 상한에 닿으면 종료 코드 1과 초기화 시각 안내를 내고, 그 뒤 API는 부르지 않는다. [SEC-002, FR-015, NFR-003]"""
    (project / "config" / "settings.yaml").write_text("quota:\n  daily_limit_units: 1\n", encoding="utf-8")
    yt = channel_api()
    install_reader(monkeypatch, yt)
    assert run_cli(project, ["fetch", "--all"], streams, clock) == 1
    err = streams.err.getvalue()
    assert "YT-300" in err and "태평양" in err and "상한 1" in err
    assert yt.count("channels.list") == 1 and yt.count("playlistItems.list") == 0 and yt.count("videos.list") == 0
    assert open_db(project).execute("SELECT units, status FROM quota_usage").fetchall()[0][:] == (1, "ok")


def test_cli_warns_at_80_percent(project, streams, clock, monkeypatch):
    """TC-284: 오늘 사용량이 상한의 80%를 넘으면 출력에 쿼터 경고가 붙는다. [NFR-003, SEC-002]"""
    (project / "config" / "settings.yaml").write_text("quota:\n  daily_limit_units: 3\n", encoding="utf-8")
    install_reader(monkeypatch, channel_api())
    assert run_cli(project, ["fetch", "--all"], streams, clock) == 0
    out = streams.out.getvalue()
    assert "3 / 3 units" in out and "[주의]" in out and "80%" in out


def test_cli_no_warning_below_threshold(project, streams, clock, monkeypatch):
    """TC-285: 사용량이 80% 미만이면 쿼터 경고 줄이 없다. [NFR-003]"""
    install_reader(monkeypatch, channel_api())
    assert run_cli(project, ["fetch", "--all"], streams, clock) == 0
    assert "80%" not in streams.out.getvalue()


def test_make_reader_loads_read_token_only(project, streams, clock, monkeypatch):
    """TC-286: 실제 make_reader는 읽기 토큰만 불러 서비스를 만들고 쓰기 토큰은 요청하지 않는다. [SEC-015, SEC-001, FR-016]"""
    kinds, built = [], []
    monkeypatch.setattr(fetch_cmd.authmod, "load_credentials", lambda kind, settings: kinds.append(kind) or "CREDS")
    yt = channel_api()
    monkeypatch.setattr(fetch_cmd, "build_services", lambda creds: built.append(creds) or (yt, Api()))
    assert run_cli(project, ["fetch", "--video", vid(1)], streams, clock) == 0
    assert kinds == ["read"] and built == ["CREDS"]


def test_make_reader_without_login_guides_auth(project, streams, clock, tmp_path):
    """TC-287: 읽기 로그인이 없으면 종료 코드 1과 `auth --read` 안내이며 DB에 영상이 생기지 않는다. [FR-016, NFR-007]"""
    code = run_cli(project, ["fetch", "--all"], streams, clock, env={"YT_TOKEN_DIR": str(tmp_path / "no_tokens")})
    assert code == 1 and "YT-400" in streams.err.getvalue() and "auth --read" in streams.err.getvalue()
    assert video_rows(open_db(project)) == {}


def test_fetch_is_listed_in_help_with_options(project, streams, clock):
    """TC-288: --help에 fetch 명령이 자동 탐색돼 나타나고 fetch --help에 옵션 설명이 있다. [EVT-002, ADR-003]"""
    assert run_cli(project, ["--help"], streams, clock) == 0
    assert "fetch" in streams.out.getvalue()
    streams.out.truncate(0), streams.out.seek(0)
    assert run_cli(project, ["fetch", "--help"], streams, clock) == 0
    out = streams.out.getvalue()
    assert all(opt in out for opt in ("--all", "--video", "--metrics", "--phase", "--days")) and "읽기 권한" in out


def test_cli_long_list_is_truncated_and_warnings_shown(project, streams, clock, monkeypatch):
    """TC-289: 영상이 20개를 넘으면 앞 20개만 표로 보이고 나머지 개수를 알리며, 건너뛴 항목·응답에 없던 영상 수를 경고한다. [SCR-007, FR-006]"""
    ids = [vid(i) for i in range(25)]
    bad = video_item(vid(90))
    del bad["snippet"]["title"]
    yt = Api().on("videos.list", lambda kw: {"items": [video_item(i) for i in kw["id"].split(",")[:-1]] + [bad]})
    install_reader(monkeypatch, yt)
    assert run_cli(project, ["fetch"] + [a for i in ids for a in ("--video", i)], streams, clock) == 0
    out = streams.out.getvalue()
    assert "영상 24개" in out and "외 4개" in out and vid(19) in out and vid(20) not in out
    assert "건너뛴 항목: 1개" in out and "응답에 없던 영상: 1개" in out


def test_cli_metrics_skipped_rows_reported(project, streams, clock, monkeypatch):
    """TC-290: 지표 응답에서 건너뛴 항목이 있으면 개수를 경고로 알린다. [FR-007, SCR-007]"""
    an = Api().on("reports.query", lambda kw: metrics_response([[vid(1), 1, 1.0, 1, 1.0], [vid(1), 2]]))
    install_reader(monkeypatch, channel_api(), an)
    assert run_cli(project, ["fetch", "--video", vid(1), "--metrics"], streams, clock) == 0
    assert "건너뛴 지표 항목: 1개" in streams.out.getvalue()
