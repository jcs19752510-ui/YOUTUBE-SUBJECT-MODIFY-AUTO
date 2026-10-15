# 관리자 로그인 인프라·스크립트 시험 결과서 (DEC-055, W-INF)

- 시작 2026-10-15 02:20:22 UTC, 종료 약 02:23 UTC, 실제 소요 약 3분(`date -u` 측정, 12분 상한 이내).
- 한 줄 결론: 인프라·스크립트 정적 시험 22건 통과, 기존 tests_infra 회귀 0건(의도된 계약 변경 시험 7건 갱신 후). **Windows 실행은 하지 않았다(미확인).**

## 한 것
| 항목 | 내용 |
|---|---|
| `web/compose.yaml` | api 서비스에만 `YTWEB_ADMIN_LOGIN=1`, `YTWEB_ADMIN_ID_FILE`, `YTWEB_ADMIN_PASSWORD_FILE`, `YTWEB_SESSION_IDLE_MINUTES=60`, secrets `admin_login_id`/`admin_login_password`(최상위 file 선언 `./secrets/...`). hardening·네트워크 불변 |
| `web/scripts/_common.ps1` | `Test-AdminLoginPresent`, `Test-InputInteractive`, `ConvertFrom-SecureToPlain`, `Save-AdminLoginInteractive`, `Initialize-AdminLogin` 추가. `$YtwebSecretNames`(DB 비밀 3개)는 그대로 |
| `web/scripts/set-admin.ps1`/`.bat` | 아이디 영숫자 4~20자, 비밀번호 SecureString 8~64자 + 재입력, UTF-8 BOM 없음·줄바꿈 없음 저장, `Set-OwnerOnlyAcl`(실패 시 경고만), 이어서 start.ps1 (`-NoRestart`로 생략). 값 인수 없음 |
| `web/scripts/start.ps1` | `Initialize-Secrets` 다음에 `Initialize-AdminLogin`: 파일 없음/비어 있음이면 입력받아 계속, 비대화형이면 `.\web\scripts\set-admin.ps1` 안내와 함께 중단 |
| `web/.env.example`, `web/README.md` | 로그인 필수·최초 입력·set-admin.bat·60분 자동 로그아웃·비밀번호 재설정 안내(자리표시자 `admin1234`/`<새 비밀번호>`만) |
| `web/tests_infra/test_admin_login_inf.py` | 신규 TC-ADM-001~019(파라미터 포함 22건) |
| 기존 시험 갱신 | 계약 변경(api 비밀 3개)에 맞춰 `test_compose_security.py` 1곳, `test_vi_independent.py` 3곳, `test_vinf2_static.py` 6곳 수정(기대값을 구현에 맞춘 것이 아니라 설계서 계약 반영, 아래 참고) |
| 확인만(변경 없음) | `backup.ps1`(pg_dump만, web\secrets 미포함), `restore.ps1`, `status.ps1`, `logs.ps1`: 비밀 파일 미참조. `.gitignore`의 `web/secrets/` 및 `.dockerignore` 확인, `git check-ignore -v web/secrets/admin_login_id web/secrets/admin_login_password` -> `.gitignore:41:web/secrets/` 로 둘 다 제외됨 |

## 시험 결과
- 신규 파일 단독, 첫 실행: 22 passed (실패 0). 이어서 **변이 점검**(worker 에 admin 비밀 추가, set-admin 흐름에 비밀번호 출력 한 줄 삽입): TC-ADM-003[worker], 011, 019 가 각각 실패로 잡아냄 -> 원복.
- TC-ADM-019 는 `docker compose config --format json` 으로 실제 렌더링해 admin 비밀이 api 에만 있음을 확인(건너뛰지 않고 실행됨; 데몬 불필요).
- 전체 tests_infra, **첫 실행 7건 실패**: test_tc_wi_018, test_tc_vi_008, test_tc_vi_027, test_vif_007, test_vif_023, test_vif_026, test_vif_053.
  - 6건은 "api 비밀은 db_app_password 하나" 등 옛 계약 단언(의도된 변경, 위 갱신).
  - test_tc_vi_027 은 이번 변경 전부터 실패하던 건(HEAD 의 파일 목록에 `gemini-on.ps1`·`live-allow-all.ps1` 누락). 목록에 이 둘과 `set-admin.ps1` 을 추가해 해결.
- 전체 tests_infra 재실행: **225 passed, 331 skipped, 1 xfailed, 실패 0**(1.8초). skipped 는 실행 중인 스택·DB·도커 데몬이 필요한 시험(이번 환경에서 미실행)이며 PASS 로 세지 않는다.

## 미확인(하지 않은 것)
1. Windows PowerShell 5.1/7 에서 set-admin.ps1·start.ps1 실제 실행 미확인(SecureString, Read-Host, icacls, 한글 출력, `[Console]::IsInputRedirected` 동작).
2. 파일이 BOM·줄바꿈 없이 실제 기록되는지는 코드 검사만 했다(런타임 확인 없음).
3. api 컨테이너가 `/run/secrets/admin_login_*` 를 비루트(10001)로 읽는지 미확인(백엔드 통합·Windows Docker 필요). 기존 DB 비밀과 같은 방식이라 같은 제약.
4. 이미 비밀 파일이 만들어져 있고 admin 파일만 없는 기존 설치: start.ps1 이 입력을 받는 경로를 코드로만 확인.
5. 부수 영향: admin 비밀 파일이 없으면 `restore.ps1`/`reset-demo.ps1` 의 `compose up` 도 실패한다(start.ps1 을 먼저 한 번 실행해야 함). 스크립트는 변경하지 않았다.
6. 백엔드 환경 변수 이름·동작(파일 읽기, 60분)은 계약 문서대로 가정했고 백엔드 쪽 일치는 통합 시 확인 필요.
7. 비밀번호 `a -cne b` 비교·`$plain = $null` 는 메모리 지우기 보장이 아니다(PowerShell 문자열은 GC 까지 남음).
