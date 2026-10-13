"""TC-VM-100~: routers/google.py (M2 단위 2 + M3 connect-write) HTTP 수준 독립 검증. 실제 로그인 흐름을 가짜 구글로 끝까지 돈다."""
from __future__ import annotations

import json
import os
import re
import stat
import urllib.parse
from pathlib import Path

import pytest
from sqlalchemy import select

from tests.verify_m23.conftest import CLIENT_SECRET, finish_flow, hdr, start_flow
from ytweb.db.models import AuditLog

HANGUL = re.compile("[가-힣]")


def secrets_dir(web_settings) -> Path:
    return web_settings.secrets_dir


def test_tc_vm_100_status_without_client_is_demo_and_has_no_secret_fields(gapp, csrf, client_file):
    client_file.unlink()
    s = gapp.get("/api/v1/google/status").json()
    assert s["mode"] == "demo" and s["connected"] is False and s["client_ready"] is False
    assert s["write_connected"] is False and s["live_write_ready"] is False
    assert HANGUL.search(s["message"])
    assert not any("token" in k or "secret" in k for k in s)


def test_tc_vm_101_status_requires_session(api, client_file):
    r = api.get("/api/v1/google/status")
    assert r.status_code == 401


@pytest.mark.parametrize("path", ["connect", "connect-write", "disconnect"])
def test_tc_vm_102_post_endpoints_need_session_csrf_and_origin(gapp, csrf, path):
    url = f"/api/v1/google/{path}"
    assert gapp.post(url, headers={"Origin": "http://127.0.0.1:8080"}).status_code in (401, 403)           # CSRF 토큰 없음
    assert gapp.post(url, headers={"Origin": "http://evil.example", "X-CSRF-Token": csrf}).status_code in (401, 403)  # 다른 Origin
    assert gapp.post(url, headers={"Origin": "http://127.0.0.1:8080", "X-CSRF-Token": "wrong"}).status_code in (401, 403)
    gapp.cookies.clear()
    assert gapp.post(url, headers=hdr(csrf)).status_code in (401, 403)                                      # 세션 없음


@pytest.mark.parametrize("path", ["connect", "connect-write"])
def test_tc_vm_103_missing_client_file_is_409_korean_with_hint(gapp, csrf, client_file, path):
    client_file.unlink()
    r = gapp.post(f"/api/v1/google/{path}", headers=hdr(csrf))
    j = r.json()
    assert r.status_code == 409 and j["code"] == "google_client_missing" if "code" in j else r.status_code == 409
    assert HANGUL.search(j.get("hint", "")) and HANGUL.search(j.get("detail", ""))
    assert CLIENT_SECRET not in r.text


@pytest.mark.parametrize("content", ["{bad", '{"installed":{}}', "[]"])
def test_tc_vm_104_invalid_client_file_is_409_not_500(gapp, csrf, client_file, content):
    client_file.write_text(content)
    for path in ("connect", "connect-write"):
        r = gapp.post(f"/api/v1/google/{path}", headers=hdr(csrf))
        assert r.status_code == 409, (content, path, r.status_code, r.text[:200])
        assert HANGUL.search(r.json().get("hint", ""))


def test_tc_vm_110_read_login_full_flow_pkce_verified_by_fake_google(gapp, csrf, fg, web_settings):
    url = start_flow(gapp, csrf, "connect")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["scope"] == ["https://www.googleapis.com/auth/youtube.readonly"]
    assert q["redirect_uri"] == ["http://127.0.0.1:8080/api/v1/google/callback"]
    assert CLIENT_SECRET not in url
    r = finish_flow(gapp, fg, url)
    assert r.status_code == 303 and r.headers["location"] == "/#/" and r.headers["cache-control"] == "no-store"
    assert "SECRET" not in r.text and "SECRET" not in json.dumps(dict(r.headers))
    tok = json.loads((secrets_dir(web_settings) / "google_token.json").read_text())
    assert tok["scope"].endswith("youtube.readonly") and tok["refresh_token"].startswith("RT-READ")
    assert not (secrets_dir(web_settings) / "google_write_token.json").exists()           # 쓰기 토큰 파일은 안 생김
    assert stat.S_IMODE(os.stat(secrets_dir(web_settings) / "google_token.json").st_mode) == 0o600
    s = gapp.get("/api/v1/google/status").json()
    assert s["connected"] is True and s["write_connected"] is False and s["mode"] == "read"
    assert "SECRET" not in json.dumps(s)


def test_tc_vm_111_write_login_saves_only_to_write_file_with_force_ssl_scope(gapp, csrf, fg, web_settings):
    url = start_flow(gapp, csrf, "connect-write")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["scope"] == ["https://www.googleapis.com/auth/youtube.force-ssl"]
    assert finish_flow(gapp, fg, url).status_code == 303
    sd = secrets_dir(web_settings)
    assert not (sd / "google_token.json").exists()                                         # 읽기 토큰은 건드리지 않는다
    w = json.loads((sd / "google_write_token.json").read_text())
    assert w["scope"].endswith("force-ssl") and w["refresh_token"].startswith("RT-WRITE")
    assert stat.S_IMODE(os.stat(sd / "google_write_token.json").st_mode) == 0o600
    s = gapp.get("/api/v1/google/status").json()
    assert s["write_connected"] is True and s["connected"] is False and s["live_write_ready"] is False   # 환경변수 없으면 준비 안 됨


def test_tc_vm_112_read_and_write_tokens_are_independent_files_with_different_values(gapp, csrf, fg, web_settings):
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect"))
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect-write"))
    sd = secrets_dir(web_settings)
    r, w = json.loads((sd / "google_token.json").read_text()), json.loads((sd / "google_write_token.json").read_text())
    assert r["access_token"] != w["access_token"] and r["refresh_token"] != w["refresh_token"] and r["scope"] != w["scope"]


def test_tc_vm_113_state_cannot_be_replayed_second_exchange_never_happens(gapp, csrf, fg, web_settings):
    url = start_flow(gapp, csrf, "connect")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    code = fg.consent(url)
    cb = f"/api/v1/google/callback?code={code}&state={q['state'][0]}"
    assert gapp.get(cb, follow_redirects=False).status_code == 303
    n_token_calls = len([c for c in fg.calls if c.path == "/token"])
    (secrets_dir(web_settings) / "google_token.json").unlink()
    code2 = fg.consent(url)
    r = gapp.get(f"/api/v1/google/callback?code={code2}&state={q['state'][0]}", follow_redirects=False)
    assert r.status_code == 303
    assert len([c for c in fg.calls if c.path == "/token"]) == n_token_calls                # 재사용 state 로는 구글에 코드 교환 요청도 안 감
    assert not (secrets_dir(web_settings) / "google_token.json").exists()
    assert gapp.get("/api/v1/google/status").json()["last_error"]                          # 한 번 안내


@pytest.mark.parametrize("state", ["forged", "", "A" * 43, "%00"])
def test_tc_vm_114_forged_state_saves_nothing_and_never_calls_google(gapp, csrf, fg, web_settings, state):
    start_flow(gapp, csrf, "connect")
    r = gapp.get(f"/api/v1/google/callback?code=C&state={state}", follow_redirects=False)
    assert r.status_code == 303
    assert [c for c in fg.calls if c.path == "/token"] == []
    assert not list(secrets_dir(web_settings).glob("google*")) if secrets_dir(web_settings).exists() else True


def test_tc_vm_115_callback_without_state_or_code_is_safe(gapp, csrf, fg):
    assert gapp.get("/api/v1/google/callback", follow_redirects=False).status_code == 303
    assert gapp.get("/api/v1/google/callback?code=C", follow_redirects=False).status_code == 303
    assert fg.calls == []


def test_tc_vm_116_state_expiry_10_minutes_over_http(gapp, csrf, fg, web_settings):
    from tests.verify_m23.test_vm_01_oauth_core import T
    url = start_flow(gapp, csrf, "connect")
    ctx = gapp.app.state.google_ctx
    t = T(1000.0)
    ctx.pending._clock = t
    # 시작 시각을 현재 가짜 시계 기준으로 다시 맞춘다
    for k, (v, ts) in list(ctx.pending._items.items()):
        ctx.pending._items[k] = (v, 1000.0)
    t.t = 1000.0 + 600
    r = finish_flow(gapp, fg, url)
    assert r.status_code == 303 and [c for c in fg.calls if c.path == "/token"] == []
    assert not (secrets_dir(web_settings) / "google_token.json").exists()


def test_tc_vm_117_user_denied_saves_nothing_consumes_state_and_audits_code_only(gapp, csrf, fg, web_settings, factory):
    url = start_flow(gapp, csrf, "connect-write")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    r = gapp.get(f"/api/v1/google/callback?error=access_denied&state={q['state'][0]}", follow_redirects=False)
    assert r.status_code == 303 and [c for c in fg.calls if c.path == "/token"] == []
    assert not (secrets_dir(web_settings) / "google_write_token.json").exists()
    r2 = gapp.get(f"/api/v1/google/callback?code=C&state={q['state'][0]}", follow_redirects=False)     # 소진됨
    assert [c for c in fg.calls if c.path == "/token"] == []
    s = gapp.get("/api/v1/google/status").json()
    assert HANGUL.search(s["last_error"] or "") and "access_denied" not in (s["last_error"] or "")
    assert gapp.get("/api/v1/google/status").json()["last_error"] is None                 # 1회만 표시


@pytest.mark.parametrize("err", ["invalid_grant", "invalid_client", "server_error"])
def test_tc_vm_118_google_token_error_saves_nothing_and_message_is_korean(gapp, csrf, fg, web_settings, err):
    url = start_flow(gapp, csrf, "connect")
    fg.token_error = err
    assert finish_flow(gapp, fg, url).status_code == 303
    assert not (secrets_dir(web_settings) / "google_token.json").exists()
    le = gapp.get("/api/v1/google/status").json()["last_error"]
    assert HANGUL.search(le) and err not in le


def test_tc_vm_119_google_omits_refresh_token_saves_nothing(gapp, csrf, fg, web_settings):
    url = start_flow(gapp, csrf, "connect")
    fg.omit_refresh = True
    finish_flow(gapp, fg, url)
    assert not (secrets_dir(web_settings) / "google_token.json").exists()
    assert HANGUL.search(gapp.get("/api/v1/google/status").json()["last_error"])


def test_tc_vm_120_read_state_can_never_write_to_write_store_and_vice_versa(gapp, csrf, fg, web_settings):
    sd = secrets_dir(web_settings)
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect"))
    assert (sd / "google_token.json").exists() and not (sd / "google_write_token.json").exists()
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect-write"))
    r = json.loads((sd / "google_token.json").read_text())
    assert r["scope"].endswith("readonly")                                                  # 쓰기 로그인이 읽기 토큰을 덮어쓰지 않음


def test_tc_vm_121_interleaved_flows_each_land_in_their_own_store(gapp, csrf, fg, web_settings):
    sd = secrets_dir(web_settings)
    u_read, u_write = start_flow(gapp, csrf, "connect"), start_flow(gapp, csrf, "connect-write")
    finish_flow(gapp, fg, u_write)
    finish_flow(gapp, fg, u_read)
    assert json.loads((sd / "google_token.json").read_text())["scope"].endswith("readonly")
    assert json.loads((sd / "google_write_token.json").read_text())["scope"].endswith("force-ssl")


def test_tc_vm_122_many_unfinished_write_logins_do_not_misroute_the_latest_write_token(gapp, csrf, fg, web_settings):
    """connect-write 를 한도(20)보다 많이 눌러도, 가장 마지막 쓰기 로그인은 쓰기 저장소에 저장돼야 한다(읽기 토큰 파일에 쓰기 토큰이 섞이면 안 됨).
    한도에 닿은 뒤 400번 더 눌러, 방금 시작한 state 가 '쓰기 state 집합'에서 사라진(=읽기로 처리될) 경우를 센다."""
    sd = secrets_dir(web_settings)
    ctx = gapp.app.state.google_ctx if getattr(gapp.app.state, "google_ctx", None) else None
    for _ in range(20):
        start_flow(gapp, csrf, "connect-write")
    ctx = gapp.app.state.google_ctx
    lost, landed = 0, 0
    for _ in range(400):
        url = start_flow(gapp, csrf, "connect-write")
        st = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
        if ctx.pending.peek_kind(st) != "write":                                             # 이 로그인은 '읽기'로 처리될 운명
            lost += 1
            finish_flow(gapp, fg, url)                                                       # 실제 영향 확인: 사용자가 바로 로그인을 마친 경우
            f = sd / "google_token.json"
            if f.exists() and json.loads(f.read_text())["scope"].endswith("force-ssl"):
                landed += 1
                f.unlink()
    assert landed == 0, f"400회 중 {lost}회 새 쓰기 state 소실, 그중 {landed}회 쓰기 토큰이 읽기 저장소(google_token.json)에 저장됨"


def test_tc_vm_123_oversized_callback_params_rejected(gapp):
    assert gapp.get("/api/v1/google/callback?code=" + "a" * 2049 + "&state=x", follow_redirects=False).status_code == 422
    assert gapp.get("/api/v1/google/callback?code=a&state=" + "a" * 257, follow_redirects=False).status_code == 422
    assert gapp.get("/api/v1/google/callback?error=" + "a" * 101, follow_redirects=False).status_code == 422


def test_tc_vm_124_callback_get_does_not_need_session_but_forged_one_changes_no_state(gapp, csrf, fg, web_settings, factory):
    with factory() as s:
        before = s.execute(select(AuditLog.action)).scalars().all()
    gapp.cookies.clear()
    r = gapp.get("/api/v1/google/callback?code=C&state=zzz", follow_redirects=False)
    assert r.status_code == 303 and fg.calls == []
    with factory() as s:
        after = s.execute(select(AuditLog.action)).scalars().all()
    assert set(after) - set(before) <= {"google.connect.failed"}


def test_tc_vm_125_disconnect_clears_both_tokens_and_audits(gapp, csrf, fg, web_settings, factory, monkeypatch):
    # 2026-10-13 보안 결정(연결 해제 때 구글에 토큰 폐기 요청)으로 응답에 revoked 가 추가됐다.
    # 이 시험 구성에는 구글 클라이언트 파일이 없어 폐기 요청을 보내지 않으므로 revoked 는 null 이어야 하고, 외부 호출이 나가면 실패한다.
    import urllib.request

    def _no_network(req, timeout=None):
        raise AssertionError("구글 클라이언트 파일이 없는데 폐기 요청이 나갔다")
    monkeypatch.setattr(urllib.request, "urlopen", _no_network)
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect"))
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect-write"))
    r = gapp.post("/api/v1/google/disconnect", headers=hdr(csrf))
    assert r.status_code == 200 and r.json() == {"connected": False, "revoked": None}
    s = gapp.get("/api/v1/google/status").json()
    assert s["connected"] is False and s["write_connected"] is False
    assert not list(secrets_dir(web_settings).glob("google*token*"))
    assert gapp.post("/api/v1/google/disconnect", headers=hdr(csrf)).status_code == 200      # 멱등


def test_tc_vm_126_audit_records_exist_and_contain_no_tokens_or_secrets(gapp, csrf, fg, factory):
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect"))
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect-write"))
    fg.token_error = "invalid_grant"
    finish_flow(gapp, fg, start_flow(gapp, csrf, "connect"))
    gapp.post("/api/v1/google/disconnect", headers=hdr(csrf))
    with factory() as s:
        rows = s.execute(select(AuditLog)).scalars().all()
    actions = [r.action for r in rows]
    for a in ("google.connect.start", "google.connect_write.start", "google.connected", "google.write_connected", "google.connect.failed", "google.disconnected"):
        assert a in actions, a
    blob = json.dumps([[r.actor, r.action, r.target_type, r.target_id, r.detail] for r in rows], ensure_ascii=False)
    for needle in ("SECRET", CLIENT_SECRET, "CODE-", "code_verifier", "access_token", "refresh_token"):
        assert needle not in blob, needle
    from ytweb.core import audit
    with factory() as s:
        assert audit.verify_chain(s) is True


def test_tc_vm_127_tokens_never_in_logs_or_any_response_during_full_flow(gapp, csrf, fg, caplog, web_settings):
    import logging
    caplog.set_level(logging.DEBUG)
    bodies = []
    for which in ("connect", "connect-write"):
        u = gapp.post(f"/api/v1/google/{which}", headers=hdr(csrf))
        bodies.append(u.text + json.dumps(dict(u.headers)))
        r = finish_flow(gapp, fg, u.json()["auth_url"])
        bodies.append(r.text + json.dumps(dict(r.headers)))
        bodies.append(gapp.get("/api/v1/google/status").text)
    bodies.append(gapp.post("/api/v1/google/disconnect", headers=hdr(csrf)).text)
    allout = "\n".join(bodies) + caplog.text
    for needle in ("AT-READ", "AT-WRITE", "RT-READ", "RT-WRITE", CLIENT_SECRET):
        assert needle not in allout, needle


def test_tc_vm_128_connect_url_contains_no_session_or_csrf_material(gapp, csrf):
    u = gapp.post("/api/v1/google/connect", headers=hdr(csrf)).json()["auth_url"]
    assert csrf not in u


def test_tc_vm_129_write_state_set_is_bounded_and_cleared_after_callback(gapp, csrf, fg):
    for _ in range(30):
        start_flow(gapp, csrf, "connect-write")
    ctx = gapp.app.state.google_ctx
    assert len(ctx.pending._kinds) <= 20  # 구현 변경(2026-10-11, DEF-VM-003 조치): 쓰기 state 집합 대신 PendingAuth 가 종류를 함께 보관·소진한다
    url = start_flow(gapp, csrf, "connect-write")
    st = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    finish_flow(gapp, fg, url)
    assert st not in ctx.pending._kinds and ctx.pending.peek_kind(st) == "read"


def test_tc_vm_130_openapi_lists_google_post_routes_and_hides_callback(gapp):
    spec = gapp.get("/openapi.json")
    if spec.status_code != 200:
        pytest.skip("openapi 비활성")
    paths = spec.json()["paths"]
    assert "/api/v1/google/connect-write" in paths and "/api/v1/google/callback" not in paths
