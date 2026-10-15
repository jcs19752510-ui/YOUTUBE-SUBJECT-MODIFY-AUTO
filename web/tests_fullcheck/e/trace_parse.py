import re, glob, os, json, collections
R = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
os.chdir(R)
src = {}
for pat in ["tests/**/*.py","web/backend/**/*.py","web/tests_*/**/*.py","web/tests_*/**/*.ts*","web/frontend/src/**/*.ts*","web/frontend/verify*/**/*.ts*","web/frontend/verify*/**/*.py"]:
    for f in glob.glob(pat, recursive=True):
        if "node_modules" in f: continue
        try: src[f] = open(f, encoding="utf-8").read()
        except Exception: pass
alltext = "\n".join(src.values())
idre = re.compile(r"^((FR|NFR|POL|SEC|W|D|F|EVT|UX|SCR|W-M2|W-M3)-[0-9a-z]+|S-W[0-9]+[a-z]?)$")
reqs = collections.OrderedDict()
for l in open("docs/harness/traceability.md", encoding="utf-8"):
    if not l.startswith("|"): continue
    p = [x.strip() for x in l.strip().strip("|").split("|")]
    if len(p) < 7 or not idre.match(p[0]): continue
    rid = p[0]; tc = p[6] if len(p) > 6 else ""
    e = reqs.setdefault(rid, {"type": p[1], "status": p[5], "tc": ""})
    if "TC-" in tc and "TC-" not in e["tc"]: e["tc"] = tc; e["status"] = p[5]
def ids(tc):
    out = set()
    for m in re.finditer(r"TC-([A-Z0-9]+-)?(\d+[A-Za-z]?)(?:~(\d+))?", tc):
        pre = "TC-" + (m.group(1) or ""); out.add(pre + m.group(2))
    # bare numbers following "TC-XX-nnn, nnn"
    for m in re.finditer(r"(TC-(?:[A-Z0-9]+-)?)\d+[A-Za-z]?((?:\s*,\s*\d+[A-Za-z]?(?:~\d+)?)+)", tc):
        for n in re.findall(r"\d+[A-Za-z]?", m.group(2)): out.add(m.group(1) + n)
    return out
res = []
for rid, e in reqs.items():
    I = ids(e["tc"]); found = [i for i in I if i in alltext or (re.sub(r"TC-([A-Z]+-)?", "", i) and False)]
    res.append((rid, e["type"], e["status"], bool(e["tc"]), len(I), len(found)))
json.dump(res, open("web/tests_fullcheck/e/trace_parse.json", "w"), ensure_ascii=False)
docs_text = "\n".join(open(f,encoding="utf-8").read() for f in glob.glob("docs/harness/**/*.md", recursive=True) if not f.endswith("traceability.md"))
for grp in ["FR","NFR","POL","SEC","W","D","F","S-W","EVT","UX","SCR","W-M2","W-M3"]:
    g = [r for r in res if r[0].startswith(grp + "-") and (grp not in ("W","S-W","SEC","D","F") or True) and (r[0].startswith("S-W") if grp=="S-W" else re.match(re.escape(grp) + r"-[0-9]", r[0]) and not r[0].startswith("W-M"))]
    if not g: continue
    print(grp, "n=", len(g), "linked(TC in doc)=", sum(r[3] for r in g), "ids-found-in-test-source>=1:", sum(r[5] > 0 for r in g))
tot = [r for r in res if r[1] in ("FR","NFR","POL","SEC","W","D","F")]
res2=[(r[0], r[1], r[2], r[3], len(ids(reqs[r[0]]["tc"])), sum(1 for i in ids(reqs[r[0]]["tc"]) if i in docs_text)) for r in res]
print("in result docs >=1:", {t: (sum(1 for r in res2 if r[1]==t and r[3]), sum(1 for r in res2 if r[1]==t and r[5]>0)) for t in set(r[1] for r in res2)})
print("TOTAL excl EVT/UX/SCR:", len(res), "all", sum(r[3] for r in res))
unl = [r[0] for r in res if not r[3]]; print("UNLINKED", unl)
notfound = [(r[0], r[4]) for r in res if r[3] and r[5] == 0]; print("LINKED-BUT-NO-ID-IN-SOURCE", notfound)
