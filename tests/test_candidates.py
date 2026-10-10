import json
import os

import pytest

from ytitle.candidates import MAX_BYTES, load_candidate_file, list_candidate_files
from ytitle.errors import InputError

VID = "abc123DEF45"


def good(**over):
    d = {"video_id": VID, "current_title": "겨울철 전기요금", "topic": "life", "summary": "겨울철 난방 습관으로 전기요금을 줄이는 방법",
         "source": "human", "candidates": [{"title": "전기요금 줄이는 난방 습관", "evidence": "난방 습관으로 전기요금을 줄이는 방법"}]}
    d.update(over)
    return d


@pytest.fixture
def cdir(tmp_path):
    d = tmp_path / "candidates"
    d.mkdir()
    return d


def write(cdir, data, name=f"{VID}.json", raw=None):
    p = cdir / name
    p.write_bytes(raw if raw is not None else json.dumps(data, ensure_ascii=False).encode("utf-8"))
    return p


def test_valid_file_loads(cdir):
    """TC-300: 올바른 후보 파일이 읽히고 해시가 기록된다. [FR-001, EVT-201]"""
    cf = load_candidate_file(write(cdir, good()), cdir)
    assert cf.video_id == VID and cf.topic == "life" and cf.candidates[0].title == "전기요금 줄이는 난방 습관"
    assert len(cf.sha256) == 64 and cf.file_name == f"{VID}.json" and cf.description_excerpt is None


def test_bom_utf8_accepted(cdir):
    """TC-301: 윈도 메모장/PowerShell이 붙이는 UTF-8 BOM이 있어도 읽힌다. [FR-001, NFR-002]"""
    raw = b"\xef\xbb\xbf" + json.dumps(good(), ensure_ascii=False).encode("utf-8")
    assert load_candidate_file(write(cdir, None, raw=raw), cdir).video_id == VID


def test_cp949_file_gives_encoding_guidance(cdir):
    """TC-302: UTF-8이 아닌 파일(cp949)은 저장 방법을 안내하는 오류가 된다. [FR-001, NFR-007]"""
    raw = json.dumps(good(), ensure_ascii=False).encode("cp949")
    with pytest.raises(InputError) as ei:
        load_candidate_file(write(cdir, None, raw=raw), cdir)
    assert "UTF-8" in ei.value.message and "메모장" in ei.value.next_step


def test_json_syntax_error_reports_position(cdir):
    """TC-303: JSON 문법 오류는 줄·칸 위치를 알려 준다. [FR-001, NFR-007]"""
    with pytest.raises(InputError) as ei:
        load_candidate_file(write(cdir, None, raw=b'{"video_id": "abc123DEF45",\n "x": }'), cdir)
    assert "줄" in ei.value.message and "칸" in ei.value.message


@pytest.mark.parametrize("raw", [b"[]", b'"text"', b"123", b"null"])
def test_non_object_root_rejected(cdir, raw):
    """TC-304: 맨 바깥이 객체가 아닌 JSON은 거부한다. [FR-001, SEC-011]"""
    with pytest.raises(InputError):
        load_candidate_file(write(cdir, None, raw=raw), cdir)


def test_path_traversal_rejected(cdir, tmp_path):
    """TC-305: candidates 폴더 밖 경로(../)와 다른 폴더의 파일은 거부한다. [SEC-011, RISK-010]"""
    outside = tmp_path / f"{VID}.json"
    outside.write_text(json.dumps(good()), encoding="utf-8")
    for p in (cdir / ".." / f"{VID}.json", outside, str(tmp_path / "candidates" / "sub" / ".." / ".." / f"{VID}.json")):
        with pytest.raises(InputError) as ei:
            load_candidate_file(p, cdir)
        assert "candidates 폴더" in ei.value.message


@pytest.mark.skipif(os.name == "nt", reason="심볼릭 링크 권한이 필요함")
def test_symlink_escape_rejected(cdir, tmp_path):
    """TC-306: candidates 안에 있어도 폴더 밖 파일을 가리키는 심볼릭 링크는 거부한다. [SEC-011]"""
    target = tmp_path / "real" / f"{VID}.json"
    target.parent.mkdir()
    target.write_text(json.dumps(good()), encoding="utf-8")
    os.symlink(target, cdir / f"{VID}.json")
    with pytest.raises(InputError):
        load_candidate_file(cdir / f"{VID}.json", cdir)


@pytest.mark.parametrize("name", ["abc.json", "abc123DEF45x.json", "abc123DEF4!.json", "abc123DEF45.txt", "한글영상아이디.json", "abc 123DEF45.json"])
def test_bad_file_names_rejected(cdir, name):
    """TC-307: 영상 ID 형식(11자 영문·숫자·-·_)이 아닌 파일 이름은 거부한다. [SEC-011]"""
    p = cdir / name
    p.write_text(json.dumps(good()), encoding="utf-8")
    with pytest.raises(InputError):
        load_candidate_file(p, cdir)


def test_missing_file_message(cdir):
    """TC-308: 없는 파일은 위치를 알려 주는 오류가 된다. [FR-001, NFR-007]"""
    with pytest.raises(InputError) as ei:
        load_candidate_file(cdir / f"{VID}.json", cdir)
    assert "찾을 수 없습니다" in ei.value.message


def test_video_id_must_match_file_name(cdir):
    """TC-309: video_id가 파일 이름과 다르면 거부한다(엉뚱한 영상 지정 방지). [SEC-011]"""
    with pytest.raises(InputError) as ei:
        load_candidate_file(write(cdir, good(video_id="zzzzzzzzzzz")), cdir)
    assert "video_id" in ei.value.message


def test_size_limit(cdir):
    """TC-310: 256KB를 넘는 파일은 열기 전에 거부한다. [SEC-011, SEC-016]"""
    with pytest.raises(InputError) as ei:
        load_candidate_file(write(cdir, None, raw=b" " * (MAX_BYTES + 1)), cdir)
    assert "너무 큽니다" in ei.value.message
    assert load_candidate_file(write(cdir, good(summary="가" * 100)), cdir)


def test_candidate_count_limit_boundaries(cdir):
    """TC-311: 후보는 1~20개만 허용한다(0개·21개 거부, 20개 허용). [SEC-011, FR-001]"""
    one = {"title": "제목", "evidence": "근거"}
    assert len(load_candidate_file(write(cdir, good(candidates=[one] * 20)), cdir).candidates) == 20
    for n in (0, 21):
        with pytest.raises(InputError):
            load_candidate_file(write(cdir, good(candidates=[one] * n)), cdir)


@pytest.mark.parametrize("patch,needle", [
    ({"summary": ""}, "summary"), ({"summary": None}, "summary"), ({"source": 5}, "source"),
    ({"current_title": "가" * 301}, "current_title"), ({"topic": "sports"}, "topic"),
    ({"candidates": [{"title": "제목"}]}, "evidence"), ({"candidates": [{"title": "", "evidence": "x"}]}, "title"),
    ({"candidates": ["문자열"]}, "형태"), ({"candidates": "목록아님"}, "candidates"),
    ({"description_excerpt": 3}, "description_excerpt"),
])
def test_field_errors_are_specific(cdir, patch, needle):
    """TC-312: 필드별 오류(형식·길이·누락)는 어느 항목이 문제인지 한국어로 알려 준다. [FR-001, NFR-007]"""
    with pytest.raises(InputError) as ei:
        load_candidate_file(write(cdir, good(**patch)), cdir)
    assert needle in ei.value.message and ei.value.next_step


def test_multiple_errors_reported_together(cdir):
    """TC-313: 여러 문제는 한 번에 모두 알려 준다(2번 고치게 만들지 않음). [NFR-007]"""
    with pytest.raises(InputError) as ei:
        load_candidate_file(write(cdir, good(summary="", source=1, topic="x")), cdir)
    assert ei.value.message.count("\n  - ") >= 3


def test_missing_source_rejected_for_pol004(cdir):
    """TC-314: source(후보 생성 출처) 필드는 필수다. [POL-004]"""
    d = good()
    del d["source"]
    with pytest.raises(InputError) as ei:
        load_candidate_file(write(cdir, d), cdir)
    assert "source" in ei.value.message


def test_list_candidate_files_sorted_and_only_json(cdir):
    """TC-315: 폴더 목록은 .json 파일만 정렬해서 돌려주고, 폴더가 없으면 빈 목록이다. [EVT-003]"""
    write(cdir, good(), name="bbbbbbbbbbb.json")
    write(cdir, good(), name="aaaaaaaaaaa.json")
    (cdir / "memo.txt").write_text("x")
    assert [p.name for p in list_candidate_files(cdir)] == ["aaaaaaaaaaa.json", "bbbbbbbbbbb.json"]
    assert list_candidate_files(cdir / "없는폴더") == []
