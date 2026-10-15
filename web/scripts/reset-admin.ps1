<#
.SYNOPSIS
  관리자 비밀번호를 잊었을 때만 씁니다. 관리자 계정·로그인 세션·실패 잠금을 지웁니다(확인 문구 필요).
.DESCRIPTION
  실행 중인 api 컨테이너에서 'python -m ytweb.admin_cli reset' 을 실행합니다. 영상·제안·이력 등 다른 데이터는 건드리지 않습니다.
  끝나면 브라우저를 새로 고쳐 "관리자 계정 만들기" 화면에서 새 계정을 만드세요. 이 스크립트는 비밀번호 값을 받거나 출력하지 않습니다.
  이 스크립트는 Windows 에서 아직 실행해 본 적이 없습니다.
#>
param([string]$ConfirmText = '')
. (Join-Path $PSScriptRoot '_common.ps1')

Test-ComposeFileExists
Test-DockerReady

$phrase = '관리자초기화'
Write-Host ''
Write-Host '!!! 경고 !!!' -ForegroundColor Red
Write-Host '관리자 계정, 로그인 상태, 로그인 실패 잠금을 모두 지웁니다. 비밀번호를 잊었을 때만 하세요. 영상·제안·이력 데이터는 지우지 않습니다.' -ForegroundColor Red
if (-not (Read-ConfirmText -Expected $phrase -Provided $ConfirmText -Prompt "계속하려면 `"$phrase`" 를 그대로 입력하세요")) {
    Write-Info '확인 문구가 맞지 않아 취소했습니다. 아무것도 바꾸지 않았습니다.'
    exit 2
}

$apiUp = @(Get-ComposeServices | Where-Object { (Get-Prop $_ 'Service') -eq 'api' -and (Get-Prop $_ 'State') -eq 'running' })
if ($apiUp.Count -eq 0) {
    Stop-Script 'api 컨테이너가 실행 중이 아닙니다.' '먼저 .\web\scripts\start.ps1 로 시작한 뒤 reset-admin 을 다시 실행하세요.'
}

$r = Invoke-Compose -ArgList @('exec', '-T', 'api', 'python', '-m', 'ytweb.admin_cli', 'reset')
if ($r.ExitCode -ne 0) {
    Stop-Script '관리자 초기화에 실패했습니다.' '원인 확인: .\web\scripts\logs.ps1 -Service api . 서버가 막 시작되는 중이면 1분 뒤 다시 실행하고, 계속 실패하면 start.ps1 로 다시 시작한 뒤 재시도하세요.'
}
Write-Ok "초기화했습니다. 브라우저에서 $YtwebUrl 를 새로 고치고 새 관리자 계정을 만드세요."
exit 0
