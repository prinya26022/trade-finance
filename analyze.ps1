# analyze.ps1 - run the agent (calls Gemini -> uses free-tier quota, 20/day)
# Usage:  .\analyze.ps1           analyze every ticker in the watchlist (incl. pending)
#         .\analyze.ps1 NVDA      analyze a single ticker
param([string]$Ticker)

$env:PYTHONIOENCODING = "utf-8"
Set-Location $PSScriptRoot

if ($Ticker) {
    python -c "from src.agent.loop import analyze; analyze('$Ticker')"
} else {
    python -c "from src.agent.loop import run_watchlist; run_watchlist()"
    # ส่ง report เข้า Discord — auto เลือกโหมดจากวันที่ (วันที่ 1=monthly, จันทร์=weekly, อื่นๆ=daily)
    # ข้ามเงียบๆ ถ้าไม่ตั้ง DISCORD_WEBHOOK_URL
    python -c "from src.agent.report import send_report; send_report()"
    # ส่ง quality alert (Phase 4 — ความแม่นการคำนวณของเราเอง) เข้าช่องแยก คนละหัวข้อกับข้างบน
    # เงียบถ้าทุกตัวปกติ หรือถ้าไม่ตั้ง DISCORD_WEBHOOK_URL_QUALITY
    python -c "from src.agent.report import send_quality_report; send_quality_report()"
}
