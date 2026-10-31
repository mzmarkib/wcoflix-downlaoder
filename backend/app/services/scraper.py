"""
Combined scraper: tries cloudscraper first, falls back to Playwright browser with stealth.
"""
import re
import cloudscraper
from bs4 import BeautifulSoup
from typing import List, Optional
from urllib.parse import urljoin, urlparse
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

from app.core.config import settings
from app.models.schemas import EpisodeInfo, AnimeInfo, Language, VideoSource, EpisodeDownloadInfo

logger = logging.getLogger(__name__)


class CloudflareBypassScraper:
    """
    Cloudscraper-based scraper with automatic browser fallback.
    """
    
    def __init__(self, proxy_url: Optional[str] = None):
        self.proxy_url = proxy_url or settings.proxy_url
        self._cloudscraper = self._create_cloudscraper()
        self._browser_scraper = None
    
    def _create_cloudscraper(self):
        """Create cloudscraper session."""
        session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        session.headers.update({
            'User-Agent': settings.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        if self.proxy_url:
            session.proxies = {'http': self.proxy_url, 'https': self.proxy_url}
        return session
    
    def _get_browser_scraper(self):
        """Lazy-load browser scraper."""
        if self._browser_scraper is None:
            from app.services.browser_scraper import BrowserScraper
            self._browser_scraper = BrowserScraper(proxy_url=self.proxy_url)
        return self._browser_scraper

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, ConnectionError, TimeoutError))
    )
    def _cloudscraper_get(self, url: str) -> BeautifulSoup:
        """Fetch with cloudscraper."""
        response = self._cloudscraper.get(url, timeout=settings.request_timeout)
        response.raise_for_status()
        
        # Check for Cloudflare challenge
        if 'challenge-platform' in response.text or 'Cloudflare' in response.text:
            if len(response.text) < 5000 and 'challenge' in response.text.lower():
                raise ConnectionError("Cloudflare challenge page detected")
        
        return BeautifulSoup(response.text, 'lxml')

    def _try_cloudscraper_first(self, func, *args, **kwargs):
        """
        Try cloudscraper first, fall back to browser on failure.
        """
        try:
            return func(*args, **kwargs)
        except (ConnectionError, httpx.HTTPError, TimeoutError) as e:
            logger.warning(f"Cloudscraper failed ({type(e).__name__}: {e}), falling back to browser...")
            browser = self._get_browser_scraper()
            # Call the equivalent browser method
            browser_func = getattr(browser, func.__name__)
            return browser_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Unexpected error in cloudscraper: {e}")
            # Try browser as last resort
            browser = self._get_browser_scraper()
            browser_func = getattr(browser, func.__name__)
            return browser_func(*args, **kwargs)

    def parse_anime_page(self, url: str, language: Language = Language.sub, season: str = "all") -> AnimeInfo:
        """Parse anime page with automatic fallback."""
        return self._try_cloudscraper_first(self._parse_anime_page_cloudscraper, url, language, season)

    def _parse_anime_page_cloudscraper(self, url: str, language: Language = Language.sub, season: str = "all") -> AnimeInfo:
        """Original cloudscraper implementation."""
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
        
        logger.info(f"Fetching anime page (cloudscraper): {filtered_url}")
        soup = self._cloudscraper_get(filtered_url)
        
        return self._parse_anime_html(soup, language)

    def _parse_anime_html(self, soup: BeautifulSoup, language: Language) -> AnimeInfo:
        """Parse anime info from HTML."""
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
        """Extract video sources with fallback."""
        return self._try_cloudscraper_first(self._extract_video_sources_cloudscraper, episode_url)

    def _extract_video_sources_cloudscraper(self, episode_url: str) -> List[VideoSource]:
        logger.info(f"Fetching episode page (cloudscraper): {episode_url}")
        soup = self._cloudscraper_get(episode_url)
        
        sources = []
        
        for video in soup.select('video source, video'):
            src = video.get('src') or video.get('data-src')
            if src:
                sources.append(VideoSource(quality=self._guess_quality(src), url=src, type=self._get_source_type(src)))
        
        for iframe in soup.select('iframe'):
            src = iframe.get('src') or iframe.get('data-src')
            if src and any(d in src for d in ['wcostream', 'vidstream', 'stream', 'embed']):
                sources.append(VideoSource(quality="Auto", url=src, type="embed"))
        
        for link in soup.select('a[href*=".mp4"], a[href*=".m3u8"], a[href*="download"], a[href*="dl."]'):
            href = link.get('href')
            if href:
                sources.append(VideoSource(quality=self._guess_quality(href), url=href, type=self._get_source_type(href)))
        
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                urls = re.findall(r'https?://[^\s"\']+\.(?:m3u8|mp4|webm)', script.string)
                for url in urls:
                    sources.append(VideoSource(quality=self._guess_quality(url), url=url, type=self._get_source_type(url)))
        
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
        """Get full download info with fallback."""
        try:
            sources = self.extract_video_sources(str(episode.url))
            return EpisodeDownloadInfo(episode=episode, video_sources=sources)
        except Exception as e:
            logger.error(f"Error extracting video sources for {episode.url}: {e}")
            return EpisodeDownloadInfo(episode=episode, video_sources=[], error=str(e))


# Singleton instance
scraper = CloudflareBypassScraper()