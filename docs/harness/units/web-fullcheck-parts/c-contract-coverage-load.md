# C 구획: API 계약·전체 커버리지·부하 (2026-10-13, 시작 01:43:52 UTC, 종료 약 01:56, 상한 12분)

## 한 줄 결론
계약 시험: 5xx 0건·명세와 실제 앱 경로/스키마 불일치 0건이나, 오류 응답 상태코드(400/404/409)와 problem+json 이 OpenAPI 에 문서화되어 있지 않음(명세 결함). 커버리지: 백엔드 줄+분기 97%, 프런트 줄 98.3%/분기 94.4%. 부하: 동시 20 은 오류 0, **동시 50 에서 읽기 경로 약 13~26% 가 HTTP 500(30초 지연 후)** — 결함. 8분 소크는 **미수행**(시간 상한).

## 명령·소요(UTC)
| 단계 | 명령 | 소요 |
|---|---|---|
| venv | python3 -m venv .harness-tmp/be + pip install(requirements-dev + pyyaml python-dotenv coverage pytest-cov schemathesis httpx) + yt.pth | 01:43:52~01:44:13 (21초), be.ready 생성 |
| 임시 PG | postgresql-16, /var/tmp/ytpg_c, 포트 54339, trust, UTF8; DB ytweb_c_a~d, ytweb_c_load; 종료 후 삭제 | 약 5초 기동 |
| A 계약 | `.harness-tmp/be/bin/python web/tests_fullcheck/c/contract_test.py 3 / 40 / 200` | 3: 약 10초, 40: 14.7초, 200: 1분3초(5208호출, 34 오퍼레이션) |
| B 백엔드 | pytest --cov=ytweb --cov-branch 4묶음 병렬(g1 core+상위, g2 domain, g3 verify_wa/fix_be/wfixbe/ai_badge, g4 verify_wb/m23), PG 시험 포함 실행 후 coverage combine | g1 01:44:34~01:45:26, g2 ~01:45:55, g3 ~01:47:18, g4 ~01:47:20 |
| B 프런트 | `npx vitest run --coverage` (@vitest/coverage-v8@5.0.3 을 `npm install --no-save` 로 node_modules 에만 설치, package.json 무변경) | 01:48:25~01:49:31 (66초) |
| C 부하 | `load_test.py <PG> 120` (httpx ASGITransport, 인-프로세스) | 01:48:59~01:54:08 (비정상 종료, 아래) |

## A. 계약 시험 (schemathesis 4.31, 인증 세션+CSRF+Origin 헤더, 오퍼레이션당 최대 200예제)
- 5xx: **0건**. 하니스 오류 0건. response_schema_conformance 위반: 0건.
- 첫 실행(보존): 내 검사 코드가 content-type 헤더를 리스트로 받아 "problem+json 아님 3396건"으로 잘못 보고했다. **시험 코드 결함**이었고 응답 본문은 모두 problem+json 이었다(헤더 비교 수정 후 재실행 0건). 제품 결함이 아님.
- 재실행(contract_run_n200.out) 결과, 명세 불일치(문서화 안 된 응답): 상태코드 17종 — POST /batches 400, GET /batches/{id} 404, POST /batches/{id}/execute 400, /cancel 404, POST /changes/{id}/rollback 400, POST /google/connect·connect-write 409, GET /jobs/{id} 404, GET /reports/changes 404, GET /reports/export.csv 404, PATCH /settings 400, POST /suggestions/generate 404, PATCH·approve·reject /suggestions/{id} 404, GET /videos/{id} 404, POST /videos/{id}/suggestions 404. 즉 OpenAPI 는 200/201/202 와 422 만 선언한다.
- Content-Type 불일치: 422 를 application/json(HTTPValidationError)으로 선언하나 실제는 application/problem+json (POST /batches, rollback, PATCH /settings, approve). GET /reports/export.csv 200 은 선언 application/json, 실제 text/csv.
- docs/yt/openapi.json 대 앱이 생성하는 스키마: 오퍼레이션 34개 동일(양쪽 차집합 0), 컴포넌트 스키마 이름·필드 집합 동일, 버전 0.1.0 동일. (파라미터·필드 타입·필수 여부의 세부 차이는 미비교.)
- 한계: 경로 변수가 무작위라 존재하는 리소스에 대한 깊은 경로(실제 승인·실행 성공)는 거의 시험되지 않음(대부분 404/400). 상태 기반 시험은 미수행.

## B. 커버리지
### 백엔드(ytweb, 줄+분기, 2028개 시험 실행: g1 274, g2 295, g3 712(xfail 1), g4 746(skip 1, xfail 1), 실패 0)
전체: 문장 4223, 미커버 89, 분기 912, 부분 37, **97%**. 모듈별 전체 표: web/tests_fullcheck/c/backend_coverage_report.txt. 100% 미만:
| 모듈 | 커버 | 미커버 | 안전 관련 |
|---|---|---|---|
| change_report.py | 0% | 3-41 | 낮음(읽기 전용 CLI, 시험 없음) |
| live_check.py | 58% | 33-40, 44 | 중간(실제 모드 점검 보조) |
| config.py | 83% | 15, 49, 57-61 | 낮음~중간 |
| db/session.py | 87% | 13, 36-37 | 낮음 |
| ai/rule.py | 94% | 27, 29 | 낮음 |
| worker.py | 95% | 38-40, 44-45, 163 | 낮음(모듈 로드 실패 경로, main) |
| domain/batches.py | 96% | 70, 79, 121, 344, **435-436, 450, 470-473, 526-527**, 621 + 분기 | **높음**: 435-436(되돌리기도 실패할 때 failed 처리), 470-473(YtError 처리·same_as_current), 526(IntegrityError) 은 반영(쓰기) 경로의 오류 분기가 한 번도 실행되지 않음 |
| domain/changes.py | 96% | 86, 135-138 | 중간(롤백 관련 분기) |
| migrate.py 96%, domain/serialize.py 96%, suggestions.py 99%(64-65, 102 IntegrityError·applied 분기), videos.py 97%, google_oauth.py 97%(125-126, 172-173), guard.py 98%(176 too_large), models.py 99%(49 naive datetime 거부), seed.py 98% | | | 낮음~중간 |
- 주의: 이 수치는 SQLite 시험과 PG 시험을 합친 값이며, 프로세스 병렬 묶음의 combine 결과다.
### 프런트(vitest 5.0.3 + v8): 시험 파일 29 통과·1 skip, 시험 752 통과·1 expected fail·21 skip, 실패 0
전체 문장 97.3%, 분기 94.43%, 함수 95.37%, 줄 98.27%. 파일별 표: web/tests_fullcheck/c/frontend_coverage.log. 낮은 곳: navigate.ts 0%(3줄 하나), context.tsx 분기 50%, verify_fix/shared.tsx(시험 보조 파일) 75%.

## C. 부하 (PG 16 임시 클러스터, 영상 200개 시드, ASGI 인-프로세스; 1차 실행 결과, 로그 load_run1.out)
NFR 합격선: docs/yt/DESIGN.md NFR-W02·W07 이 "(제안, 미실측) 조회 API p95 ≤ 1초, 제안 1건 생성 ≤ 3초, 5xx 비율 < 1%", 02_planning NFR-020 "목록 1초 이내(가정)". 확정된 합격선이 아니므로 **참고 기록**이며 합격 판정을 하지 않는다. 합격선 후보: 조회 p95 ≤ 1초(동시 20), 5xx 0%, 동시 50 에서도 오류율 < 1%.
| 경로 | 동시 | n | p50 | p95 | p99 | 오류 |
|---|---|---|---|---|---|---|
| GET /videos?page_size=200 | 20 | 300 | 237ms | 335ms | 392ms | 0 |
| GET /dashboard | 20 | 300 | 228 | 330 | 395 | 0 |
| GET /suggestions, /batches, /changes, /audit, /settings | 20 | 각 300 | 100~122 | 166~196 | 213~240 | 0 |
| GET /readyz | 20 | 300 | 45 | 76 | 94 | 0 |
| GET /videos?page_size=200 | 50 | 300 | 633 | **30195** | 30265 | **40 (HTTP 500, 13%)** |
| GET /dashboard | 50 | 300 | 796 | 30211 | 30304 | 40 (500) |
| GET /suggestions | 50 | 300 | 427 | 30145 | 30226 | 40 (500) |
| GET /batches | 50 | 300 | 374 | 30259 | 30294 | 77 (500, 26%) |
| GET /changes | 50 | 300 | 424 | 30132 | 30203 | 40 (500) |
| GET /audit | 50 | 300 | 478 | 30138 | 30235 | 39 (500) |
| GET /settings | 50 | 300 | 454 | 30204 | 30251 | 70 (500) |
| GET /readyz | 50 | 300 | 126 | 208 | 273 | 0 |
| POST /videos/{id}/suggestions | 20 | 100 | 310 | 662 | 1170 | 17건 409 (생성 83건 201), 5xx 0 |
- RSS: 부하 중 106~122MB (증가 추세 판단 불가, 소크 미수행).
- 쓰기 승인 단계: 내 시험 코드가 제안 id 를 응답에서 읽지 못해(`made` 비어 있음, 응답 본문 구조 미확인) 승인 부하가 **시험 코드 오류로 중단**(ValueError: max() empty). 승인 p50/p95/p99 는 미측정. 동시 50 의 쓰기도 미측정.
- 409 17건: 시드 영상 중 제안 생성이 거부되는 상태(제외 등)인 것으로 추정하나 원인 코드는 확인하지 않음.

## 발견 결함
1. **(High, 재현 가능) 동시 50 연결에서 읽기 요청의 13~26% 가 30초 대기 후 HTTP 500.** 재현: PG 연결, `load_test.py` 의 읽기 단계 conc=50. 추정 원인: `ytweb/db/session.py` 의 PG 풀 pool_size=5·max_overflow=5(연결 10개) + 동기 엔드포인트 스레드 풀(약 40)로 풀 대기 시간 초과(SQLAlchemy 기본 30초) — **원인은 로그로 확인하지 않은 추정**. 단일 사용자 PC 도구라 실사용 영향은 낮지만 사용자가 겪으면 30초 멈춤 뒤 오류로 보임. 완화 후보: 풀 크기 확대 또는 대기 시간 단축+503/429 problem+json 반환.
2. **(Low~Medium) OpenAPI 명세에 오류 응답(400/404/409)·problem+json·csv 응답이 문서화되지 않음**, 422 의 content-type 이 실제와 다름. 클라이언트 생성·계약 시험에 영향.
3. **(Medium, 시험 공백) 반영 경로의 오류 분기(batches.py 435-436, 470-473, 526-527)와 change_report.py 0%** 가 시험되지 않음.

## 미수행과 사유
- **8분 연속 가동(소크) 메모리·오류율: 미수행** — 12분 하드 상한(01:55:52)에 부하 단계가 01:54:08 에야 시험 코드 오류로 중단되어 시간이 남지 않았다. `load_test.py` 에 소크 단계가 구현돼 있으나 실행된 적 없음.
- 승인·동시 50 쓰기 부하, 상태 기반 계약 시험, 파라미터 세부 명세 비교: 미수행(시간·시험 코드 오류).
- 이미지 취약점 스캔 등 본 구획 범위 밖은 해당 없음. docker 미사용.
- 정리: 임시 PG(/var/tmp/ytpg_c) 정지·삭제, 임시 계약 폴더 삭제. 산출물: web/tests_fullcheck/c/{contract_test.py,load_test.py,*.out,*.txt,*.log}. git add·커밋·푸시 안 함. 소스 수정 없음(node_modules 에 @vitest/coverage-v8 만 --no-save 설치).
