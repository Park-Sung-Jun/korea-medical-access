# Netlify API 로 dist.zip 직접 배포 (CLI 불필요).
# 사용: $env:NETLIFY_AUTH_TOKEN="<토큰>"; pwsh scripts/deploy_netlify.ps1 [-Name 사이트이름]
param([string]$Name = "")

$ErrorActionPreference = "Stop"
$token = $env:NETLIFY_AUTH_TOKEN
if (-not $token) { throw "NETLIFY_AUTH_TOKEN 환경변수가 필요합니다." }
$root = Split-Path $PSScriptRoot -Parent
$zip = Join-Path $root "dist.zip"
if (-not (Test-Path $zip)) { throw "dist.zip 없음 — 먼저 build_dist.py 실행." }
$headers = @{ Authorization = "Bearer $token" }

# 1) 사이트 생성
$body = @{}
if ($Name) { $body.name = $Name }
$site = Invoke-RestMethod -Method Post -Uri "https://api.netlify.com/api/v1/sites" `
  -Headers $headers -ContentType "application/json" -Body ($body | ConvertTo-Json)
Write-Host "site_id: $($site.id)  subdomain: $($site.name)"

# 2) zip 배포
$deploy = Invoke-RestMethod -Method Post `
  -Uri "https://api.netlify.com/api/v1/sites/$($site.id)/deploys" `
  -Headers $headers -ContentType "application/zip" -InFile $zip
Write-Host "deploy_id: $($deploy.id)  state: $($deploy.state)"

# 3) ready 까지 폴링
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Seconds 3
  $d = Invoke-RestMethod -Method Get `
    -Uri "https://api.netlify.com/api/v1/deploys/$($deploy.id)" -Headers $headers
  if ($d.state -in @("ready", "current")) {
    Write-Host "`n=== 배포 완료 ==="
    Write-Host "LIVE URL: $($d.ssl_url)"
    Write-Host "ADMIN   : $($site.admin_url)"
    exit 0
  }
  if ($d.state -eq "error") { throw "배포 실패: $($d.error_message)" }
  Write-Host "  state=$($d.state) ..."
}
throw "배포 상태 확인 시간 초과"
