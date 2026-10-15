<#
.SYNOPSIS
  백업 파일로 데이터베이스를 복원합니다. 현재 데이터는 덮어써집니다.
.PARAMETER File
  복원할 .dump 파일(web\backups 안의 파일 이름 또는 전체 경로).
.PARAMETER Latest
  web\backups 에서 가장 최근 파일을 고릅니다.
.PARAMETER ConfirmText
  확인 문구를 미리 지정할 때 씁니다(자동화용). 생략하면 직접 입력합니다.
.PARAMETER SkipSafetyBackup
  복원 전 현재 데이터 자동 백업을 건너뜁니다(권장하지 않음).
#>
param(
    [string]$File = '',
    [switch]$Latest,
    [string]$ConfirmText = '',
    [switch]$SkipSafetyBackup
)
. (Join-Path $PSScriptRoot '_common.ps1')

Test-ComposeFileExists
Test-DockerReady

if ($Latest) {
    $cand = @(Get-ChildItem -LiteralPath $YtwebBackupDir -Filter '*.dump' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($cand.Count -eq 0) { Stop-Script 'web\backups 에 백업 파일이 없습니다.' '.\web\scripts\backup.ps1 로 먼저 백업하세요.' }
    $File = $cand[0].FullName
}
if (-not $File) { Stop-Script '복원할 파일을 지정하세요.' '예: .\web\scripts\restore.ps1 -File ytweb-20260101-120000.dump   또는   -Latest' }
if (-not [System.IO.Path]::IsPathRooted($File)) { $File = Join-Path $YtwebBackupDir $File }
if (-not (Test-Path -LiteralPath $File)) { Stop-Script "파일이 없습니다: $File" 'web\backups 폴더의 파일 이름을 확인하세요.' }
$leaf = Split-Path -Leaf $File
Assert-BackupFileName $leaf
if ((Get-Item -LiteralPath $File).Length -le 0) { Stop-Script '백업 파일이 비어 있습니다.' '다른 백업 파일을 고르세요.' }

$shaFile = "$File.sha256"
if (Test-Path -LiteralPath $shaFile) {
    $expected = ((Get-Content -LiteralPath $shaFile -TotalCount 1) -split '\s+')[0].ToLower()
    $actual = (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLower()
    if ($expected -ne $actual) { Stop-Script '백업 파일의 SHA-256 이 기록된 값과 다릅니다(파일이 바뀌었거나 손상됨).' '이 파일은 복원하지 마세요. 다른 백업을 고르세요.' }
    Write-Ok 'SHA-256 확인'
} else {
    Write-Warn 'SHA-256 기록 파일(.sha256)이 없어 무결성 해시는 확인하지 못했습니다(pg_restore 목차 검사는 진행합니다).'
}

if (-not (Test-DbRunning)) { Stop-Script '데이터베이스 컨테이너가 실행 중이 아닙니다.' '먼저 .\web\scripts\start.ps1 로 시작한 뒤 다시 실행하세요.' }

Write-Host ''
Write-Host '!!! 경고 !!!' -ForegroundColor Red
Write-Host '복원하면 지금 데이터베이스의 모든 데이터(영상, 제안, 승인, 이력, 감사 로그)가 백업 시점의 내용으로 바뀝니다.' -ForegroundColor Red
Write-Host "복원할 파일: $File"
if (-not (Read-ConfirmText -Expected '복원합니다' -Provided $ConfirmText -Prompt '계속하려면 "복원합니다" 를 그대로 입력하세요')) {
    Write-Info '확인 문구가 맞지 않아 취소했습니다. 아무것도 바꾸지 않았습니다.'
    exit 2
}

if (-not $SkipSafetyBackup) {
    Write-Info '복원 전 현재 데이터를 자동 백업합니다(되돌릴 수 있도록).'
    & (Join-Path $PSScriptRoot 'backup.ps1') -Prefix 'pre-restore'
    if ($LASTEXITCODE -ne 0) { Stop-Script '복원 전 자동 백업에 실패해 복원을 중단했습니다.' '원인을 해결하거나, 데이터를 버려도 될 때만 -SkipSafetyBackup 을 쓰세요.' }
}

Write-Info '웹·API·워커를 잠시 멈춥니다.'
[void](Invoke-Compose -ArgList @('stop', 'web', 'api', 'worker') -Quiet)

$ok = $false
# docker cp 는 원본 파일의 모드를 그대로 가져가므로, 컨테이너 안의 비루트 postgres 가 읽을 수 있게 임시 사본(읽기 허용)을 쓴다.
$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ('ytweb-restore-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
try {
    $tmpFile = Join-Path $tmpDir $leaf
    Copy-Item -LiteralPath $File -Destination $tmpFile
    if ($env:OS -ne 'Windows_NT') { try { [System.IO.File]::SetUnixFileMode($tmpFile, 'UserRead,GroupRead,OtherRead') } catch { } }
    Push-Location $tmpDir
    try {
        $cp = Invoke-Compose -ArgList @('cp', "./$leaf", "db:/backups/$leaf")
    } finally {
        Pop-Location
    }
    if ($cp.ExitCode -eq 0) {
        Write-Info '복원 중(하나의 트랜잭션으로 처리되어, 실패하면 기존 데이터는 그대로 남습니다)'
        $rs = Invoke-Compose -ArgList @('exec', '-T', 'db', 'ytweb-db', 'restore', $leaf)
        $ok = ($rs.ExitCode -eq 0)
        [void](Invoke-Compose -ArgList @('exec', '-T', 'db', 'ytweb-db', 'remove', $leaf) -Quiet)
    }
} finally {
    Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Info '서비스를 다시 시작합니다(필요한 마이그레이션이 자동 적용됩니다).'
$up = Invoke-Compose -ArgList @('up', '-d')
if ($up.ExitCode -ne 0) { Write-Warn '서비스 재시작에 실패했습니다. .\web\scripts\start.ps1 를 실행해 보세요.' }

if (-not $ok) {
    Stop-Script '복원에 실패했습니다. 기존 데이터는 바뀌지 않았을 것입니다(단일 트랜잭션).' "위 메시지를 확인하세요. 복원 전 자동 백업(pre-restore-*.dump)이 web\backups 에 있습니다."
}
if (-not (Wait-ForStack -TimeoutSec 240)) { exit 1 }

Write-Host ''
Write-Host '--- 복원 후 테이블 행 수 ---' -ForegroundColor White
$cnt = Invoke-Compose -ArgList @('exec', '-T', 'db', 'ytweb-db', 'counts') -Capture
$cnt.Output | ForEach-Object { Write-Host "  $_" }
Write-Ok '복원이 끝났습니다. 위 행 수가 백업 시점과 같은지 확인하세요.'
exit 0
