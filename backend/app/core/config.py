from pydantic_settings import BaseSettings
from typing import Optional, List
import json


class Settings(BaseSettings):
    app_name: str = "Wcoflix Downloader"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Scraping settings
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 2.0
    
    # Cloudflare bypass (optional - for residential proxies)
    proxy_url: Optional[str] = None
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # CORS - accept comma-separated or JSON array
    cors_origins: str = "*"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse cors_origins as comma-separated or JSON array."""
        val = self.cors_origins.strip()
        if not val:
            return []
        try:
            # Try JSON first
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        # Fall back to comma-separated
        return [v.strip() for v in val.split(",") if v.strip()]
    
    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()