"""6단계 독립 검증 9: 모의 게이트웨이 계약(통째 교체·입력 검증), 공용 도구(KST 경계·승인자·페이지 보정), 핸들러 등록, 라이브 코드 부재(M1)."""
from __future__ import annotations

import ast
import copy
import pathlib
from datetime import date, datetime, timezone

import pytest

from ytweb.core import jobs
from ytweb.db.models import Video
from ytweb.domain.common import MAX_PAGE_SIZE, clamp_page, kst_day_bounds, single_line
from ytweb.youtube.base import GatewayError, make_excerpt
from ytweb.youtube.mock import MockYouTubeGateway

from tests.verify_wb.vbh import life_ids

ROOT = pathlib.Path(__file__).resolve().parents[2] / "ytweb"


def test_tc_vb_270_mock_gateway_replaces_whole_snippet_like_youtube(seeded, db, clock):
    """통째 교체: body 에 빠진 항목은 사라진다(그래서 도메인이 snippet 전체를 보내야 함)."""
    vid = life_ids(db, 1)[0]
    g = MockYouTubeGateway(db, clock)
    snap = g.read_snippet(vid)
    snap["title"] = "새 제목"
    snap.pop("description")
    snap["localized"] = {"title": "옛", "description": "d"}
    out = g.update_snippet(vid, {"id": vid, "snippet": snap})
    again = g.read_snippet(vid)
    assert again == out and "description" not in again and again["title"] == "새 제목" and again["localized"]["title"] == "새 제목"
    v = db.get(Video, vid)
    assert v.title == "새 제목" and v.description_excerpt is None
    snap2 = g.read_snippet(vid)
    snap2["title"] = "변경 중 원본 보호"
    assert g.read_snippet(vid)["title"] == "새 제목"          # 읽기 결과는 사본(변경해도 저장소 불변)


@pytest.mark.parametrize("body, code", [
    ({"id": "demoVid0001", "snippet": {"title": "  ", "categoryId": "26"}}, "invalid_request"),
    ({"id": "demoVid0001", "snippet": {"title": "t"}}, "invalid_request"),
    ({"id": "demoVid0001", "snippet": {"title": "t", "categoryId": ""}}, "invalid_request"),
    ({"id": "demoVid0001", "snippet": {"title": 3, "categoryId": "26"}}, "invalid_request"),
    ({"id": "otherVid0001", "snippet": {"title": "t", "categoryId": "26"}}, "invalid_request"),
    ({"id": "demoVid0001", "snippet": "x"}, "invalid_request"),
])
def test_tc_vb_271_mock_gateway_rejects_malformed_body(seeded, db, clock, body, code):
    g = MockYouTubeGateway(db, clock)
    before = copy.deepcopy(db.get(Video, "demoVid0001").snippet)
    with pytest.raises(GatewayError) as e:
        g.update_snippet("demoVid0001", body)
    assert e.value.code == code and e.value.definite is True
    assert db.get(Video, "demoVid0001").snippet == before


def test_tc_vb_272_mock_gateway_unknown_video(db, clock):
    g = MockYouTubeGateway(db, clock)
    assert g.read_snippet("nope0000000") is None
    with pytest.raises(GatewayError) as e:
        g.update_snippet("nope0000000", {"id": "nope0000000", "snippet": {"title": "t", "categoryId": "1"}})
    assert e.value.code == "video_not_found"


def test_tc_vb_273_make_excerpt():
    assert make_excerpt(None) is None and make_excerpt("   ") is None
    assert make_excerpt("a  b\n c") == "a b c"
    assert len(make_excerpt("가" * 1000)) == 280


def test_tc_vb_274_kst_day_bounds_and_page_clamp():
    s, e = kst_day_bounds(date(2026, 10, 10))
    assert s == datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc) and e == datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)
    assert clamp_page(0, 0) == (1, 1) and clamp_page(-4, 99999) == (1, MAX_PAGE_SIZE) and clamp_page(3, 50) == (3, 50)


def test_tc_vb_275_single_line_strips_controls_and_truncates():
    assert single_line("a\n\tb\x00c   d", 100) == "a bc d"
    assert len(single_line("가" * 500, 200)) == 200


def test_tc_vb_276_handlers_registered_on_package_import():
    import ytweb.domain  # noqa: F401
    for t in ("videos.sync", "suggestions.generate", "batch.execute"):
        assert jobs.get_handler(t) is not None, t


def test_tc_vb_277_worker_loader_returns_scheduler():
    from ytweb.worker import load_domain_handlers
    fn = load_domain_handlers()
    assert callable(fn) and fn.__name__ == "run_due_items"


def test_tc_vb_278_no_live_youtube_or_external_ai_code_in_m1():
    """M1 데모 한정(DEC-038): 도메인·AI·유튜브 모듈에 네트워크/외부 SDK 호출 코드가 없다(정적 점검: 임포트와 호출 이름)."""
    banned_imports = {"requests", "httpx", "urllib", "urllib3", "socket", "googleapiclient", "google", "openai", "anthropic", "aiohttp", "http", "smtplib", "ftplib"}
    for sub in ("domain", "ai", "youtube"):
        for path in (ROOT / sub).glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        assert a.name.split(".")[0] not in banned_imports, (path.name, a.name)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    assert node.module.split(".")[0] not in banned_imports, (path.name, node.module)
    ai_factory = (ROOT / "ai" / "factory.py").read_text(encoding="utf-8")
    assert "mode != \"demo\"" in ai_factory
    with pytest.raises(ValueError):
        from ytweb.ai.factory import get_suggester
        get_suggester("live")


def test_tc_vb_279_routers_have_no_state_change_via_get():
    """라우터 정적 점검: @router.get 핸들러 안에 상태 변경 서비스(approve/execute/rollback/cancel/reject/edit 등) 호출이 없다."""
    mutators = {"approve", "reject", "edit_title", "create_draft", "execute_batch", "cancel_batch", "rollback_change", "apply_one", "generate_for_video", "enqueue", "seed_demo"}
    for path in (ROOT / "routers").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            is_get = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "get" and getattr(d.func.value, "id", "") == "router" for d in fn.decorator_list)
            if not is_get:
                continue
            called = {c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", "") for c in ast.walk(fn) if isinstance(c, ast.Call)}
            assert not (called & mutators), (path.name, fn.name, called & mutators)
