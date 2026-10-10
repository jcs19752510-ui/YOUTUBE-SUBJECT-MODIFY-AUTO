"""approve: 사람의 승인 파일 생성(EVT-005, FR-013, SCR-004, SEC-014).

계획(plan) 요약을 보여 주고, 사람이 영상 ID를 직접 입력해야만 승인 파일(계획 해시에 묶임·만료·1회용)을 만들고 후보를 `approved`로 바꾼다.
구글에 연결하지 않고, 영상을 바꾸지 않는다. 교체 제한·쿼터를 지금 통과하지 못하는 계획은 승인하지 않는다.
"""
from __future__ import annotations

from ytitle import approvals
from ytitle.commands.plan import AB_NOTICE, MAX_ID, limit_lines, preserved_summary
from ytitle.errors import InputError, SafetyGateError
from ytitle.history import transition_candidate
from ytitle.limits import format_kst
from ytitle.textsafe import sanitize_for_display
from ytitle.ui import badge, footer, title_line
from ytitle.updater import create_plan

NAME = "approve"
OVERWRITE_PHRASE = "덮어쓰기"


def register(sub, parent):
    p = sub.add_parser(
        "approve",
        parents=[parent],
        help="후보 1건을 사람이 승인(승인 파일 만들기)",
        description="계획 요약을 확인하고 영상 ID를 직접 입력하면 승인 파일을 만듭니다. 승인은 이 계획(영상·후보·새 제목·현재 영상 정보)에만 유효하고, 만료되며, 한 번만 쓸 수 있습니다.",
    )
    p.add_argument("--candidate", type=int, required=True, metavar="후보번호", help="`validate` 리포트의 후보번호")
    p.add_argument("--approver", required=True, metavar="이름", help="승인하는 사람의 이름(이력에 기록됨)")
    p.add_argument("--ttl-hours", type=int, default=None, metavar="시간", help="승인 유효 시간(기본은 설정 approval.ttl_hours, 그 값을 넘길 수 없음)")
    p.set_defaults(func=run)


def run(args, ctx) -> int:
    s, ui = ctx.settings, ctx.ui
    if not 1 <= args.candidate <= MAX_ID:
        raise InputError("후보번호가 올바르지 않습니다.", "`validate` 리포트의 후보번호(1 이상의 정수)를 입력하세요.")
    approver = approvals.clean_approver(args.approver)
    ttl = approvals.check_ttl(s, s.approval_ttl_hours if args.ttl_hours is None else args.ttl_hours)
    plan = create_plan(ctx.conn, s, ctx.clock, args.candidate)
    ctx.say(title_line("approve", False))
    ctx.say(f"영상: {sanitize_for_display(plan.video_id)}  후보번호: {plan.candidate_id}")
    ctx.say(f"현재 제목: {sanitize_for_display(plan.previous_title)}")
    ctx.say(f"새 제목:   {sanitize_for_display(plan.new_title)}")
    ctx.say(f"그대로 유지되는 항목: {preserved_summary(plan.snippet, plan.preserved_fields)}")
    ctx.say("교체 제한 검사")
    for line in limit_lines(plan.limits, ui):
        ctx.say(line)
    q = plan.quota
    ctx.say(f"쿼터 예상: 약 {q.needed} units 필요, 오늘 남은 양 {q.remaining} units {badge('pass' if q.enough else 'block', ui)}")
    ctx.say(f"계획 해시: {plan.plan_hash}")
    if plan.validation_result == "warn":
        ctx.say(f"{badge('caution', ui)} 검증에서 경고를 받은 제목입니다: " + "; ".join(sanitize_for_display(m) for _, _, m in plan.reasons))
    if plan.stale:
        ctx.say(f"{badge('caution', ui)} 영상 정보를 가져온 지 24시간이 넘었습니다. 승인 후 적용 단계에서 영상 정보가 달라졌으면 승인은 무효가 됩니다. 먼저 `fetch --video {sanitize_for_display(plan.video_id)}`를 권장합니다.")
    ctx.say(f"{badge('caution', ui)} {AB_NOTICE}")
    if not plan.ready:
        ctx.say(f"{badge('block', ui)} 교체 제한 또는 쿼터 조건을 지금 통과하지 못해 승인하지 않았습니다. 위 안내의 시각 이후에 다시 시도하세요.")
        ctx.say(footer())
        return 3

    now = ctx.clock.now()
    if approvals.inspect_active(s, plan.video_id, plan.candidate_id, now) is not None:
        ctx.say(f"{badge('caution', ui)} 이 후보에는 이미 유효한 승인 파일이 있습니다. 새로 승인하면 이전 승인은 사라집니다.")
        if not ctx.confirm(OVERWRITE_PHRASE):
            raise SafetyGateError("덮어쓰기를 확인받지 못해 기존 승인을 그대로 두었습니다.", "새로 승인하려면 다시 실행해 '덮어쓰기'를 입력하세요.")
    ctx.say(f"{badge('caution', ui)} 승인하면 이 계획으로 `apply --live`를 할 수 있게 됩니다(만료 {ttl}시간). 승인자: {sanitize_for_display(approver, 40)}")
    if not ctx.confirm(plan.video_id):
        raise SafetyGateError("영상 ID 확인이 완료되지 않아 승인 파일을 만들지 않았습니다.", "승인하려면 영상 ID를 화면 그대로 입력하세요.")

    approval = approvals.create_approval(
        s, video_id=plan.video_id, candidate_id=plan.candidate_id, new_title=plan.new_title, plan_hash=plan.plan_hash, approver=approver, now=now, ttl_hours=ttl, overwrite=True,
    )
    status = ctx.conn.execute("SELECT status FROM title_candidates WHERE id = ?", (plan.candidate_id,)).fetchone()[0]
    if status == "filtered":
        try:
            transition_candidate(ctx.conn, plan.candidate_id, "approved", now)
        except Exception:
            approvals.remove_approval(s, plan.video_id, plan.candidate_id)   # 상태가 바뀌지 않았다면 승인 파일도 남기지 않는다
            raise
    ctx.say(f"{badge('done', ui)} 승인했습니다. 승인자: {sanitize_for_display(approval.approver, 40)}")
    ctx.say(f"만료: {format_kst(approval.expires_at)}")
    ctx.say(f"승인 파일: {approval.path}")
    ctx.say(f"다음에 할 일: `apply --candidate {plan.candidate_id}` 로 모의 실행을 확인한 뒤, 실제로 적용하려면 `--live`를 붙이세요.")
    ctx.say(footer())
    return 0
