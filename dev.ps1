# dev.ps1 - kill port 8000, then start uvicorn (API) and npm run dev (web) each in their own window
# Usage:  .\dev.ps1
$root = $PSScriptRoot

Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root'; uvicorn src.api.main:app --port 8000"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "Set-Location '$root\web'; npm run dev"