# schedule.ps1 - register a daily Windows scheduled task that runs analyze.ps1
# Usage:  .\schedule.ps1              (default 08:00)
#         .\schedule.ps1 -Time 07:30
#         .\schedule.ps1 -Remove      (delete the task)
param(
    [string]$Time = "08:00",
    [switch]$Remove
)

$root = $PSScriptRoot
$taskName = "TradeFinanceDailyAnalysis"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed task '$taskName'" -ForegroundColor Yellow
    return
}

# log dir (gitignored)
$logDir = Join-Path $root "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir "daily-analysis.log"

# action: run analyze.ps1, merge all streams (*>&1) and append as UTF-8
# (plain *>> writes UTF-16 in Windows PowerShell 5.1 -> pipe through Out-File utf8 instead)
$psExe = (Get-Command powershell).Source
$argument = '-ExecutionPolicy Bypass -NoProfile -Command "& ''{0}\analyze.ps1'' *>&1 | Out-File -FilePath ''{1}'' -Append -Encoding utf8"' -f $root, $log
$action = New-ScheduledTaskAction -Execute $psExe -Argument $argument

# daily trigger; StartWhenAvailable = run late if the PC was off at $Time
$trigger = New-ScheduledTaskTrigger -Daily -At $Time
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

# idempotent: replace any existing task with the same name
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Daily fundamental analysis of the watchlist (trade-finance agent)" | Out-Null

Write-Host "Registered '$taskName' - runs analyze.ps1 daily at $Time" -ForegroundColor Green
Write-Host "Log file : $log"
Write-Host "Run now  : Start-ScheduledTask -TaskName $taskName"
Write-Host "Status   : Get-ScheduledTask -TaskName $taskName"
Write-Host "Remove   : .\schedule.ps1 -Remove"
