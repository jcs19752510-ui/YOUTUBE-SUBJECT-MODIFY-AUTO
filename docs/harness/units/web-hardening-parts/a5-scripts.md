# a5-scripts 보고 (시작 01:23:11 UTC, 종료 01:29 UTC, 약 6분)

## 한계 (먼저)
이 환경은 Linux 이고 pwsh 가 없다(`which pwsh` 결과 없음). PowerShell 파서 검증 불가, Windows 실행 불가. 아래 수정은 **Windows 에서 실행해 확인하지 못했다.**

## 할 일 1: 백업 폴더 권한 제한 실패
- 확인한 원인(코드 읽기): web/scripts/_common.ps1 `Set-OwnerOnlyAcl` (수정 전 165~187줄). `Get-Acl` 로 받은 보안 객체 전체를 `Set-Acl -AclObject` 로 되쓴다. Set-Acl 은 객체의 소유자·감사(SACL)까지 함께 쓰려 하므로 일반 사용자에게 없는 SeSecurityPrivilege 오류가 나는 것으로 추정된다(코드 구조는 확인, 오류 발생 자체는 Windows 에서 재현 못 함). 호출부: backup.ps1:23(폴더), backup.ps1:51(파일), _common.ps1 Initialize-Secrets(폴더/파일).
- 변경: 함수 이름·인자·반환(true/false)·경고 방식 유지. 본문만 `icacls <경로> /grant:r *<현재사용자SID>:(OI)(CI)F /grant:r *S-1-5-18:(OI)(CI)F /inheritance:r` 한 번의 명령으로 교체(Invoke-Native 사용, 종료 코드 0 아니면 예외→경고만). 부여와 상속 제거를 한 명령에 넣어 현재 사용자 잠김을 방지. 소유자·SACL 미접촉. SID 사용(한글·도메인 계정 무관). try/catch 로 실패해도 경고만 내고 백업·복원은 계속(호출부가 모두 `[void](...)`).
- 5.1 호환 점검: `??`, `?.`, `&&` 없음(grep). BOM 유지(ef bb bf).
- 미확인: icacls 가 파일 경로에 `(OI)(CI)` 를 줘도 오류 없이 처리하는지(알려진 동작은 무시이나 Windows 에서 확인 못 함).

## 할 일 2: status.ps1 -Detail 출력 이상
코드로는 원인을 확정하지 못했다. **수정하지 않았다.**
- (a) 한글 이중 출력: "--- 서비스 상태 ---" 는 `Write-Host '...'` 단일 호출(status.ps1:16~17). `-NoNewline`, `` `r ``, Start-Transcript, Tee-Object 모두 scripts 전체에 없음. 문자열 중복 생성 코드 없음.
- (b) `web` 이 `worker` 줄 끝에 겹침: 각 줄은 개별 Write-Ok/Write-Warn(Write-Host)이며 줄바꿈 억제 코드 없음.
- (c) 일부 줄 누락: "호스트에 열린 포트" 구역 줄은 `docker ps` 결과마다 무조건 출력, 코드상 조건 분기로 건너뛰는 경로 없음(단, docker ps 가 빈 결과를 주면 foreach 가 비어 줄이 안 나옴 — 가능한 코드상 원인이지만 같은 실행의 마지막 "문제 없음"이 loopback 줄도 건너뛴 점은 설명 못 함. loopback 줄은 try 안에서 항상 Write-Ok).
- 코드 쪽 관련 요소: `_common.ps1:7-8` 에서 `[Console]::OutputEncoding` 을 UTF-8 로 바꿈(예외 시 무시). 두 번째 줄에서 한글 2글자 폭 문자가 겹쳐 그려지는 증상은 전형적인 콘솔 렌더링(전각 문자·글꼴/Windows Terminal·conhost, docker 가 콘솔 모드를 바꾼 뒤) 문제와 일치하나 **추정**.
- 판별 방법(사용자 PC): `.\web\scripts\status.ps1 -Detail | Out-File status.txt -Encoding utf8` 후 status.txt 열기. 파일이 정상이면 터미널 표시 문제, 파일에도 겹치면 스크립트 결함. 추가로 Windows Terminal 대신 기본 PowerShell 창에서도 비교.

## 시험 (web/, `.harness-tmp/be/bin/python -m pytest tests_infra tests_security -q`)
- 수정 전 첫 실행: 5 실패 (요약의 passed 수치는 출력 필터 오류로 기록 못 함). 실패: test_vi_independent::tc_vi_027(스크립트 파일 목록 불일치), test_vinf2_static::vif_051(compose 덮어쓰기 로직), test_sec_02::ytweb_has_no_outbound_capable_imports, test_sec_09::d4_only_three_modules_import_urllib_request, test_sec_09::f2_built_bundle_contains_all_regulatory_and_ai_phrases.
- 수정 후: 동일한 5건 실패, 새 실패 없음. 이 5건은 다른 작업(신규 스크립트·Gemini·프런트 번들)으로 인한 기존 실패이며 이번 수정과 무관함을 목록 비교로 확인(수정 대상 함수는 tc_vi_027 의 파일 목록과 무관). 단 수정 전과 같다는 점만 확인했고 5건의 원인 조치는 하지 않음.
- Set-OwnerOnlyAcl 존재 확인 시험(test_sec_03:399)은 통과 유지.

## 사용자 PC 확인 한 줄
`.\web\scripts\backup.ps1` 실행 후 "접근 권한을 ... 제한하지 못했습니다" 경고가 없는지 보고, `icacls web\backups` 로 현재 사용자와 SYSTEM 만 나오는지 확인.
