import json
import os
import stat
from datetime import datetime, timedelta, timezone

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from youtube_title import auth, cli
from youtube_title.config import load_settings
from youtube_title.errors import AuthError

FAKE_ACCESS = "ya29.FAKEACCESSTOKENVALUE0123456789"
FAKE_REFRESH = "1//0FAKEREFRESHTOKENVALUE0123456789abcdef"


def make_creds(scopes, *, expired=False, refresh=FAKE_REFRESH):
    exp = datetime.now(timezone.utc).replace(tzinfo=None) + (timedelta(hours=-1) if expired else timedelta(hours=1))
    return Credentials(token=FAKE_ACCESS, refresh_token=refresh, token_uri="https://oauth2.googleapis.com/token",
                       client_id="cid.apps.googleusercontent.com", client_secret="GOCSPX-fakeclientsecret", scopes=list(scopes), expiry=exp)


class FakeFlow:
    def __init__(self, creds=None, exc=None):
        self.creds, self.exc, self.kwargs = creds, exc, None

    def run_local_server(self, **kw):
        self.kwargs = kw
        if self.exc:
            raise self.exc
        return self.creds


@pytest.fixture
def settings(project, tmp_path):
    (project / "secrets").mkdir()
    (project / "secrets" / "client_secret.json").write_text("{}", encoding="utf-8")
    return load_settings(project, env={"YT_TOKEN_DIR": str(tmp_path / "tokens")})


def flow_for(scopes, **kw):
    return lambda settings_, scopes_: FakeFlow(make_creds(scopes, **kw))


def test_read_login_saves_only_read_token(settings):
    """TC-080: 읽기 로그인은 읽기 토큰 파일만 저장하고 쓰기 토큰은 만들지 않는다. [FR-016, SEC-015]"""
    path, _ = auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES))
    assert path == settings.token_dir / "read_token.json" and path.exists()
    assert not (settings.token_dir / "write_token.json").exists()
    assert set(json.loads(path.read_text(encoding="utf-8"))["scopes"]) == set(auth.READ_SCOPES)


def test_write_login_is_separate_file_and_leaves_read_token_untouched(settings):
    """TC-081: 쓰기 로그인은 별도 파일에 저장되고 읽기 토큰 파일을 건드리지 않는다. [SEC-015, ADR-004]"""
    rpath, _ = auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES))
    before = rpath.read_bytes()
    wpath, _ = auth.login("write", settings, flow_factory=flow_for(auth.WRITE_SCOPES))
    assert wpath != rpath and wpath.exists() and rpath.read_bytes() == before
    assert not set(auth.WRITE_SCOPES) & set(json.loads(rpath.read_text(encoding="utf-8"))["scopes"])


def test_token_dir_is_outside_project_by_default(project):
    """TC-082: 기본 토큰 저장 위치는 프로젝트 폴더 밖이라 저장소에 올라갈 수 없다. [SEC-008, ADR-004]"""
    s = load_settings(project, env={})
    assert project.resolve() not in auth.token_path(s, "read").parents


@pytest.mark.skipif(os.name == "nt", reason="POSIX 권한")
def test_token_file_permission_restricted(settings):
    """TC-083: 저장된 토큰 파일은 소유자만 읽을 수 있고(POSIX), 임시 파일이 남지 않는다. [SEC-008]"""
    path, secured = auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES))
    assert secured and stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(settings.token_dir.glob("*.tmp"))


def test_login_requires_all_requested_scopes(settings):
    """TC-084: 사용자가 권한 일부만 허용하면 저장하지 않고 안내한다(최소 권한 확인). [FR-016]"""
    with pytest.raises(AuthError) as ei:
        auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES[:1]))
    assert "권한" in ei.value.message
    assert not (settings.token_dir / "read_token.json").exists()


def test_login_failure_masks_exception_content(settings):
    """TC-085: 로그인 도중 예외 내용(토큰이 섞일 수 있음)은 오류 메시지에 노출하지 않고 종류만 남긴다. [SEC-008]"""
    flow = lambda s, sc: FakeFlow(exc=RuntimeError(f"실패 {FAKE_ACCESS}"))
    with pytest.raises(AuthError) as ei:
        auth.login("read", settings, flow_factory=flow)
    text = ei.value.message + ei.value.next_step + ei.value.cause
    assert FAKE_ACCESS not in text and ei.value.cause == "RuntimeError"


def test_missing_client_secret_points_to_guide(project, tmp_path):
    """TC-086: 클라이언트 비밀 파일이 없으면 03 가이드 위치를 안내한다. [NFR-007]"""
    s = load_settings(project, env={"YT_TOKEN_DIR": str(tmp_path / "t")})
    with pytest.raises(AuthError) as ei:
        auth.login("read", s)
    assert "03_manual_setup.md" in ei.value.next_step


def test_load_valid_token(settings):
    """TC-087: 유효한 읽기 토큰은 그대로 읽힌다. [FR-016]"""
    auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES))
    creds = auth.load_credentials("read", settings)
    assert creds.valid and creds.token == FAKE_ACCESS


def test_load_without_token_tells_next_step(settings):
    """TC-088: 토큰이 없으면 어떤 명령을 먼저 실행할지 알려 준다(읽기/쓰기 구분). [NFR-007]"""
    for kind in ("read", "write"):
        with pytest.raises(AuthError) as ei:
            auth.load_credentials(kind, settings)
        assert f"auth --{kind}" in ei.value.next_step


def test_expired_token_is_refreshed_and_saved(settings):
    """TC-089: 만료된 토큰은 갱신 토큰으로 갱신되어 파일에 다시 저장된다. [FR-016]"""
    auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES, expired=True))
    calls = []

    def fake_refresh(creds):
        calls.append(1)
        creds.token = "ya29.NEWTOKENVALUEXXXXXXXXXXXX"
        creds.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    creds = auth.load_credentials("read", settings, refresh=fake_refresh)
    assert calls == [1] and creds.valid
    assert json.loads(auth.token_path(settings, "read").read_text(encoding="utf-8"))["token"].startswith("ya29.NEW")


def test_refresh_failure_asks_relogin_without_leaking(settings):
    """TC-090: 갱신이 거부되면(7일 만료·철회) 재로그인 안내를 하고 토큰 내용은 노출하지 않는다. [FR-016, RISK-012, SEC-008]"""
    auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES, expired=True))

    def boom(creds):
        raise RefreshError(f"invalid_grant {FAKE_REFRESH}")

    with pytest.raises(AuthError) as ei:
        auth.load_credentials("read", settings, refresh=boom)
    text = ei.value.message + ei.value.next_step + ei.value.cause
    assert "auth --read" in ei.value.next_step and FAKE_REFRESH not in text


def test_expired_without_refresh_token(settings):
    """TC-091: 갱신 토큰이 없는 만료 토큰은 재로그인을 안내한다. [FR-016]"""
    auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES, expired=True, refresh="x"))
    p = auth.token_path(settings, "read")
    info = json.loads(p.read_text(encoding="utf-8"))
    info["refresh_token"] = None
    p.write_text(json.dumps(info), encoding="utf-8")
    attempts = []
    with pytest.raises(AuthError) as ei:
        auth.load_credentials("read", settings, refresh=lambda creds: attempts.append(1))
    assert attempts == [] and "만료" in ei.value.message  # 갱신 토큰이 없으면 갱신(네트워크)을 시도조차 하지 않는다


@pytest.mark.parametrize("content", ["not json", "[]", "{}", '{"token": "x"}'])
def test_corrupted_token_file(settings, content):
    """TC-092: 손상된 토큰 파일은 삭제 후 재로그인 안내가 있는 AuthError가 된다. [NFR-007]"""
    p = auth.token_path(settings, "read")
    p.parent.mkdir(parents=True)
    p.write_text(content, encoding="utf-8")
    with pytest.raises(AuthError) as ei:
        auth.load_credentials("read", settings)
    assert "auth" in ei.value.next_step


def test_token_with_missing_scope_rejected(settings):
    """TC-093: 필요한 권한 범위가 빠진 토큰(예: 쓰기 파일에 읽기 토큰)은 거부한다. [SEC-015]"""
    p = auth.token_path(settings, "write")
    auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES))
    p.write_text(auth.token_path(settings, "read").read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(AuthError) as ei:
        auth.load_credentials("write", settings)
    assert "권한" in ei.value.message


def test_read_load_never_touches_write_token(settings):
    """TC-094: 읽기 토큰을 읽을 때 쓰기 토큰 파일은 열지 않는다(깨져 있어도 영향 없음). [SEC-015]"""
    auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES))
    wp = auth.token_path(settings, "write")
    wp.write_text("깨진 파일", encoding="utf-8")
    assert auth.load_credentials("read", settings).valid


def test_revoke_deletes_both_and_is_idempotent(settings):
    """TC-095: 로그인 삭제는 읽기·쓰기 토큰을 모두 지우고, 없어도 오류 없이 끝난다. [SEC-015]"""
    auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES))
    auth.login("write", settings, flow_factory=flow_for(auth.WRITE_SCOPES))
    assert len(auth.revoke(settings)) == 2
    assert auth.revoke(settings) == []
    assert [s["exists"] for s in auth.status(settings)] == [False, False]


def run_cli(project, argv, streams, tokens, **kw):
    return cli.main(["--base-dir", str(project)] + argv, out=streams.out, err=streams.err, env={"YT_TOKEN_DIR": str(tokens)}, **kw)


def test_cli_status_without_option(project, streams, tmp_path):
    """TC-096: 옵션 없이 실행하면 로그인 상태(없음)와 시작 안내를 보여 준다. 토큰 값은 읽지 않는다. [EVT-001, UX-001]"""
    assert run_cli(project, ["auth"], streams, tmp_path / "t") == 0
    out = streams.out.getvalue()
    assert "[주의] 없음" in out and "auth --read" in out and "법률 자문이 아니며" in out


def test_cli_read_login_end_to_end_no_token_in_output_or_log(project, streams, tmp_path, monkeypatch):
    """TC-097: `auth --read`가 저장까지 끝내고, 화면과 로그 어디에도 토큰이 찍히지 않는다. [EVT-001, SEC-008, K-6]"""
    (project / "secrets").mkdir()
    (project / "secrets" / "client_secret.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(auth, "new_flow", lambda s, sc: FakeFlow(make_creds(auth.READ_SCOPES)))
    assert run_cli(project, ["auth", "--read"], streams, tmp_path / "t") == 0
    log = (project / "data" / "logs" / "youtube-title.log").read_text(encoding="utf-8")
    for text in (streams.out.getvalue(), streams.err.getvalue(), log):
        assert FAKE_ACCESS not in text and FAKE_REFRESH not in text and "GOCSPX-fake" not in text
    assert "읽기 권한 로그인을 저장했습니다" in streams.out.getvalue()


def test_cli_write_requires_typed_confirmation(project, streams, tmp_path, monkeypatch):
    """TC-098: `auth --write`는 '쓰기권한'을 직접 입력해야 진행하고, 입력이 없으면 토큰을 만들지 않는다. [SEC-015, SEC-001]"""
    (project / "secrets").mkdir()
    (project / "secrets" / "client_secret.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(auth, "new_flow", lambda s, sc: FakeFlow(make_creds(auth.WRITE_SCOPES)))
    tokens = tmp_path / "t"
    assert run_cli(project, ["auth", "--write"], streams, tokens, input_fn=lambda p: "") == 1
    assert not (tokens / "write_token.json").exists()
    assert run_cli(project, ["auth", "--write"], streams, tokens, input_fn=lambda p: "쓰기권한") == 0
    assert (tokens / "write_token.json").exists()


def test_cli_revoke_and_exclusive_options(project, streams, tmp_path, monkeypatch):
    """TC-099: `auth --revoke`는 로컬 토큰을 지우고 구글 쪽 회수 방법을 안내한다. 옵션 동시 지정은 거부. [EVT-001]"""
    tokens = tmp_path / "t"
    tokens.mkdir()
    (tokens / "read_token.json").write_text("{}")
    assert run_cli(project, ["auth", "--revoke"], streams, tokens) == 0
    assert not (tokens / "read_token.json").exists() and "타사 앱" in streams.out.getvalue()
    assert run_cli(project, ["auth", "--read", "--write"], streams, tokens) == 2


def test_new_flow_builds_real_installed_app_flow_from_client_file(settings):
    """TC-100: 클라이언트 비밀 파일이 올바르면 요청한 권한 범위로 실제 설치형 앱 흐름 객체가 만들어진다(네트워크 호출 없음). [FR-016]"""
    settings.client_secret_path.write_text(json.dumps({"installed": {
        "client_id": "cid.apps.googleusercontent.com", "client_secret": "GOCSPX-fake", "project_id": "p",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"]}}), encoding="utf-8")
    flow = auth.new_flow(settings, auth.READ_SCOPES)
    assert flow.client_config["client_id"] == "cid.apps.googleusercontent.com"
    assert set(flow.oauth2session.scope) == set(auth.READ_SCOPES)


def test_auth_error_from_flow_passes_through_unchanged(settings):
    """TC-101: 흐름에서 이미 한국어 AuthError가 올라오면 다른 오류로 바꾸지 않고 그대로 전달한다. [NFR-007]"""
    original = AuthError("원래 메시지", "원래 안내")
    with pytest.raises(AuthError) as ei:
        auth.login("read", settings, flow_factory=lambda s, sc: FakeFlow(exc=original))
    assert ei.value is original


def test_default_refresh_path_uses_google_request(settings, monkeypatch):
    """TC-102: 갱신 함수를 따로 주지 않으면 구글 인증 라이브러리의 기본 갱신 경로(Request)를 사용한다. [FR-016]"""
    auth.login("read", settings, flow_factory=flow_for(auth.READ_SCOPES, expired=True))
    seen = []

    def fake_refresh(self, request):
        seen.append(type(request).__name__)
        self.token = "ya29.REFRESHEDVIADEFAULTPATH000"
        self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", fake_refresh)
    assert auth.load_credentials("read", settings).valid and seen == ["Request"]
