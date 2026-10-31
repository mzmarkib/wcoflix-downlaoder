from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
from enum import Enum


class Language(str, Enum):
    sub = "sub"
    dub = "dub"
    all = "all"


class EpisodeInfo(BaseModel):
    title: str
    url: HttpUrl
    season: Optional[int] = None
    episode: Optional[int] = None
    language: Language
    quality: str = "FullHD"


class AnimeInfo(BaseModel):
    title: str
    cover_url: Optional[str] = None
    description: Optional[str] = None
    genres: List[str] = []
    episodes: List[EpisodeInfo] = []
    total_episodes: int = 0
    seasons: List[int] = []  # Detected seasons from the page


class ScrapeRequest(BaseModel):
    url: HttpUrl
    language: Language = Language.sub
    season: Optional[str] = "all"  # Dynamic: "all" or specific season number
    proxy_url: Optional[str] = None  # Optional per-request proxy override


class VideoSource(BaseModel):
    quality: str  # e.g., "1080p", "720p", "480p"
    url: HttpUrl
    type: str = "direct"  # direct, m3u8, mp4


class EpisodeDownloadInfo(BaseModel):
    episode: EpisodeInfo
    video_sources: List[VideoSource] = []
    error: Optional[str] = None


class BatchDownloadRequest(BaseModel):
    episodes: List[EpisodeDownloadInfo]
    format: str = "idm"  # idm, ab_downloader, txt, aria2


class BatchDownloadResponse(BaseModel):
    download_url: str
    filename: str
    content: str