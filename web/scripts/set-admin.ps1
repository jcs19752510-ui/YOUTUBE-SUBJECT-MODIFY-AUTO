<#
.SYNOPSIS
  관리자 로그인 아이디·비밀번호를 정하거나 바꿉니다(비밀번호를 잊었을 때도 이 스크립트로 다시 정합니다).
.DESCRIPTION
  하는 일: (1) 아이디(영문·숫자 4~20자)·비밀번호(8~64자)를 입력받기(비밀번호는 화면에 보이지 않고 두 번 확인)
  (2) web\secrets\admin_login_id, web\secrets\admin_login_password 에 저장(UTF-8 BOM 없음, 줄바꿈 없음, 저장소에 올라가지 않는 폴더)
  (3) start.ps1 로 서버를 다시 시작해 새 값을 반영(-NoRestart 로 생략 가능).
  값은 명령줄 인수로 받지 않으며 화면·로그에 출력하지 않습니다. 반영되면 기존 로그인 세션은 모두 끝납니다.
  이 스크립트는 Windows 에서 아직 실행해 본 적이 없습니다.
.PARAMETER NoRestart
  저장만 하고 서버를 다시 시작하지 않습니다(나중에 start.ps1 을 직접 실행해야 반영됩니다).
#>
param([switch]$NoRestart)
. (Join-Path $PSScriptRoot '_common.ps1')

Write-Host ''
Write-Host '=== 관리자 로그인 설정 ===' -ForegroundColor White
Save-AdminLoginInteractive
if ($NoRestart) {
    Write-Warn '서버를 다시 시작하지 않았습니다. 새 값을 반영하려면 .\web\scripts\start.ps1 을 실행하세요.'
    exit 0
}
Write-Info '서버를 다시 시작해 새 값을 반영합니다...'
& (Join-Path $PSScriptRoot 'start.ps1')
exit $LASTEXITCODE
