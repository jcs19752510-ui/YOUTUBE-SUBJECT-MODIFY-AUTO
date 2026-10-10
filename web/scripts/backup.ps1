<#
.SYNOPSIS
  데이터베이스를 백업합니다(pg_dump 사용자 정의 형식, 소유자 계정 사용).
.DESCRIPTION
  web\backups\ 에 ytweb-날짜-시각.dump 파일을 만들고 크기와 pg_restore --list 로 무결성을 확인합니다.
  백업에는 영상·제안·승인·이력·감사 로그가 들어갑니다. 비밀번호(web\secrets)와 승인·감사용 서명 키(별도 볼륨)는
  들어가지 않으므로 필요하면 따로 보관하세요. 백업 파일은 암호화되지 않으니 이 폴더를 남에게 주지 마세요.
.PARAMETER Prefix
  파일 이름 앞부분(기본 ytweb).
#>
param([ValidatePattern('^[A-Za-z0-9-]+$')][string]$Prefix = 'ytweb')
. (Join-Path $PSScriptRoot '_common.ps1')

Test-ComposeFileExists
Test-DockerReady
if (-not (Test-DbRunning)) {
    Stop-Script '데이터베이스 컨테이너가 실행 중이 아닙니다.' '먼저 .\web\scripts\start.ps1 로 시작한 뒤 다시 실행하세요.'
}

$name = '{0}-{1}.dump' -f $Prefix, (Get-Date -Format 'yyyyMMdd-HHmmss')
Assert-BackupFileName $name
if (-not (Test-Path -LiteralPath $YtwebBackupDir)) { New-Item -ItemType Directory -Path $YtwebBackupDir -Force | Out-Null }
[void](Set-OwnerOnlyAcl $YtwebBackupDir)
$hostFile = Join-Path $YtwebBackupDir $name

Write-Info "백업 중: $name"
$dump = Invoke-Compose -ArgList @('exec', '-T', 'db', 'ytweb-db', 'dump', $name) -Capture
if ($dump.ExitCode -ne 0) {
    $dump.Output | ForEach-Object { Write-Host $_ }
    Stop-Script '백업에 실패했습니다.' '.\web\scripts\logs.ps1 -Service db 로 원인을 확인하세요.'
}
$inContainerSize = 0
foreach ($l in $dump.Output) { if ($l -match '크기\(바이트\):\s*(\d+)') { $inContainerSize = [int64]$Matches[1] } }

$list = Invoke-Compose -ArgList @('exec', '-T', 'db', 'ytweb-db', 'list', $name) -Capture
if ($list.ExitCode -ne 0) {
    [void](Invoke-Compose -ArgList @('exec', '-T', 'db', 'ytweb-db', 'remove', $name) -Quiet)
    Stop-Script '백업 파일 검증(pg_restore --list)에 실패했습니다. 파일을 삭제했습니다.' '다시 시도하고, 계속 실패하면 로그를 확인하세요.'
}

# 바이너리를 PowerShell 리디렉션으로 받으면 손상될 수 있어, 컨테이너 안에 만든 파일을 docker compose cp 로 꺼낸다.
Push-Location $YtwebBackupDir
try {
    $cp = Invoke-Compose -ArgList @('cp', "db:/backups/$name", "./$name")
} finally {
    Pop-Location
}
if ($cp.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $hostFile)) {
    Stop-Script '백업 파일을 내 PC 로 꺼내지 못했습니다.' '디스크 공간과 web\backups 폴더 권한을 확인하세요. 컨테이너 안의 파일은 남아 있습니다.'
}
[void](Set-OwnerOnlyAcl $hostFile)
$size = (Get-Item -LiteralPath $hostFile).Length
if ($size -le 0 -or ($inContainerSize -gt 0 -and $size -ne $inContainerSize)) {
    Stop-Script "백업 파일 크기가 맞지 않습니다(PC: $size, 컨테이너: $inContainerSize)." '다시 백업하세요. 이 파일은 사용하지 마세요.'
}
$hash = (Get-FileHash -LiteralPath $hostFile -Algorithm SHA256).Hash.ToLower()
[System.IO.File]::WriteAllText("$hostFile.sha256", "$hash  $name`n", (New-Object System.Text.UTF8Encoding($false)))
[void](Invoke-Compose -ArgList @('exec', '-T', 'db', 'ytweb-db', 'remove', $name) -Quiet)

Write-Ok "백업 완료: $hostFile"
Write-Host ("  크기: {0:N0} 바이트   {1}" -f $size, ($list.Output | Select-Object -Last 1))
Write-Host "  SHA-256: $hash  (같은 폴더의 .sha256 파일에도 저장)"
Write-Host '  비밀번호·서명 키는 이 파일에 들어 있지 않습니다. 복원: .\web\scripts\restore.ps1 -File <파일명>'
exit 0
