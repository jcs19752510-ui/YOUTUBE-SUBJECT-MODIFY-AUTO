"""plan: 제목 변경 계획(dry-run diff) 출력(EVT-004, FR-008, SCR-003). 네트워크 호출도, 이력 기록도 하지 않는다."""
from __future__ import annotations

from ytitle.banned_terms import load_dictionary
from ytitle.errors import InputError, YtError
from ytitle.limits import LimitReport
from ytitle.textsafe import sanitize_for_display
from ytitle.ui import badge, footer, title_line
from ytitle.updater import Plan, create_plan

NAME = "plan"
MAX_ID = 2**63 - 1
AB_NOTICE = "공식 A/B 테스트(Studio의 '제목 테스트')가 진행 중인 영상이 아닌지 Studio에서 확인하세요."


def register(sub, parent):
    p = sub.add_parser(
        "plan",
        parents=[parent],
        help="제목 변경 계획 보기(모의 실행, 실제 변경 없음)",
        description="후보 제목으로 바꾸면 무엇이 어떻게 달라지는지 보여 줍니다. 구글에 연결하지 않고, 마지막 `fetch`로 저장한 영상 정보를 사용합니다. 아무것도 바꾸지 않습니다.",
    )
    p.add_argument("--candidate", type=int, required=True, metavar="후보번호", help="`validate` 리포트의 후보번호")
    p.set_defaults(func=run)


def preserved_summary(snippet: dict, keys) -> str:
    parts = []
    for k in keys:
        v = snippet[k]
        if k == "description" and isinstance(v, str):
            parts.append(f"description(설명 {len(v)}자)")
        elif k == "tags" and isinstance(v, list):
            parts.append(f"tags(태그 {len(v)}개)")
        elif k == "categoryId":
            parts.append(f"categoryId(카테고리 {sanitize_for_display(v, 40)})")
        else:
            parts.append(sanitize_for_display(k, 40))
    return ", ".join(parts) if parts else "(없음)"


def limit_lines(report: LimitReport, ui) -> list[str]:
    """제한 검사 결과는 표 대신 한 줄씩 보여 준다: 표는 긴 사유(가능한 시각 등)를 잘라 버리기 때문이다."""
    return [f"  {badge('pass' if c.passed else 'block', ui)} {c.label}: {sanitize_for_display(c.message)}" for c in report.checks]


def _dictionary_changed(ctx, plan: Plan) -> str | None:
    """검증 때와 다른 금칙어 사전이면 안내 문구를 돌려준다(SEC-017). 확인할 수 없어도 안내한다."""
    try:
        current = load_dictionary(ctx.settings.config_dir / "banned_terms.yaml").short_hash
    except YtError:
        return "금칙어 사전을 읽을 수 없어 검증 이후 바뀌었는지 확인하지 못했습니다."
    if plan.dictionary_hash != current:
        return f"금칙어 사전이 검증 이후 바뀌었습니다(검증 때 {sanitize_for_display(plan.dictionary_hash or '없음')} → 지금 {current}). `validate`를 다시 실행하세요."
    return None


def run(args, ctx) -> int:
    s = ctx.settings
    if not 1 <= args.candidate <= MAX_ID:
        raise InputError("후보번호가 올바르지 않습니다.", "`validate` 리포트의 후보번호(1 이상의 정수)를 입력하세요.")
    plan = create_plan(ctx.conn, s, ctx.clock, args.candidate)
    ui = ctx.ui
    ctx.say(title_line("plan", False))
    ctx.say(f"영상: {sanitize_for_display(plan.video_id)}  후보번호: {plan.candidate_id}")
    ctx.say(f"현재 제목: {sanitize_for_display(plan.previous_title)}")
    ctx.say(f"새 제목:   {sanitize_for_display(plan.new_title)}")
    verdict = "pass" if plan.validation_result == "pass" else "warn"
    reasons = "; ".join(sanitize_for_display(m) for _, _, m in plan.reasons) or "-"
    ctx.say(f"검증 결과: {badge(verdict, ui)}  사유: {reasons}")
    ctx.say(f"그대로 유지되는 항목: {preserved_summary(plan.snippet, plan.preserved_fields)}")
    ctx.say("")
    ctx.say("교체 제한 검사")
    for line in limit_lines(plan.limits, ui):
        ctx.say(line)
    q = plan.quota
    ctx.say(f"쿼터 예상: 이번 적용에 약 {q.needed} units(쓰기 {s.update_cost} + 조회 2회) 필요, 오늘 남은 양 {q.remaining} units (태평양 시간 기준) {badge('pass' if q.enough else 'block', ui)}")
    ctx.say(f"계획 해시: {plan.plan_hash}")
    ctx.say("")
    if plan.stale:
        ctx.say(f"{badge('caution', ui)} 영상 정보를 가져온 지 24시간이 넘었거나 시각을 알 수 없습니다(저장 시각: {sanitize_for_display(plan.fetched_at)}). `fetch --video {sanitize_for_display(plan.video_id)}`로 다시 가져온 뒤 plan을 다시 실행하세요.")
    note = _dictionary_changed(ctx, plan)
    if note:
        ctx.say(f"{badge('caution', ui)} {note}")
    if plan.exclusions and not plan.exclusions_enforced:
        ctx.say(f"{badge('caution', ui)} 이 영상은 공식 A/B 대상이 아닐 수 있습니다(순차 교체 모드가 꺼져 있어 제외하지는 않았습니다): {', '.join(plan.exclusions)}")
    if plan.validation_result == "warn":
        ctx.say(f"{badge('caution', ui)} 검증에서 경고를 받은 제목입니다. 위 사유를 읽고 판단하세요.")
    ctx.say(f"{badge('caution', ui)} {AB_NOTICE}")
    ctx.say("이 화면은 모의 실행입니다. 구글에 연결하지 않았고 아무것도 바꾸지 않았습니다.")
    if not plan.ready:
        ctx.say(f"{badge('block', ui)} 교체 제한 또는 쿼터 조건을 통과하지 못해 이 계획은 진행할 수 없습니다. 위 '교체 제한 검사'의 안내를 확인하세요.")
        ctx.say(footer())
        return 3
    ctx.say(f"다음에 할 일: `approve --candidate {plan.candidate_id} --approver 이름` 으로 사람의 승인을 받으세요(계획 해시가 승인에 묶입니다).")
    ctx.say(footer())
    return 0
