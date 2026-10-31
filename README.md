# Wcoflix Downloader

A web-based tool to generate batch download links for anime episodes from wcoflix.tv. Supports IDM (Internet Download Manager), AB Downloader, Aria2, and more.

## Features

- 🎬 Scrape anime episode lists from wcoflix.tv
- 🔍 Extract video download links from episode pages
- 📥 Generate batch download files for:
  - **IDM (Internet Download Manager)** - Text format for batch import
  - **AB Downloader** - `.lst` format
  - **Aria2** - Input file format
  - **Simple Text** - One URL per line
  - **M3U Playlist** - For media players (VLC, MPV)
- 🌐 Modern web UI with episode selection
- 🐳 Docker-ready for Coolify deployment
- ⚡ Auto-deploy on git push

## Quick Start

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (in another terminal)
cd frontend
npm install
npm run dev
```

### Docker

```bash
docker-compose up --build
```

## Coolify Deployment

### 1. Prepare Repository

Push this repository to GitHub (already done at `https://github.com/mzmarkib/wcoflix-downlaoder.git`)

### 2. Create Coolify Application

1. In Coolify, click **New Resource** → **Application**
2. Select **GitHub** as source
3. Connect your repository: `mzmarkib/wcoflix-downlaoder`
4. Set **Build Pack** to `Dockerfile`
5. Set **Dockerfile Path** to `Dockerfile` (root)
6. Set **Port** to `8000`

### 3. Configure Environment Variables

In Coolify application settings, add these environment variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `DEBUG` | No | Set to `false` for production |
| `PROXY_URL` | No | Residential proxy for Cloudflare bypass (e.g., `http://user:pass@proxy:port`) |
| `USER_AGENT` | No | Custom user agent string |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |

### 4. Enable Auto-Deploy

1. Go to **Deployments** → **Settings**
2. Enable **Auto Deploy** on push to main branch
3. Configure webhook in GitHub repository settings:
   - URL: `https://your-coolify-domain.com/api/v1/webhooks/github/your-webhook-id`
   - Events: Push

### 5. Deploy

Click **Deploy** or push to main branch to trigger deployment.

## Cloudflare Protection Note

⚠️ **Important**: wcoflix.tv uses Cloudflare protection that blocks automated scraping. The application uses `cloudscraper` to bypass basic challenges, but for reliable scraping you need:

1. **Residential Proxies** (Recommended):
   - Bright Data, Oxylabs, Smartproxy, IPRoyal, etc.
   - Set `PROXY_URL` environment variable

2. **Alternative Approaches**:
   - Run locally with your browser session cookies
   - Use a headless browser with stealth plugins (Playwright/Puppeteer)
   - Manual cookie injection

Without a proxy, the scraper will likely hit Cloudflare challenge pages and fail to extract video links.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/scrape` | Scrape anime page for episode list |
| `POST` | `/api/scrape/episodes` | Scrape episodes + video sources |
| `POST` | `/api/scrape/episode/{url}` | Scrape single episode |
| `POST` | `/api/generate-downloads` | Generate batch download files |
| `GET` | `/api/download/{job_id}/{format}` | Download specific format |
| `GET` | `/api/download/{job_id}/zip` | Download all formats as ZIP |
| `GET` | `/api/health` | Health check |

## Usage

1. Open the deployed URL
2. Paste a wcoflix anime URL (e.g., `https://www.wcoflix.tv/anime/the-apothecary-diaries/?season=all&lang=sub`)
3. Select language (Sub/Dub/All) and Season
4. Click **Scrape Episodes**
5. Wait for video source extraction
6. Select episodes to download
7. Click **Generate Download Files**
8. Download the format you need

## Supported Download Formats

| Format | Extension | Use Case |
|--------|-----------|----------|
| IDM | `.txt` | Import via IDM "Add Batch" → "From text file" |
| AB Downloader | `.lst` | Load in AB Downloader |
| Aria2 | `.txt` | `aria2c -i file.txt` |
| Simple Text | `.txt` | Any download manager |
| M3U | `.m3u` | VLC, MPV, IPTV players |

## Project Structure

```
wcoflix-downlaoder/
├── backend/
│   ├── app/
│   │   ├── api/routes.py          # API endpoints
│   │   ├── core/config.py         # Configuration
│   │   ├── models/schemas.py      # Pydantic models
│   │   ├── services/
│   │   │   ├── scraper.py         # wcoflix scraping logic
│   │   │   └── download_generator.py  # Batch file generation
│   │   └── main.py                # FastAPI app
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Main React component
│   │   ├── main.jsx               # Entry point
│   │   └── index.css              # Styles
│   ├── package.json
│   └── vite.config.js
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## License

MIT License - Feel free to use and modify.

## Disclaimer

This tool is for educational purposes only. Downloading copyrighted content may violate terms of service and local laws. Use responsibly.