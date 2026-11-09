#Requires -Version 5.1
<#
.SYNOPSIS
  Start ONE local Shree Shyam Home Stay service (never unintended multiples).
  Never prints secrets. Never migrates unless -Migrate is given.
.EXAMPLE
  .\ops\start-local.ps1 -Service backend
  .\ops\start-local.ps1 -Service backend -Migrate
  .\ops\start-local.ps1 -Service frontend
#>
param(
  [Parameter(Mandatory=$true)][ValidateSet("backend","frontend")][string]$Service,
  [switch]$Migrate,
  [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = "Stop"

function Test-PortFree([int]$Port) {
  $hit = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
  return -not $hit
}

if ($Service -eq "backend") {
  if ($Migrate -and -not (Test-Path "$RepoRoot\backend\.env" -PathType Leaf)) {
    Write-Error "backend/.env is missing. Create it from backend/.env.example first (LOCAL_SETUP.md §3)."
    exit 1
  }
  if (-not (Test-PortFree 8000)) { Write-Error "Port 8000 is already in use."; exit 1 }
  $envFile = "$RepoRoot\backend\.env"
  if (-not (Test-Path $envFile -PathType Leaf)) {
    Write-Host "backend/.env not found — starting WITHOUT a .env (code defaults apply; DATABASE_URL will be the dev default)."
    Write-Host "For the documented local setup, create backend/.env from backend/.env.example first."
  }
  # No -Migrate: never touches the schema.
  if ($Migrate) {
    Write-Host "Running migrations (explicit -Migrate)…"
    & "$RepoRoot\backend\.venv\Scripts\python.exe" -m alembic upgrade head
  }
  Write-Host "Backend starting on http://localhost:8000 (docs: http://localhost:8000/docs)"
  Write-Host "Press Ctrl+C to stop."
  & "$RepoRoot\backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
}
elseif ($Service -eq "frontend") {
  ".env.local|.env" | ForEach-Object { if (Test-Path "$RepoRoot\frontend\$_" -PathType Leaf) { $env:FOUND = $_ } }
  if (-not (Test-Path "$RepoRoot\frontend\.env.local" -PathType Leaf) -and -not (Test-Path "$RepoRoot\frontend\.env" -PathType Leaf)) {
    Write-Host "frontend/.env.local not found — Next will use code defaults (localhost API). Create it from frontend/.env.example first."
  }
  if (-not (Test-PortFree 3000)) { Write-Error "Port 3000 is already in use."; exit 1 }
  Write-Host "Frontend starting on http://localhost:3000"
  Write-Host "Press Ctrl+C to stop."
  Set-Location "$RepoRoot\frontend"
  & npm run dev
}
