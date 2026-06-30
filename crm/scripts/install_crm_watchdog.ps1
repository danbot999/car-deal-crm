$ErrorActionPreference = "Stop"

$script = (Resolve-Path (Join-Path $PSScriptRoot "run_crm_watchdog.ps1")).Path
$taskName = "Car Deal CRM Self-Healing Watchdog"
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$recurring = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($logon, $recurring) `
    -Settings $settings `
    -Description "Checks and safely repairs the localhost CRM, n8n, Marketplace collector, sync, and valuation services every five minutes." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $taskName
Write-Output "[WATCHDOG] Scheduled task installed and started: $taskName"
