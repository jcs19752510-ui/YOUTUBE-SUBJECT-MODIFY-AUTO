"""report: 변경 전후 성과 비교 리포트와 Studio CSV 가져오기(EVT-008, SCR-008, FR-007, FR-018, POL-002)."""
from __future__ import annotations

import re
from collections import Counter

from ytitle import csv_import
from ytitle.errors import InputError
from ytitle.report import CAUSAL_NOTE, INSUFFICIENT_LABEL, LIMIT_NOTE, Rules, VideoReport, build_report, list_changed_video_ids, load_video_data
from ytitle.textsafe import sanitize_for_display
from ytitle.timeutil import parse_iso
from ytitle.ui import badge, footer, render_table, title_line

NAME = "report"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
MAX_VIDEOS_SHOWN = 20
MAX_ISSUES_SHOWN = 10
MAX_CHANGES_SHOWN = 5
_KIND = {"apply": "적용", "rollback": "롤백"}


def register(sub, parent):
    p = sub.add_parser(
        "report",
        parents=[parent],
        help="변경 전후 성과 비교 리포트 / Studio CSV 가져오기",
        description="제목 변경 전후의 노출수·클릭률·조회수·시청 시간을 나란히 보여 줍니다(원인을 단정하지 않으며 데이터가 부족하면 '데이터 부족'으로 표시). `--import-csv`로 Studio에서 내보낸 CSV를 이 PC의 DB에 저장할 수 있습니다. 유튜브는 바꾸지 않습니다.",
    )
    p.add_argument("--video", metavar="ID", help="영상 ID. 없으면 제목을 바꾼 적 있는 모든 영상")
    p.add_argument("--import-csv", metavar="파일", help="Studio에서 내보낸 CSV 파일(상대 경로는 프로젝트 폴더 기준)")
    p.add_argument("--phase", choices=csv_import.PHASES, default="periodic", help="CSV 지표 단계: before(변경 전), after(변경 후), periodic(정기, 비교에는 쓰이지 않음). 기본 periodic")
    p.add_argument("--period-start", metavar="YYYY-MM-DD", help="CSV 지표의 집계 시작일(비교에 필요)")
    p.add_argument("--period-end", metavar="YYYY-MM-DD", help="CSV 지표의 집계 종료일(비교에 필요)")
    p.set_defaults(func=run)


def _validate(args) -> None:
    if args.video is not None and not VIDEO_ID_RE.match(args.video):
        raise InputError("영상 ID 형식이 올바르지 않습니다(영문·숫자·-·_ 11자).", "유튜브 주소의 v= 뒤 11글자를 그대로 입력하세요.")
    if not args.import_csv and (args.period_start or args.period_end or args.phase != "periodic"):
        raise InputError("`--phase`, `--period-start`, `--period-end`는 `--import-csv`와 함께만 쓸 수 있습니다.", "CSV를 가져오려면 `report --import-csv 파일 --phase before --period-start 2026-01-01 --period-end 2026-01-28`처럼 실행하세요.")


def run(args, ctx) -> int:
    _validate(args)
    ctx.say(title_line("report", False))
    if args.import_csv:
        _import(args, ctx)
    if args.video:
        ids = [args.video]
    elif args.import_csv:
        ids = []
    else:
        ids = list_changed_video_ids(ctx.conn)
        if not ids:
            ctx.say("제목을 바꾼 기록이 없어 비교할 영상이 없습니다. 변경 전 지표는 `python -m ytitle fetch --metrics --phase before`로 미리 수집해 두세요.")
    rules = Rules.from_settings(ctx.settings)
    for vid in ids[:MAX_VIDEOS_SHOWN]:
        data = load_video_data(ctx.conn, vid)
        _print_report(ctx, build_report(vid, data.title, data.changes, data.snapshots, rules))
    if len(ids) > MAX_VIDEOS_SHOWN:
        ctx.say(f"... 외 {len(ids) - MAX_VIDEOS_SHOWN}개 영상(`--video ID`로 하나씩 보세요)")
    if ids:
        ctx.say(LIMIT_NOTE)
        ctx.say(CAUSAL_NOTE)
    ctx.say(footer())
    return 0


# ---------------------------------------------------------------- CSV 가져오기

def _import(args, ctx) -> None:
    start = csv_import.parse_day(args.period_start, "시작일") if args.period_start else None
    end = csv_import.parse_day(args.period_end, "종료일") if args.period_end else None
    res = csv_import.read_csv_file(args.import_csv, ctx.settings.base_dir, args.video)
    _print_issues(ctx, res)
    if not res.rows:
        raise InputError("가져올 수 있는 행이 하나도 없습니다.", "위 건너뛴 이유를 확인하고, Studio에서 내보낸 파일의 머리글과 영상 ID 열을 그대로 둔 채 다시 시도하세요.")
    stored = csv_import.store_rows(ctx.conn, res.rows, phase=args.phase, period_start=start, period_end=end, now=ctx.clock.now())
    period = f"{start} ~ {end}" if start else "기간 미지정"
    ctx.say(f"{badge('done', ctx.ui)} CSV {res.data_rows}행 중 {stored.inserted}행을 저장했습니다(단계 {args.phase}, 기간 {period}, 인코딩 {res.encoding}).")
    if stored.duplicates:
        ctx.say(f"  이미 같은 내용이 저장되어 있어 건너뛴 행: {stored.duplicates}개")
    if stored.unknown_videos:
        ctx.say(f"{badge('caution', ctx.ui)} DB에 영상 정보가 없는 영상 {stored.unknown_videos}개가 포함되어 있습니다(`fetch --all`로 영상 정보를 먼저 조회하세요).")
    if start is None:
        ctx.say(f"{badge('caution', ctx.ui)} 집계 기간을 알려 주지 않아 이 자료는 리포트에서 '{INSUFFICIENT_LABEL}'로 처리됩니다. `--period-start`/`--period-end`를 함께 쓰세요.")
    if args.phase == "periodic":
        ctx.say(f"{badge('caution', ctx.ui)} 단계가 periodic이면 변경 전후 비교에 쓰이지 않습니다. 비교하려면 `--phase before` 또는 `--phase after`로 가져오세요.")


def _print_issues(ctx, res) -> None:
    ctx.say("인식한 열: " + ", ".join(f"{k}={v}" for k, v in res.columns.items()))
    if res.ignored_columns:
        ctx.say("무시한 열: " + ", ".join(res.ignored_columns))
    if not res.issues:
        return
    ctx.say(f"{badge('caution', ctx.ui)} 건너뛴 행 {len(res.issues)}개:")
    counts = Counter(i.reason for i in res.issues)
    ctx.say(render_table(["이유", "개수"], [[reason, n] for reason, n in counts.most_common()], ctx.ui))
    shown = res.issues[:MAX_ISSUES_SHOWN]
    ctx.say(render_table(["줄", "이유", "값"], [[i.line, i.reason, i.detail or "-"] for i in shown], ctx.ui))
    if len(res.issues) > len(shown):
        ctx.say(f"... 외 {len(res.issues) - len(shown)}개")


# ---------------------------------------------------------------- 리포트 출력

def _kst(value: str) -> str:
    try:
        from zoneinfo import ZoneInfo

        return parse_iso(value).astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError, KeyError):
        return sanitize_for_display(value, 30)


def _num(v: float | None, digits: int = 1) -> str:
    return "-" if v is None else f"{v:,.{digits}f}"


def _signed(v: float | None, digits: int = 1, suffix: str = "") -> str:
    return "-" if v is None else f"{v:+,.{digits}f}{suffix}"


def _snap_line(label: str, s) -> str:
    period = f"{s.period_start} ~ {s.period_end}" if s.period_start and s.period_end else "기간 정보 없음"
    return f"{label}: 출처 {s.source}, 기간 {period}, 노출수 {_num(s.impressions, 0)}, 클릭률 {_num(s.ctr, 2)}%, 조회수 {_num(s.views, 0)}, 시청 시간 {_num(s.watch_minutes, 1)}분"


def _print_report(ctx, rep: VideoReport) -> None:
    title = sanitize_for_display(rep.title) if rep.title else "(DB에 저장된 제목 없음)"
    ctx.say("")
    ctx.say(f"영상: {rep.video_id}  제목: {title}")
    if rep.changes:
        rows = [[c.id, _KIND.get(c.change_type, c.change_type), c.previous_title, c.new_title, _kst(c.at)] for c in rep.changes[-MAX_CHANGES_SHOWN:]]
        ctx.say(render_table(["변경번호", "종류", "이전 제목", "새 제목", "시각(한국)"], rows, ctx.ui))
    for note in rep.notes:
        ctx.say(f"{badge('caution', ctx.ui)} {sanitize_for_display(note)}")
    if rep.status == "no_change":
        return
    if rep.status == "ok":
        ctx.say(f"{badge('done', ctx.ui)} 비교할 수 있는 자료가 충분합니다(참고용 수치이며 원인을 뜻하지 않습니다).")
        rows = [[m.label, _num(m.before, 2 if m.key == "ctr" else 1), _num(m.after, 2 if m.key == "ctr" else 1), _signed(m.delta, 2 if m.key == "ctr" else 1), _signed(m.pct, 1, "%")] for m in rep.metrics]
        ctx.say(render_table(["지표", "변경 전", "변경 후", "차이", "변화율"], rows, ctx.ui))
    else:
        ctx.say(f"{badge('caution', ctx.ui)} {INSUFFICIENT_LABEL}: 결론을 내릴 수 없어 비교하지 않습니다.")
        for r in rep.reasons:
            ctx.say(f"  - {sanitize_for_display(r)}")
        if rep.baseline_missing:
            ctx.say(f"{badge('caution', ctx.ui)} 변경 전 기준선이 없어 이후에 자료가 모여도 신뢰도가 낮습니다.")
        if rep.expected_after_date:
            ctx.say(f"  변경 후 지표 수집 예정일: {rep.expected_after_date} 이후(`fetch --metrics --phase after`)")
    if rep.before:
        ctx.say(_snap_line("변경 전 자료", rep.before))
    if rep.after:
        ctx.say(_snap_line("변경 후 자료", rep.after))
