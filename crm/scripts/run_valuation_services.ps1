$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
$work = Join-Path $root "crm\work"
New-Item -ItemType Directory -Path $work -Force | Out-Null

$mutex = [Threading.Mutex]::new($false, "Local\CarDealCRMValuationSupervisor")
if (-not $mutex.WaitOne(0)) {
    Write-Output "[VALUATION] Supervisor is already running."
    exit 0
}

function Start-ValuationProcess {
    param(
        [string]$Name,
        [string[]]$Arguments
    )
    $stdout = Join-Path $work "$Name.stdout.log"
    $stderr = Join-Path $work "$Name.stderr.log"
    return Start-Process `
        -FilePath $python `
        -ArgumentList $Arguments `
        -WorkingDirectory $root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -PassThru
}

$api = $null
$worker = $null
try {
    while ($true) {
        if ($null -eq $api -or $api.HasExited) {
            $api = Start-ValuationProcess -Name "valuation-api" -Arguments @("-m", "vehicle_valuation.run_api")
            Write-Output "[VALUATION] API started as PID $($api.Id)."
        }
        if ($null -eq $worker -or $worker.HasExited) {
            $worker = Start-ValuationProcess -Name "valuation-worker" -Arguments @("-m", "vehicle_valuation.worker")
            Write-Output "[VALUATION] Worker started as PID $($worker.Id)."
        }
        Start-Sleep -Seconds 10
    }
}
finally {
    foreach ($process in @($api, $worker)) {
        if ($null -ne $process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
