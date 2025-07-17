"""API configuration for external services."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class APIConfig:
    """Configuration for external API services."""
    
    # DeepSeek API
    DEEPSEEK_API_KEY: Optional[str] = os.getenv('DEEPSEEK_API_KEY')
    DEEPSEEK_API_URL: str = 'https://api.deepseek.com/v1/chat/completions'
    DEEPSEEK_MODEL: str = 'deepseek-chat'
    DEEPSEEK_MAX_TOKENS: int = 8000
    DEEPSEEK_TEMPERATURE: float = 0.7
    
    # Embedding API
    EMBEDDING_API_KEY: Optional[str] = os.getenv('EMBEDDING_API_KEY')
    EMBEDDING_API_URL: str = os.getenv('EMBEDDING_API_URL', 'https://api.openai.com/v1/embeddings')
    EMBEDDING_MODEL: str = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    EMBEDDING_DIMENSION: int = 1024 if 'bge-m3' in os.getenv('EMBEDDING_MODEL', '') else 1536
    
    # PubMed API
    PUBMED_API_URL: str = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'
    PUBMED_EMAIL: Optional[str] = os.getenv('PUBMED_EMAIL')
    PUBMED_API_KEY: Optional[str] = os.getenv('PUBMED_API_KEY')
    PUBMED_MAX_RESULTS: int = 500
    PUBMED_RETRIES: int = 3
    PUBMED_DELAY: float = 0.5  # seconds between requests
    
    # API Rate Limits
    DEEPSEEK_RPM: int = 60  # requests per minute
    EMBEDDING_RPM: int = 3000
    PUBMED_RPS: int = 10  # requests per second
    
    # Batch sizes
    EMBEDDING_BATCH_SIZE: int = 50  # 嵌入模型批量处理大小（优化为50篇提高效率）
    
    # Request settings
    REQUEST_TIMEOUT: int = 30  # 一般API请求超时
    DEEPSEEK_TIMEOUT: int = 360  # DeepSeek API超时，LLM生成需要更长时间
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0
    
    @classmethod
    def validate_api_keys(cls) -> dict:
        """Validate API keys and return status."""
        status = {
            'deepseek': bool(cls.DEEPSEEK_API_KEY),
            'embedding': bool(cls.EMBEDDING_API_KEY),
            'pubmed_email': bool(cls.PUBMED_EMAIL)
        }
        return status
    
    @classmethod
    def get_headers(cls, api_type: str) -> dict:
        """Get headers for API requests."""
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'NNScholar/1.0'
        }
        
        if api_type == 'deepseek' and cls.DEEPSEEK_API_KEY:
            headers['Authorization'] = f'Bearer {cls.DEEPSEEK_API_KEY}'
        elif api_type == 'embedding' and cls.EMBEDDING_API_KEY:
            headers['Authorization'] = f'Bearer {cls.EMBEDDING_API_KEY}'
        
        return headers
    
    @classmethod
    def get_pubmed_params(cls) -> dict:
        """Get PubMed API parameters."""
        params = {
            'retmax': cls.PUBMED_MAX_RESULTS,
            'retmode': 'xml',
            'tool': 'NNScholar',
            'version': '1.0'
        }
        
        if cls.PUBMED_EMAIL:
            params['email'] = cls.PUBMED_EMAIL
        if cls.PUBMED_API_KEY:
            params['api_key'] = cls.PUBMED_API_KEY
            
        return params

# Global API config instance
api_config = APIConfig()