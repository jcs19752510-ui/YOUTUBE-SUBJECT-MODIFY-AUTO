"""API 계약 시험(schemathesis 4.x, ASGI 직접 호출). 소스 수정 없음. 실행: python contract_test.py [max_examples]"""
import logging, os, sys, tempfile, json, collections
from pathlib import Path
from datetime import datetime, timezone

os.environ["YTWEB_AUTO_CREATE"] = "1"
os.environ.pop("YTWEB_STATIC_DIR", None)
import schemathesis
from schemathesis import checks as sc
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from youtube_title.config import load_settings
from ytweb.app import create_app
from ytweb.config import WebSettings
from ytweb.core.ratelimit import RateLimits
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain.seed import seed_demo
from ytweb.domain.common import Env

REPO = Path(__file__).resolve().parents[3]
ORIGIN = "http://127.0.0.1:8080"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 15
tmp = Path(tempfile.mkdtemp(prefix="ytcontract_", dir=REPO / ".harness-tmp"))
ws = WebSettings(mode="demo", database_url=f"sqlite:///{tmp/'t.db'}", base_dir=REPO, secrets_dir=tmp/"secrets",
                 allowed_hosts=("127.0.0.1:8080", "localhost:8080"), session_ttl_hours=12, session_idle_minutes=0)
app = create_app(ws, rate_limits=RateLimits(global_per_min=10_000_000, write_per_min=10_000_000, auth_per_min=10_000_000))
eng = make_engine(ws.database_url)
policy = load_settings(REPO, env={})
with make_session_factory(eng)() as s:
    seed_demo(s, datetime.now(timezone.utc), policy, count=60); s.commit()

c = TestClient(app, base_url=ORIGIN)
r = c.post("/api/v1/auth/session", headers={"Origin": ORIGIN}); assert r.status_code == 200, r.text
csrf = r.json()["csrf_token"]
cookies = "; ".join(f"{k}={v}" for k, v in c.cookies.items())
HEAD = {"Origin": ORIGIN, "X-CSRF-Token": csrf, "Cookie": cookies, "Host": "127.0.0.1:8080"}
def fresh():
    cc = TestClient(app, base_url=ORIGIN)
    rr = cc.post("/api/v1/auth/session", headers={"Origin": ORIGIN}); assert rr.status_code == 200
    return {"Origin": ORIGIN, "X-CSRF-Token": rr.json()["csrf_token"], "Cookie": "; ".join(f"{k}={v}" for k, v in cc.cookies.items()), "Host": "127.0.0.1:8080"}
spec = app.openapi()
json.dump(spec, open(tmp/"live_openapi.json", "w"), ensure_ascii=False, indent=1)
print("TMP", tmp, "paths", len(spec["paths"]))

logging.disable(logging.CRITICAL)
schema = schemathesis.openapi.from_dict(spec)
schema.config.update(base_url=ORIGIN)

stats = collections.Counter(); status_ct = collections.Counter(); fails = collections.defaultdict(list)
import hypothesis
from hypothesis import given, settings, HealthCheck, Phase

def one(case):
    global HEAD
    if case.method.upper() == "DELETE" and case.operation.path.endswith("/auth/session"):
        HEAD = fresh()
    resp = case.call(app=app, headers=HEAD)  # ASGI
    if case.method.upper() == "DELETE" and case.operation.path.endswith("/auth/session"):
        HEAD = fresh()
    key = f"{case.method} {case.operation.path}"
    stats[key] += 1; status_ct[(key, resp.status_code)] += 1
    ct = resp.headers.get("content-type", ""); ct = ",".join(ct) if isinstance(ct, list) else ct
    if resp.status_code >= 500:
        fails["5xx"].append((key, resp.status_code, str(case.body)[:200], str(case.query)[:200], str(case.path_parameters)[:120], resp.text[:200]))
    if resp.status_code >= 400 and resp.status_code < 500 and "problem+json" not in ct:
        fails["non-problem+json 4xx"].append((key, resp.status_code, ct, resp.text[:120]))
    try:
        case.validate_response(resp, checks=(sc.response_schema_conformance, sc.status_code_conformance, sc.content_type_conformance), excluded_checks=())
    except KeyboardInterrupt:
        raise
    except BaseException as e:  # noqa
        subs = getattr(e, "exceptions", [e])
        for x in subs:
            fails["schema:" + type(x).__name__].append((key, resp.status_code, str(x).split("\n")[0][:160], (str(x).replace("\n", " | "))[:260]))

for op in schema.get_all_operations():
    op = op.ok() if hasattr(op, "ok") else op
    strat = op.as_strategy()
    @settings(max_examples=N, deadline=None, database=None, suppress_health_check=list(HealthCheck), phases=[Phase.generate])
    @given(case=strat)
    def t(case): one(case)
    try:
        t()
    except Exception as e:
        fails["harness"].append((f"{op.method.upper()} {op.path}", type(e).__name__, str(e)[:200]))
print("OPERATIONS", len(stats), "calls", sum(stats.values()))
for k, v in fails.items():
    uniq = set(str(x[:3]) for x in v)
    print("==", k, len(v), "occurrences", len(uniq), "unique")
    seen = set()
    for x in v:
        sig = x[:3]
        if str(sig) in seen: continue
        seen.add(str(sig)); print("  ", x)
print("STATUS"); 
for (k, st), n in sorted(status_ct.items()): print("  ", k, st, n)
