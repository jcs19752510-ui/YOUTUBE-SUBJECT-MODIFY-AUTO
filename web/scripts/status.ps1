<#
.SYNOPSIS
  서비스 상태와 보안 설정(게시 포트가 127.0.0.1 한정인지 등)을 점검합니다.
.PARAMETER Detail
  컨테이너 보안 설정(비루트, 읽기 전용, 권한 제거)도 자세히 출력합니다.
#>
param([switch]$Detail)
. (Join-Path $PSScriptRoot '_common.ps1')

Test-ComposeFileExists
Test-DockerReady
$problems = 0

Write-Host ''
Write-Host '--- 서비스 상태 ---' -ForegroundColor White
$items = @(Get-ComposeServices)
if ($items.Count -eq 0) { Write-Warn '실행 중인 서비스가 없습니다. 시작: .\web\scripts\start.ps1'; exit 1 }
foreach ($svc in $YtwebServices) {
    $it = $items | Where-Object { (Get-Prop $_ 'Service') -eq $svc } | Select-Object -First 1
    if ($null -eq $it) { Write-Warn ("{0,-8} 없음" -f $svc); $problems++; continue }
    $state = [string](Get-Prop $it 'State'); $health = [string](Get-Prop $it 'Health'); $exit = [int](Get-Prop $it 'ExitCode' 0)
    if ($svc -eq 'migrate') {
        if ($state -eq 'exited' -and $exit -eq 0) { Write-Ok ("{0,-8} 마이그레이션 완료" -f $svc) }
        else { Write-Warn ("{0,-8} {1} (종료 코드 {2})" -f $svc, $state, $exit); $problems++ }
    } elseif ($state -eq 'running' -and $health -eq 'healthy') { Write-Ok ("{0,-8} 정상" -f $svc) }
    else { Write-Warn ("{0,-8} {1} / {2}" -f $svc, $state, $health); $problems++ }
}

Write-Host ''
Write-Host '--- 호스트에 열린 포트 (127.0.0.1:8080 하나만 있어야 합니다) ---' -ForegroundColor White
$ps = Invoke-Native -FilePath 'docker' -ArgList @('ps', '-a', '--filter', "label=com.docker.compose.project=$YtwebProject", '--format', '{{.Names}}|{{.Ports}}') -StdoutOnly
foreach ($line in $ps.Output) {
    if (-not $line.Contains('|')) { continue }
    $cname, $ports = $line.Split('|', 2)
    $svc = $cname -replace ('^' + [regex]::Escape($YtwebProject) + '-'), '' -replace '-\d+$', ''
    $published = @($ports.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ -match '->' })
    if ($published.Count -eq 0) { Write-Ok ("{0,-8} 호스트 포트 없음" -f $svc); continue }
    foreach ($p in $published) {
        if ($svc -eq 'web' -and $p -match '^127\.0\.0\.1:8080->8080/tcp$') { Write-Ok ("{0,-8} {1}" -f $svc, $p) }
        else { Write-Host ("[위험] {0,-8} {1}" -f $svc, $p) -ForegroundColor Red; $problems++ }
    }
}
$dp = Invoke-Compose -ArgList @('port', 'web', '8080') -StdoutOnly
if ($dp.ExitCode -eq 0 -and $dp.Output.Count -gt 0) {
    $addr = ([string]($dp.Output | Select-Object -First 1)).Trim()
    if ($addr.StartsWith('127.0.0.1:')) { Write-Ok "docker compose port: $addr" } else { Write-Host "[위험] docker compose port: $addr" -ForegroundColor Red; $problems++ }
}
try {
    $bad = @()
    foreach ($l in [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()) {
        if ($l.Port -eq $YtwebPort -and -not [System.Net.IPAddress]::IsLoopback($l.Address)) { $bad += $l.Address.ToString() }
    }
    if ($bad.Count -gt 0) { Write-Host ("[위험] 이 PC 의 포트 {0} 가 루프백이 아닌 주소에도 열려 있습니다: {1}" -f $YtwebPort, ($bad -join ', ')) -ForegroundColor Red; $problems++ }
    else { Write-Ok "이 PC 의 포트 $YtwebPort 리스너는 루프백(127.0.0.1)뿐입니다." }
} catch { Write-Warn '이 PC 의 리스너 주소를 확인하지 못했습니다.' }

Write-Host ''
Write-Host '--- 응답 확인 ---' -ForegroundColor White
foreach ($path in @('/api/healthz', '/api/readyz')) {
    try {
        $resp = Invoke-WebRequest -Uri ($YtwebUrl + $path) -UseBasicParsing -TimeoutSec 5
        Write-Ok ("{0} -> {1} {2}" -f $path, [int]$resp.StatusCode, ([string]$resp.Content).Trim())
    } catch {
        Write-Warn ("{0} 응답 없음: {1}" -f $path, $_.Exception.Message); $problems++
    }
}

if ($Detail) {
    Write-Host ''
    Write-Host '--- 컨테이너 보안 설정 ---' -ForegroundColor White
    $ids = Invoke-Native -FilePath 'docker' -ArgList @('ps', '-aq', '--filter', "label=com.docker.compose.project=$YtwebProject") -StdoutOnly
    foreach ($id in $ids.Output) {
        if (-not $id.Trim()) { continue }
        $fmt = '{{.Name}} user={{.Config.User}} readOnly={{.HostConfig.ReadonlyRootfs}} privileged={{.HostConfig.Privileged}} capDrop={{.HostConfig.CapDrop}} security={{.HostConfig.SecurityOpt}} network={{.HostConfig.NetworkMode}}'
        $r = Invoke-Native -FilePath 'docker' -ArgList @('inspect', '--format', $fmt, $id.Trim()) -StdoutOnly
        $r.Output | ForEach-Object { Write-Host $_ }
    }
}

Write-Host ''
if ($problems -eq 0) { Write-Ok "점검 결과: 문제 없음. 접속 주소 $YtwebUrl"; exit 0 }
Write-Warn "점검 결과: 확인이 필요한 항목 $problems 건. 로그: .\web\scripts\logs.ps1"
exit 1
