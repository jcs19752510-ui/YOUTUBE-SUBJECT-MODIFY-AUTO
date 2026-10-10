"""apply: 후보 1건의 제목을 바꾼다(EVT-006, FR-012, SCR-003/005/006, SEC-001, SEC-020).

`--live`가 없으면 모의 실행이다: plan과 같은 정보에 더해 실제 적용 시 14단계 안전 게이트 중 어디가 막는지 보여 주며, 구글에 연결하지도,
이력(`title_changes`)·쿼터에 쓰지도 않는다. `--live`가 있어도 게이트(live_guard)를 모두 통과해야만 쓴다. 한 번에 후보 1건만 처리한다.
"""
from __future__ import annotations

from ytitle.commands.plan import AB_NOTICE, MAX_ID, limit_lines, preserved_summary
from ytitle.errors import InputError
from ytitle.live_guard import GateOutcome, apply_live, env_from_ctx, gate_line, preview_apply
from ytitle.textsafe import sanitize_for_display
from ytitle.ui import badge, footer, title_line
from ytitle.updater import create_plan

NAME = "apply"


def register(sub, parent):
    p = sub.add_parser(
        "apply",
        parents=[parent],
        help="후보 1건의 제목을 바꾸기(기본은 모의 실행, 실제 적용은 --live)",
        description=(
            "후보 하나의 제목을 바꿉니다. 옵션이 없으면 모의 실행이라 아무것도 바꾸지 않고, 실제 적용 때 어떤 안전 조건이 막는지 보여 줍니다.\n"
            "--live를 붙여도 enable_live 설정·허용 목록·승인 파일·영상 ID 직접 입력 등 14단계 조건을 모두 통과해야만 바뀝니다."
        ),
    )
    p.add_argument("--candidate", type=int, required=True, metavar="후보번호", help="`validate` 리포트의 후보번호(한 번에 1건)")
    p.add_argument("--live", action="store_true", help="실제 적용(★구글에 바로 반영★). 안전 게이트 14단계를 모두 통과해야 함")
    p.set_defaults(func=run)


def run(args, ctx) -> int:
    if not 1 <= args.candidate <= MAX_ID:
        raise InputError("후보번호가 올바르지 않습니다.", "`validate` 리포트의 후보번호(1 이상의 정수)를 입력하세요.")
    if args.live:
        ctx.say(title_line("apply", True))
        result = apply_live(env_from_ctx(ctx), args.candidate, live_flag=True)
        ctx.say(footer())
        return 0 if result.ok else 1
    return _dry_run(args, ctx)


def _dry_run(args, ctx) -> int:
    plan = create_plan(ctx.conn, ctx.settings, ctx.clock, args.candidate)
    ui = ctx.ui
    ctx.say(title_line("apply", False))
    ctx.say(f"영상: {sanitize_for_display(plan.video_id)}  후보번호: {plan.candidate_id}")
    ctx.say(f"현재 제목: {sanitize_for_display(plan.previous_title)}")
    ctx.say(f"새 제목:   {sanitize_for_display(plan.new_title)}")
    ctx.say(f"그대로 유지되는 항목: {preserved_summary(plan.snippet, plan.preserved_fields)}")
    ctx.say("교체 제한 검사")
    for line in limit_lines(plan.limits, ui):
        ctx.say(line)
    q = plan.quota
    ctx.say(f"쿼터 예상: 약 {q.needed} units 필요, 오늘 남은 양 {q.remaining} units (태평양 시간 기준) {badge('pass' if q.enough else 'block', ui)}")
    ctx.say(f"계획 해시: {plan.plan_hash}")
    ctx.say("")
    ctx.say("실제 적용 조건(안전 게이트 14단계)")
    outcomes = preview_apply(env_from_ctx(ctx), plan)
    for o in outcomes:
        ctx.say(gate_line(o, ui))
    blocked: list[GateOutcome] = [o for o in outcomes if o.status == "block" and o.step != 1]
    if plan.stale:
        ctx.say(f"{badge('caution', ui)} 영상 정보를 가져온 지 24시간이 넘었거나 시각을 알 수 없습니다. `fetch --video {sanitize_for_display(plan.video_id)}`로 다시 가져온 뒤 plan부터 다시 하세요.")
    ctx.say(f"{badge('caution', ui)} {AB_NOTICE}")
    ctx.say("이 화면은 모의 실행입니다. 구글에 연결하지 않았고 아무것도 바꾸지 않았습니다.")
    if blocked:
        ctx.say(f"{badge('block', ui)} 막힌 조건 {len(blocked)}개: {', '.join(str(o.step) + '단계' for o in blocked)}. 위 안내를 해결해야 실제 적용을 할 수 있습니다.")
        ctx.say(footer())
        return 3
    ctx.say(f"다음에 할 일: 실제로 적용하려면 `apply --candidate {plan.candidate_id} --live` 를 실행하세요(마지막에 영상 ID를 직접 입력합니다).")
    ctx.say(footer())
    return 0
