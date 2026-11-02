# Wcoflix Downloader - Local Proxy & ngrok Manager
# Run this on your Windows laptop to expose your residential IP to Coolify
#
# Usage (PowerShell, Administrator recommended):
#   .\start-proxy.ps1          # Start proxy + ngrok
#   .\start-proxy.ps1 -Stop    # Stop everything
#
# Prerequisites:
#   1. Python installed (https://python.org)
#   2. ngrok installed and configured (https://ngrok.com)
#      - Run: ngrok config add-authtoken <your-token>
#   3. Proxy credentials set below (change them!)

$ErrorActionPreference = "Stop"

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
$PROXY_PORT       = 8080
$PROXY_USER       = "wcoflix_user"      # <-- change this
$PROXY_PASS       = "wcoflix_pass_2026" # <-- change this
$PYTHON_CMD       = "python"            # or "py" if python isn't in PATH
$PROXY_SCRIPT     = Join-Path $PSScriptRoot "proxy.py"
$NGROK_CMD        = "ngrok"
# ───────────────────────────────────────────────────────────────────────────

function Get-ProcessByPort {
    param($Port)
    try {
        $proc = Get-Process -Id (Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue).OwningProcess -ErrorAction SilentlyContinue
        return $proc
    } catch {
        return $null
    }
}

function Write-Status {
    param($Message, $Level = "INFO")
    $timestamp = Get-Date -Format "HH:mm:ss"
    switch ($Level) {
        "INFO"  { Write-Host "[$timestamp] $Message" -ForegroundColor Cyan }
        "OK"    { Write-Host "[$timestamp] $Message" -ForegroundColor Green }
        "WARN"  { Write-Host "[$timestamp] $Message" -ForegroundColor Yellow }
        "ERROR" { Write-Host "[$timestamp] $Message" -ForegroundColor Red }
    }
}

function Start-Proxy {
    Write-Status "Starting local HTTP proxy on port $PROXY_PORT..."

    # Check if already running
    $existing = Get-ProcessByPort -Port $PROXY_PORT
    if ($existing) {
        Write-Status "Proxy already running on port $PROXY_PORT (PID $($existing.Id))." -WARN
        return $existing.Id
    }

    # Start proxy in a hidden window
    $proxyArgs = @(
        "-WindowStyle", "Hidden",
        "-Command", "& { $env:PROXY_PORT='$PROXY_PORT'; $env:PROXY_USER='$PROXY_USER'; $env:PROXY_PASS='$PROXY_PASS'; & '$PROXY_SCRIPT' }"
    )

    $proxyProcess = Start-Process powershell.exe @proxyArgs -PassThru
    Write-Status "Proxy process started (PID $($proxyProcess.Id))." -OK

    # Wait for proxy to be ready
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 500
        $test = Get-ProcessByPort -Port $PROXY_PORT
        if ($test) { break }
    }

    return $proxyProcess.Id
}

function Start-Ngrok {
    Write-Status "Starting ngrok tunnel on port $PROXY_PORT..."

    # Check if ngrok is available
    try {
        $ngrokVersion = & $NGROK_CMD version 2>$null
        if (-not $ngrokVersion) {
            Write-Status "ngrok not found. Install from https://ngrok.com and run 'ngrok config add-authtoken <token>'" -ERROR
            return $null
        }
        Write-Status "ngrok found: $ngrokVersion" -OK
    } catch {
        Write-Status "ngrok not found. Install from https://ngrok.com" -ERROR
        return $null
    }

    # Check if ngrok already running on this port
    $existing = Get-ProcessByPort -Port 4040  # ngrok web UI port
    if ($existing) {
        Write-Status "ngrok already running (PID $($existing.Id))." -WARN
        return $existing.Id
    }

    # Start ngrok HTTP tunnel
    $ngrokArgs = @(
        "-WindowStyle", "Hidden",
        "-Command", "& { & '$NGROK_CMD' http $PROXY_PORT --log=stdout }"
    )

    $ngrokProcess = Start-Process powershell.exe @ngrokArgs -PassThru
    Write-Status "ngrok process started (PID $($ngrokProcess.Id))." -OK

    return $ngrokProcess.Id
}

function Get-NgrokUrl {
    # Query ngrok's local API to get the public URL
    try {
        $tunnels = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -TimeoutSec 5 -ErrorAction SilentlyContinue
        if ($tunnels -and $tunnels.tunnels) {
            foreach ($t in $tunnels.tunnels) {
                if ($t.proto -eq "http" -or $t.proto -eq "https") {
                    return $t.public_url
                }
            }
        }
    } catch {
        # Ignore
    }
    return $null
}

function Stop-All {
    Write-Status "Stopping proxy and ngrok..."

    # Kill processes listening on proxy port and ngrok UI port
    foreach ($port in @($PROXY_PORT, 4040)) {
        $proc = Get-ProcessByPort -Port $port
        if ($proc) {
            try {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                Write-Status "Stopped process on port $port (PID $($proc.Id))." -OK
            } catch {
                Write-Status "Could not stop process on port $port (PID $($proc.Id))." -WARN
            }
        }
    }

    # Also kill any powershell.exe running our scripts
    Get-Process powershell -ErrorAction SilentlyContinue | Where-Object {
        $_.CommandLine -like "*proxy.py*" -or $_.CommandLine -like "*ngrok*http*"
    } | ForEach-Object {
        try {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            Write-Status "Stopped PowerShell process (PID $($_.Id))." -OK
        } catch { }
    }

    Write-Status "All stopped." -OK
}

function Show-ProxyUrl {
    Write-Status "Waiting for ngrok URL (up to 15 seconds)..."
    $url = $null
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        $url = Get-NgrokUrl
        if ($url) { break }
    }

    if ($url) {
        $proxyUrl = $url -replace "^https://", "http://"
        $fullProxyUrl = "$proxyUrl/$PROXY_USER:$PROXY_PASS@" + ($url -replace "^https?://", "")

        Write-Status "" -OK
        Write-Status "╔═════════════════════════════════════════════════════════╗" -ForegroundColor Green
        Write-Status "║  PROXY IS READY                                        ║" -ForegroundColor Green
        Write-Status "╠═════════════════════════════════════════════════════════╣" -ForegroundColor Green
        Write-Status "║  Local proxy:  http://$PROXY_USER:$PROXY_PASS@localhost:$PROXY_PORT  ║" -ForegroundColor Green
        Write-Status "║  Ngrok tunnel: $url                                     ║" -ForegroundColor Green
        Write-Status "║                                                        ║" -ForegroundColor Green
        Write-Status "║  Coolify PROXY_URL (set this as Secret):               ║" -ForegroundColor Green
        Write-Status "║  http://$PROXY_USER:$PROXY_PASS@$($url -replace "^https://", "")  ║" -ForegroundColor Green
        Write-Status "╚═════════════════════════════════════════════════════════╝" -ForegroundColor Green
        Write-Status "" -OK
        Write-Status "In Coolify: Application → Environment Variables → Add PROXY_URL (Secret)" -ForegroundColor Cyan
        Write-Status "Then redeploy, and test with https://6fkk8bppuynxceqgnr6jy8vj.avalondigital.lk/api/test-proxy" -ForegroundColor Cyan
    } else {
        Write-Status "Could not detect ngrok URL. Check ngrok window for errors." -WARN
    }
}

# ─── MAIN ───────────────────────────────────────────────────────────────────
if ($PSBoundParameters.ContainsKey("Stop")) {
    Stop-All
    exit 0
}

Write-Status "Wcoflix Downloader - Local Proxy + ngrok Manager" -OK
Write-Status ""

$proxyId = Start-Proxy
$ngrokId = Start-Ngrok

if ($proxyId -and $ngrokId) {
    Show-ProxyUrl
    Write-Status "Proxy and ngrok are running. Press Ctrl+C to stop this script (does NOT stop proxy/ngrok)." -WARN
    Write-Status "To stop everything: .\start-proxy.ps1 -Stop" -ForegroundColor Cyan

    # Keep script alive so user can read the URL
    try {
        while ($true) { Start-Sleep -Seconds 1 }
    } catch {
        Write-Status "Exited." -OK
    }
} else {
    Write-Status "Failed to start proxy or ngrok. Check errors above." -ERROR
    exit 1
}