#Requires -Version 5.1
<#
.SYNOPSIS
  Restore a PostgreSQL logical backup into an EXPLICITLY named target.
  Refuses production-named targets without -AllowProduction. Password via
  PG* env only (never printed). No destructive default.
.EXAMPLE
  $env:PGHOST="localhost"; $env:PGUSER="hotel_app"; $env:PGPASSWORD="<from-secret-store>"
  .\restore-postgres.ps1 -BackupFile "C:\backups\shree-shyam\shree_shyam_backup_20261109_210000.dump" -TargetDb "shree_shyam_restore_test"
#>
param(
  [Parameter(Mandatory=$true)][string]$BackupFile,
  [Parameter(Mandatory=$true)][string]$TargetDb,
  [switch]$AllowProduction,
  [string]$ProductionDbName = "shree_shyam"
)
$ErrorActionPreference = "Stop"

if (-not (Get-Command pg_restore -ErrorAction SilentlyContinue)) { Write-Error "pg_restore not found on PATH."; exit 1 }
if (-not (Test-Path $BackupFile)) { Write-Error "Backup file is missing."; exit 1 }
if ((Get-Item $BackupFile).Length -eq 0) { Write-Error "Backup file is empty."; exit 1 }
if (-not $env:PGPASSWORD) { Write-Error "PGPASSWORD is not set (supply via environment, never as an argument)."; exit 1 }
if ($TargetDb -eq $ProductionDbName -and -not $AllowProduction) {
  Write-Error "Refusing to restore into production-named database without -AllowProduction."
  exit 1
}
$hostName = "localhost"
if ($env:PGHOST) { $hostName = $env:PGHOST }
$port = "5432"
if ($env:PGPORT) { $port = $env:PGPORT }
Write-Host "Restoring backup into database target (host $hostName)."
$terminateSql = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='" + $TargetDb + "' AND pid <> pg_backend_pid();"
& psql -h $hostName -p $port -U $env:PGUSER -d postgres -c $terminateSql
if ($LASTEXITCODE -ne 0) { Write-Error "Terminate failed."; exit $LASTEXITCODE }
$dropSql = 'DROP DATABASE IF EXISTS "' + $TargetDb + '";'
& psql -h $hostName -p $port -U $env:PGUSER -d postgres -c $dropSql
if ($LASTEXITCODE -ne 0) { Write-Error "Drop failed."; exit $LASTEXITCODE }
$createSql = 'CREATE DATABASE "' + $TargetDb + '";'
& psql -h $hostName -p $port -U $env:PGUSER -d postgres -c $createSql
if ($LASTEXITCODE -ne 0) { Write-Error "Create failed."; exit $LASTEXITCODE }
& pg_restore -h $hostName -p $port -U $env:PGUSER -d $TargetDb $BackupFile
if ($LASTEXITCODE -ne 0) { Write-Error "pg_restore failed."; exit $LASTEXITCODE }
Write-Host "Restore complete. Verify row counts before trusting it."
Write-Host "PASS: restore complete."
