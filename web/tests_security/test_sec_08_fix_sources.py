"""SEC-08 수정 단위가 만든 설정·소스 변경의 정적 보안 시험 (9단계 재검증, 개정 2판). 저장소 소스를 읽기만 한다.

`YTWEB_SEC_ROOT` 로 저장소 사본을 가리킬 수 있다(mutation_check.py 의 설정 변이 점검용).
법률 자문이 아니다: 문구의 법적 충분성은 판단하지 않고 존재·연결·일치만 본다.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

REPO = Path(os.environ.get("YTWEB_SEC_ROOT", Path(__file__).resolve().parents[2]))
DISC = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."


def _read(*parts: str) -> str:
    return REPO.joinpath(*parts).read_text(encoding="utf-8")


def test_disclaimer_sentence_is_identical_in_server_cli_and_frontend():
    cli = _read("src", "youtube_title", "ui.py")
    m = re.search(r"DISCLAIMER\s*=\s*\(?\s*[\"']([^\"']+)[\"']", cli)
    assert m and m.group(1) == DISC, m and m.group(1)
    assert f'DISCLAIMER = "{DISC}"' in _read("web", "backend", "ytweb", "domain", "notices.py")
    assert f"disclaimer: '{DISC}'" in _read("web", "frontend", "src", "i18n", "ko.ts")


def test_frontend_disclaimer_footer_is_outside_routed_outlet_and_ab_gate_blocks_execute():
    layout = _read("web", "frontend", "src", "app", "Layout.tsx")
    assert "ko.legal.disclaimer" in layout and "ko.legal.aiNotice" in layout
    assert layout.index("</main>") < layout.index("ko.legal.disclaimer"), "면책 푸터가 라우트 영역(<main>) 밖 상시 영역이어야 한다"
    batch = _read("web", "frontend", "src", "pages", "BatchDetailPage.tsx")
    assert "disabled={phrase !== expected || !abAck}" in batch
    card = _read("web", "frontend", "src", "pages", "SuggestionCard.tsx")
    assert "ko.legal.aiNotice" in card and "ko.legal.aiLimit" in card
    reports = _read("web", "frontend", "src", "pages", "ReportsPage.tsx")
    assert "ko.legal.disclaimer" in reports


def test_stale_requeue_is_bounded_and_skips_locked_rows():
    src = _read("web", "backend", "ytweb", "core", "jobs.py")
    assert "MAX_ATTEMPTS" in src and "skip_locked=True" in src
    assert 'STALE_AFTER_BY_TYPE: dict[str, timedelta] = {"batch.execute": timedelta(minutes=5)}' in src


def test_recovered_apply_is_audited_without_secrets():
    src = _read("web", "backend", "ytweb", "domain", "batches.py")
    i = src.index('"restart_recovery"')
    assert 'action="change.apply"' in src
    chunk = src[i - 400: i + 100]
    assert not re.search(r"token|secret|password|pin|snippet", chunk, re.I)


def test_nginx_api_header_file_matches_page_headers_except_csp():
    d = REPO / "web" / "docker" / "nginx"
    page = [l.strip() for l in (d / "security-headers.conf").read_text(encoding="utf-8").splitlines() if l.startswith("add_header")]
    api = [l.strip() for l in (d / "security-headers-api.conf").read_text(encoding="utf-8").splitlines() if l.startswith("add_header")]
    assert len(page) == len(api) == 7
    non_csp = lambda ls: sorted(l for l in ls if "Content-Security-Policy" not in l)
    assert non_csp(page) == non_csp(api)
    csp = [l for l in api if "Content-Security-Policy" in l][0]
    assert "default-src 'none'" in csp and "unsafe" not in csp and "frame-ancestors 'none'" in csp
    conf = (d / "nginx.conf").read_text(encoding="utf-8")
    locs = re.findall(r"location (?:= )?(/api[^\s{]*)\s*\{(.*?)\n        \}", conf, re.S)
    assert len(locs) >= 4
    for name, body in locs:
        assert "security-headers-api.conf" in body, name
    assert re.search(r"location = /healthz \{[^}]*return 404", conf, re.S) and re.search(r"location = /readyz \{[^}]*return 404", conf, re.S)
    assert "proxy_hide_header Cache-Control;" in (d / "proxy.conf").read_text(encoding="utf-8")
    # web.Dockerfile 이 새 헤더 파일을 이미지에 넣는다
    assert "security-headers-api.conf /etc/nginx/snippets/security-headers-api.conf" in _read("web", "docker", "web.Dockerfile")


def test_api_image_copies_only_runtime_directories_and_restore_regrants_are_in_audit_guard():
    df = _read("web", "docker", "api.Dockerfile")
    assert not re.search(r"^COPY\s+web/backend\s+/app/backend\s*$", df, re.M), "web/backend 전체 복사로 되돌아갔다(개발 캐시·시험이 이미지에 들어갈 수 있음, DEF-9-017)"
    for need in ("COPY web/backend/ytweb /app/backend/ytweb", "COPY web/backend/alembic /app/backend/alembic", "COPY web/backend/alembic.ini /app/backend/alembic.ini"):
        assert need in df, need
    guard = _read("web", "docker", "db", "audit-guard.sql")
    assert re.search(r"REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public\.alembic_version FROM ytweb_app", guard)
    assert re.search(r"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public\.audit_log FROM ytweb_app", guard)
    assert "RAISE EXCEPTION" in guard
