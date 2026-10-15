"""CLI 진입점: 서브커맨드 자동 탐색, 오류 처리, 실행 기록(FR-017, FR-020)."""
from __future__ import annotations

import argparse
import contextlib
import importlib
import logging
import pkgutil
import sys
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from typing import Callable, Mapping, TextIO

from youtube_title import __version__, commands as commands_pkg
from youtube_title import db as dbmod
from youtube_title.config import Settings, load_settings
from youtube_title.errors import YtError
from youtube_title.logging_setup import mask, setup_logging
from youtube_title.platform_utils import ensure_utf8_console
from youtube_title.timeutil import SystemClock
from youtube_title.ui import UiOptions, confirm_by_typing, error_block, footer


@dataclass
class AppContext:
    settings: Settings
    ui: UiOptions
    clock: object
    run_id: str
    out: TextIO
    err: TextIO
    input_fn: Callable[[str], str]
    logger: logging.Logger
    _conn: object = field(default=None, repr=False)

    @property
    def conn(self):
        if self._conn is None:
            self._conn = dbmod.connect(self.settings.db_path)
            dbmod.migrate(self._conn)
        return self._conn

    def say(self, text: str = "") -> None:
        self.out.write(text + "\n")

    def warn(self, text: str) -> None:
        self.err.write(text + "\n")

    def confirm(self, expected: str) -> bool:
        return confirm_by_typing(expected, input_fn=self.input_fn, output_fn=self.say)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


def common_parent() -> argparse.ArgumentParser:
    """모든 서브커맨드가 공유하는 전역 옵션. 서브커맨드 뒤에 써도 된다."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--plain", action="store_true", default=argparse.SUPPRESS, help="표 대신 한 줄씩 `항목: 값` 목록으로 출력(스크린리더 친화)")
    p.add_argument("--color", action="store_true", default=argparse.SUPPRESS, help="상태 표시에 색을 사용(기본은 끔)")
    p.add_argument("--base-dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return p


def build_parser() -> argparse.ArgumentParser:
    # 주의: argparse의 parents=는 옵션 객체를 복사하지 않고 공유한다. 루트와 서브커맨드가 같은 객체를 쓰면
    # 루트의 set_defaults가 서브커맨드의 SUPPRESS 기본값을 덮어써 전역 옵션이 무시된다. 따라서 각각 따로 만든다.
    parent = common_parent()
    parser = argparse.ArgumentParser(
        prog="youtube_title",
        parents=[common_parent()],
        description=(
            "'시니어 생활팁' 유튜브 제목을 안전하게 검증·반영·기록·롤백하는 도구입니다.\n"
            "처음이면 docs/yt/03_manual_setup.md부터 따라 하세요. 모든 명령의 기본은 모의 실행(dry-run)이며,\n"
            "실제 수정은 승인 조건을 모두 갖춘 `apply --live`에서만 일어납니다."
        ),
        epilog=footer(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"유튜브 제목 {__version__}")
    parser.set_defaults(plain=False, color=False, base_dir=None)
    sub = parser.add_subparsers(dest="command", metavar="<명령>", title="사용할 수 있는 명령")
    for info in pkgutil.iter_modules(commands_pkg.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"youtube_title.commands.{info.name}")
        if hasattr(module, "register"):
            module.register(sub, parent)
    return parser


def project_root(module_file: str | None = None) -> Path:
    """기본 기준 폴더. 소스 폴더에서 실행 중이면 프로젝트 루트(`pyproject.toml`과 `src/youtube_title/cli.py`가 있는 곳)로 고정한다.
    어느 폴더에서 실행해도 `data/`·`config/` 등을 같은 자리에 쓰게 하기 위해서다. 설치형(소스 트리 밖)이면 현재 폴더를 쓴다."""
    here = Path(module_file or __file__).resolve()
    root = here.parents[2]
    if (root / "pyproject.toml").is_file() and (root / "src" / "youtube_title" / "cli.py").is_file():
        return root
    return Path.cwd()


def main(
    argv: list[str] | None = None,
    *,
    out: TextIO | None = None,
    err: TextIO | None = None,
    input_fn: Callable[[str], str] = input,
    clock=None,
    env: Mapping[str, str] | None = None,
) -> int:
    if out is None and err is None:
        ensure_utf8_console()
    out = out or sys.stdout
    err = err or sys.stderr
    parser = build_parser()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    if not getattr(args, "command", None):
        parser.print_help(out)
        return 0

    base_dir = Path(args.base_dir) if args.base_dir else project_root()
    run_id = uuid.uuid4().hex[:12]
    clock = clock or SystemClock()
    ui_opts = UiOptions(plain=args.plain, color=args.color)
    ctx = None
    code, summary = 1, "unknown"
    try:
        settings = load_settings(base_dir, env)
        logger = setup_logging(settings.data_dir, run_id)
        ctx = AppContext(settings, ui_opts, clock, run_id, out, err, input_fn, logger)
        for w in settings.warnings:
            ctx.warn(f"[주의] {w}")
        mode = "live" if getattr(args, "live", False) else "dry_run"
        dbmod.start_run(ctx.conn, run_id, args.command, mode, clock.now())
        logger.info("명령 시작: %s (%s)", args.command, mode)
        code = args.func(args, ctx)
        summary = "ok"
    except YtError as exc:
        err.write(error_block(exc) + "\n")
        code, summary = exc.exit_code, f"{exc.code}"
        if ctx:
            ctx.logger.warning("오류 %s: %s", exc.code, exc.message)
    except KeyboardInterrupt:
        err.write("사용자가 중단했습니다.\n")
        code, summary = 130, "interrupted"
    except Exception as exc:  # 예상하지 못한 오류도 비밀을 가리고 한국어로 안내한다
        err.write(error_block(YtError(f"예상하지 못한 오류가 생겼습니다: {mask(type(exc).__name__)}", "로그(data/logs/youtube-title.log)를 확인하고 내용을 알려 주세요.")) + "\n")
        code, summary = 1, "unexpected"
        if ctx:
            ctx.logger.exception("예상하지 못한 오류")
    finally:
        if ctx is not None:
            try:
                dbmod.finish_run(ctx.conn, run_id, code, summary, clock.now())
            except YtError as exc:
                ctx.logger.warning("실행 기록을 마무리하지 못했습니다: %s", exc.message)
            ctx.close()
    return code
