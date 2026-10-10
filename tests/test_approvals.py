import json
import os
import stat
from datetime import timedelta

import pytest
from wu4_support import NOW, VID, make_settings

from ytitle import approvals
from ytitle.approvals import ApprovalError, approval_path, clean_approver, create_approval, inspect_active, load_approval, mark_used, remove_approval, verify_approval
from ytitle.errors import InputError, SafetyGateError

H64 = "a" * 64
H64_B = "b" * 64


@pytest.fixture
def s(project, tmp_path):
    return make_settings(project, token_dir=tmp_path / "tokens")


def make(s, **kw):
    args = dict(video_id=VID, candidate_id=7, new_title="새 제목", plan_hash=H64, approver="홍길동", now=NOW, ttl_hours=24)
    args.update(kw)
    return create_approval(s, **args)


def check(s, appr, **kw):
    args = dict(video_id=VID, candidate_id=7, new_title="새 제목", plan_hash=H64, now=NOW + timedelta(hours=1))
    args.update(kw)
    verify_approval(appr, s, **args)


def raw(path):
    return json.loads(path.read_text(encoding="utf-8"))


def put(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_create_writes_bound_expiring_unused_file(s):
    """TC-530: 승인 파일은 영상·후보·새 제목·계획 해시·승인자·승인/만료 시각을 담고 used=false이며 승인 폴더 안 정해진 이름으로 만들어진다. [FR-013, EVT-202, SEC-014]"""
    a = make(s)
    assert a.path == s.approvals_dir / f"{VID}-7.approved.json" and a.path.parent == s.approvals_dir
    d = raw(a.path)
    assert {k: d[k] for k in ("video_id", "candidate_id", "new_title", "plan_hash", "approver", "used", "used_at")} == {
        "video_id": VID, "candidate_id": 7, "new_title": "새 제목", "plan_hash": H64, "approver": "홍길동", "used": False, "used_at": None}
    assert d["approved_at"] == "2026-10-10T12:00:00Z" and d["expires_at"] == "2026-10-11T12:00:00Z" and len(d["mac"]) == 64
    assert a.approved_at == NOW and a.expires_at == NOW + timedelta(hours=24) and not a.used
    assert [p.name for p in s.approvals_dir.iterdir()] == [a.path.name]   # 임시 파일이 남지 않음


def test_file_permissions_are_restricted_on_posix(s):
    """TC-531: 승인 파일과 인증 키 파일은 현재 사용자만 읽을 수 있게 제한을 시도한다(POSIX 0600). [SEC-014, SEC-015]"""
    a = make(s)
    assert stat.S_IMODE(os.stat(a.path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(s.token_dir / approvals.KEY_FILE).st_mode) == 0o600


def test_load_and_verify_roundtrip(s):
    """TC-532: 만든 승인은 다시 읽어 검증을 통과한다(같은 영상·후보·제목·해시, 만료 전). [FR-013, SEC-014]"""
    a = make(s)
    loaded = load_approval(s, VID, 7)
    assert loaded == a
    check(s, loaded)


@pytest.mark.parametrize("field,value", [
    ("new_title", "다른 제목"), ("plan_hash", H64_B), ("approver", "도둑"), ("expires_at", "2030-01-01T00:00:00Z"),
    ("approved_at", "2026-10-10T11:00:00Z"), ("used", True), ("candidate_id", 8), ("video_id", "zzzzzzzzzzz"), ("v", 2),
])
def test_edited_file_is_rejected_by_mac(s, field, value):
    """TC-533: 승인 파일을 손으로 고치면(제목·해시·승인자·만료 연장·used 변경 등) 인증값이 맞지 않아 거부한다. [SEC-014, T-03]"""
    a = make(s)
    d = raw(a.path)
    d[field] = value
    put(a.path, d)
    with pytest.raises(ApprovalError, match="인증값"):
        load_approval(s, VID, 7)


def test_unused_flag_reset_after_use_is_rejected(s):
    """TC-534: 사용된 승인 파일의 used를 false로 되돌리거나 오래된 사본으로 바꿔치면 인증값 때문에 거부된다(1회용 우회 방지). [SEC-014, T-03]"""
    a = make(s)
    before = a.path.read_text(encoding="utf-8")
    mark_used(s, a, NOW)
    used = raw(a.path)
    assert used["used"] is True and used["used_at"] == "2026-10-10T12:00:00Z"
    used["used"], used["used_at"] = False, None
    put(a.path, used)
    with pytest.raises(ApprovalError, match="인증값"):
        load_approval(s, VID, 7)
    # 원본(미사용) 사본을 되돌려 놓으면 인증은 통과한다 — 이 재생 공격은 DB 이력(후보 상태·planned/success 행)이 막는다(TC-566 계열)
    a.path.write_text(before, encoding="utf-8")
    assert load_approval(s, VID, 7).used is False


def test_forged_file_made_with_another_key_is_rejected(s, tmp_path):
    """TC-535: 다른 키(다른 PC·다른 사람)로 만든 승인 파일은 같은 내용이어도 거부한다. [SEC-014, T-03]"""
    make(s)
    other = make_settings(s.base_dir, token_dir=tmp_path / "other_tokens")
    make(other, overwrite=True)   # 같은 위치에 다른 키로 서명한 파일을 덮어쓴다
    with pytest.raises(ApprovalError, match="인증값"):
        load_approval(s, VID, 7)


def test_missing_key_rejects_without_creating_one(s):
    """TC-536: 검증 경로는 키가 없으면 새로 만들지 않고 거부한다(키를 만들어 위조 파일을 통과시키는 길 차단). [SEC-014]"""
    a = make(s)
    (s.token_dir / approvals.KEY_FILE).unlink()
    with pytest.raises(ApprovalError, match="키가 없어"):
        load_approval(s, VID, 7)
    assert not (s.token_dir / approvals.KEY_FILE).exists() and a.path.exists()


@pytest.mark.parametrize("content", ["zz", "ab" * 10, ""])
def test_corrupt_key_is_rejected_on_both_paths(s, content):
    """TC-537: 손상된 키 파일(16진수 아님·길이 틀림)은 읽기·만들기 모두 거부하고 덮어쓰지 않는다. [SEC-014]"""
    s.token_dir.mkdir(parents=True)
    key = s.token_dir / approvals.KEY_FILE
    key.write_text(content, encoding="ascii")
    with pytest.raises(ApprovalError, match="키"):
        make(s)
    assert key.read_text(encoding="ascii") == content


def test_key_is_created_once_and_stable(s):
    """TC-538: 키는 첫 승인 때 한 번 만들어지고 이후 승인에서도 같은 키를 쓴다(기존 승인이 무효가 되지 않음). [SEC-014]"""
    make(s, candidate_id=1)
    k1 = (s.token_dir / approvals.KEY_FILE).read_text(encoding="ascii")
    make(s, candidate_id=2)
    assert (s.token_dir / approvals.KEY_FILE).read_text(encoding="ascii") == k1 and len(bytes.fromhex(k1)) == 32
    load_approval(s, VID, 1)


def test_key_creation_race_uses_the_winner(s, monkeypatch):
    """TC-539: 두 실행이 동시에 키를 만들려 하면(O_EXCL 충돌) 먼저 만든 쪽의 키를 쓴다. [SEC-014]"""
    s.token_dir.mkdir(parents=True)
    winner = bytes(range(32))
    real_open = os.open

    def racing_open(path, flags, mode=0o777):
        if str(path).endswith(approvals.KEY_FILE):
            (s.token_dir / approvals.KEY_FILE).write_text(winner.hex(), encoding="ascii")
            raise FileExistsError
        return real_open(path, flags, mode)

    monkeypatch.setattr(os, "open", racing_open)
    a = make(s)
    monkeypatch.undo()
    assert (s.token_dir / approvals.KEY_FILE).read_text(encoding="ascii") == winner.hex()
    assert load_approval(s, VID, 7) == a


def test_key_dir_unwritable_is_a_korean_error(s, tmp_path):
    """TC-540: 키를 저장할 폴더를 만들 수 없으면 한국어 오류로 알리고 승인 파일도 만들지 않는다. [NFR-007, SEC-014]"""
    (tmp_path / "blocker").write_text("파일", encoding="utf-8")
    bad = make_settings(s.base_dir, token_dir=tmp_path / "blocker" / "tokens")
    with pytest.raises(InputError, match="키를 저장하지 못했습니다"):
        make(bad)
    assert not bad.approvals_dir.exists() or not list(bad.approvals_dir.iterdir())


def test_expiry_boundary(s):
    """TC-541: 만료 1초 전은 통과, 만료 시각 정각과 그 이후는 만료로 거부한다. [FR-013, SEC-014]"""
    a = make(s, ttl_hours=2)
    check(s, a, now=NOW + timedelta(hours=2) - timedelta(seconds=1))
    for later in (timedelta(hours=2), timedelta(hours=2, seconds=1), timedelta(days=30)):
        with pytest.raises(ApprovalError, match="만료"):
            check(s, a, now=NOW + later)


def test_used_approval_cannot_be_used_again(s):
    """TC-542: mark_used 후에는 검증도, 다시 mark_used도 거부한다(1회용). [SEC-014, T-03]"""
    a = make(s)
    used = mark_used(s, a, NOW + timedelta(minutes=1))
    assert used.used and used.used_at == NOW + timedelta(minutes=1)
    with pytest.raises(ApprovalError, match="이미 사용"):
        check(s, load_approval(s, VID, 7))
    with pytest.raises(ApprovalError, match="이미 사용"):
        mark_used(s, a, NOW)
    assert load_approval(s, VID, 7).used is True


def test_mark_used_rejects_changed_file(s):
    """TC-543: 확인한 뒤 승인 파일이 다른 승인(다른 해시)으로 바뀌었으면 소진하지 않고 거부한다. [SEC-014]"""
    a = make(s)
    make(s, plan_hash=H64_B, overwrite=True)
    with pytest.raises(ApprovalError, match="바뀌었"):
        mark_used(s, a, NOW)
    assert load_approval(s, VID, 7).used is False


@pytest.mark.parametrize("kw,pattern", [
    ({"plan_hash": H64_B}, "계획 해시 불일치"),
    ({"new_title": "다른 제목"}, "새 제목과 다릅니다"),
    ({"video_id": "zzzzzzzzzzz"}, "이 영상·후보의 것이 아닙니다"),
    ({"candidate_id": 8}, "이 영상·후보의 것이 아닙니다"),
])
def test_approval_does_not_transfer_to_another_plan(s, kw, pattern):
    """TC-544: 다른 계획 해시(영상 정보가 바뀜)·다른 새 제목·다른 영상·다른 후보에는 승인을 재활용할 수 없다. [SEC-014, T-03]"""
    a = make(s)
    with pytest.raises(ApprovalError, match=pattern):
        check(s, a, **kw)


def test_future_dated_and_overlong_periods_are_rejected(s):
    """TC-545: 승인 시각이 미래이거나 유효 기간이 설정 상한(approval.ttl_hours)을 넘으면 거부한다. [SEC-014]"""
    a = make(s)
    with pytest.raises(ApprovalError, match="미래"):
        check(s, a, now=NOW - timedelta(seconds=1))
    short = make_settings(s.base_dir, token_dir=s.token_dir, approval_ttl_hours=12)
    with pytest.raises(ApprovalError, match="유효 기간"):
        check(short, a)


@pytest.mark.parametrize("bad", ["../x", "..", "a/b", "short", "toolongvideoid123", "abc 123DEF4", "abc123DEF4\n", "", None, 5])
def test_path_traversal_and_bad_video_ids(s, bad):
    """TC-546: 영상 ID가 정규식(영문·숫자·-·_ 11자)을 통과하지 못하면 경로를 만들지 않는다(경로 조작 차단). [SEC-014, SEC-011]"""
    with pytest.raises(ApprovalError, match="영상 ID"):
        approval_path(s, bad, 1)
    with pytest.raises(ApprovalError):
        load_approval(s, bad, 1)


@pytest.mark.parametrize("bad", [0, -1, True, "7", 1.5, None])
def test_bad_candidate_ids(s, bad):
    """TC-547: 후보 번호가 1 이상의 정수가 아니면 경로를 만들지 않는다. [SEC-014]"""
    with pytest.raises(ApprovalError, match="후보 번호"):
        approval_path(s, VID, bad)


def test_symlinked_file_is_rejected(s, tmp_path):
    """TC-548: 승인 파일이 심볼릭 링크이면 폴더 밖을 가리키든 폴더 안 다른 파일을 가리키든 거부한다(위치 제한). [SEC-014]"""
    a = make(s)
    outside = tmp_path / "outside.json"
    outside.write_text(a.path.read_text(encoding="utf-8"), encoding="utf-8")
    a.path.unlink()
    a.path.symlink_to(outside)
    with pytest.raises(ApprovalError, match="승인 폴더 밖"):
        load_approval(s, VID, 7)
    a.path.unlink()
    inside = s.approvals_dir / "other.json"
    inside.write_text(outside.read_text(encoding="utf-8"), encoding="utf-8")
    a.path.symlink_to(inside)
    with pytest.raises(ApprovalError, match="심볼릭 링크"):
        load_approval(s, VID, 7)


def test_missing_file_has_actionable_message(s):
    """TC-549: 승인 파일이 없으면 approve 명령을 안내한다. [NFR-007, FR-013]"""
    with pytest.raises(ApprovalError, match="승인 파일이 없습니다") as exc:
        load_approval(s, VID, 7)
    assert "approve --candidate 7" in exc.value.next_step and isinstance(exc.value, SafetyGateError) and exc.value.exit_code == 3


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("used_at"),
    lambda d: d.update(extra="x"),
    lambda d: d.update(candidate_id=True),
    lambda d: d.update(candidate_id="7"),
    lambda d: d.update(candidate_id=0),
    lambda d: d.update(new_title=""),
    lambda d: d.update(new_title=5),
    lambda d: d.update(plan_hash="XYZ"),
    lambda d: d.update(plan_hash=5),
    lambda d: d.update(approver="  "),
    lambda d: d.update(approver=5),
    lambda d: d.update(used="false"),
    lambda d: d.update(approved_at="어제"),
    lambda d: d.update(approved_at=5),
    lambda d: d.update(expires_at="2026-10-11"),
    lambda d: d.update(used_at="2026-10-10T12:00:00Z"),
    lambda d: d.update(used=True),
    lambda d: d.update(v=True),
    lambda d: d.update(video_id=5),
    lambda d: d.update(mac=5),
])
def test_schema_violations_are_rejected_even_with_valid_mac(s, mutate):
    """TC-550: 인증값이 맞더라도(키를 가진 쪽이 만들었더라도) 항목 구성·형식이 규격과 다르면 거부한다(fail-closed). [SEC-014]"""
    a = make(s)
    d = raw(a.path)
    body = {k: v for k, v in d.items() if k != "mac"}
    mutate(body)
    key = approvals._load_key(s, create=False)
    if "mac" in body:   # mac 항목을 직접 고치는 경우는 서명하지 않는다
        put(a.path, body)
    else:
        put(a.path, dict(body, mac=approvals._mac(key, body)))
    with pytest.raises(ApprovalError):
        load_approval(s, VID, 7)


@pytest.mark.parametrize("content", ["", "{", "[]", "null", '"문자열"', "﻿{}"])
def test_garbage_files_are_rejected(s, content):
    """TC-551: 비어 있거나 JSON이 아니거나 객체가 아닌 파일은 거부한다. [SEC-014, SEC-016]"""
    a = make(s)
    a.path.write_text(content, encoding="utf-8")
    with pytest.raises(ApprovalError):
        load_approval(s, VID, 7)


def test_oversize_and_non_utf8_files_are_rejected(s):
    """TC-552: 크기 상한(8KB)을 넘거나 UTF-8이 아닌 파일은 읽지 않고 거부한다. [SEC-014, SEC-016]"""
    a = make(s)
    a.path.write_text("x" * (approvals.MAX_FILE_BYTES + 1), encoding="utf-8")
    with pytest.raises(ApprovalError, match="너무 큼"):
        load_approval(s, VID, 7)
    a.path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ApprovalError, match="읽을 수 없습니다"):
        load_approval(s, VID, 7)


def test_create_refuses_overwrite_unless_asked(s):
    """TC-553: 같은 이름의 승인 파일이 있으면 overwrite 없이는 만들지 않고, 요청하면 새 승인으로 교체한다(이전 해시는 사라짐). [SEC-014, SCR-004]"""
    make(s)
    with pytest.raises(InputError, match="이미 승인 파일"):
        make(s, plan_hash=H64_B)
    assert raw(approval_path(s, VID, 7))["plan_hash"] == H64
    new = make(s, plan_hash=H64_B, overwrite=True)
    assert load_approval(s, VID, 7).plan_hash == H64_B == new.plan_hash


def test_create_validates_inputs_and_writes_nothing(s):
    """TC-554: 새 제목·계획 해시·승인자·유효 시간이 잘못되면 파일도 키도 만들지 않는다. [SEC-014, FR-013]"""
    for kw, exc in (({"new_title": "  "}, InputError), ({"plan_hash": "xyz"}, InputError), ({"plan_hash": H64.upper()}, InputError), ({"approver": ""}, InputError),
                    ({"ttl_hours": 0}, InputError), ({"ttl_hours": 25}, InputError), ({"ttl_hours": True}, InputError), ({"ttl_hours": 1.5}, InputError), ({"video_id": "bad"}, SafetyGateError)):
        with pytest.raises(exc):
            make(s, **kw)
    assert not s.approvals_dir.exists() and not (s.token_dir / approvals.KEY_FILE).exists()


def test_ttl_boundaries_follow_the_setting(s):
    """TC-555: 유효 시간은 1시간 이상 설정값(approval.ttl_hours) 이하만 가능하다(경계 포함). [FR-013, SEC-014]"""
    assert make(s, candidate_id=1, ttl_hours=1).expires_at == NOW + timedelta(hours=1)
    assert make(s, candidate_id=2, ttl_hours=24).expires_at == NOW + timedelta(hours=24)
    short = make_settings(s.base_dir, token_dir=s.token_dir, approval_ttl_hours=3)
    assert make(short, candidate_id=3, ttl_hours=3)
    with pytest.raises(InputError, match="1 이상 3 이하"):
        make(short, candidate_id=4, ttl_hours=4)


@pytest.mark.parametrize("name", ["", "   ", None, 5, "a" * 41, "홍\x1b[31m길동", "홍\n길동", "홍‮길동"])
def test_approver_name_rules(name):
    """TC-556: 승인자 이름은 비어 있지 않고 40자 이하이며 제어 문자(ANSI·줄바꿈·방향 문자)가 없어야 한다. [SEC-019, T-13, NFR-008]"""
    with pytest.raises(InputError):
        clean_approver(name)
    assert clean_approver("  홍길동  ") == "홍길동" and clean_approver("a" * 40) == "a" * 40


def test_write_failure_leaves_no_partial_file(s, monkeypatch):
    """TC-557: 파일 쓰기가 중간에 실패하면 한국어 오류로 알리고 기존 승인 파일과 임시 파일을 남기지 않는다(교체는 원자적). [NFR-007, SEC-014]"""
    make(s)
    before = approval_path(s, VID, 7).read_text(encoding="utf-8")

    def boom(src, dst):
        raise OSError("디스크 가득")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(InputError, match="저장하지 못했습니다"):
        make(s, plan_hash=H64_B, overwrite=True)
    monkeypatch.undo()
    assert approval_path(s, VID, 7).read_text(encoding="utf-8") == before
    assert [p.name for p in s.approvals_dir.iterdir()] == [f"{VID}-7.approved.json"]


def test_write_failure_when_tmp_cannot_be_removed_still_reports(s, monkeypatch):
    """TC-558: 임시 파일 정리마저 실패해도 원래 저장 실패 오류를 그대로 알린다. [NFR-007]"""
    def boom(src, dst):
        raise OSError("실패")

    monkeypatch.setattr(os, "replace", boom)
    monkeypatch.setattr(approvals.Path, "unlink", lambda self, *a, **k: (_ for _ in ()).throw(OSError("지울 수 없음")))
    with pytest.raises(InputError, match="저장하지 못했습니다"):
        make(s)


def test_inspect_active_never_raises(s):
    """TC-559: inspect_active는 유효·미사용·미만료 승인만 돌려주고, 없음·만료·사용됨·훼손은 예외 없이 None이다. [SCR-004]"""
    assert inspect_active(s, VID, 7, NOW) is None
    a = make(s)
    assert inspect_active(s, VID, 7, NOW) == a
    assert inspect_active(s, VID, 7, NOW + timedelta(hours=24)) is None
    a.path.write_text("깨짐", encoding="utf-8")
    assert inspect_active(s, VID, 7, NOW) is None
    make(s, overwrite=True)
    mark_used(s, load_approval(s, VID, 7), NOW)
    assert inspect_active(s, VID, 7, NOW) is None


def test_remove_approval(s, monkeypatch):
    """TC-560: remove_approval은 파일을 지우고, 없으면 아무 일도 하지 않으며, 지울 수 없으면 한국어 오류를 낸다. [SEC-014]"""
    a = make(s)
    remove_approval(s, VID, 7)
    assert not a.path.exists()
    remove_approval(s, VID, 7)
    make(s)
    monkeypatch.setattr(approvals.Path, "unlink", lambda self, *a, **k: (_ for _ in ()).throw(PermissionError("권한 없음")))
    with pytest.raises(InputError, match="지우지 못했습니다"):
        remove_approval(s, VID, 7)


def test_secrets_are_not_in_error_messages(s):
    """TC-561: 오류 메시지·안내에 인증 키 값이 나오지 않는다. [SEC-008, SEC-014]"""
    a = make(s)
    key = (s.token_dir / approvals.KEY_FILE).read_text(encoding="ascii")
    d = raw(a.path)
    d["approver"] = "도둑"
    put(a.path, d)
    with pytest.raises(ApprovalError) as exc:
        load_approval(s, VID, 7)
    assert key not in exc.value.message + exc.value.next_step + exc.value.cause
