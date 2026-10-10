import itertools
import json
from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from wu4_support import NOW, SNIPPET, VID, add_candidate, add_change, add_video, clock, make_settings, open_db, ts

from ytitle.errors import DatabaseError, InputError, SafetyGateError
from ytitle.history import ALLOWED_TRANSITIONS, begin_change, begin_rollback, finish_change, get_change, list_changes, plan_rollback, record_aborted, transition_candidate
from ytitle.updater import canonical_json, compute_plan_hash, create_plan

STATUSES = ["candidate", "filtered", "approved", "applied", "evaluated", "rolled_back", "blocked"]
EDGES = {("candidate", "filtered"), ("candidate", "blocked"), ("filtered", "approved"), ("approved", "applied"), ("applied", "evaluated"), ("applied", "rolled_back"), ("evaluated", "rolled_back")}


@pytest.fixture
def s(project):
    return make_settings(project)


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "t.sqlite3")
    yield c
    c.close()


def cand_status(conn, cid):
    return conn.execute("SELECT status FROM title_candidates WHERE id=?", (cid,)).fetchone()[0]


def change_count(conn):
    return conn.execute("SELECT COUNT(*) FROM title_changes").fetchone()[0]


def approved_plan(conn, s, **kw):
    add_video(conn)
    cid = add_candidate(conn, status="approved", **kw)
    return cid, create_plan(conn, s, clock(), cid)


def start(conn, s, plan, **over):
    args = dict(approver="홍길동", approved_at=NOW, run_id="run1", now=NOW)
    args.update(over)
    return begin_change(conn, s, plan, **args)


def applied_world(conn, s):
    """승인 → 적용 성공까지 끝낸 상태. 변경 번호와 후보 번호를 돌려준다."""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    finish_change(conn, chg, "success", NOW, verify_result={"title_ok": True})
    # 적용 후 fetch가 새 제목을 저장했다고 가정
    add_video(conn, snippet={**SNIPPET, "title": plan.new_title}, fetched_at=ts(NOW))
    return cid, chg, plan


# ───────────── 상태 머신 ─────────────

@pytest.mark.parametrize("src,dst", list(itertools.product(STATUSES, STATUSES)))
def test_transition_table_exact(conn, src, dst):
    """TC-460: 후보 상태 전이는 설계 3-2의 7개 간선만 허용한다(나머지 42개 조합 전부 거부, blocked·rolled_back은 종료 상태). [설계 3-2, SEC-006]"""
    cid = add_candidate(conn, status=src, result="pass")
    if (src, dst) in EDGES:
        transition_candidate(conn, cid, dst, NOW)
        assert cand_status(conn, cid) == dst
    else:
        with pytest.raises(SafetyGateError):
            transition_candidate(conn, cid, dst, NOW)
        assert cand_status(conn, cid) == src
    assert ALLOWED_TRANSITIONS["blocked"] == frozenset() == ALLOWED_TRANSITIONS["rolled_back"]


def test_transition_unknown_candidate_and_target(conn):
    """TC-461: 없는 후보는 InputError, 알 수 없는 목표 상태는 거부한다. [설계 3-2]"""
    with pytest.raises(InputError):
        transition_candidate(conn, 12345, "applied", NOW)
    cid = add_candidate(conn)
    with pytest.raises(SafetyGateError):
        transition_candidate(conn, cid, "deleted", NOW)


def test_transition_updates_timestamp(conn):
    """TC-462: 전이하면 updated_at이 갱신된다. [NFR-008]"""
    cid = add_candidate(conn)
    later = NOW + timedelta(hours=1)
    transition_candidate(conn, cid, "approved", later)
    assert conn.execute("SELECT updated_at FROM title_candidates WHERE id=?", (cid,)).fetchone()[0] == ts(later)


# ───────────── begin_change ─────────────

def test_begin_change_writes_planned_row_with_full_backup(conn, s):
    """TC-463: 호출 직전 기록은 result=planned, 승인자·승인 시각·계획 해시·run_id와 snippet 전체 백업(description·tags·categoryId 포함)을 저장한다. [FR-009, FR-010, SEC-005, SEC-006, NFR-008]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan, reason="테스트 사유")
    r = get_change(conn, chg)
    assert (r["result"], r["change_type"], r["video_id"], r["candidate_id"]) == ("planned", "apply", VID, cid)
    assert (r["previous_title"], r["new_title"], r["approver"], r["plan_hash"], r["run_id"], r["reason"]) == (plan.previous_title, plan.new_title, "홍길동", plan.plan_hash, "run1", "테스트 사유")
    assert r["approved_at"] == ts(NOW) and r["applied_at"] is None and r["created_at"] == ts(NOW)
    backup = json.loads(r["backup_snippet_json"])
    assert backup == SNIPPET and backup["description"] == SNIPPET["description"] and backup["tags"] == SNIPPET["tags"] and backup["categoryId"] == "26"
    assert r["backup_snippet_json"] == canonical_json(SNIPPET)
    assert cand_status(conn, cid) == "approved"


@pytest.mark.parametrize("status", ["candidate", "filtered", "blocked", "applied", "rolled_back"])
def test_begin_change_requires_approved_candidate(conn, s, status):
    """TC-464: 후보가 승인(approved) 상태가 아니면 이력 행을 만들지 않는다(승인 없는 상태 변경 불가). [SEC-001, FR-013, K-2]"""
    add_video(conn)
    cid = add_candidate(conn, status="approved")
    plan = create_plan(conn, s, clock(), cid)
    conn.execute("UPDATE title_candidates SET status=? WHERE id=?", (status, cid))
    conn.commit()
    with pytest.raises(SafetyGateError):
        start(conn, s, plan)
    assert change_count(conn) == 0


@pytest.mark.parametrize("over", [{"approver": None}, {"approver": ""}, {"approver": "   "}, {"approver": 5}, {"approved_at": None}, {"approved_at": datetime(2026, 10, 10, 12, 0)}, {"approved_at": "2026-10-10T12:00:00Z"}])
def test_begin_change_requires_approver_and_time(conn, s, over):
    """TC-465: 승인자·승인 시각(시간대 포함)이 없거나 형식이 틀리면 이력 행을 만들지 않는다. [SEC-001, NFR-008, T-04]"""
    cid, plan = approved_plan(conn, s)
    with pytest.raises(SafetyGateError):
        start(conn, s, plan, **over)
    assert change_count(conn) == 0


def test_begin_change_rejects_tampered_plan(conn, s):
    """TC-466: 계획 내용(새 제목·snippet)이 해시와 맞지 않거나 승인된 후보와 다르면 중단하고 아무것도 쓰지 않는다. [SEC-014, SEC-001]"""
    cid, plan = approved_plan(conn, s)
    with pytest.raises(SafetyGateError):
        start(conn, s, replace(plan, new_title="다른 제목"))
    with pytest.raises(SafetyGateError):
        start(conn, s, replace(plan, snippet={**plan.snippet, "description": "변조"}))
    other = replace(plan, new_title="다른 제목", plan_hash=compute_plan_hash(VID, cid, plan.previous_title, "다른 제목", plan.snippet))
    with pytest.raises(SafetyGateError):
        start(conn, s, other)
    with pytest.raises(SafetyGateError):
        start(conn, s, replace(plan, video_id="zzzzzzzzzzz"))
    with pytest.raises(SafetyGateError):
        start(conn, s, replace(plan, candidate_id=9999))
    assert change_count(conn) == 0


def test_begin_change_enforces_limits_again(conn, s):
    """TC-467: 72시간 이내 재변경이면 begin_change도 거부한다(WU-5 5단계와 별개의 방어). [SEC-004, SEC-020]"""
    cid, plan = approved_plan(conn, s)
    add_change(conn, at=NOW - timedelta(hours=1))
    with pytest.raises(SafetyGateError) as exc:
        start(conn, s, plan)
    assert "교체 제한" in exc.value.message and change_count(conn) == 1


def test_begin_change_sql_binding_with_hostile_text(conn, s):
    """TC-468: 제목·승인자·사유에 따옴표·세미콜론·SQL 조각이 있어도 값으로만 저장되고 테이블이 유지된다. [SEC-018, T-12]"""
    evil = "x'); DROP TABLE title_changes;--"
    add_video(conn, snippet={**SNIPPET, "title": evil, "description": evil})
    cid = add_candidate(conn, status="approved", title="멀쩡한 제목' OR '1'='1")
    plan = create_plan(conn, s, clock(), cid)
    chg = start(conn, s, plan, approver=evil, reason=evil)
    r = get_change(conn, chg)
    assert r["previous_title"] == evil and r["new_title"] == "멀쩡한 제목' OR '1'='1" and r["approver"] == evil and r["reason"] == evil
    assert change_count(conn) == 1


def test_begin_change_db_failure_is_database_error(conn, s):
    """TC-469: 이력 저장이 DB 오류로 실패하면 DatabaseError(한국어 안내)이고 행이 남지 않는다. [NFR-007]"""
    cid, plan = approved_plan(conn, s)
    conn.execute("CREATE TRIGGER no_ins BEFORE INSERT ON title_changes BEGIN SELECT RAISE(ABORT, 'disk full'); END")
    with pytest.raises(DatabaseError) as exc:
        start(conn, s, plan)
    assert exc.value.next_step and change_count(conn) == 0


def test_begin_change_candidate_read_failure(conn, s):
    """TC-470: 후보 테이블을 읽지 못하면 DatabaseError로 거부한다. [NFR-007]"""
    cid, plan = approved_plan(conn, s)
    conn.execute("ALTER TABLE title_candidates RENAME TO gone")
    with pytest.raises(DatabaseError):
        start(conn, s, plan)


# ───────────── finish_change ─────────────

def test_finish_success_moves_candidate_to_applied(conn, s):
    """TC-471: 적용 성공 기록은 이력(success·applied_at·verified_at·검증 결과)과 후보 approved→applied를 함께 바꾼다. [SEC-006, SEC-010, 설계 3-2]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    later = NOW + timedelta(minutes=2)
    finish_change(conn, chg, "success", later, verify_result={"title_ok": True, "tags_preserved": True})
    r = get_change(conn, chg)
    assert (r["result"], r["applied_at"], r["verified_at"], r["error_code"]) == ("success", ts(later), ts(later), None)
    assert json.loads(r["verify_result_json"]) == {"title_ok": True, "tags_preserved": True}
    assert cand_status(conn, cid) == "applied"


def test_finish_success_without_verify_result(conn, s):
    """TC-472: 검증 결과 없이 성공을 기록하면 verified_at은 비어 있다(검증 미실시 표시). [SEC-010]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    finish_change(conn, chg, "success", NOW)
    r = get_change(conn, chg)
    assert r["verified_at"] is None and r["verify_result_json"] is None


@pytest.mark.parametrize("result", ["failed", "aborted"])
def test_finish_failure_keeps_candidate_approved(conn, s, result):
    """TC-473: 실패·중단 기록은 후보 상태를 바꾸지 않고 applied_at을 비워 두며 사유 코드를 요구한다. [NFR-008, SEC-006]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    with pytest.raises(SafetyGateError):
        finish_change(conn, chg, result, NOW)
    assert get_change(conn, chg)["result"] == "planned"
    finish_change(conn, chg, result, NOW, error_code="YT-700")
    r = get_change(conn, chg)
    assert (r["result"], r["error_code"], r["applied_at"]) == (result, "YT-700", None)
    assert cand_status(conn, cid) == "approved"


def test_finish_unknown_result_and_unknown_change(conn, s):
    """TC-474: 알 수 없는 결과값·없는 변경 번호는 거부한다(planned로 되돌리는 것도 불가). [SEC-006]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    for bad in ("planned", "ok", ""):
        with pytest.raises(InputError):
            finish_change(conn, chg, bad, NOW)
    with pytest.raises(InputError):
        finish_change(conn, 9999, "success", NOW)


def test_finished_rows_are_immutable(conn, s):
    """TC-475: 이미 끝난 행(success/failed/aborted)은 다시 바꿀 수 없다(감사 기록 보존). [NFR-008, SEC-006]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    finish_change(conn, chg, "success", NOW)
    for res, kw in (("success", {}), ("failed", {"error_code": "X"}), ("aborted", {"error_code": "X"})):
        with pytest.raises(SafetyGateError) as exc:
            finish_change(conn, chg, res, NOW, **kw)
        assert "이미 끝난 기록" in exc.value.message
    assert get_change(conn, chg)["result"] == "success" and cand_status(conn, cid) == "applied"


def test_finish_is_atomic_when_transition_is_illegal(conn, s):
    """TC-476: 후보 상태 전이가 불가능하면(승인 없이 적용 성공 기록 시도) 이력 행도 planned로 남는다(부분 반영 없음). [설계 3-2, SEC-001]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    conn.execute("UPDATE title_candidates SET status='filtered' WHERE id=?", (cid,))   # 승인이 취소된 상황
    conn.commit()
    with pytest.raises(SafetyGateError):
        finish_change(conn, chg, "success", NOW)
    r = get_change(conn, chg)
    assert r["result"] == "planned" and r["applied_at"] is None and cand_status(conn, cid) == "filtered"


def test_finish_db_failure(conn, s):
    """TC-477: 갱신 중 DB 오류는 DatabaseError로 변환되고 행은 planned로 유지된다. [NFR-007]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    conn.execute("CREATE TRIGGER no_upd BEFORE UPDATE ON title_changes BEGIN SELECT RAISE(ABORT, 'readonly'); END")
    with pytest.raises(DatabaseError):
        finish_change(conn, chg, "success", NOW)
    assert get_change(conn, chg)["result"] == "planned"


def test_finish_rowcount_race(conn, s):
    """TC-478: 읽은 뒤 다른 실행이 먼저 끝낸 경우(경쟁)에도 덮어쓰지 않고 중단한다. [SEC-006]"""
    cid, plan = approved_plan(conn, s)
    chg = start(conn, s, plan)
    conn.execute("CREATE TRIGGER race BEFORE UPDATE ON title_changes WHEN OLD.result = 'planned' BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(SafetyGateError):
        finish_change(conn, chg, "success", NOW)
    assert cand_status(conn, cid) == "approved"


def test_transition_race_and_db_error(conn):
    """TC-479: 후보 상태가 읽은 뒤 바뀌었거나 DB 오류면 전이하지 않고 안전하게 중단한다. [설계 3-2]"""
    cid = add_candidate(conn)
    conn.execute("CREATE TRIGGER race2 BEFORE UPDATE ON title_candidates BEGIN SELECT RAISE(IGNORE); END")
    with pytest.raises(SafetyGateError):
        transition_candidate(conn, cid, "approved", NOW)
    conn.execute("DROP TRIGGER race2")
    conn.execute("CREATE TRIGGER boom BEFORE UPDATE ON title_candidates BEGIN SELECT RAISE(ABORT, 'x'); END")
    with pytest.raises(DatabaseError):
        transition_candidate(conn, cid, "approved", NOW)
    assert cand_status(conn, cid) == "filtered"


# ───────────── record_aborted / 조회 ─────────────

def test_record_aborted_rows_leave_state_untouched(conn, s):
    """TC-480: 게이트에서 막힌 시도는 aborted 행으로 남고(승인자 없음 허용), 후보 상태는 바뀌지 않는다. [설계 5-2, NFR-008]"""
    cid, plan = approved_plan(conn, s)
    rid = record_aborted(conn, change_type="apply", video_id=VID, candidate_id=cid, previous_title="a", new_title="b", plan_hash=plan.plan_hash, error_code="GATE-05", reason="72시간 미경과", run_id="run1", now=NOW)
    r = get_change(conn, rid)
    assert (r["result"], r["error_code"], r["reason"], r["approver"], r["applied_at"], r["plan_hash"]) == ("aborted", "GATE-05", "72시간 미경과", None, None, plan.plan_hash)
    assert cand_status(conn, cid) == "approved"


def test_record_aborted_validations(conn):
    """TC-481: 변경 종류가 apply/rollback이 아니거나 사유 코드가 비면 기록하지 않는다. DB 오류는 DatabaseError. [NFR-008]"""
    kw = dict(video_id=VID, candidate_id=None, previous_title="a", new_title="b", plan_hash=None, reason="r", run_id=None, now=NOW)
    with pytest.raises(InputError):
        record_aborted(conn, change_type="delete", error_code="X", **kw)
    with pytest.raises(SafetyGateError):
        record_aborted(conn, change_type="apply", error_code=" ", **kw)
    assert change_count(conn) == 0
    conn.execute("CREATE TRIGGER no_ins2 BEFORE INSERT ON title_changes BEGIN SELECT RAISE(ABORT, 'x'); END")
    with pytest.raises(DatabaseError):
        record_aborted(conn, change_type="rollback", error_code="X", **kw)


def test_list_and_get_changes(conn):
    """TC-482: 이력 조회: 최신순, 영상별 필터, 건수 제한, 없는 번호는 InputError, 잘못된 limit 거부, 바인딩 안전. [FR-010]"""
    ids = [add_change(conn, VID, at=NOW - timedelta(days=d)) for d in (3, 2, 1)] + [add_change(conn, "zzzzzzzzzzz", at=NOW)]
    assert [r["id"] for r in list_changes(conn)] == ids[::-1]
    assert [r["id"] for r in list_changes(conn, VID)] == ids[2::-1]
    assert len(list_changes(conn, VID, limit=2)) == 2
    assert list_changes(conn, "x' OR '1'='1") == []
    for bad in (0, -1, True, "5"):
        with pytest.raises(InputError):
            list_changes(conn, limit=bad)
    with pytest.raises(InputError):
        get_change(conn, 9999)
    conn.execute("DROP TABLE title_changes")
    with pytest.raises(DatabaseError):
        list_changes(conn)
    with pytest.raises(DatabaseError):
        get_change(conn, 1)


# ───────────── 롤백 계획 ─────────────

def test_plan_rollback_restores_original_title_from_backup(conn, s):
    """TC-483: 롤백 계획은 백업 snippet의 원래 제목으로 복원하고, 본문은 지금 snippet 전체 + 제목만 교체이며 description·tags·categoryId가 보존된다. [FR-011, SEC-006, SEC-005]"""
    cid, chg, plan = applied_world(conn, s)
    rp = plan_rollback(conn, s, clock(), chg)
    assert (rp.video_id, rp.change_id, rp.candidate_id, rp.restore_title, rp.current_title) == (VID, chg, cid, "겨울 전기요금", plan.new_title)
    assert rp.current_matches_applied and rp.changed_since_backup == () and not rp.stale
    assert rp.body["id"] == VID and rp.body["snippet"]["title"] == "겨울 전기요금"
    assert {k: v for k, v in rp.body["snippet"].items() if k != "title"} == {k: v for k, v in SNIPPET.items() if k != "title"}
    assert rp.body["snippet"]["description"] == SNIPPET["description"] and rp.body["snippet"]["tags"] == SNIPPET["tags"] and rp.body["snippet"]["categoryId"] == "26"


def test_plan_rollback_hash_is_deterministic_and_distinct(conn, s):
    """TC-484: 롤백 plan_hash는 결정적이고, 같은 영상의 적용 해시와 다르며, snippet이 바뀌면 달라진다. [SEC-014]"""
    cid, chg, plan = applied_world(conn, s)
    a, b = plan_rollback(conn, s, clock(), chg), plan_rollback(conn, s, clock(), chg)
    assert a.plan_hash == b.plan_hash != plan.plan_hash
    assert a.plan_hash == compute_plan_hash(VID, cid, plan.new_title, "겨울 전기요금", a.snippet, kind="rollback", change_id=chg)
    add_video(conn, snippet={**SNIPPET, "title": plan.new_title, "description": "Studio에서 고침"}, fetched_at=ts(NOW))
    c = plan_rollback(conn, s, clock(), chg)
    assert c.plan_hash != a.plan_hash and c.changed_since_backup == ("description",)


def test_plan_rollback_reports_changes_since_backup(conn, s):
    """TC-485: 적용 이후 제목 외 항목이 바뀌었으면 어떤 항목인지 알리고, 복원 본문은 지금 값을 유지한다(사람이 고친 설명을 덮지 않음). [SEC-005, T-14]"""
    cid, chg, plan = applied_world(conn, s)
    add_video(conn, snippet={**SNIPPET, "title": plan.new_title, "description": "Studio에서 고침", "tags": ["새태그"]}, fetched_at=ts(NOW))
    rp = plan_rollback(conn, s, clock(), chg)
    assert rp.changed_since_backup == ("description", "tags")
    assert rp.body["snippet"]["description"] == "Studio에서 고침" and rp.body["snippet"]["tags"] == ["새태그"]


def test_plan_rollback_detects_title_changed_elsewhere(conn, s):
    """TC-486: 지금 제목이 우리가 적용한 제목과 다르면(Studio에서 또 바꿈) current_matches_applied가 거짓이다. [SEC-009]"""
    cid, chg, plan = applied_world(conn, s)
    add_video(conn, snippet={**SNIPPET, "title": "누군가 또 바꾼 제목"}, fetched_at=ts(NOW - timedelta(hours=30)))
    rp = plan_rollback(conn, s, clock(), chg)
    assert not rp.current_matches_applied and rp.stale and rp.restore_title == "겨울 전기요금"


def test_plan_rollback_is_read_only_and_exempt_from_cadence(conn, s):
    """TC-487: 롤백 계획은 DB를 바꾸지 않고, 사고 복구를 막지 않도록 72시간·횟수·하루 상한 제한을 적용하지 않는다. [FR-011, SEC-020 설계 의도]"""
    cid, chg, plan = applied_world(conn, s)
    for d in (50, 40, 30):
        add_change(conn, "zzzzzzzzzzz", at=NOW - timedelta(minutes=d))
    before = conn.total_changes
    plan_rollback(conn, s, clock(), chg)
    assert conn.total_changes == before and not conn.in_transaction


@pytest.mark.parametrize("result", ["failed", "aborted", "planned"])
def test_plan_rollback_requires_successful_apply(conn, s, result):
    """TC-488: 성공하지 않은 변경(실패·중단·미확정)은 롤백 대상이 아니다. [FR-011]"""
    rid = add_change(conn, result=result, at=NOW, backup=canonical_json(SNIPPET), prev=SNIPPET["title"])
    with pytest.raises(SafetyGateError):
        plan_rollback(conn, s, clock(), rid)


def test_plan_rollback_refuses_rollback_rows_and_unknown(conn, s):
    """TC-489: 롤백 행을 다시 롤백하거나 없는 번호를 지정하면 거부한다. [FR-011]"""
    rid = add_change(conn, change_type="rollback", at=NOW, backup=canonical_json(SNIPPET), prev=SNIPPET["title"])
    with pytest.raises(SafetyGateError):
        plan_rollback(conn, s, clock(), rid)
    with pytest.raises(InputError):
        plan_rollback(conn, s, clock(), 4242)


@pytest.mark.parametrize("backup", [None, "", "{깨짐", "[]", json.dumps({"description": "x"}), json.dumps({"title": 5}), json.dumps({"title": "이력과 다른 제목"})])
def test_plan_rollback_requires_consistent_backup(conn, s, backup):
    """TC-490: 백업 snippet이 없거나 깨졌거나 이력의 이전 제목과 다르면 롤백 계획을 만들지 않고 복구 방법을 안내한다. [SEC-006, NFR-010]"""
    add_video(conn)
    rid = add_change(conn, at=NOW - timedelta(days=1), backup=backup, prev="겨울 전기요금", new="바뀐 제목")
    with pytest.raises(SafetyGateError) as exc:
        plan_rollback(conn, s, clock(), rid)
    assert "백업" in exc.value.message


def test_plan_rollback_only_for_latest_change(conn, s):
    """TC-491: 같은 영상에 이후 변경(성공 또는 미확정)이 있으면 오래된 제목으로 덮어쓰지 않도록 거부한다. 다른 영상·실패한 행은 영향이 없다. [FR-011, SEC-009]"""
    cid, chg, plan = applied_world(conn, s)
    add_change(conn, "zzzzzzzzzzz", at=NOW)
    add_change(conn, result="failed", at=NOW)
    plan_rollback(conn, s, clock(), chg)
    later = add_change(conn, result="planned", at=NOW)
    with pytest.raises(SafetyGateError) as exc:
        plan_rollback(conn, s, clock(), chg)
    assert f"#{later}" in exc.value.message


def test_plan_rollback_requires_candidate_in_applied_state(conn, s):
    """TC-492: 후보가 applied/evaluated가 아니면(이미 rolled_back 등) 롤백 계획을 만들지 않는다. evaluated는 허용. [설계 3-2]"""
    cid, chg, plan = applied_world(conn, s)
    conn.execute("UPDATE title_candidates SET status='evaluated' WHERE id=?", (cid,))
    conn.commit()
    plan_rollback(conn, s, clock(), chg)
    conn.execute("UPDATE title_candidates SET status='rolled_back' WHERE id=?", (cid,))
    conn.commit()
    with pytest.raises(SafetyGateError):
        plan_rollback(conn, s, clock(), chg)


def test_plan_rollback_without_candidate_row_link(conn, s):
    """TC-493: 후보가 연결되지 않은 이력(candidate_id 없음)도 롤백 계획은 만들 수 있다. 연결은 있는데 후보가 사라졌으면 거부한다. [FR-011]"""
    add_video(conn, snippet={**SNIPPET, "title": "바뀐 제목"})
    rid = add_change(conn, at=NOW - timedelta(days=1), backup=canonical_json(SNIPPET), prev=SNIPPET["title"], new="바뀐 제목")
    assert plan_rollback(conn, s, clock(), rid).candidate_id is None
    conn.execute("PRAGMA foreign_keys = OFF")
    rid2 = add_change(conn, "bbbbbbbbbbb", cid=777, at=NOW, backup=canonical_json(SNIPPET), prev=SNIPPET["title"], new="바뀐 제목")
    add_video(conn, "bbbbbbbbbbb", snippet={**SNIPPET, "title": "바뀐 제목"})
    with pytest.raises(SafetyGateError):
        plan_rollback(conn, s, clock(), rid2)


def test_plan_rollback_needs_fresh_fetch_and_changed_title(conn, s):
    """TC-494: 저장된 영상 정보가 없으면 fetch를 안내하고, 이미 원래 제목이면 되돌릴 것이 없다고 알린다. [FR-011, NFR-007]"""
    rid = add_change(conn, at=NOW - timedelta(days=1), backup=canonical_json(SNIPPET), prev=SNIPPET["title"], new="바뀐 제목")
    with pytest.raises(InputError) as exc:
        plan_rollback(conn, s, clock(), rid)
    assert "fetch" in exc.value.next_step
    add_video(conn)   # 현재 제목 == 원래 제목
    with pytest.raises(InputError) as exc:
        plan_rollback(conn, s, clock(), rid)
    assert "이미 원래 제목" in exc.value.message


def test_plan_rollback_allows_long_original_even_if_limit_lowered(conn, s):
    """TC-495: 설정의 제목 길이 상한을 나중에 낮춰도 원래 제목 복원은 막히지 않는다. [FR-011]"""
    cid, chg, plan = applied_world(conn, s)
    assert plan_rollback(conn, replace(s, hard_max_chars=3), clock(), chg).restore_title == "겨울 전기요금"


# ───────────── 롤백 DB 처리 ─────────────

def test_rollback_db_flow_end_to_end(conn, s):
    """TC-496: 롤백 DB 처리 전체: 계획 → 롤백 행(planned, 확인자·해시·현재 snippet 백업) → 성공 기록 → 후보 applied→rolled_back, 원래 적용 행은 그대로, 같은 변경은 다시 롤백 불가. [FR-011, SEC-006, 설계 3-2]"""
    cid, chg, plan = applied_world(conn, s)
    rp = plan_rollback(conn, s, clock(), chg)
    rid = begin_rollback(conn, rp, approver="홍길동", typed_video_id=VID, run_id="run2", now=NOW + timedelta(hours=1))
    r = get_change(conn, rid)
    assert (r["change_type"], r["result"], r["previous_title"], r["new_title"], r["candidate_id"], r["plan_hash"], r["approver"], r["reason"]) == ("rollback", "planned", plan.new_title, "겨울 전기요금", cid, rp.plan_hash, "홍길동", f"롤백 대상 변경 #{chg}")
    assert json.loads(r["backup_snippet_json"])["title"] == plan.new_title
    assert cand_status(conn, cid) == "applied"
    finish_change(conn, rid, "success", NOW + timedelta(hours=1, minutes=1), verify_result={"title_ok": True})
    assert cand_status(conn, cid) == "rolled_back" and get_change(conn, rid)["result"] == "success"
    assert get_change(conn, chg)["result"] == "success" and get_change(conn, chg)["change_type"] == "apply"
    with pytest.raises(SafetyGateError):
        plan_rollback(conn, s, clock(), chg)
    with pytest.raises(SafetyGateError):
        transition_candidate(conn, cid, "applied", NOW)


def test_rollback_failure_leaves_candidate_applied(conn, s):
    """TC-497: 롤백 호출이 실패하면 후보는 applied로 남고 같은 변경을 다시 롤백 계획할 수 있다(실패 행은 '이후 변경'이 아님). [FR-011, NFR-008]"""
    cid, chg, plan = applied_world(conn, s)
    rid = begin_rollback(conn, plan_rollback(conn, s, clock(), chg), approver="홍길동", typed_video_id=VID, run_id=None, now=NOW)
    finish_change(conn, rid, "failed", NOW, error_code="YT-700")
    assert cand_status(conn, cid) == "applied"
    plan_rollback(conn, s, clock(), chg)


def test_begin_rollback_requires_typed_video_id_and_approver(conn, s):
    """TC-498: 영상 ID를 직접 입력해 확인하지 않았거나 확인자가 없으면 롤백 행을 만들지 않는다(승인 없는 상태 변경 불가). [EVT-007, SEC-001]"""
    cid, chg, plan = applied_world(conn, s)
    rp = plan_rollback(conn, s, clock(), chg)
    n = change_count(conn)
    for typed in ("", "zzzzzzzzzzz", VID.lower(), VID + " ", None):
        with pytest.raises(SafetyGateError):
            begin_rollback(conn, rp, approver="홍길동", typed_video_id=typed, run_id=None, now=NOW)
    for who in (None, "", "  "):
        with pytest.raises(SafetyGateError):
            begin_rollback(conn, rp, approver=who, typed_video_id=VID, run_id=None, now=NOW)
    assert change_count(conn) == n


def test_begin_rollback_rejects_tampered_or_outdated_plan(conn, s):
    """TC-499: 롤백 계획 내용이 해시와 다르거나, 계획 이후 같은 영상에 새 변경이 생겼거나, 후보 상태가 바뀌었으면 중단한다. DB 오류는 DatabaseError. [SEC-014, SEC-009]"""
    cid, chg, plan = applied_world(conn, s)
    rp = plan_rollback(conn, s, clock(), chg)
    with pytest.raises(SafetyGateError):
        begin_rollback(conn, replace(rp, restore_title="다른 제목"), approver="a", typed_video_id=VID, run_id=None, now=NOW)
    with pytest.raises(SafetyGateError):
        begin_rollback(conn, replace(rp, snippet={**rp.snippet, "description": "x"}), approver="a", typed_video_id=VID, run_id=None, now=NOW)
    conn.execute("CREATE TRIGGER no_ins3 BEFORE INSERT ON title_changes BEGIN SELECT RAISE(ABORT, 'x'); END")
    with pytest.raises(DatabaseError):
        begin_rollback(conn, rp, approver="a", typed_video_id=VID, run_id=None, now=NOW)
    conn.execute("DROP TRIGGER no_ins3")
    conn.execute("UPDATE title_candidates SET status='filtered'")
    conn.commit()
    with pytest.raises(SafetyGateError):
        begin_rollback(conn, rp, approver="a", typed_video_id=VID, run_id=None, now=NOW)
    conn.execute("UPDATE title_candidates SET status='applied'")
    add_change(conn, result="planned", at=NOW)
    conn.commit()
    with pytest.raises(SafetyGateError) as exc:
        begin_rollback(conn, rp, approver="a", typed_video_id=VID, run_id=None, now=NOW)
    assert "다른 변경" in exc.value.message
