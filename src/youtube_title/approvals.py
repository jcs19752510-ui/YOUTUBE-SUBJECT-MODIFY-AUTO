"""사람의 승인 파일 생성·검증(FR-013, EVT-202, SEC-014, SEC-001 ②, T-03).

승인 파일은 `approvals/{영상ID}-{후보번호}.approved.json` 이다. 다음을 지킨다.
- **계획 해시에 묶임**: 파일의 `plan_hash`는 `updater.compute_plan_hash`(영상·후보·이전/새 제목·snippet 전체)이며, 쓰기 직전에 최신 snippet으로
  다시 계산한 값과 같아야 한다. 영상 정보·새 제목·후보·영상 어느 것이든 달라지면 거부한다.
- **만료**: 승인 시각 + `approval.ttl_hours`(설정값, 기본 24시간). 만료 시각과 같거나 지나면 거부한다.
- **1회용**: 쓰기 직전에 `used=true`로 바꾸고, 사용된 파일은 다시 쓸 수 없다.
- **위조 방지(설계서 대비 추가)**: 파일 내용에 HMAC-SHA256 인증값(`mac`)을 넣는다. 키는 프로젝트 밖(토큰 폴더)에만 있다.
  따라서 승인 파일을 손으로 고치거나(만료 연장, `used`를 false로 되돌림, 승인자 변경) 다른 곳에서 만든 파일은 거부된다.
  같은 PC의 악성코드가 키까지 읽을 수 있는 경우는 막지 못한다(T-03 잔여 위험, 설계서 8장 6번).
- **위치 제한**: 파일 이름은 정규식을 통과한 영상 ID와 정수 후보 번호로만 만들고, 해석한 경로의 부모가 승인 폴더가 아니거나 심볼릭 링크면 거부한다.
알 수 없는 필드, 틀린 형식, 큰 파일은 모두 거부한다(fail-closed).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from youtube_title.config import Settings
from youtube_title.errors import InputError, SafetyGateError
from youtube_title.platform_utils import restrict_file_permissions
from youtube_title.textsafe import sanitize_for_display
from youtube_title.timeutil import parse_iso, utc_iso
from youtube_title.updater import canonical_json

APPROVAL_VERSION = 1
MAX_FILE_BYTES = 8192
MAX_APPROVER_CHARS = 40
KEY_FILE = "approval_hmac.key"
KEY_BYTES = 32
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_FIELDS = frozenset({"v", "video_id", "candidate_id", "new_title", "plan_hash", "approver", "approved_at", "expires_at", "used", "used_at", "mac"})
REAPPROVE_HINT = "`plan --candidate N` 으로 계획을 다시 확인한 뒤 `approve --candidate N --approver 이름` 으로 새로 승인받으세요."


class ApprovalError(SafetyGateError):
    """승인 파일이 없거나 믿을 수 없어 쓰기를 허락하지 않음(종료 코드 3)."""


@dataclass(frozen=True)
class Approval:
    video_id: str
    candidate_id: int
    new_title: str
    plan_hash: str
    approver: str
    approved_at: datetime
    expires_at: datetime
    used: bool
    used_at: datetime | None
    path: Path


# ───────────── 경로·키 ─────────────

def approval_path(settings: Settings, video_id: object, candidate_id: object) -> Path:
    """승인 파일 경로. 영상 ID·후보 번호 형식이 틀리면 경로를 만들지 않는다(경로 조작 방지)."""
    if not isinstance(video_id, str) or not VIDEO_ID_RE.fullmatch(video_id):
        raise ApprovalError("영상 ID 형식이 올바르지 않아 승인 파일 위치를 정할 수 없습니다.", "영상 ID(영문·숫자·-·_ 11자)를 확인하세요.")
    if isinstance(candidate_id, bool) or not isinstance(candidate_id, int) or candidate_id < 1:
        raise ApprovalError("후보 번호가 올바르지 않아 승인 파일 위치를 정할 수 없습니다.", "후보 번호(1 이상의 정수)를 확인하세요.")
    base = settings.approvals_dir
    path = base / f"{video_id}-{candidate_id}.approved.json"
    if path.resolve().parent != base.resolve():
        raise ApprovalError("승인 파일 위치가 승인 폴더 밖입니다.", "approvals 폴더가 다른 곳을 가리키는 링크가 아닌지 확인하세요.")
    return path


def _key_path(settings: Settings) -> Path:
    return settings.token_dir / KEY_FILE


def _load_key(settings: Settings, *, create: bool) -> bytes:
    """승인 인증 키를 읽는다. `create`일 때만 없으면 만든다(검증 경로는 절대 만들지 않는다)."""
    path = _key_path(settings)
    if path.exists():
        try:
            key = bytes.fromhex(path.read_text(encoding="ascii").strip())
        except (ValueError, OSError, UnicodeDecodeError) as exc:
            raise ApprovalError("승인 인증 키 파일을 읽을 수 없습니다.", f"`{path}` 파일이 손상되었습니다. 지우고 승인을 새로 받으세요(기존 승인 파일은 모두 무효가 됩니다).", cause=type(exc).__name__) from exc
        if len(key) != KEY_BYTES:
            raise ApprovalError("승인 인증 키 파일의 길이가 올바르지 않습니다.", f"`{path}` 파일을 지우고 승인을 새로 받으세요(기존 승인 파일은 모두 무효가 됩니다).")
        return key
    if not create:
        raise ApprovalError("승인 인증 키가 없어 승인 파일을 믿을 수 없습니다.", REAPPROVE_HINT)
    key = secrets.token_bytes(KEY_BYTES)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(key.hex())
        restrict_file_permissions(path)
    except FileExistsError:  # 동시에 다른 실행이 먼저 만든 경우: 그 키를 쓴다
        return _load_key(settings, create=False)
    except OSError as exc:
        raise InputError("승인 인증 키를 저장하지 못했습니다.", f"`{path.parent}` 폴더의 쓰기 권한을 확인하세요.", cause=type(exc).__name__) from exc
    return key


def _mac(key: bytes, payload: dict) -> str:
    return hmac.new(key, canonical_json(payload).encode("utf-8"), hashlib.sha256).hexdigest()


# ───────────── 입력 검증 ─────────────

def clean_approver(value: object) -> str:
    """승인자 이름: 비어 있지 않고, 길이 제한 이내이며, 제어 문자가 없어야 한다(화면·로그 위조 방지, SEC-019)."""
    if not isinstance(value, str) or not value.strip():
        raise InputError("승인자 이름이 비어 있습니다.", "`--approver 이름` 으로 승인하는 사람의 이름을 쓰세요.")
    name = value.strip()
    if len(name) > MAX_APPROVER_CHARS or sanitize_for_display(name) != name:
        raise InputError(f"승인자 이름이 올바르지 않습니다(제어 문자 없이 {MAX_APPROVER_CHARS}자 이하).", "이름을 짧고 평범한 글자로 바꿔 쓰세요.")
    return name


def check_ttl(settings: Settings, ttl_hours: object) -> int:
    cap = settings.approval_ttl_hours
    if isinstance(ttl_hours, bool) or not isinstance(ttl_hours, int) or not 1 <= ttl_hours <= cap:
        raise InputError(f"승인 유효 시간이 올바르지 않습니다(1 이상 {cap} 이하의 정수 시간).", f"설정 approval.ttl_hours({cap})를 넘길 수 없습니다. 더 길게 쓰려면 설정을 먼저 바꾸세요.")
    return ttl_hours


# ───────────── 생성 ─────────────

def _payload(*, video_id: str, candidate_id: int, new_title: str, plan_hash: str, approver: str, approved_at: datetime, expires_at: datetime, used: bool, used_at: datetime | None) -> dict:
    return {
        "v": APPROVAL_VERSION,
        "video_id": video_id,
        "candidate_id": candidate_id,
        "new_title": new_title,
        "plan_hash": plan_hash,
        "approver": approver,
        "approved_at": utc_iso(approved_at),
        "expires_at": utc_iso(expires_at),
        "used": used,
        "used_at": utc_iso(used_at) if used_at is not None else None,
    }


def _write(path: Path, body: dict, key: bytes) -> None:
    """임시 파일에 쓴 뒤 교체한다(쓰다 만 승인 파일이 남지 않게). 권한은 현재 사용자 전용으로 제한을 시도한다."""
    signed = dict(body, mac=_mac(key, body))
    text = json.dumps(signed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "x", encoding="utf-8") as fh:
            fh.write(text)
        restrict_file_permissions(tmp)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise InputError("승인 파일을 저장하지 못했습니다.", f"`{path.parent}` 폴더의 쓰기 권한과 디스크 공간을 확인하세요.", cause=type(exc).__name__) from exc


def create_approval(settings: Settings, *, video_id: str, candidate_id: int, new_title: str, plan_hash: str, approver: str, now: datetime, ttl_hours: int, overwrite: bool = False) -> Approval:
    """승인 파일을 만든다. 같은 이름의 파일이 있으면 `overwrite`일 때만 교체한다."""
    path = approval_path(settings, video_id, candidate_id)
    if not isinstance(new_title, str) or not new_title.strip():
        raise InputError("승인할 새 제목이 비어 있습니다.", "후보를 확인하세요.")
    if not isinstance(plan_hash, str) or not _HASH_RE.fullmatch(plan_hash):
        raise InputError("계획 해시 형식이 올바르지 않아 승인할 수 없습니다.", "`plan`을 다시 실행하세요.")
    name = clean_approver(approver)
    ttl = check_ttl(settings, ttl_hours)
    if (path.exists() or path.is_symlink()) and not overwrite:
        raise InputError("이미 승인 파일이 있습니다.", "덮어쓰려면 확인 입력을 거쳐야 합니다. 파일을 직접 지우지 않아도 됩니다.")
    expires = now + timedelta(hours=ttl)
    body = _payload(video_id=video_id, candidate_id=candidate_id, new_title=new_title, plan_hash=plan_hash, approver=name, approved_at=now, expires_at=expires, used=False, used_at=None)
    _write(path, body, _load_key(settings, create=True))
    return Approval(video_id, candidate_id, new_title, plan_hash, name, now.replace(microsecond=0), expires.replace(microsecond=0), False, None, path)


# ───────────── 읽기·검증 ─────────────

def _bad(what: str) -> ApprovalError:
    return ApprovalError(f"승인 파일을 믿을 수 없습니다: {what}", REAPPROVE_HINT)


def _time(value: object, what: str) -> datetime:
    try:
        if not isinstance(value, str):
            raise ValueError
        return parse_iso(value)
    except ValueError:
        raise _bad(f"{what} 시각 형식이 올바르지 않음") from None


def load_approval(settings: Settings, video_id: str, candidate_id: int) -> Approval:
    """승인 파일을 읽고 형식·인증값을 확인한다. 내용이 이 쓰기에 맞는지는 `verify_approval`이 확인한다."""
    path = approval_path(settings, video_id, candidate_id)
    if path.is_symlink():
        raise _bad("심볼릭 링크는 쓸 수 없음")
    if not path.exists():
        raise ApprovalError("이 후보의 승인 파일이 없습니다.", f"`approve --candidate {candidate_id} --approver 이름` 으로 먼저 승인받으세요.")
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise _bad("파일이 너무 큼")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # UnicodeDecodeError는 ValueError의 하위 클래스
        raise ApprovalError("승인 파일을 읽을 수 없습니다.", REAPPROVE_HINT, cause=type(exc).__name__) from exc
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise _bad("항목이 규격과 다름")
    key = _load_key(settings, create=False)
    body = {k: v for k, v in data.items() if k != "mac"}
    mac = data["mac"]
    if not isinstance(mac, str) or not hmac.compare_digest(mac, _mac(key, body)):
        raise _bad("인증값이 맞지 않음(고쳐졌거나 다른 곳에서 만든 파일)")
    if data["v"] != APPROVAL_VERSION or isinstance(data["v"], bool):
        raise _bad("규격 버전이 다름")
    if not isinstance(data["video_id"], str) or not VIDEO_ID_RE.fullmatch(data["video_id"]):
        raise _bad("영상 ID 형식")
    cid = data["candidate_id"]
    if isinstance(cid, bool) or not isinstance(cid, int) or cid < 1:
        raise _bad("후보 번호 형식")
    if not isinstance(data["new_title"], str) or not data["new_title"].strip():
        raise _bad("새 제목 형식")
    if not isinstance(data["plan_hash"], str) or not _HASH_RE.fullmatch(data["plan_hash"]):
        raise _bad("계획 해시 형식")
    if not isinstance(data["approver"], str) or not data["approver"].strip():
        raise _bad("승인자 형식")
    if not isinstance(data["used"], bool):
        raise _bad("사용 여부 형식")
    approved_at, expires_at = _time(data["approved_at"], "승인"), _time(data["expires_at"], "만료")
    used_at = None if data["used_at"] is None else _time(data["used_at"], "사용")
    if data["used"] != (used_at is not None):
        raise _bad("사용 여부와 사용 시각이 맞지 않음")
    return Approval(data["video_id"], cid, data["new_title"], data["plan_hash"], data["approver"], approved_at, expires_at, data["used"], used_at, path)


def verify_approval(approval: Approval, settings: Settings, *, video_id: str, candidate_id: int, new_title: str, plan_hash: str, now: datetime) -> None:
    """쓰기 직전 확인(DESIGN 5-2 7단계). `plan_hash`는 방금 다시 조회한 snippet으로 새로 계산한 값이어야 한다."""
    if approval.video_id != video_id or approval.candidate_id != candidate_id:
        raise ApprovalError("승인 파일이 이 영상·후보의 것이 아닙니다.", REAPPROVE_HINT)
    if approval.used:
        raise ApprovalError("이 승인은 이미 사용되었습니다(승인은 한 번만 쓸 수 있습니다).", REAPPROVE_HINT)
    if now >= approval.expires_at:
        raise ApprovalError(f"승인이 만료되었습니다(만료 {utc_iso(approval.expires_at)} UTC).", REAPPROVE_HINT)
    if approval.approved_at > now:
        raise ApprovalError("승인 시각이 지금보다 미래라 믿을 수 없습니다.", "PC 시계를 확인한 뒤 새로 승인받으세요.")
    if approval.expires_at - approval.approved_at > timedelta(hours=settings.approval_ttl_hours):   # 위의 두 검사로 승인 시각 ≤ 지금 < 만료이므로 기간은 항상 양수
        raise ApprovalError("승인 유효 기간이 설정(approval.ttl_hours) 범위를 벗어났습니다.", REAPPROVE_HINT)
    if approval.new_title != new_title:
        raise ApprovalError("승인된 새 제목이 지금 계획의 새 제목과 다릅니다.", REAPPROVE_HINT)
    if approval.plan_hash != plan_hash:
        raise ApprovalError("승인 이후 영상 정보나 계획이 바뀌었습니다(계획 해시 불일치). plan부터 다시 하세요.", REAPPROVE_HINT)


def inspect_active(settings: Settings, video_id: str, candidate_id: int, now: datetime) -> Approval | None:
    """지금 쓸 수 있는 승인(유효·미사용·미만료)이 이미 있으면 돌려준다. 어떤 이유로든 읽을 수 없으면 None(예외 없음)."""
    try:
        approval = load_approval(settings, video_id, candidate_id)
    except (ApprovalError, InputError):
        return None
    return approval if not approval.used and now < approval.expires_at else None


def mark_used(settings: Settings, approval: Approval, now: datetime) -> Approval:
    """승인을 소진한다(`used=true`, 사용 시각 기록, 다시 서명). 이미 사용되었거나 파일이 바뀌었으면 거부한다."""
    current = load_approval(settings, approval.video_id, approval.candidate_id)
    if current.used:
        raise ApprovalError("이 승인은 이미 사용되었습니다(승인은 한 번만 쓸 수 있습니다).", REAPPROVE_HINT)
    if (current.plan_hash, current.new_title, current.approved_at, current.expires_at) != (approval.plan_hash, approval.new_title, approval.approved_at, approval.expires_at):
        raise ApprovalError("승인 파일이 확인한 뒤에 바뀌었습니다.", REAPPROVE_HINT)
    body = _payload(video_id=current.video_id, candidate_id=current.candidate_id, new_title=current.new_title, plan_hash=current.plan_hash, approver=current.approver, approved_at=current.approved_at, expires_at=current.expires_at, used=True, used_at=now)
    _write(current.path, body, _load_key(settings, create=False))
    return Approval(current.video_id, current.candidate_id, current.new_title, current.plan_hash, current.approver, current.approved_at, current.expires_at, True, now.replace(microsecond=0), current.path)


def remove_approval(settings: Settings, video_id: str, candidate_id: int) -> None:
    """방금 만든 승인 파일을 되돌린다(approve가 후보 상태 전이에 실패했을 때). 없으면 아무것도 하지 않는다."""
    path = approval_path(settings, video_id, candidate_id)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise InputError("승인 파일을 지우지 못했습니다.", f"`{path}` 파일을 직접 지우세요.", cause=type(exc).__name__) from exc
