# run.ps1 - start the API + dashboard together (auto-frees stale ports)
# Usage:  .\run.ps1
#   (if blocked by execution policy:  powershell -ExecutionPolicy Bypass -File .\run.ps1)
$root = $PSScriptRoot

# 1) Kill any process still holding ports 8000/3000 (prevents winerror 10048)
foreach ($port in 8000, 3000) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conns) {
        $conns.OwningProcess | Select-Object -Unique | ForEach-Object {
            Write-Host "port ${port}: killing stale PID $_" -ForegroundColor Yellow
            Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
        }
    }
}

# 2) Warn if .env missing (GEMINI_API_KEY is needed to run analysis)
if (-not (Test-Path "$root\.env")) {
    Write-Host "WARNING: .env not found (GEMINI_API_KEY needed for analysis)" -ForegroundColor Red
}

# 3) Start the API server in its own window
$apiCmd = "`$env:PYTHONIOENCODING='utf-8'; Set-Location '$root'; uvicorn src.api.main:app --port 8000"
Start-Process powershell -ArgumentList '-NoExit', '-Command', $apiCmd

# 4) Start the dashboard (Next.js dev) in another window
$webCmd = "Set-Location '$root\web'; npm run dev"
Start-Process powershell -ArgumentList '-NoExit', '-Command', $webCmd

# 5) Wait for the servers, then open the browser
Start-Sleep -Seconds 5
Start-Process "http://localhost:3000"

Write-Host ""
Write-Host "API docs  -> http://localhost:8000/docs" -ForegroundColor Green
Write-Host "Dashboard -> http://localhost:3000" -ForegroundColor Green
Write-Host "Run analysis (uses Gemini quota):  .\analyze.ps1" -ForegroundColor Cyan
