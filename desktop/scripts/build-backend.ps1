# Build the packaged FastAPI backend (PyInstaller onedir) and stage it for
# the desktop installer. Reuses backend\.venv (Python 3.11).
# Usage: powershell -File scripts/build-backend.ps1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$desktopDir = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $desktopDir
$backendDir = Join-Path $repoRoot 'backend'
$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'
$staging = Join-Path $desktopDir '.cache\staging\backend'

if (-not (Test-Path $venvPython)) {
  Write-Output 'build-backend: backend .venv not found — creating with uv …'
  Push-Location $backendDir
  uv sync
  Pop-Location
}

Write-Output 'build-backend: ensuring PyInstaller is available …'
uv pip install --python $venvPython pyinstaller | Out-Null

Push-Location $backendDir
try {
  Write-Output 'build-backend: running PyInstaller …'
  & $venvPython -m PyInstaller packaging\desktop_entry.spec --noconfirm `
    --distpath packaging\dist --workpath packaging\build
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
} finally {
  Pop-Location
}

if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $staging) | Out-Null
Copy-Item (Join-Path $backendDir 'packaging\dist\ShreeShyamBackend') $staging -Recurse -Force

$size = (Get-ChildItem $staging -Recurse | Measure-Object Length -Sum).Sum / 1MB
Write-Output "build-backend: staged $([math]::Round($size, 1)) MB -> $staging"
