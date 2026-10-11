import json, os, shutil, subprocess, sys, concurrent.futures as cf
from pathlib import Path
ROOT = Path("/home/user/youtube-subject-modify-auto"); VA = ROOT/".harness-tmp/va"; MUT = VA/"mut"
SRC = ROOT/"web/backend"
sys.path.insert(0, str(MUT)); from mutants import M
round_name = sys.argv[1]; only = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
ids = [m for m in M if not only or m[0] in only]
NW = 4
PG_SET = {"M000","M43","M56","M58","M65","M104","M117","M118"}
def check_unique():
    bad = []
    for mid, f, old, new in M:
        c = (SRC/f).read_text(encoding="utf-8").count(old)
        if c != 1 and not mid.startswith("M00"): bad.append((mid, f, c))
    return bad
def make_copy(w):
    d = MUT/f"w{w}"
    if d.exists(): shutil.rmtree(d)
    (d/"web").mkdir(parents=True)
    shutil.copytree(SRC, d/"web/backend", ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".ruff_cache", "tests/core"))
    os.symlink(ROOT/"web/docker", d/"web/docker")
    for name in ("config", "src", "pyproject.toml"):
        p = ROOT/name
        if p.exists(): os.symlink(p, d/name)
    return d
def run_one(args):
    w, (mid, f, old, new) = args
    d = MUT/f"w{w}"
    target = d/"web/backend"/f
    orig = (SRC/f).read_text(encoding="utf-8")
    target.write_text(orig.replace(old, new), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "YTWEB_TEST_PG_URL"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if mid in PG_SET:  # 역할(ytweb_app)은 클러스터 전역이라 PG 시험은 동시에 하나만 돌린다
        env["YTWEB_TEST_PG_URL"] = "postgresql+psycopg://postgres@127.0.0.1:54331/ytweb_va_m0"
    try:
        r = subprocess.run([str(VA/"venv/bin/python"), "-m", "pytest", "tests/verify_wa", "-o", "addopts=", "-q", "-x", "-p", "no:cacheprovider", "--no-header", "-W", "ignore"],
                           cwd=d/"web/backend", env=env, capture_output=True, text=True, timeout=900)
        out = r.stdout.strip().splitlines()
        killed = r.returncode != 0
        tail = next((l for l in reversed(out) if l.startswith("FAILED") or l.startswith("ERROR")), out[-1] if out else "")
    except subprocess.TimeoutExpired:
        killed, tail = True, "TIMEOUT(hang = kill)"
    finally:
        target.write_text(orig, encoding="utf-8")
    return mid, killed, tail[:200]
if __name__ == "__main__":
    bad = check_unique()
    if bad: print("NOT UNIQUE", bad); sys.exit(2)
    for w in range(NW): make_copy(w)
    # per-worker queues
    buckets = [[] for _ in range(NW)]
    plain = [m for m in ids if m[0] not in PG_SET]
    for i, m in enumerate(plain): buckets[i % (NW - 1) + 1].append(m)
    buckets[0] = [m for m in ids if m[0] in PG_SET]
    def worker(w):
        res = []
        for m in buckets[w]:
            res.append(run_one((w, m))); print(res[-1], flush=True)
        return res
    with cf.ThreadPoolExecutor(NW) as ex:
        allres = [r for part in ex.map(worker, range(NW)) for r in part]
    allres.sort(key=lambda r: int(r[0][1:]))
    (MUT/f"result_{round_name}.json").write_text(json.dumps(allres, ensure_ascii=False, indent=1), encoding="utf-8")
    surv = [r for r in allres if not r[1]]
    print("TOTAL", len(allres), "KILLED", len(allres)-len(surv), "SURVIVED", [r[0] for r in surv])
