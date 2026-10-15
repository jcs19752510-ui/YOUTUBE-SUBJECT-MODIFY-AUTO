# 관리자 로그인 인프라 3차 시험 결과서 (DEC-057: web/.env 방식)

- 시작 2026-10-15 03:08:55 UTC / 종료 03:13:06 UTC (약 4분 11초, 상한 12분 이내). 담당: 인프라/DevOps·보안.
- 한 줄 결론: 정적 시험 기준 합격(tests_infra + tests_security 532 통과, 427 건너뜀(Docker/Windows 필요), 3 xfail, 실패 0). **Windows 실행 미확인.**

## 한 것
1. `web/compose.yaml` api 에만 `YTWEB_ADMIN_ID: ${YTWEB_ADMIN_ID:-}`, `YTWEB_ADMIN_PASSWORD: ${YTWEB_ADMIN_PASSWORD:-}` 추가. `YTWEB_ADMIN_LOGIN=1`, `YTWEB_SESSION_IDLE_MINUTES=60` 유지. worker/migrate/db/web 에는 없음. api 비밀 파일은 `db_app_password` 하나(변경 없음). compose 는 `-f web/compose.yaml` 로 호출되어 프로젝트 폴더가 web/ 이므로 `web/.env` 를 자동으로 읽는다(기존 live 흐름과 동일, `--env-file` 불필요).
2. `reset-admin.ps1`, `reset-admin.bat` 삭제.
3. `start.ps1`: `web\.env` 에 두 값이 모두 비어 있지 않은지 확인(있다/없다만 표시, 값 미출력, 입력 받지 않음). 없으면 노란 주의문 + 해결 방법을 보이고 계속 진행(서버는 뜨나 로그인 불가). `.env` 가 없어도 복사하지 않고 같은 안내. 마지막 안내를 "브라우저에서 로그인하세요"로 변경.
4. `web/.env.example`(두 값은 빈 줄, 규칙·`#`/따옴표 금지·재실행·60분 설명), `web/README.md`(관리자 로그인 절을 단계별로 교체, reset-admin 행을 ".env 수정 후 start.ps1 재실행"으로 교체).
5. 시험 갱신: `test_admin_login_inf.py`(001/003/006/008/009/012/018/019 새 계약으로; 012 는 reset/set-admin 파일·참조 없음, 018 은 `git check-ignore -v web/.env` 와 미추적 확인 추가), `test_vi_independent.py`(스크립트 목록에서 reset-admin 제거, 비밀 규칙에 api 의 YTWEB_ADMIN_PASSWORD 예외), `test_compose_security.py`, `test_vinf2_static.py`, `tests_security/test_sec_03_static_repo.py`(같은 예외 + worker/migrate/db/web 에 YTWEB_ADMIN_* 없음 단언).

## 첫 실행(수정 전 시험을 새 파일 상태에서 처음 돌린 결과, 그대로 기록)
- 1차: 5 실패 / 527 통과. 원인: (a) 기존 "환경 변수의 비밀 키는 반드시 *_FILE" 규칙 4건(`test_tc_wi_009`, `test_tc_vi_008`, `test_vif_008`, `test_compose_secrets_are_files...`)이 새 설계(api 환경 변수 `YTWEB_ADMIN_PASSWORD`)와 정면 충돌, (b) 내 새 시험 `tc_adm_006` 정규식 오류(자리표시자 `${YTWEB_ADMIN_ID:-}` 자체를 값으로 오탐; yaml 파싱 비교로 교체).
- 판정: 기대값을 느슨하게 맞춘 것이 아니라 **명시적 단일 예외**로 처리했다. 예외 조건은 서비스=api, 키=`YTWEB_ADMIN_PASSWORD`, 값이 정확히 `${YTWEB_ADMIN_PASSWORD:-}`(저장소에 실제 값 없음)일 때뿐. 다른 서비스·다른 키·리터럴 값은 여전히 실패한다.

## 재실행
- 2차: `pytest tests_infra tests_security -o addopts="" -q` → 532 passed, 427 skipped, 3 xfailed, 실패 0 (55초).
- 변이 점검 1건: worker 에 `YTWEB_ADMIN_ID` 를 추가했더니 `test_tc_adm_003[worker]` 와 `test_compose_secrets_are_files_and_env_has_no_plain_credentials` 가 실패(탐지 성공), 원복 후 20건 통과.

## 안 한 것 / 미확인
- Windows PowerShell(5.1) 에서 start.ps1 실행 미확인(문자열·구조 검사만; 정규식 `^\s*KEY\s*=\s*\S` 동작과 한글 출력은 실제 PC 에서 확인 필요).
- 실제 `docker compose up`·`docker compose config` 로 web/.env 값이 api 컨테이너에 들어가는지 실제 확인 안 함(Docker 필요 시험 427건은 건너뜀). 백엔드가 `YTWEB_ADMIN_ID/PASSWORD` 로 계정을 준비하는 동작은 이 범위 밖(오케스트레이터 소유).
- 이미지 취약점 스캔 등 기존 미수행 항목은 변동 없음.

## 보안상 남는 위험(수용 필요, DEC-057 기록 권장)
- 비밀번호가 api 컨테이너 환경 변수에 평문으로 존재한다(`docker inspect`·`docker compose config` 출력에서 같은 PC 의 Docker 권한자에게 보임). 이전의 "환경 변수에는 *_FILE 만" 원칙의 유일한 예외이며, 선생님 1인 PC·127.0.0.1 한정이라는 전제로 수용. `web\.env` 는 `.gitignore`(`.env`)로 제외되고 미추적임을 시험으로 확인.
- 이 PC 에서 `.env` 파일 접근 권한(NTFS ACL)은 제한하지 않았다(미조치).

## 변경·삭제 파일
- 수정: web/compose.yaml, web/scripts/start.ps1, web/.env.example, web/README.md, web/tests_infra/{test_admin_login_inf,test_vi_independent,test_compose_security,test_vinf2_static}.py, web/tests_security/test_sec_03_static_repo.py
- 삭제: web/scripts/reset-admin.ps1, web/scripts/reset-admin.bat
- 신규: docs/harness/admin-login-inf3-test.md
