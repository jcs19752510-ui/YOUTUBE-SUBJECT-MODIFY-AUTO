<#
.SYNOPSIS
  실제 제목 수정을 켜고 "모든 영상"을 허용합니다(영상 ID 를 하나씩 넣지 않아도 됩니다).
.DESCRIPTION
  하는 일: (1) web\.env 가 없으면 .env.example 을 복사 (2) YTWEB_LIVE_WRITE=1 과 YTWEB_LIVE_ALLOWED_VIDEOS=* 로 설정 (3) start.ps1 로 다시 시작.
  이것만으로는 제목이 바뀌지 않습니다. 화면에서 [제목 수정 권한 연결], 제안 승인, 배치 실행(확인 문구 "실제 실행 N건")이 모두 필요합니다.
  비공개·어린이용·예약 라이브 영상(쇼츠는 설정에 따라)은 허용해도 계속 제외됩니다. 끄려면 live-off.bat 를 실행하세요.
  되돌려서 1개만 허용하려면 live-on.bat 를 실행하세요. 이 스크립트는 Windows 에서 아직 실행해 본 적이 없습니다.
#>
$ErrorActionPreference = 'Stop'
$VideoId = '*'
$webDir = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $webDir '.env'
$example = Join-Path $webDir '.env.example'

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
Write-Host "[완료] web\.env 설정: 실제 수정 켜짐, 허용 영상 = 모든 영상(*)" -ForegroundColor Green
Write-Host '[안내] 서버를 다시 시작합니다...'
& (Join-Path $PSScriptRoot 'start.ps1')
Write-Host ''
Write-Host '다음: 브라우저에서 맨 위 띠가 "실제 수정 모드"로 바뀌었는지 확인하고, 홈에서 [제목 수정 권한 연결]을 누르세요.' -ForegroundColor Yellow
