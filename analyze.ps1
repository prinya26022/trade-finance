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
}
