"""변이 점검 실행기. 사용: mutate.py <round> [ids...]  — 격리 사본에서만 소스를 바꾼다."""
import json, os, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
ROOT = "/home/user/youtube-subject-modify-auto"
SRC = ROOT + "/web/backend"
MUT = ROOT + "/.harness-tmp/vb/mut"
PY = ROOT + "/.harness-tmp/vb/venv/bin/python"
exec(open(ROOT + "/web/backend/tests/verify_wb/_mutation/mutations.py", encoding="utf-8").read())  # defines M: list of (id, relpath, old, new, nth, tests)

def run(m):
    mid, rel, old, new, nth, tests = m
    d = f"{MUT}/{mid}"
    shutil.rmtree(d, ignore_errors=True)
    shutil.copytree(SRC, d, ignore=shutil.ignore_patterns("__pycache__", "alembic", "*.pyc"))
    cf = f"{d}/tests/conftest.py"
    t = open(cf, encoding="utf-8").read()
    old_line = "REPO_ROOT = Path(__file__).resolve().parents[3]"
    assert old_line in t
    open(cf, "w", encoding="utf-8").write(t.replace(old_line, f'REPO_ROOT = Path("{ROOT}")'))
    p = f"{d}/{rel}"
    s = open(p, encoding="utf-8").read()
    c = s.count(old)
    if (nth is None and c != 1) or (nth is not None and c < nth):
        return mid, "BADTARGET", f"count={c}"
    if nth is None:
        s2 = s.replace(old, new)
    else:
        parts = s.split(old)
        s2 = old.join(parts[:nth]) + new + old.join(parts[nth:])
    assert s2 != s
    open(p, "w", encoding="utf-8").write(s2)
    env = dict(os.environ)
    env.pop("YTWEB_TEST_PG_URL", None)
    if tests.startswith("PG:"):
        env["YTWEB_TEST_PG_URL"] = "postgresql+psycopg://postgres@127.0.0.1:54332/ytvb_mut_" + mid.replace("-", "_")
        tests = tests[3:]
    r = subprocess.run([PY, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", *tests.split()], cwd=d, env=env, capture_output=True, text=True, timeout=900)
    out = r.stdout.strip().splitlines()
    last = out[-1] if out else ""
    first_fail = next((l for l in out if l.startswith("FAILED")), "")
    status = "KILLED" if r.returncode != 0 else "SURVIVED"
    shutil.rmtree(d, ignore_errors=True)
    return mid, status, (first_fail or last)[:200]

if __name__ == "__main__":
    ids = set(sys.argv[2:])
    ms = [m for m in M if not ids or m[0] in ids]
    res = []
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(run, ms):
            print(*r, flush=True); res.append(r)
    json.dump(res, open(f"{ROOT}/.harness-tmp/vb/mut_round{sys.argv[1]}.json", "w"), ensure_ascii=False, indent=1)
    print("KILLED", sum(r[1]=="KILLED" for r in res), "SURVIVED", [r[0] for r in res if r[1]=="SURVIVED"], "BAD", [r[0] for r in res if r[1]=="BADTARGET"])
