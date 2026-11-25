import os
from pathlib import Path
from functools import lru_cache
from typing import List, Set
import threading
import logging
from dotenv import load_dotenv

# Limit OpenMP/BLAS threads to prevent high RAM/CPU usage
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = "1"

# Load environment variables: root .env first, then backend/.env as fallback
root_env = Path(__file__).resolve().parent.parent / ".env"
backend_env = Path(__file__).resolve().parent / ".env"

if root_env.exists():
    load_dotenv(dotenv_path=root_env)
if backend_env.exists():
    load_dotenv(dotenv_path=backend_env)
load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """Application settings for Veridocs, configurable via environment variables."""

    def __init__(self):
        backend_dir = Path(__file__).resolve().parent

        # 1. Database & Persistence
        # Supports PostgreSQL (pgvector) and SQLite fallback
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{backend_dir / 'data' / 'veridocs.db'}").strip()
        self.DATA_DIR: Path = Path(os.getenv("DATA_DIR", str(backend_dir / "data"))).resolve()
        self.UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(backend_dir / "uploads"))).resolve()
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.DATABASE_PATH: str = str(self.DATA_DIR / "veridocs.db")

        # 2. Redis & Task Queue
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0").strip()
        self.QUEUE_NAME: str = os.getenv("QUEUE_NAME", "veridocs_tasks").strip()

        # 3. Parser & OCR Configuration
        self.PARSER_BACKEND: str = os.getenv("PARSER_BACKEND", "docling").strip().lower()
        self.OCR_FALLBACK: bool = os.getenv("OCR_FALLBACK", "true").lower() in ("true", "1", "yes")
        self.OCR_TEXT_LAYER_MIN_CHARS: int = int(os.getenv("OCR_TEXT_LAYER_MIN_CHARS", "50"))
        self.OCR_MIN_CONFIDENCE: float = float(os.getenv("OCR_MIN_CONFIDENCE", "0.6"))

        # 4. Universal OpenAI-compatible LLM configuration
        explicit_url = os.getenv("LLM_BASE_URL", "").strip()
        explicit_key = os.getenv("LLM_API_KEY", "").strip()
        explicit_model = os.getenv("LLM_MODEL", "").strip()

        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        ollama_url = os.getenv("OLLAMA_BASE_URL", "").strip()
        ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2").strip()

        if explicit_url:
            self.LLM_BASE_URL: str = explicit_url
            is_local = "localhost" in explicit_url or "127.0.0.1" in explicit_url
            self.LLM_API_KEY: str = explicit_key or openai_key or groq_key or ("not-needed" if is_local else "")
            self.LLM_MODEL: str = explicit_model or "default"
        elif groq_key:
            self.LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
            self.LLM_API_KEY: str = groq_key
            self.LLM_MODEL: str = explicit_model or "openai/gpt-oss-120b"
        elif openai_key:
            self.LLM_BASE_URL: str = "https://api.openai.com/v1"
            self.LLM_API_KEY: str = openai_key
            self.LLM_MODEL: str = explicit_model or openai_model
        elif ollama_url:
            self.LLM_BASE_URL: str = ollama_url.rstrip("/") + ("/v1" if not ollama_url.endswith("/v1") else "")
            self.LLM_API_KEY: str = explicit_key or "ollama"
            self.LLM_MODEL: str = explicit_model or ollama_model
        elif explicit_key:
            if explicit_key.startswith("gsk_"):
                self.LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
                self.LLM_MODEL: str = explicit_model or "openai/gpt-oss-120b"
            else:
                self.LLM_BASE_URL: str = "https://api.openai.com/v1"
                self.LLM_MODEL: str = explicit_model or "gpt-4o-mini"
            self.LLM_API_KEY: str = explicit_key
        else:
            self.LLM_BASE_URL: str = ""
            self.LLM_API_KEY: str = ""
            self.LLM_MODEL: str = explicit_model

        self.LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
        self.LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1000"))

        # 5. Embedding & Search
        self.EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
        self.CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "600"))
        self.CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "100"))
        self.TOP_K: int = int(os.getenv("TOP_K", "6"))

        # 6. Upload & page constraints
        self.MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "15"))
        self.MAX_PDF_PAGES: int = int(os.getenv("MAX_PDF_PAGES", "50"))
        self.ALLOWED_EXTENSIONS: Set[str] = {".pdf", ".txt", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".docx", ".doc"}

        # 7. Rate limiting constraints
        self.RATE_LIMIT_QUERY_PER_HOUR: int = int(os.getenv("RATE_LIMIT_QUERY_PER_HOUR", "20"))
        self.RATE_LIMIT_UPLOAD_PER_HOUR: int = int(os.getenv("RATE_LIMIT_UPLOAD_PER_HOUR", "10"))

        # 8. CORS
        raw_origins = (
            os.getenv("FRONTEND_ORIGIN") or os.getenv("CORS_ORIGINS") or "http://localhost:3000,http://127.0.0.1:3000"
        )
        self.CORS_ORIGINS: List[str] = [o.strip() for o in raw_origins.split(",") if o.strip()]

        # 9. Vision & Multimodal Configuration
        self.VISION_BASE_URL: str = os.getenv(
            "VISION_BASE_URL", self.LLM_BASE_URL or "https://api.openai.com/v1"
        ).strip()
        self.VISION_API_KEY: str = os.getenv("VISION_API_KEY", self.LLM_API_KEY).strip()
        self.VISION_MODEL: str = os.getenv("VISION_MODEL", "gpt-4o-mini").strip()
        self.MAX_VISION_PAGES_PER_DOC: int = int(os.getenv("MAX_VISION_PAGES_PER_DOC", "5"))
        self.MAX_VISION_TOKENS_PER_DOC: int = int(os.getenv("MAX_VISION_TOKENS_PER_DOC", "15000"))
        self.VISION_ENABLED: bool = os.getenv("VISION_ENABLED", "true").lower() in ("true", "1", "yes")
        self.VISION_DPI: int = int(os.getenv("VISION_DPI", "150"))

        # 10. Document Classification & Structured Schema Extraction
        self.EXTRACTION_MODEL: str = os.getenv("EXTRACTION_MODEL", self.LLM_MODEL or "gpt-4o-mini").strip()
        self.EXTRACTION_ENABLED: bool = os.getenv("EXTRACTION_ENABLED", "true").lower() in ("true", "1", "yes")

        # 11. Entity Extraction (GLiNER / Local Pattern NER)
        self.NER_MODEL: str = os.getenv("NER_MODEL", "urchade/gliner_small-v2.1").strip()
        self.NER_ENABLED: bool = os.getenv("NER_ENABLED", "true").lower() in ("true", "1", "yes")
        self.GLINER_ENABLED: bool = os.getenv("GLINER_ENABLED", "false").lower() in ("true", "1", "yes")

        # 12. NLI Verification Layer
        self.NLI_MODEL: str = os.getenv("NLI_MODEL", "cross-encoder/nli-deberta-v3-mini").strip()
        self.NLI_ENABLED: bool = os.getenv("NLI_ENABLED", "true").lower() in ("true", "1", "yes")

        # 13. Contract Comparison Configuration
        self.COMPARISON_SIMILARITY_THRESHOLD: float = float(os.getenv("COMPARISON_SIMILARITY_THRESHOLD", "0.72"))

        # 14. Anomaly Flags & Knowledge Graph Configuration
        self.FLAGS_ENABLED: bool = os.getenv("FLAGS_ENABLED", "true").lower() in ("true", "1", "yes")
        self.FLAG_ROUND_NUMBER_THRESHOLD: float = float(os.getenv("FLAG_ROUND_NUMBER_THRESHOLD", "1000.0"))
        self.FLAG_DUPLICATE_EMBEDDING_THRESHOLD: float = float(os.getenv("FLAG_DUPLICATE_EMBEDDING_THRESHOLD", "0.97"))
        self.GRAPH_MAX_RENDER_NODES: int = int(os.getenv("GRAPH_MAX_RENDER_NODES", "200"))
        self.GRAPH_RESOLUTION_SIMILARITY_THRESHOLD: float = float(
            os.getenv("GRAPH_RESOLUTION_SIMILARITY_THRESHOLD", "88.0")
        )

    def is_llm_configured(self) -> bool:
        """Check if an LLM is configured (either OpenAI key or custom/Ollama base URL)."""
        is_local = "localhost" in self.LLM_BASE_URL or "127.0.0.1" in self.LLM_BASE_URL
        return bool(self.LLM_BASE_URL and (self.LLM_API_KEY or is_local))

    @property
    def is_postgres(self) -> bool:
        """Return True if DATABASE_URL points to PostgreSQL."""
        return self.DATABASE_URL.startswith("postgresql://") or self.DATABASE_URL.startswith("postgres://")


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


def reload_settings() -> Settings:
    """Clear cached settings and re-instantiate Settings."""
    get_settings.cache_clear()
    return get_settings()


def get_model_registry() -> ModelRegistry:
    return ModelRegistry()
