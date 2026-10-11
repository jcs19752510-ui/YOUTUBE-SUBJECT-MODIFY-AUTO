"""7단계 통합 테스트: F-A(WU-1 auth, WU-2 fetch/quota) + F-B(WU-3 validate). CLI 진입점(ytitle.cli.main)으로 단위를 엮는다.

IT-A: F-A 내부 접점 / IT-B: F-B 내부·설정·입력 접점 / IT-X: F-A→F-B 교차 접점.
실제 구글·네트워크 호출 없음(소켓 차단 + 읽기 전용 가짜 서비스).
"""
import json
import socket
import time
from datetime import datetime, timedelta, timezone

import pytest
from google.oauth2.credentials import Credentials

from ytitle import auth
from ytitle.errors import AuthError
from ytitle.quota import QuotaManager
from ytitle.timeutil import FixedClock
from ytitle.ui import DISCLAIMER

from it_fab_support import (DESCRIPTION, FAKE_ACCESS, FAKE_REFRESH, GOOD_TITLE, SECRETS, SUMMARY, FakeApi, FakeFlow,
                            Lab, http_error, make_creds, video_item, vid)

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """실제 네트워크 접근을 막고, 시도가 있었는지 기록한다(시도가 있었다면 테스트 종료 시 실패)."""
    attempts = []

    def deny(*a, **k):
        attempts.append(a)
        raise OSError("테스트 중 네트워크 접근 차단")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)
    yield attempts
    assert attempts == [], "네트워크 접근 시도가 있었습니다"


@pytest.fixture
def lab(tmp_path, monkeypatch):
    return Lab(tmp_path, monkeypatch)


def assert_no_secrets(*texts):
    for t in texts:
        for s in SECRETS:
            assert s not in t, f"비밀 문자열이 노출됨: {s}"


# ================================================================= IT-A: 인증 → 조회 → 쿼터 → DB


def test_read_login_then_fetch_all_three_pages(lab):
    """TC-700: 읽기 로그인 → fetch --all(3쪽·120개)이 DB·쿼터 장부·실행 기록에 일관되게 남는다. [IT-A01, FR-006, FR-015, FR-016, EVT-002, EVT-101~103]"""
    lab.channel(120)
    lab.login_read()
    assert lab.token_files() == ["read_token.json"]
    r = lab.run("fetch", "--all")
    assert r.code == 0 and "영상 120개를 조회해 저장했습니다" in r.out and "7 / 6000 units (남음 5993)" in r.out
    assert lab.q("SELECT COUNT(*) c FROM videos")[0]["c"] == 120
    assert lab.api.count("playlistItems.list") == 3 and lab.api.count("videos.list") == 3
    assert lab.quota_rows() == [("channels.list", 1, "ok")] + [("playlistItems.list", 1, "ok")] * 3 + [("videos.list", 1, "ok")] * 3
    runs = lab.q("SELECT run_id, command, mode, exit_code, summary FROM run_logs ORDER BY id")
    assert [(x["command"], x["mode"], x["exit_code"], x["summary"]) for x in runs] == [("auth", "dry_run", 0, "ok"), ("fetch", "dry_run", 0, "ok")]
    assert {x["run_id"] for x in lab.q("SELECT run_id FROM quota_usage")} == {runs[1]["run_id"]}  # 쿼터 행이 fetch 실행 기록과 연결됨
    # 읽기 토큰에서 로드한 자격 증명은 읽기 범위만 갖는다(auth → fetch 접점)
    assert len(lab.built_with) == 1 and set(lab.built_with[0].scopes) == set(auth.READ_SCOPES)


def test_fetch_metrics_chain_uses_stored_videos(lab):
    """TC-701: fetch --all --metrics 가 지표를 기간·단계와 함께 저장하고, 이어지는 fetch --metrics 는 저장된 영상 목록을 입력으로 쓴다. [IT-A02, FR-007, FR-015, EVT-105]"""
    lab.channel(60)
    lab.login_read()
    assert lab.run("fetch", "--all", "--metrics", "--phase", "before").code == 0
    rows = lab.q("SELECT * FROM metrics_snapshots")
    assert len(rows) == 60 and {r["phase"] for r in rows} == {"before"} and {r["source"] for r in rows} == {"api"}
    assert {(r["period_start"], r["period_end"]) for r in rows} == {("2026-09-12", "2026-10-09")}
    assert lab.api.count("reports.query") == 2
    n = len(lab.api.calls)
    r = lab.run("fetch", "--metrics", "--phase", "after", "--days", "7")
    assert r.code == 0 and lab.api.count("channels.list") == 1 and lab.api.count("videos.list") == 2  # 영상 재조회 없음
    assert len(lab.api.calls) == n + 2
    assert {x["phase"] for x in lab.q("SELECT phase FROM metrics_snapshots")} == {"before", "after"}
    assert lab.q("SELECT period_start FROM metrics_snapshots WHERE phase='after' LIMIT 1")[0][0] == "2026-10-03"
    assert sum(u for m, u, s in lab.quota_rows() if m == "reports.query") == 4


def test_quota_ledger_accumulates_across_runs(lab):
    """TC-702: 쿼터 장부는 실행(명령)이 달라도 누적되고, CLI 밖에서 만든 QuotaManager도 같은 합계를 본다. [IT-A03, FR-015, SEC-002, NFR-003]"""
    lab.channel(3)
    lab.login_read()
    used = []
    for argv in (["fetch", "--all"], ["fetch", "--video", vid(1)], ["fetch", "--metrics"]):
        r = lab.run(*argv)
        assert r.code == 0
        used.append(int(r.out.split("units")[0].rsplit("/", 1)[0].split(":")[-1]))
    assert used == [3, 4, 5]
    assert len({x["run_id"] for x in lab.q("SELECT run_id FROM quota_usage")}) == 3
    import sqlite3
    conn = sqlite3.connect(lab.db_path)
    conn.row_factory = sqlite3.Row
    from ytitle.config import load_settings
    q = QuotaManager(conn, load_settings(lab.project, lab.env), lab.clock)
    assert q.used_today() == 5 and q.remaining() == 5995
    conn.close()


def test_exhausted_quota_refuses_fetch_without_calls(lab):
    """TC-703: settings.local.yaml 의 일일 상한이 소진되면 fetch 는 API 호출·DB 변경 없이 한국어 안내와 함께 거부된다. [IT-A04, SEC-002, NFR-003, NFR-007]"""
    lab.channel(2)
    lab.local_settings("quota:\n  daily_limit_units: 3\n")
    lab.login_read()
    first = lab.run("fetch", "--all")
    assert first.code == 0 and "3 / 3 units (남음 0)" in first.out
    rows_before, calls_before = lab.quota_rows(), len(lab.api.calls)
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "[오류 YT-300]" in r.err and "쿼터" in r.err and "태평양 시간 자정" in r.err
    assert lab.quota_rows() == rows_before and len(lab.api.calls) == calls_before
    assert lab.q("SELECT summary FROM run_logs ORDER BY id DESC LIMIT 1")[0][0] == "YT-300"
    assert lab.q("SELECT COUNT(*) c FROM videos")[0]["c"] == 2


def test_quota_exhausted_mid_run_never_exceeds_limit(lab):
    """TC-704: 실행 도중 상한에 닿으면 이미 받은 배치는 저장하고 나머지는 호출하지 않으며 장부 합계가 상한을 넘지 않는다. [IT-A05, SEC-002, FR-015]"""
    lab.channel(120)
    lab.local_settings("quota:\n  daily_limit_units: 5\n")
    lab.login_read()
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "YT-300" in r.err
    assert sum(u for _, u, _ in lab.quota_rows()) == 5 and lab.api.count("videos.list") == 1
    assert lab.q("SELECT COUNT(*) c FROM videos")[0]["c"] == 50


def test_quota_resets_at_pacific_midnight_through_cli(lab):
    """TC-705: 쿼터 하루 경계(태평양 시간 자정)가 CLI 시계 → 쿼터 장부 → 안내 문구까지 일관되게 적용된다. [IT-A06, NFR-003, ADR-006]"""
    lab.channel(1)
    lab.local_settings("quota:\n  daily_limit_units: 3\n")
    lab.login_read()
    assert lab.run("fetch", "--all").code == 0
    lab.clock = FixedClock(datetime(2026, 10, 11, 6, 59, tzinfo=timezone.utc))  # PT 2026-10-10 23:59
    assert lab.run("fetch", "--all").code == 1
    lab.clock = FixedClock(datetime(2026, 10, 11, 7, 0, tzinfo=timezone.utc))   # PT 2026-10-11 00:00
    r = lab.run("fetch", "--all")
    assert r.code == 0 and "태평양 시간 2026-10-11 기준): 3 / 3" in r.out
    assert {x["pt_date"] for x in lab.q("SELECT pt_date FROM quota_usage")} == {"2026-10-10", "2026-10-11"}


def test_warn_ratio_from_config_shows_warning(lab):
    """TC-706: 설정의 warn_ratio 가 쿼터 장부 합계와 만나 fetch 끝에 경고를 낸다. [IT-A07, NFR-003]"""
    lab.channel(1)
    lab.local_settings("quota:\n  daily_limit_units: 4\n  warn_ratio: 0.5\n")
    lab.login_read()
    r = lab.run("fetch", "--all")
    assert r.code == 0 and "[주의] 오늘 쿼터의 50% 이상을 썼습니다" in r.out


def test_read_only_never_touches_write_token(lab):
    """TC-707: 쓰기 토큰 없이 읽기만으로 동작하고, 쓰기 토큰 파일(깨져 있어도)은 열리거나 바뀌지 않으며 쓰기 API 시도는 0건이다. [IT-A08, SEC-001, SEC-015, ADR-004]"""
    lab.channel(2)
    lab.login_read()
    assert lab.run("fetch", "--all").code == 0 and "write_token.json" not in lab.token_files()
    w = lab.tokens / "write_token.json"
    w.write_text("{깨진 파일", encoding="utf-8")
    before = w.read_bytes()
    assert lab.run("fetch", "--all").code == 0 and lab.run("validate", "--all").code == 0
    assert w.read_bytes() == before and lab.api.forbidden == []


def test_write_token_alone_cannot_fetch(lab):
    """TC-708: 쓰기 로그인만 있고 읽기 로그인이 없으면 fetch 는 읽기 로그인을 안내하고 API 객체를 만들지 않는다. [IT-A09, SEC-015, NFR-007]"""
    lab.channel(1)
    assert lab.run("auth", "--write", input_text="쓰기권한").code == 0
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "[오류 YT-400]" in r.err and "auth --read" in r.err
    assert lab.built_with == [] and lab.quota_rows() == [] and lab.api.calls == []


@pytest.mark.parametrize("status,reason", [(401, ""), (403, "forbidden"), (400, "badRequest"), (404, "notFound")])
def test_google_errors_never_leak_secrets(lab, status, reason):
    """TC-709: 구글 오류 응답 본문·URL 의 비밀 값은 화면·로그·DB 어디에도 남지 않고, 상태별 오류 코드/종료 코드가 일관된다. [IT-A10, SEC-008, K-6, NFR-007]"""
    lab.channel(1)
    lab.login_read()
    lab.api.fail("channels.list", http_error(status, reason))
    r = lab.run("fetch", "--all")
    assert r.code == 1
    expect = "YT-400" if status in (401, 403) else "YT-700"
    assert f"[오류 {expect}]" in r.err and lab.q("SELECT summary FROM run_logs ORDER BY id DESC LIMIT 1")[0][0] == expect
    assert_no_secrets(lab.everything_shown(), lab.log_text(), lab.data_bytes().decode("latin-1"))


def test_unexpected_exception_is_masked_everywhere(lab):
    """TC-710: 예상하지 못한 예외에 토큰이 섞여 있어도 화면·로그에는 종류만 남는다. [IT-A10, SEC-008]"""
    lab.channel(1)
    lab.login_read()
    lab.api.fail("channels.list", RuntimeError(f"boom {FAKE_ACCESS} Bearer abc.def {FAKE_REFRESH}"))
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "예상하지 못한 오류" in r.err and "RuntimeError" in r.err
    assert_no_secrets(lab.everything_shown(), lab.log_text(), lab.data_bytes().decode("latin-1"))
    assert lab.q("SELECT summary FROM run_logs ORDER BY id DESC LIMIT 1")[0][0] == "unexpected"


def test_google_quota_exceeded_keeps_charge_and_does_not_retry(lab):
    """TC-711: 구글이 쿼터 초과(403 quotaExceeded)로 답하면 재시도 없이 중단하고 예약한 units 는 장부에 남는다. [IT-A11, ADR-008, SEC-003, SEC-002]"""
    lab.channel(1)
    lab.login_read()
    lab.api.fail("channels.list", http_error(403, "quotaExceeded"))
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "[오류 YT-300]" in r.err and lab.sleeps == []
    assert lab.quota_rows() == [("channels.list", 1, "failed")]
    lab.api.script.clear()
    r = lab.run("fetch", "--video", vid(1))
    assert r.code == 0 and "2 / 6000" in r.out  # 실패한 호출의 차감이 다음 실행에도 이어짐


def test_transient_errors_retry_with_backoff_and_charge_every_attempt(lab):
    """TC-712: 일시 오류(503)는 최대 2회 재시도(1초·2초 백오프)하고 시도마다 쿼터가 차감되며, 3번 모두 실패하면 YT-700 으로 끝난다. [IT-A12, SEC-003, NFR-004, ADR-008]"""
    lab.channel(1)
    lab.login_read()
    lab.api.fail("channels.list", http_error(503), http_error(503))
    assert lab.run("fetch", "--all").code == 0
    assert lab.sleeps == [1.0, 2.0]
    assert lab.quota_rows()[:3] == [("channels.list", 1, "failed"), ("channels.list", 1, "failed"), ("channels.list", 1, "ok")]
    lab.sleeps.clear()
    before = len(lab.quota_rows())
    lab.api.fail("channels.list", http_error(503), http_error(503), http_error(503))
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "[오류 YT-700]" in r.err and lab.sleeps == [1.0, 2.0]
    assert [s for _, _, s in lab.quota_rows()[before:]] == ["failed"] * 3


def test_refetch_is_idempotent_for_videos_and_keeps_candidates(lab):
    """TC-713: fetch 를 다시 실행하면 videos 는 중복 없이 갱신(제목·fetched_at)되고 쿼터만 추가되며, 이미 검증된 후보 기록은 그대로다. [IT-A13, FR-006, FR-005]"""
    ids = lab.channel(3)
    lab.login_read()
    lab.run("fetch", "--all")
    lab.candidate(ids[0])
    assert lab.run("validate", "--all").code == 0
    cands = [tuple(r) for r in lab.q("SELECT id, status, validation_result, updated_at FROM title_candidates")]
    lab.clock.advance(timedelta(hours=2))
    lab.api.items[0]["snippet"]["title"] = "스튜디오에서 바꾼 제목"
    r = lab.run("fetch", "--all")
    assert r.code == 0 and "6 / 6000" in r.out
    rows = {x["video_id"]: x for x in lab.q("SELECT * FROM videos")}
    assert len(rows) == 3 and rows[ids[0]]["title"] == "스튜디오에서 바꾼 제목" and rows[ids[0]]["fetched_at"] == "2026-10-10T14:00:00Z"
    assert rows[ids[1]]["fetched_at"] == "2026-10-10T14:00:00Z"
    assert sum(u for _, u, _ in lab.quota_rows()) == 6
    assert [tuple(r) for r in lab.q("SELECT id, status, validation_result, updated_at FROM title_candidates")] == cands


def test_reversed_order_gives_korean_guidance_and_no_side_effects(lab):
    """TC-714: 순서가 뒤바뀐 실행(로그인 전 fetch, 영상 없이 지표, 옵션 없음, 동시 옵션)은 종류별 종료 코드와 한국어 안내를 내고 쿼터·영상을 건드리지 않는다. [IT-A14, NFR-007, EVT-002]"""
    lab.channel(2)
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "[오류 YT-400]" in r.err and "먼저 `python -m ytitle auth --read`" in r.err
    assert lab.built_with == [] and lab.quota_rows() == [] and lab.q("SELECT COUNT(*) c FROM videos")[0]["c"] == 0
    assert lab.q("SELECT exit_code, summary FROM run_logs")[0][:] == (1, "YT-400")
    lab.login_read()
    r = lab.run("fetch", "--metrics")
    assert r.code == 1 and "YT-500" in r.err and "fetch --all" in r.err
    r = lab.run("fetch")
    assert r.code == 1 and "--all" in r.err and "--metrics" in r.err
    assert lab.run("fetch", "--all", "--video", vid(1)).code == 2
    assert lab.quota_rows() == []
    assert lab.run("fetch", "--all").code == 0  # 올바른 순서로 복구


def test_corrupted_token_recovery_flow(lab):
    """TC-715: 손상된 읽기 토큰 → fetch 가 안내 → auth --revoke → 다시 로그인 → fetch 성공(복구 흐름). [IT-A15, FR-016, NFR-007]"""
    lab.channel(1)
    lab.login_read()
    (lab.tokens / "read_token.json").write_text("[]", encoding="utf-8")
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "손상" in r.err and "auth --revoke" in r.err and lab.api.calls == []
    assert lab.run("auth", "--revoke").code == 0 and lab.token_files() == []
    lab.login_read()
    assert lab.run("fetch", "--all").code == 0


def test_expired_token_refreshed_during_fetch_and_failure_path(lab, monkeypatch):
    """TC-716: 만료된 읽기 토큰은 fetch 중 갱신·재저장되고, 갱신이 거부되면 API 호출·쿼터 없이 재로그인을 안내한다. [IT-A16, FR-016, RISK-012, SEC-008]"""
    lab.channel(1)
    lab.login_read()
    p = lab.tokens / "read_token.json"
    info = json.loads(p.read_text(encoding="utf-8"))
    info["expiry"] = "2020-01-01T00:00:00Z"
    p.write_text(json.dumps(info), encoding="utf-8")

    def ok_refresh(self, request):
        self.token = "ya29.REFRESHEDTOKENVALUE00000000000"
        self.expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", ok_refresh)
    assert lab.run("fetch", "--all").code == 0
    assert "REFRESHEDTOKENVALUE" in p.read_text(encoding="utf-8") and "REFRESHEDTOKENVALUE" not in lab.everything_shown() + lab.log_text()
    info = json.loads(p.read_text(encoding="utf-8"))
    info["expiry"] = "2020-01-01T00:00:00Z"
    p.write_text(json.dumps(info), encoding="utf-8")
    from google.auth.exceptions import RefreshError

    def bad_refresh(self, request):
        raise RefreshError(f"invalid_grant {FAKE_REFRESH}")

    monkeypatch.setattr(Credentials, "refresh", bad_refresh)
    n_calls, n_quota = len(lab.api.calls), len(lab.quota_rows())
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "[오류 YT-400]" in r.err and "다시 로그인" in r.err
    assert len(lab.api.calls) == n_calls and len(lab.quota_rows()) == n_quota
    assert_no_secrets(lab.everything_shown(), lab.log_text())


def test_config_layers_reach_quota_ledger_and_paths(lab):
    """TC-717: 설정 계층(settings.local.yaml 비용, .env/환경 변수 경로)이 쿼터 장부 units 와 DB·로그·토큰 위치까지 전달된다. [IT-A17, ADR-010, FR-015, NFR-003]"""
    lab.channel(1)
    lab.local_settings("quota:\n  read_cost: 2\n")
    (lab.project / ".env").write_text("YT_DATA_DIR=altdata\n", encoding="utf-8")
    lab.login_read()
    assert lab.run("fetch", "--all").code == 0
    db = lab.project / "altdata" / "ytitle.sqlite3"
    assert db.exists() and not (lab.project / "data").exists() and (lab.project / "altdata" / "logs" / "ytitle.log").exists()
    import sqlite3
    c = sqlite3.connect(db)
    assert [r[0] for r in c.execute("SELECT units FROM quota_usage")] == [2, 2, 2]
    c.close()
    other = lab.root / "elsewhere"
    r = lab.run("auth", "--plain", env={"YT_TOKEN_DIR": str(other)})
    assert str(other / "read_token.json") in r.out and "없음" in r.out  # 새 토큰 폴더에는 로그인이 없다


def test_live_section_in_base_settings_is_ignored_with_warning(lab):
    """TC-718: settings.yaml 에 쓴 live 항목은 무시되고 모든 명령이 주의 문구를 낸다(설정 계층 → CLI). [IT-A17, SEC-001, ADR-010]"""
    (lab.project / "config" / "settings.yaml").write_text("live:\n  enable_live: true\n  live_allowlist: [abc123DEF45]\n", encoding="utf-8")
    lab.channel(1)
    for argv in (["auth"], ["validate", "--all"]):
        r = lab.run(*argv)
        assert r.code == 0 and "settings.yaml의 live 항목은 무시했습니다" in r.err


def test_zero_read_cost_is_rejected_cleanly(lab):
    """TC-719: 설정이 허용하는 read_cost: 0 은 쿼터 예약 단계에서 한국어 안내로 거부되고 API 는 호출되지 않는다(관찰 O-1). [IT-A18, NFR-007]"""
    lab.channel(1)
    lab.local_settings("quota:\n  read_cost: 0\n")
    lab.login_read()
    r = lab.run("fetch", "--all")
    assert r.code == 1 and "[오류 YT-500]" in r.err and "read_cost" in r.err and lab.api.calls == []


def test_global_options_position_and_base_dir(lab):
    """TC-720: --base-dir/--plain/--color 가 서브커맨드 앞·뒤 어디에 있어도 같게 적용되고 데이터는 작업 폴더가 아니라 --base-dir 아래에 쌓인다. [IT-A19, EVT-001~003, UX-001]"""
    import os
    lab.channel(2)
    lab.login_read()
    before = lab.run("--plain", "fetch", "--all")
    after = lab.run("fetch", "--all", "--plain")
    assert before.code == after.code == 0 and "- 항목 1" in before.out and "영상 ID: vid00000001" in before.out
    assert "-----" not in before.out and "- 항목 1" in after.out
    assert "\x1b[" not in before.out
    lab.candidate(vid(1))
    assert "\x1b[32m[통과]" in lab.run("validate", "--all", "--color").out  # validate 는 --color 를 따른다
    assert "\x1b[" not in lab.run("fetch", "--all").out
    assert not os.path.exists("data") and lab.db_path.exists()
    r = lab.run("fetch", "--all", "--base-dir", str(lab.project), base_dir_args=False)
    assert r.code == 0


@pytest.mark.xfail(strict=True, reason="DEF-7-001: fetch/auth 가 전역 --color 를 무시한다(badge 호출에 ctx.ui 미전달). 소스 수정 후 이 표시를 제거한다")
@pytest.mark.parametrize("argv", [["fetch", "--all", "--color"], ["auth", "--color"]])
def test_color_option_applies_to_fetch_and_auth(lab, argv):
    """TC-746: 전역 --color 가 fetch·auth 의 상태 배지에도 적용된다(DEF-7-001, 현재 미적용이라 xfail). [IT-A19, DESIGN 4-1 --color]"""
    lab.channel(1)
    lab.login_read()
    assert "\x1b[" in lab.run(*argv).out


def test_terminal_escape_in_titles_is_neutralized(lab):
    """TC-721: 영상 제목·후보 파일에 든 ANSI 이스케이프가 fetch·validate 화면에 그대로 나오지 않는다(DB 에는 원문 보존). [IT-A20, SEC-019]"""
    lab.api.items = [video_item(vid(1), "\x1b[31m빨강\x1b[0m 제목")]
    lab.login_read()
    r = lab.run("fetch", "--all")
    assert r.code == 0 and "\x1b" not in r.out and "빨강" in r.out
    assert "\x1b[31m" in lab.q("SELECT title FROM videos")[0][0]
    p = lab.candidate(vid(1), ["\x1b[31m난방 습관 겨울철 전기요금"], current_title="\x1b[2J현재")
    r = lab.run("validate", "--all")
    assert r.code == 0 and "\x1b" not in r.out


def test_footer_disclaimer_on_all_f_ab_commands(lab):
    """TC-722: 면책 문구가 auth·fetch·validate 의 정상 출력 마지막 줄에 일관되게 붙는다. [IT-A21, POL-002]"""
    lab.channel(1)
    lab.login_read()
    lab.candidate(vid(1))
    for argv in (["auth"], ["fetch", "--all"], ["validate", "--all"]):
        assert lab.run(*argv).out.rstrip().endswith(DISCLAIMER)


# ================================================================= IT-B: 후보 → 검증 → DB


def test_validate_all_records_rows_consistent_with_screen(lab):
    """TC-723: validate --all 이 여러 파일을 검증해 title_candidates 에 상태·사전 해시를 기록하고, 화면의 후보번호가 DB id 와 같으며 쿼터를 쓰지 않는다. [IT-B01, FR-005, SEC-017, EVT-003]"""
    lab.candidate("aaaaaaaaaa1", [GOOD_TITLE, "당뇨 완치 식단"])
    lab.candidate("bbbbbbbbbb2", [GOOD_TITLE])
    r = lab.run("validate", "--all")
    assert r.code == 0 and "[통과] 2건" in r.out and "[차단] 1건" in r.out
    rows = lab.q("SELECT * FROM title_candidates ORDER BY id")
    assert [(x["video_id"], x["status"], x["validation_result"]) for x in rows] == [
        ("aaaaaaaaaa1", "filtered", "pass"), ("aaaaaaaaaa1", "blocked", "block"), ("bbbbbbbbbb2", "filtered", "pass")]
    printed_hash = r.out.split("해시 ")[1].split(")")[0]
    assert {x["dictionary_hash"] for x in rows} == {printed_hash}
    for x in rows:
        assert f"{x['id']}  " in r.out
    assert lab.quota_rows() == [] and lab.q("SELECT mode, summary FROM run_logs")[0][:] == ("dry_run", "ok")


def test_validate_rerun_idempotent_and_changed_file_adds_rows(lab):
    """TC-724: 같은 파일 재검증은 id 가 유지되고 중복이 없으며, 내용이 바뀐 파일은 새 행으로 이력이 남는다. [IT-B02, FR-005]"""
    lab.candidate("aaaaaaaaaa1")
    ids = []
    for _ in range(2):
        assert lab.run("validate", "--all").code == 0
        ids.append([x["id"] for x in lab.q("SELECT id FROM title_candidates")])
    assert ids[0] == ids[1] and len(ids[0]) == 1
    lab.candidate("aaaaaaaaaa1", summary=SUMMARY + " 추가 설명입니다")
    assert lab.run("validate", "--all").code == 0
    assert len(lab.q("SELECT id FROM title_candidates")) == 2


def test_description_from_fetch_feeds_validation(lab):
    """TC-725: fetch 가 저장한 영상 설명이 validate 의 일치율 계산 입력이 되고, 같은 후보 행이 제자리에서 차단→통과 계열로 갱신된다. 후보 파일의 description_excerpt 가 있으면 DB 보다 우선한다. [IT-B03, FR-004, WU-2→WU-3 DB 계약]"""
    ids = lab.channel(1)
    lab.login_read()
    kw = dict(summary="생활 정보 영상입니다", evidence="생활 정보 영상입니다")
    lab.candidate(ids[0], ["겨울철 전기요금 줄이는 난방 습관"], **kw)
    r = lab.run("validate", "--all")
    assert "설명 미사용" in r.out
    first = lab.q("SELECT id, validation_result, status FROM title_candidates")
    assert [x["validation_result"] for x in first] == ["block"]
    lab.run("fetch", "--all")
    r = lab.run("validate", "--all")
    assert "영상 설명: 사용함" in r.out
    after = lab.q("SELECT id, validation_result, status FROM title_candidates")
    assert len(after) == 1 and after[0]["id"] == first[0]["id"] and after[0]["validation_result"] != "block" and after[0]["status"] == "filtered"
    lab.candidate(ids[0], ["겨울철 전기요금 줄이는 난방 습관"], description_excerpt="전혀 다른 내용의 설명입니다", **kw)
    r = lab.run("validate", "--all")
    assert "영상 설명: 사용함" in r.out
    assert [x["validation_result"] for x in lab.q("SELECT validation_result FROM title_candidates ORDER BY id")][-1] == "block"


def test_db_description_excerpt_is_cut_at_500_chars(lab):
    """TC-726: DB 에 저장되는 설명 발췌는 500자까지이며, 그 뒤쪽에만 있는 낱말은 검증 일치율에 쓰이지 않는다. [IT-B04, DESIGN 3-1 videos.description_excerpt]"""
    ids = lab.channel(1, )
    lab.api.items[0]["snippet"]["description"] = "가" * 520 + " 겨울철 전기요금 난방 습관"
    lab.login_read()
    lab.run("fetch", "--all")
    row = lab.q("SELECT description_excerpt, snippet_json FROM videos")[0]
    assert len(row["description_excerpt"]) == 500
    assert json.loads(row["snippet_json"])["description"].endswith("난방 습관")  # 전체는 snippet_json 에 보존
    lab.candidate(ids[0], ["겨울철 전기요금 줄이는 난방 습관"], summary="생활 정보 영상입니다", evidence="생활 정보 영상입니다")
    r = lab.run("validate", "--all")
    assert "영상 설명: 사용함" in r.out and lab.q("SELECT validation_result FROM title_candidates")[0][0] == "block"


def _good(d):
    return json.dumps(d, ensure_ascii=False)


@pytest.mark.parametrize("case", ["bad_json", "not_object", "non_utf8", "oversize", "id_mismatch", "empty_candidates", "too_many", "bad_topic"])
def test_corrupted_candidate_files_fail_cleanly(lab, case):
    """TC-727: 손상·악성 후보 파일은 DB 기록 없이 YT-500 과 한국어 안내, 종료 코드 1 로 끝난다. [IT-B05, SEC-011, SEC-016, NFR-007]"""
    base = {"video_id": "aaaaaaaaaa1", "current_title": "현재", "topic": "life", "summary": SUMMARY, "source": "human", "candidates": [{"title": GOOD_TITLE, "evidence": SUMMARY}]}
    p = lab.project / "candidates" / "aaaaaaaaaa1.json"
    if case == "bad_json":
        p.write_text("{\"video_id\": ", encoding="utf-8")
    elif case == "not_object":
        p.write_text("[1,2]", encoding="utf-8")
    elif case == "non_utf8":
        p.write_bytes(_good(base).encode("cp949"))
    elif case == "oversize":
        p.write_text(_good({**base, "summary": "가" * 300000}), encoding="utf-8")
    elif case == "id_mismatch":
        p.write_text(_good({**base, "video_id": "bbbbbbbbbb2"}), encoding="utf-8")
    elif case == "empty_candidates":
        p.write_text(_good({**base, "candidates": []}), encoding="utf-8")
    elif case == "too_many":
        p.write_text(_good({**base, "candidates": base["candidates"] * 21}), encoding="utf-8")
    else:
        p.write_text(_good({**base, "topic": "sports"}), encoding="utf-8")
    r = lab.run("validate", "--all")
    assert r.code == 1 and "[오류 YT-500]" in r.err and "다음에" not in "" and r.err.count("\n") >= 2
    assert lab.q("SELECT COUNT(*) c FROM title_candidates")[0]["c"] == 0
    assert lab.q("SELECT exit_code, summary FROM run_logs")[0][:] == (1, "YT-500")


def test_file_argument_path_attacks_rejected(lab, tmp_path):
    """TC-728: --file 이 candidates 밖(상위 경로·절대 경로·심볼릭 링크)을 가리키거나 파일이 없으면 모두 거부되고 DB 는 비어 있다. [IT-B05, SEC-011]"""
    outside = lab.root / "evil"
    outside.mkdir()
    (outside / "aaaaaaaaaa1.json").write_text(_good({"video_id": "aaaaaaaaaa1"}), encoding="utf-8")
    lab.candidate("bbbbbbbbbb2")
    attempts = ["../evil/aaaaaaaaaa1.json", str(outside / "aaaaaaaaaa1.json"), "candidates/ccccccccccc.json", "candidates/../evil/aaaaaaaaaa1.json"]
    link = lab.project / "candidates" / "dddddddddd4.json"
    try:
        link.symlink_to(outside / "aaaaaaaaaa1.json")
        attempts.append("candidates/dddddddddd4.json")
    except OSError:
        pass
    for a in attempts:
        r = lab.run("validate", "--file", a)
        assert r.code == 1 and "YT-500" in r.err, a
    assert lab.q("SELECT COUNT(*) c FROM title_candidates")[0]["c"] == 0


def test_validate_requires_a_target(lab):
    """TC-729: 대상 없이 validate 를 실행하면 종료 코드 1 과 사용법 안내이고, 후보 폴더가 비어 있으면 안내 후 0 으로 끝난다. [IT-B05, NFR-007]"""
    r = lab.run("validate")
    assert r.code == 1 and "validate --all" in r.err
    r = lab.run("validate", "--all")
    assert r.code == 0 and "검사할 후보 파일이 없습니다" in r.out
    assert lab.run("validate", "--all", "--file", "x.json").code == 2


def test_batch_with_one_broken_file_keeps_earlier_results(lab):
    """TC-730: --all 중 파일 하나가 손상되면 실행은 종료 코드 1 로 멈추고, 그 앞 파일의 결과는 이미 저장되어 있으며 뒤 파일은 처리되지 않는다(관찰 O-2). [IT-B06, SEC-011]"""
    lab.candidate("aaaaaaaaaa1")
    (lab.project / "candidates" / "bbbbbbbbbb2.json").write_text("깨짐", encoding="utf-8")
    lab.candidate("cccccccccc3")
    r = lab.run("validate", "--all")
    assert r.code == 1 and "bbbbbbbbbb2.json" in r.err or "JSON" in r.err
    assert {x["video_id"] for x in lab.q("SELECT video_id FROM title_candidates")} == {"aaaaaaaaaa1"}


def test_validation_thresholds_from_local_settings_and_invalid_config(lab):
    """TC-731: settings.local.yaml 의 검증 임계값이 validate 판정에 반영되고, 잘못된 설정은 모든 명령이 YT-100/종료 코드 1 로 막는다. [IT-B07, ADR-010, NFR-007]"""
    lab.candidate("aaaaaaaaaa1", ["겨울철 전기요금 줄이는 난방 습관 바꾸기 요령 소개"])
    lab.local_settings("validation:\n  key_phrase_chars: 5\n  recommended_max_chars: 10\n  hard_max_chars: 12\n")
    r = lab.run("validate", "--all")
    assert r.code == 0 and "[차단] 1건" in r.out
    row = lab.q("SELECT validation_result, validation_reasons_json FROM title_candidates")[0]
    assert row[0] == "block" and "LEN_HARD" in row[1] and "상한(12자)" in row[1]
    lab.local_settings("validation:\n  warn_match_ratio: 0.1\n  block_match_ratio: 0.9\n")
    n = len(lab.q("SELECT id FROM title_candidates"))
    for argv in (["validate", "--all"], ["fetch", "--all"], ["auth"]):
        r = lab.run(*argv)
        assert r.code == 1 and "[오류 YT-100]" in r.err, argv
    assert len(lab.q("SELECT id FROM title_candidates")) == n
    lab.local_settings("quota:\n  daily_limit_units: abc\n")
    assert lab.run("validate", "--all").code == 1


def test_dictionary_change_updates_hash_and_verdict_in_place(lab):
    """TC-732: 금칙어 사전을 고치면 같은 후보 행이 새 사전 해시와 새 판정으로 갱신되고, 깨진·없는 사전은 YT-100 으로 막힌다. [IT-B08, SEC-017, FR-003]"""
    lab.candidate("aaaaaaaaaa1")
    lab.run("validate", "--all")
    old = lab.q("SELECT id, dictionary_hash, validation_result FROM title_candidates")[0]
    assert old["validation_result"] == "pass"
    d = lab.project / "config" / "banned_terms.yaml"
    d.write_text(d.read_text(encoding="utf-8").replace("types:\n", "types:\n  custom:\n    severity: block\n    terms: [\"난방 습관\"]\n", 1), encoding="utf-8")
    assert lab.run("validate", "--all").code == 0
    new = lab.q("SELECT id, dictionary_hash, validation_result, status FROM title_candidates")
    assert len(new) == 1 and new[0]["id"] == old["id"] and new[0]["dictionary_hash"] != old["dictionary_hash"]
    assert new[0]["validation_result"] == "block" and new[0]["status"] == "blocked"
    d.write_text("types: [깨짐", encoding="utf-8")
    r = lab.run("validate", "--all")
    assert r.code == 1 and "YT-100" in r.err
    d.unlink()
    assert lab.run("validate", "--all").code == 1


def test_downstream_states_are_not_overwritten_by_revalidation(lab):
    """TC-733: 승인 이후 단계(approved)로 넘어간 후보 행은 재검증이 덮어쓰지 않고, 내용이 바뀐 파일은 새 행(filtered)으로 추가된다. [IT-B09, 설계 3-2 상태 머신]"""
    lab.candidate("aaaaaaaaaa1")
    lab.run("validate", "--all")
    import sqlite3
    c = sqlite3.connect(lab.db_path)
    c.execute("UPDATE title_candidates SET status='approved'")
    c.commit()
    c.close()
    assert lab.run("validate", "--all").code == 0
    rows = lab.q("SELECT status, validation_result FROM title_candidates")
    assert [tuple(r) for r in rows] == [("approved", "pass")]
    lab.candidate("aaaaaaaaaa1", summary=SUMMARY + " 바뀜")
    lab.run("validate", "--all")
    assert sorted(r["status"] for r in lab.q("SELECT status FROM title_candidates")) == ["approved", "filtered"]


def test_relative_file_resolved_against_base_dir_not_cwd(lab):
    """TC-734: --file 의 상대 경로는 현재 폴더가 아니라 --base-dir 기준으로 해석되고 절대 경로도 같은 결과를 낸다. [IT-B10, SEC-011, UX-001]"""
    p = lab.candidate("aaaaaaaaaa1")
    assert lab.run("validate", "--file", "candidates/aaaaaaaaaa1.json").code == 0
    assert lab.run("validate", "--file", str(p)).code == 0
    assert len(lab.q("SELECT id FROM title_candidates")) == 1


def test_validate_100_candidates_within_5_seconds_via_cli(lab):
    """TC-735: 후보 100건(5파일×20개)을 CLI 로 검증하는 데 5초가 걸리지 않는다. [IT-B11, NFR-005]"""
    for i in range(5):
        lab.candidate(f"perf{i:07d}", [f"겨울철 전기요금 줄이는 난방 습관 {j}" for j in range(20)])
    t = time.perf_counter()
    r = lab.run("validate", "--all")
    dt = time.perf_counter() - t
    assert r.code == 0 and len(lab.q("SELECT id FROM title_candidates")) == 100 and dt < 5.0, dt


def test_validate_plain_output(lab):
    """TC-736: validate --plain 은 표 대신 `항목: 값` 목록을 내고 후보번호가 DB id 와 같다. [IT-B12, UX-001, EVT-003]"""
    lab.candidate("aaaaaaaaaa1")
    r = lab.run("validate", "--all", "--plain")
    cid = lab.q("SELECT id FROM title_candidates")[0]["id"]
    assert r.code == 0 and f"후보번호: {cid}" in r.out and "-----" not in r.out


def test_strict_mode_from_missing_topic_applies_to_warnings(lab):
    """TC-737: topic 이 없는 후보 파일은 엄격 모드가 되어 경고급 사유도 차단으로 기록된다(설정 → 검증 → DB). [IT-B13, POL-001]"""
    lab.candidate("aaaaaaaaaa1", ["겨울철 전기요금 줄이는 난방 습관!!"], topic=None)
    r = lab.run("validate", "--all")
    row = lab.q("SELECT strict_mode, validation_result, topic FROM title_candidates")[0]
    assert r.code == 0 and "엄격 모드" in r.out and tuple(row) == (1, "block", None)


# ================================================================= IT-X: F-A → F-B 전체 흐름


def _master_flow(lab, n=5):
    ids = lab.channel(n)
    lab.login_read()
    assert lab.run("fetch", "--all").code == 0
    stored = [r["video_id"] for r in lab.q("SELECT video_id FROM videos ORDER BY video_id")]
    for v in stored[:2]:
        lab.candidate(v, [GOOD_TITLE, "당뇨 완치 식단"])
    assert lab.run("validate", "--all").code == 0
    return ids


def test_master_end_to_end_read_only_flow(lab):
    """TC-740: 로그인 → 전체 조회 → DB 의 영상 ID 로 후보 작성 → 검증까지의 전체 흐름이 실행 기록·쿼터·후보 DB 에서 일관된다. [IT-X01, FR-006, FR-005, FR-015, FR-016, FR-020]"""
    _master_flow(lab)
    runs = lab.q("SELECT command, mode, exit_code, summary FROM run_logs ORDER BY id")
    assert [tuple(r) for r in runs] == [("auth", "dry_run", 0, "ok"), ("fetch", "dry_run", 0, "ok"), ("validate", "dry_run", 0, "ok")]
    assert lab.q("SELECT COUNT(*) c FROM videos")[0]["c"] == 5
    assert lab.q("SELECT COUNT(DISTINCT video_id) c FROM title_candidates")[0]["c"] == 2
    assert {r["video_id"] for r in lab.q("SELECT video_id FROM title_candidates")} <= {r["video_id"] for r in lab.q("SELECT video_id FROM videos")}
    assert sum(u for _, u, _ in lab.quota_rows()) == 3 and lab.token_files() == ["read_token.json"]


def test_whole_flow_makes_no_write_call_and_no_network(lab, no_network):
    """TC-741: 전체 흐름에서 쓰기 API 시도·쓰기 토큰 생성·네트워크 접근이 0건이다. [IT-X02, SEC-001, SEC-007, K-2]"""
    _master_flow(lab)
    assert lab.api.forbidden == [] and {k for k, _ in lab.api.calls} <= {"channels.list", "playlistItems.list", "videos.list", "reports.query"}
    assert not (lab.tokens / "write_token.json").exists() and no_network == []
    assert all(set(c.scopes) == set(auth.READ_SCOPES) for c in lab.built_with)


def test_whole_flow_leaks_no_secrets(lab):
    """TC-742: 전체 흐름의 화면·로그·DB 파일(바이트)·후보 폴더에 토큰/클라이언트 비밀이 없다(토큰 폴더만 예외). [IT-X03, SEC-008, K-6]"""
    _master_flow(lab)
    blob = lab.data_bytes().decode("latin-1") + lab.everything_shown() + lab.log_text()
    for p in (lab.project / "candidates").glob("*"):
        blob += p.read_text(encoding="utf-8")
    assert_no_secrets(blob)
    assert FAKE_ACCESS in (lab.tokens / "read_token.json").read_text(encoding="utf-8")  # 토큰은 토큰 폴더에만 있다
    assert lab.tokens.resolve() not in lab.project.resolve().parents and lab.project.resolve() not in lab.tokens.resolve().parents


def test_keyboard_interrupt_leaves_consistent_ledger(lab):
    """TC-743: 조회 도중 중단(Ctrl+C)되면 종료 코드 130 이고 예약된 쿼터는 failed 로 확정되어 'reserved' 로 남지 않으며 실행 기록에 interrupted 가 남는다. [IT-X04, ADR-008, 규칙 K]"""
    lab.channel(3)
    lab.login_read()
    lab.api.fail("playlistItems.list", KeyboardInterrupt())
    r = lab.run("fetch", "--all")
    assert r.code == 130 and "중단" in r.err
    statuses = [s for _, _, s in lab.quota_rows()]
    assert statuses == ["ok", "failed"] and "reserved" not in statuses
    assert lab.q("SELECT exit_code, summary FROM run_logs ORDER BY id DESC LIMIT 1")[0][:] == (130, "interrupted")


def test_data_dir_blocked_by_file_fails_with_korean_message(lab):
    """TC-744: data 경로가 이미 파일이면 트레이스백 없이 한국어 오류와 종료 코드 1 로 끝난다. [IT-X05, NFR-007]"""
    (lab.project / "data").write_text("파일", encoding="utf-8")
    r = lab.run("validate", "--all")
    assert r.code == 1 and "Traceback" not in r.err and "오류" in r.err


def test_korean_project_path_full_flow(tmp_path, monkeypatch):
    """TC-745: 한글·공백이 든 프로젝트 경로에서도 로그인 → 조회 → 검증 전체 흐름이 동작한다. [IT-X06, NFR-002]"""
    lab = Lab(tmp_path / "한글 폴더 테스트", monkeypatch) if (tmp_path / "한글 폴더 테스트").mkdir() is None else None
    _master_flow(lab, 3)
    assert "한글 폴더 테스트" in str(lab.db_path) and lab.db_path.exists()
    assert "당뇨 완치 식단" in lab.history[-1].out
