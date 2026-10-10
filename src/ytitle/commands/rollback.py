"""rollback: 이전 제목 복원(EVT-007, FR-011, SCR-005/006).

`--live`가 없으면 계획만 출력한다(구글에 연결하지 않고 이력에도 쓰지 않음). `--live`가 있으면 live_guard의 안전 게이트(enable_live·허용 목록·
쿼터·재조회·확인자·영상 ID 직접 입력 등)를 모두 통과해야만 백업된 이전 제목으로 복원한다. 교체 제한은 복구가 막히지 않도록 면제한다(WU-4 결정).
"""
from __future__ import annotations

from ytitle.errors import InputError
from ytitle.history import plan_rollback
from ytitle.live_guard import env_from_ctx, rollback_live
from ytitle.textsafe import sanitize_for_display
from ytitle.ui import badge, footer, title_line
from ytitle.commands.plan import AB_NOTICE, MAX_ID

NAME = "rollback"


def register(sub, parent):
    p = sub.add_parser(
        "rollback",
        parents=[parent],
        help="이전 제목으로 되돌리기(기본은 계획만 보기, 실제 복원은 --live)",
        description=(
            "성공한 제목 변경을 되돌리는 계획을 보여 줍니다. 옵션이 없으면 구글에 연결하지 않고 아무것도 바꾸지 않습니다.\n"
            "--live를 붙이면 enable_live 설정·허용 목록·확인자·영상 ID 직접 입력 등 안전 조건을 모두 통과했을 때만 이전 제목으로 복원합니다."
        ),
    )
    p.add_argument("--change", type=int, required=True, metavar="변경번호", help="되돌릴 적용 변경 번호(title_changes)")
    p.add_argument("--live", action="store_true", help="실제 복원(★구글에 바로 반영★). 안전 게이트를 모두 통과해야 함")
    p.add_argument("--approver", default=None, metavar="이름", help="--live일 때 필수: 복원을 확인하는 사람의 이름(이력에 기록됨)")
    p.set_defaults(func=run)


def run(args, ctx) -> int:
    if not 1 <= args.change <= MAX_ID:
        raise InputError("변경번호가 올바르지 않습니다.", "되돌릴 변경의 번호(1 이상의 정수)를 입력하세요.")
    if args.live:
        ctx.say(title_line("rollback", True))
        result = rollback_live(env_from_ctx(ctx), args.change, approver=args.approver, live_flag=True)
        ctx.say(footer())
        return 0 if result.ok else 1
    plan = plan_rollback(ctx.conn, ctx.settings, ctx.clock, args.change)
    ui = ctx.ui
    ctx.say(title_line("rollback", False))
    ctx.say(f"영상: {sanitize_for_display(plan.video_id)}  되돌릴 변경번호: {plan.change_id}")
    ctx.say(f"현재 제목:      {sanitize_for_display(plan.current_title)}")
    ctx.say(f"복원할 제목:    {sanitize_for_display(plan.restore_title)}")
    if plan.changed_since_backup:
        ctx.say(f"{badge('caution', ui)} 적용 이후 제목 외 항목이 달라졌습니다(복원 본문은 지금 값을 그대로 유지합니다): {', '.join(sanitize_for_display(k, 40) for k in plan.changed_since_backup)}")
    ctx.say(f"그대로 유지되는 항목: {', '.join(sanitize_for_display(k, 40) for k in sorted(k for k in plan.snippet if k != 'title')) or '(없음)'}")
    if not plan.current_matches_applied:
        ctx.say(f"{badge('caution', ui)} 지금 제목이 우리가 적용한 제목과 다릅니다. 적용 이후 Studio 등에서 제목이 바뀌었을 수 있습니다. 복원 전에 `fetch --video {sanitize_for_display(plan.video_id)}`로 최신 상태를 확인하세요.")
    if plan.stale:
        ctx.say(f"{badge('caution', ui)} 영상 정보를 가져온 지 24시간이 넘었거나 시각을 알 수 없습니다(저장 시각: {sanitize_for_display(plan.fetched_at)}). `fetch --video {sanitize_for_display(plan.video_id)}`로 다시 가져오세요.")
    ctx.say(f"계획 해시: {plan.plan_hash}")
    ctx.say(f"{badge('caution', ui)} {AB_NOTICE}")
    ctx.say("이 화면은 모의 실행입니다. 구글에 연결하지 않았고 아무것도 바꾸지 않았습니다.")
    ctx.say(f"다음에 할 일: 실제로 복원하려면 `rollback --change {plan.change_id} --approver 이름 --live` 를 실행하세요(마지막에 영상 ID를 직접 입력합니다).")
    ctx.say(footer())
    return 0
