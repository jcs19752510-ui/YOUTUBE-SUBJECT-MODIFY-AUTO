<#
.SYNOPSIS
  내 PC에서 떠 있는 서버(http://127.0.0.1:8080)를 대상으로 기능 자동 시험(E2E) 21개를 실행하고 결과표와 화면 캡처를 남깁니다.
.DESCRIPTION
  먼저 .\web\scripts\start.ps1 로 서버를 켜 두세요. 데모 데이터만 바뀌며 실제 유튜브·AI 는 호출하지 않습니다.
  (시험 중 제안·승인·배치 실행·롤백이 이력과 감사 로그에 기록되고, 설정의 하루 반영 상한은 바꿨다가 원래 값으로 복구합니다.)
  필요한 것: Node.js(LTS)와 Microsoft Edge. Playwright 는 처음 한 번만 %LOCALAPPDATA%\ytweb-e2e 에 자동 설치됩니다(저장소에는 설치되지 않음).
  결과: web\e2e-results\<날짜-시각>\RESULT.md (표+화면 캡처). VS Code 에서 열고 Ctrl+Shift+V 로 미리보기.
.EXAMPLE
  .\web\scripts\e2e.ps1
#>
param([string]$Base = 'http://127.0.0.1:8080', [switch]$OpenReport)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script = Join-Path $root 'web\tests_integration\tools\e2e_functional.mjs'
$playwrightVersion = '1.56.1'

# 1) 서버가 떠 있는지
try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Uri "$Base/api/healthz"; if ($r.StatusCode -ne 200) { throw 'status' } }
catch { Write-Host "[중단] 서버($Base)에 연결할 수 없습니다. 먼저 .\web\scripts\start.ps1 을 실행하고 완료된 뒤 다시 실행하세요." -ForegroundColor Red; exit 2 }

# 2) Node.js
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host '[중단] Node.js 가 없습니다. https://nodejs.org 에서 LTS 버전을 설치한 뒤 PowerShell 을 새로 열어 다시 실행하세요.' -ForegroundColor Red; exit 3 }

# 3) Edge
$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $edge) { Write-Host '[중단] Microsoft Edge 를 찾을 수 없습니다.' -ForegroundColor Red; exit 4 }

# 4) Playwright(처음 한 번만, 저장소 밖에 설치)
$tools = Join-Path $env:LOCALAPPDATA 'ytweb-e2e'
if (-not (Test-Path (Join-Path $tools 'node_modules\playwright'))) {
  Write-Host "시험 도구(Playwright $playwrightVersion)를 처음 한 번 설치합니다(약 1분)..."
  New-Item -ItemType Directory -Force -Path $tools | Out-Null
  Push-Location $tools
  try { if (-not (Test-Path 'package.json')) { '{"name":"ytweb-e2e","private":true}' | Set-Content -Encoding ascii package.json }
        npm install "playwright@$playwrightVersion" --no-audit --no-fund --loglevel=error
        if ($LASTEXITCODE -ne 0) { throw 'npm install 실패' } } finally { Pop-Location }
}

# 5) 실행
$out = Join-Path $root ("web\e2e-results\" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Force -Path $out | Out-Null
$env:E2E_BASE = $Base
$env:E2E_OUT = $out
$env:PW_PATH = ((Join-Path $tools 'node_modules') -replace '\\', '/') + '/'
$env:E2E_CHANNEL = 'msedge'
Write-Host "기능 자동 시험 21개를 실행합니다(약 1~2분). 데모 데이터가 바뀝니다." -ForegroundColor Yellow
$sw = [Diagnostics.Stopwatch]::StartNew()
node $script
$code = $LASTEXITCODE
$sw.Stop()
Write-Host ("소요 {0:N0}초 / 결과표: {1}\RESULT.md" -f $sw.Elapsed.TotalSeconds, $out)
if ($OpenReport -and (Test-Path "$out\RESULT.md")) { Invoke-Item "$out\RESULT.md" }
exit $code
