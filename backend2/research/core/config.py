"""Configuration management using pydantic-settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # API Keys
    anthropic_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None
    langsmith_api_key: Optional[str] = None
    
    # Model Configuration
    default_model: str = "claude-3-5-haiku-20241022"
    sonnet_model: str = "claude-3-5-sonnet-20241022"
    opus_model: str = "claude-3-opus-20240229"
    
    # Budget Configuration
    default_budget_usd: float = 3.0
    max_budget_usd: float = 5.0
    
    # Search Configuration
    tavily_max_results: int = 10
    tavily_news_days: int = 90
    
    # Cache Configuration
    cache_ttl_seconds: int = 300  # 5 minutes
    cache_dir: str = "~/.research/cache"
    
    # Development
    debug: bool = False
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
