"""7단계 통합 시험의 변이 점검기(원본 저장소는 수정하지 않는다).

격리 사본(.harness-tmp/int/mut/<id>/repo)에 변이를 적용 → 필요한 이미지만 다시 빌드(나머지는 원본 이미지를 태그만 복제) → 별도 compose 프로젝트로 기동
→ 지정한 통합 시험만 실행 → 실패하면 'killed', 전부 통과하면 'SURVIVED' → 프로젝트·이미지·사본 정리.
사용: python mutate.py --round 1 [--only M01,C02] [--slots 2]
필요 환경: env.sh(DOCKER_HOST, IT_PWSH …)를 source 한 셸. 결과: $IT_LOGDIR/mut_round<N>.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
INT = REPO / ".harness-tmp" / "int"
MUT = INT / "mut"
LOGS = Path(os.environ.get("IT_LOGDIR", INT / "logs"))
T = "web/tests_integration"
N1, N5 = f"{T}/test_it_01_nginx.py", f"{T}/test_it_05_ops.py"
N3 = f"{T}/test_it_03_state.py"
BASE_PFX = "harness-tmp-int"

# id, 설명, 파일(저장소 기준), 바꾸기 전, 바꾼 뒤, 다시 빌드할 이미지, 실행할 시험
M = [
 ("N01", "nginx Host 허용 목록을 기본 허용으로", "web/docker/nginx/nginx.conf", '        default 0;\n        "127.0.0.1:8080" 1;', '        default 1;\n        "127.0.0.1:8080" 1;', "web", [f"{N1}::test_it_010_host_not_allowed_gets_no_response"]),
 ("N02", "nginx 본문 상한 1m -> 64m", "web/docker/nginx/nginx.conf", "client_max_body_size 1m;", "client_max_body_size 64m;", "web", [f"{N1}::test_it_040_body_limits_nginx_layer_and_backend_layer"]),
 ("N03", "nginx 세션 발급 속도 10r/m -> 600r/m", "web/docker/nginx/nginx.conf", "rate=10r/m;", "rate=600r/m;", "web", [f"{N1}::test_it_050_rate_limits_two_layers_session_issue"]),
 ("N04", "nginx /api/ 일반 속도 제한 줄 삭제", "web/docker/nginx/nginx.conf", "        location /api/ {\n            limit_req zone=ytweb_api burst=60 nodelay;\n", "        location /api/ {\n", "web", [f"{N1}::test_it_051_rate_limit_api_general_and_write_limit"]),
 ("N05", "nginx 백엔드 CSP 숨김 제거(헤더 이중)", "web/docker/nginx/proxy.conf", "proxy_hide_header Content-Security-Policy;\n", "", "web", [f"{N1}::test_it_001_security_headers_exactly_one_set_everywhere"]),
 ("N06", "CSP 에서 frame-ancestors 삭제", "web/docker/nginx/security-headers.conf", "frame-ancestors 'none'; ", "", "web", [f"{N1}::test_it_001_security_headers_exactly_one_set_everywhere"]),
 ("N07", "index.html 캐시 no-cache -> 1시간 캐시", "web/docker/nginx/nginx.conf", 'add_header Cache-Control "no-cache" always;', 'add_header Cache-Control "public, max-age=3600" always;', "web", [f"{N1}::test_it_002_cache_and_compression_policy"]),
 ("N08", "정적 경로에 POST 허용", "web/docker/nginx/nginx.conf", "        location / {\n            limit_except GET HEAD { deny all; }", "        location / {\n            limit_except GET HEAD POST { deny all; }", "web", [f"{N1}::test_it_031_methods_allowed_by_location"]),
 ("N09", "server_tokens on(버전 노출)", "web/docker/nginx/nginx.conf", "server_tokens off;", "server_tokens on;", "web", [f"{N1}::test_it_001_security_headers_exactly_one_set_everywhere"]),
 ("N10", "nginx 헤더 수신 제한시간 10s -> 600s", "web/docker/nginx/nginx.conf", "client_header_timeout 10s;", "client_header_timeout 600s;", "web", [f"{N1}::test_it_041_malformed_content_length_and_slow_request_closed"]),
 ("N11", "속도 제한 거절 로그 수준 warn -> error(쿼리 기록)", "web/docker/nginx/nginx.conf", "limit_req_log_level warn;", "limit_req_log_level error;", "web", [f"{N5}::test_it_540_log_hygiene_query_strings_cookies_and_known_def_vi_003"]),
 ("N12", "백엔드로 Host 전달 변경($host: 포트 제거)", "web/docker/nginx/proxy.conf", "proxy_set_header Host $http_host;", "proxy_set_header Host $host;", "web", [f"{N1}::test_it_012_both_allowed_hosts_work_and_origin_must_match_host_family"]),
 ("N13", "nosniff 백엔드 값 숨김 제거", "web/docker/nginx/proxy.conf", "proxy_hide_header X-Content-Type-Options;\n", "", "web", [f"{N1}::test_it_001_security_headers_exactly_one_set_everywhere"]),
 ("N14", "/api/ 에 OPTIONS 메서드 허용", "web/docker/nginx/nginx.conf", "limit_except GET HEAD POST PUT PATCH DELETE { deny all; }", "limit_except GET HEAD POST PUT PATCH DELETE OPTIONS { deny all; }", "web", [f"{N1}::test_it_031_methods_allowed_by_location"]),
 ("N15", "nginx 오류 로그 수준 error -> info", "web/docker/nginx/nginx.conf", "error_log /dev/stderr error;", "error_log /dev/stderr info;", "web", [f"{N5}::test_it_540_log_hygiene_query_strings_cookies_and_known_def_vi_003"]),
 ("N16", "정적 경로 gzip 끔", "web/docker/nginx/nginx.conf", "            add_header Cache-Control \"public, max-age=31536000, immutable\" always;\n            gzip on;", "            add_header Cache-Control \"public, max-age=31536000, immutable\" always;\n            gzip off;", "web", [f"{N1}::test_it_002_cache_and_compression_policy"]),
 ("C01", "compose 읽기 전용 루트 해제", "web/compose.yaml", "  read_only: true\n", "  read_only: false\n", "", [f"{N5}::test_it_530_container_hardening_as_deployed"]),
 ("C02", "compose cap_drop ALL -> NET_RAW", "web/compose.yaml", "  cap_drop: [ALL]\n", "  cap_drop: [NET_RAW]\n", "", [f"{N5}::test_it_530_container_hardening_as_deployed"]),
 ("C03", "compose no-new-privileges 해제", "web/compose.yaml", 'security_opt: ["no-new-privileges:true"]', 'security_opt: ["no-new-privileges:false"]', "", [f"{N5}::test_it_530_container_hardening_as_deployed"]),
 ("C04", "web 을 back 망에도 연결(DEF-VI-001 회귀)", "web/compose.yaml", "      front: {}   # api 와만 통신(db 에는 도달하지 못한다, DEF-VI-001)\n      edge: {}", "      front: {}\n      back: {}\n      edge: {}", "", [f"{N5}::test_it_521_def_vi_001_network_split_effect_and_accepted_web_egress"]),
 ("C05", "back 망 internal 해제(외부 통신 가능)", "web/compose.yaml", "  back:\n    internal: true", "  back:\n    internal: false", "", [f"{N5}::test_it_520_demo_mode_api_worker_db_have_no_outbound_and_host_exposure_is_loopback_only"]),
 ("C06", "front 망 internal 해제(api 외부 통신 가능)", "web/compose.yaml", "  front:\n    internal: true", "  front:\n    internal: false", "", [f"{N5}::test_it_520_demo_mode_api_worker_db_have_no_outbound_and_host_exposure_is_loopback_only"]),
 ("C07", "worker 에 소유자 비밀번호 비밀 추가", "web/compose.yaml", '    command: ["python", "-m", "ytweb.worker"]\n    environment:\n      <<: *app-env\n      YTWEB_DB_USER: ytweb_app\n      YTWEB_DB_PASSWORD_FILE: /run/secrets/db_app_password\n    secrets:\n      - db_app_password', '    command: ["python", "-m", "ytweb.worker"]\n    environment:\n      <<: *app-env\n      YTWEB_DB_USER: ytweb_app\n      YTWEB_DB_PASSWORD_FILE: /run/secrets/db_app_password\n    secrets:\n      - db_app_password\n      - db_owner_password', "", [f"{N5}::test_it_510_secrets_not_in_logs_inspect_env_config_images_or_responses"]),
 ("C08", "api 를 root 로 실행", "web/compose.yaml", '    user: "10001:10001"\n    restart: unless-stopped\n    command:\n      - uvicorn', '    user: "0:0"\n    restart: unless-stopped\n    command:\n      - uvicorn', "", [f"{N5}::test_it_530_container_hardening_as_deployed"]),
 ("C09", "API 문서 켬(YTWEB_ENABLE_DOCS=1)", "web/compose.yaml", 'YTWEB_ENABLE_DOCS: "0"', 'YTWEB_ENABLE_DOCS: "1"', "", [f"{N1}::test_it_003_no_docs_no_openapi_no_dotfiles"]),
 ("C10", "백엔드 허용 Host 에 evil.example:8080 추가", "web/compose.yaml", 'YTWEB_ALLOWED_HOSTS: "127.0.0.1:8080,localhost:8080"', 'YTWEB_ALLOWED_HOSTS: "127.0.0.1:8080,localhost:8080,evil.example:8080"', "", [f"{N1}::test_it_013_backend_host_guard_independent_of_nginx"]),
 ("C11", "web 포트를 모든 인터페이스에 게시", "STACK:compose.yaml", '"127.0.0.1:{PORT}:8080"', '"{PORT}:8080"', "", [f"{N5}::test_it_520_demo_mode_api_worker_db_have_no_outbound_and_host_exposure_is_loopback_only"]),
 ("C12", "DB 비밀번호 암호화 md5", "web/compose.yaml", "      - password_encryption=scram-sha-256", "      - password_encryption=md5", "", [f"{N5}::test_it_531_db_roles_and_grants_as_deployed"]),
 ("C13", "uvicorn 접근 로그 켬(--no-access-log 제거)", "web/compose.yaml", "      - --no-access-log\n", "", "", [f"{N5}::test_it_540_log_hygiene_query_strings_cookies_and_known_def_vi_003"]),
 ("C14", "db 메모리 상한 768M -> 1024M", "web/compose.yaml", 'memory: 768M', 'memory: 1024M', "", [f"{N5}::test_it_530_container_hardening_as_deployed"]),
 ("D01", "마이그레이션 0002 REVOKE 제거", "web/backend/alembic/versions/0002_revoke_alembic_version_dml.py", "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON alembic_version FROM ytweb_app;", "PERFORM 1;", "api", [f"{N5}::test_it_522_def_vi_002_app_role_cannot_modify_alembic_version", f"{N5}::test_it_503_migration_0001_to_0002_on_deployed_db_revokes_app_dml_and_is_reversible"]),
 ("D02", "복원 후 audit_log 권한 재회수 SQL 제거", "web/docker/db/audit-guard.sql", "        REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.audit_log FROM ytweb_app;\n", "", "db", [f"{N5}::test_it_500_backup_restore_roundtrip_with_safety_backup_and_audit_guard"]),
 ("D03", "pg_hba 마지막 규칙 reject -> trust", "web/docker/db/pg_hba.conf", "host    all       all                         all             reject", "host    all       all                         all             trust", "db", [f"{N5}::test_it_531_db_roles_and_grants_as_deployed"]),
 ("D04", "ytweb-db restore 가 audit-guard 를 실행하지 않음", "web/docker/db/bin/ytweb-db", '    owner_psql -q -f "$SHARE_DIR/audit-guard.sql"\n', "", "db", [f"{N5}::test_it_500_backup_restore_roundtrip_with_safety_backup_and_audit_guard"]),
 ("D05", "초기화(schema-grants) 가 public 의 PUBLIC 권한을 회수하지 않음", "web/docker/db/schema-grants.sql", "REVOKE ALL ON SCHEMA public FROM PUBLIC;\n", "", "db", [f"{N5}::test_it_531_db_roles_and_grants_as_deployed", f"{N5}::test_it_501_reset_demo_confirmation_phrases_and_auto_backup_and_delete_volumes"]),
 ("B01", "응답 전 commit 제거(DEF-VA-010 회귀)", "web/backend/ytweb/core/guard.py", "                    await anyio.to_thread.run_sync(db_session.commit)", "                    pass", "api", [N3, "-k", "it_300 or it_301 or it_316"]),
 ("B02", "백엔드 Host 허용 목록 검사 제거", "web/backend/ytweb/core/guard.py", "len(host_values) != 1 or host_values[0] not in self.allowed", "len(host_values) != 1", "api", [f"{N1}::test_it_013_backend_host_guard_independent_of_nginx"]),
 ("B03", "백엔드 Content-Length 상한 검사 제거", "web/backend/ytweb/core/guard.py", "too_big = int(cl) > self.max_body", "too_big = False", "api", [f"{N1}::test_it_040_body_limits_nginx_layer_and_backend_layer"]),
 ("B04", "세션 쿠키 SameSite Strict -> Lax", "web/backend/ytweb/routers/auth.py", 'path=COOKIE_PATH, httponly=True, samesite="strict", secure=False)\n', 'path=COOKIE_PATH, httponly=True, samesite="lax", secure=False)\n', "api", [f"{N1}::test_it_020_cookie_attributes_and_scope_over_plain_http"]),
 ("B05", "CSRF 토큰 검사 제거", "web/backend/ytweb/core/deps.py", "    if not x_csrf_token or not hmac.compare_digest(x_csrf_token.encode(), info.csrf_token.encode()):", "    if False:", "api", [f"{N1}::test_it_022_csrf_and_missing_origin_and_get_cannot_mutate"]),
 ("S01", "restore.ps1 복원 전 자동 백업 건너뜀", "web/scripts/restore.ps1", "if (-not $SkipSafetyBackup) {", "if ($false) {", "", [f"{N5}::test_it_500_backup_restore_roundtrip_with_safety_backup_and_audit_guard"]),
 ("S02", "restore.ps1 확인 문구 불일치에도 계속", "web/scripts/restore.ps1", "    exit 2\n}\n\nif (-not $SkipSafetyBackup) {", "    # exit 2\n}\n\nif (-not $SkipSafetyBackup) {", "", [f"{N5}::test_it_500_backup_restore_roundtrip_with_safety_backup_and_audit_guard"]),
 ("S03", "backup.ps1 SHA-256 기록값 오염", "web/scripts/backup.ps1", '$hash = (Get-FileHash -LiteralPath $hostFile -Algorithm SHA256).Hash.ToLower()', '$hash = (Get-FileHash -LiteralPath $hostFile -Algorithm SHA256).Hash.ToLower().Replace("a","b")', "", [f"{N5}::test_it_500_backup_restore_roundtrip_with_safety_backup_and_audit_guard"]),
 ("S04", "reset-demo.ps1 초기화 전 자동 백업 생략", "web/scripts/reset-demo.ps1", "        & (Join-Path $PSScriptRoot 'backup.ps1') -Prefix 'pre-reset'\n", "        Write-Info 'skip'\n", "", [f"{N5}::test_it_501_reset_demo_confirmation_phrases_and_auto_backup_and_delete_volumes"]),
]
MAP = {m[0]: m for m in M}
LOCK = threading.Lock()


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def log(msg):
    with LOCK:
        print(time.strftime("%H:%M:%S"), msg, flush=True)


def copy_repo(dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    ign = shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", "tests_integration", "tests_infra", "dist")
    for rel in ("web", "src/ytitle", "config"):
        shutil.copytree(REPO / rel, dst / rel, ignore=ign)
    shutil.copy2(REPO / ".dockerignore", dst / ".dockerignore") if (REPO / ".dockerignore").exists() else None


def one(mid: str, slot: int, rnd: int) -> dict:
    _, desc, rel, old, new, build, tests = MAP[mid]
    project = f"harness-tmp-intm{slot}"
    port = 18080       # 허용된 호스트 게시 포트는 18080 하나뿐이다: 변이 스택은 주 스택을 내린 뒤 하나씩(직렬) 이 포트로 띄운다
    work = MUT / f"{mid}_r{rnd}"
    repo = work / "repo"
    t0 = time.time()
    res = {"id": mid, "desc": desc, "round": rnd, "tests": tests, "status": "", "detail": ""}
    env = {**os.environ, "YTWEB_IMAGE_PREFIX": project}
    stack = work / "stack" / "web"

    def cleanup():
        run(["docker", "compose", "-p", project, "-f", str(stack / "compose.yaml"), "down", "-v", "--remove-orphans", "-t", "5"], env=env, timeout=240)
        for n in ("api", "web", "db"):
            run(["docker", "rmi", "-f", f"{project}-{n}:local"])
        shutil.rmtree(work, ignore_errors=True)

    try:
        copy_repo(repo)
        stack_edit = rel.startswith("STACK:")
        if not stack_edit:
            f = repo / rel
            txt = f.read_text(encoding="utf-8")
            if txt.count(old) != 1:
                res.update(status="INVALID", detail=f"변이 대상 문자열이 {txt.count(old)}곳")
                return res
            f.write_text(txt.replace(old, new), encoding="utf-8")
        # 이미지: 바뀐 것만 새로 빌드, 나머지는 원본 이미지 복제 태그
        for n in ("api", "web", "db"):
            if n not in build.split():
                run(["docker", "tag", f"{BASE_PFX}-{n}:local", f"{project}-{n}:local"], check=True)
        if build:
            p = run(["bash", str(REPO / "web/tests_integration/tools/mkimages.sh"), str(repo), str(work / "build"), project, build], timeout=1500)
            if p.returncode != 0:
                res.update(status="INVALID", detail="이미지 빌드 실패: " + (p.stderr or p.stdout)[-300:])
                return res
        p = run(["bash", str(REPO / "web/tests_integration/tools/mkstack.sh"), str(repo / "web"), str(stack), str(port)])
        if p.returncode != 0:
            res.update(status="INVALID", detail="mkstack: " + p.stderr[-300:])
            return res
        if stack_edit:
            f = stack / rel.split(":", 1)[1]
            o, n_ = old.replace("{PORT}", str(port)), new.replace("{PORT}", str(port))
            txt = f.read_text(encoding="utf-8")
            if txt.count(o) != 1:
                res.update(status="INVALID", detail=f"변이 대상 문자열이 {txt.count(o)}곳")
                return res
            f.write_text(txt.replace(o, n_), encoding="utf-8")
        up = run(["docker", "compose", "-p", project, "-f", str(stack / "compose.yaml"), "up", "-d", "--no-build"], env=env, timeout=600)
        res["up_rc"] = up.returncode
        tenv = {**os.environ, "IT_PROJECT": project, "IT_PORT": str(port), "IT_STACK_DIR": str(stack), "IT_LOGDIR": str(work)}
        pr = run([sys.executable, "-m", "pytest", *tests, "-x", "-q", "-p", "no:cacheprovider", "--no-header"], env=tenv, cwd=str(REPO), timeout=1500)
        out = pr.stdout + pr.stderr
        (LOGS / f"mut_{mid}_r{rnd}.log").write_text(out[-6000:], encoding="utf-8")
        if pr.returncode == 0:
            res["status"] = "SURVIVED"
            res["detail"] = out.strip().splitlines()[-1][:200] if out.strip() else ""
        else:
            failed = re.findall(r"^(?:FAILED|ERROR) (\S+)", out, re.M)
            res["status"] = "killed"
            res["detail"] = ("기동 실패(up rc=%s) · " % up.returncode if up.returncode else "") + (failed[0].split("::")[-1] if failed else out.strip().splitlines()[-1][:160])
            if pr.returncode in (3, 4, 5) or "스택이 준비되지" in out:
                res["detail"] += " [스택 기동/수집 오류: 기동 시험으로 간주]"
    except Exception as e:  # noqa: BLE001
        res.update(status="INVALID", detail=repr(e)[:300])
    finally:
        cleanup()
        res["sec"] = round(time.time() - t0)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--slots", type=int, default=1)
    a = ap.parse_args()
    ids = [i for i in (a.only.split(",") if a.only else [m[0] for m in M]) if i]
    MUT.mkdir(parents=True, exist_ok=True)
    out = LOGS / f"mut_round{a.round}.json"
    results: list[dict] = json.loads(out.read_text()) if (out.exists() and a.only) else []
    done = {r["id"] for r in results}
    ids = [i for i in ids if i not in done]
    assert a.slots == 1, "호스트 포트가 18080 하나뿐이므로 변이 스택은 직렬로만 돈다"
    free = list(range(1, a.slots + 1))
    lk = threading.Lock()

    def job(mid):
        with lk:
            slot = free.pop(0)
        try:
            log(f"start {mid} slot{slot}")
            r = one(mid, slot, a.round)
            log(f"{mid} -> {r['status']} {r['detail'][:90]} ({r['sec']}s)")
            with LOCK:
                results.append(r)
                out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
            return r
        finally:
            with lk:
                free.append(slot)

    with ThreadPoolExecutor(max_workers=a.slots) as ex:
        list(ex.map(job, ids))
    c = {}
    for r in results:
        c[r["status"]] = c.get(r["status"], 0) + 1
    log(f"round {a.round}: {c}")


if __name__ == "__main__":
    main()
