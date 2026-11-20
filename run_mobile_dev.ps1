# Start Dynamics API in a new window, wait for /health, then run Flutter.
# From repo root:  powershell -ExecutionPolicy Bypass -File .\run_mobile_dev.ps1
# Extra args pass to flutter (e.g. -d chrome, --dart-define=API_HOST=192.168.1.5)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$DynamicsRoot = "D:\webapps\Nova"
$port = 5055

if (-not (Test-Path $DynamicsRoot)) {
    Write-Host "Dynamics project not found: $DynamicsRoot" -ForegroundColor Red
    exit 1
}

$envPath = Join-Path $DynamicsRoot ".env"
if (Test-Path $envPath) {
    $m = Select-String -Path $envPath -Pattern '^\s*FLASK_PORT\s*=\s*(\d+)' | Select-Object -First 1
    if ($m) { $port = [int]$m.Matches.Groups[1].Value }
}

Write-Host ""
Write-Host "Starting Nexa Dynamics in a separate window (port $port)..." -ForegroundColor Cyan
Write-Host ""

$apiCmd = "Set-Location '$DynamicsRoot'; python app.py"
Start-Process powershell -ArgumentList @("-NoExit", "-Command", $apiCmd) | Out-Null

$health = "http://127.0.0.1:$port/health"
$deadline = (Get-Date).AddSeconds(60)
$ok = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri $health -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ok = $true; break }
    } catch {
        Start-Sleep -Milliseconds 400
    }
}

if (-not $ok) {
    Write-Host "API not reachable at $health yet. Check the Dynamics window (Oracle, JWT, port)." -ForegroundColor Yellow
} else {
    Write-Host "API is up ($health)." -ForegroundColor Green
}

$flutterDir = Join-Path $Root "flutter_app"
if (-not (Test-Path $flutterDir)) {
    Write-Host "Missing folder: $flutterDir" -ForegroundColor Red
    exit 1
}

Set-Location $flutterDir
Write-Host ""
Write-Host "Running flutter (API_BASE_URL=http://127.0.0.1:$port)..." -ForegroundColor Cyan
& flutter run --dart-define=API_BASE_URL=http://127.0.0.1:$port @args
