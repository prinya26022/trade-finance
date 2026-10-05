# schedule-journal.ps1 - run the trade journal automatically on this PC (run once)
#   - every hour : pull positions from OKX (read only) + Discord ping for trades just opened/closed
#   - Sunday 20:00: weekly stats to Discord
#   - every hour : wave alert - Discord ping when a CLOSED 4H bar crosses a scenario's kill/confirm line,
#                  and refresh the snapshot the /wave and /check pages read (every coin in data/waves/*.json)
#   (the daily 4H wave picture runs on GitHub Actions instead - .github/workflows/wave-daily.yml -
#    it only needs yfinance prices, so it works with the PC off)
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
$wave = "TradeFinanceWaveAlert"
$waveDaily = "TradeFinanceWaveDaily"   # old: now on GitHub Actions, only removed here

if ($Remove) {
    foreach ($t in $sync, $weekly, $wave, $waveDaily) { Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue }
    Write-Host "Removed journal + wave tasks" -ForegroundColor Yellow
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

function New-PyAction([string]$module, [string]$cmd) {
    $arg = '-ExecutionPolicy Bypass -NoProfile -Command "Set-Location ''{0}''; $env:PYTHONIOENCODING=''utf-8''; python -m {1} {2} *>&1 | Out-File -FilePath ''{3}'' -Append -Encoding utf8"' -f $root, $module, $cmd, $log
    New-ScheduledTaskAction -Execute $psExe -Argument $arg
}

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
# 4H bars close at 00/04/08/12/16/20 UTC; run a few minutes past each hour so the bar has closed
$hourlyWave = New-ScheduledTaskTrigger -Once -At ((Get-Date).Date.AddHours((Get-Date).Hour + 1).AddMinutes(5)) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
$sunday = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "20:00"
# every count file in data/waves (btc.json, eth.json, ...). The list is read when THIS script runs,
# so after adding a coin file, run the script again
$waveFiles = (Get-ChildItem (Join-Path $root "data\waves") -Filter *.json | ForEach-Object { "data/waves/" + $_.Name }) -join " "

foreach ($t in $sync, $weekly, $wave, $waveDaily) { Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue }
Register-ScheduledTask -TaskName $sync -Action (New-PyAction "src.journal" "sync") -Trigger $hourly -Settings $settings `
    -Description "Pull BTC-USDT-SWAP positions from OKX (read only) into the trade journal" | Out-Null
Register-ScheduledTask -TaskName $weekly -Action (New-PyAction "src.journal" "stats --send") -Trigger $sunday -Settings $settings `
    -Description "Weekly trade journal stats to Discord" | Out-Null
Register-ScheduledTask -TaskName $wave -Action (New-PyAction "src.wave" "alert $waveFiles") -Trigger $hourlyWave `
    -Settings $settings -Description "Wave alert: closed 4H bar crossing a scenario line + refresh /wave snapshot" | Out-Null

Write-Host "Registered: OKX sync hourly + weekly stats Sunday 20:00 + wave alert hourly (:05)" -ForegroundColor Green
Write-Host "Wave files: $waveFiles"
Write-Host "Log     : $log"
Write-Host "Run now : Start-ScheduledTask -TaskName $sync"
Write-Host "Remove  : .\schedule-journal.ps1 -Remove"
