<#
.SYNOPSIS
  관리자 계정(아이디·비밀번호)을 한 번 등록합니다. 이미 계정이 있으면 새 값으로 교체합니다(잊었을 때도 같은 명령).
.DESCRIPTION
  이 스크립트(PowerShell)는 아이디도 비밀번호도 읽지 않고 다루지 않습니다. api 컨테이너 안의 등록 프로그램
  (python -m ytweb.admin_cli register)이 키보드 입력을 직접 받습니다. 비밀번호는 화면에 보이지 않고 두 번 입력하며,
  데이터베이스에 해시(scrypt)로만 저장됩니다. 파일·환경 변수·명령줄 인수·로그 어디에도 남지 않습니다.
  규칙: 아이디 영문·숫자 4~20자, 비밀번호 8~64자. 계정을 교체하면 기존 로그인 세션은 모두 종료되고 잠금은 초기화됩니다.
  이 스크립트는 Windows 에서 아직 실행해 본 적이 없습니다.
#>
. (Join-Path $PSScriptRoot '_common.ps1')

Write-Host ''
Write-Host '=== 관리자 계정 등록 ===' -ForegroundColor White

Write-Info '1/2 Docker 와 서버(api) 실행 확인'
Test-ComposeFileExists
Test-DockerReady
$apiUp = @(Get-ComposeServices | Where-Object { (Get-Prop $_ 'Service') -eq 'api' -and (Get-Prop $_ 'State') -eq 'running' })
if ($apiUp.Count -eq 0) {
    Stop-Script '서버(api)가 실행 중이 아닙니다.' '먼저 .\web\scripts\start.ps1 을 실행하세요. "준비 완료!" 가 나온 뒤 이 명령을 다시 실행하면 됩니다.'
}
Write-Ok '서버(api)가 실행 중입니다'

Write-Info '2/2 아이디와 비밀번호를 입력하세요 (비밀번호는 화면에 보이지 않으며 두 번 입력합니다)'
# 대화형으로 직접 실행한다: 출력을 가로채거나 파이프로 넘기지 않고, 입력 장치를 끊지 않는다. 입력은 컨테이너 안 프로그램이 직접 받는다.
$baseArgs = @(Get-ComposeBaseArgs)
& docker @baseArgs exec api python -m ytweb.admin_cli register
$code = $LASTEXITCODE

Write-Host ''
if ($code -eq 0) {
    Write-Ok '관리자 계정을 등록했습니다. 브라우저에서 로그인 화면으로 로그인하세요(마지막 조작 후 60분이 지나면 자동 로그아웃됩니다).'
    Write-Host '잊었거나 바꾸려면 이 명령을 다시 실행하세요(기존 계정은 새 값으로 교체되고 모든 로그인이 종료됩니다).'
    exit 0
}
Write-Host "[오류] 계정 등록에 실패했습니다(종료 코드 $code)." -ForegroundColor Red
Write-Host '[원인과 조치]' -ForegroundColor Yellow
Write-Host ' - 아이디는 영문·숫자 4~20자, 비밀번호는 8~64자이며 두 번 입력한 값이 같아야 합니다. 안내 메시지를 읽고 다시 실행하세요.' -ForegroundColor Yellow
Write-Host ' - 서버가 막 시작했다면 잠시 기다린 뒤 다시 실행하세요. 계속 실패하면 .\web\scripts\logs.ps1 -Service api 로 원인을 확인하세요.' -ForegroundColor Yellow
exit 1
