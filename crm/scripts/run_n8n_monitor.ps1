$ErrorActionPreference = "Stop"

$crmRoot = Split-Path -Parent $PSScriptRoot
$n8n = Join-Path $env:APPDATA "npm\n8n.cmd"
$stdout = Join-Path $crmRoot "work\n8n.stdout.log"
$stderr = Join-Path $crmRoot "work\n8n.stderr.log"

if (-not (Test-Path $n8n)) {
    throw "n8n was not found at $n8n"
}

New-Item -ItemType Directory -Force -Path (Join-Path $crmRoot "work") | Out-Null
Set-Location $crmRoot

$process = Start-Process `
    -FilePath $n8n `
    -ArgumentList "start" `
    -WorkingDirectory $crmRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -PassThru

$process.WaitForExit()
exit $process.ExitCode
