# Always run from the project root (folder where this script lives),
# regardless of the caller's current working directory.
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ProjectRoot

Write-Host "==> Setting up GenAI Platform at $ProjectRoot" -ForegroundColor Cyan

# --- Backend: venv + pip install ---
if (-not (Test-Path "$ProjectRoot\.venv")) {
    Write-Host "==> Creating Python venv (.venv)" -ForegroundColor Yellow
    python -m venv .venv
}

Write-Host "==> Activating venv" -ForegroundColor Yellow
& "$ProjectRoot\.venv\Scripts\Activate.ps1"

Write-Host "==> Upgrading pip" -ForegroundColor Yellow
python -m pip install --upgrade pip

Write-Host "==> Installing backend requirements" -ForegroundColor Yellow
pip install -r "$ProjectRoot\backend\requirements.txt"

# --- Frontend: npm install ---
Write-Host "==> Installing frontend dependencies (npm install)" -ForegroundColor Yellow
Push-Location "$ProjectRoot\frontend"
try {
    npm install
}
finally {
    Pop-Location
}

Write-Host "==> Setup complete." -ForegroundColor Green
