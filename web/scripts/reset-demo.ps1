<#
.SYNOPSIS
  데모 데이터를 초기화합니다(확인 문구 필요).
.DESCRIPTION
  기본: 데이터베이스의 테이블을 모두 지우고 다시 만듭니다(빈 상태로 시작). 비밀번호·서명 키·백업 파일은 유지합니다.
  -DeleteVolumes: 데이터베이스·서명 키·백업용 Docker 볼륨까지 모두 삭제합니다. 되돌릴 수 없습니다.
  어느 쪽이든 먼저 현재 데이터를 자동 백업합니다(-SkipBackup 으로 생략 가능).
#>
param(
    [switch]$DeleteVolumes,
    [switch]$SkipBackup,
    [string]$ConfirmText = ''
)
. (Join-Path $PSScriptRoot '_common.ps1')

Test-ComposeFileExists
Test-DockerReady

Write-Host ''
if ($DeleteVolumes) {
    $phrase = '모든 데이터 삭제'
    Write-Host '!!! 매우 위험 !!!' -ForegroundColor Red
    Write-Host 'Docker 볼륨(데이터베이스, 승인·감사 서명 키, 컨테이너 안 백업)을 모두 삭제합니다. 되돌릴 수 없습니다.' -ForegroundColor Red
    Write-Host 'web\backups 폴더의 백업 파일과 web\secrets 의 비밀번호 파일은 지우지 않습니다.'
} else {
    $phrase = '데모 초기화'
    Write-Host '!!! 경고 !!!' -ForegroundColor Red
    Write-Host '데이터베이스의 모든 데이터(데모 영상, 제안, 승인, 이력, 감사 로그)를 지우고 빈 상태로 다시 만듭니다.' -ForegroundColor Red
}
if (-not (Read-ConfirmText -Expected $phrase -Provided $ConfirmText -Prompt "계속하려면 `"$phrase`" 를 그대로 입력하세요")) {
    Write-Info '확인 문구가 맞지 않아 취소했습니다. 아무것도 바꾸지 않았습니다.'
    exit 2
}

if (-not $SkipBackup) {
    if (Test-DbRunning) {
        Write-Info '초기화 전 현재 데이터를 자동 백업합니다.'
        & (Join-Path $PSScriptRoot 'backup.ps1') -Prefix 'pre-reset'
        if ($LASTEXITCODE -ne 0) { Stop-Script '자동 백업에 실패해 초기화를 중단했습니다.' '데이터를 버려도 될 때만 -SkipBackup 을 쓰세요.' }
    } else {
        Write-Warn '데이터베이스가 실행 중이 아니어서 자동 백업을 건너뜁니다.'
    }
}

if ($DeleteVolumes) {
    Write-Info '컨테이너와 볼륨을 삭제합니다.'
    $r = Invoke-Compose -ArgList @('down', '--volumes')
    if ($r.ExitCode -ne 0) { Stop-Script '삭제에 실패했습니다.' 'Docker Desktop 상태를 확인하고 다시 시도하세요.' }
    Write-Ok '삭제했습니다. 처음부터 다시 시작하려면 .\web\scripts\start.ps1 를 실행하세요(비밀번호 파일은 그대로 다시 쓰입니다).'
    exit 0
}

if (-not (Test-DbRunning)) { Stop-Script '데이터베이스 컨테이너가 실행 중이 아닙니다.' '먼저 .\web\scripts\start.ps1 로 시작한 뒤 다시 실행하세요.' }
Write-Info '웹·API·워커를 잠시 멈추고 데이터를 지웁니다.'
[void](Invoke-Compose -ArgList @('stop', 'web', 'api', 'worker') -Quiet)
$rs = Invoke-Compose -ArgList @('exec', '-T', 'db', 'ytweb-db', 'reset-schema')
if ($rs.ExitCode -ne 0) {
    [void](Invoke-Compose -ArgList @('up', '-d') -Quiet)
    Stop-Script '초기화에 실패했습니다.' '.\web\scripts\logs.ps1 -Service db 로 원인을 확인하세요.'
}
Write-Info '서비스를 다시 시작합니다(마이그레이션이 빈 테이블을 다시 만듭니다).'
$up = Invoke-Compose -ArgList @('up', '-d')
if ($up.ExitCode -ne 0) { Stop-Script '서비스 재시작에 실패했습니다.' '.\web\scripts\start.ps1 를 실행해 보세요.' }
if (-not (Wait-ForStack -TimeoutSec 240)) { exit 1 }
Write-Ok "초기화 완료. 브라우저에서 $YtwebUrl 를 새로 고치세요."
exit 0
