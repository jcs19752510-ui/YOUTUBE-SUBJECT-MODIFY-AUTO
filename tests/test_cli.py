import importlib
import sys
import textwrap

from ytitle import cli, commands
from ytitle.errors import SafetyGateError


def run(project, argv, streams, **kw):
    return cli.main(["--base-dir", str(project)] + argv, out=streams.out, err=streams.err, env={}, **kw)


def test_help_lists_registered_commands_and_disclaimer(project, streams):
    """TC-055: --help가 등록된 명령(purge)과 '기본은 모의 실행' 안내, 면책 문구를 보여 준다. [FR-017, SCR-001, POL-002]"""
    code = run(project, ["--help"], streams)
    out = streams.out.getvalue()
    assert code == 0 and "purge" in out and "모의 실행" in out and "법률 자문이 아니며" in out


def test_no_arguments_shows_help_and_exits_zero(project, streams):
    """TC-056: 인자 없이 실행하면 도움말을 보여 주고 정상 종료한다(초보자 친화). [SCR-001]"""
    assert cli.main([], out=streams.out, err=streams.err) == 0
    assert "사용할 수 있는 명령" in streams.out.getvalue()


def test_unknown_command_exit_code_2(project, streams):
    """TC-057: 알 수 없는 명령은 종료 코드 2(사용법 오류)이다. [FR-017]"""
    assert run(project, ["nope"], streams) == 2


def test_live_flag_not_accepted_by_purge(project, streams):
    """TC-058: 쓰기 명령이 아닌 purge에는 --live 옵션이 존재하지 않는다(기본 dry-run 보장). [SEC-001]"""
    assert run(project, ["purge", "--before", "2026-01-01", "--live"], streams) == 2


def test_commands_are_auto_discovered(project, streams, tmp_path, monkeypatch):
    """TC-059: commands 폴더에 파일만 추가하면 --help에 자동으로 나타난다(병렬 개발 충돌 방지). [ADR-003]"""
    extra = tmp_path / "extra_cmds"
    extra.mkdir()
    (extra / "hello.py").write_text(textwrap.dedent('''
        def register(sub, parent):
            p = sub.add_parser("hello", parents=[parent], help="테스트용 명령")
            p.set_defaults(func=lambda args, ctx: 0)
    '''), encoding="utf-8")
    monkeypatch.setattr(commands, "__path__", list(commands.__path__) + [str(extra)])
    importlib.invalidate_caches()
    code = run(project, ["--help"], streams)
    sys.modules.pop("ytitle.commands.hello", None)
    assert code == 0 and "hello" in streams.out.getvalue()


def test_ytierror_is_shown_in_korean_and_exit_code_mapped(project, streams, tmp_path, monkeypatch):
    """TC-060: 안전 게이트 오류는 한국어 오류 블록으로 출력되고 종료 코드 3이 된다. [SEC-001, NFR-007]"""
    extra = tmp_path / "gate_cmds"
    extra.mkdir()
    (extra / "gate.py").write_text(textwrap.dedent('''
        from ytitle.errors import SafetyGateError
        def _run(args, ctx):
            raise SafetyGateError("조건이 부족해 중단했습니다.", "settings.local.yaml을 확인하세요.")
        def register(sub, parent):
            p = sub.add_parser("gate", parents=[parent], help="x")
            p.set_defaults(func=_run)
    '''), encoding="utf-8")
    monkeypatch.setattr(commands, "__path__", list(commands.__path__) + [str(extra)])
    importlib.invalidate_caches()
    code = run(project, ["gate"], streams)
    sys.modules.pop("ytitle.commands.gate", None)
    err = streams.err.getvalue()
    assert code == 3 and "YT-600" in err and "다음에 할 일" in err
    assert SafetyGateError.exit_code == 3


def test_unexpected_exception_is_masked_and_logged(project, streams, tmp_path, monkeypatch):
    """TC-061: 예상 못한 오류도 비밀 없이 한국어로 안내되고 로그에 남는다. [SEC-008, NFR-007]"""
    extra = tmp_path / "boom_cmds"
    extra.mkdir()
    (extra / "boom.py").write_text(textwrap.dedent('''
        def _run(args, ctx):
            raise RuntimeError("Bearer supersecret.token 노출")
        def register(sub, parent):
            sub.add_parser("boom", parents=[parent], help="x").set_defaults(func=_run)
    '''), encoding="utf-8")
    monkeypatch.setattr(commands, "__path__", list(commands.__path__) + [str(extra)])
    importlib.invalidate_caches()
    code = run(project, ["boom"], streams)
    sys.modules.pop("ytitle.commands.boom", None)
    assert code == 1 and "예상하지 못한 오류" in streams.err.getvalue()
    assert "supersecret" not in streams.err.getvalue()
    log = (project / "data" / "logs" / "ytitle.log").read_text(encoding="utf-8")
    assert "supersecret" not in log and "예상하지 못한 오류" in log


def test_run_is_recorded_in_run_logs(project, streams):
    """TC-062: 명령 실행이 run_logs에 시작·종료 시각과 종료 코드로 기록된다. [FR-020]"""
    import sqlite3

    run(project, ["purge", "--before", "2026-01-01"], streams)
    c = sqlite3.connect(project / "data" / "ytitle.sqlite3")
    row = c.execute("SELECT command, mode, exit_code, ended_at FROM run_logs").fetchone()
    c.close()
    assert row[0] == "purge" and row[1] == "dry_run" and row[2] == 0 and row[3]


def test_invalid_settings_stop_with_config_error(project, streams):
    """TC-063: 설정 오류는 명령 실행 전에 한국어 안내와 함께 중단된다. [NFR-007]"""
    (project / "config" / "settings.yaml").write_text("quota:\n  daily_limit_units: abc\n", encoding="utf-8")
    assert run(project, ["purge", "--before", "2026-01-01"], streams) == 1
    assert "YT-100" in streams.err.getvalue()


def test_settings_warning_is_printed(project, streams):
    """TC-064: settings.yaml의 live 값이 무시되면 [주의] 경고가 화면에 나온다. [SEC-001]"""
    (project / "config" / "settings.yaml").write_text("live:\n  enable_live: true\n", encoding="utf-8")
    run(project, ["purge", "--before", "2026-01-01"], streams)
    assert "[주의]" in streams.err.getvalue()


def test_plain_option_accepted_after_subcommand(project, streams):
    """TC-065: 전역 옵션 --plain은 명령 뒤에 써도 적용된다. [FR-017, SCR-002]"""
    assert run(project, ["purge", "--before", "2026-01-01", "--plain"], streams) == 0


def test_global_options_honored_before_and_after_subcommand(project, streams, tmp_path):
    """TC-072: --base-dir/--plain이 명령 앞·뒤 어느 위치에서도 적용되고, 현재 폴더에는 아무것도 만들지 않는다(회귀 방지). [FR-017]"""
    import os

    other = tmp_path / "other"
    (other / "config").mkdir(parents=True)
    for argv in (["--base-dir", str(other), "purge", "--before", "2026-01-01"], ["purge", "--before", "2026-01-01", "--base-dir", str(other)]):
        assert cli.main(argv, out=streams.out, err=streams.err, env={}) == 0
    assert (other / "data" / "ytitle.sqlite3").exists()
    assert not os.path.exists("data")
    streams.out.truncate(0), streams.out.seek(0)
    assert cli.main(["--plain", "purge", "--before", "2026-01-01", "--base-dir", str(other)], out=streams.out, err=streams.err, env={}) == 0
    assert "----" not in streams.out.getvalue()
