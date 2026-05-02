# setup_notebooklm.ps1
# One-time local setup for NotebookLM audio generation.
# Run from the repo root with your Python venv active:
#
#   .venv\Scripts\Activate.ps1
#   .\scripts\setup_notebooklm.ps1
#
# What this does:
#   1. Installs notebooklm-py and playwright Python packages
#   2. Downloads the Chromium browser Playwright needs
#   3. Opens a real browser so you can sign into Google / NotebookLM
#   4. Saves the captured session and shows the GitHub secret value to copy

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== NotebookLM Setup ===" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Install Python packages ──────────────────────────────────────────
Write-Host "Step 1/3  Installing notebooklm-py and playwright..." -ForegroundColor Yellow
pip install --quiet "notebooklm-py>=0.3.0" "playwright>=1.44.0"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: pip install failed. Make sure your venv is active." -ForegroundColor Red
    exit 1
}
Write-Host "         Done." -ForegroundColor Green

# ── Step 2: Install Chromium browser ─────────────────────────────────────────
Write-Host ""
Write-Host "Step 2/3  Downloading Playwright Chromium browser..." -ForegroundColor Yellow
playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: playwright install failed." -ForegroundColor Red
    exit 1
}
Write-Host "         Done." -ForegroundColor Green

# ── Step 3: Capture Google auth session ──────────────────────────────────────
Write-Host ""
Write-Host "Step 3/3  Capturing Google auth session." -ForegroundColor Yellow
Write-Host "         A browser window will open. Sign into the Google account"
Write-Host "         you want to use for NotebookLM, then close the browser or"
Write-Host "         press Enter here when prompted."
Write-Host ""

notebooklm login
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: notebooklm login failed." -ForegroundColor Red
    exit 1
}

# ── Locate the saved auth file ────────────────────────────────────────────────
$authFile = "$env:USERPROFILE\.notebooklm\storage_state.json"
if (-not (Test-Path $authFile)) {
    Write-Host ""
    Write-Host "ERROR: Auth file not found at:" -ForegroundColor Red
    Write-Host "  $authFile"
    Write-Host "Login may not have completed. Re-run this script and try again."
    exit 1
}

# ── Set env var for this session ──────────────────────────────────────────────
$authJson = Get-Content $authFile -Raw
$env:NOTEBOOKLM_AUTH_JSON = $authJson

Write-Host ""
Write-Host "=== Setup complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "NOTEBOOKLM_AUTH_JSON has been set for this PowerShell session."
Write-Host "You can now run:" -ForegroundColor Cyan
Write-Host "  python scripts/generator.py --id PGR_2025_Q4"
Write-Host ""
Write-Host "--- GitHub Secret (for CI) ---" -ForegroundColor Yellow
Write-Host "To enable NotebookLM in GitHub Actions, add this as a repository secret:"
Write-Host "  Name:  NOTEBOOKLM_AUTH_JSON"
Write-Host "  Value: (the contents of $authFile)"
Write-Host ""
Write-Host "Quick copy to clipboard (run in PowerShell):"
Write-Host "  Get-Content '$authFile' -Raw | Set-Clipboard"
Write-Host ""
Write-Host "NOTE: Google session cookies expire every few weeks." -ForegroundColor DarkYellow
Write-Host "When generator.py fails with an auth error, re-run this script."
