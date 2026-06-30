from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Search for .env in the backend dir, then project root (two levels up from app/)
_ENV_PATHS = [Path(__file__).parent.parent / ".env", Path(__file__).parent.parent.parent / ".env"]
_ENV_FILE = next((str(p) for p in _ENV_PATHS if p.exists()), ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # Required
    DATABASE_URL: str
    REDIS_URL: str
    JWT_SECRET_KEY: str
    ADMIN_KEY: str

    # Optional — only required when EMBEDDING_BACKEND=gemini or LLM_MODEL is a Gemini model
    GEMINI_API_KEY: str = ""

    # Optional
    JWT_EXPIRE_HOURS: int = 24
    VECTOR_BACKEND: str = "faiss"
    ALLOWED_ORIGINS: str = "*"
    FAISS_INDEX_PATH: str = "faiss_index"
    INPUT_DOCS_PATH: str = "input_docs"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    TOP_K_RESULTS: int = 5
    # Minimum normalized relevance score (0–1, higher = better) for a retrieved chunk
    # to be passed to the agent and cited as a source. Chunks below this are dropped,
    # so an off-topic query retrieves nothing instead of the k nearest weak matches.
    RELEVANCE_THRESHOLD: float = 0.5
    SESSION_TTL_SECONDS: int = 1800
    RATE_LIMIT: str = "30/minute"
    MAX_FILE_SIZE_MB: int = 2
    MAX_TENANT_STORAGE_MB: int = 10
    LOG_LEVEL: str = "INFO"
    LLM_MODEL: str = "gemini-2.5-flash"

    # Embedding backend: "huggingface" (default, free/local) or "gemini" (requires GEMINI_API_KEY)
    EMBEDDING_BACKEND: str = "huggingface"
    HF_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"  # used only when EMBEDDING_BACKEND=gemini

    # Phase 2B — Pinecone
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "rag-agent"

    # Phase 2C — Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "rag-agent"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]


settings = Settings()
