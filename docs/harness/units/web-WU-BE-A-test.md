# 테스트 결과서 — W-BE-A 백엔드 기반 (6단계 독립 검증, 웹 전환)

## 1. 개요
- 테스트 대상 (모듈/기능/업무단위/전체 시스템 중 명시): **모듈 — 작업 단위 W-BE-A**: `web/backend/ytweb/core/`, `ytweb/app.py`, `ytweb/worker.py`, `ytweb/migrate.py`, `ytweb/routers/{health,auth,settings,audit}.py`, `web/backend/alembic/`
- 테스트 유형: 단위 (독립 심사자 검증, 구현자 시험 `tests/core`는 참고만 하고 다시 실행)
- 적용 Tier (Low/Standard/High): Standard 이상으로 취급(보안 게이트 단위라 규칙 B 2회 이상 전부 적용). 프로젝트 등급은 오케스트레이터 기준을 따름
- 적용 속도 트랙: L3(일반, 표기 없음)
- 병렬 실행 정보: 병렬 웨이브에서 실행(동시에 W-BE-B `verify_wb`, W-FE `vf`, W-INF `vi` 검증이 돌았음). 임시 폴더 `.harness-tmp/va/`, PostgreSQL 포트 54331
- 테스트 목적: 구현자의 시험을 믿지 않고 설계(WEB_DESIGN §3·§5·§7·§10, DESIGN Part B, API.md)·보안 요구(S-W02/03/04/08/09/12/13/13a/16)에서 직접 시험을 만들어 Host/Origin/CSRF 가드 순서, 세션, PIN 잠금, 속도 제한, 멱등성, 감사 체인, 작업 큐, 설정 저장소, 마이그레이션 권한, 오류 형식, 로그 마스킹, KST/PT 날짜를 검증하고 결함을 찾아 고친다
- 관련 산출물: `docs/harness/units/web-WU-BE-A-note.md`, `docs/yt/WEB_DESIGN.md`, `docs/yt/DESIGN.md` Part B(검증 대기 V-01), `docs/yt/API.md`, `웹프로그램으로수정요청.md`, 공통 지시서 `docs/harness/_parallel/web-verify-brief.md`, 조정자 추가 지시(DEF-VF-B01·B02)
- 테스트 수행자(에이전트): 06 단위 테스터(독립 QA 리드 `va`)
- 테스트 일시: 2026-10-10 ~ 2026-10-11 (세션 한도·컨테이너 재시작으로 두 번 중단 후 재개)

## 2. 테스트 범위 및 제외 범위
- 범위 (In-Scope): 노트 8절 인수 조건 8개 + 조정자 추가 지시 2개(AC-9 commit-before-response, AC-10 오류 hint). 소스 직접 읽기 보안 점검, 변이 점검 134곳(+제어군 2), 6회전, 커버리지, 정적 검사, 실서버(uvicorn)·실제 워커 프로세스·실제 PostgreSQL 16 시험
- 제외 범위 (Out-of-Scope) 및 사유 (**PASS로 세지 않음**):
  - 실제 Chrome/Edge 에서 `Secure` 없는 쿠키·`SameSite=Strict`·`Sec-Fetch-Site` 동작(Q-WA-1): 사용자 PC 필요 -> **미수행**
  - Docker 컨테이너·nginx 경유 동작, PostgreSQL **17**(DEC-041의 대상 버전): 이 환경은 호스트 PostgreSQL 16.15 만 있음 -> 16 에서만 검증, 17 은 **미수행**
  - Python 3.12(요구 `>=3.12`): 이 환경은 3.13.16 뿐 -> 3.12 **미수행**
  - 실제 구글·유튜브·AI 호출(금지), 다른 단위(`ytweb/domain`, `ytweb/ai`, `ytweb/youtube`, 나머지 라우터)의 동작(W-BE-B 소유)
  - 다중 프로세스 속도 제한 공유(설계상 단일 프로세스 전제)

## 3. 테스트 환경
- 실행 환경: Linux 6.18(컨테이너), Python 3.13.16, 가상환경 `.harness-tmp/va/venv`(`requirements-dev.txt` 해시 잠금 설치: fastapi 0.143.0, starlette 1.7.0, pydantic 2.14.0, SQLAlchemy 2.1.4, alembic 1.20.0, psycopg 3.3.6, uvicorn 0.54.0, pytest 9.1.1, httpx 0.28.1), 정적 검사 ruff 0.17.0·pyflakes, 커버리지 coverage/pytest-cov
- DB: 기본 SQLite 임시 파일(시험마다 새로 생성) + **임시 PostgreSQL 16.15**(`.harness-tmp/va/pg`, 127.0.0.1:54331, DB `ytweb_va`; 변이 점검 전용 DB `ytweb_va_m0~3`)
- 테스트 데이터: 가짜 시계(`FakeClock` 2026-10-10 03:00Z), 가짜 단조시계(속도 제한), 더미 PIN/토큰만 사용(실제 비밀 없음). 실제 외부 서비스 호출 없음
- 전제 조건: PostgreSQL 시험은 `YTWEB_TEST_PG_URL` 가 있어야 하며 public 스키마를 DROP 한다(일회용 DB 에서만 실행). 역할 `ytweb_app` 은 클러스터 전역이라 PG 시험은 동시에 하나만 실행

### 재실행 방법
```
cd web/backend
python3 -m venv ../../.harness-tmp/va/venv && . ../../.harness-tmp/va/venv/bin/activate
pip install --require-hashes -r requirements-dev.txt && pip install -e ../..
export YTWEB_TEST_PG_URL=postgresql+psycopg://<일회용 DB>      # PG 시험 포함(없으면 건너뜀)
pytest tests/core tests/verify_wa -o addopts="" -q -p no:cacheprovider
pytest tests/verify_wa -o addopts="" --cov=ytweb.core --cov=ytweb.app --cov=ytweb.worker --cov=ytweb.migrate --cov-branch --cov-report=term-missing
python tests/verify_wa/mutation/run_mut.py <회전이름> [M01,M02,...]   # 변이 점검(경로는 .harness-tmp/va 기준으로 쓰여 있음, 필요 시 수정)
```

## 4. 테스트 케이스 및 결과
시험 파일: `web/backend/tests/verify_wa/test_va_01~12*.py`, 보조 `helpers.py`·`conftest.py`·`probe_routes.py`(소스를 고치지 않고 core 를 HTTP 로 두드리는 시험 전용 라우터). ID `TC-VA-001~196`(연속, 중복 없음, 생성 스크립트로 확인). 한 ID 가 파라미터화되어 여러 건을 가진다.
최종 전체 실행(구현자 `tests/core` 212건 + 독립 `tests/verify_wa` 481건 = **693건, 통과 693, 실패 0**, PostgreSQL 포함; DEF-VA-012 수정 후 재실행). 아래 표의 "실제 결과" 건수는 그 실행의 junit 결과다. 표의 "예상 결과"는 각 시험 docstring 이며 설계·요구 문장에 근거한다. 정상 경로·경계값·예외 입력·권한 경계·악의적 입력·동시성이 모두 들어 있다.

| ID | 시나리오·예상 결과(명세 근거) | 사전조건 | 실행 절차 | 실제 결과 | Pass/Fail | 비고(보안 요구 ID) |
|---|---|---|---|---|---|---|
| TC-VA-001 | 허용 Host(대소문자 무관)는 통과한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_host_allowed_variants` | 4건 통과 | PASS | S-W02 |
| TC-VA-002 | 허용 목록과 정확히 같지 않은 Host(포트 불일치·접미사·userinfo·숫자 표기·공백)는 403 이고 입력을 되돌리지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_host_rejected_variants` | 23건 통과 | PASS | S-W02 |
| TC-VA-003 | Host 헤더가 아예 없는 요청은 403. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_host_header_missing_rejected` | 1건 통과 | PASS | S-W02 |
| TC-VA-004 | Host 헤더가 여러 개이고 마지막이 비허용이면 거부(헤더 밀수 시도). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_multiple_host_headers_one_evil_rejected_when_evil_last` | 1건 통과 | PASS | S-W02 |
| TC-VA-005 | Host 헤더가 여러 개이고 하나라도 비허용이면 순서와 무관하게 거부돼야 한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_multiple_host_headers_one_evil_rejected_when_evil_first` | 1건 통과 | PASS | S-W02 |
| TC-VA-006 | DNS 리바인딩: Host/Origin 이 모두 공격자 도메인이어도 세션이 만들어지지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_dns_rebinding_post_creates_no_session` | 1건 통과 | PASS | S-W02 |
| TC-VA-007 | 헬스 경로만 Host 면제이고 본문은 status/db/mode 외 아무것도 없다(경로·URL·버전 비노출). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_health_paths_exempt_but_leak_only_minimal_info` | 4건 통과 | PASS | S-W02, S-W09 |
| TC-VA-008 | Host 면제는 정확한 경로 4개에만 적용된다(유사 경로·슬래시·대소문자 변형은 403). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_host_exemption_is_exact_path_only` | 8건 통과 | PASS | S-W02 |
| TC-VA-009 | 존재하지 않는 경로(정적 파일 포함)도 비허용 Host 면 404 가 아니라 403(경로 존재 여부 비노출). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_host_check_precedes_everything_even_unknown_routes` | 1건 통과 | PASS | S-W02 |
| TC-VA-010 | 설정 PATCH 에서 Sec-Fetch-Site(9종) x Origin(16종) 전 조합: 오라클과 일치하고, 거부된 요청은 상태를 바꾸지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_origin_secfetch_matrix_patch_settings` | 9건 통과 | PASS | S-W02, S-W03 |
| TC-VA-011 | 세션 발급 POST 에서도 같은 표가 적용되고, 거부 시 세션 행이 늘지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_origin_secfetch_matrix_session_issue` | 9건 통과 | PASS | S-W02 |
| TC-VA-012 | 세션·CSRF 가 모두 유효해도 출처가 외부면 403 이고 설정/감사 행이 생기지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_foreign_origin_with_valid_session_and_csrf_is_403_and_leaves_no_audit` | 1건 통과 | PASS | S-W02, S-W03, S-W16 |
| TC-VA-013 | 외부 출처 요청에는 세션 유무(401/403 차이)를 알리지 않는다: 세션 없는 외부 출처도 403 origin_not_allowed. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_origin_check_precedes_session_check` | 1건 통과 | PASS | S-W02 |
| TC-VA-014 | 상태 변경 엔드포인트에 GET 으로 접근하면 405 이고 아무것도 바뀌지 않는다(GET 으로 상태 변경 불가). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_state_changing_methods_never_succeed_via_get` | 1건 통과 | PASS | S-W03 |
| TC-VA-015 | 외부 Origin 의 요청에 Access-Control-Allow-* 가 붙지 않는다(브라우저가 응답을 못 읽게). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_no_cors_headers_ever_for_foreign_origin` | 1건 통과 | PASS | S-W02 |
| TC-VA-016 | Content-Length 1048576 은 413 이 아니고, 1048577 은 413 payload_too_large. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_content_length_boundary_exact_limit_and_one_over` | 1건 통과 | PASS | S-W13 |
| TC-VA-017 | Content-Length 없이 여러 조각으로 보내도 합계 1048576 까지만 허용, 1 바이트 초과 시 413 이며 설정은 바뀌지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_chunked_body_boundary_without_content_length` | 1건 통과 | PASS | S-W13 |
| TC-VA-018 | 숫자가 아닌 Content-Length 는 400 bad_content_length(500 이 아님). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_garbage_content_length_rejected_400` | 4건 통과 | PASS | S-W13 |
| TC-VA-019 | RFC 9110 의 1*DIGIT 가 아닌 Content-Length('-1','+5','1_0')도 가드가 거부해야 한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_nonstandard_numeric_content_length_rejected` | 3건 통과 | PASS | S-W13 |
| TC-VA-020 | 인증 없는 1MB+1 요청도 인증 검사 전에 413 으로 잘린다(핸들러 미도달). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_oversize_rejected_before_auth_and_before_handler` | 1건 통과 | PASS | S-W13 |
| TC-VA-021 | 전역 한도 N 번째까지 200, N+1 번째 429(Retry-After 1~60 정수), 창 경계 59.9초 후 아직 429, 정확히 60초 후 200. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_rate_limit_global_boundary_and_window_edge` | 1건 통과 | PASS | S-W13 |
| TC-VA-022 | 헬스 경로와 Host 거부 요청은 한도를 소모하지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_rate_limit_excludes_health_and_host_rejected` | 1건 통과 | PASS | S-W13 |
| TC-VA-023 | 쓰기 한도와 세션 발급 한도는 각자 따로 걸리고, 쓰기 한도가 찬 뒤에도 GET 은 통과한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_rate_limit_write_and_auth_buckets_separate` | 1건 통과 | PASS | S-W13 |
| TC-VA-024 | 외부 사이트(cross-site)가 보낸 요청은 소유자의 세션 발급 한도를 소모하지 않아야 한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_cross_site_requests_do_not_exhaust_owner_rate_limit` | 1건 통과 | PASS | S-W02, S-W13 |
| TC-VA-025 | 보안 헤더가 200/401/403(Host)/404/405/413/422 응답 모두에 붙는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_security_headers_on_every_api_response_class` | 1건 통과 | PASS | S-W04 |
| TC-VA-026 | 모든 오류는 problem+json 이고 키가 {type,title,status,detail,code,hint} 뿐이며 요청 ID 는 요청마다 다르다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_problem_json_shape_and_request_id_unique` | 1건 통과 | PASS | S-W09 |
| TC-VA-027 | enable_docs=False 이면 /docs /redoc /openapi.json 이 404 다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_docs_and_openapi_hidden_by_default` | 1건 통과 | PASS | S-W04 |
| TC-VA-028 | 웹소켓 스코프는 Host 와 무관하게 1008 로 닫는다. | 임시 PG16 | `pytest tests/verify_wa/test_va_01_http_boundary.py::test_websocket_upgrade_refused_without_reaching_app` | 1건 통과 | PASS | S-W02 |
| TC-VA-029 | Set-Cookie: HttpOnly, SameSite=Strict, Path=/api, Max-Age=TTL초, Domain 없음, Expires 없음(Max-Age 우선), 이름 ytw_session. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_cookie_attributes_exact` | 1건 통과 | PASS | S-W04 |
| TC-VA-030 | 로그아웃은 같은 Path 로 Max-Age=0 삭제 쿠키를 내리고, 서버에서도 토큰이 즉시 무효가 된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_logout_cookie_deletion_attributes_and_server_side_invalidation` | 1건 통과 | PASS | S-W04 |
| TC-VA-031 | 세션 토큰/CSRF 토큰은 URL-safe 43자(256비트)이고 40회 발급해도 겹치지 않으며 서로 다르다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_session_token_entropy_and_uniqueness` | 1건 통과 | PASS | S-W08 |
| TC-VA-032 | DB 의 sessions.id 는 sha256(토큰) 이고 sessions 테이블 어디에도 쿠키 토큰 원문이 없다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_db_stores_only_sha256_of_session_token` | 1건 통과 | PASS | S-W08 |
| TC-VA-033 | 세션 고정: 공격자가 심은 쿠키 값을 서버가 채택하지 않고 새 토큰을 발급하며, 심은 값은 인증되지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_session_fixation_attacker_supplied_cookie_not_adopted` | 1건 통과 | PASS | S-W02 |
| TC-VA-034 | 이상한 세션 쿠키(빈 값·초장문·SQL·경로 문자열)는 500 없이 단순히 미인증(401/authenticated=false) 처리. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_malformed_session_cookie_is_plain_unauthenticated` | 10건 통과 | PASS | S-W02 |
| TC-VA-035 | 만료 경계: 발급+TTL-1µs 까지 유효, 정확히 +TTL 에서 무효(행 삭제). 중간에 활동해도 만료 시각은 연장되지 않는다(절대 만료). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_session_expiry_boundary_is_exclusive_absolute_and_row_deleted` | 1건 통과 | PASS | S-W08 |
| TC-VA-036 | 만료된 세션 + 올바른 CSRF 로는 상태 변경이 401 이고 값이 바뀌지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_expired_session_cannot_mutate` | 1건 통과 | PASS | S-W03, S-W08 |
| TC-VA-037 | 세션은 최대 20개: 25번 발급하면 20개만 남고 가장 오래된 5개 토큰은 무효, 최신 20개는 유효. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_active_session_cap_is_20_and_oldest_evicted` | 1건 통과 | PASS | S-W08 |
| TC-VA-038 | (특성화) 재로그인은 이전 세션을 회전/폐기하지 않는다(복수 세션 허용). 로그아웃은 그 세션만 폐기한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_new_login_does_not_invalidate_previous_session_characterization` | 1건 통과 | PASS | S-W08 |
| TC-VA-039 | CSRF: 없음·빈 값·접두/접미 변형·대소문자 변경·공백·유니코드·세션 토큰·다른 세션의 토큰은 403 csrf_invalid, 정확한 값만 200. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_csrf_rejected_variants_and_accepted_exact` | 1건 통과 | PASS | S-W03 |
| TC-VA-040 | CSRF 토큰은 세션별로 다르고, 같은 세션의 /me 가 같은 값을 돌려준다(로테이션으로 인한 정상 요청 실패 없음). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_csrf_token_is_per_session_and_stable_within_session` | 1건 통과 | PASS | S-W03 |
| TC-VA-041 | CSRF 거부 응답에 기대 토큰이나 세션 정보가 담기지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_csrf_error_does_not_disclose_expected_value` | 1건 통과 | PASS | S-W03, S-W09 |
| TC-VA-042 | DELETE /auth/session, PATCH /settings 는 CSRF 없이는 403, 세션 없이는 401(상태 변경 불가). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_unsafe_methods_all_require_csrf_and_session` | 1건 통과 | PASS | S-W03 |
| TC-VA-043 | PIN 잠금 경계: 틀림 1~4회는 401, 5회째가 429(잠금 300초). 잠금 중엔 올바른 PIN 도 429, 299초 후도 429, 300초 후에야 성공. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_lockout_exact_boundary_4_ok_5th_locks_correct_pin_rejected_while_locked` | 1건 통과 | PASS | S-W08 |
| TC-VA-044 | 4회 실패 뒤 성공하면 카운터가 0 으로 돌아가 다시 4회까지 실패해도 잠기지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_success_resets_failure_counter` | 1건 통과 | PASS | S-W08 |
| TC-VA-045 | 잠금 시간이 300→600→1200→2400→3600→3600초로 늘고 1시간에서 멈춘다(Retry-After 로 확인). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_lock_duration_doubles_up_to_one_hour_cap` | 1건 통과 | PASS | S-W08 |
| TC-VA-046 | 잠금 상태는 DB 에 있어 프로세스를 새로 띄워도 유지된다(재시작으로 우회 불가). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_lock_survives_app_restart` | 1건 통과 | PASS | S-W08 |
| TC-VA-047 | PIN 변경 경로(PATCH /settings pin)의 current_pin 오류도 같은 잠금 카운터를 소모해 5회에 잠기고, 잠기면 세션 발급도 막힌다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_lock_shared_with_settings_pin_change_path` | 1건 통과 | PASS | S-W08 |
| TC-VA-048 | PIN 이 필요한데 본문 없음/null/빈 문자열이면 401 로 실패 처리(우회 불가)되고 세션 쿠키가 내려가지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_wrong_type_or_missing_counts_as_failure` | 1건 통과 | PASS | S-W08 |
| TC-VA-049 | PIN 형식 경계: ASCII 숫자 4~12자리만 허용(3/13자리, 문자, 유니코드 숫자, 공백, 부호는 422). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_format_boundaries` | 12건 통과 | PASS | S-W08 |
| TC-VA-050 | 끝에 줄바꿈이 붙은 PIN 은 형식 위반으로 422 여야 한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_trailing_newline_rejected` | 2건 통과 | PASS | S-W08 |
| TC-VA-051 | PIN 은 scrypt(N>=2^14,r=8,p=1)+16바이트 무작위 솔트로 저장되고 같은 PIN 도 해시가 매번 다르며 평문이 DB 에 없다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_hash_scheme_salt_and_params` | 1건 통과 | PASS | S-W08 |
| TC-VA-052 | 저장된 해시가 손상돼도 예외 없이 False(로그인 500 방지). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_verify_pin_hash_tolerates_corrupt_storage` | 7건 통과 | PASS | S-W08 |
| TC-VA-053 | PIN 설정/변경/해제 시 현재 세션 외 모든 세션이 폐기되고 현재 세션은 유지된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_change_and_clear_revoke_other_sessions_but_keep_current` | 1건 통과 | PASS | S-W08 |
| TC-VA-054 | PIN 해제는 현재 PIN 이 맞아야 하며(없거나 틀리면 401), 설정이 없을 때 해제는 409. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_clear_pin_requires_current_pin_when_set` | 1건 통과 | PASS | S-W08 |
| TC-VA-055 | PIN 값/해시/쿠키/CSRF 토큰이 감사 로그 행과 설정 응답 어디에도 없다. 실패·잠금·성공이 감사에 남는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_02_session_csrf_pin.py::test_pin_never_in_audit_rows_or_responses` | 1건 통과 | PASS | S-W08, S-W16 |
| TC-VA-056 | 허용 키 4개 외의 모든 변형(대소문자·공백·제로폭·유사 문자·내부 키 pin_hash 등)은 400 setting_not_allowed 이고 DB/감사에 흔적이 없다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_non_allowlisted_key_variants_rejected_and_nothing_written` | 36건 통과 | PASS | S-W03 |
| TC-VA-057 | 허용 키와 금지 키가 섞이면 전체가 거부되어 허용 키 값도 적용되지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_mixed_allowed_and_forbidden_rejects_entire_request` | 1건 통과 | PASS | S-W03 |
| TC-VA-058 | 허용 키 안에 중첩 객체/배열로 금지 키를 숨겨도 저장되지 않는다(타입 검증에서 422). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_nested_forbidden_keys_cannot_smuggle_through_allowed_keys` | 1건 통과 | PASS | S-W03 |
| TC-VA-059 | 중복 키 JSON 으로 금지 키를 감춰도(파서가 마지막 값 사용) 금지 키 검사에 걸린다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_duplicate_json_keys_last_wins_but_forbidden_still_detected` | 1건 통과 | PASS | S-W03 |
| TC-VA-060 | 객체가 아니거나 빈/깨진 JSON 본문은 4xx(500 아님)이고 problem+json 이다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_non_object_or_empty_body_is_422_or_400_never_500` | 10건 통과 | PASS | S-W13 |
| TC-VA-061 | text/plain 으로 JSON 문자열을 보내는 '단순 요청' 방식 CSRF 는 값을 바꾸지 못한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_wrong_content_type_does_not_apply_change` | 1건 통과 | PASS | S-W03 |
| TC-VA-062 | 정수 설정 경계: lo, hi 는 200, lo-1, hi+1 은 422. bool/실수/문자열/null/배열/객체/NaN/거대정수는 422. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_int_setting_boundaries_and_type_confusion` | 2건 통과 | PASS | S-W13 |
| TC-VA-063 | tone: 0~5개·항목 1~20자(공백 제거 후)만 허용, 6개/21자/빈/공백뿐/제어문자/비문자열/null 은 422, 앞뒤 공백은 제거되어 저장. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_tone_boundaries_and_sanitization` | 1건 통과 | PASS | S-W13 |
| TC-VA-064 | GET /settings 응답에 pin_hash/pin_fail/세션/내부 키가 없다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_settings_view_never_exposes_pin_hash_or_internal_keys` | 1건 통과 | PASS | S-W08, S-W09 |
| TC-VA-065 | 설정 변경은 감사에 값(비밀 제외)과 함께 남고, 감사 기록이 실패하면 설정 변경도 롤백된다(같은 트랜잭션). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_settings_update_is_audited_without_secrets_and_atomic_with_audit` | 1건 통과 | PASS | S-W16 |
| TC-VA-066 | 키가 없거나 빈 값이면 400 idempotency_key_required 이고 핸들러는 실행되지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_missing_key_400_and_handler_not_called` | 1건 통과 | PASS | S-W12 |
| TC-VA-067 | 키 형식 경계: 8~80자 [A-Za-z0-9._:-] 만 허용. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_key_format_boundaries` | 10건 통과 | PASS | S-W12 |
| TC-VA-068 | 같은 키+같은 본문 재전송: 핸들러 1회만 실행, 두 번째는 저장된 응답(상태·본문 동일, datetime 직렬화 포함)을 재생. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_same_key_same_body_replays_once` | 1건 통과 | PASS | S-W12 |
| TC-VA-069 | 본문 키 순서만 다르면 같은 요청(재생), 값이 1 이라도 다르면 422 idempotency_key_reuse(핸들러 미실행). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_key_order_insensitive_but_value_sensitive` | 1건 통과 | PASS | S-W12 |
| TC-VA-070 | 같은 키를 다른 라우트에 쓰면 본문이 같아도 422 이고 두 번째 라우트 핸들러는 실행되지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_same_key_different_route_is_reuse_error` | 1건 통과 | PASS | S-W12 |
| TC-VA-071 | 서로 다른 키(대소문자만 다른 것 포함)는 각각 실행된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_different_keys_run_separately_and_keys_are_case_sensitive` | 1건 통과 | PASS | S-W12 |
| TC-VA-072 | 핸들러가 실패(409)하면 키가 저장되지 않아 같은 키로 재시도하면 다시 실행된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_failed_handler_does_not_burn_the_key` | 1건 통과 | PASS | S-W12 |
| TC-VA-073 | (특성화) 멱등성 키는 세션과 무관하게 전역이다: 다른 세션이 같은 키+본문을 보내면 첫 응답이 재생된다(단일 소유자 전제). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_replay_crosses_sessions_characterization` | 1건 통과 | PASS | S-W12 |
| TC-VA-074 | CSRF/출처 검증에 실패한 요청은 멱등성 키를 저장하지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_requires_csrf_before_key_is_stored` | 1건 통과 | PASS | S-W12, S-W03 |
| TC-VA-075 | TTL 경계: 정확히 24시간 경과까지는 재생, 24시간+1µs 에는 새로 실행(만료 키 정리). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_ttl_boundary_exactly_24h_replays_and_one_microsecond_later_reexecutes` | 1건 통과 | PASS | S-W12 |
| TC-VA-076 | 처리 중(응답 미저장) 키로 같은 요청이 오면 409 in_progress, 다른 요청이면 422(우선순위: 불일치 먼저). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_in_progress_row_blocks_with_409_and_other_request_gets_422` | 1건 통과 | PASS | S-W12 |
| TC-VA-077 | required=False 이고 키가 없으면 멱등성 없이 매번 실행(키가 있으면 일반 규칙). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_not_required_mode_runs_handler_every_time` | 1건 통과 | PASS | S-W12 |
| TC-VA-078 | 비ASCII(악센트·한글·제로폭·전각) 키는 400 idempotency_key_invalid (HTTP 헤더로는 못 보내므로 단위 수준에서 확인). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_key_non_ascii_rejected_unit` | 4건 통과 | PASS | S-W12 |
| TC-VA-079 | 끝에 줄바꿈이 붙은 키는 형식 위반이어야 한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_03_settings_idempotency.py::test_idem_key_trailing_newline_rejected_unit` | 1건 통과 | PASS | S-W12 |
| TC-VA-080 | 저장된 해시가 명세로 독립 재구현한 sha256(prev+정규 JSON) 값과 모두 일치하고 첫 prev 는 0*64 이다(유니코드·중첩·None 포함). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_04_audit.py::test_chain_matches_independent_reference_implementation` | 1건 통과 | PASS | S-W16 |
| TC-VA-081 | 빈 로그는 체인 유효(True)로 본다(초기 상태). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_04_audit.py::test_empty_log_verifies_true` | 1건 통과 | PASS | S-W16 |
| TC-VA-082 | 시각은 UTC 로 정규화되어 해시되고(KST 입력도 같은 해시), naive datetime 은 ValueError. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_04_audit.py::test_non_utc_timezone_hashes_same_as_utc_and_naive_rejected` | 1건 통과 | PASS | S-W16 |
| TC-VA-083 | 변조 17종(내용 수정·1µs 시각 변경·해시/prev 변경·중간/첫 행 삭제·순서 바꾸기·위조 행 추가·해시 재계산 위장)은 verify_chain=False, API chain_ok=false. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_04_audit.py::test_tamper_detected_by_verify_and_api` | 17건 통과 | PASS | S-W16 |
| TC-VA-084 | (알려진 제한 특성화) 꼬리 절단·전체 삭제·키 없는 해시로 처음부터 다시 쓴 체인은 verify_chain 으로 탐지되지 않는다 -> DB 권한(UPDATE/DELETE/TRUNCATE 회수)이 유일한 방어선. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_04_audit.py::test_known_limits_tail_truncation_and_full_rewrite_are_not_detected` | 1건 통과 | PASS | S-W16 |
| TC-VA-085 | 감사 조회는 세션 필수(401). 페이지 경계: page_size 1·200 허용, 0·201 은 422, 범위 밖 page 는 빈 목록, 최신순. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_04_audit.py::test_audit_api_requires_session_and_paginates_newest_first` | 1건 통과 | PASS | S-W16 |
| TC-VA-086 | 매우 큰 page 값은 빈 목록(200) 또는 422 여야 하며 500 이면 안 된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_04_audit.py::test_audit_huge_page_does_not_500` | 2건 통과 | PASS | S-W13 |
| TC-VA-087 | 로그인·로그아웃·설정변경·로그인 거부가 순서대로 감사에 남고 체인이 유효하다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_04_audit.py::test_security_events_land_in_audit_with_expected_actions` | 1건 통과 | PASS | S-W16 |
| TC-VA-088 | 처리되지 않은 예외(경로·비밀이 든 메시지)는 일반 문구 500 problem+json 이고 응답 어디에도 예외 클래스/경로/메시지가 없으며 보안 헤더가 유지된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_unhandled_exception_returns_generic_500_without_leaks` | 1건 통과 | PASS | S-W09 |
| TC-VA-089 | DB 제약 위반(IntegrityError)도 SQL/테이블/드라이버 정보 없이 일반 500. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_db_error_returns_generic_500_without_sql` | 1건 통과 | PASS | S-W09 |
| TC-VA-090 | DB 오류 로그에 바인딩 파라미터 값(비밀일 수 있음)이 남지 않아야 한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_db_error_log_does_not_contain_bound_parameter_values` | 1건 통과 | PASS | S-W09 |
| TC-VA-091 | 코드가 던진 HTTPException(detail=경로/비밀)의 detail 은 응답에 나가지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_http_exception_detail_not_echoed` | 1건 통과 | PASS | S-W09 |
| TC-VA-092 | 검증 오류(422)는 위치와 사유만 알리고 제출한 값(비밀일 수 있음)을 되돌리지 않는다. 깨진 JSON 도 마찬가지. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_validation_error_does_not_echo_submitted_values` | 1건 통과 | PASS | S-W09 |
| TC-VA-093 | 404/405 도 problem+json 이고 요청 경로를 되돌리지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_404_405_are_problem_json_without_echoing_path` | 1건 통과 | PASS | S-W09 |
| TC-VA-094 | DB 가 죽어 있으면 /readyz 는 503(degraded) 이고 API 는 500 이며, 응답·로그에 DB 비밀번호/호스트/경로가 없다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_db_unreachable_gives_503_ready_and_500_api_without_connection_details` | 1건 통과 | PASS | S-W08, S-W09 |
| TC-VA-095 | 비밀 형태 16종(키=값, JSON, 쿠키, URL 자격증명, 43자 토큰)이 마스킹된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_mask_secrets_known_forms` | 16건 통과 | PASS | S-W09 |
| TC-VA-096 | Authorization 헤더 값(스킴 뒤 자격증명)까지 모두 마스킹돼야 한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_mask_secrets_authorization_header_values` | 3건 통과 | PASS | S-W09 |
| TC-VA-097 | 일반 문구·짧은 값·경로는 과하게 가리지 않는다(디버깅 가능성 유지). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_mask_does_not_destroy_ordinary_text` | 1건 통과 | PASS | S-W09 |
| TC-VA-098 | JSON 로그의 extra 필드(민감 키 이름·중첩 dict/list 값)와 예외 본문이 마스킹된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_json_formatter_masks_extra_fields_nested_and_exc` | 1건 통과 | PASS | S-W09 |
| TC-VA-099 | 실제 요청 흐름(PIN 설정·로그인·CSRF·쿠키·쿼리스트링·Authorization·검증오류)을 모두 거친 뒤 로그에 비밀이 하나도 없다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_05_errors_logs.py::test_secrets_never_reach_logs_through_real_request_flows` | 1건 통과 | PASS | S-W08, S-W09 |
| TC-VA-100 | 새 작업은 queued/attempts=0, run_after 가 미래면 claim 되지 않고 정확히 run_after 시각부터 claim 된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_enqueue_defaults_and_claim_due_boundary` | 1건 통과 | PASS | S-W12 |
| TC-VA-101 | claim 순서는 run_after, created_at 순이고, 한 번 가져간 작업은 다시 claim 되지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_claim_is_fifo_by_run_after_then_created_and_never_twice` | 1건 통과 | PASS | S-W12 |
| TC-VA-102 | queued 작업에 complete/fail 을 호출해도 상태가 바뀌지 않고, 이미 끝난 작업도 되살아나지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_complete_and_fail_only_affect_running_jobs` | 1건 통과 | PASS | S-W12 |
| TC-VA-103 | 실패 사유는 300자로 잘리고, 핸들러의 일반 예외는 클래스명만 저장되어 메시지(경로·비밀)가 DB 에 남지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_error_text_is_truncated_and_handler_exception_text_not_stored` | 1건 통과 | PASS | S-W09, S-W12 |
| TC-VA-104 | 핸들러 예외로 failed 가 된 작업은 자동 재시도되지 않는다(부작용 있는 작업의 중복 실행 방지) -> 핸들러는 1회만 호출. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_failed_job_is_never_retried_automatically` | 1건 통과 | PASS | S-W12 |
| TC-VA-105 | stale 판정 경계: locked_at 이 정확히 10분 전이면 정상 실행 중, 10분+1µs 전이면 재큐. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_requeue_stale_time_boundary` | 3건 통과 | PASS | S-W12 |
| TC-VA-106 | 죽은 워커의 작업은 시도 3회 미만이면 재큐, 3회 이상이면 failed(worker_lost). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_requeue_stale_attempt_cap` | 4건 통과 | PASS | S-W12 |
| TC-VA-107 | 워커가 죽어 running 으로 남은 작업이 재큐 후 다른 워커에게 처리되어 succeeded 가 된다(attempts=2). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_requeued_job_runs_again_and_dead_worker_result_is_replaced` | 1건 통과 | PASS | S-W12 |
| TC-VA-108 | update_progress 는 running 작업의 locked_at 을 갱신(하트비트)하고 queued 작업은 locked_at 을 만들지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_update_progress_heartbeat_only_for_running` | 1건 통과 | PASS | S-W12 |
| TC-VA-109 | (특성화) complete() 는 locked_by 를 확인하지 않는다: stale 로 재큐되어 다른 워커가 재실행 중인 작업을 느린 옛 워커가 succeeded 로 닫을 수 있다 -> 부작용 핸들러는 멱등이어야 함(권고 R-3). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_complete_without_fencing_lets_a_slow_old_worker_finish_a_reclaimed_job` | 1건 통과 | PASS | S-W12 |
| TC-VA-110 | 종료 신호(stop)가 오면 실행 중인 작업은 끝까지 마쳐 succeeded 가 되고, 나머지 작업은 queued 로 남아 다음 워커가 처리한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_worker_stop_request_finishes_current_job_and_leaves_the_rest_queued` | 1건 통과 | PASS | S-W12 |
| TC-VA-111 | 정비: 만료된 세션 삭제(만료 시각 정각 포함), 멱등성 키는 48시간 초과분만 삭제(정확히 48시간은 보존), 10분 안의 재정비는 건너뜀. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_worker_maintenance_purges_expired_sessions_and_old_idempotency_keys_with_boundaries` | 1건 통과 | PASS | S-W08, S-W12 |
| TC-VA-112 | 배치 스케줄러 함수가 예외를 던져도 tick 이 죽지 않고 작업 처리는 계속된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_worker_tick_survives_scheduler_exception` | 1건 통과 | PASS | S-W12 |
| TC-VA-113 | 실제 워커 프로세스: 큐의 작업을 처리(처리기 없음 -> failed)하고, SIGTERM 에 즉시 정상 종료(코드 0, 5초 이내)한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_06_jobs_worker.py::test_worker_process_handles_sigterm_gracefully_and_processes_jobs` | 1건 통과 | PASS | S-W12 |
| TC-VA-114 | Alembic 0001 이 만든 실제 PG 스키마의 컬럼(타입·길이·NULL·기본값)/인덱스(부분 조건 포함)/제약(CHECK·FK·UNIQUE·PK)/시퀀스가 models.py 에서 직접 생성한 스키마와 항목별로 같다. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_alembic_0001_matches_models_py` | 4건 통과 | PASS | S-W13a, S-W12 |
| TC-VA-115 | 테이블 집합이 모델 14개와 일치하고(alembic_version 제외) 누락/잉여 테이블이 없다. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_alembic_table_set_equals_model_tables_plus_version` | 1건 통과 | PASS | S-W13a |
| TC-VA-116 | upgrade head 를 한 번 더 실행해도 변화 없음, downgrade base 후 다시 upgrade 해도 성공하고 버전은 0001. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_upgrade_twice_and_downgrade_upgrade_cycle_are_safe` | 1건 통과 | PASS | S-W13a |
| TC-VA-117 | 실제 DB 가 CHECK(상태 열거)와 audit_log hash UNIQUE 를 강제한다. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_check_constraints_and_partial_unique_indexes_actually_reject_bad_rows` | 1건 통과 | PASS | S-W12 |
| TC-VA-118 | ytweb_app: audit_log 는 INSERT/SELECT 만(UPDATE·DELETE·TRUNCATE·SELECT FOR UPDATE 거부, 꼬리 행 삭제 포함), 다른 테이블은 INSERT/UPDATE/DELETE 가능, DDL·권한 부여·트리거 조작은 모두 거부. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_app_role_audit_log_is_append_only_and_other_tables_dml_allowed` | 1건 통과 | PASS | S-W16, S-W13a |
| TC-VA-119 | 앱 전체 흐름(로그인·PIN·설정·감사 체인·잡 큐·멱등성)이 실제로 ytweb_app 권한(options=-c role)으로 동작하고 chain_ok 가 true 다. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_whole_application_runs_end_to_end_as_least_privilege_role` | 1건 통과 | PASS | S-W16, S-W13a |
| TC-VA-120 | (특성화) 0001 의 REVOKE 는 '마이그레이션 시점'의 권한만 회수한다: 이후 인프라가 GRANT ALL ON ALL TABLES 를 하면 audit_log UPDATE 가 다시 열린다 -> 복원 뒤 audit-guard.sql 로 재회수해야 한다는 운영 의존성. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_grants_given_after_migration_would_undo_revoke_documented_dependency` | 1건 통과 | PASS | S-W16 |
| TC-VA-121 | JSONB 에 저장했다 읽어도 일반적인 detail 값(정수·소수·불리언·null·중첩)의 해시가 유지되어 체인이 유효하다. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_jsonb_roundtrip_keeps_chain_valid_for_ordinary_values` | 14건 통과 | PASS | S-W16 |
| TC-VA-122 | JSONB 가 정규화하는 float(지수 표기 큰 수, -0.0)는 기록 전에 거부되어 체인이 거짓 변조로 판정될 수 없다(DEF-6-008 수정 확인). | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_jsonb_unstable_floats_rejected_before_chain_can_break` | 3건 통과 | PASS | S-W16 |
| TC-VA-123 | 같은 Idempotency-Key 로 6개 스레드가 동시에 들어와도 핸들러는 정확히 1회 실행되고, 나머지는 409(처리 중) 또는 저장된 응답 재생이며 다른 예외는 없다. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_idempotency_concurrent_same_key_runs_handler_once` | 1건 통과 | PASS | S-W12 |
| TC-VA-124 | 워커 스레드 4개가 작업 40건을 process_next 로 동시에 처리해도 각 작업의 핸들러 실행은 정확히 1회이고 모두 succeeded 다. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_queue_four_workers_each_job_executed_exactly_once` | 1건 통과 | PASS | S-W12 |
| TC-VA-125 | 동시 PIN 추측: 8개 스레드가 동시에 틀린 PIN 을 보내도 잠금(5회)이 지켜져 401 응답은 4건을 넘지 않아야 한다(경쟁으로 잠금이 무력화되면 안 됨). | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_pin_lockout_holds_under_concurrent_guesses` | 1건 통과 | PASS | S-W08 |
| TC-VA-126 | HTTP 수준: 틀린 PIN 으로 10개 동시 로그인 요청을 보내도 401 은 4건을 넘지 않아야 한다(나머지는 429). | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_pin_lockout_holds_under_concurrent_http_logins` | 1건 통과 | PASS | S-W08 |
| TC-VA-127 | CSRF 토큰과 PIN 해시 비교는 hmac.compare_digest 를 쓰고, 토큰/해시를 ==/!= 로 직접 비교하는 코드가 없다. | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_secret_comparisons_use_constant_time_compare` | 1건 통과 | PASS | S-W08 |
| TC-VA-128 | 세션/CSRF 토큰은 secrets.token_urlsafe(32)(256비트), PIN 솔트는 secrets.token_bytes(16) 이며 보안 코드에 random 모듈이 없다. | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_tokens_come_from_secrets_module_with_256_bits_and_no_random_module` | 1건 통과 | PASS | S-W08 |
| TC-VA-129 | 이 단위 코드에 SQL 문자열 이어붙이기(f-string/format/% 로 만든 text())·eval·exec·pickle·shell=True·yaml.load 가 없다. | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_no_dynamic_sql_or_dangerous_calls_in_owned_code` | 1건 통과 | PASS | S-W13 |
| TC-VA-130 | 이 단위 소스에 비밀번호/토큰/키로 보이는 하드코딩 문자열 대입이 없다. | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_no_hardcoded_secret_literals_in_owned_code` | 1건 통과 | PASS | S-W08 |
| TC-VA-131 | scrypt 비용 N=2^14, r=8, p=1 이 코드에 고정돼 있다(권고 비교: OWASP 는 N>=2^17 을 제시 -> 6절 권고 R-1). | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_scrypt_parameters_meet_recorded_minimum` | 1건 통과 | PASS | S-W08 |
| TC-VA-132 | 헬스 라우트 소스는 세션/DB 값을 응답에 싣지 않는다(상태·db·mode 외 필드 없음). | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_health_routes_have_no_dependency_on_session_and_expose_nothing_else` | 1건 통과 | PASS | S-W02, S-W09 |
| TC-VA-133 | 실서버: 중복 Host 헤더(허용+비허용, 순서 두 가지)는 어느 쪽도 200 이 되지 않는다(서버 또는 가드가 거부). | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_live_duplicate_host_headers_never_served` | 1건 통과 | PASS | S-W02 |
| TC-VA-134 | 실서버: 비정상 Content-Length 는 서버(h11) 또는 가드가 4xx 로 거부한다(200 불가). | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_live_malformed_content_length_never_reaches_app_as_success` | 5건 통과 | PASS | S-W13 |
| TC-VA-135 | 실서버: Transfer-Encoding: chunked 로 1MB 를 넘기면 413, 작은 chunked 본문은 정상 처리된다. | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_live_chunked_body_over_1mb_gets_413_and_small_chunked_ok` | 1건 통과 | PASS | S-W13 |
| TC-VA-136 | 실서버 전체 흐름: 헬스(임의 Host) -> 세션 발급(쿠키 속성) -> CSRF 설정 변경 -> 로그아웃. Server 헤더 없음, 보안 헤더 존재, 서버 출력(stderr)에 쿼리스트링 비밀·토큰이 없다. | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_live_full_flow_cookie_headers_and_no_secret_in_server_output` | 1건 통과 | PASS | S-W04, S-W08, S-W09 |
| TC-VA-137 | 실서버: SIGTERM 에 10초 안에 종료하고(uvicorn 은 정리 후 신호를 다시 올려 returncode -15), 종료 로그에 'Finished server process' 가 남는다. | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_live_sigterm_graceful_shutdown` | 1건 통과 | PASS | S-W12 |
| TC-VA-138 | 정적 서빙: 상위 경로(../·인코딩 변형·널 문자)와 dist 밖을 가리키는 심볼릭 링크로 dist 밖 파일을 읽을 수 없다. | 실서버 기동 | `pytest tests/verify_wa/test_va_09_static_serving.py::test_static_path_traversal_and_symlink_escape_never_leak` | 11건 통과 | PASS | S-W10, S-W04 |
| TC-VA-139 | 실제 파일은 그대로, 모르는 화면 경로는 index.html(SPA), /api 아래 없는 경로는 index.html 이 아니라 problem+json 404, 정적 응답에도 CSP(default-src 'self')가 붙는다. | 실서버 기동 | `pytest tests/verify_wa/test_va_09_static_serving.py::test_static_serves_assets_spa_fallback_and_api_404_stays_json` | 1건 통과 | PASS | S-W04 |
| TC-VA-140 | 정적 파일도 허용되지 않은 Host 면 403(DNS 리바인딩으로 화면 코드를 읽지 못함). | 실서버 기동 | `pytest tests/verify_wa/test_va_09_static_serving.py::test_static_host_check_still_applies` | 1건 통과 | PASS | S-W02 |
| TC-VA-141 | 정적 폴백 경로에 POST/PUT/DELETE 를 보내면 405 이며 아무 일도 일어나지 않는다. | 실서버 기동 | `pytest tests/verify_wa/test_va_09_static_serving.py::test_static_does_not_accept_state_changing_methods` | 1건 통과 | PASS | S-W03 |
| TC-VA-142 | 결정적 SKIP LOCKED 시험: 트랜잭션 A 가 첫 작업 행을 FOR UPDATE 로 잡고 있어도 워커 B 의 claim 은 막히지 않고 두 번째 작업을 가져간다(5초 안). 잠금 건너뛰기가 없으면 B 가 막히거나 아무것도 못 가져간다. | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_claim_skips_row_locked_by_another_transaction_instead_of_blocking` | 1건 통과 | PASS | S-W12 |
| TC-VA-143 | 8개 스레드가 각각 10건씩 동시에 감사 기록을 남겨도 80행 모두 prev_hash 가 서로 달라 한 줄 체인이고 verify_chain 이 True 다(advisory lock). | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_concurrent_audit_writers_keep_one_linear_chain` | 1건 통과 | PASS | S-W16, S-W12 |
| TC-VA-144 | KST 날짜는 UTC 15:00 에 바뀐다(마이크로초 경계·연말·윤일 포함). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_kst_today_boundaries` | 6건 통과 | PASS | 시각 |
| TC-VA-145 | 태평양 날짜는 PST/PDT 전환(2026-03-08, 2026-11-01) 전후로 정확히 바뀐다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_pt_date_boundaries_incl_dst` | 13건 통과 | PASS | 시각 |
| TC-VA-146 | 다른 시간대로 표현된 같은 순간은 같은 날짜, naive 는 ValueError(조용히 로컬 시각으로 해석하지 않음). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_clock_accepts_other_tz_and_rejects_naive` | 1건 통과 | PASS | 시각 |
| TC-VA-147 | 저장소의 일일 한도가 손상돼도(범위 밖·bool·문자열·null) 안전한 기본값 10 으로 돌아가고, 1/20 경계는 그대로다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_effective_daily_cap_clamps_corrupt_values` | 11건 통과 | PASS | S-W13 |
| TC-VA-148 | 값이 없으면 기본 10. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_effective_daily_cap_default_when_missing` | 1건 통과 | PASS | S-W13 |
| TC-VA-149 | 설정 저장소: 없는 키는 기본값, set 은 삽입→갱신(updated_at 갱신), delete 는 없는 키에도 안전. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_settings_store_set_update_delete_and_default` | 1건 통과 | PASS |  |
| TC-VA-150 | 저장된 값이 0/빈 목록/False 여도 기본값으로 바뀌지 않는다(None 과 구분). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_get_web_setting_returns_stored_falsy_values` | 1건 통과 | PASS |  |
| TC-VA-151 | 외부 사이트 요청은 소유자 한도를 쓰지 않지만 자기 창에서는 제한(N+1 번째 429)되고 창이 지나면 풀린다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_foreign_requests_have_own_bucket_and_are_still_limited` | 1건 통과 | PASS | S-W13, DEF-6-003 수정 |
| TC-VA-152 | 외부 출처 분류 경계: 한도 1 로 두고 '소유자 요청 1건 + 대상 요청 1건' 을 보냈을 때, 외부로 분류된 것만 소유자 한도를 안 쓴다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_foreign_classification_by_sec_fetch_site` | 8건 통과 | PASS |  |
| TC-VA-153 | Sec-Fetch-Site 없이 Origin 만 틀린/없는 상태 변경 요청도 외부 분류 -> 소유자 한도를 쓰지 않는다. 올바른 Origin 은 쓴다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_post_with_bad_origin_is_foreign_even_without_sec_fetch` | 1건 통과 | PASS |  |
| TC-VA-154 | RateLimiter.check_foreign: 한도 N 번째까지 0, 다음은 양수 대기, 거부는 기록되지 않아 정확히 창 길이 뒤 풀림. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_ratelimiter_check_foreign_unit` | 1건 통과 | PASS |  |
| TC-VA-155 | Content-Length 가 두 번 오면(값이 같아도) 400 — 요청 밀수 방어. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_duplicate_or_conflicting_content_length_rejected` | 1건 통과 | PASS | S-W13 |
| TC-VA-156 | 같은 값의 Host 가 두 번이어도 API 는 거부(정확히 1개만 허용)한다. 헬스 경로는 면제. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_duplicate_host_same_value_rejected_but_health_exempt` | 1건 통과 | PASS | S-W02 |
| TC-VA-157 | 빈 값·공백·유니코드 숫자(위첨자 ²·¹ 은 isdigit() 가 True)·16진·지수 표기 Content-Length 는 400(str.isdigit 는 유니코드 숫자도 True 이므로 isascii 병행 필요). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_content_length_non_ascii_digits_rejected` | 7건 통과 | PASS | S-W13 |
| TC-VA-158 | Content-Length '0' 과 '0000000010' 같은 선행 0 은 유효 숫자다(과잉 차단 방지). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_10_clock_store_foreign.py::test_content_length_zero_and_leading_zeros_accepted` | 1건 통과 | PASS |  |
| TC-VA-159 | 내부 앱이 응답 시작 전에 예외를 던지면 500 problem+json + 보안 헤더, 예외 메시지는 응답에 없다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_guard_unhandled_error_before_response_is_clean_500` | 1건 통과 | PASS | S-W09 |
| TC-VA-160 | 응답이 이미 시작된 뒤 예외가 나면 두 번째 응답을 덧붙이지 않고 예외를 다시 올린다(연결 정리는 서버 몫). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_guard_error_after_response_started_is_reraised_not_double_sent` | 1건 통과 | PASS |  |
| TC-VA-161 | http/websocket 이외 스코프(lifespan)는 그대로 통과시킨다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_guard_ignores_lifespan_scope` | 1건 통과 | PASS |  |
| TC-VA-162 | 접근 로그에 쿼리 문자열·헤더 값·본문이 들어가지 않는다(method/path/status/ms/request_id 만). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_guard_logs_only_safe_fields` | 1건 통과 | PASS | S-W09 |
| TC-VA-163 | uvicorn --factory 진입점이 환경변수로 앱을 만들고 /healthz 가 200. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_app_from_env_builds_working_app` | 1건 통과 | PASS |  |
| TC-VA-164 | 라우터 자동 탐색: `_` 로 시작하는 모듈과 router 속성 없는 모듈은 제외, 나머지는 정렬해서 반환. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_discover_routers_skips_underscore_and_modules_without_router` | 1건 통과 | PASS |  |
| TC-VA-165 | 정적 폴더에 index.html 이 없으면 SPA 폴백은 problem+json 404(500 아님). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_static_dir_without_index_gives_problem_404` | 1건 통과 | PASS |  |
| TC-VA-166 | 워커 기동 시 startup_recover 가 stale_after=0 으로 호출되고, 이 함수가 예외를 던져도 워커는 작업 처리를 계속한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_worker_startup_recover_runs_with_zero_stale_and_failure_does_not_block` | 1건 통과 | PASS |  |
| TC-VA-167 | SQLite 경로: SELECT 후 UPDATE 사이에 다른 처리자가 먼저 가져가면 claim 은 None(중복 실행 방지). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_claim_loses_race_returns_none_on_sqlite` | 1건 통과 | PASS |  |
| TC-VA-168 | 429 의 Retry-After 는 남은 시간의 올림(최소 1초)이다: 0 이 되어 클라이언트가 즉시 재시도 폭주하지 않게 한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_retry_after_is_ceiling_seconds_never_zero` | 5건 통과 | PASS | S-W13 |
| TC-VA-169 | Origin 없는 요청은 상태 변경 메서드 4종에서만 외부로 분류되어 소유자 한도를 쓰지 않는다(GET/HEAD 는 소유자 한도 사용). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_missing_origin_counts_as_foreign_only_for_state_changing_methods` | 6건 통과 | PASS |  |
| TC-VA-170 | 세션 발급 시 만료된 세션 행이 정리된다(만료 행이 20개 한도를 차지하거나 쌓이지 않는다). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_session_issue_purges_expired_rows` | 1건 통과 | PASS | S-W08 |
| TC-VA-171 | 세션 사용 시 last_seen 은 현재 시각으로 갱신되고 만료 시각(절대 TTL)은 늘어나지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_session_lookup_updates_last_seen_but_not_expiry` | 1건 통과 | PASS | S-W08 |
| TC-VA-172 | 정비(stale 정리·만료 삭제)는 10분 간격: 9분59초 뒤엔 건너뛰고 정확히 10분 뒤엔 다시 실행한다(상수가 아닌 리터럴로 비교). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_worker_maintenance_interval_is_ten_minutes` | 3건 통과 | PASS |  |
| TC-VA-173 | 운영자가 쓰는 실제 CLI(`alembic upgrade head --sql` / `downgrade 0001:base --sql`)가 DB 없이 성공하고, 14개 테이블 생성 + audit_log 변경 권한 회수(REVOKE)를 포함하며, 데이터를 읽는 쪽 권한을 새로 주는 GRANT 는 없다. | 임시 PG16 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_alembic_cli_offline_upgrade_and_downgrade_render` | 1건 통과 | PASS | S-W13a |
| TC-VA-174 | 감사 detail 의 JSONB 불안정 float(지수 표기 큰 수·-0.0)는 중첩 위치와 무관하게 기록 전에 ValueError, 평범한 값은 허용(SQLite 수준, DEF-6-008 회귀). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_audit_record_rejects_only_jsonb_unstable_floats_at_any_depth` | 11건 통과 | PASS | S-W16 |
| TC-VA-175 | 정규 JSON 은 NaN/Infinity 를 거부한다(JSON 표준 밖 값이 해시 입력에 섞이지 않게). 감사 기록도 같은 이유로 실패하고 행을 남기지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_canonical_json_refuses_non_finite_numbers` | 3건 통과 | PASS | S-W16 |
| TC-VA-176 | tone 항목 안의 제어문자 경계: 0x00~0x1f 는 422, 0x20(공백)·일반 문자는 허용. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_tone_control_character_boundary` | 7건 통과 | PASS | S-W13 |
| TC-VA-177 | 잠금이 1초도 안 남았을 때 Retry-After/hint 는 0 이 아니라 1 이다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_pin_lock_retry_after_never_zero` | 1건 통과 | PASS | S-W08 |
| TC-VA-178 | 문자열이 아닌 PIN 값(정수·목록·바이트 등)은 500 이 아니라 일반 실패(401)로 처리되고 실패 횟수에 반영된다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_check_pin_non_string_input_is_plain_failure_not_crash` | 6건 통과 | PASS | S-W08 |
| TC-VA-179 | 저장 해시의 방식 표지가 scrypt 가 아니면(나머지 값이 정상이어도) 검증 실패 — 방식 혼동 방지. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_pin_hash_with_other_scheme_label_never_verifies` | 1건 통과 | PASS | S-W08 |
| TC-VA-180 | 감사 로그의 세션 대상 식별자는 12자 접두사뿐이다(세션 해시 전체가 감사에 남지 않는다). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_audit_session_target_is_truncated_id_not_full_hash` | 1건 통과 | PASS | S-W08, S-W16 |
| TC-VA-181 | enable_docs=True(개발 프로필)에서만 /docs·/openapi.json 이 열리고 /redoc 는 계속 닫혀 있다. Host 검증은 여전히 적용. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_docs_enabled_exposes_only_docs_and_openapi` | 1건 통과 | PASS | S-W04 |
| TC-VA-182 | 세션 발급 응답이 나가는 순간 다른 연결에서도 세션 행과 감사 행이 이미 보인다(발급 직후 첫 요청이 401 이 되지 않는다). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_session_row_is_committed_before_response_starts` | 1건 통과 | PASS | S-W08 |
| TC-VA-183 | 설정 변경(PIN 설정) 응답이 나가는 순간 pin_hash 가 이미 확정돼 있다 -> 바로 이어진 PIN 변경이 current_pin 없이 통과하지 못한다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_setting_change_is_committed_before_response_starts` | 1건 통과 | PASS | S-W03, S-W08 |
| TC-VA-184 | PIN 설정 직후 current_pin 없는 변경을 50번 연달아 시도해도 한 번도 통과하지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_pin_change_without_current_pin_never_succeeds_in_rapid_sequence` | 1건 통과 | PASS | S-W08 |
| TC-VA-185 | 오류 응답(검증 실패 422)의 변경은 확정되지 않는다: 같은 요청에서 먼저 바꾼 값이 남지 않는다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_failed_request_is_still_rolled_back` | 1건 통과 | PASS |  |
| TC-VA-186 | 확정(commit)이 실패하면 클라이언트는 성공(200)이 아니라 일반 500 을 받는다(예전: 성공 응답 후 조용히 유실). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_commit_failure_before_response_gives_500_not_success` | 1건 통과 | PASS | S-W09 |
| TC-VA-187 | 이 단위 소스의 모든 `ProblemError(...)` 생성(및 problem_response/reject 호출)이 hint 를 채운다(정적 검사: 새 오류 코드가 hint 없이 추가되는 회귀 방지). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_every_problem_error_in_core_unit_code_declares_a_hint` | 1건 통과 | PASS | S-W09 |
| TC-VA-188 | 실제 응답에서도 이 단위의 오류 코드(pin_invalid 422/401, pin_not_set, validation_error, setting_not_allowed, not_found, method_not_allowed, bad_content_length, csrf/session)가 비어 있지 않은 한국어 hint 를 돌려준다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_problem_responses_from_this_unit_carry_korean_hint` | 1건 통과 | PASS | S-W09 |
| TC-VA-189 | 처리기가 없는 작업 유형은 재시도 없이 failed 로 기록되고 오류 필드는 "no_handler: ..." 형식이다. | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_job_without_handler_fails_with_hint_text` | 1건 통과 | PASS |  |
| TC-VA-190 | 실서버: 세션 발급 직후 첫 요청이 401 이 되지 않고, PIN 설정 직후 current_pin 없는 PIN 변경이 단 한 번도 통과하지 않는다(요청마다 새 연결; 세션 발급 8회 + PIN 변경 시도 4회, 발급 한도 때문에 반복 수는 제한). 한계: 수정 전 코드에서도 이 환경에서는 6회 모두 통과해 경쟁을 재현하지 못했다 -> 결정적 증명은 TC-VA-182/183, 이 시험은 실서버 스모크. | 실서버 기동 | `pytest tests/verify_wa/test_va_08_static_and_live.py::test_live_read_after_write_sees_committed_state_pin_cannot_be_bypassed` | 1건 통과 | PASS | S-W08, DEF-VA-010 회귀 |
| TC-VA-191 | 쓰기 뒤 409 로 실패한 요청의 변경은 확정되지 않고(롤백), 성공(200) 요청의 변경은 확정된다(성공 응답에만 조기 commit). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_error_response_after_write_is_rolled_back_but_success_is_committed` | 1건 통과 | PASS | S-W12 |
| TC-VA-192 | 예외 없이 '반환'된 4xx(예: 저장된 오류 응답 재생)의 쓰기도 응답이 나가기 전에 확정된다(상태 코드 때문에 경합이 남지 않는다). | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_12_commit_before_response.py::test_returned_4xx_response_commits_before_it_is_sent` | 1건 통과 | PASS | S-W12 |
| TC-VA-193 | 새 DB(0001->0002 한 번에 적용, 인프라와 같은 기본 권한): 앱 계정은 alembic_version 을 읽기만 하고 INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER·구조 변경이 모두 거부, 다른 테이블 DML·audit_log 제한은 그대로 | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_app_role_cannot_modify_alembic_version_on_new_database` | 1건 통과 | PASS | S-W16, S-W13a (DEF-VA-012) |
| TC-VA-194 | 이미 0001 로 배포된 DB(앱 계정이 버전표 DML 보유)에 0002 적용 시 권한 회수, 재실행 안전, 데이터 보존, 0002->0001 되돌리기는 권한 복원 | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_upgrade_existing_0001_database_revokes_version_table_dml` | 1건 통과 | PASS | S-W16, S-W13a (DEF-VA-012) |
| TC-VA-195 | 역할 없는 환경에서도 0002 가 성공(건너뜀)하고 downgrade base 까지 순환 가능 | 임시 PG16 | `pytest tests/verify_wa/test_va_07_postgres.py::test_upgrade_without_app_role_still_works_and_offline_render_has_revoke` | 1건 통과 | PASS | S-W13a |
| TC-VA-196 | 실제 CLI 오프라인 렌더: 0002 가 alembic_version 의 INSERT/UPDATE/DELETE/TRUNCATE 를 앱 역할에서 회수하고 SELECT 는 건드리지 않으며 헤드는 0002 하나 | SQLite 임시 DB+가짜 시계 | `pytest tests/verify_wa/test_va_11_guard_worker_misc.py::test_alembic_offline_render_revokes_version_table_privileges` | 1건 통과 | PASS | S-W16 |

### 4-1. 인수 조건 <-> 시험 추적 (연결 없는 AC 없음)
| AC | 내용 | 시험 ID | 결과 |
|---|---|---|---|
| AC-1 | 허용 Host/Origin 이 아니면 상태 변경 불가(403), 세션·CSRF 없으면 401/403, 가드 순서(Host -> 크기 -> 속도 -> Origin/Sec-Fetch-Site -> 세션 -> CSRF) | TC-VA-001~015, 039~042, 074, 133, 140, 156, 161 | 충족 |
| AC-2 | 쿠키 속성이 정확하고 DB 에 토큰 원문 없음, 세션 만료·20개 상한 | TC-VA-029~038, 127, 128, 170, 171 | 충족 |
| AC-3 | 설정 PATCH 로 enable_live 등 금지 키 변경 불가(400), 허용 키 범위 검증, 4개 키 제한 | TC-VA-056~065, 147~150, 176 | 충족 |
| AC-4 | 오류 응답에 스택·경로·예외 메시지·입력 값 없음(500 포함), RFC 9457 형식 | TC-VA-025, 026, 088~094, 159, 160, 162 | 충족 |
| AC-5 | 감사 로그 변조·삭제·타임스탬프 변경 탐지, 해시 체인 독립 재구현 일치, 동시 기록 | TC-VA-080~087, 121, 122, 143, 174, 175, 180 | 충족(꼬리 절단은 알려진 제한, TC-VA-084 특성화, 방어선은 DELETE 권한 회수 TC-VA-118) |
| AC-6 | 같은 키 재전송 부작용 1회, 다른 요청 422, 키 없음 400, 처리 중 409, 24시간 TTL | TC-VA-066~079, 123 | 충족 |
| AC-7 | 잡 중복 처리 없음(SKIP LOCKED·CAS), 재시도 없음, stale 재큐, SIGTERM 완료 후 종료 | TC-VA-100~113, 124, 137, 142, 167, 172, 189 | 충족 |
| AC-8 | 마이그레이션 오프라인 렌더 + 실제 PG 적용, 앱 계정이 감사 로그 수정·삭제·TRUNCATE 불가, **버전표 alembic_version 은 SELECT 만(DEF-VA-012)** | TC-VA-114~120, 173, 193~196 | 충족(PG 16 한정) |
| AC-9 | (조정자 추가) 변경은 응답이 나가기 전에 확정, PIN 우회 불가(DEF-VF-B01) | TC-VA-182~186, 190~192 | 충족 |
| AC-10 | (조정자 추가) 이 단위의 오류 코드는 한국어 hint 를 채움(DEF-VF-B02) | TC-VA-187~189 | 충족 |
| AC-11 | PIN 잠금(5회 -> 5분, 2배, 최대 1시간), PIN 해시·형식 | TC-VA-043~055, 125, 126, 177~179 | 충족 |
| AC-12 | 속도 제한·요청 크기 | TC-VA-016~024, 151~158, 168, 169 | 충족 |
| AC-13 | 로그 비밀 마스킹 | TC-VA-095~099, 162 | 충족 |
| AC-14 | KST/PT 날짜 경계(자정·DST 전환·윤일·naive 거부) | TC-VA-144~146 | 충족 |

## 5. 커버리지
- 측정: `pytest tests/core tests/verify_wa --cov=ytweb.core --cov=ytweb.app --cov=ytweb.worker --cov=ytweb.migrate --cov=ytweb.routers.{health,auth,settings,audit} --cov-branch` (PostgreSQL 포함). 이 단위 소유 파일 합계 **1038문장 중 20 미실행, 256분기 중 4 부분 -> 98%**.
  - 100%: app, audit, canonical, clock, deps, errors, idempotency, jobs, logsetup, pin, ratelimit, sessions, settings_store, 라우터 4종
  - `core/guard.py` 98%: 158->163, 176 — 158: 본문 읽기 중 한도 초과 후 응답 대체 경로의 분기 일부, 176: 이미 응답이 나간 뒤 예외가 난 경우 로그만 남기는 `finally` 분기 일부. 둘 다 ASGI 서버 내부 상태 의존이라 TestClient/ASGI 직접 호출로는 도달 불가(분기 조합), 직접 도달 가능한 쪽은 TC-VA-017·160 이 검증
  - `migrate.py` 96%: 55 = `if __name__ == "__main__"` 줄(프로세스 진입점, 임포트로는 실행 안 됨)
  - `worker.py` 84%: 37-39(도메인 패키지 없음 경로, W-BE-B 모듈이 존재해 도달 불가), 43-44(도메인 모듈 임포트 실패 로그: W-BE-B 모듈을 일부러 깨뜨리지 않음), 106(기동 정리 로그), 116-131·135(`main()`/`__main__`: 시그널 등록·무한 루프, 하위 프로세스로 TC-VA-113·137 이 실행 검증하지만 하위 프로세스의 커버리지는 측정하지 않음)
- 분기 커버리지는 위 수치에 포함. 기능 커버리지: 인수 조건 14/14 연결.
- 구현자 보고(95%)와 차이는 독립 시험이 worker/migrate/app 경로를 더 채운 결과.

## 6. 결함(Defect) 목록
이전 중지 세션이 발견해 시험(strict xfail)로 남긴 9건은 ID `DEF-6-00n` 이었고 여기서는 `DEF-VA-00n` 으로 통일한다(번호 동일). 전부 이 단위 소유 파일 안의 결함이라 직접 고치고 회귀 시험을 추가한 뒤 전체를 다시 돌렸다(규칙 F).

| ID | 설명 | 재현 절차 | 심각도 | 상태 | 조치 내용 |
|---|---|---|---|---|---|
| DEF-VA-001 | Host 헤더가 둘 이상일 때 마지막 값만 검사해 첫 값이 비허용이어도 통과(방어 심층 결함, 실서버 h11 은 앞단에서 거부) | ASGI 로 `host: evil.com`, `host: 127.0.0.1:8080` 순서로 전송(TC-VA-005) | Low | Fixed | `guard.py`: Host 값을 전부 모아 정확히 1개여야 하고 허용 목록에 있어야 함. 회귀 TC-VA-004·005·156(값이 같아도 2개면 거부, 헬스는 면제) |
| DEF-VA-002 | `int()` 가 `-1`, `+5`, `1_0`, 유니코드 숫자를 받아 Content-Length 검사를 통과(유니코드 위첨자는 `isdigit()` 도 참이라 500 가능) | Content-Length `-1`(TC-VA-019), `²`(TC-VA-157) | Low | Fixed | `guard.py`: ASCII 숫자만(`isascii() and isdigit()`), Content-Length 가 2개 이상이면 400. 회귀 TC-VA-018·019·155·157·158 |
| DEF-VA-003 | 속도 제한이 Origin/Sec-Fetch-Site 검사보다 앞이라 외부 웹사이트가 로컬 주소로 보낸 요청이 소유자의 세션 발급(분당 10)·전역 한도를 소진시켜 소유자를 막을 수 있음(DoS) | 외부 출처 POST 10회 후 소유자 로그인 -> 429(TC-VA-024) | Medium | Fixed | `guard.py`/`ratelimit.py`: 출처가 소유자 화면이 아닌 요청(`Sec-Fetch-Site` same-origin/none 이외, 또는 상태 변경인데 Origin 불일치)은 별도 창(`check_foreign`)에서 세고 소유자 한도를 쓰지 않음(외부 창도 한도 있음). 동작 변경 없음(deps 가 어차피 403). 회귀 TC-VA-024·151~154 |
| DEF-VA-004 | PIN 형식·멱등성 키 정규식이 `re.match` + `$` 라 끝에 줄바꿈이 붙은 값(`1234\n`)을 통과 | PIN `1234\n` 설정(TC-VA-050), 키 단위 시험(TC-VA-079) | Low | Fixed | `pin.py`, `idempotency.py`: `fullmatch`. 회귀 TC-VA-049·050·067·079 |
| DEF-VA-005 | 감사 조회 `page` 상한이 없어 `page=10**18` 이면 offset 이 64비트를 넘어 DB 오류 -> 500 | `GET /api/v1/audit?page=1000000000000000000`(TC-VA-086) | Low | Fixed | `routers/audit.py`: `le=1_000_000`(범위 밖은 422). 회귀 TC-VA-085·086 |
| DEF-VA-006 | SQLAlchemy 예외 문자열의 `[parameters: ...]` 가 로그에 그대로 실려 바인딩 값(PIN 해시 등)이 로그에 남을 수 있음 | DB 오류를 일으키는 프로브 라우트(TC-VA-090) | Medium | Fixed | `logsetup.py`: `[parameters: ...]` 를 마스킹. (`db/session.py` 에 `hide_parameters=True` 를 넣는 것이 더 근본이나 다른 단위 소유라 질문 목록에 기록). 회귀 TC-VA-090·099 |
| DEF-VA-007 | `Authorization: Bearer <토큰>`/`Basic <자격증명>` 에서 키=값 정규식이 스킴 단어만 가리고 실제 토큰이 로그에 남음 | `mask_secrets("Authorization: Bearer abc.def.ghi")`(TC-VA-096) | Medium | Fixed | `logsetup.py`: Authorization 뒤 스킴+값 전체를 마스킹. 회귀 TC-VA-095·096·097 |
| DEF-VA-008 | PostgreSQL JSONB 가 지수 표기 큰 float(1e22)·-0.0 을 정규화해 읽은 값의 해시가 달라져 정상 기록이 "변조"로 판정됨(잠재: 현재 호출처는 float 를 쓰지 않음) | PG 에서 `detail={"v": 1e22}` 기록 후 `verify_chain`(TC-VA-122) | Low(잠재) | Fixed | `audit.py`: 해당 float 를 기록 전에 `ValueError` 로 거부(평범한 float 는 허용). 회귀 TC-VA-121·122·174 |
| DEF-VA-009 | PIN 실패 횟수 갱신이 읽기-수정-쓰기라 동시 요청에서 갱신이 유실되어 잠금(5회)이 무력화됨(동시 추측으로 5회를 넘겨 시도 가능) | PG 에서 8 스레드 동시 틀린 PIN(TC-VA-125), HTTP 10건 동시(TC-VA-126) | **High** | Fixed | `pin.py`: PostgreSQL 트랜잭션 advisory lock 으로 `check_pin` 직렬화 + 락 획득 후 상태 행 갱신 읽기. 회귀 TC-VA-125·126 (수정 후 401 이 4건 이하) |
| DEF-VA-010 (= 조정자 DEF-VF-B01) | `core/deps.get_session` 이 `yield` 뒤에서 commit 하는데 FastAPI 0.143.0 은 이 종료 코드를 **응답을 보낸 뒤** 실행한다. 바로 이어진 요청이 옛 상태를 읽음: 세션 발급 직후 첫 요청 401, 방금 만든 작업 404, **PIN 설정 직후의 PIN 변경이 `current_pin` 없이 통과(W-FE 관찰: 40회 중 7회)**. 확정이 실패해도 클라이언트는 성공 응답을 받고 변경이 조용히 유실됨 | TC-VA-182(세션 발급 응답 시작 순간 다른 연결로 조회 -> 세션/감사 행 0건), TC-VA-183(PIN 설정 응답 시작 순간 pin_hash 0건), TC-VA-186(commit 실패 시 200) | **High**(PIN 우회 연결) | Fixed | `guard.py`: 응답 시작 직전에 요청의 열린 DB 세션을 commit(스레드풀 실행), 실패하면 일반 500(`internal_error`). `deps.get_session` 은 세션을 `scope["ytweb_open_sessions"]` 에 등록(W-BE-B 라우터 수정 불필요, 설치 버전 그대로 동작). 예외로 끝난 요청은 의존성 종료에서 이미 rollback 되어 이 commit 은 무효(TC-VA-185·191). **수정 전 FAIL 증명**: 수정 전 사본(`.harness-tmp/va/pre_fix`)에서 TC-VA-182·183·186 실패(+187·188 은 DEF-VA-011), 수정 후 통과. 회귀 TC-VA-182~186, 191, 192, 실서버 스모크 190. **주의**: 실서버 경합(190)은 이 환경의 수정 전 코드에서 6회 모두 재현되지 않았다 -> 결정적 증명은 182/183 이며 190 은 스모크로만 센다. 변이 점검 M124~M127·M134 |
| DEF-VA-011 (= 조정자 DEF-VF-B02) | `pin_invalid`, `pin_not_set`, `validation_error`(설정), `no_handler`, 404/405(`http_error`), `bad_content_length` 가 `hint` 를 비움 | 코드 읽기, TC-VA-187(정적), TC-VA-188(실응답) | Low | Fixed | 이 단위가 만드는 모든 `ProblemError`/응답에 한국어 hint 추가. `title_invalid` 등 도메인 코드는 W-BE-B 소유라 손대지 않음. 정적 시험 TC-VA-187 이 이후 새 코드가 hint 없이 추가되는 것을 막음. 변이 M128~M133 |

- 직접 고친 파일(전부 이 단위 소유): `ytweb/core/{guard,ratelimit,pin,idempotency,logsetup,audit,deps,jobs}.py`, `ytweb/routers/{audit,settings}.py`, `ytweb/app.py`, `ytweb/migrate.py`(import 정렬만), 정적 검사 자동 수정(import 정렬·`datetime.UTC`·불필요 noqa·미사용 import, 동작 불변) — 소유 범위 안의 `ytweb/core/*`, `app.py`, `worker.py`, `routers/{auth,settings,audit,health}.py`.
- **작업 중 실수 기록**: 정적 검사 자동 수정(`ruff --fix`)을 `ytweb` 전체에 돌려 W-BE-B 소유 파일 10개(`routers/{videos,suggestions,changes,batches}.py`, `domain/{schemas,videos,suggestions,changes,reports,batches}.py`)의 import 줄 정렬이 바뀌었다. 수정 직후 발견해, 변경 전 사본(`.harness-tmp/va/pre_fix`)과 비교해 "ruff 정렬만 바뀜"을 확인한 뒤 **바이트 단위로 원상 복구**했다(복구 후 비교 일치, `tests/domain` 175건 통과). 다른 단위 파일의 최종 내용은 바뀌지 않았다.
- DEF-VA-012 (= W-INF 독립 검증 DEF-VI-002, Low, **Fixed**): 앱 DB 계정 `ytweb_app` 이 `alembic_version` 을 수정·삭제할 수 있었다(Alembic 이 소유자 계정으로 만든 표라 인프라의 기본 권한 `GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES` 가 적용됨). 설계상 앱 계정은 구조 변경 불가이고, 버전 행이 바뀌면 다음 업그레이드가 오동작한다. 재현: 앱 역할로 `UPDATE alembic_version SET version_num='0000'`(TC-VA-193). 조치: **새 마이그레이션 `alembic/versions/0002_revoke_alembic_version_dml.py`**(0001 불변) — 역할이 있으면 `REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON alembic_version FROM ytweb_app`(SELECT 유지), downgrade 는 INSERT/UPDATE/DELETE 복원, 역할 없는 환경은 건너뜀. 새 DB(0001->0002 연속 적용)와 이미 0001 인 기존 DB 양쪽에서 실제 PG 16 으로 확인. 수정 전 FAIL: REVOKE 를 무력화한 사본에서 TC-VA-193·194 실패. 변이 5곳(UPDATE/TRUNCATE/TRIGGER 누락, 복원 GRANT 누락, down_revision 변경) 전부 잡힘. 기존 시험의 헤드 기대(0001->0002) 3곳 갱신(`tests/core/test_postgres.py`, `tests/core/test_migration.py`, TC-VA-116). **한계/제안(W-INF 소유, 코드 미수정)**: 복원 후 인프라가 `GRANT ... ON ALL TABLES` 를 다시 주면 0001 의 audit_log 회수처럼 이 회수도 무효가 된다 -> `web/docker/db/audit-guard.sql` 에 `REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.alembic_version FROM ytweb_app;` 추가를 제안한다.
- 열린 결함: **없음(Open 0건)**.

### 결함 0건이 아니므로 추가로 남기는 확인 근거
- 구현자 시험 `tests/core` 212건은 DEF-VA-001~011 을 하나도 잡지 못했다(수정 전에도 전부 통과). 이 결함들은 독립 시험·변이·소스 읽기로 발견했다.
- 수정 후: 구현자 212 + 독립 481 = 693건 전부 통과, W-BE-B `tests/domain` 175건 통과(회귀 없음, 건너뜀 7은 PostgreSQL 전용).

## 7. 테스트 환경 정리(Teardown) 확인 — 규칙 K
- 이번 테스트에서 생성한 임시 아티팩트 목록: `.harness-tmp/va/venv/`(가상환경), `.harness-tmp/va/pg/`(임시 PostgreSQL 16 데이터·소켓·로그, 포트 54331), DB `ytweb_va`, `ytweb_va_m0~3`, `.harness-tmp/va/mut/`(변이 사본 w0~3 + 로그), `.harness-tmp/va/pre_fix/`(수정 전 사본), `.harness-tmp/va/gen/`(junit·표 생성), `.harness-tmp/va/.coverage`, `PROGRESS.md`. 저장소 안의 캐시(`web/backend/.ruff_cache`, `.pytest_cache`, `__pycache__`, `.coverage`)도 정리.
- 위 아티팩트를 전부 `.harness-tmp/` 하위에서만 생성했는가 (규칙 K 1번): [x] 예 (저장소 안 캐시 파일은 도구가 만든 것을 삭제)
- 정리(삭제) 완료 여부: 완료. PostgreSQL 은 `pg_ctl stop` 으로 중지("server stopped") 후 `.harness-tmp/va` 전체 삭제. `pgrep` 으로 `va/pg`·`ytweb_va`·`run_mut`·`uvicorn` 프로세스 잔존 없음 확인. 다른 에이전트의 폴더(`.harness-tmp/vb` 등)·프로세스는 건드리지 않음. 남은 `.harness-tmp/` 내용: `vb`(다른 단위 소유)만.
- 정리 후 `git status` 실행 결과: **실행하지 않음** — 공통 지시서 3절이 git 명령을 금지하므로 `git status` 원문을 첨부할 수 없다(오케스트레이터가 웨이브 종료 후 전체 트리 점검). 대신 파일시스템으로 확인: 이 단위가 의도해 남긴 변경은 (a) `web/backend/ytweb/core/*`, `ytweb/app.py`, `ytweb/migrate.py`, `ytweb/routers/{audit,settings}.py` 결함 수정, (b) `web/backend/tests/verify_wa/` 시험 파일 16개 + `mutation/`(변이 목록·실행기·회전별 결과 JSON·표 생성기), (c) `docs/harness/units/web-WU-BE-A-test.md`, `docs/harness/verify-log_web-WU-BE-A-test.md` 뿐이다. 미추적 잔여 임시 파일 없음. 참고: `src/youtube_title.egg-info/` 는 `pip install -e` 가 만드는 저장소 루트 산출물로 다른 단위의 가상환경과 공유되어 삭제하지 않았다(`.gitignore` 대상 여부는 오케스트레이터 확인).
- 병렬 실행이었다면: 동시 작업 중인 다른 단위(W-BE-B, W-FE, W-INF)의 변경분(`web/frontend/**`, `web/backend/tests/verify_wb/`, `.harness-tmp/vb|vf|vi` 등)은 그 단위 소유이고 이 실행의 소유가 아니다. "이 실행이 만든 임시 아티팩트·미추적 잔여물이 없음"을 위 정리 확인으로 판정. 웨이브 종료 후 전체 점검은 오케스트레이터 몫.
- DEF-VA-012 추가 검증(2026-10-11, 규칙 K 재수행): `.harness-tmp/va/` 에 가상환경·임시 PG(54331)를 새로 만들어 시험하고 끝나면 PG 중지·`.harness-tmp/va` 삭제·저장소 안 캐시 삭제. 다른 에이전트 폴더(`.harness-tmp/int`, `vb` 등)·프로세스는 건드리지 않음.
- 이번 테스트 도중 강제 중단(TaskStop 등)이 있었는가: [x] 있음 — 세션 한도와 컨테이너 재시작으로 두 번 중단. 재개 시 `.harness-tmp/va` 의 가상환경·데이터 폴더를 재사용하고 죽은 PostgreSQL 만 다시 띄웠으며, 중단 전 남은 변이 점검 부산물(PG 역할 `ytweb_app` 등)을 확인해 정리 직전에 임시 클러스터째 삭제.
- 7절 확인 완료.

## 8. 리스크 및 잔존 이슈
- 이번 테스트로 커버되지 않는 알려진 리스크(PASS로 세지 않음): ① 실제 브라우저(Chrome/Edge)에서 `Secure` 없는 쿠키·`SameSite=Strict`·`Sec-Fetch-Site` 동작(Q-WA-1) ② PostgreSQL 17·Docker·nginx 경유(07단계/사용자 PC) ③ Python 3.12 ④ 다중 프로세스 환경의 속도 제한·세션 정책 ⑤ 감사 로그 **꼬리 절단**(마지막 행 삭제)은 해시 체인만으로는 탐지되지 않음(알려진 제한, 방어선은 앱 계정의 DELETE/TRUNCATE 회수 TC-VA-118 + 이후 인프라가 `GRANT ALL ON ALL TABLES` 를 다시 주면 방어선이 사라짐 TC-VA-120 특성화) ⑥ 실서버 경합(DEF-VA-010)을 수정 전 코드에서 재현하지 못함: 결정적 시험으로 증명했지만 실서버 경합 자체는 W-FE 의 실서버 시험(`VF_LIVE_SETTLE_MS=0`)과 07단계에서 다시 확인 필요
- 권고(결함 아님): R-1 scrypt N=2^14 는 OWASP 권고(N>=2^17)보다 약하다(TC-VA-131 이 현재 값을 고정). 4~12자리 숫자 PIN 은 해시 강도보다 잠금 정책이 방어선. R-2 `/healthz`·`/readyz` 는 Host 면제이고 `/readyz` 응답에 `mode`(demo) 가 있어 DNS 리바인딩으로 읽힐 수 있다(민감도 낮음, 노트 3장 4번 결정 재확인 요청). R-3 `db/session.make_engine` 에 `hide_parameters=True` 를 두면 로그 마스킹(DEF-VA-006)과 별개로 근본 방어가 된다(다른 단위 소유). R-4 설정 `YTWEB_SESSION_TTL_HOURS` 가 매우 크면 `timedelta` 오버플로로 로그인이 500 이 된다(소유자가 설정하는 값, Low). R-5 `routers` 에 남은 ruff 기본 규칙 위반: B008 24건(FastAPI `Depends` 관용구), G201 5건(`log.error(exc_info=True)`) — 프로젝트에 린트 설정이 없어 기술부채로만 기록. R-6 `/api` 로 시작하는 임의 경로(`/apix`)도 속도 제한 대상(무해).
- 후속 조치가 필요한 항목: 07단계에서 nginx 경유 실서버로 DEF-VA-010 경합·쿠키·속도 제한 재확인, W-FE 의 "작업 404 재확인" 임시 완화 제거 여부 결정(W-FE Q3), 사용자 질문 목록은 검증 로그 하단.

## 9. 결론 및 판정
- [x] PASS (수용된 알려진 제한 포함) — 다음 단계 진행 가능 (7절 Teardown 확인 완료가 전제조건)
  - 근거: 인수 조건 14/14 시험 연결·통과(693/693), 변이 점검 마지막 회전에서 놓침 0(동치 1건 근거 기록), 커버리지 98%(미실행 줄 사유 기록), 정적 검사(F·E9) 통과, Open 결함 0건(12건 전부 Fixed + 회귀 시험), 정리 완료. 단, 2절·8절의 미수행 항목(실브라우저, PG 17, Docker/nginx, Python 3.12)은 PASS로 세지 않았고 후속 단계로 넘긴다.
- [ ] CONDITIONAL PASS
- [ ] FAIL

## 10. 내부 검증 (최소 2회, `verification-log-template.md` 사용)
- 1차 검증 결과 요약: 작성자 관점 — 이전 세션 시험 143건 검토·재사용, 결함 9건 확인(구현자 시험은 전부 통과하던 것). 수정·회귀 시험 추가.
- 2차 검증 결과 요약: 심사자 관점 — 변이 점검(1회전 실제 8곳+동치 1곳 놓침 -> 보강, 2회전 7곳+동치 -> 보강, 3회전 놓침 0), 조정자 추가 결함 B01·B02 처리 후 4~6회전에서 새 변이 포함 재점검(M124 는 설계 재검토 후 해소), 소스 직접 읽기. 최종 회전 놓침 0.
- 검증 로그 파일 경로: `docs/harness/verify-log_web-WU-BE-A-test.md`

### 부록 A. 변이 점검 (코드를 일부러 망가뜨려 시험이 잡는지 확인)
- 방식: 변이 134곳(`tests/verify_wa/mutation/mutants.py`, 구현 노트의 후보 7개와 겹치지 않는 것 위주: 안전 로직의 경계 한 칸·반전·제거·상수 변경). 각 변이는 격리 사본(`.harness-tmp/va/mut/w0~3`)에서만 적용하고 원본은 바꾸지 않았다. 변이마다 대상 문자열이 소스에 **정확히 1곳**인지 사전 확인(실행기가 자동 검사). 시험은 `tests/verify_wa` 전체를 `-x` 로 실행, 하나라도 실패하면 "잡음". PostgreSQL 이 필요한 변이는 직렬로 실제 PG 시험 포함. 제어군 2건(M000 PG, M001 비PG: 변이 없음)은 반드시 "생존"해야 하며 하네스가 정상임을 증명한다.
- 하네스 결함 기록: 1회전(r1)은 PG 시험이 클러스터 전역 역할 `ytweb_app` 으로 서로 충돌하고 복사본에 `web/docker` 가 없어 **무효**였다(전부 "잡힘"으로 보였으나 제어군 실패로 발견) -> 폐기하고 1b 부터 다시 했다(`r1_INVALID...` 로그는 보존하지 않음). PG 변이 5곳(M43·M56·M58·M65·M104)의 1b 결과는 가짜 잡음이라 2회전에서 재검증.
| 회전 | 변이 수 | 놓침 | 놓친 변이와 조치 |
|---|---|---|---|
| 1b | 105 | 9 | M07 Retry-After 올림(0 허용), M13 DELETE 외부 분류, M26 만료 세션 정리, M27 last_seen 갱신, M45 멱등성 TTL(시험이 모듈 상수를 그대로 써서 변이를 따라감 -> 리터럴 24시간으로 교체), M57 감사 float 거부, M98 보관 48시간(같은 이유), M105 problem `type` 형식, M90(동치) -> 시험 TC-VA-168~172·174 등 추가 |
| 2 | 118 + 제어 2 | 7(+동치 M90) | M103 NaN 거부, M108 제어문자 경계 0x1f, M110 PIN 잠금 Retry-After 0, M111 비문자열 PIN, M112 해시 방식 표지, M113 감사 세션 식별자 12자, M114 redoc(동치 아님: enable_docs 시 /redoc 닫힘) -> TC-VA-175~181 추가 |
| 3 | 123 + 제어 2 | 0 (M90 동치만) | 제어군 M000 이 1회 실패(동시에 내가 다른 시험을 돌려 부하가 높았고 실서버 읽기 시간 5초가 부족) -> 읽기 대기 15초로 완화, 부하 없이 재실행 시 통과 |
| 4 | 133 + 제어 2 | 1 | M124(응답 코드 400 이상도 조기 commit): 분석 결과 예외로 끝난 요청은 이미 rollback 이라 동치이나 **반환된 4xx 응답의 commit 은 조기에 해야 일관**하므로 상태 코드 조건을 제거하도록 설계 정정 + TC-VA-191·192 추가 |
| 5 | 135(133 + 제어 2) | 1 (M124, 위 설계 정정 전 코드) | 위와 동일 |
| 6(최종, 정정 코드의 가드·의존성·제어 관련 25곳 재점검: M01~M15, M08, M115, M124~M127, M131, M134, 제어 2, M90) | 25 | **0** (제어군 2 + 동치 M90 만 생존) | 최종 회전 놓침 0 |
- 최종 회전 외의 변이(M16~M123 등)는 5회전(정정 직전 코드)에서 전부 잡혔고, 정정은 `guard.py` 의 commit 조건 한 곳이라 해당 영역 변이를 6회전에서 다시 확인했다. (6회전이 전체 133곳 전수가 아니라는 사실을 숨기지 않는다. 전수 마지막 회전은 5회전이며 놓침은 정정 대상 M124 하나였다.)
- 동치(잡을 수 없음) 1건: **M90** `docs_url="/docs" if enable_docs else None` -> `"/docs"`: FastAPI 는 `openapi_url` 이 None 이면 docs 를 아예 마운트하지 않으므로 동작이 같다. 실제로 의미 있는 변이는 `openapi_url`(M116)이며 잡힘.
- 잡힘 수치: 5회전(전수) 실제 변이 133곳 중 131곳 잡힘, 동치 1(M90), 놓침 1(M124) -> M124 정정(+M134 추가) 후 6회전에서 0 놓침.
- 경계 변이 예: M03/M04(1MB 경계 한 칸), M33/M38(PIN 5회), M34/M35/M36(5분·1시간·2배), M20/M23(세션 TTL), M21/M22(20개 상한), M44/M45(24시간), M61/M62/M67(stale 10분·시도 3회), M16/M17(속도 제한 창 경계).

### 부록 B. 공유 문서 갱신 요청 (오케스트레이터, 규칙 H·G)
| 문서 | 항목 | 컬럼 | 값 |
|---|---|---|---|
| `traceability.md` | 웹 보안 요구 S-W02·S-W03·S-W04·S-W08·S-W09·S-W12·S-W13·S-W13a·S-W16 의 W-BE-A 행 | 단위테스트 | TC-VA-001~196 + 구현자 TC-WA-001~157, 판정 PASS(수용된 알려진 제한 포함), 결함 DEF-VA-001~012 전부 Fixed |
| `decisions.md` | ① 응답 전 commit(guard) 방식 채택: `Depends(scope="function")` 대신 미들웨어 훅(다른 단위 라우터 수정 불필요) ② 외부 출처 요청은 속도 제한 별도 창 ③ PIN 직렬화 advisory lock ④ 감사 detail 에서 지수 표기 큰 float·-0.0 금지 ⑤ Host 헤더는 정확히 1개 | — | 기록 요청 |
| `DESIGN.md` 검증 대기 V-01 | 상태 | — | W-BE-A 독립 검증 완료(PASS, 수용된 제한 포함). W4·W9·부록 A-1 에 DEF-VA-001~012 반영 필요(출처 검사 선행 순서에 "속도 제한은 소유자/외부 분리", "응답 전 commit" 추가) |
| `web/docker/db/audit-guard.sql`(W-INF 소유) | 복원 후 재회수 | — | 제안: `REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLE public.alembic_version FROM ytweb_app;` 추가(DEF-VA-012) |
| `API.md` 1·3장 | 오류 응답 | — | 400 `bad_content_length`, 422 감사 `page` 상한 1,000,000, 429 외부 출처 별도 창 |
