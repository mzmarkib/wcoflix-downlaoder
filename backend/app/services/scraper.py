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


class WcoflixScraper:
    def __init__(self):
        self.session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'mobile': False
            }
        )
        self.session.headers.update({
            'User-Agent': settings.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        if settings.proxy_url:
            self.session.proxies = {'http': settings.proxy_url, 'https': settings.proxy_url}

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPError, ConnectionError, TimeoutError))
    )
    def _get(self, url: str) -> BeautifulSoup:
        response = self.session.get(url, timeout=settings.request_timeout)
        response.raise_for_status()
        
        # Check if we hit Cloudflare challenge
        if 'challenge-platform' in response.text or 'Cloudflare' in response.text:
            # Check if it's actually the challenge page (not the real content)
            if len(response.text) < 5000 and 'challenge' in response.text.lower():
                raise ConnectionError("Cloudflare challenge page detected")
        
        return BeautifulSoup(response.text, 'lxml')

    def parse_anime_page(self, url: str, language: Language = Language.sub, season: str = "all") -> AnimeInfo:
        """Parse the main anime page to extract episode list."""
        # Build the filtered URL
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        # Add query parameters
        params = []
        if season != "all":
            params.append(f"season={season}")
        if language != Language.all:
            params.append(f"lang={language.value}")
        
        filtered_url = base_url
        if params:
            filtered_url += "?" + "&".join(params)
        
        logger.info(f"Fetching anime page: {filtered_url}")
        soup = self._get(filtered_url)
        
        # Extract anime title
        title_elem = soup.select_one('h1, h2, .anime-title, .entry-title')
        title = title_elem.get_text(strip=True) if title_elem else "Unknown Anime"
        
        # Extract cover image
        cover_elem = soup.select_one('img[src*="wcostream"], img[src*="catimg"], .anime-cover img, .poster img')
        cover_url = cover_elem.get('src') if cover_elem else None
        
        # Extract description
        desc_elem = soup.select_one('.anime-description, .entry-content, .description, .synopsis')
        description = desc_elem.get_text(strip=True) if desc_elem else None
        
        # Extract genres
        genre_elems = soup.select('a[href*="genre"], .genre a, .genres a')
        genres = [g.get_text(strip=True) for g in genre_elems]
        
        # Extract available seasons from the page
        detected_seasons = self._detect_seasons(soup)
        
        # Extract episode links
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
        """Detect available seasons from the page tabs/filters."""
        seasons = set()
        
        # Method 1: Look for season tabs/buttons
        season_tabs = soup.select('[data-season], .season-tab, .season-btn, .season-filter a, [href*="season="]')
        for tab in season_tabs:
            # Check data-season attribute
            data_season = tab.get('data-season')
            if data_season and data_season.isdigit():
                seasons.add(int(data_season))
            
            # Check href for season parameter
            href = tab.get('href', '')
            season_match = re.search(r'season[=-](\d+)', href)
            if season_match:
                seasons.add(int(season_match.group(1)))
            
            # Check text content
            text = tab.get_text(strip=True)
            season_match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
            if season_match:
                seasons.add(int(season_match.group(1)))
        
        # Method 2: Extract from episode URLs in the page
        episode_links = soup.select('a[href*="episode"]')
        for link in episode_links:
            href = link.get('href', '')
            season_match = re.search(r'season[_-]?(\d+)', href, re.IGNORECASE)
            if season_match:
                seasons.add(int(season_match.group(1)))
        
        # If no seasons detected, default to [1]
        if not seasons:
            seasons.add(1)
        
        return sorted(seasons)

    def _extract_episodes(self, soup: BeautifulSoup, language: Language) -> List[EpisodeInfo]:
        """Extract episode links from the anime page."""
        episodes = []
        
        # Find all episode links
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
            
            # Parse episode info from URL and link text
            text = link.get_text(strip=True)
            ep_info = self._parse_episode_info(full_url, text, language)
            if ep_info:
                episodes.append(ep_info)
        
        # Sort by season and episode number
        episodes.sort(key=lambda e: (e.season or 0, e.episode or 0))
        return episodes

    def _parse_episode_info(self, url: str, text: str, language: Language) -> Optional[EpisodeInfo]:
        """Parse episode information from URL and link text."""
        # URL patterns:
        # /the-apothecary-diaries-season-3-episode-5-english-subbed
        # /kusuriya-no-hitorigoto-season-2-episode-24-english-subbed
        # /the-apothecary-diaries-episode-24-english-dubbed (season 1, no season in URL)
        # /chibi-godzilla-raids-again-episode-119-english-subbed (no season)
        
        season_match = re.search(r'season[_-]?(\d+)', url, re.IGNORECASE)
        episode_match = re.search(r'episode[_-]?(\d+)', url, re.IGNORECASE)
        
        # Also try to extract from text
        if not season_match:
            season_match = re.search(r'Season\s+(\d+)', text, re.IGNORECASE)
        if not episode_match:
            episode_match = re.search(r'Episode\s+(\d+)', text, re.IGNORECASE)
        
        season = int(season_match.group(1)) if season_match else None
        episode = int(episode_match.group(1)) if episode_match else None
        
        # Determine language from URL/text
        ep_language = language
        if 'dubbed' in url.lower() or 'dubbed' in text.lower():
            ep_language = Language.dub
        elif 'subbed' in url.lower() or 'subbed' in text.lower():
            ep_language = Language.sub
        
        # Clean title
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
        """Extract video download links from an episode page."""
        logger.info(f"Fetching episode page: {episode_url}")
        soup = self._get(episode_url)
        
        sources = []
        
        # Method 1: Look for direct video sources in video tags
        for video in soup.select('video source, video'):
            src = video.get('src') or video.get('data-src')
            if src:
                quality = self._guess_quality(src)
                sources.append(VideoSource(quality=quality, url=src, type=self._get_source_type(src)))
        
        # Method 2: Look for iframes (embedded players)
        for iframe in soup.select('iframe'):
            src = iframe.get('src') or iframe.get('data-src')
            if src and any(domain in src for domain in ['wcostream', 'vidstream', 'stream', 'embed']):
                sources.append(VideoSource(quality="Auto", url=src, type="embed"))
        
        # Method 3: Look for download links
        for link in soup.select('a[href*=".mp4"], a[href*=".m3u8"], a[href*="download"], a[href*="dl."]'):
            href = link.get('href')
            if href:
                quality = self._guess_quality(href)
                sources.append(VideoSource(quality=quality, url=href, type=self._get_source_type(href)))
        
        # Method 4: Search for video URLs in JavaScript/JSON data
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                urls = re.findall(r'https?://[^\s"\']+\.(?:m3u8|mp4|webm)', script.string)
                for url in urls:
                    quality = self._guess_quality(url)
                    sources.append(VideoSource(quality=quality, url=url, type=self._get_source_type(url)))
        
        # Deduplicate
        seen = set()
        unique_sources = []
        for s in sources:
            if s.url not in seen:
                seen.add(s.url)
                unique_sources.append(s)
        
        return unique_sources

    def _guess_quality(self, url: str) -> str:
        """Guess video quality from URL."""
        url_lower = url.lower()
        if '1080' in url_lower or 'fullhd' in url_lower or 'fhd' in url_lower:
            return '1080p'
        elif '720' in url_lower or 'hd' in url_lower:
            return '720p'
        elif '480' in url_lower or 'sd' in url_lower:
            return '480p'
        return 'Auto'

    def _get_source_type(self, url: str) -> str:
        """Determine source type from URL."""
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


# Singleton instance
scraper = WcoflixScraper()