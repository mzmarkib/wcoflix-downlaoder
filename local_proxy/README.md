# Local Residential Proxy + ngrok for Wcoflix Downloader

Turn your Windows laptop into a residential proxy that your Coolify-deployed Wcoflix Downloader can use to scrape wcoflix.tv.

## Files

| File | Purpose |
|------|---------|
| `proxy.py` | Python HTTP proxy with Basic Auth (runs on your laptop) |
| `start-proxy.ps1` | PowerShell script to start/stop proxy + ngrok with one command |

## Prerequisites

1. **Python 3** installed on your laptop  
   Download: https://python.org  
   Verify: `python --version`

2. **ngrok** installed and authenticated  
   Download: https://ngrok.com/download  
   Get a free authtoken from https://dashboard.ngrok.com/get-started/setup  
   Run once: `ngrok config add-authtoken <your-token>`

3. **PowerShell** (built into Windows)

## Quick Start

### 1. Open PowerShell in this folder

Right-click the `local_proxy/` folder → "Open in Terminal" or "Open PowerShell window here"

### 2. Start the proxy and ngrok

```powershell
.\start-proxy.ps1
```

This will:
- Start a local HTTP proxy on `http://localhost:8080`
- Start ngrok to expose it to the internet
- Display your **Coolify PROXY_URL** (copy this!)

### 3. Set PROXY_URL in Coolify

1. Go to your Coolify application page
2. **Environment Variables** → Add variable:
   - **Key:** `PROXY_URL`
   - **Value:** `http://wcoflix_user:wcoflix_pass_2026@<ngrok-url>` (copy from script output)
   - **Is Secret:** ✅ Yes
   - **Is Runtime:** ✅ Yes
3. **Deploy** (or it auto-deploys on next push)

### 4. Test

Visit your app: https://6fkk8bppuynxceqgnr6jy8vj.avalondigital.lk

- Enter the proxy URL in the Proxy Settings panel
- Click **Test** → should show **CONNECTED**
- Enter: `https://www.wcoflix.tv/anime/mushoku-tensei-jobless-reincarnation/?season=all`
- Click **Scrape Episodes** → should now work!

### 5. Stop everything

```powershell
.\start-proxy.ps1 -Stop
```

## Customizing Credentials

Edit `start-proxy.ps1` and change these lines:

```powershell
$PROXY_USER = "your_username"      # <-- change
$PROXY_PASS = "your_password"      # <-- change
```

Then restart the proxy.

## How It Works

1. `proxy.py` listens on your laptop's port 8080
2. `ngrok` creates a public tunnel (e.g., `https://abc123.ngrok-free.app`)
3. Coolify connects through ngrok → your laptop → wcoflix.tv (your residential IP)
4. Cloudflare sees a real residential connection, not a datacenter bot

## Important Notes

- **Keep your laptop awake** — if it sleeps, the proxy dies and scraping stops
- **Keep PowerShell open** — closing it stops ngrok (but not necessarily the Python proxy)
- **Change the default credentials** — anyone with the proxy URL can use it
- **Free ngrok limits** — bandwidth and connection limits apply; upgrade if needed
- **Your home IP is exposed** — only share the proxy URL with trusted parties

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python: command not found` | Use `py` instead of `python`, or add Python to PATH |
| `ngrok: command not found` | Add ngrok to PATH or use full path to ngrok.exe |
| Port 8080 already in use | Change `$PROXY_PORT` in start-proxy.ps1 |
| ngrok URL not detected | Make sure ngrok web UI is accessible at `http://localhost:4040` |
| Coolify can't connect | Check that ngrok tunnel is up and URL is correct in Coolify |

## Repository

https://github.com/mzmarkib/wcoflix-downlaoder
