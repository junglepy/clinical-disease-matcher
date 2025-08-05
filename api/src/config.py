import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Конфигурация приложения"""
    
    # API settings
    port: int = 8002
    log_level: str = "INFO"
    architecture: str = "hybrid_bm25_llm"
    
    # LLM API settings
    openai_api_key: str
    openai_model: str = "gpt-4-turbo-preview"
    openai_temperature: float = 0.3
    openai_max_tokens: int = 2000
    openai_base_url: Optional[str] = None  # Для OpenRouter или Ollama
    
    # Baseline API
    baseline_api_url: str = "http://localhost:8000"
    baseline_timeout: int = 30
    
    # Ensembl settings
    ensembl_release: int = 106  # GRCh38
    ensembl_cache_dir: str = "/tmp/pyensembl"
    
    # Data paths
    genemap_path: str = "data/genemap2.txt"
    datasets_dir: str = "datasets"
    bm25_index_path: str = "data/bm25_index"
    
    # Search settings
    gene_weight: float = 0.6
    bm25_weight: float = 0.4
    conflict_penalty: float = 0.3
    
    # BM25 settings
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    bm25_gene_boost: float = 1.5
    max_search_queries: int = 5
    
    # LLM settings
    llm_retry_attempts: int = 3
    llm_retry_delay: float = 1.0
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> Settings:
    """Получить настройки приложения"""
    return Settings()


# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROMPTS_DIR = PROJECT_ROOT / "prompts"