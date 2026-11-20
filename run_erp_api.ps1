# Start Nexa Dynamics (web ERP + mobile /api/v1 on same port).
# Run: powershell -ExecutionPolicy Bypass -File .\run_erp_api.ps1
$ErrorActionPreference = "Stop"
$DynamicsRoot = "D:\webapps\Nova"
if (-not (Test-Path $DynamicsRoot)) {
    Write-Host "Dynamics project not found: $DynamicsRoot" -ForegroundColor Red
    exit 1
}
Set-Location $DynamicsRoot

Write-Host ""
Write-Host "Starting Nexa Dynamics (web + mobile API)..." -ForegroundColor Cyan
Write-Host "  Health:  http://127.0.0.1:5055/health" -ForegroundColor Gray
Write-Host "  Mobile:  http://127.0.0.1:5055/api/v1/..." -ForegroundColor Gray
Write-Host ""

python app.py
