"""compose 3종 설정 점검(정적, docker 미사용). 병합은 compose 규칙의 단순 재현(서비스별 networks/secrets/environment 합집합)."""
import pathlib, yaml, re
W = pathlib.Path(__file__).resolve().parents[2]
def load(n): return yaml.safe_load((W / n).read_text(encoding="utf-8"))
base, online, gem = load("compose.yaml"), load("compose.online.yaml"), load("compose.gemini.yaml")
SV = base["services"]

def merged(*extra):
    out = {k: dict(v) for k, v in SV.items()}
    for ex in extra:
        for k, v in ex.get("services", {}).items():
            o = out[k]
            for f in ("networks", "secrets"):
                if f in v: o[f] = (list(o.get(f, [])) if not isinstance(o.get(f), dict) else dict(o[f])) if f == "secrets" else {**o.get(f, {}), **v[f]}
                if f == "secrets": o[f] = list(o.get(f, [])) + v[f]
            if "environment" in v: o["environment"] = {**o.get("environment", {}), **v["environment"]}
    return out

def test_only_one_published_port_loopback():
    pub = {k: v["ports"] for k, v in SV.items() if "ports" in v}
    assert list(pub) == ["web"] and pub["web"] == ["127.0.0.1:8080:8080"], pub
    for ex in (online, gem): assert all("ports" not in v for v in ex["services"].values())

def test_hardening_every_service():
    for k, v in SV.items():
        assert v["read_only"] is True and v["cap_drop"] == ["ALL"] and "no-new-privileges:true" in v["security_opt"], k
        assert str(v["user"]).split(":")[0] not in ("0", "root"), k
        assert "privileged" not in v and "cap_add" not in v and "network_mode" not in v and "pid" not in v, k
        assert v["deploy"]["resources"]["limits"]["pids"], k
        assert not any("docker.sock" in str(x) for x in v.get("volumes", [])), k

def test_networks():
    n = base["networks"]
    assert n["front"]["internal"] and n["back"]["internal"] and not n["edge"].get("internal")
    assert set(SV["db"]["networks"]) == {"back"}
    assert set(SV["web"]["networks"]) == {"front", "edge"}
    for ex in (online, gem):
        assert "db" not in ex["services"] and "web" not in ex["services"] and "migrate" not in ex["services"]
    m = merged(online, gem)
    assert "egress" not in m["db"]["networks"] and "egress" not in m["web"]["networks"] and "egress" not in m["migrate"]["networks"]

def test_secrets_scoping_and_no_plain_values():
    m = merged(online, gem)
    assert not any("secrets" in m[s] and "db_" in str(m[s]["secrets"]) for s in ("web",))
    assert "db_app_password" not in m["migrate"].get("secrets", []) and "db_owner_password" not in m["api"].get("secrets", [])
    assert "google_client" not in m["db"].get("secrets", []) and "gemini_api_key" not in m["db"].get("secrets", [])
    txt = "".join((W / f).read_text(encoding="utf-8") for f in ("compose.yaml", "compose.online.yaml", "compose.gemini.yaml"))
    assert not re.search(r"(?i)(password|secret|key)[ \t]*:[ \t]*['\"]?[A-Za-z0-9/+_-]{12,}", re.sub(r"_FILE:.*|file:.*|POSTGRES_PASSWORD_FILE.*", "", txt))

def test_live_write_default_off_and_empty_allowlist():
    e = online["services"]["api"]["environment"]
    assert e["YTWEB_LIVE_WRITE"] == "${YTWEB_LIVE_WRITE:-0}" and e["YTWEB_LIVE_ALLOWED_VIDEOS"] == "${YTWEB_LIVE_ALLOWED_VIDEOS:-}"
    assert "YTWEB_LIVE_WRITE" not in str(base)

def test_base_mode_demo_docs_off():
    env = base["x-app-env"]
    assert env["YTWEB_MODE"] == "demo" and env["YTWEB_ENABLE_DOCS"] == "0"

def test_dockerfile_from_uses_digest_pinned_args():
    for f in (W / "docker").glob("*.Dockerfile"):
        t = f.read_text(encoding="utf-8")
        args = dict(re.findall(r"^ARG (\w+_IMAGE)=(\S+)", t, re.M))
        froms = re.findall(r"^FROM (\S+)", t, re.M)
        assert args and froms, f
        for fr in froms:
            name = re.fullmatch(r"\$\{(\w+)\}", fr).group(1)
            assert "@sha256:" in args[name] and re.search(r"@sha256:[0-9a-f]{64}$", args[name]), (f.name, name)
        assert re.search(r"^USER ", t, re.M), f

def test_db_image_has_compose_healthcheck_replacing_dockerfile_one():
    assert "healthcheck" in SV["db"] and "pg_isready" in str(SV["db"]["healthcheck"]["test"])
