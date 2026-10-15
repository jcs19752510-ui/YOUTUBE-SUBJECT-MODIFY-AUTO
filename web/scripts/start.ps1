<#
.SYNOPSIS
  유튜브 제목 웹(데모 모드)을 시작합니다. 처음 한 번 실행하면 필요한 준비를 모두 합니다.
.DESCRIPTION
  1) Docker 설치·실행 확인  2) 비밀번호 파일 생성(없을 때만)  3) 포트 8080 점검
  4) 이미지 빌드와 컨테이너 시작  5) 준비될 때까지 대기  6) 접속 주소 안내
.PARAMETER OpenBrowser
  준비가 끝나면 기본 브라우저로 접속 주소를 엽니다.
.PARAMETER NoBuild
  이미지를 다시 빌드하지 않고 기존 이미지로 시작합니다.
.PARAMETER TimeoutSec
  준비 완료까지 기다리는 최대 시간(초). 처음 실행은 이미지 빌드 때문에 오래 걸릴 수 있습니다.
#>
param(
    [switch]$OpenBrowser,
    [switch]$NoBuild,
    [int]$TimeoutSec = 300
)
. (Join-Path $PSScriptRoot '_common.ps1')

Write-Host ''
Write-Host '=== 유튜브 제목 웹(데모 모드) 시작 ===' -ForegroundColor White
Write-Host '데모 모드: 가짜 영상 데이터만 쓰며 유튜브·AI 서비스에는 아무것도 전송하지 않습니다.'
Write-Host ''

Write-Info '1/5 Docker 확인'
Test-ComposeFileExists
Test-DockerReady

Write-Info '2/5 비밀 파일 확인'
Initialize-Secrets

# 관리자 로그인 설정 확인(값은 화면·로그에 출력하지 않고 있다/없다만 안내한다. 입력을 받지 않는다. 없어도 계속 진행한다 = 로그인 불가로 닫힘)
$adminEnvFile = Join-Path $YtwebWebDir '.env'
$adminIdSet = $false
$adminPwSet = $false
if (Test-Path $adminEnvFile) {
    foreach ($envLine in [System.IO.File]::ReadAllLines($adminEnvFile)) {
        if ($envLine -match '^\s*YTWEB_ADMIN_ID\s*=\s*\S') { $adminIdSet = $true }
        if ($envLine -match '^\s*YTWEB_ADMIN_PASSWORD\s*=\s*\S') { $adminPwSet = $true }
    }
}
if ($adminIdSet -and $adminPwSet) {
    Write-Ok '관리자 로그인 설정이 있습니다(web\.env 의 아이디·비밀번호; 값은 표시하지 않음)'
} else {
    Write-Warn '관리자 로그인 설정이 없습니다. 이대로 시작하면 서버는 뜨지만 로그인할 수 없습니다.'
    Write-Host '  해결 방법:' -ForegroundColor Yellow
    Write-Host '   1) 메모장으로 web\.env 파일을 엽니다(없으면 새로 만듭니다; 저장소 맨 위 폴더 아래 web 폴더).' -ForegroundColor Yellow
    Write-Host '   2) 아래 두 줄을 추가합니다(아이디 영문·숫자 4~20자, 비밀번호 8~64자; # 과 따옴표는 쓰지 마세요).' -ForegroundColor Yellow
    Write-Host '        YTWEB_ADMIN_ID=원하는아이디' -ForegroundColor Yellow
    Write-Host '        YTWEB_ADMIN_PASSWORD=원하는비밀번호' -ForegroundColor Yellow
    Write-Host '   3) 저장한 뒤 .\web\scripts\start.ps1 을 다시 실행합니다.' -ForegroundColor Yellow
}

Write-Info '3/5 포트 확인'
$own = @(Get-ComposeServices | Where-Object { (Get-Prop $_ 'Service') -eq 'web' -and (Get-Prop $_ 'State') -eq 'running' })
if ($own.Count -eq 0 -and (Test-PortInUse $YtwebPort)) {
    Stop-Script "포트 $YtwebPort 를 다른 프로그램이 이미 사용 중입니다." "사용 중인 프로그램을 종료한 뒤 다시 실행하세요. 어떤 프로그램인지 확인: PowerShell 에서 'Get-NetTCPConnection -LocalPort $YtwebPort -State Listen' 를 실행하면 OwningProcess(번호)가 나오고, 'Get-Process -Id 번호' 로 프로그램 이름을 볼 수 있습니다."
}
Write-Ok "포트 $YtwebPort 사용 가능(또는 이미 이 프로그램이 사용 중)"

Write-Info '4/5 이미지 빌드 및 컨테이너 시작 (처음에는 5~15분 걸릴 수 있습니다)'
$upArgs = @('up', '-d')
if (-not $NoBuild) { $upArgs += '--build' }
$up = Invoke-Compose -ArgList $upArgs
if ($up.ExitCode -ne 0) {
    Write-Host ''
    Write-Host '[오류] 시작에 실패했습니다. 위 메시지를 확인하세요.' -ForegroundColor Red
    $items = @(Get-ComposeServices)
    foreach ($it in $items) {
        $svc = [string](Get-Prop $it 'Service')
        if ((Get-Prop $it 'State') -eq 'exited' -and [int](Get-Prop $it 'ExitCode' 0) -ne 0) { Show-ServiceFailure $svc "$svc 컨테이너가 실패했습니다." }
    }
    Write-Host '[조치] 흔한 원인: 인터넷 연결 없음(이미지·패키지 내려받기 실패), 디스크 부족, 8080 포트 충돌, Docker Desktop 메모리 부족.' -ForegroundColor Yellow
    exit 1
}

Write-Info '5/5 준비될 때까지 대기'
if (-not (Wait-ForStack -TimeoutSec $TimeoutSec)) { exit 1 }

$port = Invoke-Compose -ArgList @('port', 'web', '8080') -StdoutOnly
$bound = ($port.Output | Select-Object -First 1)
if ($bound -and -not ([string]$bound).Trim().StartsWith('127.0.0.1:')) {
    Write-Warn "웹 포트가 127.0.0.1 이 아닌 주소에 열려 있습니다: $bound  (.\web\scripts\status.ps1 로 점검하세요)"
}

Write-Host ''
Write-Host '=============================================' -ForegroundColor Green
Write-Host " 준비 완료!  브라우저에서 열기:  $YtwebUrl" -ForegroundColor Green
Write-Host '=============================================' -ForegroundColor Green
Write-Host '브라우저에서 로그인하세요(아이디·비밀번호는 web\.env 에 적은 값입니다. 웹에서 계정을 만들 수 없습니다).'
Write-Host '상태 확인  .\web\scripts\status.ps1'
Write-Host '로그 보기  .\web\scripts\logs.ps1'
Write-Host '종료       .\web\scripts\stop.ps1   (데이터는 보존됩니다)'
Write-Host ''
if ($OpenBrowser) { Start-Process $YtwebUrl }
exit 0
