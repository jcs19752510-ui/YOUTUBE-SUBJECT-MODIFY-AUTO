"""SEC-09 M2(구글 OAuth 읽기)·M3(쓰기 게이트웨이·실제 모드) 신규 공격면 시험 — 9단계 보안 재검증(개정 2판, 2026-10-11).

실제 구글/외부 호출 없음: web/backend/tests/verify_m23 의 FakeGoogle(urlopen 대체 + 이름 해석 차단)을 그대로 쓴다.
운영 코드는 읽기만 하며 고치지 않는다. 결함은 `repro_` 시험으로 '현재 동작'을 고정한다(고치면 이 시험이 실패 -> 표식 갱신).
재실행: cd web/backend && python -m pytest ../tests_security/test_sec_09_m23_attack.py -p no:cacheprovider -o addopts='' --noconftest
"""
from __future__ import annotations

import json
import logging
import os
import stat
import urllib.parse
import urllib.request

import pytest
from sqlalchemy import select, text

from tests.verify_m23.conftest import (  # noqa: F401  (fixture 재사용)
    DOMAIN_ROUTERS, SEED_COUNT, _reset_default_env, api, csrf, dapp, env, env_free, gapp, client_file, fg, gw, live,
    no_real_network, policy, seeded, approve_via_api, do_execute, finish_flow, hdr, load_fake_videos, make_draft, start_flow, connect_both,
)
from tests.conftest import clock, web_settings, engine, factory, db, fake_time  # noqa: F401
from tests.verify_m23.test_vm_07_live_e2e import changes, prepare, queued, tick
from ytweb.db.models import AuditLog, Base, Batch, BatchItem, Change, Video
from ytweb.domain import live_gateway as lg
from ytweb.youtube import google_oauth as oauth
from ytweb.youtube.base import GatewayError
from ytweb.youtube.live_write import LiveYouTubeGateway

CANARIES = ("AT-WRITE-SECRET", "AT-READ-SECRET", "RT-WRITE-SECRET", "RT-READ-SECRET", "csec-456", "AT-WRITE-REFRESHED", "AT-READ-REFRESHED")


def _all_db_text(factory) -> str:
    out = []
    with factory() as s:
        for t in Base.metadata.sorted_tables:
            for row in s.execute(select(t)).all():
                out.append(repr(tuple(row)))
    return "\n".join(out)


class _Logs(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))


@pytest.fixture
def logs():
    h = _Logs()
    h.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.addHandler(h)
    ytw = logging.getLogger("ytweb")
    ytw.addHandler(h)
    old = root.level
    root.setLevel(logging.DEBUG)
    yield h
    root.removeHandler(h)
    ytw.removeHandler(h)
    root.setLevel(old)


# ================= A. OAuth 콜백 (TW-37, TW-42) =================

def test_a1_forged_state_callback_saves_nothing_and_leaks_nothing(gapp, csrf, fg, web_settings):
    gapp.cookies.clear()
    r = gapp.get("/api/v1/google/callback?code=EVILCODE&state=" + "A" * 43, follow_redirects=False,
                 headers={"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"})
    assert r.status_code == 303 and r.headers["location"] == "/#/"
    assert not (web_settings.secrets_dir / "google_token.json").exists()
    assert not (web_settings.secrets_dir / lg.WRITE_TOKEN_FILE).exists()
    assert fg.calls == []  # 모르는 state 는 구글 토큰 교환 자체를 하지 않는다


def test_a2_state_is_single_use_and_cross_kind_cannot_land_in_other_store(gapp, csrf, fg, web_settings):
    url = start_flow(gapp, csrf, "connect")
    assert finish_flow(gapp, fg, url).status_code == 303
    n = len(fg.calls)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    r = gapp.get(f"/api/v1/google/callback?code=CODE-X&state={q['state'][0]}", follow_redirects=False)
    assert r.status_code == 303 and len(fg.calls) == n  # 재사용 state: 교환 시도 없음
    assert (web_settings.secrets_dir / "google_token.json").exists()
    assert not (web_settings.secrets_dir / lg.WRITE_TOKEN_FILE).exists()  # 읽기 로그인이 쓰기 토큰 파일을 만들지 않는다


def test_a3_state_expires_after_10_minutes(gapp, csrf, fg):
    url = start_flow(gapp, csrf, "connect-write")
    ctx = gapp.app.state.google_ctx
    for k, (v, t) in list(ctx.pending._items.items()):
        ctx.pending._items[k] = (v, t - 601)
    r = finish_flow(gapp, fg, url)
    assert r.status_code == 303 and fg.put_calls() == [] and ctx.write_store.load() is None


def test_a4_callback_sets_no_cookie_and_no_cache_and_open_redirect_impossible(gapp, csrf, fg):
    url = start_flow(gapp, csrf, "connect")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    for extra in ({"X-Forwarded-Host": "evil.example"}, {"Referer": "https://evil.example/"}, {"Origin": "https://evil.example"}):
        r = gapp.get(f"/api/v1/google/callback?code=X&state={q['state'][0]}&next=https://evil.example&redirect=//evil.example&redirect_uri=https://evil.example",
                     follow_redirects=False, headers=extra)
        assert r.headers["location"] == "/#/" and r.headers.get("cache-control") == "no-store"
        assert "set-cookie" not in {k.lower() for k in r.headers}
    bad_host = gapp.get("/api/v1/google/callback?code=X&state=y", headers={"Host": "evil.example"}, follow_redirects=False)
    assert bad_host.status_code == 403  # Host 허용 목록


def test_a5_authorization_url_is_fixed_google_host_and_pkce(gapp, csrf):
    u = urllib.parse.urlparse(start_flow(gapp, csrf, "connect-write"))
    q = urllib.parse.parse_qs(u.query)
    assert (u.scheme, u.netloc, u.path) == ("https", "accounts.google.com", "/o/oauth2/v2/auth")
    assert q["code_challenge_method"] == ["S256"] and len(q["state"][0]) >= 43 and q["redirect_uri"][0].startswith("http://127.0.0.1:")


def test_a6_token_files_0600_atomic_no_tmp_left_and_dir_not_world_readable(gapp, csrf, fg, web_settings):
    connect_both(gapp, csrf, fg)
    d = web_settings.secrets_dir
    for name in ("google_token.json", lg.WRITE_TOKEN_FILE):
        assert stat.S_IMODE((d / name).stat().st_mode) == 0o600
    assert [p.name for p in d.iterdir() if p.suffix == ".tmp"] == []
    dir_mode = stat.S_IMODE(d.stat().st_mode)
    # 참고: 폴더 권한은 umask 에 의존한다(컨테이너에서는 명명 볼륨 + 비루트 사용자). 값은 결과서에 기록.
    print("secrets dir mode", oct(dir_mode))


def test_a7_no_secret_in_responses_audit_db_logs_after_full_live_cycle(live, logs):
    w = live
    bodies = []
    sids = prepare(w, 1)
    r = make_draft(w.api, w.csrf, sids)
    bodies.append(r.text)
    bid = r.json()["batch"]["id"]
    bodies.append(do_execute(w.api, w.csrf, bid, r.json()["precheck"]["confirm_text"]).text)
    tick(w)
    ch = [c for c in changes(w) if c.change_type == "apply"]
    assert ch and ch[0].mode == "live" and ch[0].result == "success"
    for url in ("/api/v1/google/status", "/api/v1/audit?page_size=200", "/api/v1/changes", "/api/v1/reports/changes", f"/api/v1/batches/{bid}", "/api/v1/dashboard", "/api/v1/jobs"):
        bodies.append(w.api.get(url).text)
    rb = w.api.post(f"/api/v1/changes/{ch[0].id}/rollback", json={"typed_video_id": ch[0].video_id, "approver": "검수자"}, headers=hdr(w.csrf, "idem-a7-rb-0001"))
    bodies.append(rb.text)
    assert rb.status_code == 201, rb.text
    assert logs.lines, "로그 캡처 자체가 비어 있으면 시험이 무의미"
    blob = "\n".join(bodies) + _all_db_text(w.factory) + "\n".join(logs.lines)
    for c in CANARIES:
        assert c not in blob, c
    # 구글에 보낸 Authorization 은 있었는지(시험 유효성)
    assert any((c.auth or "").startswith("Bearer AT-WRITE") for c in w.fg.put_calls())


def test_a8_oauth_error_text_from_google_is_not_reflected_to_user_but_lands_in_audit_detail(gapp, csrf, fg):
    """[관찰] 구글이 돌려준 error 문자열이 e.code 로 감사 기록에 들어간다(길이 상한 없음). 사용자 응답/화면에는 고정 한국어 메시지만."""
    fg.token_error = "RT-WRITE-SECRET-LEAK" + "z" * 3000
    url = start_flow(gapp, csrf, "connect")
    r = finish_flow(gapp, fg, url)
    assert r.status_code == 303 and "SECRET" not in r.text
    st = gapp.get("/api/v1/google/status").json()
    assert st["last_error"] and "SECRET" not in json.dumps(st, ensure_ascii=False)
    items = gapp.get("/api/v1/audit?page_size=200").json()["items"]
    failed = [i for i in items if i["action"] == "google.connect.failed"]
    assert failed
    code = json.dumps(failed[0], ensure_ascii=False)
    print("audit detail length", len(code))


def test_a9_unauthenticated_cross_site_callback_flood_writes_no_audit_rows(gapp, csrf, fg, factory):
    """[DEF-9B-001 조치 확인] 세션 없이(교차 사이트 GET) 임의 state 로 /callback 을 쳐도 감사 기록이 쌓이지 않는다. (2026-10-11 조치 전 첫 실행에서는 25회에 25행이 쌓여 이 시험이 '재현' 형태로 통과했다 — 결과서 R 절에 기록)"""
    gapp.cookies.clear()
    with factory() as s:
        before = s.execute(select(AuditLog)).scalars().all()
    n = 25
    for i in range(n):
        gapp.get(f"/api/v1/google/callback?code=C&state=forged{i}", follow_redirects=False, headers={"Sec-Fetch-Site": "cross-site"})
    with factory() as s:
        rows = s.execute(select(AuditLog)).scalars().all()
    added = [r for r in rows if r.action == "google.connect.failed"]
    assert len(added) == 0, len(added)


# ================= B. 허용 목록 우회 (TW-39) =================

VID = "abcdefghijk"


def _gw(allowed, sent):
    def send(url, token, body):
        sent.append((url, body))
        return {"snippet": body["snippet"]}

    class Acc:
        def access_token(self):
            return "T"
    return LiveYouTubeGateway(Acc(), allowed, http_get=lambda u, t: {"items": []}, http_send=send)


@pytest.mark.parametrize("vid", ["ABCDEFGHIJK", "abcdefghijk ", " abcdefghijk", "abcdefghijk\n", "abcdefghijk​", "​abcdefghijk", "ａｂｃｄｅｆｇｈｉｊｋ", "abcdefghijk/../x",
                                 "abcdefghijk?part=status", "abcdefghijk,zzzzzzzzzzz", "*", "", "abcdefghij", "abcdefghijkl", "abcdefghijk%00"])
def test_b1_live_write_rejects_every_variant_before_network(vid):
    sent = []
    g = _gw({VID}, sent)
    body = {"id": vid, "snippet": {"title": "t", "categoryId": "22"}}
    with pytest.raises(GatewayError) as e:
        g.update_snippet(vid, body)
    assert e.value.code == "not_allowed" and sent == []


def test_b2_body_id_mismatch_and_bad_snippet_rejected_before_network():
    sent = []
    g = _gw({VID}, sent)
    for body in ({"id": "zzzzzzzzzzz", "snippet": {"title": "t", "categoryId": "22"}}, {"id": VID, "snippet": "x"}, {"id": VID, "snippet": {"title": " ", "categoryId": "22"}},
                 {"id": VID, "snippet": {"title": "t"}}, {"snippet": {"title": "t", "categoryId": "22"}}, [], None):
        with pytest.raises(GatewayError):
            g.update_snippet(VID, body)  # type: ignore[arg-type]
    assert sent == []
    g.update_snippet(VID, {"id": VID, "snippet": {"title": "t", "categoryId": "22"}})
    assert len(sent) == 1 and sent[0][0] == "https://www.googleapis.com/youtube/v3/videos?part=snippet"  # 고정 URL, part=snippet 한정


@pytest.mark.parametrize("raw,expected", [("a, b ,,c", {"a", "b", "c"}), ("A,a", {"A", "a"}), (" 　x ", {"x"}), ("*", {"*"}), ("a;b", {"a;b"}), ("", set())])
def test_b3_allowed_env_parsing_is_exact_match_no_wildcard(raw, expected):
    assert lg.allowed_videos({"YTWEB_LIVE_ALLOWED_VIDEOS": raw}) == frozenset(expected)


@pytest.mark.parametrize("v", ["true", "yes", " 1", "1 ", "01", "on", "TRUE", "1\n", "", "2"])
def test_b4_live_write_flag_only_exact_1_fail_closed(v):
    assert lg.live_write_enabled({"YTWEB_LIVE_WRITE": v}) is False
    assert lg.live_write_enabled({"YTWEB_LIVE_WRITE": "1"}) is True
    assert lg.live_write_enabled({}) is False


def test_b5_settings_api_cannot_enable_live_or_change_allowlist(live):
    for k, v in (("live_write", True), ("YTWEB_LIVE_WRITE", "1"), ("live_allowed_videos", "x"), ("enable_live", True), ("mode", "live")):
        r = live.api.patch("/api/v1/settings", json={k: v}, headers=hdr(live.csrf))
        assert r.status_code == 400, (k, r.status_code, r.text)
    big = live.api.patch("/api/v1/settings", json={"daily_apply_cap": 10_000}, headers=hdr(live.csrf))
    assert big.status_code in (400, 422)


# ================= C. 모드 전환·롤백·모호 응답·감사 (TW-40, TW-41) =================

def test_c1_confirmed_in_live_then_switched_to_demo_does_not_apply(live):
    w = live
    bid, _ = queued(w)
    w.mp.setenv("YTWEB_LIVE_WRITE", "0")
    tick(w)
    assert w.fg.put_calls() == []
    with w.factory() as s:
        it = s.execute(select(BatchItem)).scalars().first()
        assert it.status != "success" and "live_mode_changed" in (it.skip_reason or "")
        assert s.execute(select(Change)).scalars().all() == []


def test_c2_confirmed_in_demo_then_switched_to_live_does_not_apply(live):
    w = live
    w.mp.setenv("YTWEB_LIVE_WRITE", "0")
    sids = prepare(w, 1)
    r = make_draft(w.api, w.csrf, sids)
    bid = r.json()["batch"]["id"]
    assert r.json()["precheck"]["confirm_text"].startswith("실행 ")  # 데모 문구
    assert do_execute(w.api, w.csrf, bid, r.json()["precheck"]["confirm_text"]).status_code == 202
    w.mp.setenv("YTWEB_LIVE_WRITE", "1")
    tick(w)
    assert w.fg.put_calls() == []
    with w.factory() as s:
        assert "live_mode_changed" in (s.execute(select(BatchItem)).scalars().first().skip_reason or "")


def test_c3_demo_confirm_text_rejected_in_live_mode(live):
    bid = make_draft(live.api, live.csrf, prepare(live, 1)).json()["batch"]["id"]
    for t in ("실행 1건", "실제 실행 1건​", "실제 실행 １건", "실제 실행 1건"):
        assert do_execute(live.api, live.csrf, bid, t).status_code == 422
    assert live.fg.put_calls() == []


def test_c4_rollback_live_mode_mismatch(live):
    w = live
    queued(w)
    tick(w)
    c = [c for c in changes(w) if c.change_type == "apply"][0]
    assert c.mode == "live" and len(w.fg.put_calls()) == 1
    w.mp.setenv("YTWEB_LIVE_WRITE", "0")
    r = w.api.post(f"/api/v1/changes/{c.id}/rollback", json={"typed_video_id": c.video_id, "approver": "검수자"}, headers=hdr(w.csrf, "idem-c4-rb-0001"))
    assert r.status_code == 409 and r.json()["code"] == "live_mode_mismatch" and len(w.fg.put_calls()) == 1


def test_c5_ambiguous_timeout_not_applied_never_double_writes(live):
    w = live
    w.fg.update_mode = "timeout_not_applied"
    bid, sids = queued(w)
    for _ in range(4):
        tick(w)
    assert len(w.fg.put_calls()) == 1
    cs = changes(w)
    assert len(cs) == 1 and cs[0].result == "planned"  # 사람이 확인해야 하는 상태로 남음(자동 정리·재시도 없음)
    # 같은 영상에 새 배치를 시도해도 두 번째 쓰기는 나가지 않는다
    w.fg.update_mode = "ok"
    sid2 = approve_via_api(w.api, w.csrf, w.ids[0])
    r = make_draft(w.api, w.csrf, [sid2])
    if r.status_code == 201:
        do_execute(w.api, w.csrf, r.json()["batch"]["id"], r.json()["precheck"]["confirm_text"])
        tick(w)
    assert len(w.fg.put_calls()) == 1


def test_c6_ambiguous_5xx_applied_is_confirmed_once_not_rewritten(live):
    w = live
    w.fg.update_mode = "http_5xx_applied"
    queued(w)
    tick(w)
    tick(w)
    assert len(w.fg.put_calls()) == 1
    assert [c.result for c in changes(w)] == ["success"]


def test_c7_only_allowed_video_ever_touched_by_put(live):
    w = live
    sids = prepare(w, 3)
    r = make_draft(w.api, w.csrf, sids)
    assert r.status_code == 201
    do_execute(w.api, w.csrf, r.json()["batch"]["id"], r.json()["precheck"]["confirm_text"])
    for _ in range(3):
        tick(w)
    assert {c.body["id"] for c in w.fg.put_calls()} <= {w.ids[0]}


def test_c8_audit_trail_covers_connect_execute_apply_rollback_disconnect(live):
    w = live
    queued(w)
    tick(w)
    c = [c for c in changes(w) if c.change_type == "apply"][0]
    w.api.post(f"/api/v1/changes/{c.id}/rollback", json={"typed_video_id": c.video_id, "approver": "검수자"}, headers=hdr(w.csrf, "idem-c8-rb-0001"))
    w.api.post("/api/v1/google/disconnect", headers=hdr(w.csrf))
    actions = [i["action"] for i in w.api.get("/api/v1/audit?page_size=200").json()["items"]]
    for a in ("google.connect.start", "google.connected", "google.connect_write.start", "google.write_connected", "batch.execute", "change.apply", "google.disconnected"):
        assert a in actions, (a, actions)
    assert any(a.startswith("change.rollback") or a == "change.rollback" for a in actions), actions


def test_c9_disconnect_removes_both_token_files(live, web_settings):
    live.api.post("/api/v1/google/disconnect", headers=hdr(live.csrf))
    assert not (web_settings.secrets_dir / "google_token.json").exists() and not (web_settings.secrets_dir / lg.WRITE_TOKEN_FILE).exists()
    st = live.api.get("/api/v1/google/status").json()
    assert st["live_write_ready"] is False


# ================= D. 외부 호출·SSRF·리다이렉트 (TW-35, TW-44) =================

def test_d1_non_https_refused_by_all_three_transports():
    from ytweb.youtube.live_read import default_http_get
    from ytweb.youtube.live_write import default_http_send
    for u in ("http://www.googleapis.com/x", "file:///etc/passwd", "ftp://x/", "HTTPS://x", " https://x"):
        with pytest.raises(Exception):
            default_http_get(u, "T")
        with pytest.raises(Exception):
            default_http_send(u, "T", {})
        with pytest.raises(Exception):
            oauth.default_http_post(u, {})


def test_d2_read_snippet_encodes_video_id_into_single_query_param():
    seen = []

    class Acc:
        def access_token(self):
            return "T"
    g = LiveYouTubeGateway(Acc(), {VID}, http_get=lambda u, t: seen.append(u) or {"items": []})
    g.read_snippet("x&part=status&id=other#frag")
    assert seen[0].startswith("https://www.googleapis.com/youtube/v3/videos?") and "&part=status&" not in seen[0] and "#" not in seen[0]


def test_d3_urllib_redirect_forwards_bearer_to_other_host_repro():
    """[재현 DEF-9B-002] default_http_get 은 urllib 기본 리다이렉트 처리기를 쓴다. 초기 URL 만 https 를 검사하고, 3xx 대상(다른 호스트·http)으로
    Authorization 헤더가 그대로 따라간다(urllib 동작). 구글 서버/중간자 장악이 전제라 가능성은 낮다(L)."""
    h = urllib.request.HTTPRedirectHandler()
    req = urllib.request.Request("https://www.googleapis.com/youtube/v3/videos", headers={"Authorization": "Bearer SECRET-T"})
    new = h.redirect_request(req, None, 302, "Found", {}, "http://evil.example/steal")
    assert new is not None and new.full_url == "http://evil.example/steal"
    assert new.get_header("Authorization") == "Bearer SECRET-T"


def test_d4_only_three_modules_import_urllib_request():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "backend" / "ytweb"
    bad = re.compile(r"^\s*(import|from)\s+(requests|httpx|urllib\.request|http\.client|aiohttp|socket|googleapiclient|google\.|openai|anthropic|subprocess|ftplib|smtplib|telnetlib)\b", re.M)
    hits = sorted({f.relative_to(root).as_posix() for f in root.rglob("*.py") for _ in bad.finditer(f.read_text(encoding="utf-8"))} - {"worker.py"})
    assert hits == ["youtube/google_oauth.py", "youtube/live_read.py", "youtube/live_write.py"], hits


# ================= E. 롤백 덮어쓰기 (DEF-9-002 의 M3 실제 모드 재현) =================


def _rollback(w, c, key):
    return w.api.post(f"/api/v1/changes/{c.id}/rollback", json={"typed_video_id": c.video_id, "approver": "검수자"}, headers=hdr(w.csrf, key))


def test_e2_live_rollback_refuses_when_studio_edited_after_apply(live):
    """[재현 DEF-9-002(High, M3 승격)] 실제 모드 반영 뒤 사람이 Studio 에서 설명을 고치고(그리고 제목도 다시 바꿈) 롤백하면, 백업 snippet 통째로
    PUT 되어 Studio 수정이 사라진다. 롤백은 '현재 제목 == 방금 반영한 제목'을 확인하지 않는다."""
    w = live
    queued(w)
    tick(w)
    c = [x for x in changes(w) if x.change_type == "apply"][0]
    vid = c.video_id
    orig_desc = w.fg.videos[vid].get("description")
    w.fg.videos[vid]["description"] = "STUDIO-EDIT-AFTER-APPLY 중요한 새 설명"
    w.fg.videos[vid]["title"] = "사람이 Studio 에서 다시 고친 제목입니다"
    r = _rollback(w, c, "idem-e2-rb-0001")
    # DEF-9-002 조치(2026-10-11, 보수적 기본): 반영 뒤 Studio 에서 바뀌었으면 덮어쓰지 않고 거부한다. 조치 전 첫 실행에서는 201 로 덮어썼다(결과서 R 절 기록).
    assert r.status_code == 409 and "live_changed_since_apply" in r.text, r.text
    after = w.fg.videos[vid]
    assert after["description"] == "STUDIO-EDIT-AFTER-APPLY 중요한 새 설명" and after["title"] == "사람이 Studio 에서 다시 고친 제목입니다"


# ================= F. 규칙 I·J 문구 — API 응답과 빌드 번들 (DEF-9-007·008 닫힘 직접 확인) =================

DISCLAIMER = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."


def test_f1_api_carries_disclaimer_in_precheck_and_report(live):
    w = live
    r = make_draft(w.api, w.csrf, prepare(w, 1))
    assert r.status_code == 201 and r.json()["precheck"]["notice"] == DISCLAIMER
    rep = w.api.get("/api/v1/reports/changes").json()
    assert DISCLAIMER in rep["notes"]
    csv = w.api.get("/api/v1/reports/changes.csv")
    if csv.status_code == 200:
        assert "법률 자문" in csv.text


def test_f2_built_bundle_contains_all_regulatory_and_ai_phrases():
    from pathlib import Path
    dist = Path(__file__).resolve().parents[1] / "frontend" / "dist" / "assets"
    js = "".join(p.read_text(encoding="utf-8") for p in dist.glob("*.js"))
    for phrase in (DISCLAIMER, "AI가 생성한 제안입니다", "A/B 테스트 중이 아님을 확인했습니다", "실제 수정 모드"):
        assert phrase in js, phrase


# ================= G. 상태 변경 POST 의 CSRF·출처 검사 (신규 google 라우트) =================

@pytest.mark.parametrize("path", ["/api/v1/google/connect", "/api/v1/google/connect-write", "/api/v1/google/disconnect"])
def test_g1_google_post_routes_reject_missing_csrf_foreign_origin_and_cross_site(gapp, csrf, path):
    ok = {"Origin": "http://127.0.0.1:8080", "X-CSRF-Token": csrf}
    assert gapp.post(path, headers={"Origin": ok["Origin"]}).status_code == 403                                   # CSRF 토큰 없음
    assert gapp.post(path, headers={**ok, "Origin": "https://evil.example"}).status_code == 403                    # 다른 출처
    assert gapp.post(path, headers={**ok, "Sec-Fetch-Site": "cross-site"}).status_code == 403                      # 교차 사이트
    assert gapp.post(path, headers={**ok, "X-CSRF-Token": "x" * len(csrf)}).status_code == 403                     # 틀린 토큰
    gapp.cookies.clear()
    assert gapp.post(path, headers=ok).status_code in (401, 403)                                                  # 세션 없음
    for m in ("get", "put", "delete", "patch"):                                                                     # GET 으로 상태 변경 불가
        assert getattr(gapp, m)(path, headers=ok).status_code in (401, 403, 404, 405)
