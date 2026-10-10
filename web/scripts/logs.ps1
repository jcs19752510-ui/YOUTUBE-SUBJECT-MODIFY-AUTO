<#
.SYNOPSIS
  서비스 로그를 봅니다. 비밀번호는 로그에 기록되지 않습니다.
.PARAMETER Service
  web, api, worker, migrate, db 중 하나. 생략하면 전체.
.PARAMETER Tail
  마지막 몇 줄을 볼지(기본 200).
.PARAMETER Follow
  계속 따라가며 보기(Ctrl+C 로 중단).
#>
param(
    [ValidateSet('', 'web', 'api', 'worker', 'migrate', 'db')][string]$Service = '',
    [int]$Tail = 200,
    [switch]$Follow
)
. (Join-Path $PSScriptRoot '_common.ps1')

Test-ComposeFileExists
Test-DockerReady
$a = @('logs', '--no-color', '--tail', "$Tail")
if ($Follow) { $a += '--follow' }
if ($Service) { $a += $Service }
$r = Invoke-Compose -ArgList $a
exit $r.ExitCode
