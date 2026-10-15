"""package-lock.json 에서 CycloneDX 1.6 SBOM 을 직접 만든다(9단계 보강 도구).

왜 필요한가: @cyclonedx/cyclonedx-npm 6.0.1 은 설치된 트리(또는 --package-lock-only)를 기준으로 하기 때문에
  (a) 이 PC 에 설치되지 않는 플랫폼 선택 의존성(esbuild/rollup 의 다른 OS 바이너리 등)을 빼고,
  (b) --package-lock-only 에서는 같은 이름·다른 버전의 중첩 설치 12개를 합쳐 버린다(370 < 고유 382).
잠금 파일이 "빌드가 설치할 수 있는 전부"의 근거이므로, SBOM 은 잠금 파일 전체(고유 이름@버전)를 담아야 한다.

사용:  python3 web/tests_security/sbom_from_npm_lock.py web/frontend/package-lock.json 출력.json [--prod]
- 해시는 잠금의 integrity(sha512), 라이선스는 잠금의 license 필드, 의존 그래프는 node_modules 해석 규칙(가장 가까운 상위 node_modules)으로 만든다.
- 유지보수자 이메일 등 개인정보는 잠금 파일에 없으므로 담기지 않는다.
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.parse
import uuid
from datetime import datetime, timezone


def purl(name: str, version: str) -> str:
    if name.startswith("@"):
        scope, rest = name.split("/", 1)
        return f"pkg:npm/{urllib.parse.quote(scope, safe='')}/{rest}@{version}"
    return f"pkg:npm/{name}@{version}"


def build(lock: dict, prod_only: bool) -> dict:
    pk = lock["packages"]
    root = pk[""]

    def name_of(path: str) -> str:
        return pk[path].get("name") or path.split("node_modules/")[-1]

    def resolve(frm: str, dep: str) -> str | None:
        base = frm
        while True:
            cand = (base + "/" if base else "") + "node_modules/" + dep
            if cand in pk:
                return cand
            if not base:
                return None
            idx = base.rfind("/node_modules/")
            base = base[:idx] if idx >= 0 else ""

    reachable: set[str] = set()
    stack = [""]
    seen = {""}
    while stack:
        cur = stack.pop()
        meta = pk[cur]
        deps = dict(meta.get("dependencies", {}))
        deps.update(meta.get("optionalDependencies", {}))
        if cur == "":
            deps.update({} if prod_only else meta.get("devDependencies", {}))
        for d in deps:
            tgt = resolve(cur, d)
            if tgt and tgt not in seen:
                seen.add(tgt)
                stack.append(tgt)
    paths = [p for p in pk if p and (p in seen or not prod_only)]
    if prod_only:
        paths = [p for p in paths if p in seen]

    comps: dict[tuple[str, str], dict] = {}
    for p in paths:
        m = pk[p]
        n, v = name_of(p), m["version"]
        key = (n, v)
        if key in comps:
            continue
        c = {"type": "library", "bom-ref": purl(n, v), "name": n, "version": v, "purl": purl(n, v)}
        if "integrity" in m and m["integrity"].startswith("sha512-"):
            c["hashes"] = [{"alg": "SHA-512", "content": base64.b64decode(m["integrity"][7:]).hex()}]
        if m.get("license"):
            c["licenses"] = [{"expression": m["license"]} if any(t in m["license"] for t in (" OR ", " AND ", "(")) else {"license": {"id": m["license"]}}]
        props = []
        for flag in ("dev", "optional", "peer"):
            if m.get(flag):
                props.append({"name": f"npm:{flag}", "value": "true"})
        if m.get("hasInstallScript"):
            props.append({"name": "npm:hasInstallScript", "value": "true"})
        if props:
            c["properties"] = props
        comps[key] = c

    graph: dict[str, set[str]] = {}
    for p in paths:
        m = pk[p]
        ref = purl(name_of(p), m["version"])
        ds = graph.setdefault(ref, set())
        for d in {**m.get("dependencies", {}), **m.get("optionalDependencies", {})}:
            t = resolve(p, d)
            if t and (t in seen or not prod_only):
                ds.add(purl(name_of(t), pk[t]["version"]))
    deps_out = [{"ref": r, "dependsOn": sorted(s)} for r, s in sorted(graph.items())]
    return {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "serialNumber": "urn:uuid:" + str(uuid.uuid4()),
        "metadata": {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tools": {"components": [{"type": "application", "name": "sbom_from_npm_lock.py (web/tests_security)", "version": "1"}]},
            "component": {"type": "application", "name": root.get("name", "frontend"), "version": root.get("version", "0"), "bom-ref": "root"},
            "properties": [{"name": "scope", "value": "production-only" if prod_only else "all (dev+prod+optional, from package-lock.json)"}],
        },
        "components": sorted(comps.values(), key=lambda c: (c["name"], c["version"])),
        "dependencies": deps_out,
    }


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    lock = json.load(open(sys.argv[1], encoding="utf-8"))
    out = build(lock, "--prod" in sys.argv)
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{sys.argv[2]}: components={len(out['components'])} dependencies={len(out['dependencies'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
