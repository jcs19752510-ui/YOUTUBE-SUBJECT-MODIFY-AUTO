import ast, re, sys, glob, xml.etree.ElementTree as ET
from collections import defaultdict
BE = "/home/user/youtube-subject-modify-auto/web/backend"
res = defaultdict(lambda: [0, 0, 0])  # key (file::func) -> pass, fail, skip
for tc in ET.parse(sys.argv[1]).getroot().iter("testcase"):
    cls = tc.get("classname").split("."); f = cls[-1] + ".py"; name = re.sub(r"\[.*\]$", "", tc.get("name"))
    k = f"{f}::{name}"
    if tc.find("failure") is not None or tc.find("error") is not None: res[k][1] += 1
    elif tc.find("skipped") is not None: res[k][2] += 1
    else: res[k][0] += 1
rows = []
for path in sorted(glob.glob(f"{BE}/tests/verify_wa/test_va_*.py")):
    fn = path.split("/")[-1]
    for node in ast.parse(open(path, encoding="utf-8").read()).body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            doc = ast.get_docstring(node) or ""
            m = re.match(r"TC-VA-(\d+)\s*(\[[^\]]*\])?\s*(.*)", doc, re.S)
            if not m: print("NO TC", fn, node.name, file=sys.stderr); continue
            p, f_, s = res.get(f"{fn}::{node.name}", [0, 0, 0])
            rows.append((int(m.group(1)), (m.group(2) or "").strip("[]"), " ".join(m.group(3).split()), fn, node.name, p, f_, s))
rows.sort()
out = ["| ID | 시나리오·예상 결과(명세 근거) | 사전조건 | 실행 절차 | 실제 결과 | Pass/Fail | 비고(보안 요구 ID) |", "|---|---|---|---|---|---|---|"]
tot = [0, 0, 0]
for n, tags, doc, fn, name, p, f_, s in rows:
    pre = "임시 PG16" if "07_postgres" in fn or "pg" in name else ("실서버 기동" if "08_static" in fn or "09_static" in fn else "SQLite 임시 DB+가짜 시계")
    st = "PASS" if f_ == 0 and p > 0 else ("SKIP" if p == 0 and s else "FAIL")
    tot[0] += p; tot[1] += f_; tot[2] += s
    out.append(f"| TC-VA-{n:03d} | {doc.replace('|', '/')} | {pre} | `pytest tests/verify_wa/{fn}::{name}` | {p}건 통과" + (f", {f_}건 실패" if f_ else "") + (f", {s}건 건너뜀" if s else "") + f" | {st} | {tags} |")
print("\n".join(out))
print(f"\n<!-- TCs={len(rows)} pass={tot[0]} fail={tot[1]} skip={tot[2]} -->", file=sys.stderr)
