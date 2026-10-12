<#
.SYNOPSIS
  실제 제목 수정을 켭니다(영상 1개만 허용). 영상 ID 를 한 번 붙여넣으면 web\.env 를 만들고 서버를 다시 시작합니다.
.DESCRIPTION
  하는 일: (1) web\.env 가 없으면 .env.example 을 복사 (2) YTWEB_LIVE_WRITE=1 과 YTWEB_LIVE_ALLOWED_VIDEOS=<영상ID> 로 설정
  (3) start.ps1 로 다시 시작. 이것만으로는 제목이 바뀌지 않습니다. 화면에서 [제목 수정 권한 연결], 제안 승인, 배치 실행(확인 문구)이 모두 필요합니다.
  끄려면 live-off.bat 를 실행하세요. 이 스크립트는 Windows 에서 아직 실행해 본 적이 없습니다.
#>
param([string]$VideoId = '')
$ErrorActionPreference = 'Stop'
$webDir = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $webDir '.env'
$example = Join-Path $webDir '.env.example'

if (-not $VideoId) { $VideoId = (Read-Host '실제로 제목을 바꿀 영상 ID 1개를 붙여넣고 Enter (11자리)').Trim() }
if ($VideoId -notmatch '^[A-Za-z0-9_-]{11}$') {
  Write-Host '[오류] 영상 ID 형식이 아닙니다(영문·숫자·-·_ 11자리). 영상 목록 화면에서 복사해 붙여넣으세요.' -ForegroundColor Red
  exit 1
}
if (-not (Test-Path $envFile)) {
  if (-not (Test-Path $example)) { Write-Host '[오류] web\.env.example 이 없습니다.' -ForegroundColor Red; exit 1 }
  Copy-Item $example $envFile
}
$lines = [System.IO.File]::ReadAllLines($envFile)
$out = New-Object System.Collections.Generic.List[string]
$hasW = $false; $hasV = $false
foreach ($l in $lines) {
  if ($l -match '^\s*YTWEB_LIVE_WRITE\s*=') { $out.Add('YTWEB_LIVE_WRITE=1'); $hasW = $true }
  elseif ($l -match '^\s*YTWEB_LIVE_ALLOWED_VIDEOS\s*=') { $out.Add("YTWEB_LIVE_ALLOWED_VIDEOS=$VideoId"); $hasV = $true }
  else { $out.Add($l) }
}
if (-not $hasW) { $out.Add('YTWEB_LIVE_WRITE=1') }
if (-not $hasV) { $out.Add("YTWEB_LIVE_ALLOWED_VIDEOS=$VideoId") }
[System.IO.File]::WriteAllLines($envFile, $out, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "[완료] web\.env 설정: 실제 수정 켜짐, 허용 영상 = $VideoId (이 영상 1개만)" -ForegroundColor Green
Write-Host '[안내] 서버를 다시 시작합니다...'
& (Join-Path $PSScriptRoot 'start.ps1')
Write-Host ''
Write-Host '다음: 브라우저에서 맨 위 띠가 "실제 수정 모드"로 바뀌었는지 확인하고, 홈에서 [제목 수정 권한 연결]을 누르세요.' -ForegroundColor Yellow
