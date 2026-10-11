"""제목 변경 계획 생성(FR-008, FR-009, SEC-005, SEC-009, POL-003). 이 모듈은 계산만 하고 아무것도 호출·기록하지 않는다.

- 현재 snippet 전체는 DB `videos.snippet_json`(마지막 `fetch` 결과)에서 읽는다(네트워크 호출 없음).
- 요청 본문은 그 snippet 전체를 그대로 두고 `title`만 바꾼 것이다(description·tags·categoryId 등 보존).
- `plan_hash`는 canonical JSON(키 정렬, 공백 없음, UTF-8) 위의 SHA-256이다.

YouTube 쓰기 호출은 이 단위에 없다. 실제 호출은 WU-5 `live_guard.py`에서만 이루어지며(SEC-001), 여기에는
호출 자리를 표시하는 `UpdateGateway` 규약과 항상 거부하는 `execute_update`만 둔다.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from ytitle.config import Settings
from ytitle.errors import DatabaseError, InputError, SafetyGateError
from ytitle.limits import LimitReport, check_limits
from ytitle.quota import QuotaManager
from ytitle.textsafe import char_count
from ytitle.timeutil import parse_iso

STALE_AFTER = timedelta(hours=24)       # EVT-004: 저장 시각이 이보다 오래되면 fetch를 다시 하라고 경고
PLAN_HASH_VERSION = 1
READ_CALLS_PER_APPLY = 2                # DESIGN 5-2: 6단계와 13단계 재조회
_BIDI_CONTROLS = frozenset(chr(c) for c in list(range(0x202A, 0x202F)) + list(range(0x2066, 0x206A)))


# ───────────── canonical JSON / 해시 ─────────────

def canonical_json(obj: Any) -> str:
    """키 정렬·공백 없음·한글 그대로(UTF-8)인 JSON. 같은 내용이면 항상 같은 문자열이다."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def snippet_hash(snippet: dict) -> str:
    return sha256_hex(canonical_json(snippet))


def compute_plan_hash(video_id: str, candidate_id: int | None, previous_title: str, new_title: str, snippet: dict, *, kind: str = "apply", change_id: int | None = None) -> str:
    """계획 해시(DESIGN 4-1 EVT-004, SEC-014). WU-5는 6단계에서 다시 조회한 snippet으로 이 함수를 그대로 써서 비교한다.

    입력: 영상 ID, 후보 ID, 이전 제목, 새 제목, snippet 전체의 해시. 설계서 정의에 `v`(해시 규격 버전)와 `kind`(apply/rollback 구분)를 더해
    적용용 해시가 롤백 계획에 재사용되지 못하게 했다. 롤백은 대상 변경 번호(`change_id`)도 묶는다.
    """
    payload = {
        "v": PLAN_HASH_VERSION,
        "kind": kind,
        "video_id": video_id,
        "candidate_id": candidate_id,
        "change_id": change_id,
        "previous_title": previous_title,
        "new_title": new_title,
        "snippet_sha256": snippet_hash(snippet),
    }
    return sha256_hex(canonical_json(payload))


# ───────────── 입력 검증 ─────────────

def validate_new_title(title: object, settings: Settings, *, check_length: bool = True) -> str:
    """검증기를 통과한 제목이라도 쓰기 직전 마지막 방어선으로 최소 규격을 다시 확인한다(YouTube 규격).

    `check_length=False`는 롤백이 '원래 제목'을 되돌릴 때 쓴다: 설정을 나중에 낮춰도 복원이 막히면 안 된다."""
    if not isinstance(title, str) or not title.strip():
        raise InputError("새 제목이 비어 있습니다.", "후보 파일의 제목을 확인하세요.")
    if "<" in title or ">" in title:
        raise InputError("제목에는 < 또는 > 를 쓸 수 없습니다(YouTube 규격).", "후보 제목에서 해당 기호를 지우고 `validate`를 다시 실행하세요.")
    if any(ch in _BIDI_CONTROLS or (ord(ch) < 32 or 0x7F <= ord(ch) < 0xA0) for ch in title):
        raise InputError("제목에 제어 문자가 들어 있어 사용할 수 없습니다.", "후보 제목에서 보이지 않는 문자를 지우세요.")
    if check_length and char_count(title) > settings.hard_max_chars:
        raise InputError(f"제목이 상한({settings.hard_max_chars}자)을 넘습니다.", "제목을 줄이고 `validate`를 다시 실행하세요.")
    return title


def parse_snippet(raw: object, video_id: str) -> dict:
    """DB의 snippet_json을 읽어 쓰기 본문의 재료로 쓸 수 있는지 확인한다(깨졌으면 거부)."""
    try:
        snippet = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        snippet = None
    if not isinstance(snippet, dict) or not isinstance(snippet.get("title"), str) or not snippet["title"]:
        raise InputError(f"저장된 영상 정보가 올바르지 않습니다: {video_id}", f"`fetch --video {video_id}`로 영상 정보를 다시 가져오세요.")
    if not isinstance(snippet.get("categoryId"), str) or not snippet["categoryId"]:
        # 영상 snippet 쓰기(part=snippet)는 categoryId가 없으면 실패하거나 값을 지울 수 있어 쓰기 본문을 만들지 않는다.
        raise InputError(f"저장된 영상 정보에 categoryId가 없습니다: {video_id}", f"`fetch --video {video_id}`로 영상 정보를 다시 가져오세요.")
    return snippet


def build_update_body(video_id: str, snippet: dict, new_title: str) -> dict:
    """요청 본문: snippet 전체(깊은 복사) + 제목만 교체(SEC-005, FR-009). 입력 snippet은 바뀌지 않는다."""
    body_snippet = copy.deepcopy(snippet)
    body_snippet["title"] = new_title
    return {"id": video_id, "snippet": body_snippet}


def load_video_row(conn: sqlite3.Connection, video_id: str) -> sqlite3.Row:
    try:
        row = conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError("저장된 영상 정보를 읽지 못했습니다.", "data 폴더의 DB 파일을 확인하세요.", cause=type(exc).__name__) from exc
    if row is None:
        raise InputError(f"저장된 영상 정보가 없습니다: {video_id}", f"`fetch --video {video_id}`로 영상 정보를 먼저 가져오세요.")
    return row


def is_stale(fetched_at: object, now) -> bool:
    """영상 정보 저장 시각이 24시간보다 오래됐거나 읽을 수 없으면 오래된 것으로 본다(보수적)."""
    try:
        return now - parse_iso(str(fetched_at)) > STALE_AFTER
    except ValueError:
        return True


def sequential_exclusions(row: sqlite3.Row, settings: Settings) -> tuple[str, ...]:
    """공식 A/B가 어려운 영상군(POL-003): 비공개·아동용·예약 라이브/프리미어·Shorts 가능성. 모르는 값은 제외 쪽으로 본다."""
    reasons = []
    privacy = row["privacy_status"]
    if privacy is None:
        reasons.append("공개 상태를 알 수 없음")
    elif privacy == "private":
        reasons.append("비공개 영상")
    kids = row["made_for_kids"]
    if kids is None:
        reasons.append("아동용 여부를 알 수 없음")
    elif kids == 1:
        reasons.append("아동용 영상")
    if row["live_broadcast_content"] in ("upcoming", "live"):
        reasons.append("예약 라이브·프리미어 또는 라이브 중")
    duration = row["duration_sec"]
    if duration is None:
        reasons.append("영상 길이를 알 수 없어 Shorts 여부를 판별할 수 없음")
    elif duration <= settings.shorts_max_seconds:
        reasons.append(f"Shorts 가능성({settings.shorts_max_seconds}초 이하)")
    return tuple(reasons)


# ───────────── 계획 ─────────────

@dataclass(frozen=True)
class QuotaEstimate:
    needed: int
    remaining: int

    @property
    def enough(self) -> bool:
        return self.remaining >= self.needed


@dataclass(frozen=True)
class Plan:
    candidate_id: int
    video_id: str
    previous_title: str
    new_title: str
    snippet: dict
    snippet_sha256: str
    plan_hash: str
    body: dict
    preserved_fields: tuple[str, ...]
    fetched_at: str
    stale: bool
    validation_result: str
    dictionary_hash: str | None
    reasons: tuple[tuple[str, str, str], ...]
    limits: LimitReport
    quota: QuotaEstimate
    exclusions: tuple[str, ...]
    exclusions_enforced: bool

    @property
    def ready(self) -> bool:
        """제한·쿼터를 모두 통과했는가(승인 단계로 넘어갈 수 있는가). 순차 교체 모드의 제외 영상은 create_plan에서 이미 거부된다."""
        return self.limits.passed and self.quota.enough


def _load_candidate(conn: sqlite3.Connection, candidate_id: int) -> sqlite3.Row:
    try:
        row = conn.execute("SELECT * FROM title_candidates WHERE id = ?", (candidate_id,)).fetchone()
    except sqlite3.Error as exc:
        raise DatabaseError("후보 정보를 읽지 못했습니다.", "data 폴더의 DB 파일을 확인하세요.", cause=type(exc).__name__) from exc
    if row is None:
        raise InputError(f"후보 번호 {candidate_id}번이 없습니다.", "`validate --all`을 실행해 출력된 '후보번호'를 사용하세요.")
    return row


def _parse_reasons(raw: object) -> tuple[tuple[str, str, str], ...]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else []
        return tuple((str(c), str(s), str(m)) for c, s, m in data)
    except (ValueError, TypeError):
        return (("REASONS_UNREADABLE", "warn", "검증 사유를 읽을 수 없습니다. validate를 다시 실행하세요."),)


def assert_candidate_planable(cand: sqlite3.Row) -> None:
    """차단·미검증·이미 처리된 후보는 계획조차 만들지 않는다(fail-closed)."""
    cid, status, result = cand["id"], cand["status"], cand["validation_result"]
    if status == "blocked" or result == "block":
        raise SafetyGateError(f"후보 {cid}번은 검증에서 차단되어 계획을 만들 수 없습니다.", "후보 제목을 고친 뒤 `validate`를 다시 실행하세요(차단 사유는 validate 리포트에 있습니다).")
    if status in ("applied", "evaluated", "rolled_back"):
        raise SafetyGateError(f"후보 {cid}번은 이미 처리된 후보입니다(상태: {status}).", "새 제목이 필요하면 후보 파일에 추가한 뒤 `validate`를 다시 실행하세요.")
    if status not in ("filtered", "approved") or result not in ("pass", "warn"):
        raise SafetyGateError(f"후보 {cid}번은 아직 검증을 통과하지 않았습니다(상태: {status}).", "`validate --file candidates/영상ID.json`을 먼저 실행하세요.")


def create_plan(conn: sqlite3.Connection, settings: Settings, clock, candidate_id: int) -> Plan:
    """후보 하나의 변경 계획을 만든다. DB는 읽기만 하고, 네트워크는 쓰지 않는다."""
    cand = _load_candidate(conn, candidate_id)
    assert_candidate_planable(cand)
    video_id = cand["video_id"]
    row = load_video_row(conn, video_id)
    snippet = parse_snippet(row["snippet_json"], video_id)
    previous_title = snippet["title"]
    if row["title"] != previous_title:
        raise InputError(f"저장된 영상 정보가 서로 맞지 않습니다: {video_id}", f"`fetch --video {video_id}`로 영상 정보를 다시 가져오세요.")
    new_title = validate_new_title(cand["candidate_title"], settings)
    if new_title == previous_title:
        raise InputError("새 제목이 현재 제목과 같아 바꿀 내용이 없습니다.", "다른 후보를 선택하세요(같은 제목을 쓰면 쿼터와 변경 횟수만 소모됩니다).")

    now = clock.now()
    exclusions = sequential_exclusions(row, settings)
    if settings.sequential_enabled and exclusions:
        raise SafetyGateError("순차 교체 모드에서 제외되는 영상입니다: " + ", ".join(exclusions), "이 영상은 순차 교체 대상에서 빼거나, 사유를 확인한 뒤 설정을 조정하세요(POL-003).")

    quota = QuotaManager(conn, settings, clock)
    return Plan(
        candidate_id=candidate_id,
        video_id=video_id,
        previous_title=previous_title,
        new_title=new_title,
        snippet=snippet,
        snippet_sha256=snippet_hash(snippet),
        plan_hash=compute_plan_hash(video_id, candidate_id, previous_title, new_title, snippet),
        body=build_update_body(video_id, snippet, new_title),
        preserved_fields=tuple(sorted(k for k in snippet if k != "title")),
        fetched_at=str(row["fetched_at"]),
        stale=is_stale(row["fetched_at"], now),
        validation_result=cand["validation_result"],
        dictionary_hash=cand["dictionary_hash"],
        reasons=_parse_reasons(cand["validation_reasons_json"]),
        limits=check_limits(conn, settings, video_id, now),
        quota=QuotaEstimate(settings.update_cost + READ_CALLS_PER_APPLY * settings.read_cost, quota.remaining()),
        exclusions=exclusions,
        exclusions_enforced=settings.sequential_enabled,
    )


# ───────────── 쓰기 자리(미구현) ─────────────

class UpdateGateway(Protocol):
    """WU-5 `live_guard`가 구현할 쓰기 규약. 이 단위에는 구현이 없다."""

    def update_snippet(self, body: dict) -> dict: ...


def execute_update(*_args: object, **_kwargs: object) -> None:
    """실제 쓰기는 WU-5 live_guard의 14단계 게이트 안에서만 가능하다. 여기서는 어떤 경우에도 호출하지 않고 거부한다(SEC-001)."""
    raise SafetyGateError("제목 변경 실행은 아직 활성화되지 않았습니다.", "실제 적용은 안전 게이트(live_guard)가 구현된 뒤 `apply --live`에서만 가능합니다.")
