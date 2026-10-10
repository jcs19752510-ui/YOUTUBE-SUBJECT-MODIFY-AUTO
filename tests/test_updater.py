import ast
import copy
import json
import re
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from wu4_support import NOW, SNIPPET, VID, add_candidate, add_change, add_video, clock, make_settings, open_db, ts

from ytitle import updater
from ytitle.errors import InputError, SafetyGateError
from ytitle.updater import build_update_body, canonical_json, compute_plan_hash, create_plan, execute_update, is_stale, parse_snippet, sequential_exclusions, validate_new_title

SRC = Path(__file__).resolve().parent.parent / "src" / "ytitle"


@pytest.fixture
def s(project):
    return make_settings(project)


@pytest.fixture
def conn(tmp_path):
    c = open_db(tmp_path / "t.sqlite3")
    yield c
    c.close()


def planned(conn, s, **kw):
    add_video(conn, **{k: v for k, v in kw.items() if k in ("privacy", "kids", "live", "duration", "fetched_at")})
    cid = add_candidate(conn, **{k: v for k, v in kw.items() if k in ("status", "result", "title", "reasons")})
    return cid, create_plan(conn, s, clock(), cid)


# ───────────── canonical JSON / plan_hash ─────────────

def test_canonical_json_is_order_independent_and_keeps_hangul():
    """TC-421: canonical JSON은 키 순서와 무관하고 공백이 없으며 한글을 이스케이프하지 않는다. [SEC-014, EVT-004]"""
    a = canonical_json({"b": 1, "a": "한글", "c": [3, 1]})
    assert a == canonical_json({"c": [3, 1], "a": "한글", "b": 1}) == '{"a":"한글","b":1,"c":[3,1]}'


def test_plan_hash_is_deterministic_hex():
    """TC-422: 같은 입력이면 plan_hash가 항상 같은 64자리 16진수이고, snippet의 키 순서가 달라도 같다. [SEC-014, EVT-004]"""
    h1 = compute_plan_hash(VID, 7, "이전", "새 제목", SNIPPET)
    h2 = compute_plan_hash(VID, 7, "이전", "새 제목", dict(reversed(list(SNIPPET.items()))))
    assert h1 == h2 and re.fullmatch(r"[0-9a-f]{64}", h1)
    assert h1 == compute_plan_hash(VID, 7, "이전", "새 제목", copy.deepcopy(SNIPPET))


def test_plan_hash_golden_value():
    """TC-423: plan_hash 규격을 고정한다(고정 입력의 기대 해시 값). 규격이 바뀌면 이미 만든 승인 파일이 모두 무효가 되므로 실수로 못 바꾸게 한다. [SEC-014]"""
    assert compute_plan_hash("v", 1, "a", "b", {"title": "a"}) == "48e6bce30a705e1d3b5990a43d7e90d60cc69c51e5906d9645dceee59fdb5212"
    assert compute_plan_hash("abc123DEF45", 7, "이전", "새 제목", {"title": "이전", "categoryId": "26", "tags": ["가"]}, kind="rollback", change_id=3) == "0790a513cf368257e790596bb1c378db60e8ddebc7921b929f704c3c21deb47a"


@pytest.mark.parametrize("mutate", [
    lambda a: {**a, "video_id": "zzzzzzzzzzz"},
    lambda a: {**a, "candidate_id": 8},
    lambda a: {**a, "previous_title": "이전 "},
    lambda a: {**a, "new_title": "새 제목!"},
    lambda a: {**a, "snippet": {**SNIPPET, "description": SNIPPET["description"] + "."}},
    lambda a: {**a, "snippet": {**SNIPPET, "tags": list(reversed(SNIPPET["tags"]))}},
    lambda a: {**a, "snippet": {**SNIPPET, "categoryId": "27"}},
    lambda a: {**a, "snippet": {k: v for k, v in SNIPPET.items() if k != "defaultLanguage"}},
    lambda a: {**a, "kind": "rollback"},
    lambda a: {**a, "kind": "rollback", "change_id": 3},
])
def test_plan_hash_changes_when_anything_changes(mutate):
    """TC-424: 영상·후보·이전/새 제목·snippet의 어떤 항목이 달라져도(설명 1글자, 태그 순서, 카테고리 포함) 해시가 달라진다. [SEC-014, SEC-009]"""
    base = {"video_id": VID, "candidate_id": 7, "previous_title": "이전", "new_title": "새 제목", "snippet": SNIPPET, "kind": "apply", "change_id": None}
    assert compute_plan_hash(**base) != compute_plan_hash(**mutate(base))


def test_plan_hash_field_boundaries_are_unambiguous():
    """TC-425: 이전/새 제목 경계를 옮긴 입력("ab","c" vs "a","bc")이 같은 해시가 되지 않는다. [SEC-014]"""
    assert compute_plan_hash(VID, 1, "ab", "c", SNIPPET) != compute_plan_hash(VID, 1, "a", "bc", SNIPPET)


# ───────────── 요청 본문 / 보존 ─────────────

def test_body_preserves_every_other_field():
    """TC-426: 요청 본문은 snippet 전체에서 title만 다르다(description·tags·categoryId·기타 전부 보존). [SEC-005, FR-009, K-3]"""
    before = copy.deepcopy(SNIPPET)
    body = build_update_body(VID, SNIPPET, "새 제목")
    assert body["id"] == VID and body["snippet"]["title"] == "새 제목"
    assert {k: v for k, v in body["snippet"].items() if k != "title"} == {k: v for k, v in before.items() if k != "title"}
    assert body["snippet"]["description"] == before["description"] and body["snippet"]["tags"] == before["tags"] and body["snippet"]["categoryId"] == "26"
    assert SNIPPET == before


def test_body_is_a_deep_copy():
    """TC-427: 본문을 고쳐도 원본 snippet(백업 재료)이 바뀌지 않는다. [SEC-005]"""
    body = build_update_body(VID, SNIPPET, "새 제목")
    body["snippet"]["tags"].append("x")
    body["snippet"]["localized"]["title"] = "변조"
    assert SNIPPET["tags"] == ["전기요금", "난방", "시니어"] and SNIPPET["localized"]["title"] == "겨울 전기요금"


@pytest.mark.parametrize("raw", [None, 5, "", "{not json", "[]", '"str"', json.dumps({"description": "x", "categoryId": "1"}), json.dumps({"title": "", "categoryId": "1"}), json.dumps({"title": 5, "categoryId": "1"})])
def test_parse_snippet_rejects_broken_data(raw):
    """TC-428: 깨졌거나 제목이 없는 저장 snippet은 거부하고 fetch를 안내한다. [SEC-005, NFR-007]"""
    with pytest.raises(InputError) as exc:
        parse_snippet(raw, VID)
    assert "fetch" in exc.value.next_step


@pytest.mark.parametrize("cat", [None, "", 22])
def test_parse_snippet_requires_category_id(cat):
    """TC-429: categoryId가 없는 snippet으로는 쓰기 본문을 만들지 않는다(카테고리가 지워지는 사고 방지). [T-15, SEC-005]"""
    with pytest.raises(InputError) as exc:
        parse_snippet(json.dumps({"title": "x", "categoryId": cat}), VID)
    assert "categoryId" in exc.value.message


# ───────────── 새 제목 최소 규격 ─────────────

@pytest.mark.parametrize("bad", ["", "   ", None, 5, "a<b", "a>b", "a\x1bb", "a\nb", "a‮b", "a\x7fb", "가" * 101])
def test_validate_new_title_rejects(s, bad):
    """TC-430: 빈 제목·`<` `>`·제어/방향 문자·101자 초과는 쓰기 계획 단계에서도 거부한다(마지막 방어선). [FR-002, SEC-019, YouTube 규격]"""
    with pytest.raises(InputError):
        validate_new_title(bad, s)


def test_validate_new_title_accepts_boundary_and_emoji(s):
    """TC-431: 100자는 통과하고, 이모지 결합 문자(ZWJ)는 거부하지 않는다. 길이 검사를 끄면 긴 원래 제목도 복원 가능하다. [FR-002]"""
    assert validate_new_title("가" * 100, s) == "가" * 100
    assert validate_new_title("가족\U0001F468‍\U0001F469 산책", s)
    assert validate_new_title("가" * 150, s, check_length=False)


# ───────────── create_plan ─────────────

def test_create_plan_success_reads_only(conn, s):
    """TC-432: 정상 후보는 diff·본문·해시·보존 항목을 갖춘 계획이 되고, 계획 생성은 DB를 전혀 바꾸지 않는다. [FR-008, EVT-004, SEC-001]"""
    add_video(conn)
    cid = add_candidate(conn)
    before = conn.total_changes
    p = create_plan(conn, s, clock(), cid)
    assert (p.video_id, p.previous_title, p.new_title) == (VID, "겨울 전기요금", "겨울철 전기요금 줄이는 난방 습관")
    assert p.preserved_fields == tuple(sorted(k for k in SNIPPET if k != "title"))
    assert p.body == build_update_body(VID, SNIPPET, p.new_title) and p.plan_hash == compute_plan_hash(VID, cid, p.previous_title, p.new_title, SNIPPET)
    assert p.ready and not p.stale and p.validation_result == "pass"
    assert conn.total_changes == before
    assert conn.execute("SELECT COUNT(*) FROM title_changes").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM title_candidates WHERE id=?", (cid,)).fetchone()[0] == "filtered"


def test_plan_hash_depends_on_current_snippet(conn, s):
    """TC-433: 영상 정보(설명)가 Studio에서 바뀌어 다시 fetch되면 같은 후보라도 plan_hash가 달라진다(승인 무효화 근거). [SEC-014, SEC-009, T-14]"""
    add_video(conn)
    cid = add_candidate(conn)
    h1 = create_plan(conn, s, clock(), cid).plan_hash
    add_video(conn, snippet={**SNIPPET, "description": SNIPPET["description"] + " (수정)"})
    assert create_plan(conn, s, clock(), cid).plan_hash != h1


@pytest.mark.parametrize("status,result", [("blocked", "block"), ("filtered", "block"), ("blocked", "pass")])
def test_create_plan_refuses_blocked_candidate(conn, s, status, result):
    """TC-434: 차단된 후보는(상태 또는 검증 결과 중 하나만 차단이어도) 계획을 만들지 않고 안전 게이트 오류(종료 코드 3)이다. [FR-005, POL-001, SEC-001]"""
    add_video(conn)
    cid = add_candidate(conn, status=status, result=result)
    with pytest.raises(SafetyGateError) as exc:
        create_plan(conn, s, clock(), cid)
    assert exc.value.exit_code == 3 and "차단" in exc.value.message


@pytest.mark.parametrize("status,result", [("candidate", None), ("filtered", None), ("candidate", "pass")])
def test_create_plan_refuses_unvalidated(conn, s, status, result):
    """TC-435: 검증을 통과하지 않은(또는 결과가 비어 있는) 후보는 거부한다(fail-closed). [FR-005]"""
    add_video(conn)
    cid = add_candidate(conn, status=status, result=result)
    with pytest.raises(SafetyGateError) as exc:
        create_plan(conn, s, clock(), cid)
    assert "validate" in exc.value.next_step


@pytest.mark.parametrize("status", ["applied", "evaluated", "rolled_back"])
def test_create_plan_refuses_finished_candidates(conn, s, status):
    """TC-436: 이미 적용·평가·롤백된 후보는 다시 계획하지 않는다. [설계 3-2]"""
    add_video(conn)
    cid = add_candidate(conn, status=status)
    with pytest.raises(SafetyGateError):
        create_plan(conn, s, clock(), cid)


@pytest.mark.parametrize("status,result", [("approved", "pass"), ("filtered", "warn")])
def test_create_plan_allows_approved_and_warn(conn, s, status, result):
    """TC-437: 승인됨(approved) 후보와 경고(warn) 후보도 계획은 볼 수 있다(경고는 사유와 함께 표시). [설계 3-2, FR-005]"""
    add_video(conn)
    cid = add_candidate(conn, status=status, result=result, reasons=[["EXCL", "warn", "느낌표 1개"]])
    p = create_plan(conn, s, clock(), cid)
    assert p.validation_result == result and p.reasons == (("EXCL", "warn", "느낌표 1개"),)


def test_create_plan_missing_candidate_and_video(conn, s):
    """TC-438: 없는 후보 번호나, 영상 정보를 fetch한 적 없는 후보는 안내와 함께 InputError이다. [EVT-004, SCR-003]"""
    with pytest.raises(InputError) as exc:
        create_plan(conn, s, clock(), 999)
    assert "validate" in exc.value.next_step
    cid = add_candidate(conn)
    with pytest.raises(InputError) as exc:
        create_plan(conn, s, clock(), cid)
    assert "fetch" in exc.value.next_step


def test_create_plan_same_title_rejected(conn, s):
    """TC-439: 새 제목이 현재 제목과 같으면(쿼터·횟수 낭비) 거부한다. [FR-008]"""
    add_video(conn)
    cid = add_candidate(conn, title=SNIPPET["title"])
    with pytest.raises(InputError):
        create_plan(conn, s, clock(), cid)


def test_create_plan_cache_mismatch_rejected(conn, s):
    """TC-440: videos.title 열과 snippet_json의 제목이 다르면(캐시 훼손) 거부한다. [SEC-005, SEC-009]"""
    add_video(conn, title="다른 제목")
    cid = add_candidate(conn)
    with pytest.raises(InputError):
        create_plan(conn, s, clock(), cid)


def test_create_plan_rechecks_new_title_rules(conn, s):
    """TC-441: DB의 후보 제목이 규격 위반이면(검증 이후 변조 등) 계획 단계에서 다시 거부한다. [FR-002, T-02]"""
    add_video(conn)
    cid = add_candidate(conn, title="좋은 제목 <script>")
    with pytest.raises(InputError):
        create_plan(conn, s, clock(), cid)


def test_stale_boundary_24_hours():
    """TC-442: 저장 시각이 24시간 이내면 최신, 24시간을 넘으면(또는 읽을 수 없으면) 오래된 것으로 본다. [EVT-004]"""
    assert not is_stale(ts(NOW - timedelta(hours=24)), NOW)
    assert is_stale(ts(NOW - timedelta(hours=24, seconds=1)), NOW)
    assert is_stale("엉터리", NOW) and is_stale(None, NOW)


def test_plan_marks_stale_video(conn, s):
    """TC-443: 영상 정보가 25시간 전 것이면 plan.stale이 참이다(경고 표시용). [EVT-004]"""
    cid, p = planned(conn, s, fetched_at=ts(NOW - timedelta(hours=25)))
    assert p.stale


def test_plan_not_ready_when_limits_fail(conn, s):
    """TC-444: 교체 제한에 걸리면 plan.ready가 거짓이다(72시간 이내 재변경). [FR-014, SEC-004]"""
    add_change(conn, at=NOW - timedelta(hours=1))
    cid, p = planned(conn, s)
    assert not p.ready and not p.limits.passed


def test_plan_not_ready_when_quota_short(conn, s):
    """TC-445: 오늘 남은 쿼터가 필요량(쓰기 50 + 조회 2)보다 적으면 ready가 거짓이다. [SEC-002, SCR-003]"""
    s2 = replace(s, daily_limit_units=51)
    cid, p = planned(conn, s2)
    assert p.quota.needed == 52 and p.quota.remaining == 51 and not p.quota.enough and not p.ready
    cid, p = planned(conn, replace(s, daily_limit_units=52))
    assert p.quota.enough and p.ready


def test_reasons_unreadable_json_is_flagged(conn, s):
    """TC-446: 검증 사유 JSON이 깨져 있어도 계획은 만들되 사유를 읽을 수 없다는 경고 항목을 넣는다. [FR-005]"""
    add_video(conn)
    cid = add_candidate(conn)
    conn.execute("UPDATE title_candidates SET validation_reasons_json = '{깨짐'")
    conn.commit()
    assert create_plan(conn, s, clock(), cid).reasons[0][0] == "REASONS_UNREADABLE"


# ───────────── 제외 영상군 ─────────────

def _row(conn, **kw):
    add_video(conn, **kw)
    return conn.execute("SELECT * FROM videos WHERE video_id=?", (VID,)).fetchone()


@pytest.mark.parametrize("kw,needle", [
    ({"privacy": "private"}, "비공개"), ({"kids": 1}, "아동용"), ({"live": "upcoming"}, "라이브"), ({"live": "live"}, "라이브"),
    ({"duration": 180}, "Shorts"), ({"duration": None}, "길이를 알 수 없어"), ({"privacy": None}, "공개 상태를 알 수 없음"), ({"kids": None}, "아동용 여부를 알 수 없음"),
])
def test_sequential_exclusions_reasons(conn, s, kw, needle):
    """TC-447: 비공개·아동용·예약 라이브/프리미어·Shorts(180초 이하)·모르는 값은 제외 사유가 된다. [POL-003, FR-019]"""
    assert any(needle in r for r in sequential_exclusions(_row(conn, **kw), s))


def test_sequential_exclusions_boundary_and_clean(conn, s):
    """TC-448: 181초 공개·일반 영상은 제외 사유가 없다. [POL-003]"""
    assert sequential_exclusions(_row(conn, duration=181), s) == ()


def test_exclusions_enforced_only_in_sequential_mode(conn, s):
    """TC-449: 순차 교체 모드가 켜지면 제외 영상은 계획을 거부하고, 꺼져 있으면 계획은 만들되 제외 사유를 알린다(비공개 테스트 영상 첫 적용을 막지 않기 위함). [POL-003, FR-019, SEC-012]"""
    add_video(conn, privacy="private")
    cid = add_candidate(conn)
    p = create_plan(conn, s, clock(), cid)
    assert p.exclusions == ("비공개 영상",) and not p.exclusions_enforced
    with pytest.raises(SafetyGateError) as exc:
        create_plan(conn, replace(s, sequential_enabled=True), clock(), cid)
    assert "비공개" in exc.value.message


# ───────────── 쓰기 없음 ─────────────

class FakeService:
    """어떤 속성에 접근하든 기록하고 실패하는 가짜 YouTube 서비스."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        self.calls.append(name)
        raise AssertionError(f"쓰기/조회 호출 시도: {name}")


def test_execute_update_is_a_refusing_stub():
    """TC-450: 쓰기 실행 자리는 어떤 인자로 불러도 SafetyGateError로 거부하고 가짜 서비스를 건드리지 않는다. [SEC-001, DESIGN 1-3 WU-4]"""
    svc = FakeService()
    for args in ((), (svc, {"id": VID}), (svc,)):
        with pytest.raises(SafetyGateError) as exc:
            execute_update(*args, live=True)
        assert "활성화되지 않았" in exc.value.message
    assert svc.calls == []


@pytest.mark.parametrize("name", ["updater.py", "limits.py", "history.py", "commands/plan.py", "commands/rollback.py"])
def test_no_youtube_write_or_network_code_in_sources(name):
    """TC-451: 이 단위의 모듈에는 구글/네트워크 import, 서비스 객체 접근(.videos), 업데이트 호출(.update), 쓰기 호출 문자열이 없다. [SEC-001, SEC-007, K-2]"""
    text = (SRC / name).read_text(encoding="utf-8")
    tree = ast.parse(text)
    banned_roots = {"googleapiclient", "google", "google_auth_oauthlib", "requests", "urllib", "urllib3", "http", "httplib2", "socket", "ssl", "selenium", "playwright", "ytitle.auth", "ytitle.youtube_read", "ytitle.retry"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & banned_roots, (name, ast.dump(node))
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned_roots and (node.module or "") not in banned_roots, (name, node.module)
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"update", "videos", "insert", "request", "urlopen"}, (name, node.attr)
    for bad in ("videos().update", ".update(body", "videos.update(", "build(", "requests.", "urlopen"):
        assert bad not in text, (name, bad)


def test_no_dict_update_calls_in_sources():
    """TC-452: 위 소스 검사가 `.update` 속성 접근을 전부 막으므로 dict.update도 쓰지 않는다는 사실을 별도로 고정한다(우회 불가). [SEC-001]"""
    for name in ("updater.py", "limits.py", "history.py", "commands/plan.py", "commands/rollback.py"):
        assert ".update(" not in (SRC / name).read_text(encoding="utf-8"), name


def test_module_has_gateway_protocol_only():
    """TC-453: 쓰기 규약(UpdateGateway)은 Protocol 선언만 있고 구현 클래스가 없다. [SEC-001]"""
    assert hasattr(updater, "UpdateGateway") and updater.UpdateGateway.__dict__.get("update_snippet") is not None
    impls = [n for n in vars(updater).values() if isinstance(n, type) and n is not updater.UpdateGateway and "update_snippet" in vars(n)]
    assert impls == []


def test_db_read_failures_become_database_error(conn, s):
    """TC-454: 후보·영상 테이블을 읽지 못하면 DatabaseError(한국어 안내)로 변환한다. [NFR-007]"""
    from ytitle.errors import DatabaseError
    add_video(conn)
    cid = add_candidate(conn)
    conn.execute("ALTER TABLE videos RENAME TO videos_gone")
    with pytest.raises(DatabaseError) as exc:
        create_plan(conn, s, clock(), cid)
    assert exc.value.next_step
    conn.execute("ALTER TABLE title_candidates RENAME TO cands_gone")
    with pytest.raises(DatabaseError):
        create_plan(conn, s, clock(), cid)


def test_plan_uses_the_candidates_own_video(conn, s):
    """TC-455: 여러 영상이 저장돼 있어도 후보가 가리키는 영상의 snippet으로 계획을 만든다(다른 영상 정보로 본문을 만들지 않음). [SEC-005, T-15]"""
    other = {**SNIPPET, "title": "다른 영상", "description": "남의 설명", "categoryId": "10"}
    add_video(conn, "zzzzzzzzzzz", snippet=other)
    add_video(conn)
    cid = add_candidate(conn)
    p = create_plan(conn, s, clock(), cid)
    assert p.video_id == VID and p.snippet == SNIPPET and p.body["snippet"]["description"] == SNIPPET["description"] and p.body["id"] == VID
