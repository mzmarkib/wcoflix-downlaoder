from pydantic_settings import BaseSettings
from typing import Optional


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
    
    # CORS
    cors_origins: list[str] = ["*"]
    
    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()