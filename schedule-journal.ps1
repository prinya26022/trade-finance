# schedule-journal.ps1 - ให้สมุดเทรดทำงานเองบนคอมนี้ (รันครั้งเดียวพอ)
#   - ทุกชั่วโมง: ดึงไม้จาก OKX + แจ้ง Discord ไม้ที่เพิ่งเปิด/ปิด
#   - ทุกวันอาทิตย์ 20:00: ส่งสรุปสถิติเข้า Discord
# Usage:  .\schedule-journal.ps1            (ตั้ง)
#         .\schedule-journal.ps1 -Remove    (ลบ)
#
# ทำไมรันบนคอมนี้ ไม่ใช่ GitHub Actions: OKX จำกัดการเข้าถึงจาก IP สหรัฐ ซึ่งเป็นที่ตั้งของ runner
# ปิดคอมไว้ไม่เป็นไร — OKX เก็บประวัติ 3 เดือน เปิดคอมเมื่อไหร่ก็ดึงย้อนมาครบ (StartWhenAvailable)
param([switch]$Remove)

$root = $PSScriptRoot
$sync = "TradeFinanceJournalSync"
$weekly = "TradeFinanceJournalWeekly"

if ($Remove) {
    foreach ($t in $sync, $weekly) { Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue }
    Write-Host "Removed journal tasks" -ForegroundColor Yellow
    return
}

if (-not (Select-String -Path "$root\.env" -Pattern '^OKX_API_KEY=.+' -Quiet -ErrorAction SilentlyContinue)) {
    Write-Host "ยังไม่มี OKX_API_KEY ใน .env — ใส่ key แบบ Read only ก่อน (ดู .env.example)" -ForegroundColor Red
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

Write-Host "ตั้งแล้ว: ดึงไม้จาก OKX ทุกชั่วโมง + สรุปทุกวันอาทิตย์ 20:00" -ForegroundColor Green
Write-Host "log      : $log"
Write-Host "รันตอนนี้ : Start-ScheduledTask -TaskName $sync"
Write-Host "ลบ       : .\schedule-journal.ps1 -Remove"
