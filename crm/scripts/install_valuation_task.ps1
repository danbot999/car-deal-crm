$ErrorActionPreference = "Stop"

$script = (Resolve-Path (Join-Path $PSScriptRoot "run_valuation_services.ps1")).Path
$taskName = "Car Deal CRM Valuation Service"
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Runs the local NZ vehicle market index API and durable valuation worker." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName
Write-Output "[VALUATION] Scheduled task installed and started: $taskName"
