# Always run from the project root (folder where this script lives),
# regardless of the caller's current working directory.
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $ProjectRoot

Write-Host "==> Starting GenAI Platform at $ProjectRoot" -ForegroundColor Cyan

if (-not (Test-Path "$ProjectRoot\.venv\Scripts\Activate.ps1")) {
    Write-Error "Python venv not found. Run .\setup.ps1 first."
    exit 1
}

if (-not (Test-Path "$ProjectRoot\frontend\node_modules")) {
    Write-Error "Frontend node_modules not found. Run .\setup.ps1 first."
    exit 1
}

# Backend in its own window
$backendCmd = "Set-Location '$ProjectRoot'; & '$ProjectRoot\.venv\Scripts\Activate.ps1'; uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
Start-Process pwsh -ArgumentList '-NoExit', '-Command', $backendCmd | Out-Null
Write-Host "==> Backend launched on http://localhost:8000" -ForegroundColor Green

# Frontend in its own window
$frontendCmd = "Set-Location '$ProjectRoot\frontend'; npm run dev"
Start-Process pwsh -ArgumentList '-NoExit', '-Command', $frontendCmd | Out-Null
Write-Host "==> Frontend launched on http://localhost:3000" -ForegroundColor Green

Write-Host "==> Both services starting in new windows." -ForegroundColor Cyan
