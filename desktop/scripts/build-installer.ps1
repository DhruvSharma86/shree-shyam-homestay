# End-to-end installer build.
# Usage: powershell -File scripts/build-installer.ps1 [-SkipFrontendBuild] [-SkipBackendBuild]
[CmdletBinding()]
param(
  [switch]$SkipFrontendBuild,
  [switch]$SkipBackendBuild
)

$ErrorActionPreference = 'Stop'
$desktopDir = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $desktopDir

function Step($name) { Write-Output "`n=== $name ===" }

Step 'Desktop npm dependencies'
if (-not (Test-Path (Join-Path $desktopDir 'node_modules'))) {
  Push-Location $desktopDir
  npm install --no-audit --no-fund
  Pop-Location
}

if (-not $SkipFrontendBuild) {
  Step 'Frontend production build (Next.js standalone)'
  Push-Location (Join-Path $repoRoot 'frontend')
  npm run build
  Pop-Location
} else {
  Write-Output 'Skipping frontend build (-SkipFrontendBuild).'
}

if (-not $SkipBackendBuild) {
  Step 'Backend packaging (PyInstaller)'
  & (Join-Path $PSScriptRoot 'build-backend.ps1')
} else {
  Write-Output 'Skipping backend build (-SkipBackendBuild).'
}

Step 'Staging Next.js standalone server'
node (Join-Path $PSScriptRoot 'prepare-frontend.mjs')

Step 'Staging Node.js runtime'
& (Join-Path $PSScriptRoot 'fetch-node-runtime.ps1')

Step 'Building Windows installer (electron-builder / NSIS)'
Push-Location $desktopDir
try {
  npx electron-builder --win nsis
  if ($LASTEXITCODE -ne 0) { throw "electron-builder failed with exit code $LASTEXITCODE" }
} finally {
  Pop-Location
}

$installer = Join-Path $desktopDir 'dist\Shree-Shyam-Home-Stay-Setup.exe'
if (Test-Path $installer) {
  $sizeMb = [math]::Round((Get-Item $installer).Length / 1MB, 1)
  Write-Output "`nInstaller ready: $installer ($sizeMb MB)"
} else {
  throw 'electron-builder finished but the installer was not found.'
}
