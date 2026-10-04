# schedule-journal.ps1 - run the trade journal automatically on this PC (run once)
#   - every hour : pull positions from OKX (read only) + Discord ping for trades just opened/closed
#   - Sunday 20:00: weekly stats to Discord
# Usage:  .\schedule-journal.ps1            (register)
#         .\schedule-journal.ps1 -Remove    (delete)
#
# ASCII only on purpose: Windows PowerShell 5.1 reads a .ps1 without BOM as the ANSI code page,
# so Thai text here turned into mojibake and broke the quoting (same reason schedule.ps1 is English).
#
# Why this PC and not GitHub Actions: OKX restricts US IPs, which is where the runners are.
# PC off for a while is fine - OKX keeps 3 months of history and StartWhenAvailable catches up.
param([switch]$Remove)

$root = $PSScriptRoot
$sync = "TradeFinanceJournalSync"
$weekly = "TradeFinanceJournalWeekly"

if ($Remove) {
    foreach ($t in $sync, $weekly) { Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue }
    Write-Host "Removed journal tasks" -ForegroundColor Yellow
    return
}

$envFile = Join-Path $root ".env"
if (-not (Select-String -Path $envFile -Pattern '^OKX_API_KEY=.+' -Quiet -ErrorAction SilentlyContinue)) {
    Write-Host "OKX_API_KEY not found in .env - add a READ ONLY key first (see .env.example)" -ForegroundColor Red
    return
}

$logDir = Join-Path $root "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log = Join-Path $logDir "journal.log"
$psExe = (Get-Command powershell).Source

function New-JournalAction([string]$cmd) {
    $arg = '-ExecutionPolicy Bypass -NoProfile -Command "Set-Location ''{0}''; $env:PYTHONIOENCODING=''utf-8''; python -m src.journal {1} *>&1 | Out-File -FilePath ''{2}'' -Append -Encoding utf8"' -f $root, $cmd, $log
    New-ScheduledTaskAction -Execute $psExe -Argument $arg
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$sunday = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "20:00"

foreach ($t in $sync, $weekly) { Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue }
Register-ScheduledTask -TaskName $sync -Action (New-JournalAction "sync") -Trigger $hourly -Settings $settings `
    -Description "Pull BTC-USDT-SWAP positions from OKX (read only) into the trade journal" | Out-Null
Register-ScheduledTask -TaskName $weekly -Action (New-JournalAction "stats --send") -Trigger $sunday -Settings $settings `
    -Description "Weekly trade journal stats to Discord" | Out-Null

Write-Host "Registered: OKX sync every hour + weekly stats Sunday 20:00" -ForegroundColor Green
Write-Host "Log     : $log"
Write-Host "Run now : Start-ScheduledTask -TaskName $sync"
Write-Host "Remove  : .\schedule-journal.ps1 -Remove"
