# Download and stage the official Node.js Windows x64 runtime used to serve
# the packaged Next.js standalone server. Only node.exe + LICENSE are staged.
# Usage: powershell -File scripts/fetch-node-runtime.ps1
[CmdletBinding()]
param(
  [string]$Version = 'v26.13.1'
)

$ErrorActionPreference = 'Stop'
$desktopDir = Split-Path -Parent $PSScriptRoot
$cache = Join-Path $desktopDir '.cache'
$staging = Join-Path $cache 'staging\node'
$zipPath = Join-Path $cache "node-$Version-win-x64.zip"
$extractDir = Join-Path $cache "node-$Version-extract"
$url = "https://nodejs.org/dist/$Version/node-$Version-win-x64.zip"

if (Test-Path (Join-Path $staging 'node.exe')) {
  Write-Output "fetch-node: staging already contains node.exe ($Version)"
  exit 0
}

New-Item -ItemType Directory -Force -Path $cache | Out-Null
if (-not (Test-Path $zipPath)) {
  Write-Output "fetch-node: downloading $url"
  Invoke-WebRequest -Uri $url -OutFile $zipPath -TimeoutSec 600 -UseBasicParsing
}

if (Test-Path $extractDir) { Remove-Item $extractDir -Recurse -Force }
Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

$inner = Join-Path $extractDir "node-$Version-win-x64"
New-Item -ItemType Directory -Force -Path $staging | Out-Null
Copy-Item (Join-Path $inner 'node.exe') (Join-Path $staging 'node.exe') -Force
Copy-Item (Join-Path $inner 'LICENSE') (Join-Path $staging 'LICENSE') -Force
Remove-Item $extractDir -Recurse -Force
Write-Output "fetch-node: staged $((Get-Item (Join-Path $staging 'node.exe')).Length / 1MB) MB -> $staging"
