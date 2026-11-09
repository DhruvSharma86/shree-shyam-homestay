#Requires -Version 5.1
<#
.SYNOPSIS
  Create a PostgreSQL logical backup (pg_dump). Safe defaults: explicit target,
  password via PG* environment variables only (never printed, never on the
  command line), non-zero exit on failure.
.EXAMPLE
  $env:PGHOST="localhost"; $env:PGPORT="5432"; $env:PGUSER="hotel_app"; $env:PGPASSWORD="<from-secret-store>"; $env:PGDATABASE="shree_shyam"
  .\backup-postgres.ps1 -DbName "shree_shyam" -OutputDir "C:\backups\shree-shyam"
.NOTES
  Never pass the password as -DbName/output values. Rotate the file if it
  leaves the machine (it contains guest + financial data).
#>
param(
  [Parameter(Mandatory=$true)][string]$DbName,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [int]$RetentionDays = 30
)
$ErrorActionPreference = "Stop"

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
  Write-Error "pg_dump not found on PATH. Install PostgreSQL client tools."
  exit 1
}
if (-not $env:PGPASSWORD) {
  Write-Error "PGPASSWORD environment variable is not set. Supply it via the environment (never as an argument)."
  exit 1
}
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$outFile = Join-Path $OutputDir ("{0}_backup_{1}.dump" -f $DbName, $stamp)
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$writePort = "5432"
if ($env:PGPORT) { $writePort = $env:PGPORT }
$writeHost = "localhost"
if ($env:PGHOST) { $writeHost = $env:PGHOST }
Write-Host "Backing up database '$DbName' -> $outFile"
& pg_dump -h $writeHost -p $writePort -U $env:PGUSER -d $DbName -Fc -f $outFile
if ($LASTEXITCODE -ne 0) { Write-Error "pg_dump failed (exit $LASTEXITCODE). No backup was created."; exit $LASTEXITCODE }
if (-not (Test-Path $outFile) -or (Get-Item $outFile).Length -eq 0) {
  Write-Error "Backup file is missing or empty. Treat this as a failed backup."
  exit 1
}
Write-Host "Backup OK: $outFile ($([int]((Get-Item $outFile).Length/1024)) KB). Restrict ACLs to the operator account."
# Prune files older than retention.
Get-ChildItem -Path $OutputDir -Filter "$DbName`_backup_*.dump" |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } |
  Remove-Item -Force -Verbose
Write-Host "PASS: backup complete."
