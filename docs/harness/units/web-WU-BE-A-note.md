# 단위 노트 — W-BE-A (백엔드 기반)

| 항목 | 내용 |
|---|---|
| 근거 | `docs/yt/WEB_DESIGN.md` §3·§5·§7·§10, DEC-032~038, 조사축 D(`01-axisD-local-web-security.md`) |
| 속도 트랙 | 전달받은 표기 없음 -> L3 |
| 병렬 실행 | 예(병렬 웨이브): 동시 단위 W-BE-B(도메인), W-FE, W-INF. 이 단위는 자기 소유 범위만 수정함 |
| 작성 | 5단계 구현. 결과서·검증 로그는 6단계가 따로 작성 |

## 1. 만든 파일 (모두 `web/backend/` 아래)
- `ytweb/core/`: `errors.py`, `clock.py`, `canonical.py`, `audit.py`, `idempotency.py`, `jobs.py`, `settings_store.py`, `deps.py`, `sessions.py`, `pin.py`, `guard.py`(ASGI 미들웨어), `ratelimit.py`, `logsetup.py`
- `ytweb/app.py`, `ytweb/worker.py`, `ytweb/migrate.py`
- `ytweb/routers/__init__.py`(없어서 빈 패키지 표지로 생성), `health.py`, `auth.py`, `settings.py`, `audit.py`
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/0001_initial.py`
- `pyproject.toml`, `requirements.in`, `requirements.txt`(해시 잠금), `requirements-dev.in`, `requirements-dev.txt`(해시 잠금)
- `tests/__init__.py`, `tests/conftest.py`, `tests/core/` (파일 12개, 테스트 TC-WA-001~157)
- 수정한 소유 외 파일: 없음(`db/*`, `config.py` 미수정)

## 2. 공개 인터페이스 요약 (WEB_DESIGN §10 시그니처 유지)
- `errors.ProblemError(status, code, title, detail="", hint="", headers=None)`, `problem_body(...)`
- `deps`: `get_session`, `get_web_settings`, `get_policy`, `get_clock`, `require_session`, `require_csrf`, `get_idempotency_key`(추가), `verify_same_origin`(추가). FastAPI 의존성이라 `request` 를 주입받는 인자가 내부에 있으나 `Depends(...)` 사용법은 §10 과 동일. `SessionInfo` 는 `core.sessions` 에 정의.
- `audit.record(session, *, actor, action, target_type, target_id, detail, now)`, `audit.verify_chain(session)` (+`compute_hash`)
- `idempotency.run_idempotent(session, *, key, route, request, now, handler, required=True)`
- `jobs.enqueue`, `register_handler`, `update_progress` (§10) + `claim`, `complete`, `fail`, `requeue_stale`, `process_next`(워커용)
- `settings_store.get_web_setting`, `effective_daily_cap` (§10) + `set_web_setting`, `delete_web_setting`
- `clock.kst_today`, `clock.pt_date`, `clock.utcnow`
- `app.create_app(settings=None, *, clock, router_modules, rate_limits, time_fn)`, `app.app_from_env()`(uvicorn `--factory ytweb.app:app_from_env`), `app.discover_routers()`
- 앱 상태: `app.state.{web_settings, engine, session_factory, policy, clock}`. W-BE-B 의 테스트는 `create_app(settings, clock=..., router_modules=[...])` 로 자기 라우터만 올릴 수 있다.
- 워커: `python -m ytweb.worker`. 마이그레이션: `python -m ytweb.migrate`.
- 추가 엔드포인트: 루트 `/healthz` `/readyz` 와 `/api/healthz` `/api/readyz`.

## 3. 설계 결정과 근거
1. **출처 검증**(코디네이터 지시, 조사축 D SEC-D02): 상태 변경·세션 발급은 `Sec-Fetch-Site` 가 있으면 `same-origin` 만 통과(`same-site`/`cross-site`/`none` 거부), 그리고 **Origin 은 항상** 허용 출처(`http://<allowed_hosts>`)와 정확히 일치해야 한다(없음/`null` 거부). 헤더가 없는 비브라우저 클라이언트는 Origin 일치만으로 통과. 출처 검증은 세션 확인보다 먼저(비허용 출처에 세션 유무를 알리지 않음).
2. **쿠키**: `ytw_session; HttpOnly; SameSite=Strict; Path=/api; Max-Age=TTL`. `__Host-` 접두사 없음(Path=/api 필요), `Secure` 없음(http://127.0.0.1). 설계 질문 Q-WA-1: 실제 Chrome/Edge 에서 `Secure` 없이 동작함을 실측으로 확인하는 일은 아직 안 함(사용자 PC 필요).
3. **Host 검증은 최외곽 순수 ASGI 미들웨어**(`guard.py`): Host 허용 목록 -> Content-Length 1MB -> 속도 제한 -> 앱. 스트리밍(chunked) 본문도 계수한다. FastAPI 가 본문 읽기 예외를 400 으로 바꾸므로, 한도 초과 시 앱 응답을 버리고 413 으로 대체한다. 처리되지 않은 예외도 이 계층에서 500 problem+json 으로 만들어 보안 헤더가 빠지지 않게 했다(ServerErrorMiddleware 는 이 계층 밖).
4. **Host 검증 예외**: `/healthz` `/readyz` `/api/healthz` `/api/readyz` 는 Host 검증을 받지 않는다(컨테이너 헬스체크가 `api:8000` 등 다른 Host 를 쓸 수 있음). 응답에 민감 정보 없음. 반대 의견이면 알려 달라.
5. **세션**: 토큰 `secrets.token_urlsafe(32)`, DB 에는 sha256 만. 세션 최대 20개(오래된 것부터 삭제), 만료는 절대 TTL(`session_ttl_hours`). CSRF 토큰은 세션별, `hmac.compare_digest` 비교.
6. **PIN**: 숫자 4~12자리, `hashlib.scrypt`(n=2^14,r=8,p=1)+16바이트 솔트, `settings_kv.pin_hash`. 전역 실패 카운터(소유자 1명 전제): 5회 연속 실패 시 5분 잠금, 잠금마다 2배(최대 1시간). 실패 기록은 예외 롤백 전에 commit 한다. PIN 설정·변경·해제 시 현재 세션 외 세션 폐기. PIN 값은 로그·감사에 남기지 않음.
7. **설정 PATCH**: 허용 키 4개(`daily_apply_cap` 1~20, `suggestions_per_video` 1~5, `tone` 최대 5개·각 1~20자, `pin`). 그 외는 400 `setting_not_allowed`(섞여 있으면 전체 거부). `pin` 본문 형식: `{"action":"set"|"clear","new_pin"?,"current_pin"?}` (WEB_DESIGN 에 형식이 없어 이 단위에서 정함 -> W-FE 가 따라야 함). 기본값 `suggestions_per_video=3`, `tone=[]` 도 이 단위에서 정함.
8. **감사 해시 체인**: `hash = sha256(prev_hash + canonical_json({ts, actor, action, target:{type,id}, detail}))`, ts 는 UTC 마이크로초 ISO, 첫 prev 는 `"0"*64`. PostgreSQL 에서는 `pg_advisory_xact_lock` 으로 기록을 직렬화(동시 기록 시 체인 분기 방지; PG 테스트로 확인). 한계: 맨 끝 행 삭제(꼬리 절단)는 체인만으로는 탐지 불가 -> 앱 계정의 DELETE/TRUNCATE 권한 회수(0001 마이그레이션)가 방어선.
9. **멱등성**: 키 형식 `[A-Za-z0-9._:-]{8,80}`, 24시간 TTL, 처리 중 키는 409 `idempotency_in_progress`(동시 같은 키는 INSERT 충돌로 감지). 핸들러 실패 시 트랜잭션 롤백으로 키도 사라져 재시도 가능. 응답 본문은 `jsonable_encoder` 로 변환해 저장하고 첫 응답도 같은 형태로 돌려준다.
10. **잡 큐**: PostgreSQL `FOR UPDATE SKIP LOCKED`, SQLite 는 조건부 UPDATE(compare-and-set). 핸들러 예외는 `failed`(자동 재시도 없음 -> 부작용 있는 배치 작업의 중복 실행 방지), 저장되는 error 에는 예외 클래스명/ProblemError code 만(경로·메시지 비노출). `running` 잔존 작업은 `locked_at` 10분 경과 시 재큐, 시도 3회 초과면 `failed(worker_lost)`. `update_progress` 가 하트비트(locked_at 갱신)를 겸한다.
11. **워커**: 틱마다 stale 정리·만료 세션/오래된 멱등성 키 삭제(10분 주기) -> due 작업 모두 처리 -> `ytweb.domain.batches.run_due_items(session_factory, now)` 호출. 시작 시 `ytweb.domain` 하위 모듈을 모두 임포트해 `register_handler` 가 실행되게 한다(모듈 임포트 실패는 로그 남기고 계속). SIGTERM/SIGINT 는 중지 플래그만 세워 현재 작업을 마치고 종료.
12. **마이그레이션**: 0001 은 모델에서 렌더링한 PostgreSQL DDL 을 고정 문자열(23문장)로 보관, 모델을 임포트하지 않는다. 끝에서 `ytweb_app` 역할이 있으면 `REVOKE UPDATE, DELETE, TRUNCATE ON audit_log`. URL 은 `alembic.ini` 에 두지 않고 `cfg.attributes["url"]`(configparser `%` 문제 회피) 또는 `YTWEB_MIGRATE_DATABASE_URL`.
13. **로그**: `ytweb` 로거 JSON 한 줄, 마스킹(키=값, Bearer, URL 자격증명, 40자 이상 토큰 모양, 민감 키의 extra). 접근 로그는 method/path/status/ms/request_id 만(쿼리·헤더·본문 없음). uvicorn 자체 접근 로그는 쿼리 문자열을 찍으므로 실행 시 `--no-access-log` 필요(W-INF).
14. **속도 제한**: 프로세스 내 슬라이딩 윈도(기본 전역 600/분, 쓰기 120/분, 세션 발급 10/분). 단일 소유자 로컬 앱 전제이며 다중 프로세스 공유 안 함. `/api` 아래만 제한(헬스·정적 제외). 수치는 임의 기본값 -> 조정 가능.

## 4. 보안 요구 <-> 구현 <-> TC 매핑
| 요구 | 구현 | TC |
|---|---|---|
| Host 허용 목록(DNS 리바인딩) | `guard.py` | TC-WA-001~004 (004 = 헬스 예외) |
| 요청 크기 1MB | `guard.py` | TC-WA-005~007 |
| 속도 제한 | `ratelimit.py`, `guard.py` | TC-WA-008~011 |
| 보안 헤더 / 요청 ID | `guard.py` | TC-WA-012, 013 |
| /docs 는 enable_docs 일 때만 / 웹소켓 거부 | `app.py`, `guard.py` | TC-WA-014~016 |
| 오류 problem+json, 스택 비노출, 입력 에코 금지 | `errors.py`, `app.py`, `guard.py` | TC-WA-017~023 |
| Origin / Sec-Fetch-Site / CSRF / 세션 / 쿠키 / PIN | `deps.py`, `sessions.py`, `pin.py`, `routers/auth.py` | TC-WA-024~058 (test_auth.py: `test_foreign_origin_*`, `test_sec_fetch_*`, `test_csrf_*`, `test_session_cookie_attributes`, `test_session_token_stored_only_as_sha256`, `test_session_expires_*`, `test_logout_*`, `test_pin_*`) |
| 설정 허용/금지 키 | `routers/settings.py` | TC-WA-059~072 |
| 감사 체인 정상·변조 탐지·API chain_ok | `core/audit.py`, `routers/audit.py` | TC-WA-073~085 |
| 멱등성 재생·충돌·누락 | `core/idempotency.py` | TC-WA-086~097 |
| 잡 enqueue->claim->완료/실패/재큐, 워커 SIGTERM 동작 | `core/jobs.py`, `worker.py` | TC-WA-098~114 |
| 마이그레이션 오프라인 렌더, 실행기, auto-create | `alembic/`, `migrate.py` | TC-WA-115~125 |
| 로그 마스킹 | `logsetup.py` | TC-WA-126~132 |
| 시간 유틸, 의존성, 라우터 탐색, 헬스, 정적 서빙 | `clock.py`, `deps.py`, `app.py` | TC-WA-133~146 |
| SKIP LOCKED·부분 고유 인덱스·역할 권한·마이그레이션 실적용·동시 감사 기록 | `jobs.py`, `audit.py`, `0001_initial.py` | TC-WA-147~157 (PG 필요) |

(TC-WA-001~157 연속, 중복 없음 확인. 파라미터화 테스트는 하나의 TC 번호가 여러 실행 케이스를 가진다(그래서 pytest 통과 수 212 > TC 157). 번호는 각 테스트 docstring 첫머리: `grep -rn "TC-WA-" web/backend/tests/core`.)

## 5. 알려진 제한·미수행·편차
- **린트/포맷터/타입 검사 설정이 프로젝트에 없음**(루트 `pyproject.toml` 에 ruff/mypy 설정 없음, pre-commit 훅 없음). 임의로 도구를 고르지 않았다. 대신 `python -m compileall` 통과와 테스트 통과만 확인. **요청**: 린트 도구 선정(규칙 A) 후 설정 추가.
- **Docker 로 실제 컨테이너 기동 미수행**(범위 밖). Uvicorn 실기동(`uvicorn --factory`)도 이 단위에서는 TestClient 로만 확인.
- **브라우저 실측 미수행**: http://127.0.0.1 에서 `Secure` 없는 쿠키·`SameSite=Strict`·`Sec-Fetch-Site` 동작은 사용자 PC 의 Chrome/Edge 로 확인해야 한다(Q-WA-1).
- 해시 잠금: `pip-compile --generate-hashes --allow-unsafe --strip-extras`(pip-tools 7.6.2)로 `requirements.txt`/`requirements-dev.txt` 생성, `pip install --require-hashes` 로 설치 확인함. 잠금은 Python 3.13 환경에서 해석했다(3.12 에서도 설치 가능한 휠이 있는지는 3.12 로 미검증). 잠금에 `opentelemetry-api`, `annotated-doc` 등 간접 의존성이 포함됨(FastAPI/Starlette 이 끌어옴).
- 직접 의존성 존재·버전은 `pip index versions`/`pip download --no-deps` 로 확인: fastapi 0.143.0, uvicorn 0.54.0, pydantic 2.14.0, sqlalchemy 2.1.4, alembic 1.20.0, psycopg[binary] 3.3.6, pytest 9.1.1, pytest-cov 7.1.0, httpx 0.28.1. **라이선스는 이 단위에서 PyPI 메타데이터로 개별 확인하지 못했다**(조사축 D 패키지 표 참조 필요).
- Starlette TestClient 가 "httpx 대신 httpx2 설치" 폐기 경고를 낸다. `httpx2` 는 실존·신뢰 여부를 확인하지 않아 설치하지 않음(경고만).
- `config.py`(소유 외, 미수정) 문제 의심: DB 비밀번호를 `urllib.parse.quote(pw)` 로 URL 에 넣어 `/` 가 인코딩되지 않는다(`safe=""` 필요). `migrate.py` 는 `URL.create` 를 써서 이 문제가 없다. **요청**: 오케스트레이터가 `config.py` 에서 `quote(..., safe="")` 또는 `URL.create` 로 바꾸기(비밀번호 생성 스크립트가 `/` 를 만들 수 있으면 접속 실패). `config.py` 자체 테스트는 이 단위 범위 밖이라 없다(커버리지 40%).
- `ytweb.domain`/`ytweb.ai`/`ytweb.youtube` 패키지는 W-BE-B 소유. 이 단위 테스트는 `router_modules` 를 명시해 W-BE-B 의 미완성 라우터에 영향받지 않게 했으나, `test_discover_routers_finds_core_modules` 와 `test_discovery_default_includes_core_routes` 는 자동 탐색을 쓰므로 W-BE-B 의 라우터 모듈 중 임포트가 깨진 것이 있으면 실패한다(의도한 통합 신호).
- 속도 제한·세션 전체 폐기 정책은 단일 프로세스 가정. api 컨테이너를 여러 개로 늘리면 속도 제한이 프로세스별이 된다.
- 감사 로그 꼬리 절단은 체인 검증으로 탐지되지 않음(위 3-8).

## 6. 실행 방법
```
python3 -m venv .harness-tmp/venv_be_a
. .harness-tmp/venv_be_a/bin/activate
pip install --require-hashes -r web/backend/requirements-dev.txt
pip install -e .                      # 저장소 루트의 기존 코어 src/ytitle (복사 금지, 재사용)
cd web/backend
pytest tests/core -o addopts="" -rs                                   # SQLite 만(PG 테스트는 건너뜀)
YTWEB_TEST_PG_URL=postgresql+psycopg://<일회용 DB> pytest tests/core -o addopts="" -rs   # PG 포함
pytest tests/core -o addopts="" --cov=ytweb --cov-branch --cov-report=term-missing
alembic upgrade head --sql | head     # 오프라인 렌더(PYTHONPATH=. 필요)
```
- PG 테스트는 **public 스키마를 DROP 하고 다시 만들며 같은 DB 의 다른 접속을 끊는다** -> 반드시 일회용 테스트 DB 에만 사용.
- 개발 서버: `YTWEB_DATABASE_URL=sqlite:///x.db YTWEB_AUTO_CREATE=1 YTWEB_BASE_DIR=<저장소 루트> YTWEB_STATIC_DIR=<dist> uvicorn --factory ytweb.app:app_from_env --host 127.0.0.1 --port 8080 --no-access-log`

## 7. 테스트 실행 결과 (이 환경: Python 3.13.16, 2026-10-10)
| 실행 | 통과 | 건너뜀 | 실패 |
|---|---|---|---|
| 임시 PostgreSQL 16(127.0.0.1:54329, DB `ytweb_test_a`) 포함 전체 | **212** | 0 | 0 |
| `YTWEB_TEST_PG_URL` 없이(SQLite 만) | 201 | 11 (사유: "YTWEB_TEST_PG_URL 이 없어 PostgreSQL 전용 테스트를 건너뜀" 또는 해당 사유) | 0 |

- 분기 커버리지 포함 전체 커버리지(PG 포함 실행): **95%** (`ytweb` 전체 1266문장·246분기). 90% 목표 충족. 미달 파일: `config.py` 40%(소유 외, 이 단위 테스트 대상 아님), `worker.py` 80%(`main()` 신호 설정·`ytweb.domain` 임포트 경로 일부는 W-BE-B 모듈 유무에 의존해 미실행), `db/session.py` 87%.
- 실적용 확인: `alembic upgrade head`(`ytweb.migrate.upgrade`)를 실제 PostgreSQL 16 에 적용 -> 15개 테이블(모델 14 + alembic_version), 부분 고유 인덱스 2개 거부 동작, `SKIP LOCKED` 동시 claim(스레드 8개, 작업 20건 중복 0), 동시 감사 기록 50건 체인 유효, `ytweb_app` 역할의 `audit_log` UPDATE/DELETE/TRUNCATE 가 `permission denied`, downgrade base 정상.
- PG 테스트 중 임시로 만든 `ytweb_app` 역할은 테스트가 만든 경우에만 삭제한다(이미 있으면 건드리지 않음). 이전 중단 실행이 남긴 NOLOGIN `ytweb_app` 역할을 이 세션에서 정리했다. 마지막 실행 후 DB 는 빈 public 스키마 상태.

## 8. 6단계 테스터를 위한 인수 조건(요약)
1. 허용 Host/Origin 이 아니면 어떤 상태 변경도 불가(403), 세션·CSRF 없으면 401/403.
2. 쿠키 속성이 정확하고 DB 에 토큰 원문이 없음.
3. 설정 PATCH 로 `enable_live`/`live_allowlist` 등 금지 키 변경 불가(400), 허용 키는 범위 검증.
4. 오류 응답 어디에도 스택트레이스·내부 경로·예외 메시지 없음(500 포함).
5. 감사 로그 변조·삭제·타임스탬프 변경이 `chain_ok=false` 로 드러남.
6. 같은 Idempotency-Key 재전송은 부작용 1회, 다른 요청이면 422, 키 없으면 400.
7. 잡이 중복 처리되지 않고, 죽은 워커의 작업이 재큐됨. SIGTERM 에서 현재 작업은 완료 후 종료.
8. 마이그레이션 오프라인 렌더와 실제 PostgreSQL 적용 모두 성공.
변이 점검 후보(06 단계): `hmac.compare_digest` -> `==`, Origin 검사 제거, Sec-Fetch-Site 검사 제거, 세션 만료 비교 반전, 감사 체인 `prev_hash` 무시, `setting_not_allowed` 허용 목록 확대, `FOR UPDATE SKIP LOCKED` 제거.

## 9. 게이트 2 — 자체 코드 리뷰 체크리스트
- [x] 설계서/디자인서 명세와 구현 일치(편차: pin 본문 형식·기본값 정의, health Host 예외 -> 3장에 기록)
- [x] 에러 처리 누락 없음(예외를 삼키는 곳은 워커의 도메인 모듈 임포트·스케줄러 틱뿐이며 모두 `log.error(exc_info)` 로 남김)
- [x] 시스템 경계 입력 검증(Pydantic/수동 검증: 설정, PIN, 멱등성 키, 페이지 파라미터, Host/Origin/크기)
- [x] 하드코딩된 시크릿 없음(테스트용 더미 값만)
- [x] 새 의존성은 PyPI 에서 `pip index versions` / `pip download --no-deps` 로 실존 확인 후 고정(라이선스 개별 확인은 미수행 -> 5장)
- [x] 범위 밖 변경 없음(`routers/__init__.py` 신규 생성만 소유 목록에 명시되지 않았으나 라우터 자동 포함에 필요한 빈 패키지 표지)
- 게이트 1(린트): 프로젝트에 설정이 없어 **미수행**(5장에 사실 기록).

## 10. 공유 문서 갱신 요청 (오케스트레이터)
- traceability: 웹 보안 요구(Host/Origin/CSRF/세션/PIN/감사 체인/멱등성/잡 큐/마이그레이션) 항목의 작업 단위=W-BE-A, 구현 상태=구현 완료(6단계 대기).
- decisions: (a) 출처 검증 규칙(Sec-Fetch-Site same-origin 강제 + Origin 항상 일치), (b) 헬스 경로 Host 예외, (c) 쿠키에 Secure·`__Host-` 미사용(Q-WA-1), (d) 잡 핸들러 실패는 자동 재시도하지 않음, (e) PIN 잠금 정책 5회/5분 지수 증가.
- 질문(규칙 A): Q-WA-1 `Secure` 없는 쿠키의 실제 브라우저 동작 확인, Q-WA-2 린트 도구 선정, Q-WA-3 속도 제한 수치 확정, Q-WA-4 PIN 본문 형식을 W-FE 에 전달.
