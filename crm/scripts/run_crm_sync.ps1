$ErrorActionPreference = "Stop"

$crmRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $crmRoot
$python = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
$stdout = Join-Path $crmRoot "work\cloud-sync-worker.stdout.log"
$stderr = Join-Path $crmRoot "work\cloud-sync-worker.stderr.log"

New-Item -ItemType Directory -Force -Path (Join-Path $crmRoot "work") | Out-Null
Set-Location $crmRoot

& $python "scripts\sync_n8n_to_crm.py" `
    --interval-seconds 60 `
    --availability-interval-seconds 600 `
    --availability-limit 30 `
    --availability-stale-hours 6 `
    --cloud-sync-interval-seconds 600 `
    1>> $stdout `
    2>> $stderr

exit $LASTEXITCODE
