from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import List, Optional
import logging
import uuid
import os

from app.models.schemas import (
    ScrapeRequest, AnimeInfo, EpisodeDownloadInfo, 
    BatchDownloadRequest, BatchDownloadResponse, Language
)
from app.services.scraper import scraper, CloudflareBypassScraper
from app.services.download_generator import DownloadFileGenerator
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["downloader"])

# In-memory job storage (use Redis in production)
jobs = {}


def _get_scraper(proxy_url: Optional[str] = None):
    """Get scraper instance with optional proxy override."""
    if proxy_url:
        # Create a new scraper with the proxy
        from app.services.scraper import WcoflixScraper
        return WcoflixScraper(proxy_url=proxy_url)
    return scraper


@router.post("/scrape", response_model=AnimeInfo)
async def scrape_anime(request: ScrapeRequest):
    """Scrape anime page to get episode list."""
    try:
        s = _get_scraper(request.proxy_url)
        anime = s.parse_anime_page(
            str(request.url), 
            language=request.language, 
            season=request.season or "all"
        )
        return anime
    except Exception as e:
        logger.error(f"Scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape/episodes", response_model=List[EpisodeDownloadInfo])
async def scrape_episodes(request: ScrapeRequest):
    """Scrape anime page and extract video sources for all episodes."""
    try:
        s = _get_scraper(request.proxy_url)
        # First get anime info with episode list
        anime = s.parse_anime_page(
            str(request.url), 
            language=request.language, 
            season=request.season or "all"
        )
        
        # Then get video sources for each episode
        results = []
        for episode in anime.episodes:
            ep_info = s.get_episode_download_info(episode)
            results.append(ep_info)
        
        return results
    except Exception as e:
        logger.error(f"Episode scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape/episode/{episode_url:path}")
async def scrape_single_episode(episode_url: str, proxy_url: Optional[str] = None):
    """Scrape a single episode for video sources."""
    try:
        from app.models.schemas import EpisodeInfo, Language
        s = _get_scraper(proxy_url)
        
        # Create a minimal episode info
        ep = EpisodeInfo(
            title="Unknown Episode",
            url=episode_url,
            language=Language.sub
        )
        
        ep_info = s.get_episode_download_info(ep)
        return ep_info
    except Exception as e:
        logger.error(f"Single episode scrape error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-downloads")
async def generate_downloads(request: BatchDownloadRequest):
    """Generate batch download files for the given episodes."""
    try:
        job_id = str(uuid.uuid4())
        output_dir = f"/tmp/wcoflix_downloads/{job_id}"
        
        # Generate all formats
        results = DownloadFileGenerator.generate_all_formats(request.episodes, output_dir)
        
        # Store job info
        jobs[job_id] = {
            'status': 'completed',
            'output_dir': output_dir,
            'files': results
        }
        
        return {
            'job_id': job_id,
            'download_url': f"/api/download/{job_id}",
            'files': {k: {'filename': v['filename'], 'url': f"/api/download/{job_id}/{k}"} 
                     for k, v in results.items()}
        }
    except Exception as e:
        logger.error(f"Download generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{job_id}/zip")
async def download_zip(job_id: str):
    """Download all formats as a zip file."""
    from fastapi.responses import FileResponse
    import zipfile
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    output_dir = job['output_dir']
    zip_path = f"{output_dir}/wcoflix_batch_downloads.zip"
    
    # Create zip if not exists
    if not os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for format_type, file_info in job['files'].items():
                if os.path.exists(file_info['path']):
                    zf.write(file_info['path'], file_info['filename'])
    
    return FileResponse(
        path=zip_path,
        filename="wcoflix_batch_downloads.zip",
        media_type='application/zip'
    )


@router.get("/download/{job_id}/{format_type}")
async def download_file(job_id: str, format_type: str):
    """Download a generated batch file."""
    from fastapi.responses import FileResponse
    
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    if format_type not in job['files']:
        raise HTTPException(status_code=404, detail="Format not found")
    
    file_info = job['files'][format_type]
    return FileResponse(
        path=file_info['path'],
        filename=file_info['filename'],
        media_type='application/octet-stream'
    )


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "wcoflix-downloader"}


@router.get("/test-proxy")
async def test_proxy(proxy_url: Optional[str] = Query(None)):
    """Test if a proxy can reach wcoflix.tv."""
    import httpx
    
    test_url = "https://www.wcoflix.tv"
    proxy = proxy_url or settings.proxy_url
    
    try:
        test_scraper = CloudflareBypassScraper(proxy_url=proxy) if proxy else scraper
        # Just test basic connectivity
        session = test_scraper._cloudscraper
        if proxy:
            session.proxies = {'http': proxy, 'https': proxy}
        
        response = session.get(test_url, timeout=10)
        response.raise_for_status()
        
        # Check if we got a real page (not Cloudflare challenge)
        if 'challenge-platform' in response.text or 'Cloudflare' in response.text:
            if len(response.text) < 5000 and 'challenge' in response.text.lower():
                return {"status": "cloudflare_challenge", "message": "Proxy reached wcoflix but hit Cloudflare challenge"}
        
        return {"status": "connected", "message": "Proxy can reach wcoflix.tv"}
    except httpx.ProxyError as e:
        return {"status": "proxy_error", "message": f"Proxy connection failed: {str(e)}"}
    except httpx.ConnectError as e:
        return {"status": "connection_error", "message": f"Cannot connect via proxy: {str(e)}"}
    except httpx.TimeoutException:
        return {"status": "timeout", "message": "Proxy request timed out"}
    except Exception as e:
        return {"status": "error", "message": f"Proxy test failed: {str(e)}"}


@router.get("/test-proxy-debug")
async def test_proxy_debug():
    """Debug test endpoint."""
    return {"status": "debug", "message": "Test proxy debug endpoint works"}