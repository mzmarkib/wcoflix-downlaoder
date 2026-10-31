@echo off
REM Windows ngrok + tinyproxy setup for wcoflix downloader
REM Run as Administrator

echo ============================================
echo wcoflix Downloader - ngrok Proxy Setup (Windows)
echo ============================================

REM 1. Check if tinyproxy exists
if not exist "C:\Program Files\tinyproxy\tinyproxy.exe" (
    echo.
    echo [1/4] Installing tinyproxy via Chocolatey...
    choco install tinyproxy -y
    if errorlevel 1 (
        echo Chocolatey not found. Installing Chocolatey first...
        powershell -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
        choco install tinyproxy -y
    )
) else (
    echo [1/4] tinyproxy already installed
)

REM 2. Configure tinyproxy
echo.
echo [2/4] Configuring tinyproxy...
set TINYPROXY_CONF=C:\Program Files\tinyproxy\tinyproxy.conf
if not exist "%TINYPROXY_CONF%" (
    echo ERROR: tinyproxy.conf not found at %TINYPROXY_CONF%
    pause
    exit /b 1
)

REM Backup original
copy "%TINYPROXY_CONF%" "%TINYPROXY_CONF%.bak" >nul

REM Write new config
(
    echo Port 8080
    echo Listen 0.0.0.0
    echo Allow 127.0.0.1
    echo Allow 0.0.0.0/0
    echo LogLevel Info
    echo Timeout 600
    echo MaxClients 100
    echo MinSpareServers 5
    echo MaxSpareServers 20
    echo StartServers 10
) > "%TINYPROXY_CONF%"

echo tinyproxy configured on port 8080

REM 3. Start tinyproxy
echo.
echo [3/4] Starting tinyproxy...
net stop tinyproxy 2>nul
sc config tinyproxy start= demand 2>nul
net start tinyproxy
if errorlevel 1 (
    echo Starting tinyproxy directly...
    start "tinyproxy" "C:\Program Files\tinyproxy\tinyproxy.exe" -c "%TINYPROXY_CONF%"
)

timeout /t 2 >nul

REM 4. Check if running
netstat -an | findstr :8080 >nul
if errorlevel 1 (
    echo WARNING: tinyproxy may not be running on port 8080
) else (
    echo tinyproxy running on port 8080
)

REM 5. Create ngrok adapter script
echo.
echo [4/4] Creating ngrok adapter...
cat > ngrok_adapter.py << 'PYEOF'
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
import sys
import threading
import time

class ProxyHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.proxy_opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({
                'http': 'http://127.0.0.1:8080',
                'https': 'http://127.0.0.1:8080'
            })
        )
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        try:
            req = urllib.request.Request(self.path)
            req.add_header('User-Agent', self.headers.get('User-Agent', 'Mozilla/5.0'))
            for h in ['Accept', 'Accept-Language', 'Accept-Encoding', 'Connection', 'Referer']:
                if self.headers.get(h):
                    req.add_header(h, self.headers.get(h))
            
            resp = self.proxy_opener.open(req, timeout=30)
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ['transfer-encoding', 'content-encoding']:
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_error(502, f"Proxy error: {str(e)}")
    
    def do_POST(self):
        self.do_GET()
    
    def do_HEAD(self):
        self.do_GET()
    
    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {self.client_address[0]} - {format % args}")

if __name__ == '__main__':
    print("Starting ngrok adapter on port 8081...")
    print("Forwarding to tinyproxy on port 8080")
    server = HTTPServer(('0.0.0.0', 8081), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()
PYEOF

echo.
echo ============================================
echo SETUP COMPLETE
echo ============================================
echo.
echo Next steps:
echo 1. Run ngrok in a NEW terminal:
echo    ngrok http 8081
echo.
echo 2. Copy the HTTPS URL (e.g., https://abc123.ngrok-free.app)
echo.
echo 3. In Coolify, add Environment Variable:
echo    PROXY_URL=https://your-ngrok-url.ngrok-free.app
echo.
echo 4. Redeploy the app
echo.
echo To test locally first:
echo    curl -x http://127.0.0.1:8080 https://httpbin.org/ip
echo.
pause