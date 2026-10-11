"""보안 시험이 정말 보안 통제를 잡아내는지 확인하는 변이 점검(원본 소스는 건드리지 않는다).

사용:  <venv>/bin/python web/tests_security/mutation_check.py [--only N,M] [--out 결과.json]
- 원본 web/backend/ytweb 와 src/youtube_title 를 .harness-tmp/sec/mut/<번호>/ 로 복사한 뒤 한 곳만 고치고,
  YTWEB_SEC_BACKEND_DIR/YTWEB_SEC_SRC_DIR 로 그 사본을 가리켜 오프라인 시험(01·02)을 돌린다.
- 시험이 하나라도 실패하면 killed(잡음), 모두 통과하면 survived(놓침, 시험 보강 또는 동치 변이 근거 필요).
- 대상 문자열은 원본 소스에 정확히 1곳이어야 한다(아니면 오류로 중단).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".harness-tmp" / "sec" / "mut"
S1 = "web/tests_security/test_sec_01_http_boundary.py"
S2 = "web/tests_security/test_sec_02_injection_ai_integrity.py"
S7 = "web/tests_security/test_sec_07_fix_regressions.py"
SUITES = [S1, S2, S7]
# 먼저 돌릴 시험 파일(빨리 잡히게). 못 잡으면 둘 다 돌려 최종 판정한다.
HINT = {"core/deps.py": [S1], "core/guard.py": [S1], "routers/auth.py": [S1], "core/sessions.py": [S1], "core/pin.py": [S1], "routers/settings.py": [S1, S2], "core/ratelimit.py": [S1], "app.py": [S1]}

# (id, 위협, 파일(web/backend/ytweb 기준 또는 src/youtube_title), 원문, 변이, 설명)
M = [
    ("core/deps.py", "if origin is None or origin.strip().lower() not in allowed_origins(settings):", "if False:", "TW-01", "Origin 검증 제거"),
    ("core/deps.py", 'if sec is not None and sec.strip().lower() != "same-origin":', "if False:", "TW-01", "Sec-Fetch-Site 검증 제거"),
    ("core/deps.py", "if not x_csrf_token or not hmac.compare_digest(x_csrf_token.encode(), info.csrf_token.encode()):", "if False:", "TW-01", "CSRF 토큰 검증 제거"),
    ("core/deps.py", "if not x_csrf_token or not hmac.compare_digest(x_csrf_token.encode(), info.csrf_token.encode()):", "if not x_csrf_token:", "TW-01", "CSRF 토큰 값 비교 제거(존재만 확인)"),
    ("core/guard.py", "(len(host_values) != 1 or host_values[0] not in self.allowed)", "False", "TW-02", "Host 허용 목록 검증 제거"),
    ("core/guard.py", "(len(host_values) != 1 or host_values[0] not in self.allowed)", "(host_values[0] not in self.allowed)", "TW-02", "중복 Host 헤더 허용"),
    ("core/guard.py", "if len(cl_values) != 1 or not (cl.isascii() and cl.isdigit()):", "if False:", "TW-25", "Content-Length 형식 검증 제거"),
    ("core/guard.py", "MAX_BODY_BYTES = 1024 * 1024", "MAX_BODY_BYTES = 1024 * 1024 * 1024", "TW-25", "본문 크기 상한 확대"),
    ("core/guard.py", "if received > self.max_body:", "if False:", "TW-25", "chunked 본문 계수 제거"),
    ("core/guard.py", '"x-frame-options": "DENY",', '"x-frame-options": "SAMEORIGIN",', "TW-23", "X-Frame-Options 완화"),
    ("core/guard.py", 'h["cache-control"] = "no-store"', 'h["cache-control"] = "public"', "TW-23", "API 캐시 허용"),
    ("core/canonical.py", '"""해시 입력용 정규 JSON(키 정렬·공백 없음·비ASCII 그대로)."""', '"""해시 입력용 정규 JSON."""', "-", "독스트링만 변경(동치 대조군)"),
    ("routers/auth.py", "path=COOKIE_PATH, httponly=True, samesite=\"strict\", secure=False)", "path=COOKIE_PATH, httponly=False, samesite=\"strict\", secure=False)", "TW-20", "쿠키 HttpOnly 제거"),
    ("routers/auth.py", "path=COOKIE_PATH, httponly=True, samesite=\"strict\", secure=False)", "path=COOKIE_PATH, httponly=True, samesite=\"lax\", secure=False)", "TW-01", "쿠키 SameSite 완화"),
    ("core/sessions.py", "token = secrets.token_urlsafe(32)", "token = secrets.token_urlsafe(2)", "TW-20", "세션 토큰 엔트로피 축소"),
    ("core/sessions.py", "id=hash_token(token), csrf_token=csrf", "id=token, csrf_token=csrf", "TW-20", "세션 토큰 평문 저장"),
    ("core/sessions.py", "if row.expires_at <= now or (idle_timeout is not None and row.last_seen + idle_timeout <= now):", "if False:", "TW-20", "세션 만료 검사 제거"),
    ("core/sessions.py", "for old in active[MAX_ACTIVE_SESSIONS - 1:]:", "for old in []:", "TW-20", "세션 개수 상한 제거"),
    ("core/pin.py", "MAX_FAILURES = 5", "MAX_FAILURES = 500", "TW-04", "PIN 잠금 임계 확대"),
    ("core/pin.py", "return hmac.compare_digest(actual, expected)", "return True", "TW-04", "PIN 비교 무력화"),
    ("core/pin.py", "MAX_LOCK = timedelta(hours=1)", "MAX_LOCK = timedelta(hours=100)", "TW-04", "PIN 잠금 상한 확대"),
    ("core/pin.py", "BASE_LOCK * (2 ** st[\"lockouts\"])", "BASE_LOCK", "TW-04", "PIN 잠금 시간 배증 제거"),
    ("core/pin.py", "_PIN_RE = re.compile(r\"[0-9]{4,12}\")", "_PIN_RE = re.compile(r\".*\")", "TW-04", "PIN 형식 검증 제거"),
    ("routers/settings.py", 'ALLOWED_KEYS = frozenset({"daily_apply_cap", "suggestions_per_video", "tone", "pin"})', 'ALLOWED_KEYS = frozenset({"daily_apply_cap", "suggestions_per_video", "tone", "pin", "enable_live"})', "TW-33", "설정 허용 키에 enable_live 추가"),
    ("routers/settings.py", "delete_other_sessions(db, info.session_id)", "pass", "TW-20", "PIN 변경 시 다른 세션 폐기 제거"),
    ("routers/settings.py", 'if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:', 'if not lo <= value <= hi:', "TW-33", "정수 검증 약화(불리언·타입)"),
    ("core/ratelimit.py", 'if method == "POST" and path.rstrip("/") == "/api/v1/auth/session":', "if False:", "TW-25", "세션 발급 속도 제한 제거"),
    ("core/ratelimit.py", "wait = self._f.peek()", "wait = 0", "TW-25", "교차 출처 요청 별도 한도 제거"),
    ("core/logsetup.py", "return _LONG_TOKEN_RE.sub(MASK, text)", "return text", "TW-17", "긴 토큰 마스킹 제거"),
    ("core/logsetup.py", "token|pin|api[-_]?key", "token|api[-_]?key", "TW-17", "pin 키 마스킹 제거"),
    ("core/logsetup.py", "text = _URL_CRED_RE.sub(f\"{MASK}:{MASK}@\", text)", "pass", "TW-17", "URL 자격증명 마스킹 제거"),
    ("app.py", "e.get('msg', '')}", "e.get('msg', '')} {e.get('input', '')}", "TW-17", "422 오류에 입력값 에코"),
    ("app.py", 'openapi_url="/openapi.json" if settings.enable_docs else None', 'openapi_url="/openapi.json"', "TW-34", "/openapi.json 상시 노출"),
    ("app.py", "if full_path and target.is_file() and (root == target.parent or root in target.parents):", "if full_path and target.is_file():", "경로 순회", "정적 파일 경로 포함 검사 제거"),
    ("domain/reports.py", '_FORMULA_START = ("=", "+", "-", "@", "\\t", "\\r")', '_FORMULA_START = ("=", "+", "@")', "TW-10", "CSV 수식 접두 일부 제거"),
    ("domain/reports.py", "writer.writerow([csv_safe(v) for v in row])", "writer.writerow(row)", "TW-10", "CSV 셀 무독화 제거"),
    ("domain/reports.py", "writer.writerow([csv_safe(note)])", "writer.writerow([note])", "TW-10", "CSV 주석 행 무독화 제거"),
    ("ai/guard.py", "elif has_contact_or_url(title):", "elif False:", "LLM05", "AI 출력의 링크·연락처 제거 삭제"),
    ("ai/guard.py", 'text = _URL.sub("[링크]", text)', "text = text", "LLM02", "AI 입력 링크 마스킹 제거"),
    ("ai/guard.py", "text = _EMAIL.sub(\"[이메일]\", text)", "text = text", "LLM02", "AI 입력 이메일 마스킹 제거"),
    ("ai/guard.py", "elif len(title) > MAX_TITLE_CHARS:", "elif False:", "LLM10", "AI 출력 길이 상한 제거"),
    ("ai/guard.py", "topic = parts[2] if isinstance(parts[2], str) and parts[2] in TOPICS else None", "topic = parts[2]", "LLM05", "AI topic 화이트리스트 제거"),
    ("domain/suggestions.py", "if not hmac.compare_digest(expected, ap.mac):", "if False:", "TW-07", "승인 HMAC 검증 제거"),
    ("domain/suggestions.py", "if ap.used_at is not None:", "if False:", "TW-07", "승인 1회용 검사 제거"),
    ("domain/suggestions.py", "if sug.plan_hash != ap.plan_hash or plan_hash_for(sug, video, snap) != ap.plan_hash:", "if False:", "TW-07", "계획 해시 일치 검사 제거"),
    ("domain/suggestions.py", "if ref_time >= ap.expires_at:", "if False:", "TW-07", "승인 만료 검사 제거"),
    ("domain/suggestions.py", "fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)", "fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)", "TW-07", "HMAC 키 파일 권한 완화"),
    ("domain/suggestions.py", "invalidated = _drop_approval(session, sug)\n    old = sug.title", "invalidated = False\n    old = sug.title", "TW-07", "제목 수정 시 승인 무효화 제거"),
    ("core/audit.py", "if row.hash != expected:", "if False:", "TW-08", "감사 해시 재계산 검증 제거"),
    ("core/audit.py", "if row.prev_hash != prev:", "if False:", "TW-08", "감사 체인 연결 검증 제거"),
    ("core/idempotency.py", "if row.route != route or row.request_hash != request_hash:", "if False:", "TW-06", "멱등키 재사용 검증 제거"),
    ("core/idempotency.py", '_KEY_RE = re.compile(r"[A-Za-z0-9._:\\-]{8,80}")', '_KEY_RE = re.compile(r".*", re.S)', "TW-06", "멱등키 형식 검증 제거"),
    ("domain/common.py", "or sanitize_for_display(name) != name", "", "TW-16", "승인자 이름 제어문자 검사 제거"),
    ("domain/changes.py", "if typed_video_id != target.video_id:", "if False:", "롤백", "롤백 영상 ID 재입력 확인 제거"),
    ("domain/changes.py", "if later is not None:", "if False:", "롤백", "롤백 후속 변경 검사 제거"),
    ("domain/batches.py", "if confirm_text != expected:", "if False:", "TW-14", "배치 실행 확인 문구 검사 제거"),
    ("config.py", 'MODES = ("demo",)', 'MODES = ("demo", "live")', "TW-33", "live 모드 허용"),
    ("ai/factory.py", 'if mode != "demo":', "if False:", "TW-33", "AI 팩토리 모드 검사 제거"),
    # ── 2회전에서 추가한 변이(1회전 생존분 보강 + 새 영역) ──
    ("core/pin.py", "set_web_setting(db, FAIL_KEY, st, now=now)\n    db.commit()", "set_web_setting(db, FAIL_KEY, st, now=now)", "TW-04", "PIN 실패 기록 commit 제거(롤백되어 잠금 누적 안 됨)"),
    ("core/guard.py", 'if scope["type"] == "websocket":', "if False:", "TW-34", "웹소켓 거부 제거"),
    ("routers/auth.py", "delete_session(db, info.session_id)\n    audit.record(db, actor=\"owner\", action=\"session.delete\"", "audit.record(db, actor=\"owner\", action=\"session.delete\"", "TW-20", "로그아웃 시 서버 세션 삭제 제거"),
    ("core/sessions.py", "where(SessionRow.id != keep_id)", "where(SessionRow.id == keep_id)", "TW-20", "다른 세션 폐기 조건 반전"),
    ("core/idempotency.py", "request_hash = sha256_hex(canonical_json(jsonable_encoder(request)))", 'request_hash = "x"', "TW-06", "멱등키 요청 해시 상수화"),
    ("ai/guard.py", "return _PHONE.sub(\"[전화번호]\", text)", "return text", "LLM02", "AI 입력 전화번호 마스킹 제거"),
    ("ai/guard.py", "text = _RRN.sub(\"[번호]\", text)", "text = text", "LLM02", "AI 입력 주민번호 마스킹 제거"),
    ("ai/guard.py", 'elif ch in _BIDI or ch in _INVISIBLE or unicodedata.category(ch) == "Cc":', "elif False:", "LLM05", "AI/사용자 문자열 제어·방향·비가시 문자 제거 삭제"),
    ("domain/suggestions.py", "title = clean_text(new_title)", "title = new_title", "TW-11", "제목 수정 시 문자 정제 제거"),
    ("domain/suggestions.py", "if sug.status not in EDITABLE:", "if False:", "TW-07", "제목 수정 가능 상태 검사 제거"),
    ("domain/batches.py", 'if sug.status != "approved":\n        return "not_approved"', 'if False:\n        return "not_approved"', "TW-07", "배치 적격성: 승인 상태 검사 제거"),
    ("domain/batches.py", "if len(suggestion_ids) > MAX_BATCH_ITEMS:", "if False:", "TW-06", "배치 50건 상한 제거"),
    ("routers/settings.py", "if not 1 <= len(item) <= TONE_MAX_CHARS or any(ord(c) < 32 for c in item):", "if False:", "LLM01", "말투 설정 제어문자·길이 검사 제거"),
    ("routers/settings.py", "if not isinstance(value, list) or len(value) > TONE_MAX_ITEMS:", "if not isinstance(value, list):", "LLM01", "말투 항목 수 상한 제거"),
    ("core/logsetup.py", "text = _SQL_PARAMS_RE.sub(f\"[parameters: {MASK}]\", text)", "pass", "TW-17", "SQL 바인딩 값 마스킹 제거"),
    ("core/logsetup.py", "if _SENSITIVE_FIELD.search(key):", "if False:", "TW-17", "로그 extra 민감 키 마스킹 제거"),
    # ── 개정 2판(2026-10-11): W-FIX-BE/FE/INF 가 만든 새 통제에 대한 변이 ──
    ("core/sessions.py", " or (idle_timeout is not None and row.last_seen + idle_timeout <= now)", "", "TW-20", "[R2] 세션 유휴 만료 검사 제거(lookup)"),
    ("core/sessions.py", "cond = or_(cond, SessionRow.last_seen <= now - idle_timeout)", "pass", "TW-20", "[R2] 유휴 세션 정리(purge) 제거"),
    ("core/deps.py", "now=clock(), idle_timeout=request.app.state.web_settings.session_idle_timeout)\n    if info is None:", "now=clock())\n    if info is None:", "TW-20", "[R2] require_session 에서 유휴 만료 인자 제거"),
    ("routers/auth.py", "now=clock(), idle_timeout=request.app.state.web_settings.session_idle_timeout)\n    return {\"authenticated\"", "now=clock())\n    return {\"authenticated\"", "TW-20", "[R2] /auth/me 에서 유휴 만료 인자 제거"),
    ("config.py", 'session_idle_minutes=_non_negative_int(e, "YTWEB_SESSION_IDLE_MINUTES", 30)', 'session_idle_minutes=_non_negative_int(e, "YTWEB_SESSION_IDLE_MINUTES", 0)', "TW-20", "[R2] 유휴 만료 기본값 30분 -> 꺼짐"),
    ("config.py", "    if value < 0:\n        raise ValueError", "    if False:\n        raise ValueError", "TW-20", "[R2] 유휴 설정 음수 거부 제거"),
    ("domain/common.py", ' or any(unicodedata.category(ch) in ("Cf", "Zl", "Zp") for ch in name)', "", "TW-16", "[R2] 승인자 이름 서식 문자(Cf/Zl/Zp) 거부 제거"),
    ("domain/schemas.py", "MAX_ID = 2**63 - 1", "MAX_ID = 2**80", "S-W13", "[R2] ID 상한 확대"),
    ("domain/schemas.py", "MAX_PAGE = 1_000_000", "MAX_PAGE = 10**30", "S-W13", "[R2] 쪽 번호 상한 확대"),
    ("domain/schemas.py", "suggestion_ids: list[Annotated[int, Field(ge=1, le=MAX_ID)]]", "suggestion_ids: list[int]", "S-W13", "[R2] 배치 제안 ID 항목 범위 제거"),
    ("routers/batches.py", "def post_cancel(batch_id: int = Path(ge=1, le=MAX_ID)", "def post_cancel(batch_id: int = Path(ge=1)", "S-W13", "[R2] cancel 경로 ID 상한 제거"),
    ("routers/batches.py", "env: Env = Depends(get_env), _=Depends(require_csrf)):\n    batch = cancel_batch(", "env: Env = Depends(get_env)):\n    batch = cancel_batch(", "TW-01", "[R2] 초안 버리기(cancel) CSRF·세션 의존 제거"),
    ("domain/batches.py", 'if batch.status in ("cancelled", "done"):', "if False:", "TW-06", "[R2] 취소/완료 배치 재취소 거부 제거"),
    ("domain/batches.py", '"notice": DISCLAIMER,', '"notice": None,', "POL-002", "[R2] 사전 점검 notice 제거"),
    ("domain/reports.py", '"notes": [DISCLAIMER, LIMIT_NOTE,', '"notes": [LIMIT_NOTE,', "POL-002", "[R2] 리포트·CSV 면책 주석 제거"),
    ("domain/notices.py", 'DISCLAIMER = "이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다."', 'DISCLAIMER = "이 검증은 정확합니다."', "POL-002", "[R2] 면책 문구 내용 변경"),
    ("core/jobs.py", "stmt = stmt.with_for_update(skip_locked=True)\n    requeued = failed = 0", "pass\n    requeued = failed = 0", "TW-06", "[R2] stale 재큐의 SKIP LOCKED 제거"),
    ("core/jobs.py", "if job.locked_at is not None and job.locked_at >= now - limit(job.type):\n            continue", "if False:\n            continue", "TW-06", "[R2] 작업 유형별 stale 기준 검사 제거"),
    ("core/jobs.py", "if job.attempts >= MAX_ATTEMPTS:\n            job.status, job.error, job.finished_at = \"failed\"", "if False:\n            job.status, job.error, job.finished_at = \"failed\"", "TW-06", "[R2] 재큐 시도 횟수 상한 제거"),
    ("worker.py", "purge_expired(s, now=now, idle_timeout=self.session_idle_timeout)", "purge_expired(s, now=now)", "TW-20", "[R2] 워커 정비의 유휴 세션 정리 제거"),
]
# 대조군(동치 변이)은 맨 위의 한 줄뿐이다. 사람이 읽기 쉽게 표시한다.

# ── 인프라·설정 변이(test_sec_03 만 돌린다. YTWEB_SEC_ROOT 로 복사본을 가리킨다). old=="" 이면 파일 끝에 new 를 덧붙인다 ──
MC = [
    ("web/compose.yaml", "  read_only: true\n  cap_drop", "  read_only: false\n  cap_drop", "TW-31", "모든 서비스 읽기 전용 루트 해제"),
    ("web/compose.yaml", "cap_drop: [ALL]", "cap_drop: []", "TW-31", "capability 제거 해제"),
    ("web/compose.yaml", 'security_opt: ["no-new-privileges:true"]', "security_opt: []", "TW-31", "no-new-privileges 제거"),
    ("web/compose.yaml", '- "127.0.0.1:8080:8080"', '- "0.0.0.0:8080:8080"', "S-W01", "게시 포트를 모든 인터페이스로"),
    ("web/compose.yaml", "  front:\n    internal: true", "  front:\n    internal: false", "TW-21", "front 망 internal 해제"),
    ("web/compose.yaml", "  back:\n    internal: true", "  back:\n    internal: false", "TW-21", "back 망 internal 해제"),
    ("web/compose.yaml", "      edge: {}    # 호스트 포트 게시용(유일한 비-internal 망)", "      edge: {}\n      back: {}", "TW-21", "web 을 back 망(db)에 연결"),
    ("web/compose.yaml", 'user: "101:101"', 'user: "0:0"', "TW-31", "web 컨테이너 루트 실행"),
    ("web/compose.yaml", 'YTWEB_ENABLE_DOCS: "0"', 'YTWEB_ENABLE_DOCS: "1"', "TW-34", "/docs 켬"),
    ("web/compose.yaml", "      - log_statement=none", "      - log_statement=all", "TW-17", "DB 문장 로그 전체 기록"),
    ("web/compose.yaml", "POSTGRES_PASSWORD_FILE: /run/secrets/db_superuser_password", "POSTGRES_PASSWORD: hunter2hunter2hunter2", "TW-18", "DB 비밀번호 평문 환경변수"),
    ("web/compose.yaml", "    ports:\n      - \"127.0.0.1:8080:8080\"", "    ports:\n      - \"127.0.0.1:8080:8080\"\n      - \"5432:5432\"", "TW-21", "DB 포트 게시 추가(web 서비스에 잘못 추가해도 목록 검사에 걸림)"),
    ("web/compose.online.yaml", "  worker:\n    networks:\n      egress: {}", "  worker:\n    networks:\n      egress: {}\n  db:\n    networks:\n      egress: {}", "TW-21", "online 덧씌우기에서 db 를 egress 에 연결"),
    ("web/docker/nginx/nginx.conf", "return 444;", "return 200;", "TW-02", "허용되지 않은 Host 처리 제거"),
    ("web/docker/nginx/nginx.conf", "client_max_body_size 1m;", "client_max_body_size 10g;", "TW-25", "본문 크기 상한 확대"),
    ("web/docker/nginx/nginx.conf", "server_tokens off;", "server_tokens on;", "TW-17", "nginx 버전 노출"),
    ("web/docker/nginx/nginx.conf", "        location /assets/ {\n            limit_except GET HEAD { deny all; }\n            include /etc/nginx/snippets/security-headers.conf;", "        location /assets/ {\n            limit_except GET HEAD { deny all; }", "TW-23", "assets location 보안 헤더 include 제거"),
    ("web/docker/nginx/nginx.conf", "set $api_upstream http://api:8000;\n            proxy_pass $api_upstream/healthz;", "proxy_pass http://$arg_target/healthz;", "TW-35", "업스트림을 요청 쿼리로 결정(SSRF)"),
    ("web/docker/nginx/security-headers.conf", 'X-Frame-Options "DENY"', 'X-Frame-Options "SAMEORIGIN"', "TW-23", "X-Frame-Options 완화"),
    ("web/docker/nginx/security-headers.conf", "script-src 'self';", "script-src 'self' 'unsafe-inline';", "TW-11", "CSP 인라인 스크립트 허용"),
    ("web/docker/nginx/security-headers.conf", "frame-ancestors 'none';", "frame-ancestors *;", "TW-23", "CSP frame-ancestors 완화"),
    ("web/docker/db/pg_hba.conf", "host    all       all                         all             reject", "host    all       all                         all             trust", "TW-21", "pg_hba 기본 거부를 trust 로"),
    ("web/docker/db/schema-grants.sql", "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ytweb_app;", "GRANT ALL PRIVILEGES ON TABLES TO ytweb_app;", "TW-32", "앱 계정 전체 권한"),
    ("web/docker/db/init/01-roles.sh", "CREATE ROLE ytweb_app LOGIN PASSWORD :'app_pw'\n    NOSUPERUSER", "CREATE ROLE ytweb_app LOGIN PASSWORD :'app_pw'\n    SUPERUSER", "TW-32", "앱 계정 슈퍼유저"),
    ("web/docker/api.Dockerfile", "pip install --only-binary=:all: --require-hashes --no-deps -r /build/requirements.txt", "pip install --only-binary=:all: --no-deps -r /build/requirements.txt", "TW-13", "백엔드 설치에서 해시 강제 제거"),
    ("web/docker/api.Dockerfile", "USER 10001:10001", "USER root", "TW-31", "api 이미지 루트 실행"),
    ("web/docker/web.Dockerfile", "npm ci --ignore-scripts --no-audit --no-fund", "npm install", "TW-13", "npm ci --ignore-scripts → npm install"),
    ("web/docker/web.Dockerfile", "node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392", "node:22-bookworm-slim", "TW-13", "베이스 이미지 다이제스트 고정 제거"),
    ("web/docker/web.Dockerfile", " && find dist -name '*.map' -type f -delete", "", "TW-18", "소스맵 삭제 제거"),
    ("web/docker/web.Dockerfile", "USER 101:101", "USER root", "TW-31", "web 이미지 루트 실행"),
    (".gitignore", "\ntoken*.json\n", "\n", "TW-18", ".gitignore 에서 token*.json 제거"),
    (".gitignore", "\n.harness-tmp/\n", "\n", "규칙 K", ".gitignore 에서 .harness-tmp/ 제거"),
    (".dockerignore", "\n.git\n", "\n", "TW-18", ".dockerignore 에서 .git 제거"),
    (".dockerignore", "\nweb/secrets/\n", "\n", "TW-18", ".dockerignore 에서 web/secrets/ 제거"),
    ("web/frontend/package.json", '"react": "19.3.0"', '"react": "^19.3.0"', "TW-13", "프런트 의존성 범위 허용"),
    ("web/frontend/src/components/Badge.tsx", "", "\nexport const __evil = { dangerouslySetInnerHTML: { __html: '<b>x</b>' } };\n", "TW-11", "프런트에 dangerouslySetInnerHTML 추가"),
    ("web/frontend/src/components/Badge.tsx", "", "\nexport const __evil2 = () => localStorage.setItem('csrf', 'x');\n", "TW-20", "프런트에 localStorage 사용 추가"),
    ("web/frontend/src/components/Badge.tsx", "", "\nexport const __evil3 = () => fetch('https://cdn.example.com/x.js');\n", "S-W11", "프런트에 외부 URL fetch 추가"),
    ("web/frontend/vite.config.ts", "sourcemap: false", "sourcemap: true", "TW-18", "빌드 소스맵 켬"),
    ("web/frontend/tsconfig.build.json", '"src/test/**"', '"src/none/**"', "TW-18", "운영 빌드에 시험 폴더 포함"),
    ("web/scripts/restore.ps1", "Assert-BackupFileName $leaf\n", "", "TW-12", "복원 파일명 검증 제거"),
    ("web/scripts/stop.ps1", "$r = Invoke-Compose -ArgList @('down')", "$r = Invoke-Compose -ArgList @('down', '--volumes')", "TW-29", "종료 스크립트에 볼륨 삭제"),
    ("web/scripts/backup.ps1", "param([ValidatePattern('^[A-Za-z0-9-]+$')][string]$Prefix = 'ytweb')", "param([string]$Prefix = 'ytweb')", "TW-12", "백업 접두사 검증 제거"),
    ("web/backend/requirements.txt", "uvicorn==0.54.0 \\\n    --hash=sha256:", "uvicorn==0.54.0 \\\n    # --hash=sha256:", "TW-13", "해시 줄 주석 처리(잠금 파일 해시 누락)"),
    ("automation/github-actions-harness.yml", "production-deploy-approval", "production-deploy", "규칙 E", "배포 승인 environment 이름 변경(승인 게이트 상실)"),    # ── 개정 2판 ──
    (".gitignore", "client_secret*.json\n*client_secret*.json\n", "", "TW-18", "[R2] .gitignore 의 client_secret 패턴 제거"),
    (".dockerignore", "*.pem\n**/*.pem\n*.key\n**/*.key\n", "", "TW-18", "[R2] .dockerignore 의 키 파일 패턴 제거"),
    (".dockerignore", "**/.ruff_cache\n", "", "TW-18", "[R2] .dockerignore 의 개발 캐시 패턴 제거"),
    ("web/docker/api.Dockerfile", "COPY web/backend/ytweb /app/backend/ytweb\nCOPY web/backend/alembic /app/backend/alembic\nCOPY web/backend/alembic.ini /app/backend/alembic.ini", "COPY web/backend /app/backend", "TW-18", "[R2] api 이미지 COPY 를 web/backend 전체로 되돌림"),
    ("web/docker/nginx/security-headers-api.conf", 'Content-Security-Policy "default-src \'none\';', 'Content-Security-Policy "default-src \'self\';', "TW-23", "[R2] API 응답 CSP 완화"),
    ("web/docker/nginx/nginx.conf", "limit_except GET HEAD POST PUT PATCH DELETE { deny all; }\n            include /etc/nginx/snippets/security-headers-api.conf;", "limit_except GET HEAD POST PUT PATCH DELETE { deny all; }\n            include /etc/nginx/snippets/security-headers.conf;", "TW-23", "[R2] /api/ location 이 페이지용 CSP 사용"),
    ("web/docker/nginx/nginx.conf", "        location = /healthz {\n            include /etc/nginx/snippets/security-headers.conf;\n            add_header Cache-Control \"no-store\" always;\n            default_type text/plain;\n            return 404 \"not found\\n\";", "        location = /healthz {\n            include /etc/nginx/snippets/security-headers.conf;\n            add_header Cache-Control \"no-store\" always;\n            default_type text/plain;\n            return 200 \"ok\\n\";", "TW-34", "[R2] 루트 /healthz 를 200 으로(SPA 오판 재도입)"),
    ("web/docker/nginx/proxy.conf", "proxy_hide_header Cache-Control;\n", "", "TW-23", "[R2] 백엔드 Cache-Control 숨김 제거(중복 헤더)"),
    ("web/docker/db/audit-guard.sql", "REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON TABLE public.alembic_version FROM ytweb_app;", "", "TW-32", "[R2] 복원 후 alembic_version 권한 회수 제거"),
    ("web/docker/db/audit-guard.sql", "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE public.audit_log FROM ytweb_app;", "", "TW-08", "[R2] 복원 후 audit_log 권한 회수 제거"),
    ("web/docker/web.Dockerfile", "COPY --chown=0:0 web/docker/nginx/security-headers-api.conf /etc/nginx/snippets/security-headers-api.conf\n", "", "TW-23", "[R2] web 이미지에 API 헤더 파일 미포함"),
    ("web/frontend/src/app/Layout.tsx", "        <p>{ko.legal.disclaimer}</p>\n", "", "POL-002", "[R2] 화면 상시 푸터의 면책 문구 제거"),
    ("web/frontend/src/pages/BatchDetailPage.tsx", "disabled={phrase !== expected || !abAck}", "disabled={phrase !== expected}", "POL-013", "[R2] A/B 확인 없이 실행 버튼 활성"),
    ("web/frontend/src/i18n/ko.ts", "disclaimer: '이 검증은 법률 자문이 아니며 최종 책임은 채널 소유자에게 있습니다.',", "disclaimer: '이 검증은 정확합니다.',", "POL-002", "[R2] 화면 면책 문구 내용 변경"),
]


def locate(rel: str) -> Path:
    p = ROOT / "web/backend/ytweb" / rel
    assert p.is_file(), p
    return p


def run_one(idx: int, spec) -> dict:
    fname, old, new, threat, desc = spec
    src_file = locate(fname)
    text = src_file.read_text(encoding="utf-8")
    n = text.count(old)
    equivalent_control = '동치 대조군' in desc
    if n != 1:
        return {"id": idx, "desc": desc, "threat": threat, "file": fname, "result": "ERROR", "detail": f"대상 문자열 {n}곳"}
    d = WORK / f"m{idx:02d}"
    if d.exists():
        shutil.rmtree(d)
    (d / "backend").mkdir(parents=True)
    shutil.copytree(ROOT / "web/backend/ytweb", d / "backend/ytweb", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "src/youtube_title", d / "src/youtube_title", ignore=shutil.ignore_patterns("__pycache__"))
    rel = src_file.relative_to(ROOT / "web/backend")
    target = d / "backend" / rel
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    env = dict(os.environ, YTWEB_SEC_BACKEND_DIR=str(d / "backend"), YTWEB_SEC_SRC_DIR=str(d / "src"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("YTWEB_SEC_LIVE_PORT", None)
    t0 = time.time()

    def run(suites):
        p = subprocess.run([sys.executable, "-m", "pytest", *suites, "-q", "-x", "-p", "no:cacheprovider", "--tb=line", "-W", "ignore"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=1200)
        return p.returncode != 0, p.stdout

    first_suites = HINT.get(fname, [S2])
    killed, out = run(first_suites)
    if not killed and set(first_suites) != set(SUITES):
        killed, out = run(SUITES)
    first = next((l for l in out.splitlines() if l.startswith("FAILED") or "Error" in l[:40]), "")
    shutil.rmtree(d, ignore_errors=True)
    res = "killed" if killed else ("survived(동치 대조군)" if equivalent_control else "SURVIVED")
    return {"id": idx, "desc": desc, "threat": threat, "file": fname, "result": res, "by": first[:140], "sec": round(time.time() - t0, 1)}


COPY_ITEMS = ["web/compose.yaml", "web/compose.online.yaml", "web/docker", "web/scripts", "web/frontend/src", "web/frontend/index.html", "web/frontend/package.json", "web/frontend/package-lock.json",
              "web/frontend/tsconfig.build.json", "web/frontend/vite.config.ts", "web/frontend/eslint.config.js", "web/frontend/.gitignore", ".gitignore", ".dockerignore", "requirements.txt",
              "web/backend/requirements.txt", "web/backend/requirements-dev.txt", "web/backend/requirements.in", "automation", "config", "web/backend/ytweb", "src/youtube_title/ui.py"]


def run_infra(idx: int, spec) -> dict:
    rel, old, new, threat, desc = spec
    src = ROOT / rel
    text = src.read_text(encoding="utf-8")
    appended = old == ""
    if not appended and text.count(old) != 1:
        return {"id": idx, "desc": desc, "threat": threat, "file": rel, "result": "ERROR", "detail": f"대상 문자열 {text.count(old)}곳"}
    d = WORK / f"c{idx:03d}"
    if d.exists():
        shutil.rmtree(d)
    for item in COPY_ITEMS:
        a, b = ROOT / item, d / "root" / item
        b.parent.mkdir(parents=True, exist_ok=True)
        if a.is_dir():
            shutil.copytree(a, b, ignore=shutil.ignore_patterns("__pycache__", "node_modules", "dist"))
        elif a.exists():
            shutil.copy2(a, b)
    target = d / "root" / rel
    target.write_text(text + new if appended else text.replace(old, new, 1), encoding="utf-8")
    env = dict(os.environ, YTWEB_SEC_ROOT=str(d / "root"), PYTHONDONTWRITEBYTECODE="1")
    env.pop("YTWEB_SEC_LIVE_PORT", None)
    t0 = time.time()
    p = subprocess.run([sys.executable, "-m", "pytest", "web/tests_security/test_sec_03_static_repo.py", "web/tests_security/test_sec_08_fix_sources.py", "-q", "-p", "no:cacheprovider", "--tb=line", "-W", "ignore"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    failed = [l for l in p.stdout.splitlines() if l.startswith("FAILED")]
    killed = p.returncode != 0 and bool(failed)
    shutil.rmtree(d, ignore_errors=True)
    return {"id": idx, "desc": desc, "threat": threat, "file": rel, "result": "killed" if killed else "SURVIVED", "by": (failed[0] if failed else p.stdout.strip().splitlines()[-1:] and p.stdout.strip().splitlines()[-1])[:140], "sec": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--infra", action="store_true", help="코드 변이 대신 인프라·설정 변이(MC)를 돌린다(번호는 101~)")
    ap.add_argument("--out", default=str(WORK / "result.json"))
    a = ap.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    only = {int(x) for x in a.only.split(",") if x}
    results = []
    items = [(100 + i, spec) for i, spec in enumerate(MC, 1)] if a.infra else list(enumerate(M, 1))
    for i, spec in items:
        if only and i not in only:
            continue
        r = run_infra(i, spec) if a.infra else run_one(i, spec)
        results.append(r)
        print(f"{r['id']:>3} {r['result']:<22} {r['threat']:<8} {r['desc']}  {r.get('by', r.get('detail', ''))[:100]}", flush=True)
        Path(a.out).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    killed = sum(1 for r in results if r["result"] == "killed")
    surv = [r for r in results if r["result"] == "SURVIVED"]
    err = [r for r in results if r["result"] == "ERROR"]
    print(f"\n변이 {len(results)}곳: killed {killed}, SURVIVED {len(surv)}, ERROR {len(err)}")
    return 1 if surv or err else 0


if __name__ == "__main__":
    raise SystemExit(main())
