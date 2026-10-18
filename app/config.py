"""
Application configuration for BlastRadius Agent.
"""
from pydantic_settings import BaseSettings
from typing import Optional

from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "BlastRadius Agent"
    APP_ENV: str = "development"
    DEBUG: bool = True
    
    # FalkorDB settings
    FALKORDB_HOST: str = "127.0.0.1"
    FALKORDB_PORT: int = 6379
    FALKORDB_PASSWORD: Optional[str] = None
    FALKORDB_GRAPH_NAME: str = "blast_radius"
    ALLOW_MEMORY_FALLBACK: bool = True
    
    # LLM Settings (via LiteLLM)
    LLM_MODEL: str = "gemini/gemini-2.5-flash"  # or gpt-4o-mini, claude-3-5-sonnet, ollama/llama3
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    
    # Simulation / Safety settings
    DEFAULT_REMEDIATION_MODE: str = "approval"  # "observe", "approval", "simulation"
    MAX_TRAVERSAL_HOPS: int = 4

settings = Settings()
