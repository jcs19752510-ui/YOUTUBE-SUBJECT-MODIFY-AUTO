"""W-FIX-INF + M2 compose.online 독립 검증(6단계, 2026-10-11) 정적 시험 — TC-VIF-001 부터.

구현자 시험(test_fix_inf*.py, test_compose_security.py, test_vi_independent.py)을 복사하지 않고 명세(DEC-045~048)에서 새로 만들었다.
도커 데몬이 필요 없다(교차 검증 1건만 docker CLI 가 있으면 실행). 변이 점검을 위해 VINF2_ROOT 로 저장소 사본을 가리킬 수 있다.

주의: 이 파일에서 xfail(strict) 로 표시된 시험은 열린 결함(DEF-VIF-NNN)을 증명하는 시험이다. 결함이 고쳐지면 XPASS 로 실패해 표식 제거를 알린다.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).resolve()
ROOT = Path(os.environ.get("VINF2_ROOT") or HERE.parents[2])
WEB = ROOT / "web"
COMPOSE = WEB / "compose.yaml"
ONLINE = WEB / "compose.online.yaml"
NGX = WEB / "docker" / "nginx"
SCRIPTS = WEB / "scripts"
DOCS = ROOT / "docs" / "yt"

SERVICES = ["db", "migrate", "api", "worker", "web"]
EXPECTED_USER = {"db": "999:999", "migrate": "10001:10001", "api": "10001:10001", "worker": "10001:10001", "web": "101:101"}
SEC_HEADERS = ["Content-Security-Policy", "X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy",
               "Permissions-Policy", "Cross-Origin-Opener-Policy", "Cross-Origin-Resource-Policy"]


def rd(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


@pytest.fixture(scope="module")
def base() -> dict:
    return yaml.safe_load(rd(COMPOSE))


@pytest.fixture(scope="module")
def overlay() -> dict:
    return yaml.safe_load(rd(ONLINE))


def _names(v) -> set[str]:
    """networks/secrets 가 목록이든 사전이든 이름 집합으로."""
    if v is None:
        return set()
    return set(v.keys()) if isinstance(v, dict) else {x if isinstance(x, str) else x["source"] for x in v}


def _env(s: dict) -> dict:
    e = s.get("environment", {})
    if isinstance(e, list):
        return dict(x.split("=", 1) for x in e)
    return {k: str(v) for k, v in e.items()}


def merge_online(base: dict, ov: dict) -> dict:
    """compose 병합 규칙의 최소 구현: 사전은 재귀 병합, 목록 중 networks/secrets/ports/volumes 는 합집합(추가)."""
    out = copy.deepcopy(base)
    for name, osvc in (ov.get("services") or {}).items():
        s = out["services"].setdefault(name, {})
        for k, v in osvc.items():
            if k == "environment":
                s["environment"] = {**_env(s), **_env({"environment": v})}
            elif k == "networks":
                cur = s.get("networks") or {}
                cur = {n: {} for n in cur} if isinstance(cur, list) else dict(cur)
                add = {n: {} for n in v} if isinstance(v, list) else dict(v)
                s["networks"] = {**cur, **add}
            elif k in ("secrets", "ports", "volumes"):
                s[k] = list(s.get(k, [])) + list(v)
            else:
                s[k] = v
    for sect in ("secrets", "networks", "volumes"):
        if sect in ov:
            out.setdefault(sect, {}).update(ov[sect])
    return out


# ---------------------------------------------------------------- A. compose 기본 하드닝

@pytest.mark.parametrize("name", SERVICES)
def test_vif_001_hardening_flags(base, name):
    """TC-VIF-001 서비스마다 read_only, cap_drop ALL, no-new-privileges, 권한 상승 옵션 없음."""
    s = base["services"][name]
    assert s.get("read_only") is True
    assert [str(c).upper() for c in s.get("cap_drop", [])] == ["ALL"]
    assert not s.get("cap_add")
    assert "no-new-privileges:true" in [str(x).replace(" ", "") for x in s.get("security_opt", [])]
    assert not s.get("privileged")


@pytest.mark.parametrize("name", SERVICES)
def test_vif_002_non_root_user(base, name):
    """TC-VIF-002 숫자 uid:gid 로 지정된 비루트 사용자."""
    u = str(base["services"][name].get("user", ""))
    assert re.fullmatch(r"\d+:\d+", u), u
    assert not u.startswith("0:") and not u.endswith(":0")
    assert u == EXPECTED_USER[name]


def test_vif_003_no_host_level_escapes(base):
    """TC-VIF-003 호스트 네임스페이스·소켓·장치·호스트 경로 마운트·host-gateway 가 없다."""
    for name, s in base["services"].items():
        for k in ("network_mode", "pid", "ipc", "uts", "userns_mode", "devices", "sysctls", "cgroup_parent", "extra_hosts", "dns"):
            assert k not in s, (name, k)
        for v in s.get("volumes", []):
            src = v.split(":")[0] if isinstance(v, str) else v.get("source", "")
            assert src in base["volumes"], (name, v)           # 이름 붙은 볼륨만
            assert "docker.sock" not in str(v)
    assert "docker.sock" not in COMPOSE.read_text(encoding="utf-8")


def test_vif_004_only_web_publishes_loopback_8080(base):
    """TC-VIF-004 호스트 포트는 web 의 127.0.0.1:8080->8080 하나뿐."""
    pub = {n: s["ports"] for n, s in base["services"].items() if s.get("ports")}
    assert list(pub) == ["web"]
    assert pub["web"] == ["127.0.0.1:8080:8080"]
    for n, s in base["services"].items():
        assert "0.0.0.0" not in json.dumps(s.get("ports", []))
    assert not re.search(r"^\s*-\s*['\"]?(?:0\.0\.0\.0:|:)?\d+:\d+['\"]?\s*$", COMPOSE.read_text(encoding="utf-8"), re.M), "IP 없는 포트 게시 행"


def test_vif_005_network_definitions(base):
    """TC-VIF-005 front/back 은 internal, edge 만 비-internal, 그 외 망 없음."""
    n = base["networks"]
    assert set(n) == {"front", "back", "edge"}
    assert n["front"].get("internal") is True
    assert n["back"].get("internal") is True
    assert not n["edge"].get("internal")
    for k, v in n.items():
        assert not v.get("external"), k


def test_vif_006_network_membership_matrix(base):
    """TC-VIF-006 DEC-045: web 은 db 에 닿지 못한다. 서비스별 소속 망이 정확히 일치."""
    exp = {"db": {"back"}, "migrate": {"back"}, "api": {"front", "back"}, "worker": {"back"}, "web": {"front", "edge"}}
    for name, s in base["services"].items():
        assert _names(s.get("networks")) == exp[name], name
    assert not (_names(base["services"]["web"]["networks"]) & _names(base["services"]["db"]["networks"]))
    holders_edge = [n for n, s in base["services"].items() if "edge" in _names(s.get("networks"))]
    assert holders_edge == ["web"]


def test_vif_007_secrets_files_and_allocation(base):
    """TC-VIF-007 비밀 3개는 ./secrets/<이름> 파일, 서비스별 최소 권한 분배."""
    sec = base["secrets"]
    assert set(sec) == {"db_superuser_password", "db_owner_password", "db_app_password"}
    for k, v in sec.items():
        assert v == {"file": f"./secrets/{k}"}, k
    alloc = {n: _names(s.get("secrets")) for n, s in base["services"].items()}
    assert alloc["db"] == set(sec)
    assert alloc["migrate"] == {"db_owner_password"}
    assert alloc["api"] == {"db_app_password"}
    assert alloc["worker"] == {"db_app_password"}
    assert alloc["web"] == set()


def test_vif_008_no_plaintext_secret_in_env(base):
    """TC-VIF-008 환경변수의 비밀 항목은 *_FILE 이고 /run/secrets 를 가리킨다. 비밀값 자체가 파일에 없다."""
    for name, s in base["services"].items():
        for k, v in _env(s).items():
            if re.search(r"(PASS|SECRET|TOKEN|KEY|CREDENTIAL)", k, re.I) and not k.endswith("_DIR"):   # _DIR 은 경로(값이 아님)
                assert k.endswith("_FILE"), (name, k)
                assert v.startswith("/run/secrets/"), (name, k, v)
    assert "POSTGRES_PASSWORD:" not in COMPOSE.read_text(encoding="utf-8").replace("POSTGRES_PASSWORD_FILE:", "")


def test_vif_009_writable_surface(base):
    """TC-VIF-009 쓰기 가능한 곳은 tmpfs(noexec,nosuid)와 이름 볼륨뿐. 볼륨은 필요한 서비스에만."""
    for name, s in base["services"].items():
        for t in s.get("tmpfs", []):
            assert "noexec" in t and "nosuid" in t, (name, t)
    vols = {n: {(v.split(":")[0] if isinstance(v, str) else v["source"]) for v in s.get("volumes", [])} for n, s in base["services"].items()}
    assert vols == {"db": {"pgdata", "backups"}, "migrate": set(), "api": {"app_secrets"}, "worker": {"app_secrets"}, "web": set()}


def test_vif_010_resource_limits(base):
    """TC-VIF-010 모든 서비스에 cpus·memory·pids 상한."""
    for name, s in base["services"].items():
        lim = s["deploy"]["resources"]["limits"]
        assert {"cpus", "memory", "pids"} <= set(lim), name


def test_vif_011_healthchecks_and_ordering(base):
    """TC-VIF-011 db/api/worker/web 헬스체크, api·worker 는 migrate 성공 후 기동, web 은 api 정상 후 기동."""
    sv = base["services"]
    for n in ("db", "api", "worker", "web"):
        assert sv[n]["healthcheck"].get("test"), n
    assert sv["migrate"]["healthcheck"] == {"disable": True}
    for n in ("api", "worker"):
        assert sv[n]["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert sv["web"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert sv["migrate"]["depends_on"]["db"]["condition"] == "service_healthy"
    assert sv["migrate"]["restart"] == "no"


def test_vif_012_images_and_pull_policy(base):
    """TC-VIF-012 api/worker/migrate 는 같은 이미지, 만든 적 없는 이미지를 받아오지 않는다(pull_policy never)."""
    sv = base["services"]
    imgs = {sv[n]["image"] for n in ("api", "worker", "migrate")}
    assert imgs == {"${YTWEB_IMAGE_PREFIX:-ytweb}-api:local"}
    assert sv["migrate"]["pull_policy"] == "never" and sv["worker"]["pull_policy"] == "never"
    assert "build" in sv["api"] and "build" not in sv["worker"] and "build" not in sv["migrate"]


def test_vif_013_api_healthcheck_uses_internal_root_path(base):
    """TC-VIF-013 nginx 가 루트 /healthz 를 404 로 닫아도 컨테이너 헬스체크는 api 내부(8000)의 /healthz 를 쓴다."""
    t = " ".join(base["services"]["api"]["healthcheck"]["test"])
    assert "127.0.0.1:8000/healthz" in t
    assert "/nginx-health" in " ".join(base["services"]["web"]["healthcheck"]["test"])


@pytest.mark.xfail(strict=True, reason="DEF-VIF-002 open: compose.yaml 머리 주석이 폐기된 app 네트워크 구조를 설명한다")
def test_vif_014_compose_comment_matches_network_design():
    """TC-VIF-014 compose.yaml 설계 요약 주석이 DEC-045 이후의 3망 구조와 모순되지 않는다."""
    head = "\n".join(rd(COMPOSE).splitlines()[:10])
    assert "app 네트워크" not in head


# ---------------------------------------------------------------- B. compose.online 덧씌우기

def test_vif_020_overlay_key_whitelist(overlay):
    """TC-VIF-020 덧씌우기는 api/worker 의 networks·environment·secrets 와 최상위 secrets/networks 만 건드린다(권한·포트·마운트 추가 불가)."""
    assert set(overlay) <= {"services", "secrets", "networks"}
    assert set(overlay["services"]) == {"api", "worker"}
    for n, s in overlay["services"].items():
        assert set(s) == {"networks", "environment", "secrets"}, n
    assert set(overlay["secrets"]) == {"google_client"}
    assert set(overlay["networks"]) == {"egress"}
    txt = ONLINE.read_text(encoding="utf-8")
    for bad in ("ports:", "cap_add", "privileged", "volumes:", "devices", "network_mode", "read_only", "user:", "security_opt", "docker.sock"):
        assert not re.search(rf"^\s*{re.escape(bad)}", txt, re.M), bad


def test_vif_021_merged_no_new_ports_or_privileges(base, overlay):
    """TC-VIF-021 병합 결과에서 포트·하드닝·사용자·볼륨이 기본과 완전히 같다."""
    m = merge_online(base, overlay)
    for n in SERVICES:
        for k in ("ports", "read_only", "cap_drop", "cap_add", "security_opt", "user", "volumes", "tmpfs", "privileged", "image", "command", "healthcheck", "deploy"):
            assert m["services"][n].get(k) == base["services"][n].get(k), (n, k)
    assert m["services"]["web"]["ports"] == ["127.0.0.1:8080:8080"]
    assert sum(1 for s in m["services"].values() if s.get("ports")) == 1


def test_vif_022_egress_membership_and_db_isolation(base, overlay):
    """TC-VIF-022 egress 는 api·worker 만. db·web·migrate 는 외부 통신 가능한 망에 새로 붙지 않는다."""
    m = merge_online(base, overlay)
    holders = sorted(n for n, s in m["services"].items() if "egress" in _names(s.get("networks")))
    assert holders == ["api", "worker"]
    for n in ("db", "migrate"):
        assert _names(m["services"][n]["networks"]) == {"back"}
    assert _names(m["services"]["web"]["networks"]) == {"front", "edge"}
    assert "egress" not in base["networks"]                      # 기본 실행에는 egress 가 존재하지 않는다
    assert overlay["networks"]["egress"] == {"driver": "bridge"}  # external·기존 망 부착 없음
    # 기존 망 소속은 유지(front/back internal 약화 없음)
    assert m["networks"]["front"]["internal"] and m["networks"]["back"]["internal"]


def test_vif_023_google_secret_scope(base, overlay):
    """TC-VIF-023 google_client 비밀은 api·worker 에만, 환경변수는 파일 경로만 가진다."""
    m = merge_online(base, overlay)
    assert m["secrets"]["google_client"] == {"file": "./secrets/google_client.json"}
    holders = sorted(n for n, s in m["services"].items() if "google_client" in _names(s.get("secrets")))
    assert holders == ["api", "worker"]
    for n in ("api", "worker"):
        assert _env(m["services"][n])["YTWEB_GOOGLE_CLIENT_FILE"] == "/run/secrets/google_client"
        assert _names(m["services"][n]["secrets"]) == {"db_app_password", "google_client"}
    # 기존 환경변수 보존(덮어쓰기로 모드·허용 호스트가 바뀌지 않음)
    for n in ("api", "worker"):
        for k, v in _env(base["services"][n]).items():
            assert _env(m["services"][n])[k] == v


def test_vif_024_overlay_secret_file_consistent_with_ps1():
    """TC-VIF-024 오버레이가 읽는 파일 경로와 _common.ps1 이 존재 여부를 검사하는 경로가 같은 파일이다."""
    ov = rd(ONLINE)
    assert re.search(r"file:\s*\./secrets/google_client\.json\s*$", ov, re.M)
    ps = rd(SCRIPTS / "_common.ps1")
    m = re.search(r"\$YtwebGoogleClient\s*=\s*Join-Path\s+\$YtwebWebDir\s+'secrets\\google_client\.json'", ps)
    assert m, "ps1 의 구글 클라이언트 경로"
    m2 = re.search(r"\$YtwebOnlineFile\s*=\s*Join-Path\s+\$YtwebWebDir\s+'compose\.online\.yaml'", ps)
    assert m2 and ONLINE.exists()


def test_vif_025_google_secret_never_committed_or_built():
    """TC-VIF-025 web/secrets 는 git·docker 빌드 컨텍스트에서 제외된다."""
    gi = rd(ROOT / ".gitignore")
    assert re.search(r"^web/secrets/\s*$", gi, re.M)
    di = rd(ROOT / ".dockerignore")
    assert re.search(r"^secrets/\s*$", di, re.M) and re.search(r"^\*\*/secrets/\s*$", di, re.M)


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI 없음")
def test_vif_026_docker_compose_config_cross_check(tmp_path):
    """TC-VIF-026 `docker compose config` 로 실제 병합한 결과를 독립 확인(내 병합 함수와 같은 결론인지)."""
    w = tmp_path / "web"
    (w / "secrets").mkdir(parents=True)
    for f in ("db_superuser_password", "db_owner_password", "db_app_password", "google_client.json"):
        (w / "secrets" / f).write_text("x")
    shutil.copy(COMPOSE, w / "compose.yaml")
    shutil.copy(ONLINE, w / "compose.online.yaml")

    def cfg(*files):
        a = ["docker", "compose", "-p", "x"]
        for f in files:
            a += ["-f", str(w / f)]
        p = subprocess.run(a + ["config", "--format", "json"], capture_output=True, text=True, timeout=60, env={**os.environ, "YTWEB_IMAGE_PREFIX": "x"})
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)

    b, o = cfg("compose.yaml"), cfg("compose.yaml", "compose.online.yaml")
    for n in SERVICES:
        assert o["services"][n].get("read_only") is True and o["services"][n]["cap_drop"] == ["ALL"], n
        assert o["services"][n].get("ports") == b["services"][n].get("ports"), n
        assert o["services"][n].get("user") == b["services"][n].get("user"), n
    assert [(p["host_ip"], p["published"], p["target"]) for p in o["services"]["web"]["ports"]] == [("127.0.0.1", "8080", 8080)]
    assert set(o["services"]["api"]["networks"]) == {"front", "back", "egress"}
    assert set(o["services"]["worker"]["networks"]) == {"back", "egress"}
    assert set(o["services"]["db"]["networks"]) == {"back"}
    assert set(o["services"]["api"]["secrets"][i]["source"] for i in range(len(o["services"]["api"]["secrets"]))) == {"db_app_password", "google_client"}
    assert "egress" not in b["networks"]
    assert o["networks"]["front"]["internal"] is True and o["networks"]["back"]["internal"] is True


# ---------------------------------------------------------------- C. nginx

def strip_comments(t: str) -> str:
    return "\n".join(re.sub(r"(?<!\S)#.*$", "", ln) for ln in t.splitlines())


def blocks(text: str, head_re: str) -> list[tuple[str, str]]:
    """head_re 로 시작하는 `{ ... }` 블록의 (머리, 본문) 목록(중괄호 짝 맞춤)."""
    out = []
    for m in re.finditer(head_re + r"\s*\{", text):
        i, depth = m.end(), 1
        while depth and i < len(text):
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        out.append((text[m.start():m.end() - 1].strip(), text[m.end():i - 1]))
    return out


@pytest.fixture(scope="module")
def nginx() -> str:
    return strip_comments(rd(NGX / "nginx.conf"))


@pytest.fixture(scope="module")
def locs(nginx) -> dict[str, str]:
    return {h: b for h, b in blocks(nginx, r"location\s+[^{;]+?")}


def test_vif_030_root_probes_closed_with_404(locs):
    """TC-VIF-030 DEC-047: 루트 /healthz·/readyz 는 정확 일치 위치에서 404 를 반환하고 프록시·SPA 로 넘기지 않는다."""
    for p in ("/healthz", "/readyz"):
        b = locs[f"location = {p}"]
        assert re.search(r"return\s+404\b", b)
        assert "proxy_pass" not in b and "try_files" not in b and "rewrite" not in b
        assert "Cache-Control" in b
    # 같은 경로를 되살리는 다른 위치(접두사·정규식)가 없다
    for h in locs:
        if h.startswith("location = "):
            continue
        assert "healthz" not in h and "readyz" not in h, h


def test_vif_031_api_probes_proxied_to_exact_upstream_paths(locs):
    """TC-VIF-031 /api/healthz·/api/readyz 만 열려 있고 api:8000 의 /healthz·/readyz 로 간다."""
    for p in ("healthz", "readyz"):
        b = locs[f"location = /api/{p}"]
        assert re.search(rf"proxy_pass\s+\$api_upstream/{p}\s*;", b)
        assert "limit_req zone=ytweb_api" in b
        assert "security-headers-api.conf" in b


def test_vif_032_only_one_upstream(nginx):
    """TC-VIF-032 프록시 대상은 http://api:8000 하나(열린 프록시·SSRF 불가)."""
    assert set(re.findall(r"set\s+\$api_upstream\s+(\S+?);", nginx)) == {"http://api:8000"}
    for t in re.findall(r"proxy_pass\s+(\S+?);", nginx):
        assert t.startswith("$api_upstream"), t
    assert not re.search(r"proxy_pass\s+https?://", nginx)


def test_vif_033_security_header_snippets():
    """TC-VIF-033 두 스니펫이 7개 보안 헤더를 always 로 가진다. 페이지용 CSP 는 unsafe-eval/인라인 스크립트 없음, API 용은 default-src 'none'."""
    page = strip_comments(rd(NGX / "security-headers.conf"))
    api = strip_comments(rd(NGX / "security-headers-api.conf"))
    for name, t in (("page", page), ("api", api)):
        for h in SEC_HEADERS:
            assert len(re.findall(rf'add_header\s+{h}\s+"[^"]+"\s+always;', t)) == 1, (name, h)
        assert "Cache-Control" not in t, name
    csp = re.search(r'Content-Security-Policy\s+"([^"]+)"', page).group(1)
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "unsafe-eval" not in csp
    assert not re.search(r"script-src[^;]*unsafe-inline", csp)
    assert "*" not in csp
    acsp = re.search(r'Content-Security-Policy\s+"([^"]+)"', api).group(1)
    assert acsp.startswith("default-src 'none'")
    other = lambda t: sorted(l.strip() for l in t.splitlines() if "add_header" in l and "Content-Security-Policy" not in l)
    assert other(page) == other(api)


def test_vif_034_headers_survive_nginx_add_header_inheritance(nginx, locs):
    """TC-VIF-034 add_header 를 가진 모든 위치는 보안 스니펫을 include 한다(상속 소실 방지). server 레벨에도 include."""
    srv = blocks(nginx, r"server")[0][1]
    top_level = re.sub(r"location\s+[^{;]+?\{(?:[^{}]|\{[^{}]*\})*\}", "", srv)
    assert "security-headers.conf" in top_level
    for h, b in locs.items():
        if "add_header" in b or "security-headers" in b:
            assert re.search(r"include\s+/etc/nginx/snippets/security-headers(-api)?\.conf;", b), h


def test_vif_035_cache_control_exactly_once(nginx, locs):
    """TC-VIF-035 DEF-7-001: 위치마다 nginx 가 Cache-Control 을 정확히 1번 붙이고, 프록시 위치는 업스트림 것을 숨긴다."""
    proxy = strip_comments(rd(NGX / "proxy.conf"))
    assert re.search(r"proxy_hide_header\s+Cache-Control\s*;", proxy)
    for h, b in locs.items():
        if h in ("location = /nginx-health",):
            assert "Cache-Control" not in b
            continue
        n = len(re.findall(r"add_header\s+Cache-Control\b", b))
        assert n == 1, (h, n)
        if "proxy_pass" in b:
            assert re.search(r"include\s+/etc/nginx/snippets/proxy\.conf;", b), h
    assert len(re.findall(r"add_header\s+Cache-Control", nginx)) == len(locs) - 1


def test_vif_036_proxy_hides_backend_duplicates():
    """TC-VIF-036 proxy.conf 가 백엔드의 7개 보안 헤더·Server·X-Powered-By 를 숨겨 한 벌만 나가게 한다."""
    p = strip_comments(rd(NGX / "proxy.conf"))
    for h in SEC_HEADERS + ["Server", "X-Powered-By", "Cache-Control"]:
        assert re.search(rf"proxy_hide_header\s+{h}\s*;", p), h
    assert "proxy_set_header Host $http_host" in p
    assert "X-Forwarded-For $remote_addr" in p                   # 클라이언트 입력(XFF)을 이어 붙이지 않는다


def test_vif_037_server_level_controls(nginx):
    """TC-VIF-037 server_tokens off, 8080 하나만 listen, Host 허용 목록과 444, 오류 로그 수준."""
    assert re.search(r"server_tokens\s+off;", nginx)
    assert re.findall(r"listen\s+([^;]+);", nginx) == ["8080 default_server"]
    m = blocks(nginx, r"map\s+\$http_host\s+\$ytweb_host_ok")[0][1]
    assert re.findall(r'"([^"]+)"\s+1;', m) == ["127.0.0.1:8080", "localhost:8080"]
    assert re.search(r"default\s+0;", m)
    assert re.search(r"if\s*\(\$ytweb_host_ok\s*=\s*0\)\s*\{\s*return\s+444;", nginx)
    assert re.search(r"^error_log\s+/dev/stderr\s+error;", nginx, re.M)
    assert not re.search(r"autoindex\s+on|\balias\b|\.\./", nginx)


def test_vif_038_access_log_has_no_query_cookie(nginx):
    """TC-VIF-038 액세스 로그 형식에 쿼리 문자열·쿠키·원본 요청 줄·Authorization 이 없다(OAuth ?code= 대비)."""
    fmt = re.search(r"log_format\s+json_log\s+[^']*'([^']+)'", nginx).group(1)
    for bad in ("$args", "$query_string", "$request_uri", "$request ", "$http_cookie", "$http_authorization", "$http_referer", "$cookie_"):
        assert bad not in fmt + " ", bad
    assert "$uri" in fmt


def test_vif_039_method_and_size_limits(nginx, locs):
    """TC-VIF-039 / 와 /assets/ 는 GET·HEAD 외 거부, /api/ 는 허용 메서드 한정, 본문 1m 제한."""
    assert re.search(r"limit_except\s+GET\s+HEAD\s*\{\s*deny all;", locs["location /"])
    assert re.search(r"limit_except\s+GET\s+HEAD\s*\{\s*deny all;", locs["location /assets/"])
    assert re.search(r"limit_except\s+GET\s+HEAD\s+POST\s+PUT\s+PATCH\s+DELETE\s*\{\s*deny all;", locs["location /api/"])
    assert re.search(r"client_max_body_size\s+1m;", nginx)
    assert re.search(r"limit_req_status\s+429;", nginx)
    assert "ytweb_auth" in locs["location = /api/v1/auth/session"]
    assert re.search(r"proxy_pass\s+\$api_upstream;", locs["location /api/"])   # 변수 프록시: URI 를 그대로 전달


def test_vif_040_nginx_health_is_local_only():
    """TC-VIF-040 /nginx-health 는 정적 200 응답이며 프록시하지 않는다."""
    b = blocks(strip_comments(rd(NGX / "nginx.conf")), r"location\s+=\s+/nginx-health")[0][1]
    assert "return 200" in b and "proxy_pass" not in b


@pytest.mark.xfail(strict=True, reason="DEF-VIF-001 open: 끝 슬래시·대소문자 변형(/healthz/, /HEALTHZ)은 SPA 로 넘어가 HTML 200 을 돌려준다")
def test_vif_041_root_probe_variants_not_html_200(locs):
    """TC-VIF-041 DEF-7-006 의 취지(프로브가 HTML 200 을 정상으로 오판하지 않음)가 /healthz/ 변형에도 적용된다."""
    # 정확 일치(=) 위치만 있고 접두사/정규식 폴백이 없으면 /healthz/ 는 location / 로 가 SPA 가 된다.
    assert any(h.startswith("location ~") and "healthz" in h for h in locs) or any(h.startswith("location /healthz") for h in locs)


# ---------------------------------------------------------------- D. PowerShell 정적 점검 (pwsh 없음: 문자열·정규식 수준)

PS_FILES = sorted(SCRIPTS.glob("*.ps1"))


def ps_strip(t: str) -> str:
    """주석(#...)·here-string·따옴표 문자열 내용을 비워 괄호 짝을 센다."""
    t = re.sub(r"<#.*?#>", "", t, flags=re.S)
    t = re.sub(r'@"\r?\n.*?\r?\n"@', '""', t, flags=re.S)
    t = re.sub(r"@'\r?\n.*?\r?\n'@", "''", t, flags=re.S)
    out = []
    for ln in t.splitlines():
        res, q = "", None
        for ch in ln:
            if q:
                if ch == q:
                    q = None
                continue
            if ch in "'\"":
                q = ch
                continue
            if ch == "#":
                break
            res += ch
        out.append(res)
    return "\n".join(out)


@pytest.mark.parametrize("f", PS_FILES, ids=lambda p: p.name)
def test_vif_050_ps_bom_and_balance(f):
    """TC-VIF-050 모든 ps1 은 UTF-8 BOM(한글, Windows PowerShell 5.1)이고 중괄호·괄호 짝이 맞으며 CRLF/LF 혼재가 아니다."""
    raw = f.read_bytes()
    assert raw[:3] == b"\xef\xbb\xbf", f.name
    s = ps_strip(raw.decode("utf-8-sig"))
    for a, b in (("{", "}"), ("(", ")"), ("[", "]")):
        assert s.count(a) == s.count(b), (f.name, a, s.count(a), s.count(b))
    assert not (b"\r\n" in raw and re.search(rb"[^\r]\n", raw)), "줄바꿈 혼재"


def test_vif_051_invoke_compose_overlay_logic():
    """TC-VIF-051 Invoke-Compose: 구글 파일이 있을 때만 기본 파일 다음에 오버레이를 붙이고, 프로젝트 이름을 -p 로 전달한다."""
    ps = rd(SCRIPTS / "_common.ps1")
    fn = blocks(ps, r"function\s+Invoke-Compose[^{]*")[0][1]
    assert re.search(r"\$files\s*=\s*@\('-f',\s*\$YtwebComposeFile\)", fn)
    assert re.search(r"if\s*\(Test-Path\s+\$YtwebGoogleClient\)\s*\{\s*\$files\s*\+=\s*@\('-f',\s*\$YtwebOnlineFile\)\s*\}", fn)
    assert fn.index("$YtwebComposeFile") < fn.index("$YtwebOnlineFile")
    assert re.search(r"@\('compose',\s*'-p',\s*\$YtwebProject\)\s*\+\s*\$files\s*\+\s*\$ArgList", fn)
    assert fn.count("Test-Path") == 1                          # 오버레이 조건이 한 곳뿐


def test_vif_052_all_scripts_go_through_invoke_compose():
    """TC-VIF-052 _common.ps1 밖에서 docker compose 를 직접 부르지 않는다(오버레이 누락 방지)."""
    for f in PS_FILES:
        if f.name == "_common.ps1":
            continue
        t = ps_strip(rd(f))
        raw = rd(f)
        assert "$YtwebComposeFile" not in t.replace("Test-ComposeFileExists", ""), f.name
        assert not re.search(r"-ArgList\s+@\(\s*'compose'", raw), f.name
        assert not re.search(r"&\s*docker\s+compose", raw), f.name


def test_vif_053_ps_constants_match_compose(base):
    """TC-VIF-053 스크립트의 포트·URL·서비스·비밀 이름이 compose.yaml 과 일치."""
    ps = rd(SCRIPTS / "_common.ps1")
    assert "$YtwebPort        = 8080" in ps or re.search(r"\$YtwebPort\s*=\s*8080", ps)
    assert re.search(r"\$YtwebUrl\s*=\s*'http://127\.0\.0\.1:8080'", ps)
    names = re.search(r"\$YtwebSecretNames\s*=\s*@\(([^)]*)\)", ps).group(1)
    assert re.findall(r"'([^']+)'", names) == sorted(base["secrets"], key=lambda x: ["db_superuser_password", "db_owner_password", "db_app_password"].index(x))
    svcs = re.search(r"\$YtwebServices\s*=\s*@\(([^)]*)\)", ps).group(1)
    assert re.findall(r"'([^']+)'", svcs) == SERVICES
    assert set(re.findall(r"'([^']+)'", svcs)) == set(base["services"])
    assert re.search(r"if \(\$env:YTWEB_PROJECT\) \{ \$env:YTWEB_PROJECT \} else \{ 'ytweb' \}", ps)
    assert base["name"] == "ytweb"


def test_vif_054_secret_generation_policy():
    """TC-VIF-054 비밀은 CSPRNG 32바이트, 기존 파일은 덮어쓰지 않고, DB 볼륨이 있으면 새로 만들지 않으며, 값을 출력하지 않는다."""
    ps = rd(SCRIPTS / "_common.ps1")
    nr = blocks(ps, r"function\s+New-RandomSecret")[0][1]
    assert "RandomNumberGenerator" in nr and "New-Object byte[] 32" in nr and "Get-Random" not in ps
    ini = blocks(ps, r"function\s+Initialize-Secrets")[0][1]
    assert ini.count("-gt 0) { continue }") == 2               # 이미 있으면 건너뜀(루프 두 곳)
    assert re.search(r"Test-VolumeExists\s+'pgdata'", ini) and "Stop-Script" in ini
    assert re.search(r"Test-SecretsPresent\)\s*\{[^}]*return", ini, re.S)
    for ln in ps.splitlines():
        if re.search(r"Write-(Host|Info|Ok|Warn)", ln):
            assert not re.search(r"\$(secret|password|bytes)\b|Get-Content", ln, re.I), ln


def test_vif_055_no_dangerous_constructs():
    """TC-VIF-055 Invoke-Expression·원격 스크립트 내려받아 실행·비밀 폴더 재귀 삭제·0.0.0.0 바인딩이 스크립트에 없다."""
    for f in PS_FILES:
        t = rd(f)
        assert not re.search(r"Invoke-Expression|\biex\b", t, re.I), f.name
        assert not re.search(r"(DownloadString|Invoke-WebRequest|Invoke-RestMethod|\bcurl\b|\bwget\b)", t, re.I) or f.name in ("e2e.ps1", "pin-digests.ps1"), f.name
        assert "0.0.0.0" not in t, f.name
        assert not re.search(r"Remove-Item[^\n]*\$YtwebSecretsDir", t), f.name
    urls = set()
    for f in PS_FILES:
        urls |= set(re.findall(r"https?://[^\s'\"`)]+", rd(f)))
    ok = re.compile(r"^https?://(127\.0\.0\.1|localhost)|^https://(www\.docker\.com|docs\.docker\.com|github\.com|aka\.ms|learn\.microsoft\.com)")
    assert [u for u in urls if not ok.match(u)] == []


def test_vif_056_destructive_scripts_require_confirmation():
    """TC-VIF-056 복원·초기화는 확인 문구 없이는 진행하지 않는다."""
    r = rd(SCRIPTS / "restore.ps1")
    assert "Read-ConfirmText" in r and "exit 2" in r and "복원합니다" in r
    assert "Assert-BackupFileName" in r and "SHA-256" in r
    z = rd(SCRIPTS / "reset-demo.ps1")
    assert "Read-ConfirmText" in z


def test_vif_057_backup_filename_guard_regex_matches_db_tool():
    """TC-VIF-057 ps1 의 백업 파일명 정규식과 DB 도구(ytweb-db)의 정규식이 같은 집합을 허용한다(경로 이탈 방지)."""
    ps = rd(SCRIPTS / "_common.ps1")
    a = re.search(r"\$Name -notmatch '([^']+)'", ps).group(1)
    sh = rd(WEB / "docker" / "db" / "bin" / "ytweb-db")
    b = re.search(r'\[\[ "\$name" =~ ([^ ]+) \]\]', sh).group(1)
    assert a == b == r"^[A-Za-z0-9._-]+\.dump$"
    rx = re.compile(a)
    assert not rx.match("../x.dump") and not rx.match("a/b.dump") and not rx.match("a.dump\n x") and rx.match("ytweb-20260101-120000.dump")


# ---------------------------------------------------------------- E. 문서 일관성 (DEC-047)

def test_vif_060_docs_state_root_probe_closed():
    """TC-VIF-060 API.md·WEB_DESIGN.md·README 가 nginx 경유 상태 경로를 /api/healthz·/api/readyz 로, 루트는 404 로 쓴다."""
    for p in (DOCS / "API.md", DOCS / "WEB_DESIGN.md", WEB / "README.md"):
        t = rd(p)
        assert "/api/healthz" in t and "/api/readyz" in t, p.name
        assert re.search(r"루트[^\n]{0,40}(/healthz|`/healthz`)[^\n]{0,80}404", t) or re.search(r"404", t), p.name
    assert re.search(r"nginx[^\n]{0,30}루트 `/healthz`·`/readyz`를 404", rd(DOCS / "API.md"))


@pytest.mark.xfail(strict=True, reason="DEF-VIF-003 open: DESIGN.md NFR-W07 이 브라우저 포트에서 404 인 루트 /readyz 로 가용성을 측정한다고 적는다")
def test_vif_061_design_doc_availability_probe_path():
    """TC-VIF-061 DESIGN.md 가 사용자 포트로 측정할 수 있는 상태 경로를 안내한다(루트 /readyz 는 404)."""
    t = rd(DOCS / "DESIGN.md")
    line = [l for l in t.splitlines() if l.startswith("| NFR-W07")][0]
    assert "/api/readyz" in line
