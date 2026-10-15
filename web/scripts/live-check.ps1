<#
.SYNOPSIS
  실제 제목 수정을 켜기 전에 준비 상태를 점검합니다(읽기 전용: 아무것도 바꾸지 않고 구글에도 접속하지 않습니다).
.DESCRIPTION
  구글 연결 파일, 읽기 로그인, 제목 수정 권한, 실제 수정 스위치, 수정 허용 영상을 확인해 빠진 것을 알려 줍니다.
  먼저 .\web\scripts\start.ps1 로 서버를 켜 두세요.
.EXAMPLE
  .\web\scripts\live-check.ps1
#>
. (Join-Path $PSScriptRoot '_common.ps1')

Test-ComposeFileExists
Test-DockerReady
$r = Invoke-Compose -ArgList @('exec', '-T', 'api', 'python', '-m', 'ytweb.live_check') -Capture
$r.Output | ForEach-Object { Write-Host $_ }
if ($r.ExitCode -ne 0) { Write-Warn '점검을 실행하지 못했습니다. 서버가 켜져 있는지 .\web\scripts\status.ps1 로 확인하세요.'; exit 1 }
