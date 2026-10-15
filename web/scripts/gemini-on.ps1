<#
.SYNOPSIS
  Gemini(AI 제목 제안) 키를 한 번 연결합니다. 키를 붙여넣고 Enter 를 누르면 web\secrets\gemini_api_key 에 저장하고 서버를 다시 시작합니다.
.DESCRIPTION
  하는 일: (1) 키를 화면에 보이지 않게 입력받기 (2) web\secrets\gemini_api_key 에 저장(줄바꿈 없이, 저장소에 올라가지 않는 폴더) (3) start.ps1 로 다시 시작.
  연결되면 챕터가 없는 영상(쇼츠 포함)도 AI 가 제목 후보를 만듭니다. 끄려면 web\secrets\gemini_api_key 파일을 지우고 start.ps1 을 다시 실행하세요.
  이 스크립트는 Windows 에서 아직 실행해 본 적이 없습니다.
#>
param([string]$Key = '')
$ErrorActionPreference = 'Stop'
$webDir = Split-Path -Parent $PSScriptRoot
$dir = Join-Path $webDir 'secrets'
$file = Join-Path $dir 'gemini_api_key'
if (-not $Key) {
  $sec = Read-Host 'Gemini API 키를 붙여넣고 Enter (화면에 보이지 않습니다)' -AsSecureString
  $Key = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
$Key = $Key.Trim()
if ($Key.Length -lt 20 -or $Key -match '\s') {
  Write-Host '[오류] 키 형식이 아닙니다(공백 없는 긴 문자열). 다시 실행해 키만 붙여넣으세요.' -ForegroundColor Red
  exit 1
}
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
[System.IO.File]::WriteAllText($file, $Key, (New-Object System.Text.UTF8Encoding($false)))
Write-Host '[완료] web\secrets\gemini_api_key 에 저장했습니다.' -ForegroundColor Green
Write-Host '[안내] 서버를 다시 시작합니다...'
& (Join-Path $PSScriptRoot 'start.ps1')
Write-Host ''
Write-Host '다음: 영상 목록에서 쇼츠를 선택해 [선택 영상 AI 제안 생성]을 다시 누르세요.' -ForegroundColor Yellow
