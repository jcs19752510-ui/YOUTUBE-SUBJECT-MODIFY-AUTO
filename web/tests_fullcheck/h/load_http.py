"""실서버(uvicorn) 대상 HTTP 부하. 사용: load_http.py <base_url> <concs 쉼표> <total> [writes]"""
import asyncio, sys, time, httpx
BASE = sys.argv[1]; CONCS = [int(x) for x in sys.argv[2].split(",")]; TOTAL = int(sys.argv[3]); WRITES = len(sys.argv) > 4
ORIGIN = "http://127.0.0.1:8080"; HH = {"Host": "127.0.0.1:8080"}
def pct(v, p): v = sorted(v); return v[min(len(v)-1, int(len(v)*p/100))]*1000 if v else float("nan")
async def main():
    lim = httpx.Limits(max_connections=500, max_keepalive_connections=500)
    async with httpx.AsyncClient(base_url=BASE, timeout=60, limits=lim, headers=HH) as c:
        r = await c.post("/api/v1/auth/session", headers={"Origin": ORIGIN}); csrf = r.json()["csrf_token"]
        H = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        vids = [v["video_id"] for v in (await c.get("/api/v1/videos?page_size=200")).json()["items"]]
        READS = ["/api/v1/videos?page_size=200", "/api/v1/dashboard", "/api/v1/suggestions", "/api/v1/batches", "/api/v1/changes", "/api/v1/audit", "/api/v1/settings", "/api/readyz"]
        async def run(name, conc, total, mk):
            lat, codes = [], {}; q = asyncio.Queue(); [q.put_nowait(i) for i in range(total)]
            async def w():
                while True:
                    try: i = q.get_nowait()
                    except asyncio.QueueEmpty: return
                    t = time.perf_counter()
                    try: resp = await mk(i); k = resp.status_code
                    except Exception as e: k = type(e).__name__
                    lat.append(time.perf_counter()-t); codes[k] = codes.get(k, 0)+1
            t0 = time.perf_counter(); await asyncio.gather(*[w() for _ in range(conc)]); dt = time.perf_counter()-t0
            bad = sum(v for k, v in codes.items() if not (isinstance(k, int) and k < 400))
            print(f"RESULT {name} conc={conc} n={total} rps={total/dt:.0f} p50={pct(lat,50):.0f} p95={pct(lat,95):.0f} p99={pct(lat,99):.0f} max={max(lat)*1000:.0f} err={bad} ({100*bad/total:.1f}%) codes={codes}", flush=True)
        for conc in CONCS:
            await run(f"MIX-READ(8 endpoints)", conc, TOTAL, lambda i: c.get(READS[i % len(READS)]))
            await run("GET /videos?page_size=200", conc, TOTAL, lambda i: c.get(READS[0]))
        if WRITES:
            pos = 0
            for conc in CONCS:
                part = vids[pos:pos+min(conc*2, 100)]; pos += len(part); made = {}; errs = []
                async def mk(i, part=part, made=made, errs=errs):
                    resp = await c.post(f"/api/v1/videos/{part[i]}/suggestions", headers=H, json={})
                    if resp.status_code < 300:
                        j = resp.json(); made[part[i]] = j.get("id") or j.get("suggestion_id") or (j.get("suggestion") or {}).get("id")
                    elif len(errs) < 2: errs.append((resp.status_code, resp.text[:200]))
                    return resp
                await run("POST /videos/{id}/suggestions", conc, len(part), mk)
                if errs: print("WRITE-ERR-SAMPLE", errs)
                ids = [x for x in made.values() if x]
                print("suggestion ids read:", len(ids), "of", len(part))
                async def ap(i, ids=ids): return await c.post(f"/api/v1/suggestions/{ids[i]}/approve", headers=H, json={"approver": "load"})
                if ids: await run("POST /suggestions/{id}/approve", conc, len(ids), ap)
asyncio.run(main())
