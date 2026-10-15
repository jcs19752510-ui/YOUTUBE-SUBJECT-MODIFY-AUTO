"""SEC-03 저장소·설정 정적 점검: 비밀 유출, 무시 파일, 컨테이너/compose 하드닝, 이미지 고정, 의존성 잠금, 프런트 금지 패턴, nginx/DB 설정, 스크립트.

git 명령은 쓰지 않는다(현재 파일 트리만 본다). 출력에는 비밀 값 자체를 싣지 않고 파일:줄과 규칙 이름만 쓴다.
TW-13·18·21·23·31·32, S-W08·W11·W14, D-02~D-07a·D-11 관련.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(os.environ.get("YTWEB_SEC_ROOT", Path(__file__).resolve().parents[2]))  # 변이 점검이 사본을 가리킬 때만 YTWEB_SEC_ROOT 를 쓴다
SKIP_DIRS = {".git", "node_modules", ".harness-tmp", "__pycache__", ".pytest_cache", "dist", ".venv", "venv", ".mypy_cache", ".ruff_cache"}
TEXT_EXT = {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".yaml", ".yml", ".md", ".MD", ".txt", ".ps1", ".sh", ".sql", ".conf", ".toml", ".ini", ".html", ".css", ".in", "", ".example", ".sample", ".cfg", ".env"}


def walk():
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for f in fn:
            p = Path(dp) / f
            yield p


def text_files():
    for p in walk():
        if p.suffix in TEXT_EXT and p.stat().st_size < 3_000_000:
            try:
                yield p, p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue


# ───────────── 비밀 유출(현재 파일 트리) ─────────────

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "google_oauth_secret": re.compile(r"\bGOCSPX-[0-9A-Za-z_\-]{20,}\b"),
    "google_oauth_client_id": re.compile(r"\b\d{6,}-[0-9a-z]{20,}\.apps\.googleusercontent\.com\b"),
    "github_token": re.compile(r"\b(ghp|gho|ghu|ghs|ghr|github_pat)_[0-9A-Za-z_]{20,}\b"),
    "openai_like_key": re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[0-9A-Za-z\-]{10,}\b"),
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
    "url_with_password": re.compile(r"\b[a-z][a-z0-9+.\-]*://[^/\s:@\"']+:(?!\*\*\*|<|\$|%|\{|x{3,}|password|pw\b|secret|changeme)[^/\s@\"']{6,}@[^/\s\"']+", re.I),
    "oauth_refresh_token_json": re.compile(r"\"refresh_token\"\s*:\s*\"[^\"]{10,}\""),
    "client_secret_json": re.compile(r"\"client_secret\"\s*:\s*\"[^\"]{10,}\""),
    "hex_secret_64_assigned": re.compile(r"(?i)(secret|password|passwd|api[_-]?key|token)\w*\s*[:=]\s*[\"']?[0-9a-f]{64}[\"']?\b"),
}
# 시험 코드의 의도적 가짜 값(마스킹 시험용)과 문서 예시는 허용: 파일 단위로 허용 목록을 둔다.
ALLOW = {
    "web/tests_infra/test_vinf2_live.py",
    "web/tests_security/test_sec_02_injection_ai_integrity.py",  # 마스킹 시험용 가짜 값
    "web/tests_security/test_sec_03_static_repo.py",
    "web/backend/tests/core/test_logging.py",
    "web/backend/tests/verify_wa/test_va_05_errors_logs.py",
    "tests/test_auth.py",                 # CLI 시험의 명백한 가짜 값("GOCSPX-fake" 등)
    "tests/test_logging.py",
    "tests/integration/it_fab_support.py",
}


def test_no_secrets_in_current_tree():
    hits = []
    for p, txt in text_files():
        rel = p.relative_to(ROOT).as_posix()
        if rel in ALLOW or rel.startswith("web/backend/tests/verify_m23/"):  # verify_m23: 가짜 구글 토큰 JSON(명백한 가짜 값)만 쓰는 독립 시험 폴더
            continue
        for name, rx in SECRET_PATTERNS.items():
            for m in rx.finditer(txt):
                line = txt.count("\n", 0, m.start()) + 1
                hits.append((rel, line, name))
    assert not hits, hits[:30]


def test_no_secret_like_files_in_tree():
    bad_names = re.compile(r"^(\.env(\..*)?|token.*\.json|client_secret.*\.json|.*\.pem|.*\.key|id_rsa.*|.*\.p12|.*\.pfx|.*\.dump|credentials.*|.*\.sqlite3?|.*\.db)$", re.I)
    allowed = {"settings.local.yaml.example", ".env.example"}  # 템플릿(값 없음, 비밀 아님)
    hits = [p.relative_to(ROOT).as_posix() for p in walk() if bad_names.match(p.name) and p.name not in allowed]
    assert not hits, hits
    for d in ("data", "web/secrets", "web/backups", "secrets", "approvals"):
        assert not (ROOT / d).exists(), f"{d}/ 가 작업 트리에 있다(.gitignore 대상이어도 이미지·백업 유출 위험)"
    assert not (ROOT / "config" / "settings.local.yaml").exists()


def _ignore_lines(name: str) -> set[str]:
    return {l.strip() for l in (ROOT / name).read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")}


def test_gitignore_covers_secret_and_artifact_paths():
    g = _ignore_lines(".gitignore")
    for need in (".env", "secrets/", "token*.json", "*.token", "data/", "config/settings.local.yaml", "approvals/", ".harness-tmp/", "web/secrets/", "web/backups/", "*.dump", "node_modules/", "web/frontend/dist/", "docs/harness/_ci-logs/"):
        assert need in g, f".gitignore 에 {need} 가 없다"


def test_gitignore_has_client_secret_pattern():
    assert any("client_secret" in x for x in _ignore_lines(".gitignore"))


def test_dockerignore_excludes_secrets_tests_docs_and_vcs():
    d = _ignore_lines(".dockerignore")
    for need in (".git", ".env", "secrets/", "web/secrets/", "web/backups/", "data/", "token*.json", "client_secret*.json", ".harness-tmp/", "**/node_modules/", "docs/", "tests/", "**/tests/", ".claude/", "approvals/", "config/settings.local.yaml"):
        assert need in d, f".dockerignore 에 {need} 가 없다"


# ───────────── Dockerfile ─────────────

def dockerfiles():
    return sorted((ROOT / "web" / "docker").glob("*.Dockerfile"))


def test_dockerfiles_pin_base_images_by_digest_and_never_latest():
    for f in dockerfiles():
        txt = f.read_text(encoding="utf-8")
        for m in re.finditer(r"^ARG\s+(\w+_IMAGE)=(\S+)", txt, re.M):
            assert re.search(r"@sha256:[0-9a-f]{64}$", m.group(2)), (f.name, m.group(2))
            assert ":latest" not in m.group(2)
        for m in re.finditer(r"^FROM\s+(\S+)", txt, re.M):
            ref = m.group(1)
            assert ref.startswith("${") or "@sha256:" in ref or ref in ("build", "builder", "runtime"), (f.name, ref)


def test_dockerfiles_final_stage_runs_as_nonroot_and_no_remote_scripts():
    for f in dockerfiles():
        txt = f.read_text(encoding="utf-8")
        users = re.findall(r"^USER\s+(\S+)", txt, re.M)
        assert users and users[-1] not in ("root", "0", "0:0"), (f.name, users)
        assert not re.search(r"(curl|wget)[^\n|]*\|\s*(ba)?sh", txt), f.name
        assert not re.search(r"^ADD\s+https?://", txt, re.M), f.name
        assert "--privileged" not in txt and "chmod 777" not in txt and "chmod -R 777" not in txt


def test_python_image_installs_only_hash_locked_binary_wheels():
    txt = (ROOT / "web" / "docker" / "api.Dockerfile").read_text(encoding="utf-8")
    assert txt.count("--require-hashes") >= 2 and "--only-binary=:all:" in txt and "--no-deps" in txt
    assert "pip install -r" not in txt and "--index-url" not in txt and "--extra-index-url" not in txt


def test_node_image_installs_with_ci_and_no_scripts_and_removes_sourcemaps():
    txt = (ROOT / "web" / "docker" / "web.Dockerfile").read_text(encoding="utf-8")
    assert "npm ci --ignore-scripts" in txt and "*.map" in txt and "npm install" not in txt
    assert re.search(r"COPY --from=build .*dist /usr/share/nginx/html", txt), "최종 이미지에는 빌드 산출물만 복사해야 한다"


# ───────────── compose 하드닝 ─────────────

def load_compose():
    return yaml.safe_load((ROOT / "web" / "compose.yaml").read_text(encoding="utf-8"))


def test_compose_every_service_is_hardened():
    c = load_compose()
    svcs = c["services"]
    assert set(svcs) == {"db", "migrate", "api", "worker", "web"}
    for name, s in svcs.items():
        assert s.get("read_only") is True, name
        assert s.get("cap_drop") == ["ALL"] and "cap_add" not in s, name
        assert "no-new-privileges:true" in s.get("security_opt", []), name
        assert s.get("init") is True, name
        assert s.get("privileged") in (None, False) and "network_mode" not in s and "pid" not in s and "ipc" not in s and "devices" not in s, name
        user = str(s.get("user", ""))
        assert user and not user.startswith(("0", "root")), (name, user)
        for v in s.get("volumes", []) or []:
            v = v if isinstance(v, str) else json.dumps(v)
            assert "docker.sock" not in v and not v.startswith(("/", "./", "~")), (name, v)
        lim = s.get("deploy", {}).get("resources", {}).get("limits", {})
        assert {"cpus", "memory", "pids"} <= set(lim), name
        assert s["logging"]["options"]["max-size"] and s["logging"]["options"]["max-file"], name


def test_compose_only_web_publishes_a_loopback_port():
    c = load_compose()
    published = {n: s.get("ports") for n, s in c["services"].items() if s.get("ports")}
    assert published == {"web": ["127.0.0.1:8080:8080"]}, published


def test_compose_networks_are_internal_except_edge_and_only_web_joins_edge():
    c = load_compose()
    nets = c["networks"]
    assert nets["front"]["internal"] is True and nets["back"]["internal"] is True and not nets["edge"].get("internal")
    members = {n: set((s.get("networks") or {}).keys()) for n, s in c["services"].items()}
    assert members["web"] == {"front", "edge"}
    assert members["db"] == {"back"} and members["worker"] == {"back"} and members["migrate"] == {"back"} and members["api"] == {"front", "back"}
    assert [n for n, m in members.items() if "edge" in m] == ["web"]
    online = yaml.safe_load((ROOT / "web" / "compose.online.yaml").read_text(encoding="utf-8"))
    assert set(online["services"]) == {"api", "worker"}, "egress 는 api/worker 에만(db·web 금지)"


def test_compose_secrets_are_files_and_env_has_no_plain_credentials():
    c = load_compose()
    assert all(list(v) == ["file"] for v in c["secrets"].values())
    blob_re = re.compile(r"(?i)(pass(word)?|secret|token|key)")
    for n, s in c["services"].items():
        env = s.get("environment") or {}
        env = env if isinstance(env, dict) else dict(e.split("=", 1) for e in env)
        for k, v in env.items():
            if n == "api" and k == "YTWEB_ADMIN_PASSWORD":  # DEC-057 예외: 값은 web/.env 에서만 오고 저장소엔 자리표시자뿐
                assert str(v) == "${YTWEB_ADMIN_PASSWORD:-}", v
                continue
            if blob_re.search(k) and not k.endswith("_DIR"):
                assert k.endswith("_FILE"), (n, k)
                assert str(v).startswith("/run/secrets/"), (n, k, v)
    api = c["services"]["api"]
    assert api["environment"]["YTWEB_ENABLE_DOCS"] == "0"
    # DEC-057: 관리자 아이디·비밀번호는 api 환경 변수(web/.env 값)로만, 비밀 파일 없음. worker/migrate/db/web 에는 전달하지 않는다
    for other in ("worker", "migrate", "db", "web"):
        oenv = c["services"][other].get("environment") or {}
        assert not [k for k in oenv if k.startswith("YTWEB_ADMIN_")], other
    assert c["services"]["api"]["environment"]["YTWEB_ADMIN_ID"] == "${YTWEB_ADMIN_ID:-}"
    assert c["services"]["api"]["secrets"] == ["db_app_password"] and c["services"]["worker"]["secrets"] == ["db_app_password"]
    assert c["services"]["migrate"]["secrets"] == ["db_owner_password"]
    assert "secrets" not in c["services"]["web"]
    cmd = " ".join(c["services"]["db"]["command"])
    assert "password_encryption=scram-sha-256" in cmd and "log_statement=none" in cmd and "hba_file=/etc/postgresql/pg_hba.conf" in cmd


def test_compose_no_dev_profile_leak_and_no_env_file_use():
    txt = (ROOT / "web" / "compose.yaml").read_text(encoding="utf-8")
    assert "env_file" not in txt and "0.0.0.0:" not in txt.replace("--host\n      - 0.0.0.0", "")
    assert "YTWEB_MODE: demo" in txt


# ───────────── nginx / DB 설정 ─────────────

def test_nginx_conf_rules():
    n = (ROOT / "web" / "docker" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert "server_tokens off" in n and "client_max_body_size 1m" in n and "return 444" in n and "autoindex" not in n
    assert len(re.findall(r"limit_req\s+zone=", n)) >= 3 and "limit_except" in n
    # add_header 상속 규칙: location 안에 add_header 가 하나라도 있으면 server 수준 헤더가 사라지므로 그런 location 은 보안 헤더 파일을 직접 include 해야 한다.
    srv = n[n.index("server {"):]
    assert "include /etc/nginx/snippets/security-headers.conf;" in srv.split("location ")[0], "server 수준 include 필요"
    blocks = re.split(r"\n\s+location ", srv)[1:]
    assert len(blocks) >= 6
    for b in blocks:
        if "add_header" in b:
            # 2026-10-11 W-FIX-INF: /api 계열 location 은 JSON 용 헤더 파일(security-headers-api.conf, CSP default-src 'none')을 include 한다
            assert re.search(r"security-headers(-api)?\.conf", b), "add_header 가 있는 location 이 보안 헤더를 include 하지 않는다: " + b.splitlines()[0]
    proxies = re.findall(r"proxy_pass\s+([^;]+);", n)
    assert proxies and all(p.startswith("$api_upstream") for p in proxies), proxies
    assert re.findall(r"set \$api_upstream (\S+);", n) == ["http://api:8000"] * 4
    assert "$arg_" not in n and "$http_x_" not in n and "$http_referer" not in n and "$cookie" not in n
    h = (ROOT / "web" / "docker" / "nginx" / "security-headers.conf").read_text(encoding="utf-8")
    exact = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin", "Cross-Origin-Opener-Policy": "same-origin", "Cross-Origin-Resource-Policy": "same-origin"}
    for k, v in exact.items():
        assert re.search(rf'add_header {k} "{v}" always;', h), k
    assert re.search(r'add_header Permissions-Policy "[^"]*camera=\(\)[^"]*microphone=\(\)[^"]*geolocation=\(\)[^"]*" always;', h)
    assert re.search(r'add_header Content-Security-Policy "[^"]+" always;', h)
    csp = re.search(r"Content-Security-Policy \"([^\"]+)\"", h).group(1)
    directives = {d.split()[0]: d.split()[1:] for d in (x.strip() for x in csp.split(";")) if d}
    assert directives["default-src"] == ["'self'"] and directives["script-src"] == ["'self'"] and directives["frame-ancestors"] == ["'none'"] and directives["object-src"] == ["'none'"]
    assert directives["base-uri"] == ["'none'"] and directives["form-action"] == ["'self'"] and directives["connect-src"] == ["'self'"] and directives["style-src"] == ["'self'"]
    assert "unsafe-eval" not in csp and "'unsafe-inline'" not in " ".join(directives["script-src"] + directives["default-src"] + directives["style-src"])
    assert "https:" not in csp and "*" not in csp.replace("'self'", "")


def test_db_configs_have_no_trust_and_no_literal_passwords():
    hba = (ROOT / "web" / "docker" / "db" / "pg_hba.conf").read_text(encoding="utf-8")
    rules = [l.split() for l in hba.splitlines() if l.strip() and not l.startswith("#")]
    assert all(r[-1] in ("scram-sha-256", "reject") for r in rules), rules
    assert rules[-1][-1] == "reject" and rules[-1][3] == "all"
    sql = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "web" / "docker" / "db").glob("*.sql"))
    sh = (ROOT / "web" / "docker" / "db" / "init" / "01-roles.sh").read_text(encoding="utf-8")
    assert not re.search(r"(?i)PASSWORD\s+'[^']+'", sql + sh), "SQL/스크립트에 리터럴 비밀번호"
    for role, pw in (("ytweb_owner", "owner_pw"), ("ytweb_app", "app_pw")):
        assert re.search(rf"CREATE ROLE {role} LOGIN PASSWORD :'{pw}'\s+NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS", sh), role
    assert "REVOKE ALL ON DATABASE ytweb FROM PUBLIC" in sh and "GRANT CONNECT ON DATABASE ytweb TO ytweb_app" in sh
    grants = (ROOT / "web" / "docker" / "db" / "schema-grants.sql").read_text(encoding="utf-8")
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ytweb_app" in grants and "ALL PRIVILEGES" not in grants.upper() and "SUPERUSER" not in grants.upper()


# ───────────── 의존성 잠금 / 공급망 ─────────────

def test_python_lock_files_are_pinned_hashed_registry_only():
    for rel in ("web/backend/requirements.txt", "web/backend/requirements-dev.txt", "web/docker/requirements-youtube-title.txt"):
        raw = (ROOT / rel).read_text(encoding="utf-8")
        txt = "\n".join(re.sub(r"\s+#.*$", "", l) for l in raw.splitlines()).replace("\\\n", " ")  # 주석 처리된 해시는 해시가 아니다
        reqs = [l for l in txt.splitlines() if re.match(r"^[A-Za-z0-9_.\-]+(\[.*\])?==", l)]
        assert len(reqs) >= 3, rel
        for l in reqs:
            assert re.search(r"--hash=sha256:[0-9a-f]{64}", l), (rel, l[:40])
        assert not re.search(r"^\s*(-e\b|git\+|https?://|--index-url|--extra-index-url|--find-links|-f\s)", txt, re.M), rel
        assert "@" not in re.sub(r"--hash=sha256:[0-9a-f]+", "", " ".join(reqs)), rel  # 직접 URL 의존성(name @ url) 금지


def test_core_requirements_are_direct_pins_only_known_gap():
    """[정보] 루트 requirements.txt(CLI 코어)는 해시 잠금이 아니다 - 웹 이미지는 web/docker/requirements-youtube-title.txt(해시)를 쓰므로 웹 경로에는 영향 없음."""
    txt = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert all("==" in l for l in txt.splitlines() if l.strip() and not l.startswith("#"))
    assert "--hash" not in txt


def test_package_json_exact_versions_and_lock_registry_only():
    pkg = json.loads((ROOT / "web" / "frontend" / "package.json").read_text(encoding="utf-8"))
    for sect in ("dependencies", "devDependencies"):
        for n, v in pkg[sect].items():
            assert re.fullmatch(r"\d+\.\d+\.\d+", v), (n, v)
    lock = json.loads((ROOT / "web" / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    assert lock["lockfileVersion"] >= 3
    scripts = []
    for path, meta in lock["packages"].items():
        if not path:
            continue
        assert meta.get("integrity", "").startswith("sha512-"), path
        assert meta.get("resolved", "").startswith("https://registry.npmjs.org/"), (path, meta.get("resolved"))
        if meta.get("hasInstallScript"):
            scripts.append((path, meta.get("dev"), meta.get("optional")))
    assert all(dev and opt for _, dev, opt in scripts), scripts  # 설치 스크립트는 개발 전용 선택 의존성(fsevents)뿐
    assert [p for p, _, _ in scripts] == ["node_modules/fsevents"], scripts


def test_no_unpinned_or_remote_install_commands_in_scripts_and_docs_code():
    bad = re.compile(r"(?i)(pip install(?!.*--require-hashes)[^\n]*\b(git\+|http)|curl[^\n|]*\|\s*(ba)?sh|iex\s*\(|Invoke-Expression|DownloadString|npm i(nstall)? -g(?! @anthropic))")
    hits = []
    for p, txt in text_files():
        rel = p.relative_to(ROOT).as_posix()
        if p.suffix in (".ps1", ".sh", ".yaml", ".yml") or rel.startswith("web/docker"):
            for m in bad.finditer(txt):
                hits.append((rel, txt.count("\n", 0, m.start()) + 1, m.group(0)[:40]))
    assert not hits, hits


# ───────────── 프런트 소스 금지 패턴 ─────────────

FE_SRC = ROOT / "web" / "frontend" / "src"


def fe_files(tests=False):
    for p in FE_SRC.rglob("*"):
        if p.suffix in (".ts", ".tsx") and (tests or ".test." not in p.name) and "src/test" not in p.as_posix():
            yield p


def test_frontend_has_no_dom_injection_or_storage_or_eval():
    bad = re.compile(r"dangerouslySetInnerHTML|\.innerHTML|\.outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(|new Function\s*\(|localStorage|sessionStorage|indexedDB|document\.cookie|window\.open\s*\(|postMessage\s*\(|\.srcdoc|createContextualFragment|javascript:")
    hits = [(p.relative_to(ROOT).as_posix(), bad.search(p.read_text(encoding="utf-8")).group(0)) for p in fe_files() if bad.search(p.read_text(encoding="utf-8"))]
    assert not hits, hits


def test_frontend_has_no_external_urls_or_cdn_and_fetch_only_in_client():
    ext = re.compile(r"https?://(?!127\.0\.0\.1|localhost|www\.w3\.org)[^\s\"'`)]+")
    hits = []
    for p in fe_files():
        t = p.read_text(encoding="utf-8")
        for m in ext.finditer(t):
            hits.append((p.relative_to(ROOT).as_posix(), m.group(0)[:50]))
        if re.search(r"\bfetch\s*\(", t) and p.name != "client.ts":
            hits.append((p.name, "fetch"))
        if re.search(r"\bXMLHttpRequest|\bWebSocket\b|\bEventSource\b|navigator\.sendBeacon", t):
            hits.append((p.name, "other-net"))
    assert not hits, hits
    html = (ROOT / "web" / "frontend" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"(src|href)=[\"']https?://", html) and "<style" not in html and not re.search(r"<script(?![^>]*src=)[^>]*>", html)
    css = "\n".join(p.read_text(encoding="utf-8") for p in (FE_SRC / "styles").glob("*.css"))
    assert not re.search(r"@import\s+(url\()?[\"']?(https?:)?//", css) and not re.search(r"url\(\s*[\"']?(https?:)?//", css), "원격 폰트/이미지 금지(F-04)"


def test_frontend_eslint_forbids_the_dangerous_apis():
    cfg = (ROOT / "web" / "frontend" / "eslint.config.js").read_text(encoding="utf-8")
    for need in ("dangerouslySetInnerHTML", "innerHTML", "localStorage"):
        assert need in cfg, need


def test_vite_build_has_no_sourcemaps_and_test_files_excluded_from_build():
    v = (ROOT / "web" / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert "sourcemap: false" in v
    b = json.loads((ROOT / "web" / "frontend" / "tsconfig.build.json").read_text(encoding="utf-8"))
    assert "src/**/*.test.tsx" in b["exclude"] and "src/test/**" in b["exclude"]


def test_built_dist_if_present_has_no_maps_tests_or_dev_urls():
    dist = ROOT / "web" / "frontend" / "dist"
    if not dist.exists():
        pytest.skip("dist 없음(이미지 안의 산출물은 test_sec_04 가 확인)")
    files = [p for p in dist.rglob("*") if p.is_file()]
    assert not [p for p in files if p.suffix == ".map" or ".test." in p.name]
    js = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in files if p.suffix == ".js")
    for needle in ("sourceMappingURL", "mock-server", "127.0.0.1:8081", "localhost:5173"):
        assert needle not in js, needle


# ───────────── PowerShell 스크립트 ─────────────

def test_powershell_scripts_have_no_dangerous_constructs_and_confirm_destructive_ops():
    d = ROOT / "web" / "scripts"
    allp = {p.name: p.read_text(encoding="utf-8") for p in d.glob("*.ps1")}
    assert len(allp) >= 9
    for name, t in allp.items():
        if name not in ("pin-digests.ps1", "status.ps1", "e2e.ps1"):  # e2e: 127.0.0.1 주소 점검용 Invoke-WebRequest  # pin-digests: Docker Hub 다이제스트 조회, status: 127.0.0.1 상태 확인 - 아래에서 따로 확인
            assert not re.search(r"(?i)\b(iex|Invoke-Expression|Invoke-WebRequest|Invoke-RestMethod|DownloadString|Start-BitsTransfer|Add-Type|\[Reflection\.Assembly\]::Load)\b", t), name
        assert not re.search(r"(?i)\b(iex|Invoke-Expression|DownloadString|Add-Type)\b", t), name
        assert not re.search(r"(?i)Write-(Host|Output|Info|Ok|Warn)[^\n]*\$(secret|pw|password|bytes)\b", t), name
    assert "ValidatePattern('^[A-Za-z0-9-]+$')" in allp["backup.ps1"]
    assert "Assert-BackupFileName" in allp["restore.ps1"] and "복원합니다" in allp["restore.ps1"]
    assert "모든 데이터 삭제" in allp["reset-demo.ps1"] and "데모 초기화" in allp["reset-demo.ps1"]
    assert "down" in allp["stop.ps1"] and "--volumes" not in allp["stop.ps1"] and " -v" not in allp["stop.ps1"]
    st_urls = set(re.findall(r"https?://[^/\s\"']+", allp["status.ps1"])) | set(re.findall(r"Invoke-WebRequest -Uri \((\$\w+)", allp["status.ps1"]))
    assert st_urls == {"$YtwebUrl"}, st_urls  # status.ps1 의 웹 요청은 127.0.0.1:8080($YtwebUrl)뿐
    pin = allp["pin-digests.ps1"]
    assert re.findall(r"https?://[^/\s\"']+", pin) and set(re.findall(r"https?://([^/\s\"'$:]+)", pin)) <= {"auth.docker.io", "registry-1.docker.io"}
    assert "param([switch]$Apply)" in pin  # 기본은 비교만, -Apply 일 때만 Dockerfile 을 고친다
    assert "Set-OwnerOnlyAcl" in allp["_common.ps1"] and "Test-SecretsPresent" in allp["_common.ps1"]


# ───────────── CI/자동화(.github 없음, automation/ 예시) ─────────────

def test_ci_files_inventory_and_known_hardening_gaps():
    """[정보] 저장소에는 활성 CI(.github/workflows)가 없다. automation/github-actions-harness.yml 은 예시이며 아래 갭은 '활성화 전' 해결 대상(DEF-9-005)."""
    assert not (ROOT / ".github").exists()
    wf = (ROOT / "automation" / "github-actions-harness.yml").read_text(encoding="utf-8")
    assert "permissions:" not in wf                       # 최소 권한 선언 없음
    assert re.search(r"actions/checkout@v\d", wf) and not re.search(r"@[0-9a-f]{40}", wf)  # 태그 고정, SHA 고정 아님
    assert "npm install -g @anthropic-ai/claude-code" in wf and "@anthropic-ai/claude-code@" not in wf  # 버전 미고정
    assert re.search(r"^env:\s*\n\s+ANTHROPIC_API_KEY", wf, re.M)  # 비밀이 워크플로 전체 환경변수
    assert "production-deploy-approval" in wf              # 배포 승인 environment 는 있음


def test_dockerignore_covers_secret_like_and_dev_cache_patterns():
    lines = {l.strip() for l in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
    allowlist = "*" in lines  # 허용 목록 방식이면 아래 항목은 필요 없다
    needed = {"*.pem", "*.key", "credentials*.json", ".ruff_cache", "**/.ruff_cache"}
    assert allowlist or ({"*.pem", "*.key"} <= lines and "credentials*.json" in lines and bool(lines & {".ruff_cache", "**/.ruff_cache"})), needed - lines
