"""TC-VM-200~: youtube/live_read.py (M2 단위 3) 독립 검증 — 읽기 전용, 쪽 나누기, 오류 번역, 토큰 갱신."""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

from ytweb.youtube import google_oauth as oauth
from ytweb.youtube import live_read as lr
from ytweb.youtube.base import GatewayError
from tests.verify_m23.fakegoogle import FakeGoogle, SCOPE_READ

HANGUL = re.compile("[가-힣]")
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def vid(n):
    return f"vid{n:08d}"


def item(n, title="제목", **over):
    base = {"id": vid(n), "snippet": {"title": title, "categoryId": "26", "description": " 설명   내용 "},
            "contentDetails": {"duration": "PT10M5S"}, "status": {"privacyStatus": "public", "madeForKids": False}, "statistics": {"viewCount": "12"}}
    base.update(over)
    return base


# ---------- parse_duration 경계 ----------
@pytest.mark.parametrize("v,exp", [
    ("PT0S", 0), ("PT1S", 1), ("PT59S", 59), ("PT1M", 60), ("PT3M", 180), ("PT3M1S", 181), ("PT1H", 3600), ("PT1H1M1S", 3661),
    ("P1D", 86400), ("P1DT1H", 90000), ("PT90M", 5400), ("PT100H", 360000),
    ("P", None), ("PT", None), ("", None), ("pt1m", None), ("PT-5S", None), ("PT1.5S", None), ("P1W", None), ("P1Y", None), ("1M", None),
    (None, None), (123, None), ([], None)
])
def test_tc_vm_200_parse_duration(v, exp):
    assert lr.parse_duration(v) == exp


@pytest.mark.xfail(reason="DEF-VM-004(Info): 끝에 개행이 붙은 값('PT1M\\n')도 60으로 해석됨. 구글은 개행을 보내지 않아 사용자 영향 없음, 수용 후보", strict=True)
def test_tc_vm_200b_parse_duration_trailing_newline_is_rejected():
    assert lr.parse_duration("PT1M\n") is None


# ---------- to_video_fields ----------
@pytest.mark.parametrize("it", [
    {}, {"id": "short", "snippet": {"title": "t"}}, {"id": "x" * 12, "snippet": {"title": "t"}}, {"id": 5, "snippet": {"title": "t"}},
    {"id": "abcdefghijk"}, {"id": "abcdefghijk", "snippet": "str"}, {"id": "abcdefghijk", "snippet": {"title": 5}}, {"id": "abcdefghijk", "snippet": {}},
])
def test_tc_vm_201_malformed_items_are_rejected(it):
    assert lr.to_video_fields(it) is None


def test_tc_vm_202_to_video_fields_maps_everything():
    f = lr.to_video_fields(item(1, privacy="x") | {"status": {"privacyStatus": "private", "madeForKids": True}})
    assert f["video_id"] == vid(1) and f["privacy_status"] == "private" and f["made_for_kids"] is True and f["source"] == "youtube"
    assert f["duration_sec"] == 605 and f["views"] == 12 and f["category_id"] == "26" and f["description_excerpt"] == "설명 내용"
    f2 = lr.to_video_fields({"id": vid(2), "snippet": {"title": "t"}})
    assert f2["views"] is None and f2["duration_sec"] is None and f2["privacy_status"] is None


@pytest.mark.parametrize("vc,exp", [("0", 0), ("abc", None), (None, None), ("", None), (7, 7)])
def test_tc_vm_203_view_count_parsing(vc, exp):
    it = item(3)
    it["statistics"] = {"viewCount": vc}
    assert lr.to_video_fields(it)["views"] == exp


# ---------- Reader (주입 http_get) ----------
class Fake:
    def __init__(self, pages=None, items=None, uploads="UU1"):
        self.pages, self.items, self.uploads, self.urls, self.tokens = pages or [[]], items or {}, uploads, [], []

    def __call__(self, url, token):
        self.urls.append(url)
        self.tokens.append(token)
        p = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(p.query).items()}
        if p.path.endswith("/channels"):
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": self.uploads}}}]} if self.uploads else {"items": []}
        if p.path.endswith("/playlistItems"):
            i = int(q.get("pageToken", "P0")[1:]) if q.get("pageToken") else 0
            out = {"items": [{"contentDetails": {"videoId": v}} for v in self.pages[i]]}
            if i + 1 < len(self.pages):
                out["nextPageToken"] = f"P{i + 1}"
            return out
        ids = q["id"].split(",")
        return {"items": [self.items[i] for i in ids if i in self.items]}


def test_tc_vm_210_only_get_calls_to_three_endpoints_with_bearer_and_no_write():
    f = Fake(pages=[[vid(1), vid(2)]], items={vid(1): item(1), vid(2): item(2)})
    rows = lr.YouTubeReader(lambda: "TOK", f).fetch_all()
    assert [r["video_id"] for r in rows] == [vid(1), vid(2)] and set(f.tokens) == {"TOK"}
    assert all(u.startswith("https://www.googleapis.com/youtube/v3/") for u in f.urls)
    assert {urllib.parse.urlparse(u).path.split("/")[-1] for u in f.urls} == {"channels", "playlistItems", "videos"}
    src = open(lr.__file__, encoding="utf-8").read()
    assert not hasattr(lr, "default_http_send") and 'method="PUT"' not in src and "method=" not in src and "data=" not in src   # 읽기 모듈에 쓰기 요청 코드 없음


def test_tc_vm_211_pagination_and_dedupe_preserve_order():
    f = Fake(pages=[[vid(1), vid(2)], [vid(2), vid(3)], [vid(4)]], items={vid(i): item(i) for i in range(1, 5)})
    assert [r["video_id"] for r in lr.YouTubeReader(lambda: "T", f).fetch_all()] == [vid(i) for i in (1, 2, 3, 4)]


@pytest.mark.parametrize("n,chunks", [(0, 0), (1, 1), (50, 1), (51, 2), (100, 2), (101, 3)])
def test_tc_vm_212_videos_requested_in_chunks_of_50(n, chunks):
    ids = [vid(i) for i in range(n)]
    f = Fake(pages=[ids] if ids else [[]], items={i: item(int(i[3:])) for i in ids})
    rows = lr.YouTubeReader(lambda: "T", f).fetch_all()
    assert len(rows) == n
    vcalls = [u for u in f.urls if urllib.parse.urlparse(u).path.endswith("/videos")]
    assert len(vcalls) == chunks
    for u in vcalls:
        assert len(urllib.parse.parse_qs(urllib.parse.urlparse(u).query)["id"][0].split(",")) <= 50


def test_tc_vm_213_page_cap_40_stops_without_infinite_loop():
    class Inf(Fake):
        def __call__(self, url, token):
            if urllib.parse.urlparse(url).path.endswith("/playlistItems"):
                self.urls.append(url)
                return {"items": [{"contentDetails": {"videoId": vid(len(self.urls))}}], "nextPageToken": "N"}
            return super().__call__(url, token)
    f = Inf(items={})
    list(lr.YouTubeReader(lambda: "T", f).video_ids("UU1"))
    assert len([u for u in f.urls if "playlistItems" in u]) == lr.MAX_PAGES == 40


def test_tc_vm_214_no_channel_is_gateway_error_with_korean_message():
    with pytest.raises(GatewayError) as e:
        lr.YouTubeReader(lambda: "T", Fake(uploads=None)).fetch_all()
    assert e.value.code == "no_channel" and HANGUL.search(e.value.message) and e.value.definite


def test_tc_vm_215_bad_items_skipped_good_kept():
    f = Fake(pages=[[vid(1), vid(2), "bogus"]], items={vid(1): item(1), vid(2): {"id": vid(2), "snippet": {"title": 5}}})
    assert [r["video_id"] for r in lr.YouTubeReader(lambda: "T", f).fetch_all()] == [vid(1)]


def test_tc_vm_216_non_string_video_ids_in_playlist_ignored():
    class W(Fake):
        def __call__(self, url, token):
            if "playlistItems" in url:
                return {"items": [{"contentDetails": {"videoId": 5}}, {}, {"contentDetails": None}, {"contentDetails": {"videoId": vid(1)}}]}
            return super().__call__(url, token)
    f = W(items={vid(1): item(1)})
    assert len(lr.YouTubeReader(lambda: "T", f).fetch_all()) == 1


def test_tc_vm_217_videos_list_request_carries_maxResults_together_with_id_OBSERVATION():
    """관찰(Low, 미검증): YouTube Data API 문서는 videos.list 에서 maxResults 를 id 와 함께 쓰지 않는다고 적는다.
    공식 문서·실서버에 접속할 수 없어 동작은 미확인. 요청에 두 파라미터가 함께 나가는 사실만 기록한다."""
    f = Fake(pages=[[vid(1)]], items={vid(1): item(1)})
    lr.YouTubeReader(lambda: "T", f).fetch_all()
    u = next(x for x in f.urls if urllib.parse.urlparse(x).path.endswith("/videos"))
    q = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
    assert "id" in q and "maxResults" in q


# ---------- default_http_get 오류 번역 ----------
def _get(fg, code_mode=None):
    return lr.default_http_get


def test_tc_vm_220_default_get_refuses_non_https_without_call(fg):
    with pytest.raises(GatewayError) as e:
        lr.default_http_get("http://www.googleapis.com/youtube/v3/videos", "T")
    assert e.value.code == "insecure_url" and fg.calls == []


def test_tc_vm_221_default_get_unauthorized_token_maps_to_korean_unauthorized(fg):
    with pytest.raises(GatewayError) as e:
        lr.default_http_get(lr.API + "/channels?part=x", "bad-token")
    assert e.value.code == "unauthorized" and HANGUL.search(e.value.message) and "bad-token" not in e.value.message


def test_tc_vm_222_default_get_quota_vs_forbidden_vs_5xx_vs_network(fg, monkeypatch):
    import io
    import urllib.error
    import urllib.request

    def raiser(code, reason=None):
        def f(req, timeout=None):
            body = json.dumps({"error": {"errors": [{"reason": reason}]}}).encode() if reason else b"<html>"
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, io.BytesIO(body))
        return f

    cases = [(403, "quotaExceeded", "quota_exceeded"), (403, "dailyLimitExceeded", "quota_exceeded"), (403, "rateLimitExceeded", "quota_exceeded"),
             (403, "forbidden", "forbidden"), (403, None, "forbidden"), (500, None, "http_500"), (503, "backendError", "http_503"), (404, None, "http_404")]
    for code, reason, exp in cases:
        monkeypatch.setattr(urllib.request, "urlopen", raiser(code, reason))
        with pytest.raises(GatewayError) as e:
            lr.default_http_get(lr.API + "/videos?id=x", "SECRET-T")
        assert e.value.code == exp and HANGUL.search(e.value.message) and "SECRET-T" not in e.value.message, (code, reason)

    def net(req, timeout=None):
        raise OSError("dns fail for www.googleapis.com token=SECRET-T")
    monkeypatch.setattr(urllib.request, "urlopen", net)
    with pytest.raises(GatewayError) as e:
        lr.default_http_get(lr.API + "/videos?id=x", "SECRET-T")
    assert e.value.code == "network" and "SECRET-T" not in e.value.message and "dns" not in e.value.message and e.value.__cause__ is None


def test_tc_vm_223_default_get_non_json_success_body_is_network_error_not_crash(monkeypatch):
    import urllib.request
    from tests.verify_m23.fakegoogle import _Resp
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: _Resp(b"<html>captive portal</html>"))
    with pytest.raises(GatewayError) as e:
        lr.default_http_get(lr.API + "/videos?id=x", "T")
    assert e.value.code == "network"


# ---------- GoogleAccess ----------
def _access(tmp_path, tokens=None, client=True, http=None):
    cf = tmp_path / "c.json"
    if client:
        cf.write_text(json.dumps({"installed": {"client_id": "cid-123", "client_secret": "csec-456"}}))
    st = oauth.TokenStore(tmp_path / "t.json")
    if tokens:
        st.save(tokens)
    return lr.GoogleAccess(cf, st, http or oauth.default_http_post), st


def _fresh(**kw):
    return {"access_token": "A-FRESH", "refresh_token": "R", "expires_at": (NOW + timedelta(hours=1)).isoformat(), **kw}


def test_tc_vm_230_not_connected_error_and_connected_flag(tmp_path):
    a, st = _access(tmp_path)
    assert a.connected() is False
    with pytest.raises(GatewayError) as e:
        a.access_token(NOW)
    assert e.value.code == "not_connected" and HANGUL.search(e.value.message)
    a2, _ = _access(tmp_path / "x" if False else tmp_path, tokens=_fresh(), client=False)
    (tmp_path / "c.json").unlink(missing_ok=True)
    assert a2.connected() is False                      # 클라이언트 파일이 없으면 연결로 보지 않는다


def test_tc_vm_231_fresh_token_returned_without_network(tmp_path, fg):
    a, _ = _access(tmp_path, tokens=_fresh())
    assert a.access_token(NOW) == "A-FRESH" and fg.calls == []


def test_tc_vm_232_stale_token_refreshed_saved_and_refresh_token_kept(tmp_path, fg):
    fg.refresh["R-OLD"] = SCOPE_READ
    stale = {"access_token": "OLD", "refresh_token": "R-OLD", "expires_at": (NOW - timedelta(hours=1)).isoformat()}
    a, st = _access(tmp_path, tokens=stale)
    tok = a.access_token(NOW)
    assert tok.startswith("AT-READ-REFRESHED") and st.load()["access_token"] == tok and st.load()["refresh_token"] == "R-OLD"
    assert len([c for c in fg.calls if c.path == "/token"]) == 1
    assert a.access_token(NOW) == tok and len([c for c in fg.calls if c.path == "/token"]) == 1   # 두 번째는 갱신 안 함


def test_tc_vm_233_refresh_rejected_becomes_unauthorized_and_does_not_leak(tmp_path, fg):
    stale = {"access_token": "OLD", "refresh_token": "R-REVOKED-SECRET", "expires_at": (NOW - timedelta(hours=1)).isoformat()}
    a, st = _access(tmp_path, tokens=stale)
    with pytest.raises(GatewayError) as e:
        a.access_token(NOW)
    assert e.value.code == "unauthorized" and HANGUL.search(e.value.message) and "R-REVOKED-SECRET" not in e.value.message
    assert st.load()["access_token"] == "OLD"            # 실패 시 기존 파일을 망가뜨리지 않음


def test_tc_vm_234_missing_client_file_on_refresh_is_unauthorized_not_crash(tmp_path, fg):
    stale = {"access_token": "OLD", "refresh_token": "R", "expires_at": (NOW - timedelta(hours=1)).isoformat()}
    a, _ = _access(tmp_path, tokens=stale, client=False)
    with pytest.raises(GatewayError) as e:
        a.access_token(NOW)
    assert e.value.code == "unauthorized" and fg.calls == []
