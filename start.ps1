$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (!(Test-Path -LiteralPath '.env') -or !(Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'Create .env from .env.example and run uv sync --frozen first.'
}

try { docker info --format '{{.ServerVersion}}' 2>$null | Out-Null } catch { }
if ($LASTEXITCODE -ne 0) {
    $travelDockerApp = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (!(Test-Path -LiteralPath $travelDockerApp)) { throw 'Start Docker Desktop first.' }
    Start-Process -FilePath $travelDockerApp -WindowStyle Hidden
    for ($travelDockerAttempt = 0; $travelDockerAttempt -lt 60; $travelDockerAttempt++) {
        Start-Sleep -Seconds 2
        try { docker info --format '{{.ServerVersion}}' 2>$null | Out-Null } catch { }
        if ($LASTEXITCODE -eq 0) { break }
    }
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop did not become ready within two minutes.' }
}
docker compose up -d --wait --wait-timeout 180
if ($LASTEXITCODE -ne 0) { throw 'Database startup failed. Check docker compose ps and docker compose logs.' }

$travelUrl = 'http://127.0.0.1:8001'
try { $travelHealth = Invoke-RestMethod "$travelUrl/health" -TimeoutSec 2 } catch { $travelHealth = $null }
if ($travelHealth -and $travelHealth.service -ne 'travel-query') {
    throw 'Port 8001 is occupied by another service. Stop it or choose another port manually.'
}
if (!$travelHealth) {
    $env:PYTHONUTF8 = '1'
    $travelLogs = Join-Path $PSScriptRoot 'data\runtime'
    New-Item -ItemType Directory -Path $travelLogs -Force | Out-Null
    $travelProcess = Start-Process -FilePath "$PSScriptRoot\.venv\Scripts\python.exe" `
        -ArgumentList @('-m', 'uvicorn', 'web.api.query_service:app', '--host', '127.0.0.1', '--port', '8001') `
        -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$travelLogs\server.stdout.log" `
        -RedirectStandardError "$travelLogs\server.stderr.log"
    $travelProcess.Id | Set-Content "$travelLogs\launcher.pid"
    for ($travelAttempt = 0; $travelAttempt -lt 90; $travelAttempt++) {
        try {
            $travelHealth = Invoke-RestMethod "$travelUrl/health" -TimeoutSec 2
            if ($travelHealth.service -eq 'travel-query') { break }
        } catch { }
        if ($travelProcess.HasExited) { throw "Server exited. Read $travelLogs\server.stderr.log" }
        Start-Sleep -Seconds 1
    }
    if ($travelHealth.service -ne 'travel-query') { throw "Server startup timed out. Read $travelLogs\server.stderr.log" }
}

Write-Host "Travel chat and import are ready: $travelUrl/chat.html"
Start-Process -FilePath "$travelUrl/chat.html"
