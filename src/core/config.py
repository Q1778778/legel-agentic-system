"""Configuration management for Legal Analysis System."""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator
import json


class Settings(BaseSettings):
    """Application settings with validation."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # Application
    app_name: str = Field(default="court-argument")
    app_env: str = Field(default="development")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    
    # API
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000)
    api_prefix: str = Field(default="/api/v1")
    
    # Supabase
    supabase_url: Optional[str] = Field(default=None)
    supabase_key: Optional[str] = Field(default=None)
    supabase_service_key: Optional[str] = Field(default=None)
    
    # Weaviate Vector DB
    weaviate_host: str = Field(default="weaviate")  # Docker service name
    weaviate_port: int = Field(default=8080)  # Docker internal port
    weaviate_url: str = Field(default="http://weaviate:8080")
    weaviate_api_key: Optional[str] = Field(default=None)
    weaviate_class_name: str = Field(default="ArgumentSegments")
    weaviate_vector_size: int = Field(default=1536)
    
    # Neo4j Graph DB
    neo4j_uri: str = Field(default="bolt://neo4j:7687")  # Use Docker service name
    neo4j_user: str = Field(default="neo4j")
    neo4j_password: str = Field(default="CourtSim2024!")  # Match docker-compose.fast.yml
    neo4j_database: str = Field(default="neo4j")
    
    # OpenAI / LLM
    openai_api_key: Optional[str] = Field(default=None)
    embedding_model: str = Field(default="text-embedding-3-small")
    llm_model: str = Field(default="gpt-4-turbo-preview")
    llm_temperature: float = Field(default=0.7)
    
    # Azure OpenAI (for NLWeb)
    azure_openai_api_key: Optional[str] = Field(default=None)
    azure_openai_endpoint: Optional[str] = Field(default=None)
    
    # Legal APIs
    courtlistener_api_key: Optional[str] = Field(default=None)
    cap_api_key: Optional[str] = Field(default=None)
    recap_api_key: Optional[str] = Field(default=None)
    govinfo_api_key: Optional[str] = Field(default=None)
    
    # Redis / Celery
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")
    
    # Security
    secret_key: str = Field(default="change-me-in-production")
    cors_origins: str = Field(default="http://localhost:3000")
    
    # Monitoring
    prometheus_port: int = Field(default=9090)
    enable_metrics: bool = Field(default=True)
    
    # Multi-tenancy
    default_tenant: str = Field(default="default")
    enable_multi_tenancy: bool = Field(default=False)
    
    # GraphRAG Parameters
    graphrag_max_hops: int = Field(default=2)
    graphrag_alpha: float = Field(default=0.4)  # Vector score weight
    graphrag_beta: float = Field(default=0.2)   # Judge match weight
    graphrag_gamma: float = Field(default=0.2)  # Citation overlap weight
    graphrag_delta: float = Field(default=0.1)  # Outcome boost weight
    graphrag_epsilon: float = Field(default=0.1)  # Issue hop distance weight
    
    # Retrieval Parameters
    retrieval_limit: int = Field(default=500)
    retrieval_top_k: int = Field(default=10)
    retrieval_timeout: int = Field(default=10)  # seconds
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string to list."""
        if isinstance(v, str):
            # Handle JSON array string
            if v.startswith('[') and v.endswith(']'):
                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    pass
            # Handle single URL or comma-separated URLs
            if ',' in v:
                return [url.strip() for url in v.split(',')]
            # Return as single-item list
            return v  # Keep as string, will be converted in get_cors_origins
        return v
    
    @property
    def weaviate_url_full(self) -> str:
        """Build full Weaviate URL from host and port."""
        return f"http://{self.weaviate_host}:{self.weaviate_port}"
    
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env.lower() == "production"
    
    def get_cors_origins(self) -> List[str]:
        """Get CORS origins as list."""
        if isinstance(self.cors_origins, str):
            try:
                return json.loads(self.cors_origins)
            except json.JSONDecodeError:
                return [self.cors_origins]
        return self.cors_origins


# Global settings instance
settings = Settings()