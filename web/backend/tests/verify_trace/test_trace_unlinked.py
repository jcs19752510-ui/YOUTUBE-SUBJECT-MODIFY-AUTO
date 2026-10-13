"""추적성 보강 시험 (t 에이전트, 2026-10-13). 요구 원문: docs/yt/02_planning.md, DESIGN.md.

시험 연결이 없던 요구 중 시험 가능한 것만 다룬다. 기대값은 요구 원문에서 가져왔고 구현에 맞추지 않았다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
# CLI 의존성(googleapiclient 등)이 있는 별도 가상환경. 웹 가상환경에는 CLI 의존성이 없다.
import os
CLI_PY = os.environ.get("TRACE_CLI_PY", str(ROOT / ".harness-tmp/t-cli/bin/python"))


def _run(args, cwd=ROOT, timeout=300):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


# ---- NFR-006: 제목 검증기·요청 본문 구성 모듈 줄 커버리지 90% 이상 (02_planning §6-1) ----
def test_tc_trace_nfr006_validator_and_request_body_line_coverage_at_least_90(tmp_path):
    out = tmp_path / "cov.json"
    r = _run([CLI_PY, "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header",
              "tests/test_validator.py", "tests/test_banned_terms.py", "tests/test_textsafe.py",
              "tests/test_live_guard.py", "tests/test_updater.py", "tests/test_apply_cmd.py",
              "--cov=youtube_title", f"--cov-report=json:{out}", "-o", "pythonpath=src"])
    assert out.exists(), r.stdout[-800:] + r.stderr[-800:]
    files = json.loads(out.read_text())["files"]
    pct = {}
    for name in ("validator.py", "live_guard.py", "updater.py"):
        key = next(k for k in files if k.replace("\\", "/").endswith("youtube_title/" + name))
        pct[name] = files[key]["summary"]["percent_covered_display"], files[key]["summary"]["num_statements"]
    below = {k: v for k, v in pct.items() if float(v[0]) < 90.0}
    assert not below, f"줄(+분기) 커버리지 90% 미만: {below} 전체 {pct}"


# ---- SEC-013: 신규 의존성 버전 고정 (실존·라이선스 확인은 절차, 시험은 고정 부분만) ----
@pytest.mark.parametrize("path", ["requirements.txt", "requirements-dev.txt", "web/backend/requirements.txt", "web/backend/requirements-dev.txt"])
def test_tc_trace_sec013_dependencies_are_version_pinned(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    reqs = [l for l in text.splitlines() if l and not l.startswith(("#", " ", "-")) and "==" in l or (l and not l.startswith(("#", " ", "-")) and re.match(r"^[A-Za-z0-9_.\-\[\]]+", l))]
    assert reqs, path
    unpinned = [l for l in reqs if "==" not in l]
    assert not unpinned, f"{path}: 버전 미고정 {unpinned}"


def test_tc_trace_sec013_backend_lock_has_hashes():
    text = (ROOT / "web/backend/requirements.txt").read_text(encoding="utf-8")
    assert "--hash=sha256:" in text


# ---- W-015: 기존 CLI 유지(웹이 src/youtube_title 을 복사 없이 임포트, CLI 도 동작) ----
def test_tc_trace_w015_cli_still_runs_and_web_imports_it_without_copy():
    r = _run([CLI_PY, "-I", "-c", "import sys; sys.path.insert(0, 'src'); sys.argv=['youtube_title','--help']; "
              "from youtube_title.cli import main; sys.exit(main(['--help']))"])
    assert r.returncode == 0 and "usage" in (r.stdout + r.stderr).lower(), r.stderr[-500:]
    import ytweb  # noqa: F401
    web_src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "web/backend/ytweb").rglob("*.py"))
    assert re.search(r"from youtube_title|import youtube_title", web_src)
    assert not (ROOT / "web/backend/ytweb/youtube_title").exists()


def test_tc_trace_w015_cli_regression_suite_passes():
    r = _run([CLI_PY, "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", "tests/test_cli.py",
              "tests/test_validate_cmd.py", "tests/test_plan_cmd.py", "tests/test_rollback_cmd.py", "-o", "pythonpath=src"])
    assert r.returncode == 0, r.stdout[-1500:]


# ---- S-W10: CSV 업로드 검증 — 업로드 기능 자체가 없음(M2 대기). 요구가 구현되면 이 시험이 켜지도록 xfail(strict) ----
@pytest.mark.xfail(strict=True, reason="미구현: CSV 업로드 엔드포인트 없음(S-W10, DESIGN M2 대기). 구현되면 이 xfail 을 제거하고 검증 시험을 쓴다")
def test_tc_trace_sw10_csv_upload_endpoint_exists():
    routers = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "web/backend/ytweb/routers").glob("*.py"))
    assert re.search(r"UploadFile|csv.*upload|upload.*csv", routers, re.I)


# ---- POL-007: 외부 AI 전송 고지(서비스명·서버 위치, 자막·성과 제외, 설명의 이름·연락처 삭제 권고) ----
@pytest.mark.xfail(strict=True, reason="미구현 의심: Gemini 어댑터가 외부 전송을 하는데 화면 고지 문구(서비스명·서버 위치·자막·성과 제외·이름/연락처 삭제 권고)를 프런트 소스에서 못 찾음(POL-007)")
def test_tc_trace_pol007_external_ai_transfer_notice_in_frontend():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "web/frontend/src").rglob("*.ts*") if ".test." not in p.name)
    assert "Gemini" in src or "Google" in src
    assert re.search(r"자막", src) and re.search(r"연락처", src) and re.search(r"서버", src)


# ---- SEC-027: AI 호출 일/배치당 호출·토큰·비용 상한, 빈도 제한, 재시도 상한, 타임아웃 ----
def test_tc_trace_sec027_gemini_has_retry_cap_timeout_and_output_token_cap():
    from ytweb.ai import gemini
    assert gemini.TIMEOUT_SEC > 0 and gemini.MAX_OUTPUT_TOKENS > 0
    assert len(gemini.RETRY_WAIT_SEC) >= 1 and len(gemini.RETRY_WAIT_SEC) <= 5


@pytest.mark.xfail(strict=True, reason="미구현: AI 호출 일/배치당 횟수·비용 상한과 빈도 제한 코드 없음(SEC-027 일부, 02_planning/DESIGN 에 미구현 명시)")
def test_tc_trace_sec027_daily_or_batch_ai_call_cap_exists():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "web/backend/ytweb").rglob("*.py"))
    assert re.search(r"(daily|per_day|max)_ai_calls|ai_call_(cap|limit)|AI_DAILY|ai_daily", src, re.I)
