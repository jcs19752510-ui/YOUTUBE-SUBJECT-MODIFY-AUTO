<#
.SYNOPSIS
  실제 제목 수정을 끕니다(YTWEB_LIVE_WRITE=0, 허용 영상 목록 비움). 이미 바뀐 제목은 돌아오지 않습니다.
#>
$ErrorActionPreference = 'Stop'
$envFile = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'
if (-not (Test-Path $envFile)) { Write-Host '[안내] web\.env 가 없어 이미 꺼진 상태입니다.'; exit 0 }
$out = foreach ($l in [System.IO.File]::ReadAllLines($envFile)) {
  if ($l -match '^\s*YTWEB_LIVE_WRITE\s*=') { 'YTWEB_LIVE_WRITE=0' }
  elseif ($l -match '^\s*YTWEB_LIVE_ALLOWED_VIDEOS\s*=') { 'YTWEB_LIVE_ALLOWED_VIDEOS=' }
  else { $l }
}
[System.IO.File]::WriteAllLines($envFile, [string[]]$out, (New-Object System.Text.UTF8Encoding($false)))
Write-Host '[완료] 실제 수정을 껐습니다. 서버를 다시 시작합니다...' -ForegroundColor Green
& (Join-Path $PSScriptRoot 'start.ps1')
