<#
.SYNOPSIS
  ytitle 웹을 종료합니다. 데이터(데이터베이스·설정 키·백업)는 그대로 보존됩니다.
#>
. (Join-Path $PSScriptRoot '_common.ps1')

Test-ComposeFileExists
Test-DockerReady
Write-Info '컨테이너를 정상 종료합니다(진행 중인 작업을 마무리하느라 최대 1분쯤 걸릴 수 있습니다).'
# 주의: 데이터 볼륨을 지우는 옵션을 절대 넣지 않는다. 데이터 삭제는 reset-demo.ps1 -DeleteVolumes 에서만 가능하다.
$r = Invoke-Compose -ArgList @('down')
if ($r.ExitCode -ne 0) { Stop-Script '종료에 실패했습니다.' 'Docker Desktop 이 실행 중인지 확인하고 다시 시도하세요.' }
Write-Ok '종료했습니다. 데이터는 보존되어 있습니다. 다시 시작: .\web\scripts\start.ps1'
Write-Warn '데이터까지 지우려면 reset-demo.ps1 를 쓰세요(확인 문구가 필요합니다).'
exit 0
