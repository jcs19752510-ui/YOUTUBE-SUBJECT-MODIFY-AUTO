"""purge: 오래된 기록 삭제(FR-017, NFR-009, EVT-009). 기본은 미리보기이며 삭제 전 DB 사본을 만든다."""
from __future__ import annotations

from ytitle import db as dbmod
from ytitle.errors import InputError
from ytitle.timeutil import parse_date
from ytitle.ui import badge, footer, render_table, title_line

NAME = "purge"
CONFIRM_WORD = "삭제"

# 각 테이블의 시각 컬럼. 최근 성공 변경(롤백 가능성)은 보호한다.
_TARGETS = [
    ("title_changes", "created_at"),
    ("title_candidates", "created_at"),
    ("metrics_snapshots", "taken_at"),
    ("run_logs", "started_at"),
    ("quota_usage", "called_at"),
]
_PROTECT_CHANGES = "id NOT IN (SELECT MAX(id) FROM title_changes WHERE result = 'success' GROUP BY video_id)"


def register(sub, parent):
    p = sub.add_parser("purge", parents=[parent], help="오래된 기록 삭제(기본은 미리보기)", description="지정한 날짜 이전의 기록을 지웁니다. 삭제 전에 DB 사본을 자동으로 만들고, 영상별 가장 최근 성공 변경은 롤백을 위해 보존합니다.")
    p.add_argument("--before", required=True, help="이 날짜(YYYY-MM-DD) 이전 기록이 대상")
    p.add_argument("--execute", action="store_true", help="실제로 삭제(없으면 미리보기만)")
    p.set_defaults(func=run)


def _count(conn, cutoff: str, run_id: str) -> dict[str, int]:
    c = {}
    c["title_changes"] = conn.execute(f"SELECT COUNT(*) FROM title_changes WHERE created_at < ? AND {_PROTECT_CHANGES}", (cutoff,)).fetchone()[0]
    c["title_candidates"] = conn.execute(
        "SELECT COUNT(*) FROM title_candidates WHERE created_at < ? AND id NOT IN (SELECT candidate_id FROM title_changes WHERE candidate_id IS NOT NULL AND NOT (created_at < ? AND " + _PROTECT_CHANGES + "))",
        (cutoff, cutoff),
    ).fetchone()[0]
    c["metrics_snapshots"] = conn.execute("SELECT COUNT(*) FROM metrics_snapshots WHERE taken_at < ?", (cutoff,)).fetchone()[0]
    c["run_logs"] = conn.execute("SELECT COUNT(*) FROM run_logs WHERE started_at < ? AND run_id <> ?", (cutoff, run_id)).fetchone()[0]
    c["quota_usage"] = conn.execute("SELECT COUNT(*) FROM quota_usage WHERE called_at < ?", (cutoff,)).fetchone()[0]
    return c


def run(args, ctx) -> int:
    cutoff_date = parse_date(args.before)
    today = ctx.clock.now().date()
    if cutoff_date > today:
        raise InputError("미래 날짜는 지정할 수 없습니다.", "오늘 이전 날짜를 YYYY-MM-DD로 입력하세요.")
    cutoff = f"{cutoff_date.isoformat()}T00:00:00Z"
    conn = ctx.conn
    counts = _count(conn, cutoff, ctx.run_id)
    total = sum(counts.values())
    ctx.say(title_line("purge", False))
    ctx.say(f"대상 기준: {cutoff_date.isoformat()} 이전")
    ctx.say(render_table(["기록 종류", "삭제 대상 건수"], [[k, v] for k, v in counts.items()], ctx.ui))
    ctx.say("영상별 가장 최근 성공 변경(롤백용 백업)은 보존됩니다.")
    if total == 0:
        ctx.say("삭제할 기록이 없습니다.")
        ctx.say(footer())
        return 0
    if not args.execute:
        ctx.say("미리보기입니다. 아무것도 지우지 않았습니다. 실제로 지우려면 같은 명령에 --execute를 붙이세요.")
        ctx.say(footer())
        return 0
    if not ctx.confirm(CONFIRM_WORD):
        raise InputError("확인이 완료되지 않아 삭제하지 않았습니다.", f"다시 실행해 '{CONFIRM_WORD}'를 입력하세요.")
    backup_path = dbmod.backup(conn, ctx.settings.data_dir / "backups", ctx.clock.now())
    ctx.say(f"삭제 전 DB 사본을 만들었습니다: {backup_path}")
    with conn:
        conn.execute(f"DELETE FROM title_changes WHERE created_at < ? AND {_PROTECT_CHANGES}", (cutoff,))
        conn.execute("DELETE FROM title_candidates WHERE created_at < ? AND id NOT IN (SELECT candidate_id FROM title_changes WHERE candidate_id IS NOT NULL)", (cutoff,))
        conn.execute("DELETE FROM metrics_snapshots WHERE taken_at < ?", (cutoff,))
        conn.execute("DELETE FROM run_logs WHERE started_at < ? AND run_id <> ?", (cutoff, ctx.run_id))
        conn.execute("DELETE FROM quota_usage WHERE called_at < ?", (cutoff,))
    ctx.say(f"{badge('done')} 총 {total}건을 삭제했습니다.")
    ctx.say(footer())
    return 0

