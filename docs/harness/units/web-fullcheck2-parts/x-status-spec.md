# x-status-spec (STATUS-1, SPEC-1) 시작 02:12:15Z, 상한 도달 02:24Z (docker 미사용, Windows 미실행)

## STATUS-1 status.ps1
명령: pwsh 7.4.13(.harness-tmp/pwsh) + 가짜 docker(web/tests_fullcheck/b/docker-shim.sh, PATH 앞) + fake-web.py(8080). 스크립트 web/tests_fullcheck/x/run-status-scenarios.sh. 결과 .harness-tmp/x/{before-noweb,before,after}/.
첫 실행(before-noweb, 8080 서버 없이): 6개 모두 /api/healthz 응답 없음으로 exit 1, "문제 없음" 경로에 도달 못함 -> 시험 구성 불충분, 보존. 서버를 띄운 before 가 수정 전 기준.
| 시나리오 | 수정 전 | 수정 후 |
|---|---|---|
| full | 문제 없음 exit0 | 동일(바이트 동일) |
| array(JSON 배열) | 문제 없음 exit0 | 동일(바이트 동일) |
| badport | 위험 2줄, 2건 exit1 | 동일 |
| empty(서비스 없음) | 없음 안내 exit1 | 동일 |
| partial(db/api/web만) | 2건 exit1 | 동일 + "migrate/worker 호스트 포트를 확인하지 못함" 경고 2줄(판정 건수는 그대로 2건) |
| psempty(docker ps 만 빈 결과) | **문제 없음 exit0 (결함 재현)** | 경고 "컨테이너의 호스트 포트 정보를 읽지 못했습니다... (확인하지 못함)" + "점검 결과: 확인 불가 항목 있음 (1 건)..." exit1 |
diff: web/scripts/status.ps1 +18/-1. $unverified 카운터 추가; docker ps 실패/빈 결과, 서비스가 ps 목록에 없음, `compose port` 실패, 리스너 점검 예외를 확인 불가로 집계; problems=0 이고 unverified>0 이면 별도 문구로 exit 1. BOM 유지, 5.1 구문(파서 검사 errors=0, v7 구문 없음).
인프라/보안 정적: `pytest tests_infra tests_security -k "not test_f2"` -> 1 실패 test_sec_03 test_no_secrets_in_current_tree: web/backend/tests/verify_revoke/test_revoke.py:18-19 (다른 에이전트의 새 파일, status.ps1 무관; 내 변경을 stash 해도 동일 실패 확인). 이 외 실패 없음. 통과 수 요약줄은 출력되지 않아 숫자 비교 못함(미수행). status.ps1 을 막는 기대 문구 시험은 없었음.
한계: Windows 실행 미확인. 실제 docker 미사용(가짜 docker). 개별 서비스 web 만 빠진 시나리오는 별도 실행 안 함(코드상 partial 과 같은 경로).

## SPEC-1 OpenAPI
- 신규 web/backend/ytweb/core/openapi_errors.py(오류 응답 문서화만, Problem 스키마 = problem_body 6필드, 모든 동작에 400/404/409/422 application/problem+json). web/backend/ytweb/app.py: import 1줄 + `openapi_errors.install(app)` 1줄(동작 변경 없음; 같은 파일의 다른 미커밋 변경은 타 에이전트 것).
- docs/yt/openapi.json 재생성(앱 app.openapi(), indent 2, ensure_ascii False). 수정 전 코드로 생성한 결과가 저장본과 동일함을 먼저 확인. 변경: 삭제 78줄은 기본 422 HTTPValidationError(application/json) 26개를 problem+json 으로 교체한 것뿐, 나머지는 추가(Problem 스키마·오류 응답).
- docs/yt/API.md 9장 2항 1줄 갱신.
- 새 시험 web/backend/tests/verify_spec/test_openapi_errors.py. 첫 실행: 4개 중 1개 실패(test_saved_openapi_json_is_current) - 원인은 시험이 core 라우터 4개만 올리는 client 픽스처를 써서 전체 앱과 비교한 시험 결함. 시험 기대값이 아니라 대상 앱 구성을 전체 라우터(create_app(web_settings))로 고침, 재실행 4/4 통과.
- 기존 시험: 전체 `tests` 실행은 240초 제한에 걸려 중단(결과 없음). 단일 test_tc_m2_030 은 실패하나 원인은 타 에이전트의 google.py/google_oauth.py 미커밋 변경(`revoked` 필드 추가) - 내 변경과 무관(미검증: 내 변경만 되돌려 확인하지는 않음). tests/domain, core, verify_m23 의 전체 통과와 contract_test.py 재실행은 **미수행**(시간 상한).
