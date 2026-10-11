"""가짜 구글(독립 검증 M2·M3). urllib.request.urlopen 을 대체한다 — 실제 네트워크 호출은 어떤 경로로도 나가지 않는다.
토큰 발급(PKCE·redirect·client_secret 검증), 읽기 API, 쓰기 API(PUT videos)를 흉내 내며 모든 호출을 기록한다."""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import urllib.error
import urllib.parse
from dataclasses import dataclass, field

SCOPE_READ = "https://www.googleapis.com/auth/youtube.readonly"
SCOPE_WRITE = "https://www.googleapis.com/auth/youtube.force-ssl"


class RealNetworkAttempt(AssertionError):
    pass


@dataclass
class Call:
    method: str
    url: str
    path: str
    query: dict
    auth: str | None
    body: object


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@dataclass
class FakeGoogle:
    client_id: str = "cid-123"
    client_secret: str = "csec-456"
    videos: dict = field(default_factory=dict)          # video_id -> snippet
    calls: list = field(default_factory=list)
    codes: dict = field(default_factory=dict)           # code -> (challenge, scope, redirect, client_id)
    access: dict = field(default_factory=dict)          # access token -> scope
    refresh: dict = field(default_factory=dict)         # refresh token -> scope
    seq: int = 0
    update_mode: str = "ok"      # ok | wrong_title | http_4xx:<code> | http_5xx_applied | http_5xx_not_applied | timeout_applied | timeout_not_applied | empty_json
    token_error: str | None = None
    omit_refresh: bool = False
    pages: list | None = None    # playlistItems 페이지: [[ids...], ...]
    uploads: str | None = "UUuploads"
    quota_on_read: bool = False
    expires_in: int = 3600

    # ---- 보조
    def consent(self, auth_url: str) -> str:
        """사용자가 구글 화면에서 허용했다고 가정하고 인가 코드를 만든다."""
        q = {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query).items()}
        assert q["client_id"] == self.client_id and q["response_type"] == "code" and q["code_challenge_method"] == "S256"
        self.seq += 1
        code = f"CODE-{self.seq}"
        self.codes[code] = (q["code_challenge"], q["scope"], q["redirect_uri"], q["client_id"])
        return code

    def put_calls(self):
        return [c for c in self.calls if c.method == "PUT"]

    def video_calls(self):
        return [c for c in self.calls if c.path.endswith("/videos")]

    def touched_ids(self) -> set[str]:
        ids: set[str] = set()
        for c in self.calls:
            if c.method == "PUT" and isinstance(c.body, dict):
                ids.add(c.body.get("id"))
            elif c.path.endswith("/videos") and "id" in c.query:
                ids.update(c.query["id"].split(","))
        return ids

    # ---- urlopen 대체
    def urlopen(self, req, timeout=None, **kw):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        method = req.get_method() if hasattr(req, "get_method") else "GET"
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in ("oauth2.googleapis.com", "www.googleapis.com"):
            raise RealNetworkAttempt(f"허용되지 않은 호출: {method} {url}")
        hdrs = {k.lower(): v for k, v in (req.headers if hasattr(req, "headers") else {}).items()}
        data = getattr(req, "data", None)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if parsed.hostname == "oauth2.googleapis.com":
            form = {k: v[0] for k, v in urllib.parse.parse_qs((data or b"").decode()).items()}
            self.calls.append(Call(method, url, parsed.path, query, hdrs.get("authorization"), form))
            return self._token(form, url)
        body = json.loads(data.decode("utf-8")) if data else None
        self.calls.append(Call(method, url, parsed.path, query, hdrs.get("authorization"), body))
        return self._api(method, parsed.path, query, hdrs.get("authorization"), body, url)

    # ---- 토큰 엔드포인트
    def _http_error(self, url, code, payload):
        return urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(json.dumps(payload).encode()))

    def _json(self, obj):
        return _Resp(json.dumps(obj).encode("utf-8"))

    def _token(self, f, url):
        if self.token_error:
            raise self._http_error(url, 400, {"error": self.token_error})
        if f.get("client_id") != self.client_id or f.get("client_secret") != self.client_secret:
            raise self._http_error(url, 401, {"error": "invalid_client"})
        self.seq += 1
        if f.get("grant_type") == "authorization_code":
            info = self.codes.pop(f.get("code", ""), None)   # 코드는 1회용
            if info is None:
                raise self._http_error(url, 400, {"error": "invalid_grant"})
            challenge, scope, redirect, _cid = info
            ver = base64.urlsafe_b64encode(hashlib.sha256(f.get("code_verifier", "").encode()).digest()).rstrip(b"=").decode()
            if ver != challenge or f.get("redirect_uri") != redirect:
                raise self._http_error(url, 400, {"error": "invalid_grant"})
            tag = "WRITE" if scope == SCOPE_WRITE else "READ"
            at, rt = f"AT-{tag}-SECRET-{self.seq}", f"RT-{tag}-SECRET-{self.seq}"
            self.access[at] = scope
            self.refresh[rt] = scope
            out = {"access_token": at, "expires_in": self.expires_in, "scope": scope, "token_type": "Bearer"}
            if not self.omit_refresh:
                out["refresh_token"] = rt
            return self._json(out)
        if f.get("grant_type") == "refresh_token":
            scope = self.refresh.get(f.get("refresh_token", ""))
            if scope is None:
                raise self._http_error(url, 400, {"error": "invalid_grant"})
            tag = "WRITE" if scope == SCOPE_WRITE else "READ"
            at = f"AT-{tag}-REFRESHED-{self.seq}"
            self.access[at] = scope
            return self._json({"access_token": at, "expires_in": self.expires_in, "scope": scope})
        raise self._http_error(url, 400, {"error": "unsupported_grant_type"})

    # ---- 유튜브 API
    def _api(self, method, path, q, auth, body, url):
        tok = (auth or "").removeprefix("Bearer ")
        scope = self.access.get(tok)
        if scope is None:
            raise self._http_error(url, 401, {"error": {"errors": [{"reason": "authError"}]}})
        if method == "GET":
            if self.quota_on_read:
                raise self._http_error(url, 403, {"error": {"errors": [{"reason": "quotaExceeded"}]}})
            if path.endswith("/channels"):
                if not self.uploads:
                    return self._json({"items": []})
                return self._json({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": self.uploads}}}]})
            if path.endswith("/playlistItems"):
                pages = self.pages if self.pages is not None else [list(self.videos)]
                idx = int(q["pageToken"].removeprefix("P")) if q.get("pageToken") else 0
                out = {"items": [{"contentDetails": {"videoId": v}} for v in pages[idx]]}
                if idx + 1 < len(pages):
                    out["nextPageToken"] = f"P{idx + 1}"
                return self._json(out)
            if path.endswith("/videos"):
                ids = q.get("id", "").split(",")
                items = [{"id": i, "snippet": copy.deepcopy(self.videos[i]), "contentDetails": {"duration": "PT10M"}, "status": {"privacyStatus": "public"}, "statistics": {"viewCount": "5"}}
                         for i in ids if i in self.videos]
                return self._json({"items": items})
        if method == "PUT" and path.endswith("/videos"):
            if scope != SCOPE_WRITE:
                raise self._http_error(url, 403, {"error": {"errors": [{"reason": "insufficientPermissions"}]}})
            vid, sn = body["id"], body["snippet"]
            m = self.update_mode
            if m.startswith("http_4xx:"):
                raise self._http_error(url, int(m.split(":")[1]), {"error": {"errors": [{"reason": "forbidden"}]}})
            if m == "http_5xx_applied":
                self.videos[vid] = copy.deepcopy(sn)
                raise self._http_error(url, 503, {})
            if m == "http_5xx_not_applied":
                raise self._http_error(url, 500, {})
            if m == "timeout_applied":
                self.videos[vid] = copy.deepcopy(sn)
                raise TimeoutError("read timed out")
            if m == "timeout_not_applied":
                raise TimeoutError("read timed out")
            if m == "wrong_title":
                self.videos[vid] = copy.deepcopy(sn)
                return self._json({"snippet": {**sn, "title": sn["title"] + "?"}})
            if m == "empty_json":
                self.videos[vid] = copy.deepcopy(sn)
                return self._json({})
            self.videos[vid] = copy.deepcopy(sn)
            return self._json({"id": vid, "snippet": copy.deepcopy(sn)})
        raise self._http_error(url, 404, {})
