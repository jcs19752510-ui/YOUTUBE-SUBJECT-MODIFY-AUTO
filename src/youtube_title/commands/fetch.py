"""fetch: 영상 정보와 성과 지표를 읽기 전용으로 조회해 저장(EVT-002, SCR-007, FR-006, FR-007)."""
from __future__ import annotations

import argparse
import re
from datetime import timedelta

from youtube_title import auth as authmod
from youtube_title.errors import InputError
from youtube_title.quota import QuotaManager
from youtube_title.timeutil import pt_date
from youtube_title.ui import badge, footer, render_table, title_line
from youtube_title.youtube_read import PHASES, YouTubeReader, build_services

NAME = "fetch"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
LIST_PREVIEW = 20
_PRIVACY = (("public", "공개"), ("private", "비공개"), ("unlisted", "일부 공개"))


def _days(value: str) -> int:
    try:
        n = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("숫자로 입력하세요(1~365).") from None
    if not 1 <= n <= 365:
        raise argparse.ArgumentTypeError("1에서 365 사이여야 합니다.")
    return n


def register(sub, parent):
    p = sub.add_parser(
        "fetch",
        parents=[parent],
        help="내 채널 영상과 성과 지표 조회(읽기 전용)",
        description="내 채널의 영상 정보와 성과 지표를 읽기 권한으로만 조회해 이 PC의 DB에 저장합니다. 유튜브의 영상은 바꾸지 않습니다.",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="채널의 모든 영상을 조회")
    g.add_argument("--video", action="append", metavar="ID", help="영상 ID(여러 번 쓸 수 있음)")
    p.add_argument("--metrics", action="store_true", help="성과 지표도 수집(단독이면 이미 저장된 영상이 대상)")
    p.add_argument("--phase", choices=PHASES, default="periodic", help="지표 단계: before(변경 전), after(변경 후), periodic(정기). 기본 periodic")
    p.add_argument("--days", type=_days, default=28, metavar="N", help="지표 기간 일수(1~365, 기본 28)")
    p.set_defaults(func=run)


def make_reader(ctx) -> YouTubeReader:
    """읽기 토큰으로 서비스를 만든다. 테스트에서는 이 함수를 교체한다."""
    creds = authmod.load_credentials("read", ctx.settings)
    youtube, analytics = build_services(creds)
    quota = QuotaManager(ctx.conn, ctx.settings, ctx.clock)
    return YouTubeReader(youtube, analytics, quota, ctx.conn, ctx.settings, ctx.clock, run_id=ctx.run_id)


def _validate(args) -> None:
    if not (args.all or args.video or args.metrics):
        raise InputError("무엇을 조회할지 정하지 않았습니다.", "`--all`(전체 영상), `--video ID`(특정 영상), `--metrics`(성과 지표) 중 하나를 쓰세요. 자세한 설명: `python -m youtube_title fetch --help`")
    for vid in args.video or []:
        if not VIDEO_ID_RE.match(vid):
            raise InputError("영상 ID 형식이 올바르지 않습니다(영문·숫자·-·_ 11자).", "유튜브 주소의 v= 뒤 11글자를 그대로 입력하세요.")


def run(args, ctx) -> int:
    _validate(args)
    ctx.say(title_line("fetch", False))
    reader = make_reader(ctx)

    fetched = None
    ids: list[str] = []
    if args.all or args.video:
        requested = reader.list_channel_video_ids() if args.all else list(args.video)
        fetched = reader.fetch_videos(requested)
        ids = [r["video_id"] for r in fetched.rows]
        _print_videos(ctx, fetched)
    else:
        ids = [r[0] for r in ctx.conn.execute("SELECT video_id FROM videos ORDER BY video_id")]
        if not ids:
            raise InputError("지표를 수집할 영상이 저장되어 있지 않습니다.", "먼저 `python -m youtube_title fetch --all`로 영상을 조회하세요.")

    metrics = None
    if args.metrics:
        end = pt_date(ctx.clock.now()) - timedelta(days=1)  # Analytics 자료는 당일분이 아직 없을 수 있어 어제까지로 한다
        start = end - timedelta(days=args.days - 1)
        metrics = reader.fetch_metrics(ids, start, end, args.phase)
        _print_metrics(ctx, metrics)

    _print_quota(ctx, reader.quota)
    ctx.say(footer())
    return 0


def _print_videos(ctx, fetched) -> None:
    rows = fetched.rows
    ctx.say(f"{badge('done')} 영상 {len(rows)}개를 조회해 저장했습니다(요청 {fetched.requested}개).")
    counts = [[label, sum(1 for r in rows if r["privacy_status"] == key)] for key, label in _PRIVACY]
    counts.append(["아동용", sum(1 for r in rows if r["made_for_kids"] == 1)])
    ctx.say(render_table(["구분", "개수"], counts, ctx.ui))
    if rows:
        shown = [[r["video_id"], r["title"], r["privacy_status"] or "-"] for r in rows[:LIST_PREVIEW]]
        ctx.say(render_table(["영상 ID", "제목", "공개 상태"], shown, ctx.ui))
        if len(rows) > LIST_PREVIEW:
            ctx.say(f"... 외 {len(rows) - LIST_PREVIEW}개")
    if fetched.skipped:
        ctx.say(f"{badge('caution')} 응답 형식이 맞지 않아 건너뛴 항목: {fetched.skipped}개")
    if fetched.missing:
        ctx.say(f"{badge('caution')} 요청했지만 응답에 없던 영상: {fetched.missing}개(비공개 처리·삭제·다른 채널 영상일 수 있음)")


def _print_metrics(ctx, m) -> None:
    ctx.say(f"{badge('done')} 지표 수집: 영상 {len(m.rows)}개 / 요청 {m.requested}개 (단계 {m.phase}, 기간 {m.period_start} ~ {m.period_end})")
    if m.missing:
        ctx.say(f"  이 기간에 지표가 없는 영상: {m.missing}개")
    if m.skipped:
        ctx.say(f"{badge('caution')} 응답 형식이 맞지 않아 건너뛴 지표 항목: {m.skipped}개")
    if not m.impressions_available:
        ctx.say(f"{badge('caution')} 노출수·클릭률(CTR)은 API에서 받지 못했습니다. Studio에서 내보낸 CSV를 `python -m youtube_title report --import-csv 파일`로 가져오세요.")


def _print_quota(ctx, quota) -> None:
    ctx.say(f"쿼터 사용량(태평양 시간 {quota.today()} 기준): {quota.used_today()} / {quota.limit} units (남음 {quota.remaining()})")
    if quota.is_warning():
        ctx.say(f"{badge('caution')} 오늘 쿼터의 {int(ctx.settings.warn_ratio * 100)}% 이상을 썼습니다. 상한에 닿으면 조회가 중단됩니다.")
