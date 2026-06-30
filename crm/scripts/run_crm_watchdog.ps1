$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$stdout = Join-Path $root "work\watchdog.stdout.log"
$stderr = Join-Path $root "work\watchdog.stderr.log"

New-Item -ItemType Directory -Path (Join-Path $root "work") -Force | Out-Null
Set-Location $root

& $python "scripts\crm_watchdog.py" 1>> $stdout 2>> $stderr
exit $LASTEXITCODE
