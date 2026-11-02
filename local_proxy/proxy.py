#!/usr/bin/env python3
"""
Simple HTTP Proxy with Authentication for wcoflix-downloader
Run on your laptop to expose your residential IP to Coolify via ngrok.

Usage:
    python proxy.py

Environment variables (optional):
    PROXY_PORT=8080         Port to listen on (default: 8080)
    PROXY_USER=myuser       Proxy username (default: 'user')
    PROXY_PASS=mypassword   Proxy password (default: 'pass')
    BIND_ADDR=0.0.0.0       Bind address (default: 0.0.0.0)
"""

import socket
import threading
import base64
import os
import sys
import time
import signal
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler


# Configuration from environment
PROXY_PORT = int(os.environ.get("PROXY_PORT", "8080"))
PROXY_USER = os.environ.get("PROXY_USER", "user")
PROXY_PASS = os.environ.get("PROXY_PASS", "pass")
BIND_ADDR = os.environ.get("BIND_ADDR", "0.0.0.0")

# Auth header
AUTH_HEADER = base64.b64encode(f"{PROXY_USER}:{PROXY_PASS}".encode()).decode()


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP proxy handler with basic auth."""

    def log_message(self, format, *args):
        """Suppress default logging to keep output clean."""
        pass

    def do_CONNECT(self):
        """Handle HTTPS CONNECT tunneling."""
        if not self._check_auth():
            self.send_response(407)
            self.send_header("Proxy-Authenticate", 'Basic realm="Proxy"')
            self.end_headers()
            return

        try:
            host, port = self.path.split(":")
            port = int(port)
            remote = socket.create_connection((host, port), timeout=10)
            self.send_response(200, "Connection Established")
            self.end_headers()

            conn = self.connection
            # Bidirectional tunnel
            def forward(src, dst):
                try:
                    while True:
                        data = src.recv(4096)
                        if not data:
                            break
                        dst.sendall(data)
                except Exception:
                    pass
                finally:
                    try:
                        src.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    try:
                        src.close()
                    except Exception:
                        pass
                    try:
                        dst.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass
                    try:
                        dst.close()
                    except Exception:
                        pass

            t1 = threading.Thread(target=forward, args=(conn, remote), daemon=True)
            t2 = threading.Thread(target=forward, args=(remote, conn), daemon=True)
            t1.start()
            t2.start()
            t1.join()
            t2.join()
        except Exception as e:
            try:
                self.send_response(502)
                self.end_headers()
            except Exception:
                pass

    def do_GET(self):
        """Handle HTTP GET requests."""
        if not self._check_auth():
            self.send_response(407)
            self.send_header("Proxy-Authenticate", 'Basic realm="Proxy"')
            self.end_headers()
            return

        try:
            # Parse target URL
            if not self.path.startswith("http"):
                self.send_response(400)
                self.end_headers()
                return

            req = urllib.request.Request(
                self.path,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                # Forward key headers
                for key in ("Content-Type", "Content-Length", "Location"):
                    if key in resp.headers:
                        self.send_header(key, resp.headers[key])
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
        except Exception as e:
            try:
                self.send_response(502)
                self.end_headers()
            except Exception:
                pass

    def do_POST(self):
        """Handle HTTP POST requests."""
        self.do_GET()

    def _check_auth(self):
        """Check Basic Auth header."""
        auth = self.headers.get("Proxy-Authorization", "")
        if auth.startswith("Basic "):
            return auth.split(" ", 1)[1] == AUTH_HEADER
        return False


def print_banner():
    print("=" * 60)
    print("  WCOFLIX DOWNLOADER - LOCAL RESIDENTIAL PROXY")
    print("=" * 60)
    print(f"  Listen address: {BIND_ADDR}:{PROXY_PORT}")
    print(f"  Proxy username: {PROXY_USER}")
    print(f"  Proxy password: {PROXY_PASS}")
    print(f"  Proxy URL:      http://{PROXY_USER}:{PROXY_PASS}@{BIND_ADDR}:{PROXY_PORT}")
    print()
    print("  For Coolify PROXY_URL, use the ngrok URL:")
    print(f"  http://{PROXY_USER}:{PROXY_PASS}@<ngrok-url>")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 60)


def main():
    print_banner()
    server = HTTPServer((BIND_ADDR, PROXY_PORT), ProxyHandler)

    def shutdown(signum, frame):
        print("\nShutting down proxy...")
        server.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("Proxy stopped.")


if __name__ == "__main__":
    main()