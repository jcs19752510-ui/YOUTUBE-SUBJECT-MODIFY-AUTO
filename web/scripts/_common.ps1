# 공통 함수 모음. 다른 스크립트가 `. (Join-Path $PSScriptRoot '_common.ps1')` 로 불러온다. 직접 실행하지 않는다.
# Windows PowerShell 5.1 과 PowerShell 7 모두에서 동작하도록 작성했다.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $OutputEncoding = [Console]::OutputEncoding
} catch { }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

$YtwebWebDir      = Split-Path -Parent $PSScriptRoot
$YtwebComposeFile = Join-Path $YtwebWebDir 'compose.yaml'
$YtwebSecretsDir  = Join-Path $YtwebWebDir 'secrets'
$YtwebBackupDir   = Join-Path $YtwebWebDir 'backups'
$YtwebPort        = 8080
$YtwebUrl         = 'http://127.0.0.1:8080'
# 테스트용으로 다른 프로젝트 이름을 쓸 때만 YTWEB_PROJECT 환경변수를 지정한다(운영 데이터와 분리).
$YtwebProject     = if ($env:YTWEB_PROJECT) { $env:YTWEB_PROJECT } else { 'ytweb' }
$YtwebSecretNames = @('db_superuser_password', 'db_owner_password', 'db_app_password')
$YtwebServices    = @('db', 'migrate', 'api', 'worker', 'web')

function Write-Info { param([string]$Message) Write-Host "[안내] $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Message) Write-Host "[완료] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[주의] $Message" -ForegroundColor Yellow }

function Stop-Script {
    param([string]$Message, [string]$Hint = '', [int]$Code = 1)
    Write-Host "[오류] $Message" -ForegroundColor Red
    if ($Hint) { Write-Host "[조치] $Hint" -ForegroundColor Yellow }
    exit $Code
}

# 외부 명령 실행. docker 는 진행 상황을 stderr 로 내보내므로 ErrorActionPreference 를 잠시 Continue 로 바꾼다
# (Windows PowerShell 5.1 에서 stderr 출력이 곧바로 예외가 되는 문제 방지).
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$ArgList = @(),
        [switch]$Capture,
        [switch]$StdoutOnly,
        [switch]$Quiet
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $lines = New-Object System.Collections.Generic.List[string]
    $code = 0
    try {
        if ($StdoutOnly) {
            & $FilePath @ArgList 2>$null | ForEach-Object { [void]$lines.Add("$_") }
        } else {
            & $FilePath @ArgList 2>&1 | ForEach-Object {
                $text = "$_"
                if ($Capture) { [void]$lines.Add($text) }
                elseif (-not $Quiet) { Write-Host $text }
            }
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    return [pscustomobject]@{ ExitCode = $code; Output = $lines.ToArray() }
}

function Invoke-Compose {
    param([string[]]$ArgList, [switch]$Capture, [switch]$StdoutOnly, [switch]$Quiet)
    $all = @('compose', '-p', $YtwebProject, '-f', $YtwebComposeFile) + $ArgList
    return Invoke-Native -FilePath 'docker' -ArgList $all -Capture:$Capture -StdoutOnly:$StdoutOnly -Quiet:$Quiet
}

function Get-Prop {
    param($Object, [string]$Name, $Default = '')
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p -or $null -eq $p.Value) { return $Default }
    return $p.Value
}

# 1단계: Docker 설치·실행·모드·Compose 버전 확인
function Test-DockerReady {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Stop-Script 'Docker 가 설치되어 있지 않거나 PATH 에 없습니다.' 'Docker Desktop 을 설치한 뒤(https://www.docker.com/products/docker-desktop/) PowerShell 을 새로 열고 다시 실행하세요.'
    }
    $info = Invoke-Native -FilePath 'docker' -ArgList @('info', '--format', '{{.ServerVersion}}|{{.OSType}}') -StdoutOnly
    if ($info.ExitCode -ne 0 -or $info.Output.Count -eq 0) {
        Stop-Script 'Docker 엔진에 연결할 수 없습니다.' 'Docker Desktop 을 먼저 실행하세요. 작업 표시줄의 고래 아이콘이 "실행 중"으로 바뀐 뒤(1~2분) 다시 시도하세요. 계속 안 되면 PowerShell 에서 `wsl --update` 후 PC 를 다시 시작해 보세요(WSL2 사용 시).'
    }
    $parts = ($info.Output | Select-Object -First 1).Split('|')
    if ($parts.Count -ge 2 -and $parts[1].Trim() -ne 'linux') {
        Stop-Script 'Docker 가 Windows 컨테이너 모드입니다.' '작업 표시줄의 Docker 아이콘을 오른쪽 클릭해 "Switch to Linux containers..." 를 선택하세요.'
    }
    $cv = Invoke-Native -FilePath 'docker' -ArgList @('compose', 'version', '--short') -StdoutOnly
    if ($cv.ExitCode -ne 0 -or $cv.Output.Count -eq 0) {
        Stop-Script 'Docker Compose(v2)를 찾을 수 없습니다.' 'Docker Desktop 을 최신 버전으로 업데이트하세요.'
    }
    $verText = ($cv.Output | Select-Object -First 1).Trim().TrimStart('v')
    $m = [regex]::Match($verText, '^(\d+)\.(\d+)')
    if ($m.Success) {
        $major = [int]$m.Groups[1].Value; $minor = [int]$m.Groups[2].Value
        if ($major -lt 2 -or ($major -eq 2 -and $minor -lt 20)) {
            Stop-Script "Docker Compose 버전이 너무 낮습니다($verText). 2.20 이상이 필요합니다." 'Docker Desktop 을 최신 버전으로 업데이트하세요.'
        }
    }
    Write-Ok ("Docker 엔진 {0} / Compose {1} 확인" -f $parts[0], $verText)
    if ($env:OS -eq 'Windows_NT' -and (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        $w = Invoke-Native -FilePath 'wsl.exe' -ArgList @('--status') -Quiet
        if ($w.ExitCode -ne 0) {
            Write-Warn 'WSL 상태를 확인하지 못했습니다. Docker Desktop 이 WSL2 를 쓰는 설정이면 `wsl --update` 를 실행해 보세요.'
        }
    }
}

function Test-ComposeFileExists {
    if (-not (Test-Path -LiteralPath $YtwebComposeFile)) {
        Stop-Script "compose 파일을 찾을 수 없습니다: $YtwebComposeFile" '저장소를 올바르게 받았는지 확인하세요(web 폴더가 있어야 합니다).'
    }
}

function Get-ComposeServices {
    $r = Invoke-Compose -ArgList @('ps', '-a', '--format', 'json') -StdoutOnly
    $text = ($r.Output -join "`n").Trim()
    $items = @()
    if (-not $text) { return $items }
    if ($text.StartsWith('[')) {
        $items = @($text | ConvertFrom-Json)
    } else {
        foreach ($line in ($text -split "`n")) {
            if ($line.Trim()) { $items += ($line | ConvertFrom-Json) }
        }
    }
    return $items
}

function Test-VolumeExists {
    param([string]$Name)
    $r = Invoke-Native -FilePath 'docker' -ArgList @('volume', 'ls', '-q', '--filter', "name=^${YtwebProject}_${Name}$") -StdoutOnly
    return ($r.ExitCode -eq 0 -and @($r.Output | Where-Object { $_.Trim() }).Count -gt 0)
}

function Test-SecretsPresent {
    foreach ($n in $YtwebSecretNames) {
        $p = Join-Path $YtwebSecretsDir $n
        if (-not (Test-Path -LiteralPath $p) -or (Get-Item -LiteralPath $p).Length -eq 0) { return $false }
    }
    return $true
}

function Test-PortInUse {
    param([int]$Port)
    try {
        $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
        foreach ($l in $listeners) { if ($l.Port -eq $Port) { return $true } }
    } catch { }
    return $false
}

function Set-OwnerOnlyAcl {
    param([string]$Path)
    if ($env:OS -ne 'Windows_NT') { return $true }
    try {
        $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
        $isDir = (Get-Item -LiteralPath $Path -Force).PSIsContainer
        $acl = Get-Acl -LiteralPath $Path
        $acl.SetAccessRuleProtection($true, $false)
        foreach ($r in @($acl.Access)) { [void]$acl.RemoveAccessRule($r) }
        if ($isDir) {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        } else {
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'Allow')
        }
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $Path -AclObject $acl
        return $true
    } catch {
        Write-Warn "접근 권한을 현재 사용자 전용으로 제한하지 못했습니다: $Path ($($_.Exception.Message))"
        return $false
    }
}

function New-RandomSecret {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}

# 2단계: 비밀 파일 준비. 값은 화면·로그에 출력하지 않는다. 이미 있는 파일은 절대 덮어쓰지 않는다.
function Initialize-Secrets {
    if (Test-SecretsPresent) {
        Write-Ok '비밀 파일이 이미 있습니다(기존 파일을 그대로 사용합니다).'
        return
    }
    foreach ($n in $YtwebSecretNames) {
        $p = Join-Path $YtwebSecretsDir $n
        if ((Test-Path -LiteralPath $p) -and (Get-Item -LiteralPath $p).Length -gt 0) { continue }
        if (Test-VolumeExists 'pgdata') {
            Stop-Script "비밀 파일($n)이 없는데 데이터베이스 볼륨은 이미 있습니다." '새 비밀번호를 만들면 기존 데이터베이스에 접속할 수 없습니다. 백업해 둔 web\secrets 폴더를 되돌려 놓으세요. 데이터를 버리고 처음부터 시작하려면 reset-demo.ps1 -DeleteVolumes 를 먼저 실행하세요.'
        }
    }
    if (-not (Test-Path -LiteralPath $YtwebSecretsDir)) {
        New-Item -ItemType Directory -Path $YtwebSecretsDir -Force | Out-Null
    }
    [void](Set-OwnerOnlyAcl $YtwebSecretsDir)
    $enc = New-Object System.Text.UTF8Encoding($false)
    foreach ($n in $YtwebSecretNames) {
        $p = Join-Path $YtwebSecretsDir $n
        if ((Test-Path -LiteralPath $p) -and (Get-Item -LiteralPath $p).Length -gt 0) { continue }
        [System.IO.File]::WriteAllText($p, (New-RandomSecret), $enc)
        [void](Set-OwnerOnlyAcl $p)
        Write-Ok "비밀 파일을 만들었습니다: web\secrets\$n (내용은 표시하지 않습니다)"
    }
    Write-Warn 'web\secrets 폴더는 데이터베이스 비밀번호입니다. 지우거나 다른 곳에 올리지 마세요. 저장소(git)에서는 제외되어 있습니다.'
}

# 서비스 상태가 모두 준비될 때까지 기다린다. 실패하면 원인 로그 일부를 보여 주고 $false 를 돌려준다.
function Wait-ForStack {
    param([int]$TimeoutSec = 300)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $lastReport = ''
    while ((Get-Date) -lt $deadline) {
        $items = @(Get-ComposeServices)
        $ready = 0; $total = $YtwebServices.Count
        $summary = @()
        foreach ($svc in $YtwebServices) {
            $it = $items | Where-Object { (Get-Prop $_ 'Service') -eq $svc } | Select-Object -First 1
            if ($null -eq $it) { $summary += "$svc=없음"; continue }
            $state = [string](Get-Prop $it 'State'); $health = [string](Get-Prop $it 'Health'); $exit = [int](Get-Prop $it 'ExitCode' 0)
            if ($svc -eq 'migrate') {
                if ($state -eq 'exited' -and $exit -eq 0) { $ready++; $summary += 'migrate=완료' }
                elseif ($state -eq 'exited') { Show-ServiceFailure $svc "마이그레이션이 실패했습니다(종료 코드 $exit)."; return $false }
                else { $summary += 'migrate=실행 중' }
                continue
            }
            if ($state -eq 'running' -and $health -eq 'healthy') { $ready++; $summary += "$svc=정상" }
            elseif ($state -eq 'exited' -or $state -eq 'dead') { Show-ServiceFailure $svc "$svc 컨테이너가 종료되었습니다(종료 코드 $exit)."; return $false }
            else { $summary += "$svc=$state/$health" }
        }
        $report = $summary -join '  '
        if ($report -ne $lastReport) { Write-Info $report; $lastReport = $report }
        if ($ready -eq $total) { return $true }
        Start-Sleep -Seconds 3
    }
    Write-Warn "제한 시간($TimeoutSec 초) 안에 모든 서비스가 준비되지 않았습니다."
    $bad = @(Get-ComposeServices | Where-Object { (Get-Prop $_ 'Service') -ne 'migrate' -and (Get-Prop $_ 'Health') -ne 'healthy' })
    foreach ($b in $bad) { Show-ServiceFailure ([string](Get-Prop $b 'Service')) '아직 정상 상태가 아닙니다.' }
    return $false
}

function Show-ServiceFailure {
    param([string]$Service, [string]$Reason)
    Write-Host "[오류] $Reason" -ForegroundColor Red
    Write-Host "----- $Service 로그(마지막 25줄) -----" -ForegroundColor Yellow
    [void](Invoke-Compose -ArgList @('logs', '--no-color', '--tail', '25', $Service))
    Write-Host '-----' -ForegroundColor Yellow
    Write-Host "[조치] 전체 로그: .\web\scripts\logs.ps1 -Service $Service   /   원인을 모르면 위 로그를 복사해 문의하세요(비밀번호는 로그에 나오지 않습니다)." -ForegroundColor Yellow
}

function Read-ConfirmText {
    param([string]$Expected, [string]$Provided = '', [string]$Prompt)
    if ($Provided) { return ($Provided -eq $Expected) }
    $typed = Read-Host $Prompt
    return ($typed -eq $Expected)
}

function Assert-BackupFileName {
    param([string]$Name)
    if ($Name -notmatch '^[A-Za-z0-9._-]+\.dump$') {
        Stop-Script "백업 파일 이름이 올바르지 않습니다: $Name" '영문, 숫자, . - _ 만 쓰는 .dump 파일이어야 합니다.'
    }
}

function Test-DbRunning {
    $items = @(Get-ComposeServices)
    $db = $items | Where-Object { (Get-Prop $_ 'Service') -eq 'db' } | Select-Object -First 1
    return ($null -ne $db -and (Get-Prop $db 'State') -eq 'running' -and (Get-Prop $db 'Health') -eq 'healthy')
}
