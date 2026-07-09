# analyze.ps1 - run the agent (calls Gemini -> uses free-tier quota, 20/day)
# Usage:  .\analyze.ps1           analyze every ticker in the watchlist (incl. pending)
#         .\analyze.ps1 NVDA      analyze a single ticker
param([string]$Ticker)

$env:PYTHONIOENCODING = "utf-8"
Set-Location $PSScriptRoot

if ($Ticker) {
    # ต้องอ่าน asset_type จาก watchlist ก่อน (ไม่ใช่ default 'stock' เฉยๆ) ไม่งั้น
    # crypto ticker (เช่น BTC) จะหลุดไปใช้ StockPriceProvider ผิด provider
    python -c "from src.watchlist.store import get_entry; from src.agent.loop import analyze; row = get_entry('$Ticker'); analyze('$Ticker', asset_type=(row['asset_type'] if row else 'stock'))"
} else {
    python -c "from src.agent.loop import run_watchlist; run_watchlist()"
    # ส่ง report เข้า Discord — auto เลือกโหมดจากวันที่ (วันที่ 1=monthly, จันทร์=weekly, อื่นๆ=daily)
    # ข้ามเงียบๆ ถ้าไม่ตั้ง DISCORD_WEBHOOK_URL
    python -c "from src.agent.report import send_report; send_report()"
    # ส่ง quality alert (Phase 4 — ความแม่นการคำนวณของเราเอง) เข้าช่องแยก คนละหัวข้อกับข้างบน
    # เงียบถ้าทุกตัวปกติ หรือถ้าไม่ตั้ง DISCORD_WEBHOOK_URL_QUALITY
    python -c "from src.agent.report import send_quality_report; send_quality_report()"
    # ส่ง portfolio alert (Phase 5.5 — เงื่อนไขออกโดนแตะเฉพาะโพซิชันที่ถืออยู่จริง) เข้าช่องแยก
    # เงียบถ้าไม่มี breach หรือถ้าไม่ตั้ง DISCORD_WEBHOOK_URL_PORTFOLIO
    python -c "from src.agent.report import send_portfolio_alert; send_portfolio_alert()"
}
