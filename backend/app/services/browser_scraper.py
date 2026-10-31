"""
Browser-based scraper using Playwright with stealth mode.
Used as fallback when cloudscraper fails or no proxy available.
"""
import asyncio
import logging
import re
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from app.models.schemas import EpisodeInfo, AnimeInfo, Language, VideoSource, EpisodeDownloadInfo

logger = logging.getLogger(__name__)

# Global browser instance for reuse
_browser = None
_playwright = None


async def _get_browser():
    """Get or create Playwright browser instance with stealth."""
    global _browser, _playwright
    
    if _browser and _browser.is_connected():
        return _browser
    
    try:
        from playwright.async_api import async_playwright
        from playwright_stealth import stealth_async
    except ImportError:
        logger.warning("Playwright not available, browser scraping disabled")
        return None
    
    _playwright = await async_playwright().start()
    
    # Launch browser with realistic fingerprint
    _browser = await _playwright.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-web-security',
            '--disable-features=IsolateOrigins,site-per-process',
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        ]
    )
    
    return _browser


async def _create_stealth_page(browser, proxy_url: Optional[str] = None):
    """Create a new page with stealth mode enabled."""
    from playwright_stealth import stealth_async
    
    context_options = {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'locale': 'en-US',
        'timezone_id': 'America/New_York',
        'permissions': [],
        'extra_http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
    }
    
    if proxy_url:
        context_options['proxy'] = {'server': proxy_url}
    
    context = await browser.new_context(**context_options)
    page = await context.new_page()
    
    # Apply stealth
    await stealth_async(page)
    
    # Additional anti-detection
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = { runtime: {} };
    """)
    
    return page, context


class BrowserScraper:
    """Playwright-based scraper with stealth mode for Cloudflare bypass."""
    
    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url
        self._browser = None
    
    async def __aenter__(self):
        self._browser = await _get_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass  # Browser is globally managed
    
    async def _fetch_page(self, url: str, wait_for: str = 'networkidle') -> str:
        """Fetch page content using Playwright with stealth."""
        if not self._browser:
            raise RuntimeError("Browser not initialized")
        
        page, context = await _create_stealth_page(self._browser, self.proxy_url)
        
        try:
            logger.info(f"Browser fetching: {url}")
            
            # Navigate with timeout
            response = await page.goto(url, wait_until=wait_for, timeout=60000)
            
            if not response:
                raise ConnectionError(f"Failed to load {url}")
            
            # Check for Cloudflare challenge
            content = await page.content()
            if self._is_cloudflare_challenge(content, page):
                # Wait a bit more for challenge to resolve
                await page.wait_for_timeout(5000)
                content = await page.content()
                
                if self._is_cloudflare_challenge(content, page):
                    raise ConnectionError("Cloudflare challenge not resolved")
            
            # Wait for dynamic content
            await page.wait_for_timeout(2000)
            
            # Get final content
            content = await page.content()
            return content
            
        finally:
            await context.close()
    
    def _is_cloudflare_challenge(self, content: str, page) -> bool:
        """Check if page is Cloudflare challenge."""
        if len(content) < 5000:
            if 'challenge-platform' in content or 'cf-challenge' in content:
                return True
            if 'Cloudflare' in content and 'challenge' in content.lower():
                return True
        return False
    
    def parse_anime_page(self, url: str, language: Language = Language.sub, season: str = "all") -> AnimeInfo:
        """Parse anime page using browser."""
        # Build filtered URL
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        params = []
        if season != "all":
            params.append(f"season={season}")
        if language != Language.all:
            params.append(f"lang={language.value}")
        
        filtered_url = base_url + ("?" + "&".join(params) if params else "")
        
        # Run async in sync context
        content = asyncio.run(self._fetch_page(filtered_url))
        soup = BeautifulSoup(content, 'lxml')
        
        return self._parse_anime_html(soup, filtered_url, language)
    
    def _parse_anime_html(self, soup: BeautifulSoup, url: str, language: Language) -> AnimeInfo:
        """Parse anime info from HTML (same logic as cloudscraper)."""
        # Extract title
        title_elem = soup.select_one('h1, h2, .anime-title, .entry-title')
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Anime"
        
        # Cover image
        cover_elem = soup.select_one('img[src*="wcostream"], img[src*="catimg"], .anime-cover img, .poster img')
        cover_url = cover_elem.get('src') if cover_elem else None
        
        # Description
        desc_elem = soup.select_one('.anime-description, .entry-content, .description, .synopsis')
        description = desc_elem.get_text(strip=True) if desc_elem else None
        
        # Genres
        genre_elems = soup.select('a[href*="genre"], .genre a, .genres a')
        genres = [g.get_text(strip=True) for g in genre_elems]
        
        # Detect seasons
        detected_seasons = self._detect_seasons(soup)
        
        # Extract episodes
        episodes = self._extract_episodes(soup, language)
        
        return AnimeInfo(
            title=title,
            cover_url=cover_url,
            description=description,
            genres=genres,
            episodes=episodes,
            total_episodes=len(episodes),
            seasons=detected_seasons
        )
    
    def _detect_seasons(self, soup: BeautifulSoup) -> List[int]:
        """Detect available seasons from page."""
        seasons = set()
        
        # Method 1: Season tabs/buttons
        season_tabs = soup.select('[data-season], .season-tab, .season-btn, .season-filter a, [href*="season="]')
        for tab in season_tabs:
            data_season = tab.get('data-season')
            if data_season and data_season.isdigit():
                seasons.add(int(data_season))
            
            href = tab.get('href', '')
            season_match = re.search(r'season[=-](\d+)', href)
            if season_match:
                seasons.add(int(season_match.group(1)))
            
            text = tab.get_text(strip=True)
            season_match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
            if season_match:
                seasons.add(int(season_match.group(1)))
        
        # Method 2: From episode URLs
        episode_links = soup.select('a[href*="episode"]')
        for link in episode_links:
            href = link.get('href', '')
            season_match = re.search(r'season[_-]?(\d+)', href, re.IGNORECASE)
            if season_match:
                seasons.add(int(season_match.group(1)))
        
        if not seasons:
            seasons.add(1)
        
        return sorted(seasons)
    
    def _extract_episodes(self, soup: BeautifulSoup, language: Language) -> List[EpisodeInfo]:
        """Extract episode links."""
        episodes = []
        episode_links = soup.select('a[href*="episode"]')
        
        seen_urls = set()
        for link in episode_links:
            href = link.get('href')
            if not href:
                continue
            
            full_url = urljoin("https://www.wcoflix.tv", href)
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            
            text = link.get_text(strip=True)
            ep_info = self._parse_episode_info(full_url, text, language)
            if ep_info:
                episodes.append(ep_info)
        
        episodes.sort(key=lambda e: (e.season or 0, e.episode or 0))
        return episodes
    
    def _parse_episode_info(self, url: str, text: str, language: Language) -> Optional[EpisodeInfo]:
        """Parse episode info from URL and text."""
        season_match = re.search(r'season[_-]?(\d+)', url, re.IGNORECASE)
        episode_match = re.search(r'episode[_-]?(\d+)', url, re.IGNORECASE)
        
        if not season_match:
            season_match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
        if not episode_match:
            episode_match = re.search(r'Episode\s+(\d+)', text, re.IGNORECASE)
        
        season = int(season_match.group(1)) if season_match else None
        episode = int(episode_match.group(1)) if episode_match else None
        
        ep_language = language
        if 'dubbed' in url.lower() or 'dubbed' in text.lower():
            ep_language = Language.dub
        elif 'subbed' in url.lower() or 'subbed' in text.lower():
            ep_language = Language.sub
        
        title = text.replace('FullHD', '').strip()
        if not title:
            if season and episode:
                title = f"Season {season} Episode {episode}"
            elif episode:
                title = f"Episode {episode}"
            elif season:
                title = f"Season {season}"
            else:
                title = "Unknown Episode"
        
        return EpisodeInfo(
            title=title,
            url=url,
            season=season,
            episode=episode,
            language=ep_language,
            quality="FullHD"
        )
    
    def extract_video_sources(self, episode_url: str) -> List[VideoSource]:
        """Extract video sources from episode page."""
        content = asyncio.run(self._fetch_page(episode_url, wait_for='domcontentloaded'))
        soup = BeautifulSoup(content, 'lxml')
        
        sources = []
        
        # Method 1: Video tags
        for video in soup.select('video source, video'):
            src = video.get('src') or video.get('data-src')
            if src:
                sources.append(VideoSource(
                    quality=self._guess_quality(src),
                    url=src,
                    type=self._get_source_type(src)
                ))
        
        # Method 2: Iframes (embedded players)
        for iframe in soup.select('iframe'):
            src = iframe.get('src') or iframe.get('data-src')
            if src and any(d in src for d in ['wcostream', 'vidstream', 'stream', 'embed', 'player']):
                sources.append(VideoSource(quality="Auto", url=src, type="embed"))
        
        # Method 3: Download links
        for link in soup.select('a[href*=".mp4"], a[href*=".m3u8"], a[href*="download"], a[href*="dl."]'):
            href = link.get('href')
            if href:
                sources.append(VideoSource(
                    quality=self._guess_quality(href),
                    url=href,
                    type=self._get_source_type(href)
                ))
        
        # Method 4: JavaScript/JSON data
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                urls = re.findall(r'https?://[^\s"\']+\.(?:m3u8|mp4|webm)', script.string)
                for u in urls:
                    sources.append(VideoSource(
                        quality=self._guess_quality(u),
                        url=u,
                        type=self._get_source_type(u)
                    ))
        
        # Deduplicate
        seen = set()
        unique = []
        for s in sources:
            if s.url not in seen:
                seen.add(s.url)
                unique.append(s)
        
        return unique
    
    def _guess_quality(self, url: str) -> str:
        url_lower = url.lower()
        if '1080' in url_lower or 'fullhd' in url_lower or 'fhd' in url_lower:
            return '1080p'
        elif '720' in url_lower or 'hd' in url_lower:
            return '720p'
        elif '480' in url_lower or 'sd' in url_lower:
            return '480p'
        return 'Auto'
    
    def _get_source_type(self, url: str) -> str:
        url_lower = url.lower()
        if '.m3u8' in url_lower:
            return 'm3u8'
        elif any(ext in url_lower for ext in ['.mp4', '.webm', '.mkv']):
            return 'direct'
        return 'embed'
    
    def get_episode_download_info(self, episode: EpisodeInfo) -> EpisodeDownloadInfo:
        """Get full download info for an episode."""
        try:
            sources = self.extract_video_sources(str(episode.url))
            return EpisodeDownloadInfo(episode=episode, video_sources=sources)
        except Exception as e:
            logger.error(f"Error extracting video sources for {episode.url}: {e}")
            return EpisodeDownloadInfo(episode=episode, video_sources=[], error=str(e))


# Convenience function for sync usage
def scrape_with_browser(url: str, language: Language = Language.sub, season: str = "all", proxy_url: Optional[str] = None) -> AnimeInfo:
    """Synchronous wrapper for browser scraping."""
    scraper = BrowserScraper(proxy_url=proxy_url)
    return scraper.parse_anime_page(url, language, season)


def scrape_episodes_with_browser(url: str, language: Language = Language.sub, season: str = "all", proxy_url: Optional[str] = None) -> List[EpisodeDownloadInfo]:
    """Scrape anime page and extract video sources for all episodes."""
    scraper = BrowserScraper(proxy_url=proxy_url)
    anime = scraper.parse_anime_page(url, language, season)
    
    results = []
    for episode in anime.episodes:
        ep_info = scraper.get_episode_download_info(episode)
        results.append(ep_info)
    
    return results