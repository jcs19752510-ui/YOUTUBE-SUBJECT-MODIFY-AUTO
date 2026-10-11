"""W-FIX-INF 독립 검증 시험(6단계, 2026-10-11) — TC-VFI-001 부터. 구현자 시험(test_fix_inf.py, TC-WIX-*)을 복사하지 않고 결함 재현 절차에서 새로 만들었다.

구성
  A. 정적(기본 실행, 도커 불필요): nginx 설정을 직접 파싱해 "위치별 실효 헤더"를 계산, 헤더 중복 불변식, 정확 일치 위치, .gitignore 의미(git check-ignore), 문서 일관성
  B. 도커 하네스(VFI_DOCKER=1): 일회용 nginx(스텁 백엔드가 중복 헤더를 일부러 보냄), 실제 .dockerignore 로 빌드 컨텍스트 걸러내기
  C. 실가동(VFI_LIVE=1): 이미 떠 있는 임시 compose 프로젝트(harness-tmp-vfi*)에서 복원 권한·헤더·하드닝·네트워크 실측
  D. pwsh(VFI_PWSH=<pwsh 7 경로>): 운영 스크립트 backup.ps1/restore.ps1 경유 복원

환경변수: VFI_ROOT(저장소 사본 루트, 변이 점검용; 기본 실제 저장소), VFI_PROJECT(기본 harness-tmp-vfi), VFI_PORT(기본 18180),
          VFI_STACK_DIR(compose.yaml·scripts·secrets 사본, D 구간), VFI_DOCKER=1, VFI_LIVE=1, VFI_PWSH
안전장치: 프로젝트 이름은 반드시 harness-tmp- 로 시작해야 한다(운영 스택 보호). 복원 시험은 그 프로젝트 DB 를 덮어쓴다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve()
ROOT = Path(os.environ.get("VFI_ROOT") or HERE.parents[2])
WEB = ROOT / "web"
DOCKER_DIR = WEB / "docker"
NGINX = Path(os.environ.get("VFI_NGX_DIR") or (DOCKER_DIR / "nginx"))
PROJECT = os.environ.get("VFI_PROJECT", "harness-tmp-vfi")
PORT = os.environ.get("VFI_PORT", "18180")
STACK = Path(os.environ["VFI_STACK_DIR"]) if os.environ.get("VFI_STACK_DIR") else None
PWSH = os.environ.get("VFI_PWSH")

needs_docker = pytest.mark.skipif(os.environ.get("VFI_DOCKER") != "1", reason="VFI_DOCKER=1 필요(도커 데몬)")
live = pytest.mark.skipif(os.environ.get("VFI_LIVE") != "1", reason="VFI_LIVE=1 필요(임시 compose 스택)")
needs_pwsh = pytest.mark.skipif(not (os.environ.get("VFI_LIVE") == "1" and PWSH and STACK), reason="VFI_LIVE=1, VFI_PWSH, VFI_STACK_DIR 필요")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def sh(cmd: list[str], timeout: int = 120, input_: str | None = None, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_, env=env, cwd=str(cwd) if cwd else None)


# ======================================================================================
# A-1. nginx 설정 파서: 위치(location)별 "실효 응답 헤더" 계산
# ======================================================================================

def strip_comments(t: str) -> str:
    return "\n".join(re.sub(r"(?<!\S)#.*$", "", ln) for ln in t.splitlines())


def parse_block(text: str) -> list:
    """중괄호 구조를 (directive, args, children|None) 목록으로 단순 파싱한다(따옴표 안의 ; { } 는 무시)."""
    i, n = 0, len(text)
    out, stack = [], []
    cur = out
    buf = ""
    q = None
    while i < n:
        c = text[i]
        if q:
            buf += c
            if c == q:
                q = None
        elif c in "'\"":
            q = c
            buf += c
        elif c == ";":
            if buf.strip():
                cur.append((buf.strip(), None))
            buf = ""
        elif c == "{":
            node = (buf.strip(), [])
            cur.append(node)
            stack.append(cur)
            cur = node[1]
            buf = ""
        elif c == "}":
            if buf.strip():
                cur.append((buf.strip(), None))
            buf = ""
            cur = stack.pop()
        else:
            buf += c
        i += 1
    return out


def find(nodes: list, head: str) -> list:
    return [n for n in nodes if n[0] == head or n[0].startswith(head + " ")]


def expand_includes(nodes: list) -> list:
    """snippets include 를 파일 내용으로 펼친다(/etc/nginx/snippets/X → NGINX/X, mime.types 는 무시)."""
    res = []
    for d, kids in nodes:
        m = re.fullmatch(r"include\s+/etc/nginx/snippets/(\S+)", d)
        if m:
            res.extend(expand_includes(parse_block(strip_comments(read(NGINX / m.group(1))))))
        elif kids is not None:
            res.append((d, expand_includes(kids)))
        else:
            res.append((d, kids))
    return res


def server_node() -> tuple[list, list]:
    conf = expand_includes(parse_block(strip_comments(read(NGINX / "nginx.conf"))))
    http = find(conf, "http")[0][1]
    server = find(http, "server")[0][1]
    return http, server


def add_headers(nodes: list) -> list[tuple[str, str]]:
    out = []
    for d, kids in nodes:
        if kids is None and d.startswith("add_header "):
            m = re.fullmatch(r'add_header\s+(\S+)\s+("(?:[^"]*)"|\S+)(\s+always)?', d)
            assert m, d
            out.append((m.group(1).lower(), m.group(2).strip('"')))
    return out


def locations() -> dict[str, list]:
    _, server = server_node()
    return {d[len("location "):].strip(): kids for d, kids in server if d.startswith("location ") and kids is not None}


def effective_headers(loc: list) -> list[tuple[str, str]]:
    """nginx 상속 규칙: location 에 add_header 가 하나라도 있으면 상위(server)의 add_header 는 모두 무시된다."""
    own = add_headers(loc)
    if own:
        return own
    _, server = server_node()
    return add_headers(server)


def test_tc_vfi_001_every_location_emits_each_header_name_at_most_once():
    """DEF-7-001 근본 원인 점검: 한 위치에서 같은 이름의 헤더를 nginx 가 두 번 붙이지 않는다(추가형 중복 방지)."""
    locs = locations()
    assert len(locs) >= 9, list(locs)
    for name, body in locs.items():
        names = [h for h, _ in effective_headers(body)]
        dup = {x for x in names if names.count(x) > 1}
        assert not dup, (name, dup)
        assert "content-security-policy" in names and "x-content-type-options" in names, name   # 어떤 위치도 보안 헤더가 빠지지 않는다(상속 소실 방지)


def test_tc_vfi_002_each_location_has_complete_security_header_set_and_cache_rule():
    sec = {"content-security-policy", "x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy",
           "cross-origin-opener-policy", "cross-origin-resource-policy"}
    _, server = server_node()
    for name, body in locations().items():
        eff = effective_headers(body)
        names = {h for h, _ in eff}
        assert sec <= names, (name, sec - names)
        cc = [v for h, v in eff if h == "cache-control"]
        if name == "= /nginx-health":
            assert cc == [], name                        # 프로브 경로: 캐시 헤더 없음(기존 동작)
            continue
        assert len(cc) == 1, (name, cc)
        if name.startswith("= /") or name.startswith("/api/"):
            assert cc == ["no-store"], (name, cc)        # 상태·API 경로는 항상 no-store
    # server 수준에도 보안 헤더 한 벌이 있다(상속되는 위치, 예: 413 오류 페이지)
    assert sec <= {h for h, _ in add_headers(server)}


def test_tc_vfi_003_api_locations_use_none_csp_and_page_locations_use_self_csp():
    for name, body in locations().items():
        csp = [v for h, v in effective_headers(body) if h == "content-security-policy"]
        assert len(csp) == 1, name
        is_proxy = any(d.startswith("proxy_pass") for d, _ in body)
        if is_proxy:
            assert csp[0] == "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'", name
        else:
            assert csp[0].startswith("default-src 'self'") and "script-src 'self'" in csp[0] and "unsafe-eval" not in csp[0] and "'unsafe-inline'" in csp[0].split("style-src-attr")[1] and csp[0].count("'unsafe-inline'") == 1, name


def test_tc_vfi_004_proxy_hides_every_header_nginx_adds_so_only_one_copy_reaches_browser():
    """백엔드가 같은 이름의 헤더를 보내도(스텁이 증명) 브라우저에는 nginx 것 한 벌만 가야 한다: add_header 이름 ⊆ proxy_hide_header 이름."""
    hide = {m.lower() for m in re.findall(r"(?m)^\s*proxy_hide_header\s+(\S+);", strip_comments(read(NGINX / "proxy.conf")))}
    added = set()
    for name, body in locations().items():
        if any(d.startswith("proxy_pass") for d, _ in body):
            added |= {h for h, _ in effective_headers(body)}
    assert added, "프록시 위치가 없다"
    assert added <= hide, added - hide


def test_tc_vfi_005_root_health_locations_are_exact_match_404_and_no_regex_override():
    locs = locations()
    for p in ("/healthz", "/readyz"):
        body = locs[f"= {p}"]
        ds = [d for d, _ in body]
        assert any(re.fullmatch(r'return 404 "[^"]*"', d) for d in ds), p
        assert not any(d.startswith(("proxy_pass", "try_files", "rewrite", "alias", "root")) for d in ds), (p, ds)
        assert "default_type text/plain" in ds, p
    # 정규식 위치(~)가 있으면 정확 일치보다 먼저 평가되지는 않지만(= 가 최우선) 다른 경로의 의미를 바꿀 수 있으므로 금지
    assert not [k for k in locs if k.startswith("~")], list(locs)
    # 상태 점검을 여는 위치는 정확 일치 두 개뿐
    health_proxy = [k for k, b in locs.items() if any(d.startswith("proxy_pass") and "healthz" in d or d.startswith("proxy_pass") and "readyz" in d for d, _ in b)]
    assert sorted(health_proxy) == ["= /api/healthz", "= /api/readyz"]


def test_tc_vfi_006_proxy_pass_targets_are_fixed_upstream_paths():
    locs = locations()
    assert [d for d, _ in locs["= /api/healthz"] if d.startswith("proxy_pass")] == ["proxy_pass $api_upstream/healthz"]
    assert [d for d, _ in locs["= /api/readyz"] if d.startswith("proxy_pass")] == ["proxy_pass $api_upstream/readyz"]
    for k in ("= /api/v1/auth/session", "/api/"):
        assert [d for d, _ in locs[k] if d.startswith("proxy_pass")] == ["proxy_pass $api_upstream"], k
        assert "set $api_upstream http://api:8000" in [d for d, _ in locs[k]], k
    for k in ("= /api/healthz", "= /api/readyz"):
        assert "set $api_upstream http://api:8000" in [d for d, _ in locs[k]], k


def test_tc_vfi_007_rate_limits_and_method_limits_survive_on_api_locations():
    locs = locations()
    assert any(d.startswith("limit_req zone=ytweb_auth") for d, _ in locs["= /api/v1/auth/session"])
    assert any(d.startswith("limit_req zone=ytweb_api") for d, _ in locs["/api/"])
    assert any(d.startswith("limit_req zone=ytweb_api") for d, _ in locs["= /api/healthz"])
    for k in ("= /api/v1/auth/session", "/api/", "/assets/", "/"):
        assert any(d.startswith("limit_except") for d, _ in locs[k]), k
    http, server = server_node()
    assert ("if ($ytweb_host_ok = 0)", ) == tuple(d for d, _ in server if d.startswith("if "))[:1]
    assert any(d.startswith("return 444") for d, _ in find(server, "if")[0][1])


def test_tc_vfi_008_api_header_file_is_page_file_with_only_csp_changed():
    page = dict(add_headers(parse_block(strip_comments(read(NGINX / "security-headers.conf")))))
    api = dict(add_headers(parse_block(strip_comments(read(NGINX / "security-headers-api.conf")))))
    assert set(page) == set(api)
    diff = {k for k in page if page[k] != api[k]}
    assert diff == {"content-security-policy"}, diff


# ======================================================================================
# A-2. 복원 가드 SQL 정적 검사
# ======================================================================================

GUARD = DOCKER_DIR / "db" / "audit-guard.sql"


def test_tc_vfi_010_guard_revokes_before_checking_and_checks_cover_all_revoked_privileges():
    g = read(GUARD)
    for tbl in ("audit_log", "alembic_version"):
        m = re.search(rf"REVOKE ([A-Z, ]+) ON TABLE public\.{tbl} FROM ytweb_app;", g)
        assert m, tbl
        revoked = [x.strip() for x in m.group(1).split(",")]
        assert "SELECT" not in revoked
        assert revoked.index("UPDATE") >= 0 and "DELETE" in revoked and "TRUNCATE" in revoked
        after = g[m.end():]
        for p in revoked:
            assert f"has_table_privilege('ytweb_app', 'public.{tbl}', '{p}')" in after[:after.index("END IF;\n\n") if "END IF;\n\n" in after else len(after)], (tbl, p)
    # 마이그레이션 0001/0002 의 회수 목록과 같다(상태가 복원 전후 같아야 한다)
    m1 = read(WEB / "backend" / "alembic" / "versions" / "0001_initial.py")
    m2 = read(WEB / "backend" / "alembic" / "versions" / "0002_revoke_alembic_version_dml.py")
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM ytweb_app" in m1
    assert "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON alembic_version FROM ytweb_app" in m2
    assert "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public.alembic_version FROM ytweb_app;" in g


def test_tc_vfi_011_guard_is_idempotent_by_construction_and_skips_missing_tables():
    g = read(GUARD)
    assert g.count("to_regclass(") == 2
    assert "DROP " not in g.upper().replace("DROP SCHEMA", "X") and "GRANT " not in re.sub(r"--.*", "", g)       # 권한을 주는 문장 없음(회수·검사만)
    assert g.count("RAISE EXCEPTION") == 3


def test_tc_vfi_012_restore_runs_guard_as_owner_after_pg_restore_and_fails_closed():
    s = read(DOCKER_DIR / "db" / "bin" / "ytweb-db")
    body = s[s.index("cmd_restore()"):s.index("cmd_reset_schema()")]
    assert body.index("pg_restore -h") < body.index("owner_psql -q -f \"$SHARE_DIR/audit-guard.sql\"")
    assert "--single-transaction" in body and "--exit-on-error" in body
    assert "ON_ERROR_STOP=1" in s[s.index("owner_psql()"):s.index("cmd_dump()")]
    assert "set -Eeuo pipefail" in s
    # 성공 메시지는 guard 가 성공한 뒤에만 나온다
    assert body.index("audit-guard.sql") < body.index("echo \"복원 완료")
    d = read(DOCKER_DIR / "db.Dockerfile")
    assert "web/docker/db/audit-guard.sql /usr/local/share/ytweb/audit-guard.sql" in d


# ======================================================================================
# A-3. .gitignore 의미 검사(git check-ignore: 읽기 전용) / 추적 파일 가림 여부
# ======================================================================================

def _git(*args: str) -> subprocess.CompletedProcess:
    return sh(["git", "-C", str(ROOT), *args])


@pytest.fixture(scope="module")
def gitrepo():
    if _git("rev-parse", "--is-inside-work-tree").stdout.strip() != "true":
        pytest.skip("git 저장소가 아님")
    return True


@pytest.mark.parametrize("path", [
    "client_secret.json", "client_secret_123-abc.apps.googleusercontent.com.json", "web/secrets/client_secret_x.json", "docs/yt/my_client_secret.json",
    "a/b/c/client_secret-prod.json", "credentials.json", "credentials_prod.json", "sub/dir/credentials.json", "server.pem", "x/y/server.key", "a/b/cert.p12",
])
def test_tc_vfi_020_gitignore_blocks_secret_like_names(gitrepo, path):
    r = _git("check-ignore", "--no-index", "-q", path)
    assert r.returncode == 0, path


@pytest.mark.parametrize("path", [
    "web/backend/ytweb/app.py", "web/docker/nginx/nginx.conf", "docs/yt/API.md", "config/limits.yaml", "web/frontend/package-lock.json",
    "web/frontend/src/main.tsx", "src/youtube_title/config.py", "README.md", "web/backend/alembic/versions/0002_revoke_alembic_version_dml.py", "web/docker/db/audit-guard.sql",
    "keyboard.md", "monkey.json", "client.json", "secret_santa.txt",
])
def test_tc_vfi_021_gitignore_does_not_swallow_ordinary_files(gitrepo, path):
    r = _git("check-ignore", "--no-index", "-q", path)
    assert r.returncode == 1, path


def test_tc_vfi_022_no_tracked_file_is_hidden_by_new_ignore_patterns(gitrepo):
    r = _git("ls-files", "-ci", "--exclude-standard")
    assert r.returncode == 0
    assert r.stdout.strip() == "", r.stdout[:500]


# ======================================================================================
# A-4. .dockerignore / Dockerfile 정적 불변식
# ======================================================================================

def _patterns(p: Path) -> list[str]:
    return [l.strip() for l in read(p).splitlines() if l.strip() and not l.strip().startswith("#")]


def test_tc_vfi_030_dockerignore_has_no_negation_that_reopens_secrets_and_keeps_old_denies():
    pats = _patterns(ROOT / ".dockerignore")
    assert not [p for p in pats if p.startswith("!")], "허용(부정) 패턴이 비밀형 거부를 되살릴 수 있다"
    for need in ("**/*.pem", "**/*.key", "**/credentials*.json", "**/client_secret*.json", "**/.ruff_cache", "**/.mypy_cache", "**/.coverage", "**/*.p12", "**/id_rsa*",
                 "**/secrets/", "web/secrets/", "web/backups/", ".git", ".env", "data/", ".harness-tmp/", "token*.json", "**/node_modules/"):
        assert need in pats, need


def test_tc_vfi_031_dockerfile_copy_sources_exist_and_are_not_ignored_by_new_patterns():
    """새 .dockerignore 패턴이 이미지에 필요한 추적 파일을 지워 버리는 회귀를 막는다(근사: 접미사·이름 패턴 대조; 실제 빌드는 시험 C 가 확인)."""
    tracked = _git("ls-files").stdout.splitlines()
    needed = [f for f in tracked if f.startswith(("src/youtube_title/", "config/", "web/backend/ytweb/", "web/backend/alembic", "web/frontend/src/", "web/docker/"))]
    assert len(needed) > 100
    bad = [f for f in needed if re.search(r"\.(pem|key|p12)$", f) or re.search(r"(^|/)(credentials[^/]*\.json|client_secret[^/]*\.json|id_rsa[^/]*|\.ruff_cache|\.mypy_cache|\.coverage[^/]*)$", f)]
    assert bad == [], bad


# ======================================================================================
# A-5. 문서 정합성(DEC-046 의 3개 보안 결정이 정확히 기록됐는가)
# ======================================================================================

def _dec046() -> str:
    t = read(ROOT / "docs" / "harness" / "decisions.md")
    return re.search(r"(?m)^\| DEC-046 \|.*$", t).group(0)


def _section(path: Path, start: str, end: str | None) -> str:
    t = read(path)
    s = t[t.index(start):]
    return s[:s.index(end)] if end else s


DOCS = {
    "install": (ROOT / "docs" / "yt" / "WEB_INSTALL.md", "## 7. 알려진 보안 사항", None),
    "runbook": (ROOT / "docs" / "yt" / "WEB_RUNBOOK.md", "### 13-2. 보안 결정", "## 14."),
    "readme": (WEB / "README.md", "## 10. 보안 결정 요약", None),
}


def test_tc_vfi_040_decision_record_says_what_the_docs_must_say():
    d = _dec046()
    for need in ("DEF-9-011", "DEF-9-014", "DEF-9-013", "M1 한정 수용", "30일", "방화벽", "전문가 확인", "M2 착수 전"):
        assert need in d, need


@pytest.mark.parametrize("key", ["install", "runbook", "readme"])
def test_tc_vfi_041_each_doc_records_each_defect_with_its_own_facts(key):
    p, a, b = DOCS[key]
    t = _section(p, a, b)
    # 결함별로 해당 항목 블록 안에서 사실을 찾는다(다른 항목의 문구로 통과하지 못하게)
    blocks = re.split(r"(?=DEF-9-0(?:11|13|14))", t)
    by = {}
    for blk in blocks:
        m = re.match(r"DEF-9-0(11|13|14)", blk)
        if m and m.group(1) not in by:
            by[m.group(1)] = blk[:1500] if key == "readme" else blk
    assert set(by) == {"11", "13", "14"}, (key, set(by))
    assert "방화벽" in by["11"] and "실측" in by["11"] and "Docker Desktop" in by["11"]
    assert "재계산" in by["14"] and ("해시" in by["14"] or "지문" in by["14"]) and "M2" in by["14"]
    assert "30일" in by["13"] and "전문가" in by["13"] and "법률 자문" in by["13"]
    assert "암호화" in by["13"]


@pytest.mark.parametrize("key", ["install", "runbook", "readme"])
def test_tc_vfi_042_docs_do_not_claim_the_three_accepted_risks_are_fixed(key):
    p, a, b = DOCS[key]
    t = _section(p, a, b).split("복원 후 권한(DEF-7-002)")[0].split("**상태 확인 경로 정리")[0]     # 같은 절에 있는 '수정 완료' 항목(다른 결함) 문단은 제외
    for bad in ("해결되었", "해결했", "수정했습니다", "고쳤습니다", "문제 없습니다", "안전합니다", "완전히 막"):
        assert bad not in t, (key, bad)
    assert "수용" in t or "그대로 두" in t


def test_tc_vfi_043_docs_trigger_sets_match_decision_across_all_three_docs():
    for key in ("install", "runbook"):
        p, a, b = DOCS[key]
        t = _section(p, a, b)
        for need in ("외부 접속", "다중 사용자", "M2 착수 전"):
            assert need in t, (key, need)
    # 경로 문서가 새 동작과 일치: 루트 헬스는 404, /api 경로는 JSON
    rb = read(ROOT / "docs" / "yt" / "WEB_RUNBOOK.md")
    assert "일부러 **404**" in rb and "/api/healthz" in rb
    api = read(ROOT / "docs" / "yt" / "API.md")
    assert "nginx는 루트 `/healthz`·`/readyz`를 404로 닫음" in api
    wd = read(ROOT / "docs" / "yt" / "WEB_DESIGN.md")
    assert "루트 경로는 nginx에서 404" in wd


def test_tc_vfi_044_status_script_and_probes_only_use_paths_nginx_serves():
    st = read(WEB / "scripts" / "status.ps1")
    assert "@('/api/healthz', '/api/readyz')" in st
    for f in (WEB / "scripts").glob("*.ps1"):
        for m in re.finditer(r"""(?i)(8080|\$YtwebPort|\$port)[^\n'"]*?(/healthz|/readyz)""", read(f)):
            pytest.fail(f"{f.name}: 루트 헬스 경로를 8080 으로 호출하는 코드: {m.group(0)}")
    assert not re.search(r"""(?m)^\s*(?!#).*localhost:8080/(healthz|readyz)""", read(WEB / "README.md"))


# ======================================================================================
# B. 일회용 nginx 하네스(VFI_DOCKER=1): 백엔드가 같은 이름의 헤더를 보내도 한 벌만 나가는가
# ======================================================================================

STUB_PY = r'''
import json, http.server
class H(http.server.BaseHTTPRequestHandler):
    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else b""
        out = json.dumps({"path": self.path, "method": self.command}).encode()
        code = 307 if self.path.endswith("/redir") else 200
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (("Content-Security-Policy", "default-src *"), ("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "SAMEORIGIN"),
                     ("Referrer-Policy", "no-referrer"), ("Permissions-Policy", "camera=*"), ("Cross-Origin-Opener-Policy", "unsafe-none"),
                     ("Cross-Origin-Resource-Policy", "cross-origin"), ("Cache-Control", "no-store"), ("X-Powered-By", "stub"), ("Server", "stubsrv"),
                     ("Set-Cookie", "a=1; HttpOnly"), ("Set-Cookie", "b=2; HttpOnly")):
            self.send_header(k, v)
        if code == 307:
            self.send_header("Location", "/api/x")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers(); self.wfile.write(out)
    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _go
    def log_message(self, *a): pass
http.server.ThreadingHTTPServer(("0.0.0.0", 8000), H).serve_forever()
'''


def docker(*a: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return sh(["docker", *a], timeout=timeout)


def raw_http(ip: str, path: str, method: str = "GET", host: str = "127.0.0.1:8080", body: bytes | None = None, port: int = 8080, extra: dict | None = None):
    """urllib 이 경로를 다듬거나 헤더를 합치지 않도록 curl 로 원문 응답 헤더를 받는다. 반환: (상태, {이름: [값...]}, 본문)."""
    args = ["curl", "-s", "-m", "10", "--path-as-is", "-i", "-X", method, f"http://{ip}:{port}{path}", "-H", f"Host: {host}"]
    for k, v in (extra or {}).items():
        args += ["-H", f"{k}: {v}"]
    if body is not None:
        args += ["--data-binary", "@-"]
    if method == "HEAD":
        args = ["curl", "-s", "-m", "10", "--path-as-is", "-I", f"http://{ip}:{port}{path}", "-H", f"Host: {host}"]
    r = subprocess.run(args, capture_output=True, input=body, timeout=30)
    raw = r.stdout.decode("latin-1")
    if not raw:
        return 0, {}, ""
    head, _, b = raw.partition("\r\n\r\n")
    lines = head.split("\r\n")
    h: dict[str, list[str]] = {}
    for ln in lines[1:]:
        k, _, v = ln.partition(":")
        h.setdefault(k.strip().lower(), []).append(v.strip())
    return int(lines[0].split()[1]), h, b


@pytest.fixture(scope="module")
def ngx():
    if os.environ.get("VFI_DOCKER") != "1":
        pytest.skip("VFI_DOCKER=1 필요")
    assert PROJECT.startswith("harness-tmp-")
    tag = f"{PROJECT}-vfingx"
    net = tag
    names = [f"{tag}-stub", f"{tag}-web"]
    for n in names:
        docker("rm", "-f", n)
    docker("network", "rm", net)
    assert docker("network", "create", net).returncode == 0
    try:
        r = docker("run", "-d", "--name", names[0], "--network", net, "--network-alias", "api", "--read-only", "--cap-drop", "ALL",
                   "--entrypoint", "python", f"{PROJECT}-api:local", "-c", STUB_PY)
        assert r.returncode == 0, r.stderr
        ng = NGINX
        r = docker("run", "-d", "--name", names[1], "--network", net, "--read-only", "--cap-drop", "ALL", "--tmpfs", "/tmp:rw,noexec,nosuid,uid=101,gid=101,mode=1777",
                   "-v", f"{ng/'nginx.conf'}:/etc/nginx/nginx.conf:ro", "-v", f"{ng/'security-headers.conf'}:/etc/nginx/snippets/security-headers.conf:ro",
                   "-v", f"{ng/'proxy.conf'}:/etc/nginx/snippets/proxy.conf:ro",
                   "-v", f"{ng/'security-headers-api.conf'}:/etc/nginx/snippets/security-headers-api.conf:ro", f"{PROJECT}-web:local")
        assert r.returncode == 0, r.stderr
        ip = ""
        for _ in range(40):
            ip = docker("inspect", names[1], "--format", f"{{{{(index .NetworkSettings.Networks \"{net}\").IPAddress}}}}").stdout.strip()
            if ip and docker("inspect", names[1], "--format", "{{.State.Running}}").stdout.strip() == "true":
                st, _, _ = raw_http(ip, "/nginx-health")
                stub_ok = docker("exec", names[0], "python", "-c", "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/x').read()").returncode == 0
                if st == 200 and stub_ok:
                    break
            time.sleep(0.5)
        else:
            pytest.fail("nginx 하네스 기동 실패: " + docker("logs", names[1]).stderr[-800:])
        yield ip
    finally:
        for n in names:
            docker("rm", "-f", n)
        docker("network", "rm", net)


SEC = ("content-security-policy", "x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy",
       "cross-origin-opener-policy", "cross-origin-resource-policy")


@needs_docker
@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/api/healthz", "/api/readyz", "/api/v1/auth/session", "/api/v1/videos", "/api/v1/x/redir", "//api/v1/videos", "/api/v1/../v1/videos"])
def test_tc_vfi_050_proxied_responses_carry_exactly_one_copy_of_every_nginx_header(ngx, path, method):
    st, h, _ = raw_http(ngx, path, method, body=b"{}" if method in ("POST", "PUT", "PATCH") else None, extra={"Content-Type": "application/json"} if method in ("POST", "PUT", "PATCH") else None)
    if st in (429,):
        pytest.skip("속도 제한에 걸림")
    assert st in (200, 307, 403, 405, 404), (path, method, st)
    for k in SEC:
        assert len(h.get(k, [])) == 1, (path, method, k, h.get(k))
    assert h["content-security-policy"] == ["default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"]
    assert h["cache-control"] == ["no-store"], (path, method, h.get("cache-control"))
    assert "x-powered-by" not in h and h.get("server") == ["nginx"]
    assert h["x-frame-options"] == ["DENY"] and h["cross-origin-resource-policy"] == ["same-origin"]
    if st in (200, 307):
        assert len(h.get("set-cookie", [])) == 2        # 쿠키는 숨기지 않는다(두 개 모두 통과)


@needs_docker
def test_tc_vfi_051_head_on_api_paths_has_single_headers_too(ngx):
    for p in ("/api/healthz", "/api/readyz", "/api/v1/videos"):
        st, h, _ = raw_http(ngx, p, "HEAD")
        assert st == 200 and len(h["cache-control"]) == 1 and len(h["content-security-policy"]) == 1, (p, h)


@needs_docker
@pytest.mark.parametrize("method", ["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"])
@pytest.mark.parametrize("path", ["/healthz", "/readyz", "/healthz?probe=1", "/%68ealthz", "//healthz", "/./healthz", "/x/../healthz", "/api/../readyz", "/%72eadyz"])
def test_tc_vfi_052_root_health_is_404_plain_text_for_every_method_and_spelling(ngx, path, method):
    st, h, body = raw_http(ngx, path, method)
    assert st == 404, (path, method, st)
    if method != "HEAD":
        assert body == "not found\n" or body == "", body
    assert h["content-type"][0].startswith("text/plain")
    assert h["cache-control"] == ["no-store"]
    for k in SEC:
        assert len(h[k]) == 1, k
    assert h["content-security-policy"][0].startswith("default-src 'self'")        # 페이지 정책(루트 경로는 페이지 쪽 설정)
    assert "set-cookie" not in h and "x-request-id" not in h                       # 백엔드에 닿지 않았다


@needs_docker
def test_tc_vfi_053_spa_and_static_paths_unchanged_by_health_blocking(ngx):
    for p in ("/", "/videos", "/healthzx", "/healthz/x", "/api"):
        st, h, body = raw_http(ngx, p)
        if p == "/api":
            assert st in (200, 301, 307, 404, 405), st
            continue
        assert st == 200 and h["content-type"][0].startswith("text/html"), (p, st)
        assert h["cache-control"] == ["no-cache"] and len(h["content-security-policy"]) == 1
    st, h, _ = raw_http(ngx, "/nginx-health")
    assert st == 200 and h["content-type"][0].startswith("text/plain")


@needs_docker
def test_tc_vfi_054_nginx_generated_errors_have_single_headers(ngx):
    st, h, _ = raw_http(ngx, "/api/v1/auth/session", "POST", body=b"x" * (1024 * 1024 + 10), extra={"Content-Type": "application/json"})
    assert st == 413 and len(h["content-security-policy"]) == 1 and "default-src 'none'" in h["content-security-policy"][0] and h["cache-control"] == ["no-store"]
    st, h, _ = raw_http(ngx, "/api/v1/videos", "TRACE")
    assert st in (405, 403) and len(h["content-security-policy"]) == 1
    st, h, _ = raw_http(ngx, "/", "POST", body=b"{}")
    assert st in (403, 405) and len(h["content-security-policy"]) == 1 and "default-src 'self'" in h["content-security-policy"][0]
    st, h, _ = raw_http(ngx, "/api/healthz", host="evil.example")
    assert st == 0                                                                     # 444: 연결 종료
    st, h, _ = raw_http(ngx, "/healthz", host="evil.example")
    assert st == 0                                                                     # 새 위치도 Host 허용 목록 뒤에 있다


@needs_docker
def test_tc_vfi_055_rate_limited_api_response_has_api_headers(ngx):
    seen = None
    for _ in range(40):
        st, h, _ = raw_http(ngx, "/api/v1/auth/session", "POST", body=b"{}", extra={"Content-Type": "application/json"})
        if st == 429:
            seen = h
            break
    assert seen is not None, "429 에 도달하지 못했다"
    assert len(seen["content-security-policy"]) == 1 and "default-src 'none'" in seen["content-security-policy"][0] and seen["cache-control"] == ["no-store"]


# ======================================================================================
# B-2. 실제 .dockerignore 로 빌드 컨텍스트를 걸러 본다(VFI_DOCKER=1)
# ======================================================================================

CTX_FILES = {
    "web/backend/ytweb/app.py": "keep", "web/backend/ytweb/core/x.py": "keep", "web/backend/alembic.ini": "keep", "web/backend/alembic/versions/0002.py": "keep",
    "src/youtube_title/config.py": "keep", "config/limits.yaml": "keep", "web/docker/api.Dockerfile": "keep", "web/frontend/src/main.tsx": "keep",
    "web/frontend/package.json": "keep", "web/backend/requirements.txt": "keep",
    # 걸러져야 하는 것
    "client_secret_1.json": "drop", "web/client_secret_google.json": "drop", "a/b/client_secret_x.json": "drop", "credentials.json": "drop", "a/b/credentials.json": "drop",
    "credentials_prod.json": "drop", "server.pem": "drop", "a/b/c/server.pem": "drop", "id.key": "drop", "a/b/c/id.key": "drop", "a/b/cert.p12": "drop",
    "a/id_rsa": "drop", "a/id_rsa.pub": "drop", "web/backend/.ruff_cache/0.1/x": "drop", "web/backend/.mypy_cache/y": "drop", "web/backend/.coverage": "drop",
    "web/backend/.coverage.host.123": "drop", "src/youtube_title/.ruff_cache/z": "drop", ".env": "drop", "web/.env.local": "drop", "web/secrets/db_owner_password": "drop",
    "web/backups/x.dump": "drop", "data/state.json": "drop", "token.json": "drop", "a/token_x.json": "drop", "docs/x.md": "drop", ".git/config": "drop",
    "web/backend/tests/test_x.py": "drop", "web/frontend/node_modules/m/i.js": "drop", "x/__pycache__/m.pyc": "drop", "README.md": "drop",
}


@needs_docker
def test_tc_vfi_060_real_dockerignore_filters_a_fixture_context():
    assert PROJECT.startswith("harness-tmp-")
    with tempfile.TemporaryDirectory(prefix="vfi-ctx-", dir=str(Path(os.environ.get("VFI_TMP", tempfile.gettempdir())))) as d:
        ctx = Path(d) / "ctx"
        for rel, kind in CTX_FILES.items():
            p = ctx / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(kind)
        shutil.copy(ROOT / ".dockerignore", ctx / ".dockerignore")
        (ctx / "Dockerfile.probe").write_text("FROM scratch\nCOPY . /ctx\n")
        out = Path(d) / "out"
        r = sh(["docker", "buildx", "build", "--no-cache", "-f", str(ctx / "Dockerfile.probe"), "--output", f"type=local,dest={out}", str(ctx)], timeout=180)
        if r.returncode != 0:
            r = sh(["docker", "build", "--no-cache", "-f", str(ctx / "Dockerfile.probe"), "--output", f"type=local,dest={out}", str(ctx)], timeout=180)
        assert r.returncode == 0, r.stderr[-800:]
        got = {str(p.relative_to(out / "ctx")) for p in (out / "ctx").rglob("*") if p.is_file()}
        keep = {k for k, v in CTX_FILES.items() if v == "keep"}
        drop = {k for k, v in CTX_FILES.items() if v == "drop"}
        assert keep <= got, keep - got
        assert not (got & drop), got & drop


DECOYS = ["web/backend/.ruff_cache/0.5/decoy", "web/backend/.coverage", "web/backend/.coverage.host.1", "web/backend/ytweb/.mypy_cache/decoy", "web/backend/key.pem",
          "web/backend/ytweb/server.key", "web/backend/credentials_prod.json", "web/backend/client_secret_x.json", "web/backend/pyproject.toml",
          "web/backend/requirements-dev.txt", "web/backend/tests/test_decoy.py", "web/backend/ytweb.egg-info/PKG-INFO"]
REAL = ["web/backend/ytweb/app.py", "web/backend/alembic/versions/0002.py", "web/backend/alembic.ini", "src/youtube_title/config.py", "config/limits.yaml",
        "web/backend/requirements.txt", "web/docker/requirements-youtube-title.txt"]


def _probe_build(dockerfile_text: str, dockerignore_text: str) -> set[str]:
    with tempfile.TemporaryDirectory(prefix="vfi-img-", dir=os.environ.get("VFI_TMP", tempfile.gettempdir())) as d:
        ctx = Path(d) / "ctx"
        for rel in DECOYS + REAL:
            p = ctx / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x")
        (ctx / ".dockerignore").write_text(dockerignore_text)
        (ctx / "Dockerfile.probe").write_text(dockerfile_text)
        out = Path(d) / "out"
        r = sh(["docker", "buildx", "build", "--no-cache", "-f", str(ctx / "Dockerfile.probe"), "--output", f"type=local,dest={out}", str(ctx)], timeout=180)
        assert r.returncode == 0, r.stderr[-600:]
        return {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file()}


def _runtime_copy_lines(dockerfile: str) -> str:
    rt = dockerfile[dockerfile.index("AS runtime"):]
    return "FROM scratch\n" + "\n".join(l for l in rt.splitlines() if l.startswith("COPY ") and "--from" not in l) + "\n"


@needs_docker
def test_tc_vfi_061_current_api_copy_lines_and_dockerignore_keep_decoys_out_of_image():
    got = _probe_build(_runtime_copy_lines(read(DOCKER_DIR / "api.Dockerfile")), read(ROOT / ".dockerignore"))
    leaked = [x for x in got if any(x.endswith(d.split("/")[-1]) or d.split("/")[-1] in x for d in DECOYS)]
    assert leaked == [], leaked
    assert "app/backend/ytweb/app.py" in got and "app/backend/alembic.ini" in got and "app/backend/alembic/versions/0002.py" in got and "app/src/youtube_title/config.py" in got


@needs_docker
def test_tc_vfi_062_before_fix_state_leaks_decoys_proving_061_is_not_vacuous():
    old_df = sh(["git", "-C", str(ROOT), "show", "994f67d~1:web/docker/api.Dockerfile"])
    old_di = sh(["git", "-C", str(ROOT), "show", "0151987~1:.dockerignore"])
    if old_df.returncode != 0 or old_di.returncode != 0:
        pytest.skip("이전 커밋을 읽을 수 없음")
    got = _probe_build(_runtime_copy_lines(old_df.stdout), old_di.stdout)
    leaked = sorted(x for x in got if re.search(r"(\.ruff_cache|\.coverage|\.pem|\.key|credentials|client_secret|pyproject|requirements-dev|egg-info|\.mypy_cache|test_decoy)", x))
    assert any(".ruff_cache" in x for x in leaked) and any(".coverage" in x for x in leaked), leaked      # 수정 전: 작업 폴더의 미추적 개발 산출물이 이미지로 들어갔다


# ======================================================================================
# C. 실가동(VFI_LIVE=1)
# ======================================================================================

def http(path: str, method: str = "GET", host: str = "127.0.0.1:8080", data: bytes | None = None, headers: dict | None = None):
    return raw_http("127.0.0.1", path, method, host, data, int(PORT), headers)


def db_exec(*cmd: str, input_: str | None = None, timeout: int = 180) -> subprocess.CompletedProcess:
    return sh(["docker", "exec", "-i", f"{PROJECT}-db-1", *cmd], input_=input_, timeout=timeout)


def psql(role: str, sql: str, dbname: str = "ytweb") -> subprocess.CompletedProcess:
    pw = {"postgres": "db_superuser_password", "ytweb_owner": "db_owner_password", "ytweb_app": "db_app_password"}[role]
    return sh(["docker", "exec", "-i", "-e", f"R={role}", "-e", f"F={pw}", "-e", f"D={dbname}", f"{PROJECT}-db-1", "bash", "-c",
               'PGPASSWORD=$(tr -d "\\r\\n" < /run/secrets/$F) psql -h 127.0.0.1 -U $R -d $D -X -At -F"|" -v ON_ERROR_STOP=1'], input_=sql, timeout=120)


PRIVS = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"]


def priv_matrix() -> dict[str, dict[str, bool]]:
    """ytweb_app 의 public 스키마 모든 표 x 모든 권한, 모든 시퀀스 x USAGE/SELECT/UPDATE (실제 has_*_privilege 값)."""
    sql = ("select c.relname, c.relkind, " + ", ".join(f"has_table_privilege('ytweb_app', c.oid, '{p}')" for p in PRIVS) + ", "
           "case when c.relkind='S' then has_sequence_privilege('ytweb_app', c.oid, 'USAGE') end, "
           "case when c.relkind='S' then has_sequence_privilege('ytweb_app', c.oid, 'UPDATE') end "
           "from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind in ('r','S') order by 1")
    r = psql("postgres", sql)
    assert r.returncode == 0, r.stderr
    out: dict[str, dict[str, bool]] = {}
    for ln in r.stdout.strip().splitlines():
        f = ln.split("|")
        row = {p: f[2 + i] == "t" for i, p in enumerate(PRIVS)}
        if f[1] == "S":
            row["SEQ_USAGE"], row["SEQ_UPDATE"] = f[9] == "t", f[10] == "t"
        out[f[0]] = row
    return out


def api_login():
    import httpx
    c = httpx.Client(base_url=f"http://127.0.0.1:{PORT}", headers={"Host": "127.0.0.1:8080", "Origin": "http://127.0.0.1:8080"}, timeout=30)
    r = c.post("/api/v1/auth/session", json={})
    assert r.status_code == 200, r.text
    csrf = r.json().get("csrf_token") or c.get("/api/v1/auth/me").json()["csrf_token"]
    return c, csrf


@live
def test_tc_vfi_070_health_http_matrix_through_real_stack():
    for p in ("/healthz", "/readyz", "/healthz?x=1", "/%68ealthz", "//readyz"):
        st, h, body = http(p)
        assert st == 404 and h["content-type"][0].startswith("text/plain") and "<html" not in body.lower(), p
    for p, want in (("/api/healthz", {"status": "ok"}), ("/api/readyz", {"status": "ok", "db": "ok", "mode": "demo"})):
        st, h, body = http(p)
        assert st == 200 and json.loads(body) == want, p
        assert len(h["cache-control"]) == 1 and h["cache-control"] == ["no-store"]
        assert h["content-security-policy"] == ["default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"]
    st, h, _ = http("/api/healthz", "HEAD")
    assert st in (200, 405) and len(h["cache-control"]) == 1 and len(h["content-security-policy"]) == 1       # 백엔드는 GET 만 연다(405, 수정 전과 동일)
    st, h, body = http("/api/healthz", "POST", data=b"{}", headers={"Content-Type": "application/json"})
    assert st in (403, 405) and len(h["cache-control"]) == 1


@live
def test_tc_vfi_071_authenticated_api_responses_have_single_headers_including_csv():
    c, csrf = api_login()
    try:
        paths = ["/api/v1/auth/me", "/api/v1/settings", "/api/v1/videos", "/api/v1/audit", "/api/v1/batches", "/api/v1/reports/export.csv"]
        for p in paths:
            r = c.get(p)
            assert r.status_code in (200, 404), (p, r.status_code)
            hs = r.headers.multi_items()
            names = [k.lower() for k, _ in hs]
            for k in SEC + ("cache-control",):
                assert names.count(k) == 1, (p, k, names.count(k))
            assert r.headers["cache-control"] == "no-store", p
            assert r.headers["content-security-policy"].startswith("default-src 'none'"), p
            time.sleep(0.05)
        r = c.get("/api/v1/reports/export.csv")
        if r.status_code == 200:
            assert r.headers["content-type"].startswith("text/csv") and "attachment" in r.headers["content-disposition"]
    finally:
        c.close()


@live
def test_tc_vfi_072_page_responses_unchanged():
    st, h, body = http("/")
    assert st == 200 and "<html" in body.lower() and h["cache-control"] == ["no-cache"]
    assert len(h["content-security-policy"]) == 1 and h["content-security-policy"][0].startswith("default-src 'self'; script-src 'self'")
    m = re.search(r'/assets/[^"\']+\.js', body)
    assert m
    st, h, _ = http(m.group(0))
    assert st == 200 and h["cache-control"] == ["public, max-age=31536000, immutable"] and len(h["content-security-policy"]) == 1
    st, h, _ = http(m.group(0) + ".map")
    assert st == 404                                                               # 소스맵은 이미지에 없다


@live
def test_tc_vfi_073_nginx_error_log_has_no_request_lines_after_health_probes():
    for _ in range(5):
        http("/healthz?secret=CANARYQ")
        http("/api/healthz?secret=CANARYQ")
    log = sh(["docker", "logs", f"{PROJECT}-web-1"]).stderr
    assert "CANARYQ" not in log
    out = sh(["docker", "logs", f"{PROJECT}-web-1"]).stdout
    assert "CANARYQ" not in out                                                    # 접근 로그는 $uri 만 기록(쿼리 문자열 제외)


# ------------------------------- 복원 권한 -------------------------------

OLD_GUARD = """DO $$
BEGIN
    IF to_regclass('public.audit_log') IS NOT NULL THEN
        REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.audit_log FROM ytweb_app;
        IF has_table_privilege('ytweb_app', 'public.audit_log', 'UPDATE')
           OR has_table_privilege('ytweb_app', 'public.audit_log', 'DELETE')
           OR has_table_privilege('ytweb_app', 'public.audit_log', 'TRUNCATE') THEN
            RAISE EXCEPTION 'audit_log 권한 회수에 실패했습니다.';
        END IF;
    END IF;
END
$$;
"""      # 수정 전(커밋 0151987 이전) audit-guard.sql 의 본문(audit_log 만 회수) — 결함 DEF-7-002 재현용 대조군


def _dump(name: str) -> None:
    db_exec("ytweb-db", "remove", name)
    r = db_exec("ytweb-db", "dump", name)
    assert r.returncode == 0, r.stdout + r.stderr


def _raw_restore(name: str) -> None:
    r = db_exec("bash", "-c", f"PGPASSWORD=$(tr -d '\\r\\n' < /run/secrets/db_owner_password) pg_restore -h 127.0.0.1 -U ytweb_owner -d ytweb --single-transaction --exit-on-error --clean --if-exists --no-owner /backups/{name}")
    assert r.returncode == 0, r.stderr


@live
def test_tc_vfi_080_defect_reproduction_old_guard_leaves_alembic_version_writable_new_guard_closes_it():
    """원래 재현 절차(DEF-7-002): 백업 → pg_restore --clean → 수정 전 가드. 수정 전 가드로는 앱 계정이 버전표를 고칠 수 있고(FAIL 증명), 현재 가드로는 닫힌다."""
    assert PROJECT.startswith("harness-tmp-")
    name = "vfi080.dump"
    base = priv_matrix()
    assert not any(base["alembic_version"][p] for p in PRIVS if p != "SELECT")      # 시작 상태(0002 적용)
    _dump(name)
    try:
        _raw_restore(name)
        loose = priv_matrix()
        assert loose["alembic_version"]["UPDATE"] and loose["alembic_version"]["DELETE"] and loose["audit_log"]["UPDATE"] and loose["audit_log"]["DELETE"]   # 대조군: 기본 권한이 되살아남
        r = psql("ytweb_owner", OLD_GUARD)
        assert r.returncode == 0, r.stderr
        after_old = priv_matrix()
        assert after_old["audit_log"]["UPDATE"] is False and after_old["alembic_version"]["UPDATE"] is True and after_old["alembic_version"]["DELETE"] is True   # 수정 전 FAIL 재현
        assert "permission denied" not in psql("ytweb_app", "update alembic_version set version_num = version_num").stderr
        r = db_exec("ytweb-db", "restore", name)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "복원 완료" in r.stdout
        fixed = priv_matrix()
        assert fixed == base, {k: (base.get(k), fixed.get(k)) for k in set(base) | set(fixed) if base.get(k) != fixed.get(k)}     # 복원 전과 권한이 표·권한 전수 일치
        for stmt in ("update alembic_version set version_num = version_num", "delete from alembic_version", "truncate alembic_version",
                     "insert into alembic_version values ('x')", "update audit_log set actor = 'x'", "delete from audit_log", "truncate audit_log"):
            r = psql("ytweb_app", stmt)
            assert r.returncode != 0 and "permission denied" in r.stderr, stmt
    finally:
        db_exec("ytweb-db", "remove", name)


@live
def test_tc_vfi_081_after_restore_app_still_works_end_to_end_and_audit_chain_ok():
    """회수가 과해서 앱이 깨지는 회귀 점검: 복원 직후 로그인·읽기·쓰기(작업 큐/감사 추가)가 되고 체인이 유효하다."""
    c, csrf = api_login()
    c.close()
    name = "vfi081.dump"
    _dump(name)
    try:
        r = db_exec("ytweb-db", "restore", name)
        assert r.returncode == 0, r.stderr
        sh(["docker", "restart", f"{PROJECT}-api-1", f"{PROJECT}-worker-1"], timeout=120)
        t0 = time.time()
        while time.time() - t0 < 90:
            st, _, body = http("/api/readyz")
            if st == 200:
                break
            time.sleep(1)
        else:
            pytest.fail("복원 뒤 api 가 준비되지 않음")
        c, csrf = api_login()
        try:
            before = c.get("/api/v1/audit").json()
            r = c.post("/api/v1/videos/sync", headers={"X-CSRF-Token": csrf, "Idempotency-Key": "vfi081-" + str(time.time())}, json={})
            assert r.status_code in (200, 202), (r.status_code, r.text[:300])
            time.sleep(1)
            after = c.get("/api/v1/audit").json()
            assert after["chain_ok"] is True and before["chain_ok"] is True
            assert len(after["items"]) >= 1
            assert c.get("/api/v1/videos").status_code == 200
        finally:
            c.close()
        # 앱 계정이 읽기·쓰기해야 하는 표들(감사 외)이 여전히 쓰기 가능
        m = priv_matrix()
        for t, row in m.items():
            if t in ("alembic_version", "audit_log") or "SEQ_USAGE" in row:
                continue
            assert row["SELECT"] and row["INSERT"] and row["UPDATE"] and row["DELETE"], t
        assert m["audit_log"]["SELECT"] and m["audit_log"]["INSERT"]
        assert m["alembic_version"]["SELECT"]
        for t, row in m.items():
            if "SEQ_USAGE" in row:
                assert row["SEQ_USAGE"], t
    finally:
        db_exec("ytweb-db", "remove", name)


@live
def test_tc_vfi_082_restore_twice_and_guard_alone_are_idempotent():
    name = "vfi082.dump"
    base = priv_matrix()
    _dump(name)
    try:
        for _ in range(2):
            r = db_exec("ytweb-db", "restore", name)
            assert r.returncode == 0, r.stderr
            assert priv_matrix() == base
        for _ in range(2):
            r = psql("ytweb_owner", read(GUARD))
            assert r.returncode == 0 and priv_matrix() == base
    finally:
        db_exec("ytweb-db", "remove", name)


def _txn(setup: str, probe: str = "") -> subprocess.CompletedProcess:
    """실제 ytweb DB 안에서 한 트랜잭션으로 상황을 꾸미고 가드를 실행한 뒤 항상 ROLLBACK 한다(pg_hba 가 다른 DB 접속을 막으므로 격리 DB 대신 쓴다).
    psql 이 오류로 중단되면 연결이 끊겨 암묵적으로 롤백된다."""
    return psql("ytweb_owner", f"BEGIN;\n{setup};\n{read(GUARD)}\n{probe}\nROLLBACK;\n")


RENAME_BOTH = "alter table alembic_version rename to vfi_av_x; alter table audit_log rename to vfi_al_x"
APP_AV = ("select has_table_privilege('ytweb_app','alembic_version','SELECT'), has_table_privilege('ytweb_app','alembic_version','INSERT'), "
          "has_table_privilege('ytweb_app','alembic_version','TRIGGER'), has_table_privilege('ytweb_app','alembic_version','REFERENCES')")


@live
def test_tc_vfi_083_guard_boundaries_inside_rolled_back_transactions():
    base = priv_matrix()
    # (1) 두 표가 모두 없는 덤프(아주 오래된 백업): 오류 없이 통과
    r = _txn(RENAME_BOTH)
    assert r.returncode == 0, r.stderr
    # (2) alembic_version 이 없고 audit_log 만 있음
    r = _txn("alter table alembic_version rename to vfi_av_x; grant update, delete, truncate on audit_log to ytweb_app",
             "select has_table_privilege('ytweb_app','audit_log','UPDATE'), has_table_privilege('ytweb_app','audit_log','INSERT')")
    assert r.returncode == 0 and r.stdout.strip().splitlines()[-1] == "f|t", (r.stdout, r.stderr)
    # (3) audit_log 가 없고 alembic_version 만 있음 + 앱 계정에 전권이 있던 상태
    r = _txn("alter table audit_log rename to vfi_al_x; grant all on alembic_version to ytweb_app", APP_AV)
    assert r.returncode == 0 and r.stdout.strip().splitlines()[-1] == "t|f|f|f", (r.stdout, r.stderr)
    # (4) 앱 계정의 SELECT 가 없는 상태: 가드는 SELECT 를 되돌려 주지 않고 오류로 알린다(읽기 없는 앱은 뜨지 못한다)
    r = _txn("revoke all on alembic_version from ytweb_app")
    assert r.returncode != 0 and "읽기 권한이 사라졌습니다" in r.stderr, r.stderr
    assert priv_matrix() == base                                      # 전부 롤백됨


@live
def test_tc_vfi_084_guard_fails_closed_when_revoke_cannot_remove_inherited_or_public_privilege():
    """REVOKE ... FROM ytweb_app 은 PUBLIC 이나 다른 역할을 통해 상속된 권한을 지우지 못한다. 그때는 조용히 넘어가지 말고 실패해야 한다(복원 명령 전체 실패)."""
    base = priv_matrix()
    r = _txn("grant update on alembic_version to public")
    assert r.returncode != 0 and "alembic_version 권한 회수에 실패했습니다" in r.stderr, r.stderr
    r = _txn("grant delete on audit_log to public")
    assert r.returncode != 0 and "audit_log 권한 회수에 실패했습니다" in r.stderr, r.stderr
    r = _txn("grant truncate on alembic_version to public")
    assert r.returncode != 0 and "alembic_version 권한 회수에 실패했습니다" in r.stderr, r.stderr
    assert priv_matrix() == base


@live
def test_tc_vfi_085_restore_of_corrupt_or_missing_dump_changes_nothing():
    base = priv_matrix()
    counts_before = db_exec("ytweb-db", "counts").stdout
    name = "vfi085.dump"
    db_exec("bash", "-c", f"head -c 300 /dev/urandom > /backups/{name}")
    try:
        r = db_exec("ytweb-db", "restore", name)
        assert r.returncode != 0 and "복원 완료" not in r.stdout
        r = db_exec("ytweb-db", "restore", "does-not-exist.dump")
        assert r.returncode != 0
        r = db_exec("ytweb-db", "restore", "../etc/passwd")
        assert r.returncode != 0
        assert priv_matrix() == base and db_exec("ytweb-db", "counts").stdout == counts_before
    finally:
        db_exec("ytweb-db", "remove", name)


@live
def test_tc_vfi_086_restore_of_dump_with_app_grants_baked_in_is_still_revoked():
    """덤프 안에 GRANT 가 들어 있어도(예전 백업·조작된 백업) 복원 직후 가드가 마지막에 회수한다."""
    name = "vfi086.dump"
    base = priv_matrix()
    _dump(name)
    try:
        # 현재 DB 에 일부러 권한을 더 줘서 그 상태로 덤프를 뜬다
        r = psql("ytweb_owner", "grant all on alembic_version to ytweb_app; grant update, delete, truncate on audit_log to ytweb_app")
        assert r.returncode == 0, r.stderr
        db_exec("ytweb-db", "remove", name)
        _dump(name)
        r = db_exec("ytweb-db", "restore", name)
        assert r.returncode == 0, r.stdout + r.stderr
        assert priv_matrix() == base
    finally:
        psql("ytweb_owner", "revoke insert,update,delete,truncate,references,trigger on alembic_version from ytweb_app; revoke update,delete,truncate on audit_log from ytweb_app")
        db_exec("ytweb-db", "remove", name)


# ------------------------------- 하드닝·네트워크·기동 순서(새 회귀 탐색) -------------------------------

def inspect(name: str) -> dict:
    r = sh(["docker", "inspect", name])
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)[0]


EXPECT_USER = {"db": "999:999", "migrate": "10001:10001", "api": "10001:10001", "worker": "10001:10001", "web": "101:101"}
EXPECT_NETS = {"db": {"back"}, "migrate": {"back"}, "api": {"front", "back"}, "worker": {"back"}, "web": {"front", "edge"}}


@live
@pytest.mark.parametrize("svc", ["db", "migrate", "api", "worker", "web"])
def test_tc_vfi_090_container_hardening_survives_the_fix(svc):
    i = inspect(f"{PROJECT}-{svc}-1")
    hc = i["HostConfig"]
    assert i["Config"]["User"] == EXPECT_USER[svc]
    assert hc["ReadonlyRootfs"] is True
    assert hc["CapDrop"] == ["ALL"] and not hc["CapAdd"]
    assert "no-new-privileges:true" in hc["SecurityOpt"] and hc["Init"] is True
    assert hc["Privileged"] is False and hc["PidMode"] == "" and hc["NetworkMode"] != "host"
    assert hc["Memory"] > 0 and hc["PidsLimit"] and hc["PidsLimit"] > 0
    nets = {n.removeprefix(f"{PROJECT}_") for n in i["NetworkSettings"]["Networks"]}
    assert nets == EXPECT_NETS[svc], (svc, nets)
    assert not [m for m in i["Mounts"] if m["Type"] == "bind" and "docker.sock" in m["Source"]]
    if svc != "migrate":
        uid = sh(["docker", "exec", f"{PROJECT}-{svc}-1", "id", "-u"]).stdout.strip()
        assert uid == EXPECT_USER[svc].split(":")[0] and uid != "0"


@live
def test_tc_vfi_091_only_one_published_port_on_loopback():
    out = sh(["docker", "ps", "--filter", f"label=com.docker.compose.project={PROJECT}", "--format", "{{.Names}}|{{.Ports}}"]).stdout.strip().splitlines()
    pub = [l for l in out if "->" in l]
    assert len(pub) == 1 and pub[0].startswith(f"{PROJECT}-web-1|") and f"127.0.0.1:{PORT}->8080/tcp" in pub[0] and "0.0.0.0" not in pub[0] and "[::]" not in pub[0], out
    for svc in ("db", "api", "worker", "migrate"):
        assert not inspect(f"{PROJECT}-{svc}-1")["HostConfig"]["PortBindings"], svc


@live
def test_tc_vfi_092_network_flags_and_web_cannot_reach_db_but_api_can():
    nets = {n: json.loads(sh(["docker", "network", "inspect", f"{PROJECT}_{n}"]).stdout)[0] for n in ("front", "back", "edge")}
    assert nets["front"]["Internal"] is True and nets["back"]["Internal"] is True and nets["edge"]["Internal"] is False
    members = {n: {v["Name"].removeprefix(f"{PROJECT}-").removesuffix("-1") for v in d["Containers"].values()} for n, d in nets.items()}
    assert "db" not in members["front"] and "db" in members["back"] and members["edge"] == {"web"}
    db_ip = next(v["IPv4Address"].split("/")[0] for v in nets["back"]["Containers"].values() if v["Name"].endswith("-db-1"))
    w = sh(["docker", "exec", f"{PROJECT}-web-1", "sh", "-c", f"nc -w 3 -z {db_ip} 5432; echo rc=$?; nc -w 3 -z db 5432; echo rc2=$?; getent hosts db || echo nohost"])
    assert "rc=0" not in w.stdout and "rc2=0" not in w.stdout and "nohost" in w.stdout, w.stdout
    a = sh(["docker", "exec", f"{PROJECT}-api-1", "python", "-c", "import socket;s=socket.create_connection(('db',5432),3);print('connected')"])
    assert "connected" in a.stdout, a.stderr[-300:]
    egress = sh(["docker", "exec", f"{PROJECT}-api-1", "python", "-c", "import socket;socket.create_connection(('1.1.1.1',443),3)"])
    assert egress.returncode != 0                                      # internal 망: 인터넷 경로 없음


@live
def test_tc_vfi_093_db_hba_and_roles_unchanged_by_guard():
    r = psql("postgres", "select rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin from pg_roles where rolname like 'ytweb%' order by 1")
    rows = {l.split("|")[0]: l.split("|")[1:] for l in r.stdout.strip().splitlines()}
    assert rows["ytweb_app"] == ["f", "f", "f", "t"] and rows["ytweb_owner"][0] == "f"
    r = psql("postgres", "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public' and c.relkind='r' and pg_get_userbyid(c.relowner)<>'ytweb_owner'")
    assert r.stdout.strip() == "0"                                     # 복원(--no-owner)이 표 소유자를 바꾸지 않았다
    assert psql("ytweb_app", "create table vfi_x(i int)").returncode != 0      # 앱 계정은 DDL 불가
    assert psql("ytweb_app", "select 1 from alembic_version limit 1").returncode == 0


@live
def test_tc_vfi_094_cold_start_order_after_down_up():
    """down(볼륨 유지) → up: db healthy → migrate 시작 → migrate 종료 0 → api 시작 → api healthy → web 시작 → web healthy (docker events 로 실측)."""
    assert STACK is not None, "VFI_STACK_DIR 필요(compose.yaml 사본)"
    base = ["docker", "compose", "-p", PROJECT, "-f", str(STACK / "compose.yaml")]
    env = {**os.environ, "YTWEB_IMAGE_PREFIX": PROJECT}
    since = int(time.time())
    assert sh(base + ["down", "-t", "20"], env=env, timeout=240).returncode == 0
    r = sh(base + ["up", "-d", "--no-build"], env=env, timeout=300)
    assert r.returncode == 0, r.stderr[-500:]
    t0 = time.time()
    while time.time() - t0 < 120:
        st = {l.split()[0]: l for l in sh(base + ["ps", "-a", "--format", "{{.Service}} {{.Status}}"], env=env).stdout.strip().splitlines()}
        if all("(healthy)" in st.get(s, "") for s in ("db", "api", "worker", "web")):
            break
        time.sleep(2)
    ev = sh(["docker", "events", "--since", str(since), "--until", str(int(time.time()) + 1), "--filter", f"label=com.docker.compose.project={PROJECT}",
             "--format", '{{.TimeNano}}|{{.Action}}|{{index .Actor.Attributes "com.docker.compose.service"}}|{{index .Actor.Attributes "exitCode"}}'], timeout=60).stdout
    rows = [l.split("|") for l in ev.strip().splitlines() if l.count("|") == 3]

    def first(a: str, s: str, code: str | None = None) -> int:
        c = [int(t) for t, aa, ss, x in rows if aa == a and ss == s and (code is None or x == code)]
        assert c, (a, s)
        return min(c)
    db_ok, ms, me = first("health_status: healthy", "db"), first("start", "migrate"), first("die", "migrate", "0")
    a_s, w_s = first("start", "api"), first("start", "worker")
    a_ok, w_ok = first("health_status: healthy", "api"), first("health_status: healthy", "worker")
    web_s, web_ok = first("start", "web"), first("health_status: healthy", "web")
    assert db_ok < ms < me < min(a_s, w_s) and a_s < a_ok < web_s < web_ok and w_s < w_ok
    st, _, _ = http("/api/readyz")
    assert st == 200


@live
def test_tc_vfi_095_published_port_serves_only_allowed_hosts():
    for host in ("evil.example", "127.0.0.1:9999", "localhost", "127.0.0.1"):
        st, _, _ = http("/api/healthz", host=host)
        assert st == 0, host
    for host in ("127.0.0.1:8080", "localhost:8080"):
        st, _, _ = http("/api/healthz", host=host)
        assert st == 200, host


# ------------------------------- 이미지 내용물 -------------------------------

@live
def test_tc_vfi_100_api_image_contains_only_git_tracked_runtime_files():
    """DEF-9-017: 이미지 /app 의 모든 파일이 저장소 추적 파일(또는 컴파일된 .pyc)에 대응한다. 작업 폴더의 미추적 파일(캐시·비밀형)이 이미지에 들어가면 실패."""
    img = f"{PROJECT}-api:local"
    r = sh(["docker", "run", "--rm", "--entrypoint", "find", img, "/app", "-type", "f"])
    assert r.returncode == 0, r.stderr
    files = [f for f in r.stdout.splitlines() if f.strip()]
    assert len(files) > 100
    tracked = set(_git("ls-files").stdout.splitlines())
    mapping = (("/app/src/youtube_title/", "src/youtube_title/"), ("/app/config/", "config/"), ("/app/backend/ytweb/", "web/backend/ytweb/"),
               ("/app/backend/alembic/", "web/backend/alembic/"), ("/app/backend/alembic.ini", "web/backend/alembic.ini"))
    extra = []
    for f in files:
        if f.endswith(".pyc") and "__pycache__" in f:
            continue
        for a, b in mapping:
            if f.startswith(a):
                if (b + f[len(a):] if a.endswith("/") else b) in tracked:
                    break
        else:
            extra.append(f)
    assert extra == [], extra
    assert not [f for f in files if not f.endswith(".example") and re.search(r"(\.pem|\.key|\.p12|credentials|client_secret|token|\.env|settings\.local|\.sqlite3|\.coverage|_cache|\.dump)", f)]
    # 필요한 것은 모두 들어 있다
    for must in ("/app/backend/alembic.ini", "/app/backend/alembic/versions/0001_initial.py", "/app/backend/alembic/versions/0002_revoke_alembic_version_dml.py",
                 "/app/backend/ytweb/app.py", "/app/src/youtube_title/config.py"):
        assert must in files, must


@live
def test_tc_vfi_101_api_and_web_images_run_as_nonroot_and_import_cleanly():
    img = f"{PROJECT}-api:local"
    r = sh(["docker", "run", "--rm", "--entrypoint", "python", img, "-c", "import os,ytweb.app,ytweb.migrate,ytweb.worker;print(os.getuid())"])
    assert r.stdout.strip() == "10001", r.stderr
    r = sh(["docker", "run", "--rm", "--entrypoint", "sh", f"{PROJECT}-web:local", "-c",
            "find /usr/share/nginx/html -name '*.map' -o -name '*.test.*' | head; ls /etc/nginx/snippets"])
    out = r.stdout.split()
    assert sorted(out) == ["proxy.conf", "security-headers-api.conf", "security-headers.conf"], out


# ======================================================================================
# D. pwsh 경유(운영 스크립트): backup.ps1 → restore.ps1 → 권한 전수 비교
# ======================================================================================

def ps(script: str, *args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    env = {**os.environ, "YTWEB_PROJECT": PROJECT, "YTWEB_IMAGE_PREFIX": PROJECT, "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1"}
    return subprocess.run([PWSH, "-NoProfile", "-File", str(STACK / "scripts" / script), *args], env=env, capture_output=True, text=True, timeout=timeout)


@needs_pwsh
def test_tc_vfi_110_restore_ps1_end_to_end_keeps_privilege_matrix_identical():
    base = priv_matrix()
    for f in (STACK / "backups").glob("*.dump*"):
        f.unlink()
    p = ps("backup.ps1")
    assert p.returncode == 0, p.stdout[-800:]
    dumps = [f for f in (STACK / "backups").glob("ytweb-*.dump")]
    assert dumps
    # 복원 전에 일부러 권한을 풀어 둔다(복원 후에는 다시 닫혀 있어야 한다)
    assert psql("postgres", "grant update, delete on alembic_version to ytweb_app; grant update on audit_log to ytweb_app").returncode == 0
    p = ps("restore.ps1", "-File", dumps[0].name, "-ConfirmText", "복원합니다", "-SkipSafetyBackup")
    assert p.returncode == 0, p.stdout[-800:] + p.stderr[-400:]
    assert "복원이 끝났습니다" in p.stdout
    assert priv_matrix() == base
    st, _, body = http("/api/readyz")
    assert st == 200 and json.loads(body)["db"] == "ok"
    for f in (STACK / "backups").glob("*.dump*"):
        f.unlink()


@needs_pwsh
def test_tc_vfi_111_restore_ps1_wrong_confirmation_and_bad_name_change_nothing():
    base = priv_matrix()
    p = ps("restore.ps1", "-File", "nope.dump", "-ConfirmText", "복원합니다", "-SkipSafetyBackup")
    assert p.returncode != 0
    p = ps("restore.ps1", "-File", "../../etc/passwd", "-ConfirmText", "복원합니다", "-SkipSafetyBackup")
    assert p.returncode != 0
    assert priv_matrix() == base
