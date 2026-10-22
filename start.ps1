# ============================================================================
# NexAgent Docker Bootstrap & Launch Script for PowerShell
# Ensures all prerequisite base images are pre-fetched sequentially
# to avoid concurrent TLS handshake timeouts on slow/unstable networks.
# ============================================================================

$ErrorActionPreference = "Continue"

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "   Starting NexAgent Stack Initialization" -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

$images = @(
    "postgres:16-alpine",
    "redis:7-alpine",
    "python:3.11-slim",
    "node:20-alpine",
    "nginx:alpine"
)

$index = 1
foreach ($image in $images) {
    Write-Host "[$index/$($images.Count)] Checking/Pulling $image..." -ForegroundColor Yellow
    docker pull $image
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[WARNING] Stalled or failed. Retrying $image..." -ForegroundColor Magenta
        Start-Sleep -Seconds 2
        docker pull $image
    }
    $index++
}

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host "   All base images ready. Launching Docker Compose..." -ForegroundColor Green
Write-Host "========================================================`n" -ForegroundColor Green

docker compose up --build $args
