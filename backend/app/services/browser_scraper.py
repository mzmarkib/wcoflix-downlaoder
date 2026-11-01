"""
Playwright-based browser scraper with stealth mode for Cloudflare bypass.
Used as fallback when cloudscraper fails (no proxy, or proxy blocked).
"""
import asyncio
import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

from app.core.config import settings
from app.models.schemas import EpisodeInfo, AnimeInfo, Language, VideoSource, EpisodeDownloadInfo

logger = logging.getLogger(__name__)


class BrowserScraper:
    """
    Full browser automation with Playwright + stealth for Cloudflare bypass.
    Slower than cloudscraper but handles JS challenges, cookies, TLS fingerprints.
    """
    
    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._intercepted_urls = []  # Capture network requests for video URLs
    
    async def _ensure_browser(self):
        """Lazy-initialize browser with stealth."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            
            # Launch args for better Cloudflare evasion
            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-gpu',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--user-agent=' + settings.user_agent,
            ]
            
            proxy_config = None
            if self.proxy_url:
                # Parse proxy URL for Playwright
                import urllib.parse
                parsed = urllib.parse.urlparse(self.proxy_url)
                proxy_config = {
                    'server': f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                }
                if parsed.username and parsed.password:
                    proxy_config['username'] = parsed.username
                    proxy_config['password'] = parsed.password
            
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=launch_args,
                proxy=proxy_config
            )
            
            self._context = await self._browser.new_context(
                user_agent=settings.user_agent,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='America/New_York',
                permissions=[],
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            )
            
            # Apply stealth to avoid detection
            self._page = await self._context.new_page()
            await stealth_async(self._page)
            
            # Add comprehensive stealth scripts
            await self._page.add_init_script("""
                // Hide webdriver
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                
                // Mock plugins
                Object.defineProperty(navigator, 'plugins', { 
                    get: () => [
                        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                        {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}
                    ] 
                });
                
                // Mock languages
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                
                // Mock chrome
                window.chrome = { 
                    runtime: {}, 
                    loadTimes: function() {}, 
                    csi: function() {}, 
                    app: { isInstalled: false } 
                };
                
                // Mock permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );
                
                // Mock device memory
                Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                
                // Mock hardware concurrency
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                
                // Mock screen
                Object.defineProperty(screen, 'colorDepth', { get: () => 24 });
                
                // Remove automation indicators
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
                delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
            """)
            
            # Set up network request interception for video URLs
            async def handle_request(request):
                if any(ext in request.url for ext in ['.m3u8', '.mp4', '.webm']):
                    self._intercepted_urls.append(request.url)
            self._page.on('request', handle_request)
    
    async def close(self):
        """Clean up browser resources."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    async def _get_page(self, url: str) -> BeautifulSoup:
        """Navigate to URL and return parsed HTML."""
        await self._ensure_browser()
        
        try:
            # Navigate with wait for network idle
            response = await self._page.goto(
                url, 
                wait_until='domcontentloaded',
                timeout=settings.request_timeout * 1000
            )
            
            if not response or response.status >= 400:
                raise ConnectionError(f"HTTP {response.status if response else 'No response'}")
            
            # Wait for potential Cloudflare challenge
            await self._page.wait_for_load_state('domcontentloaded')
            await asyncio.sleep(3)  # Let JS execute
            
            # Check for Cloudflare challenge and try to resolve it
            content = await self._page.content()
            if 'challenge-platform' in content or 'cf-challenge' in content or 'Checking your browser' in content or 'Just a moment' in content:
                # Try to wait for challenge to complete with longer timeout
                logger.info("Cloudflare challenge detected, attempting to resolve...")
                await self._handle_cloudflare_challenge()
                
                content = await self._page.content()
                
                if 'challenge-platform' in content or 'cf-challenge' in content:
                    raise ConnectionError("Cloudflare challenge not resolved")
            
            return BeautifulSoup(content, 'lxml')
            
        except Exception as e:
            logger.error(f"Browser navigation failed for {url}: {e}")
            raise
    
    async def _handle_cloudflare_challenge(self):
        """Attempt to resolve Cloudflare challenge by waiting and interacting."""
        if not self._page:
            logger.warning("No page available for Cloudflare challenge handling")
            return
            
        max_wait = 30  # seconds
        check_interval = 2
        waited = 0
        
        while waited < max_wait:
            await asyncio.sleep(check_interval)
            waited += check_interval
            
            content = await self._page.content()
            
            # Check if challenge is still present
            if 'challenge-platform' not in content and 'cf-challenge' not in content:
                logger.info(f"Cloudflare challenge resolved after {waited}s")
                return
            
            # Try to find and click the checkbox if it exists
            try:
                # Common Cloudflare challenge selectors
                checkbox_selectors = [
                    'input[type="checkbox"]',
                    '#challenge-stage input',
                    '.cf-turnstile input',
                    '[data-ray] input',
                    'iframe[src*="challenge"] input',
                ]
                
                for selector in checkbox_selectors:
                    checkbox = await self._page.query_selector(selector)
                    if checkbox:
                        await checkbox.click()
                        logger.info("Clicked Cloudflare checkbox")
                        await asyncio.sleep(3)
                        break
            except Exception as e:
                logger.debug(f"Could not interact with challenge: {e}")
            
            # Also try to wait for the challenge iframe to load and complete
            try:
                frames = self._page.frames
                for frame in frames:
                    if 'challenge' in frame.url or 'turnstile' in frame.url:
                        logger.debug(f"Found challenge frame: {frame.url}")
                        # Try to click in the frame
                        try:
                            await frame.click('input[type="checkbox"]', timeout=2000)
                            await asyncio.sleep(2)
                        except:
                            pass
            except Exception as e:
                logger.debug(f"Frame interaction failed: {e}")
        
        logger.warning(f"Cloudflare challenge not resolved after {max_wait}s")
    
    def parse_anime_page(self, url: str, language: Language = Language.sub, season: str = "all") -> AnimeInfo:
        """Sync wrapper for parse_anime_page_async - uses thread pool to avoid event loop conflicts."""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self._parse_anime_page_async(url, language, season))
            return future.result()
    
    async def _parse_anime_page_async(self, url: str, language: Language = Language.sub, season: str = "all") -> AnimeInfo:
        from urllib.parse import urlparse
        
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        params = []
        if season != "all":
            params.append(f"season={season}")
        if language != Language.all:
            params.append(f"lang={language.value}")
        
        filtered_url = base_url
        if params:
            filtered_url += "?" + "&".join(params)
        
        logger.info(f"Fetching anime page (browser): {filtered_url}")
        soup = await self._get_page(filtered_url)
        
        return self._parse_anime_html(soup, language)
    
    def _parse_anime_html(self, soup: BeautifulSoup, language: Language) -> AnimeInfo:
        """Shared HTML parsing logic."""
        title_elem = soup.select_one('h1, h2, .anime-title, .entry-title')
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Anime"
        
        cover_elem = soup.select_one('img[src*="wcostream"], img[src*="catimg"], .anime-cover img, .poster img')
        cover_url = cover_elem.get('src') if cover_elem else None
        
        desc_elem = soup.select_one('.anime-description, .entry-content, .description, .synopsis')
        description = desc_elem.get_text(strip=True) if desc_elem else None
        
        genre_elems = soup.select('a[href*="genre"], .genre a, .genres a')
        genres = [g.get_text(strip=True) for g in genre_elems]
        
        detected_seasons = self._detect_seasons(soup)
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
        seasons = set()
        
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
        """Sync wrapper for extract_video_sources_async - uses thread pool to avoid event loop conflicts."""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, self._extract_video_sources_async(episode_url))
            return future.result()
    
    async def _extract_video_sources_async(self, episode_url: str) -> List[VideoSource]:
        logger.info(f"Fetching episode page (browser): {episode_url}")
        soup = await self._get_page(episode_url)
        
        sources = []
        
        # Method 1: Video tags
        for video in soup.select('video source, video'):
            src = video.get('src') or video.get('data-src')
            if src:
                sources.append(VideoSource(quality=self._guess_quality(src), url=src, type=self._get_source_type(src)))
        
        # Method 2: Iframes (embedded players)
        for iframe in soup.select('iframe'):
            src = iframe.get('src') or iframe.get('data-src')
            if src and any(d in src for d in ['wcostream', 'vidstream', 'stream', 'embed']):
                sources.append(VideoSource(quality="Auto", url=src, type="embed"))
        
        # Method 3: Download links
        for link in soup.select('a[href*=".mp4"], a[href*=".m3u8"], a[href*="download"], a[href*="dl."]'):
            href = link.get('href')
            if href:
                sources.append(VideoSource(quality=self._guess_quality(href), url=href, type=self._get_source_type(href)))
        
        # Method 4: Scripts with video URLs
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                urls = re.findall(r'https?://[^\s"\']+\.(?:m3u8|mp4|webm)', script.string)
                for url in urls:
                    sources.append(VideoSource(quality=self._guess_quality(url), url=url, type=self._get_source_type(url)))
        
        # Method 5: Network requests (intercepted during page load)
        if hasattr(self, '_intercepted_urls') and self._intercepted_urls:
            for url in self._intercepted_urls:
                if any(ext in url for ext in ['.m3u8', '.mp4', '.webm']):
                    sources.append(VideoSource(quality=self._guess_quality(url), url=url, type=self._get_source_type(url)))
        
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
        try:
            sources = self.extract_video_sources(str(episode.url))
            return EpisodeDownloadInfo(episode=episode, video_sources=sources)
        except Exception as e:
            logger.error(f"Error extracting video sources for {episode.url}: {e}")
            return EpisodeDownloadInfo(episode=episode, video_sources=[], error=str(e))