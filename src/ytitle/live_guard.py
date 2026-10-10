"""쓰기 안전 게이트와 `videos.update` 호출(SEC-001, FR-009~013, SEC-002, SEC-004, SEC-005, SEC-009, SEC-010, SEC-012, SEC-014, SEC-015, SEC-020).

**이 프로젝트에서 YouTube에 쓰는 코드는 이 파일의 `_send_update` 단 한 곳뿐이다**(소스 검사 테스트가 증명한다).
DESIGN 5-2의 14단계를 문서 순서대로 실행하며 하나라도 실패하면 즉시 중단한다(fail-closed, 종료 코드 3).

    1 --live 플래그          2 enable_live(settings.local.yaml)   3 허용 목록        4 쿼터 여유       5 교체 제한
    6 호출 직전 재조회        7 승인 파일(계획 해시·만료·1회용)      8 변경 전 지표      9 요청 본문       10 영상 ID 직접 입력
    11 백업·planned 기록·쿼터 선예약   12 videos.update 호출   13 재조회 사후 검증   14 결과 기록

값싼 로컬 검사(1~5)를 먼저, 네트워크 읽기(6)는 그 뒤, 사람 확인(10) 이후에야 쓰기 토큰을 읽고(11) 쓴다(12).
1~11단계에서 막히면 `title_changes`에 `aborted` 행을 남긴다(감사). 11단계에서 `planned` 행이 생긴 뒤에는 그 행을 `success`/`failed`/`aborted`로 끝내거나,
결과를 알 수 없으면(타임아웃·5xx) `planned`로 남긴다. **자동 롤백은 하지 않는다**: 사후 검증이 실패해도 경보와 `rollback` 안내만 한다.

롤백(`rollback --live`)은 같은 엔진을 쓴다. 승인 파일 대신 확인자 이름과 영상 ID 직접 입력이 사람의 승인이며,
교체 제한(72시간·횟수·노출수·하루 상한)과 변경 전 지표 확인은 WU-4 결정대로 면제한다(복구가 막히면 안 된다).
"""
from __future__ import annotations

import dataclasses
import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import httplib2
from googleapiclient.errors import HttpError

from ytitle import approvals
from ytitle import auth as authmod
from ytitle import db as dbmod
from ytitle.approvals import Approval
from ytitle.config import Settings
from ytitle.errors import ApiError, AuthError, QuotaError, SafetyGateError, YtError
from ytitle.history import RollbackPlan, begin_change, begin_rollback, finish_change, plan_rollback, record_aborted
from ytitle.limits import check_limits
from ytitle.quota import RESET_HINT, QuotaManager
from ytitle.retry import call_with_retry
from ytitle.textsafe import sanitize_for_display
from ytitle.ui import UiOptions, badge, progress_steps
from ytitle.updater import READ_CALLS_PER_APPLY, Plan, build_update_body, compute_plan_hash, create_plan, parse_snippet, snippet_hash, validate_new_title
from ytitle.youtube_read import YouTubeReader, build_services

# DESIGN 5-2. (번호, 짧은 이름)
STEP_LABELS: dict[int, str] = {
    1: "--live 플래그",
    2: "enable_live 설정(settings.local.yaml)",
    3: "허용 목록(live_allowlist)",
    4: "쿼터 여유",
    5: "교체 제한",
    6: "호출 직전 재조회(현재 제목 일치)",
    7: "승인(계획 해시·만료·1회용)",
    8: "변경 전 지표 스냅샷",
    9: "요청 본문(snippet 전체 보존)",
    10: "영상 ID 직접 입력 확인",
    11: "백업·변경 기록·쿼터 선예약",
    12: "videos.update 호출",
    13: "재조회 사후 검증",
    14: "결과 기록",
}
LAST_STEP = 14
BASELINE_PHRASE = "지표없이진행"

# videos.update 본문에서 뺄 snippet 항목. 지금은 비어 있어 snippet 전체를 그대로 보낸다(요구: 전체 보존, SEC-005).
# [확인 필요] thumbnails·publishedAt·channelId 같은 읽기 전용 항목을 보내도 API가 받아들이는지는 12단계(비공개 테스트 영상)에서 실측한다.
# 거부되면 여기에 이름을 추가하면 본문 구성과 본문 검사(check_body)가 함께 바뀐다. 보존 범위 테스트(TC-5xx)도 같이 고칠 것.
NOT_SENT_SNIPPET_FIELDS: tuple[str, ...] = ()

# 사후 검증에서 '같아야 하는' 항목(SEC-010). 그 밖에 달라진 항목은 검증 실패로 보지 않고 verify_result에 이름만 남긴다.
VERIFY_PRESERVED_FIELDS = ("description", "tags", "categoryId", "defaultLanguage", "defaultAudioLanguage")
_MISSING = object()


class LiveGateError(SafetyGateError):
    """14단계 중 `step`번에서 중단됨(종료 코드 3)."""

    def __init__(self, step: int, message: str, next_step: str = "", *, cause: str = "") -> None:
        super().__init__(message, next_step, cause=cause)
        self.step = step


class WriteApiError(ApiError):
    """쓰기 호출 오류. `definite`=True면 구글이 요청을 처리하지 않았음이 분명하고, False면 반영됐는지 알 수 없다."""

    def __init__(self, message: str, next_step: str = "", *, retryable: bool = False, definite: bool = True, cause: str = "") -> None:
        super().__init__(message, next_step, retryable=retryable, cause=cause)
        self.definite = definite


@dataclass(frozen=True)
class GateOutcome:
    step: int
    status: str     # pass | block | warn | pending | skip
    detail: str


@dataclass
class LiveResult:
    kind: str
    video_id: str
    change_id: int
    verify: dict
    ok: bool
    gates: list[GateOutcome] = field(default_factory=list)


@dataclass
class LiveEnv:
    """게이트가 쓰는 협력 객체. 테스트는 구글 대신 가짜 서비스를 돌려주는 팩토리를 넣는다."""

    conn: sqlite3.Connection
    settings: Settings
    clock: Any
    run_id: str
    say: Callable[[str], None]
    confirm: Callable[[str], bool]
    ui: UiOptions
    logger: logging.Logger
    make_reader: Callable[[], YouTubeReader]    # 읽기 토큰으로 만든 조회기(6·13단계). 쓰기 토큰을 쓰지 않는다
    make_write_service: Callable[[], Any]       # 쓰기 토큰을 읽어 서비스를 만든다(11단계에서만 호출된다)
    sleep: Callable[[float], None] = time.sleep


def make_reader(ctx) -> YouTubeReader:
    """읽기 토큰으로 조회기를 만든다. 테스트에서는 이 함수를 교체한다."""
    creds = authmod.load_credentials("read", ctx.settings)
    youtube, analytics = build_services(creds)
    return YouTubeReader(youtube, analytics, QuotaManager(ctx.conn, ctx.settings, ctx.clock), ctx.conn, ctx.settings, ctx.clock, run_id=ctx.run_id)


def make_write_service(settings: Settings):
    """쓰기 토큰을 읽어 YouTube 서비스를 만든다(SEC-015). 쓰기 토큰을 읽는 곳은 프로젝트 전체에서 이 함수뿐이다."""
    creds = authmod.load_credentials("write", settings)
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def env_from_ctx(ctx) -> LiveEnv:
    return LiveEnv(
        conn=ctx.conn, settings=ctx.settings, clock=ctx.clock, run_id=ctx.run_id, say=ctx.say, confirm=ctx.confirm, ui=ctx.ui, logger=ctx.logger,
        make_reader=lambda: make_reader(ctx), make_write_service=lambda: make_write_service(ctx.settings),
    )


# ───────────── 요청 본문 ─────────────

def build_write_body(video_id: str, snippet: dict, new_title: str) -> dict:
    """`videos.update` 본문. 어떤 항목을 보낼지는 이 함수 한 곳에서만 정한다: snippet 전체(깊은 복사) + 제목만 교체(SEC-005)."""
    body = build_update_body(video_id, snippet, new_title)
    for name in NOT_SENT_SNIPPET_FIELDS:
        body["snippet"].pop(name, None)
    return body


def check_body(body: object, video_id: str, snippet: dict, new_title: str) -> None:
    """보내기 직전 본문 검사(9단계): 영상 ID, 새 제목, 그리고 제목 외 모든 항목이 재조회한 snippet과 똑같아야 한다."""
    if not isinstance(body, dict) or set(body) != {"id", "snippet"} or body["id"] != video_id or not isinstance(body["snippet"], dict):
        raise LiveGateError(9, "요청 본문의 구조가 올바르지 않아 중단했습니다.", "프로그램 오류입니다. 로그를 확인하고 알려 주세요.")
    sent = body["snippet"]
    if sent.get("title") != new_title:
        raise LiveGateError(9, "요청 본문의 제목이 새 제목과 다릅니다.", "프로그램 오류입니다. 로그를 확인하고 알려 주세요.")
    expected = {k: v for k, v in snippet.items() if k != "title" and k not in NOT_SENT_SNIPPET_FIELDS}
    actual = {k: v for k, v in sent.items() if k != "title"}
    if actual != expected:
        lost = sorted(set(expected) - set(actual))
        raise LiveGateError(9, "요청 본문이 재조회한 영상 정보를 전부 보존하지 않아 중단했습니다" + (f"(빠진 항목: {', '.join(lost)})" if lost else "") + ".", "설명·태그·카테고리가 지워질 수 있어 보내지 않았습니다. 로그를 확인하고 알려 주세요.")
    if not isinstance(sent.get("categoryId"), str) or not sent["categoryId"]:
        raise LiveGateError(9, "요청 본문에 categoryId가 없어 중단했습니다.", f"`fetch --video {video_id}`로 영상 정보를 다시 가져오세요.")


# ───────────── 실행 상태 ─────────────

@dataclass
class _Run:
    kind: str                       # apply | rollback
    video_id: str
    candidate_id: int | None
    change_id: int | None           # 롤백 대상 변경 번호
    previous_title: str             # 지금(저장본 기준) 제목
    new_title: str
    stored_snippet: dict
    stored_plan_hash: str
    live_flag: bool
    plan: Any = None                # create_plan / plan_rollback 결과(저장본 기준)
    approver: str | None = None
    step: int = 0
    approval: Approval | None = None
    fresh_snippet: dict | None = None
    live_hash: str | None = None
    body: dict | None = None
    record_id: int | None = None    # title_changes.id (planned 행)
    reserve_id: int | None = None
    gates: list[GateOutcome] = field(default_factory=list)


def _run_from_plan(plan: Plan, live_flag: bool) -> _Run:
    return _Run("apply", plan.video_id, plan.candidate_id, None, plan.previous_title, plan.new_title, plan.snippet, plan.plan_hash, live_flag, plan)


def _run_from_rollback(plan: RollbackPlan, live_flag: bool, approver: str | None) -> _Run:
    return _Run("rollback", plan.video_id, plan.candidate_id, plan.change_id, plan.current_title, plan.restore_title, plan.snippet, plan.plan_hash, live_flag, plan, approver)


def _live_hash(run: _Run) -> str:
    """6단계에서 다시 조회한 snippet으로 계획 해시를 새로 계산한다(7단계 비교용)."""
    fresh = run.fresh_snippet
    if run.kind == "apply":
        return compute_plan_hash(run.video_id, run.candidate_id, fresh["title"], run.new_title, fresh)
    return compute_plan_hash(run.video_id, run.candidate_id, fresh["title"], run.new_title, fresh, kind="rollback", change_id=run.change_id)


# ───────────── 1~10단계 ─────────────

def _g1(env: LiveEnv, run: _Run) -> str:
    if run.live_flag is not True:
        raise LiveGateError(1, "--live 플래그가 없어 실제 적용을 하지 않았습니다.", "모의 실행입니다. 실제로 적용하려면 같은 명령에 --live를 붙이세요.")
    return "--live 지정됨"


def _g2(env: LiveEnv, run: _Run) -> str:
    if env.settings.enable_live is not True:
        raise LiveGateError(2, "enable_live가 꺼져 있어 실제 적용을 하지 않았습니다.", "config/settings.local.yaml 에 `live:` 아래 `enable_live: true`를 쓰세요. config/settings.yaml 의 값은 무시됩니다(실수로 커밋되는 사고 방지).")
    return "enable_live=true (settings.local.yaml)"


def _g3(env: LiveEnv, run: _Run) -> str:
    allow = env.settings.live_allowlist
    if not allow:
        raise LiveGateError(3, "live_allowlist가 비어 있어 모든 영상의 실제 적용을 거부합니다.", "처음에는 비공개 테스트 영상 ID 하나만 settings.local.yaml 의 live_allowlist에 넣으세요(SEC-012).")
    if run.video_id not in allow:
        raise LiveGateError(3, f"영상 {sanitize_for_display(run.video_id)}는 live_allowlist에 없어 거부합니다.", "이 영상을 실제로 바꾸려면 settings.local.yaml 의 live_allowlist에 영상 ID를 직접 추가하세요.")
    return "허용 목록에 있음"


def _g4(env: LiveEnv, run: _Run) -> str:
    s = env.settings
    need = s.update_cost + READ_CALLS_PER_APPLY * s.read_cost
    remaining = QuotaManager(env.conn, s, env.clock).remaining()
    if remaining < need:
        raise LiveGateError(4, f"오늘 남은 쿼터({remaining} units)가 필요한 양({need} units)보다 적어 중단했습니다.", RESET_HINT)
    return f"남은 {remaining} units ≥ 필요 {need} units"


def _pending_planned(env: LiveEnv, video_id: str) -> int | None:
    row = env.conn.execute("SELECT id FROM title_changes WHERE video_id = ? AND result = 'planned' ORDER BY id LIMIT 1", (video_id,)).fetchone()
    return None if row is None else int(row[0])


def _g5(env: LiveEnv, run: _Run) -> str:
    stale = _pending_planned(env, run.video_id)
    if stale is not None:
        raise LiveGateError(
            5, f"이 영상에 결과가 확정되지 않은 변경 기록(#{stale}, planned)이 남아 있어 중단했습니다. 이전 실행이 도중에 끊겼을 수 있습니다.",
            f"Studio에서 현재 제목을 확인하고 `fetch --video {run.video_id}`로 정보를 갱신하세요. 이 기록은 자동으로 지우지 않으며, 정리 전에는 이 영상을 적용·롤백할 수 없습니다.",
        )
    if run.kind == "rollback":
        return "롤백은 교체 제한을 적용하지 않음(복구가 막히면 안 됨); 미확정 기록 없음"
    report = check_limits(env.conn, env.settings, run.video_id, env.clock.now())
    if not report.passed:
        raise LiveGateError(5, "교체 제한에 걸려 중단했습니다: " + " / ".join(c.message for c in report.failures), "안내된 시각 이후에 다시 시도하세요(가능한 시각은 위 문구에 있습니다).")
    return "간격·횟수·노출수·하루 건수 통과; 미확정 기록 없음"


def _g6(env: LiveEnv, run: _Run) -> str:
    result = env.make_reader().fetch_videos([run.video_id])
    if not result.rows:
        raise LiveGateError(6, "구글에서 이 영상을 다시 조회하지 못했습니다(삭제·비공개 처리·다른 채널 영상일 수 있음).", f"Studio에서 영상을 확인하고 `fetch --video {run.video_id}`를 다시 실행하세요.")
    fresh = parse_snippet(result.rows[0]["snippet_json"], run.video_id)
    if fresh["title"] != run.previous_title:
        raise LiveGateError(
            6, f"저장해 둔 제목과 지금 구글의 제목이 다릅니다(저장본: {sanitize_for_display(run.previous_title, 60)} / 현재: {sanitize_for_display(fresh['title'], 60)}). Studio에서 바뀐 제목을 덮어쓰지 않으려고 중단했습니다.",
            "방금 조회한 정보가 저장되었습니다. `plan`부터 다시 하세요(필요하면 승인도 새로 받습니다).",
        )
    run.fresh_snippet = fresh
    run.live_hash = _live_hash(run)
    return "구글의 현재 제목이 저장본과 같음"


def _candidate_status(env: LiveEnv, candidate_id: int) -> str | None:
    row = env.conn.execute("SELECT status FROM title_candidates WHERE id = ?", (candidate_id,)).fetchone()
    return None if row is None else row[0]


def _g7(env: LiveEnv, run: _Run) -> str:
    if run.live_hash is None:
        raise LiveGateError(7, "재조회한 영상 정보가 없어 계획 해시를 확인할 수 없습니다.", "프로그램 오류입니다. 로그를 확인하고 알려 주세요.")
    now = env.clock.now()
    if run.kind == "rollback":
        approvals.clean_approver(run.approver)   # 형식이 틀리면 InputError → 7단계 중단
        if run.live_hash != run.stored_plan_hash:
            raise LiveGateError(7, "롤백 계획을 만든 뒤 영상 정보가 바뀌었습니다(계획 해시 불일치).", "`fetch --video`로 최신 정보를 가져온 뒤 `rollback --change N` 계획부터 다시 하세요.")
        return f"확인자 {sanitize_for_display(run.approver, 40)}; 롤백 계획 해시 일치"
    status = _candidate_status(env, run.candidate_id)
    if status != "approved":
        raise LiveGateError(7, f"후보 {run.candidate_id}번이 승인 상태가 아닙니다(상태: {status}).", f"`approve --candidate {run.candidate_id} --approver 이름` 으로 사람의 승인을 받으세요.")
    approval = approvals.load_approval(env.settings, run.video_id, run.candidate_id)
    approvals.verify_approval(approval, env.settings, video_id=run.video_id, candidate_id=run.candidate_id, new_title=run.new_title, plan_hash=run.live_hash, now=now)
    run.approval = approval
    run.approver = approval.approver
    return f"승인자 {sanitize_for_display(approval.approver, 40)}, 만료 전, 미사용, 계획 해시 일치"


def _has_baseline(env: LiveEnv, video_id: str) -> bool:
    return env.conn.execute("SELECT 1 FROM metrics_snapshots WHERE video_id = ? AND phase = 'before' LIMIT 1", (video_id,)).fetchone() is not None


def _g8(env: LiveEnv, run: _Run) -> str:
    if run.kind == "rollback":
        return "해당 없음(롤백)"
    if _has_baseline(env, run.video_id):
        return "변경 전(before) 지표 있음"
    env.say(f"  {badge('caution', env.ui)} 이 영상의 변경 전 지표(기준선)가 없어 나중에 변경 효과를 비교할 수 없습니다. `fetch --metrics --phase before`로 먼저 받아 두는 것이 좋습니다.")
    if not env.confirm(BASELINE_PHRASE):
        raise LiveGateError(8, "변경 전 지표 없이 진행하는 것을 확인받지 못해 중단했습니다.", f"`fetch --video {run.video_id} --metrics --phase before`로 지표를 받은 뒤 다시 하세요.")
    return "변경 전 지표 없음 — 없이 진행하겠다고 직접 확인함"


def _g9(env: LiveEnv, run: _Run) -> str:
    fresh = run.fresh_snippet
    try:
        validate_new_title(run.new_title, env.settings, check_length=run.kind == "apply")
    except YtError as exc:
        raise LiveGateError(9, f"새 제목이 쓰기 규격을 통과하지 못했습니다: {exc.message}", exc.next_step) from exc
    run.body = build_write_body(run.video_id, fresh, run.new_title)
    check_body(run.body, run.video_id, fresh, run.new_title)
    kept = sorted(k for k in fresh if k != "title" and k not in NOT_SENT_SNIPPET_FIELDS)
    return f"snippet 전체 + 제목만 교체(보존 항목 {len(kept)}개)"


def _g10(env: LiveEnv, run: _Run) -> str:
    say, ui = env.say, env.ui
    say("")
    say("★ 실제 적용(LIVE) 직전 요약 ★")
    say(f"작업: {'제목 변경' if run.kind == 'apply' else '제목 롤백(이전 제목 복원)'}   영상: {sanitize_for_display(run.video_id)}")
    say(f"변경 전: {sanitize_for_display(run.fresh_snippet['title'])}")
    say(f"변경 후: {sanitize_for_display(run.new_title)}")
    say(f"승인/확인자: {sanitize_for_display(run.approver, 40)}")
    say("조건 확인 결과")
    for g in run.gates:
        say(_gate_line(g, ui))
    say(f"{badge('caution', ui)} 이 작업은 되돌릴 수 있지만 구글에 바로 반영됩니다. 영상 ID를 확인해 주세요.")
    if not env.confirm(run.video_id):
        raise LiveGateError(10, "영상 ID 확인이 완료되지 않아 아무것도 바꾸지 않았습니다.", "적용하려면 영상 ID를 화면 그대로 입력하세요.")
    return "사람이 영상 ID를 직접 입력해 확인함"


_PRE_GATES: tuple[tuple[int, Callable[[LiveEnv, _Run], str]], ...] = (
    (1, _g1), (2, _g2), (3, _g3), (4, _g4), (5, _g5), (6, _g6), (7, _g7), (8, _g8), (9, _g9), (10, _g10),
)


# ───────────── 출력 ─────────────

def _gate_line(g: GateOutcome, ui: UiOptions) -> str:
    mark = {"pass": badge("pass", ui), "block": badge("block", ui), "warn": badge("caution", ui), "pending": "[ 대기 ]", "skip": "[해당 없음]"}[g.status]
    return f"  {mark} {g.step:>2}/{LAST_STEP} {STEP_LABELS[g.step]}: {sanitize_for_display(g.detail, 300)}"


def _pass(env: LiveEnv, run: _Run, step: int, detail: str) -> None:
    out = GateOutcome(step, "skip" if detail.startswith("해당 없음") else "pass", detail)
    run.gates.append(out)
    env.logger.info("안전 게이트 %d단계 통과(%s)", step, run.kind)
    if step >= 10:   # 1~9단계 결과는 10단계의 요약 표(또는 중단 시 아래 표)로 한 번에 보여 준다
        env.say(_gate_line(out, env.ui))


# ───────────── 중단 기록 ─────────────

def _record_abort(env: LiveEnv, run: _Run, step: int, message: str) -> None:
    """막힌 시도를 `aborted` 행으로 남긴다(감사). 기록 자체가 실패해도 원래 중단 사유를 가리지 않는다."""
    try:
        record_aborted(
            env.conn, change_type=run.kind, video_id=run.video_id, candidate_id=run.candidate_id, previous_title=run.previous_title, new_title=run.new_title,
            plan_hash=run.live_hash or run.stored_plan_hash, error_code=f"GATE-{step:02d}", reason=sanitize_for_display(message, 300), run_id=env.run_id, now=env.clock.now(), approver=run.approver,
        )
    except YtError as exc:
        env.logger.warning("중단 기록을 남기지 못했습니다: %s", exc.message)


def _abort(env: LiveEnv, run: _Run, exc: BaseException) -> BaseException:
    """1~11단계에서 난 오류를 기록하고 돌려줄 예외(종료 코드 3)를 정한다. 사용자 중단(Ctrl+C) 같은 BaseException은 기록 후 그대로 돌려준다."""
    step = run.step
    if isinstance(exc, LiveGateError):
        wrapped: BaseException = exc
        message = exc.message
    elif isinstance(exc, YtError):
        wrapped = LiveGateError(step, f"{step}단계({STEP_LABELS[step]})에서 중단했습니다: {exc.message}", exc.next_step, cause=exc.code)
        message = exc.message
    else:
        wrapped, message = exc, f"예상하지 못한 오류({type(exc).__name__})"
    if run.record_id is None:
        _record_abort(env, run, step, message)
    env.logger.warning("안전 게이트 %d단계에서 중단(%s)", step, run.kind)
    if isinstance(exc, Exception):
        _show_block(env, run, step, message)
    return wrapped


def _show_block(env: LiveEnv, run: _Run, step: int, message: str) -> None:
    """중단 시 화면: 통과한 조건과 막힌 조건을 한 표로 보여 준다(SCR-005 '하나라도 [차단]이면 이유 출력 후 종료')."""
    if step <= 9:
        env.say("조건 확인 결과")
        for g in run.gates:
            env.say(_gate_line(g, env.ui))
    env.say(_gate_line(GateOutcome(step, "block", message), env.ui))
    env.say(f"{badge('block', env.ui)} {step}단계에서 막혀 아무것도 바꾸지 않았습니다.")


# ───────────── 11단계: 백업·기록·선예약 ─────────────

def _step11(env: LiveEnv, run: _Run) -> Any:
    """사람이 확인한 뒤에야 쓰기 토큰을 읽는다. 쓰기 직전의 모든 준비가 끝나야만 서비스를 돌려준다."""
    s, now = env.settings, env.clock.now()
    service = env.make_write_service()
    try:
        dbmod.backup(env.conn, s.data_dir / "backups", now)
    except (OSError, sqlite3.Error) as exc:
        raise LiveGateError(11, "쓰기 전 DB 사본(백업)을 만들지 못해 중단했습니다.", "data/backups 폴더의 쓰기 권한과 디스크 공간을 확인하세요.", cause=type(exc).__name__) from exc
    if run.kind == "apply":
        run.approval = approvals.mark_used(s, run.approval, now)   # 호출이 시작되기 전에 승인을 소진한다(최대 1회)
    fresh = run.fresh_snippet
    if run.kind == "apply":
        plan = dataclasses.replace(run.plan, snippet=fresh, snippet_sha256=snippet_hash(fresh), previous_title=fresh["title"], plan_hash=run.live_hash, body=run.body)
        run.record_id = begin_change(env.conn, s, plan, approver=run.approval.approver, approved_at=run.approval.approved_at, run_id=env.run_id, now=now, reason=f"후보 #{run.candidate_id} 적용")
    else:
        plan = dataclasses.replace(run.plan, snippet=fresh, snippet_sha256=snippet_hash(fresh), current_title=fresh["title"], plan_hash=run.live_hash, body=run.body)
        run.record_id = begin_rollback(env.conn, plan, approver=approvals.clean_approver(run.approver), typed_video_id=run.video_id, run_id=env.run_id, now=now)
    try:
        run.reserve_id = QuotaManager(env.conn, s, env.clock).reserve("videos.update", s.update_cost, env.run_id)
    except YtError as exc:
        finish_change(env.conn, run.record_id, "aborted", env.clock.now(), error_code="GATE-11")
        raise LiveGateError(11, f"쿼터를 예약하지 못해 호출하지 않았습니다: {exc.message}", exc.next_step, cause=exc.code) from exc
    return service


# ───────────── 12단계: 유일한 videos.update ─────────────

def _send_update(service: Any, body: dict) -> Any:
    """이 프로젝트에서 YouTube 제목을 바꾸는 유일한 호출(SEC-001). 다른 모듈에는 같은 호출이 없어야 한다."""
    return service.videos().update(part="snippet", body=body).execute()


_REASON_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")


def _http_reason(exc: HttpError) -> str:
    try:
        content = exc.content.decode("utf-8", "replace") if isinstance(exc.content, bytes) else str(exc.content)
        reason = json.loads(content)["error"]["errors"][0]["reason"]
    except Exception:
        return ""
    return reason if isinstance(reason, str) and _REASON_RE.match(reason) else ""


def classify_write_error(exc: Exception) -> YtError:
    """외부 예외를 우리 오류로 바꾼다. 응답 본문·토큰은 메시지에 넣지 않고 상태와 reason 코드·예외 이름만 남긴다."""
    if isinstance(exc, HttpError):
        status = int(getattr(exc.resp, "status", 0) or 0)
        reason = _http_reason(exc)
        tag = f"HTTP {status}" + (f" {reason}" if reason else "")
        if status == 403 and reason in ("quotaExceeded", "dailyLimitExceeded"):
            return QuotaError("구글이 오늘 API 쿼터를 모두 썼다고 응답했습니다. 제목은 바뀌지 않았습니다.", RESET_HINT, cause=tag)
        if status in (401, 403):
            return AuthError("구글이 쓰기 로그인 정보나 권한을 받아들이지 않았습니다. 제목은 바뀌지 않았습니다.", "`python -m ytitle auth --write`로 다시 로그인하세요.", cause=tag)
        if status == 429:
            return WriteApiError("구글이 요청이 너무 많다고 응답했습니다. 제목은 바뀌지 않았습니다.", "잠시 후 다시 시도하세요.", retryable=True, definite=True, cause=tag)
        if status >= 500:
            return WriteApiError("구글 서버가 응답하지 못했습니다. 제목이 바뀌었는지 알 수 없습니다.", "Studio에서 현재 제목을 확인하세요.", retryable=True, definite=False, cause=tag)
        return WriteApiError("구글이 제목 변경 요청을 받아들이지 않았습니다. 제목은 바뀌지 않았습니다.", "같은 오류가 반복되면 로그(data/logs/ytitle.log)를 확인하고 알려 주세요.", retryable=False, definite=True, cause=tag)
    if isinstance(exc, (OSError, httplib2.HttpLib2Error)):
        return WriteApiError("구글에 연결하지 못했거나 응답이 끊겼습니다. 제목이 바뀌었는지 알 수 없습니다.", "인터넷 연결을 확인하고 Studio에서 현재 제목을 확인하세요.", retryable=True, definite=False, cause=type(exc).__name__)
    return WriteApiError("제목 변경 도중 예상하지 못한 오류가 생겼습니다. 제목이 바뀌었는지 알 수 없습니다.", "Studio에서 현재 제목을 확인하세요.", retryable=False, definite=False, cause=type(exc).__name__)


@dataclass
class _CallState:
    reserve_id: int | None          # 11단계에서 선예약한 첫 호출분
    indeterminate: bool = False     # 한 번이라도 '반영됐는지 알 수 없는' 실패가 있었는가


def _send_with_retry(env: LiveEnv, run: _Run, service: Any, state: _CallState) -> Any:
    """쿼터 선예약 후 호출한다. 재시도(최대 2회)마다 새로 예약한다(실패해도 차감 유지, ADR-008)."""
    quota = QuotaManager(env.conn, env.settings, env.clock)

    def attempt() -> Any:
        if state.reserve_id is None:
            state.reserve_id = quota.reserve("videos.update", env.settings.update_cost, env.run_id)
        rid, state.reserve_id = state.reserve_id, None
        try:
            response = _send_update(service, run.body)
        except BaseException as exc:
            quota.mark(rid, "failed")
            if not isinstance(exc, Exception):
                state.indeterminate = True
                raise
            err = classify_write_error(exc)
            if isinstance(err, WriteApiError) and not err.definite:
                state.indeterminate = True
            raise err from None
        quota.mark(rid, "ok")
        return response

    return call_with_retry(attempt, sleep=env.sleep)


# ───────────── 13~14단계: 사후 검증과 기록 ─────────────

def compare_after(before: dict, after: dict, expected_title: str) -> dict:
    """제목 반영과 설명·태그·카테고리 보존을 비교한다(SEC-010)."""
    preserved = {k: before.get(k, _MISSING) == after.get(k, _MISSING) for k in VERIFY_PRESERVED_FIELDS}
    other = sorted(k for k in (set(before) | set(after)) if k not in VERIFY_PRESERVED_FIELDS and k not in ("title", "localized") and before.get(k, _MISSING) != after.get(k, _MISSING))
    title_ok = after.get("title") == expected_title
    return {"ok": bool(title_ok and all(preserved.values())), "checked": True, "title_ok": title_ok, "preserved": preserved, "other_changed": other}


def _reread(env: LiveEnv, video_id: str) -> dict | None:
    """구글에서 영상 snippet을 다시 읽는다. 읽지 못하면 None(예외 없음)."""
    try:
        result = env.make_reader().fetch_videos([video_id])
        if not result.rows:
            return None
        snippet = json.loads(result.rows[0]["snippet_json"])
    except Exception:
        return None
    return snippet if isinstance(snippet, dict) else None


def _verify_and_record(env: LiveEnv, run: _Run, after: dict | None, note: str = "") -> LiveResult:
    run.step = 13
    if after is None:
        after = _reread(env, run.video_id)
    if after is None:
        verify = {"ok": False, "checked": False, "reason": "재조회에 실패해 제목 반영과 보존을 확인하지 못함"}
    else:
        verify = compare_after(run.fresh_snippet, after, run.new_title)
    if note:
        verify["note"] = note
    run.step = 14
    try:
        finish_change(env.conn, run.record_id, "success", env.clock.now(), verify_result=verify)
    except YtError:
        env.say(f"{badge('fail', env.ui)} 구글에는 반영되었을 수 있으나 변경 기록(#{run.record_id})을 완료로 바꾸지 못했습니다. `fetch --video {run.video_id}`로 현재 제목을 확인하고 DB 파일 상태를 점검하세요.")
        raise
    env.logger.info("%s 완료(검증 %s)", run.kind, "통과" if verify["ok"] else "실패")
    result = LiveResult(run.kind, run.video_id, run.record_id, verify, bool(verify["ok"]), run.gates)
    _print_result(env, run, result)
    return result


def _print_result(env: LiveEnv, run: _Run, result: LiveResult) -> None:
    say, ui, v = env.say, env.ui, result.verify
    say("")
    say(progress_steps(["백업(DB 사본)", "videos.update 호출", "재조회 검증"], 3))
    if not v.get("checked"):
        say(f"{badge('fail', ui)} 호출은 성공했지만 사후 검증을 하지 못했습니다: {sanitize_for_display(v.get('reason'))}")
    elif v["ok"]:
        say(f"{badge('pass', ui)} 제목 반영 확인, 설명·태그·카테고리 등 보존 확인")
    else:
        failed = [k for k, ok in v["preserved"].items() if not ok]
        say(f"{badge('fail', ui)} ★ 사후 검증 실패: " + ("제목이 새 제목과 다릅니다. " if not v["title_ok"] else "") + (f"보존되지 않은 항목: {', '.join(failed)}. " if failed else ""))
    if v.get("other_changed"):
        say(f"{badge('caution', ui)} 그 밖에 값이 달라진 항목(실패로 보지는 않음): {', '.join(sanitize_for_display(k, 40) for k in v['other_changed'])}")
    if v.get("note"):
        say(f"{badge('caution', ui)} {sanitize_for_display(v['note'])}")
    label = "제목 변경" if run.kind == "apply" else "롤백"
    if v.get("ok"):
        say(f"{badge('done', ui)} {label}을 마쳤습니다. 변경 번호: {result.change_id}")
    else:
        say(f"{badge('fail', ui)} {label} 호출은 끝났지만 검증이 통과하지 못했습니다. 변경 번호: {result.change_id}")
        say("자동으로 되돌리지 않았습니다(쓰기는 사람이 확인해야 합니다). 먼저 Studio에서 영상의 제목·설명·태그를 확인하세요.")
    if run.kind == "apply":
        say(f"되돌리려면: `python -m ytitle rollback --change {result.change_id} --approver 이름 --live`")


def _finish_failed(env: LiveEnv, run: _Run, exc: YtError) -> None:
    """구글이 요청을 처리하지 않았음이 분명한 실패: 이력을 failed로 끝낸다(후보 상태는 그대로)."""
    code = (exc.cause or exc.code)[:80]
    finish_change(env.conn, run.record_id, "failed", env.clock.now(), error_code=code)
    env.say(f"{badge('fail', env.ui)} 제목을 바꾸지 못했습니다(변경 번호 {run.record_id}, 기록: failed). 구글은 요청을 처리하지 않았습니다.")


def _handle_call_failure(env: LiveEnv, run: _Run, exc: BaseException, state: _CallState) -> LiveResult:
    if isinstance(exc, YtError) and not state.indeterminate:
        _finish_failed(env, run, exc)    # 구글이 처리하지 않았음이 분명한 실패
        raise exc
    if not isinstance(exc, Exception):   # 사용자 중단(Ctrl+C) 등: 더 호출하지 않고 미확정으로 남긴다
        env.say(f"{badge('fail', env.ui)} 중단되었습니다. 제목이 바뀌었는지 알 수 없어 변경 기록 #{run.record_id}은 결과 미확정(planned)으로 남깁니다. Studio에서 현재 제목을 확인하세요.")
        raise exc
    # 반영됐는지 알 수 없다: 한 번 읽어 보고, 새 제목이 확인되면 성공으로 이어서 검증한다. 아니면 planned로 남긴다(자동 정리 없음).
    after = _reread(env, run.video_id)
    if after is not None and after.get("title") == run.new_title:
        return _verify_and_record(env, run, after, note="호출 도중 오류가 있었지만 재조회로 새 제목이 반영된 것을 확인했습니다.")
    env.say(f"{badge('fail', env.ui)} 호출 결과를 확인하지 못했습니다. 제목이 실제로 바뀌었을 수도 있습니다. 변경 기록 #{run.record_id}은 결과 미확정(planned)으로 남깁니다.")
    raise WriteApiError(
        "제목 변경 호출의 결과를 확인하지 못했습니다(반영됐을 수도 있습니다).",
        f"Studio에서 현재 제목을 확인하고 `fetch --video {run.video_id}`로 정보를 갱신하세요. 미확정 기록(#{run.record_id})은 자동으로 지우지 않으며, 정리 전에는 이 영상을 적용·롤백할 수 없습니다.",
        retryable=False, definite=False, cause=getattr(exc, "cause", "") or type(exc).__name__,
    ) from None


# ───────────── 실행 엔진 ─────────────

def _execute(env: LiveEnv, run: _Run) -> LiveResult:
    env.say(f"쓰기 안전 게이트 {LAST_STEP}단계를 순서대로 확인합니다. 하나라도 실패하면 아무것도 바꾸지 않습니다.")
    try:
        for number, gate in _PRE_GATES:
            run.step = number
            _pass(env, run, number, gate(env, run))
        run.step = 11
        service = _step11(env, run)
        _pass(env, run, 11, "쓰기 토큰 로드, DB 사본, 승인 소진, planned 기록, 쿼터 예약 완료" if run.kind == "apply" else "쓰기 토큰 로드, DB 사본, planned 기록, 쿼터 예약 완료")
    except BaseException as exc:
        err = _abort(env, run, exc)
        if err is exc:
            raise
        raise err from exc
    run.step = 12
    state = _CallState(run.reserve_id)
    try:
        _send_with_retry(env, run, service, state)
    except BaseException as exc:
        return _handle_call_failure(env, run, exc, state)
    _pass(env, run, 12, "videos.update 호출 성공")
    return _verify_and_record(env, run, None)


def apply_live(env: LiveEnv, candidate_id: int, *, live_flag: bool = True) -> LiveResult:
    """`apply --live`: 14단계 게이트를 거쳐 후보 1건의 제목을 바꾼다."""
    try:
        plan = create_plan(env.conn, env.settings, env.clock, candidate_id)
    except YtError as exc:
        _record_unplanned_apply(env, candidate_id, exc)
        raise
    return _execute(env, _run_from_plan(plan, live_flag))


def rollback_live(env: LiveEnv, change_id: int, *, approver: str | None, live_flag: bool = True) -> LiveResult:
    """`rollback --live`: 성공한 적용 하나를 되돌린다. 같은 엔진을 쓰되 교체 제한·변경 전 지표 확인은 면제한다."""
    try:
        plan = plan_rollback(env.conn, env.settings, env.clock, change_id)
    except YtError as exc:
        _record_unplanned_rollback(env, change_id, exc)
        raise
    return _execute(env, _run_from_rollback(plan, live_flag, approver))


def _record_unplanned_apply(env: LiveEnv, candidate_id: int, exc: YtError) -> None:
    """계획을 만들지 못한 시도(차단된 후보 등)도 감사 기록으로 남긴다. 후보나 영상 정보를 알 수 없으면 남기지 않는다."""
    try:
        cand = env.conn.execute("SELECT video_id, candidate_title FROM title_candidates WHERE id = ?", (candidate_id,)).fetchone()
        video = env.conn.execute("SELECT title FROM videos WHERE video_id = ?", (cand["video_id"],)).fetchone() if cand else None
        if cand is not None:
            record_aborted(env.conn, change_type="apply", video_id=cand["video_id"], candidate_id=candidate_id, previous_title=video["title"] if video else "", new_title=cand["candidate_title"],
                           plan_hash=None, error_code="PLAN", reason=sanitize_for_display(exc.message, 300), run_id=env.run_id, now=env.clock.now())
    except (YtError, sqlite3.Error) as err:
        env.logger.warning("중단 기록을 남기지 못했습니다: %s", getattr(err, "message", type(err).__name__))


def _record_unplanned_rollback(env: LiveEnv, change_id: int, exc: YtError) -> None:
    try:
        row = env.conn.execute("SELECT video_id, candidate_id, previous_title, new_title FROM title_changes WHERE id = ?", (change_id,)).fetchone()
        if row is not None:
            record_aborted(env.conn, change_type="rollback", video_id=row["video_id"], candidate_id=row["candidate_id"], previous_title=row["new_title"], new_title=row["previous_title"],
                           plan_hash=None, error_code="PLAN", reason=sanitize_for_display(exc.message, 300), run_id=env.run_id, now=env.clock.now())
    except (YtError, sqlite3.Error) as err:
        env.logger.warning("중단 기록을 남기지 못했습니다: %s", getattr(err, "message", type(err).__name__))


# ───────────── 모의 실행(--live 없음) ─────────────

def preview_apply(env: LiveEnv, plan: Plan) -> list[GateOutcome]:
    """`apply`(--live 없음)가 보여 줄 게이트 표. 구글에 연결하지 않고 DB·설정·승인 파일만 읽는다(아무것도 쓰지 않음).

    6·10~14단계는 실제 적용 때만 하므로 '대기'로 표시한다. 7·9단계는 마지막 fetch로 저장된 영상 정보로 미리 확인한다."""
    run = _run_from_plan(plan, False)
    run.fresh_snippet = plan.snippet
    run.live_hash = _live_hash(run)
    out: list[GateOutcome] = []
    for number in range(1, LAST_STEP + 1):
        run.step = number
        if number == 1:
            out.append(GateOutcome(1, "block", "모의 실행입니다(--live 없음). 아래 조건은 실제 적용 때 이 순서로 다시 확인합니다."))
        elif number == 6:
            out.append(GateOutcome(6, "pending", "실제 적용 때 구글에서 현재 제목을 다시 조회해 저장본과 비교합니다."))
        elif number == 8:
            if _has_baseline(env, run.video_id):
                out.append(GateOutcome(8, "pass", "변경 전(before) 지표 있음"))
            else:
                out.append(GateOutcome(8, "warn", "변경 전 지표가 없습니다. 실제 적용 때 없이 진행한다는 확인 입력이 필요합니다."))
        elif number >= 10:
            out.append(GateOutcome(number, "pending", "실제 적용 때 진행합니다."))
        else:
            try:
                detail = _PRE_GATES[number - 1][1](env, run)
            except YtError as exc:
                out.append(GateOutcome(number, "block", f"{exc.message} → {exc.next_step}" if exc.next_step else exc.message))
            else:
                out.append(GateOutcome(number, "pass", detail + (" (저장된 영상 정보 기준)" if number in (7, 9) else "")))
    return out


def gate_line(g: GateOutcome, ui: UiOptions) -> str:
    return _gate_line(g, ui)
