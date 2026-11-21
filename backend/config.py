import os
from pathlib import Path
from functools import lru_cache
from typing import Optional
import threading
import logging
from dotenv import load_dotenv

# Limit OpenMP/BLAS threads to prevent high RAM/CPU usage on laptops
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = "1"

# Load environment variables
_backend_env = Path(__file__).resolve().parent / ".env"
if _backend_env.exists():
    load_dotenv(dotenv_path=_backend_env)
load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """Application settings for Veridocs."""

    def __init__(self):
        # OpenAI-compatible LLM configuration (hosted or local Ollama)
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "").strip()

        explicit_key = os.getenv("LLM_API_KEY", "").strip()
        explicit_url = os.getenv("LLM_BASE_URL", "").strip()
        explicit_model = os.getenv("LLM_MODEL", "").strip()

        if explicit_url:
            self.LLM_BASE_URL: str = explicit_url
            self.LLM_API_KEY: str = explicit_key or self.OPENAI_API_KEY or "not-needed"
            self.LLM_MODEL: str = explicit_model or "default"
        elif self.OPENAI_API_KEY:
            self.LLM_BASE_URL: str = "https://api.openai.com/v1"
            self.LLM_API_KEY: str = self.OPENAI_API_KEY
            self.LLM_MODEL: str = explicit_model or os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        elif self.OLLAMA_BASE_URL:
            self.LLM_BASE_URL: str = self.OLLAMA_BASE_URL.rstrip("/") + ("/v1" if not self.OLLAMA_BASE_URL.endswith("/v1") else "")
            self.LLM_API_KEY: str = explicit_key or "ollama"
            self.LLM_MODEL: str = explicit_model or os.getenv("OLLAMA_MODEL", "llama3.2").strip()
        else:
            # Check default local Ollama port
            self.LLM_BASE_URL: str = ""
            self.LLM_API_KEY: str = explicit_key
            self.LLM_MODEL: str = explicit_model

        self.LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
        self.LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1000"))

        # Embedding & search
        self.EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        self.CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
        self.CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))
        self.TOP_K: int = int(os.getenv("TOP_K", "5"))

        # Storage & persistence
        backend_dir = Path(__file__).resolve().parent
        self.UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(backend_dir / "uploads"))).resolve()
        self.DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(backend_dir / "data"))).resolve()
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.DATABASE_PATH: str = str(self.DATA_DIR / "veridocs.db")

        # Upload constraints
        self.MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
        self.ALLOWED_EXTENSIONS: set = {".pdf", ".txt"}

        # CORS
        origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
        self.CORS_ORIGINS: list = [o.strip() for o in origins if o.strip()]

    def is_llm_configured(self) -> bool:
        """Check if an LLM is configured (either OpenAI key or custom/Ollama base URL)."""
        return bool(self.LLM_BASE_URL and (self.LLM_API_KEY or "localhost" in self.LLM_BASE_URL or "127.0.0.1" in self.LLM_BASE_URL))


class ModelRegistry:
    """Thread-safe singleton for lazy-loading Fastembed embedding model."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ModelRegistry, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._embedding_model = None
        self._model_lock = threading.Lock()
        self._initialized = True

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            with self._model_lock:
                if self._embedding_model is None:
                    settings = get_settings()
                    logger.info(f"Loading Fastembed model: {settings.EMBEDDING_MODEL}...")
                    from fastembed import TextEmbedding
                    self._embedding_model = TextEmbedding(model_name=settings.EMBEDDING_MODEL)
                    logger.info("Fastembed model loaded successfully.")
        return self._embedding_model


@lru_cache()
def get_settings() -> Settings:
    return Settings()


def get_model_registry() -> ModelRegistry:
    return ModelRegistry()
