"""Application settings and configuration."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Application configuration class."""
    
    # Flask settings
    SECRET_KEY: str = os.getenv('SECRET_KEY', 'your-secret-key-here')
    DEBUG: bool = os.getenv('DEBUG', 'False').lower() == 'true'
    HOST: str = os.getenv('HOST', '0.0.0.0')
    PORT: int = int(os.getenv('PORT', 5000))
    
    # File paths
    LOGS_DIR: str = 'logs'
    EXPORTS_DIR: str = 'exports'
    STATIC_DIR: str = 'static'
    TEMPLATES_DIR: str = 'templates'
    
    # Journal data paths
    JOURNAL_5YEAR_FILE: str = 'data/journal_metrics/5year.json'
    JOURNAL_JCR_CAS_FILE: str = 'data/journal_metrics/jcr_cas_ifqb.json'
    
    # Application limits
    MAX_SEARCH_RESULTS: int = 500
    MAX_CONCURRENT_REQUESTS: int = 10
    REQUEST_TIMEOUT: int = 30
    
    # Cache settings
    CACHE_TIMEOUT: int = 3600  # 1 hour
    MAX_CACHE_SIZE: int = 1000
    
    # WebSocket settings
    WEBSOCKET_TIMEOUT: int = 60
    MAX_CONNECTIONS: int = 100
    
    # Export settings
    EXPORT_MAX_PAPERS: int = 1000
    EXPORT_TIMEOUT: int = 300  # 5 minutes
    
    # Text processing
    MAX_TEXT_LENGTH: int = 10000
    MIN_RELEVANCE_SCORE: float = 0.5
    
    # NLTK settings
    NLTK_DATA_PATH: Optional[str] = os.getenv('NLTK_DATA')
    
    @classmethod
    def validate(cls) -> bool:
        """Validate configuration settings."""
        required_dirs = [cls.LOGS_DIR, cls.EXPORTS_DIR]
        for directory in required_dirs:
            os.makedirs(directory, exist_ok=True)
        return True
    
    @classmethod
    def get_env_info(cls) -> dict:
        """Get environment information for debugging."""
        return {
            'debug': cls.DEBUG,
            'host': cls.HOST,
            'port': cls.PORT,
            'logs_dir': cls.LOGS_DIR,
            'exports_dir': cls.EXPORTS_DIR
        }

# Global config instance
config = Config()