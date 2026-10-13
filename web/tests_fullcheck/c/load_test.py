"""부하·장시간 스모크(ASGI 인-프로세스, 임시 PG). 사용: load_test.py <pg_url> <soak_seconds>"""
import asyncio, logging, os, sys, time, random, statistics, resource
from pathlib import Path
from datetime import datetime, timezone
import httpx
from youtube_title.config import load_settings
from ytweb.app import create_app
from ytweb.config import WebSettings
from ytweb.core.ratelimit import RateLimits
from ytweb.db.models import Base
from ytweb.db.session import make_engine, make_session_factory
from ytweb.domain.seed import seed_demo
REPO = Path(__file__).resolve().parents[3]; ORIGIN = "http://127.0.0.1:8080"
url, SOAK = sys.argv[1], int(sys.argv[2])
logging.disable(logging.CRITICAL)
tmp = REPO / ".harness-tmp" / "loadsecrets"
ws = WebSettings(mode="demo", database_url=url, base_dir=REPO, secrets_dir=tmp, allowed_hosts=("127.0.0.1:8080",), session_ttl_hours=12, session_idle_minutes=0)
eng = make_engine(url); Base.metadata.drop_all(eng); Base.metadata.create_all(eng)
with make_session_factory(eng)() as s:
    seed_demo(s, datetime.now(timezone.utc), load_settings(REPO, env={}), count=200); s.commit()
app = create_app(ws, rate_limits=RateLimits(global_per_min=10**8, write_per_min=10**8, auth_per_min=10**8))
def rss(): return int(open("/proc/self/statm").read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6
def pct(v, p): v = sorted(v); return v[min(len(v)-1, int(len(v)*p/100))] * 1000 if v else float("nan")
async def main():
    tr = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=tr, base_url=ORIGIN, timeout=60) as c:
        r = await c.post("/api/v1/auth/session", headers={"Origin": ORIGIN}); csrf = r.json()["csrf_token"]
        H = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        vids = [v["video_id"] for v in (await c.get("/api/v1/videos?page_size=200")).json()["items"]]
        print("videos", len(vids))
        READS = ["/api/v1/videos?page_size=200", "/api/v1/dashboard", "/api/v1/suggestions", "/api/v1/batches", "/api/v1/changes", "/api/v1/audit", "/api/v1/settings", "/api/readyz"]
        async def run(name, conc, total, mk):
            lat, errs, codes = [], 0, {}
            q = asyncio.Queue(); [q.put_nowait(i) for i in range(total)]
            async def w():
                nonlocal errs
                while True:
                    try: i = q.get_nowait()
                    except asyncio.QueueEmpty: return
                    t = time.perf_counter()
                    try: resp = await mk(i)
                    except Exception as e: errs += 1; codes[type(e).__name__] = codes.get(type(e).__name__, 0) + 1; continue
                    lat.append(time.perf_counter() - t); codes[resp.status_code] = codes.get(resp.status_code, 0) + 1
                    if resp.status_code >= 400: errs += 1
            t0 = time.perf_counter(); await asyncio.gather(*[w() for _ in range(conc)]); dt = time.perf_counter() - t0
            print(f"RESULT {name} conc={conc} n={total} rps={total/dt:.0f} p50={pct(lat,50):.0f}ms p95={pct(lat,95):.0f}ms p99={pct(lat,99):.0f}ms max={max(lat)*1000:.0f}ms err={errs} codes={codes} rss={rss():.0f}MB", flush=True)
        for conc in (20, 50):
            for ep in READS:
                await run(f"GET {ep}", conc, 300, lambda i, ep=ep: c.get(ep))
        # 쓰기: 제안 생성 → 승인 (영상별 1건씩)
        made = {}
        for conc, part in ((20, vids[:100]), (50, vids[100:200])):
            async def mk(i, part=part):
                resp = await c.post(f"/api/v1/videos/{part[i]}/suggestions", headers=H, json={})
                if resp.status_code < 300:
                    try: made[part[i]] = resp.json()["id"]
                    except Exception: pass
                return resp
            await run("POST /videos/{id}/suggestions", conc, len(part), mk)
            ids = [made[v] for v in part if v in made]
            async def ap(i, ids=ids): return await c.post(f"/api/v1/suggestions/{ids[i]}/approve", headers=H, json={"approver": "load"})
            await run("POST /suggestions/{id}/approve", conc, len(ids), ap)
        # 소크
        print("SOAK start", time.strftime("%T"), "rss", f"{rss():.0f}MB", flush=True)
        t0 = time.time(); n = 0; errs = 0; lat = []; samples = []; nxt = t0
        async def vu():
            nonlocal n, errs
            while time.time() - t0 < SOAK:
                ep = random.choice(READS); t = time.perf_counter()
                try: resp = await c.get(ep)
                except Exception: errs += 1; continue
                lat.append(time.perf_counter() - t); n += 1
                if resp.status_code >= 400: errs += 1
                await asyncio.sleep(0.02)
        async def sampler():
            while time.time() - t0 < SOAK:
                samples.append((int(time.time() - t0), rss(), n, errs)); await asyncio.sleep(15)
        await asyncio.gather(sampler(), *[vu() for _ in range(10)])
        samples.append((int(time.time() - t0), rss(), n, errs))
        for s_ in samples: print("SOAKSAMPLE t=%ds rss=%.1fMB reqs=%d errs=%d" % s_)
        print(f"SOAK total n={n} err={errs} p50={pct(lat,50):.0f}ms p95={pct(lat,95):.0f}ms p99={pct(lat,99):.0f}ms maxrss_kb={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}")
asyncio.run(main())
