# Scawward -- one-shot launcher for the browser UI.
#
# Starts the FastAPI backend (port 8765) and the Vite dev server (port 5173)
# in two separate PowerShell windows, then opens http://localhost:5173 in
# your default browser. Close those windows to stop the servers.

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $root "nexus-os\venv\Scripts\python.exe"
$frontendDir = Join-Path $root "frontend"

if (-not (Test-Path $venvPython)) {
    Write-Host "[!] Python venv not found at $venvPython" -ForegroundColor Red
    Write-Host "    Activate the venv first or check the path." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $frontendDir "node_modules"))) {
    Write-Host "[!] frontend\node_modules missing." -ForegroundColor Red
    Write-Host "    Run 'cd frontend; npm install' first." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  S C A W W A R D  -  launching backend + frontend" -ForegroundColor Cyan
Write-Host "  -----------------------------------------------"
Write-Host "    backend  ->  http://127.0.0.1:8765/docs"
Write-Host "    frontend ->  http://localhost:5173"
Write-Host ""

# Use single quotes around interpolated paths so we never need backtick escaping.
$backendCommand  = "Set-Location '$root'; Write-Host '[backend] starting...' -ForegroundColor Yellow; & '$venvPython' -m backend.main"
$frontendCommand = "Set-Location '$frontendDir'; Write-Host '[frontend] starting...' -ForegroundColor Yellow; npm run dev"

function Wait-Url($url, $maxAttempts = 30, $intervalMs = 700) {
    for ($i = 0; $i -lt $maxAttempts; $i++) {
        Start-Sleep -Milliseconds $intervalMs
        try {
            $r = Invoke-WebRequest -Uri $url -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
            if ($r.StatusCode -eq 200) { return $true }
        } catch {
            # keep polling
        }
    }
    return $false
}

# 1. Backend first.
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand | Out-Null
Write-Host "  waiting for backend /api/health..." -ForegroundColor DarkGray
$backendReady = Wait-Url "http://127.0.0.1:8765/api/health"

if (-not $backendReady) {
    Write-Host "  [!] Backend did not answer in 20s. Check the backend window for errors." -ForegroundColor Red
    Write-Host "      Aborting frontend start." -ForegroundColor Red
    exit 1
}
Write-Host "  backend ready." -ForegroundColor Green

# 2. Frontend only after backend is alive, so Vite's proxy works cleanly.
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand | Out-Null
Write-Host "  waiting for Vite to come up..." -ForegroundColor DarkGray
$viteReady = Wait-Url "http://localhost:5173"

if ($viteReady) {
    Write-Host "  -> opening http://localhost:5173" -ForegroundColor Green
    Start-Process "http://localhost:5173"
} else {
    Write-Host "  Vite did not answer in 20s. Open http://localhost:5173 manually." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Two windows are now running. Close them to stop the servers." -ForegroundColor DarkGray
Write-Host ""
