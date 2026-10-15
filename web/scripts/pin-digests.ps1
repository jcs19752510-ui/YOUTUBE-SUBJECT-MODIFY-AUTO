<#
.SYNOPSIS
  Dockerfile 의 베이스 이미지 다이제스트(sha256)를 Docker Hub 에서 다시 조회해 비교/갱신합니다.
.DESCRIPTION
  web\docker\*.Dockerfile 의 `ARG ..._IMAGE=이름:태그@sha256:...` 줄을 읽어, 같은 태그의 현재 다이제스트를 조회합니다.
  기본은 비교만 합니다. -Apply 를 주면 파일을 새 다이제스트로 바꿉니다(그 뒤 start.ps1 로 다시 빌드).
  다이제스트 고정은 "같은 태그라도 내용이 몰래 바뀌는 것"을 막고, 갱신은 이 스크립트로 의도적으로 합니다.
.PARAMETER Apply
  비교 결과가 다르면 Dockerfile 을 수정합니다.
#>
param([switch]$Apply)
. (Join-Path $PSScriptRoot '_common.ps1')

function Get-RegistryDigest {
    param([string]$Repo, [string]$Tag)
    $scopeRepo = if ($Repo.Contains('/')) { $Repo } else { "library/$Repo" }
    $tokenUrl = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:${scopeRepo}:pull"
    $accept = 'application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json'
    for ($i = 1; $i -le 6; $i++) {
        try {
            $token = (Invoke-RestMethod -Uri $tokenUrl -UseBasicParsing -TimeoutSec 30).token
            $resp = Invoke-WebRequest -Method Head -UseBasicParsing -TimeoutSec 30 `
                -Uri "https://registry-1.docker.io/v2/$scopeRepo/manifests/$Tag" `
                -Headers @{ Authorization = "Bearer $token"; Accept = $accept }
            $d = $resp.Headers['Docker-Content-Digest']
            if ($d -is [array]) { $d = $d[0] }
            return [string]$d
        } catch {
            $status = 0
            try { $status = [int]$_.Exception.Response.StatusCode } catch { }
            if ($status -eq 429 -and $i -lt 6) { Start-Sleep -Seconds (5 * $i); continue }
            throw "다이제스트 조회 실패($Repo`:$Tag): $($_.Exception.Message)"
        }
    }
}

$dockerDir = Join-Path $YtwebWebDir 'docker'
$pattern = '(?m)^ARG\s+(?<name>\w+_IMAGE)=(?<repo>[^:@\s]+):(?<tag>[^@\s]+)@(?<digest>sha256:[0-9a-f]{64})\s*$'
$changed = 0; $failed = 0
foreach ($file in Get-ChildItem -LiteralPath $dockerDir -Filter '*.Dockerfile') {
    $text = [System.IO.File]::ReadAllText($file.FullName)
    $new = $text
    foreach ($m in [regex]::Matches($text, $pattern)) {
        $repo = $m.Groups['repo'].Value; $tag = $m.Groups['tag'].Value; $cur = $m.Groups['digest'].Value
        try { $latest = Get-RegistryDigest -Repo $repo -Tag $tag } catch { Write-Warn $_; $failed++; continue }
        if ($latest -eq $cur) { Write-Ok ("{0}: {1}:{2} 최신과 같음" -f $file.Name, $repo, $tag); continue }
        $changed++
        Write-Warn ("{0}: {1}:{2}`n    현재  {3}`n    최신  {4}" -f $file.Name, $repo, $tag, $cur, $latest)
        if ($Apply) { $new = $new.Replace($cur, $latest) }
    }
    if ($Apply -and $new -ne $text) {
        [System.IO.File]::WriteAllText($file.FullName, $new, (New-Object System.Text.UTF8Encoding($false)))
        Write-Ok "$($file.Name) 을 갱신했습니다."
    }
}
if ($failed -gt 0) { Write-Warn "$failed 건은 조회하지 못했습니다(인터넷·Docker Hub 접속을 확인하세요)." }
if ($changed -gt 0 -and -not $Apply) { Write-Info '갱신하려면 -Apply 를 붙여 다시 실행하세요. 갱신 후 .\web\scripts\start.ps1 로 다시 빌드하고 동작을 확인하세요.' }
if ($failed -gt 0) { exit 1 }
exit 0
