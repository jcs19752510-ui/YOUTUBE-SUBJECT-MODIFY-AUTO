# 관리자 로그인 인프라 2차(웹 화면 계정 생성 방식) 시험 결과서

- 담당: 인프라/DevOps·보안. 시작 2026-10-15 02:50:33 UTC, 종료 02:52:55 UTC 경과 확인 후 결과서 작성(코드·시험 작업 약 3분, 상한 12분 이내).
- 근거: 선생님 지시 - 터미널의 관리자 아이디·비밀번호 입력과 `web\secrets\admin_login_*` 파일 제거, 웹 화면에서만 계정 생성. 기대값 변경은 이 지시된 설계 변경 때문이다.

## 한 것
| 항목 | 내용 |
|---|---|
| compose.yaml | api 의 admin secrets 마운트·`YTWEB_ADMIN_ID_FILE`·`YTWEB_ADMIN_PASSWORD_FILE`·최상위 secrets 2개 제거. `YTWEB_ADMIN_LOGIN=1`·`YTWEB_SESSION_IDLE_MINUTES=60` api 에 유지. api 비밀은 `db_app_password` 하나 |
| start.ps1 / _common.ps1 | `Initialize-AdminLogin`·`Save-AdminLoginInteractive`·`Test-AdminLoginPresent`·`Test-InputInteractive`·`ConvertFrom-SecureToPlain`·`$YtwebAdminIdFile/PwFile` 삭제. 마지막 안내에 "처음 접속하면 브라우저에서 관리자 계정을 만드세요" 추가 |
| 삭제 | `web/scripts/set-admin.ps1`, `set-admin.bat` (파일 삭제만) |
| 신규 | `web/scripts/reset-admin.ps1`(UTF-8 BOM), `reset-admin.bat`. 확인 문구 `관리자초기화`(`Read-ConfirmText`) -> api 실행 확인 -> `compose exec -T api python -m ytweb.admin_cli reset`. 꺼져 있으면 start.ps1 먼저 하라는 오류, 실패 시 원인·대처 문구. 비밀번호 값을 받거나 출력하지 않음 |
| 문서 | `web/.env.example`, `web/README.md` 새 방식으로 수정(자리표시자만) |
| 시험 | `test_admin_login_inf.py` 전면 재작성(TC-ADM-001~021), `test_compose_security.py`·`test_vi_independent.py`(스크립트 목록 포함)·`test_vinf2_static.py`·`tests_security/test_sec_03_static_repo.py` 기대값 갱신 |

## 시험 결과
- 첫 실행(수정 전 시험 + 새 코드): tests_infra 19건 실패(206 통과), test_sec_03 1건 실패. 원인은 전부 옛 admin 비밀 2개·set-admin 을 기대하던 단언(설계 변경).
- 시험 수정 중 내 시험 결함 2건(주석의 `ytweb.admin_cli` 문자열과 `set-admin` 부분 문자열이 `reset-admin` 에 걸림) -> 시험 쪽 수정 후 재실행.
- 재실행: `web/tests_infra` 228 통과, 331 건너뜀(기존 실스택·docker 의존), 1 xfail, 실패 0. `tests_security/test_sec_03_static_repo.py` 28 통과(`--noconftest`).
- 변이 점검 1건: compose 의 api·worker secrets 에 `admin_login_id` 되돌려 넣음 -> tests_infra 15 실패, test_sec_03 1 실패(검출됨). 원복 후 다시 전부 통과.
- 확인 단언: api/worker 비밀 `db_app_password` 하나, `*_FILE` admin 환경 변수 없음, start.ps1·_common.ps1 에 SecureString·admin 입력 없음, set-admin 파일·참조 없음, reset-admin 의 확인 문구·`-T`·`ytweb.admin_cli reset`·값 비취급, `.gitignore`/`.dockerignore` 의 `web/secrets/` 유지.

## restore.ps1 / reset-demo.ps1 (항목 7)
두 스크립트와 compose 에 admin 비밀 참조가 없고(TC-ADM-020), 필요한 비밀 파일은 `Initialize-Secrets` 가 만드는 DB 비밀 3개뿐이다. 따라서 이전의 "admin 비밀 파일이 없으면 컨테이너 시작 실패" 제약은 코드상 사라졌다(정적 확인).

## 안 한 것 / 미확인
- Windows PowerShell 에서 start.ps1·reset-admin.ps1/.bat 실제 실행: **Windows 실행 미확인**(정적 문자열 검사만).
- `ytweb.admin_cli` 의 `reset` 하위 명령 존재·동작: 백엔드 담당 구현물이며 이 작업에서 확인하지 않음(미확인). 이 모듈이 없으면 reset-admin 이 실패하고 안내 문구를 출력한다.
- 환경에 fastapi 가 없어 `tests_security` 의 conftest 가 필요한 나머지 파일(sec_01/02/04)은 실행하지 못함: 전체 `tests_security` 회귀는 **미수행**(sec_03 만 수행). admin 비밀 관련 단언은 sec_03 한 곳(grep 확인)뿐이다.
- 이 작업 범위 밖 문서(`docs/yt/API.md`, `WEB_FAQ.md`, `WEB_USER_MANUAL.md`, `WEB_RUNBOOK.md`, `ADMIN_LOGIN_DESIGN.md`)에 `set-admin`·admin 비밀 파일 설명이 남아 있다(수정 금지 범위, 오케스트레이터가 11단계에서 고쳐야 함).
- git add/commit/push 하지 않음.
