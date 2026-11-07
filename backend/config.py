import os

# Limit thread pools to prevent high memory usage
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = "1"

from functools import lru_cache
from typing import Optional
import threading
import logging
import hashlib
import numpy as np
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        # API Keys & Endpoints for any LLM Provider
        self.GOOGLE_API_KEY: str = (os.getenv("GOOGLE_API_KEY", "") or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE", "") or os.getenv("google", "")).strip()
        self.GROQ_API_KEY: str = (os.getenv("GROQ_API_KEY", "")).strip()
        self.GROQ_MODEL: str = (os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")).strip()
        self.OPENAI_API_KEY: str = (os.getenv("OPENAI_API_KEY", "")).strip()
        self.OPENAI_MODEL: str = (os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip()
        self.ANTHROPIC_API_KEY: str = (os.getenv("ANTHROPIC_API_KEY", "")).strip()
        self.ANTHROPIC_MODEL: str = (os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")).strip()
        self.DEEPSEEK_API_KEY: str = (os.getenv("DEEPSEEK_API_KEY", "")).strip()
        self.DEEPSEEK_MODEL: str = (os.getenv("DEEPSEEK_MODEL", "deepseek-chat")).strip()
        self.MISTRAL_API_KEY: str = (os.getenv("MISTRAL_API_KEY", "")).strip()
        self.MISTRAL_MODEL: str = (os.getenv("MISTRAL_MODEL", "mistral-small-latest")).strip()
        self.OPENROUTER_API_KEY: str = (os.getenv("OPENROUTER_API_KEY", "")).strip()
        self.OPENROUTER_MODEL: str = (os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-r1:free")).strip()
        self.GITHUB_TOKEN: str = (os.getenv("GITHUB_TOKEN", "") or os.getenv("GITHUB_API_KEY", "") or os.getenv("GITHUB", "") or os.getenv("github", "")).strip()
        self.GITHUB_MODEL: str = (os.getenv("GITHUB_MODEL", "gpt-4o-mini")).strip()
        self.OLLAMA_BASE_URL: str = (os.getenv("OLLAMA_BASE_URL", "") or os.getenv("OLLAMA_HOST", "")).strip()
        self.OLLAMA_MODEL: str = (os.getenv("OLLAMA_MODEL", "llama3.2")).strip()
        self.LLM_BASE_URL: str = (os.getenv("LLM_BASE_URL", "") or os.getenv("CUSTOM_LLM_URL", "")).strip()
        self.LLM_API_KEY: str = (os.getenv("LLM_API_KEY", "")).strip()
        self.LLM_MODEL: str = (os.getenv("LLM_MODEL", "")).strip()

        # Dynamic LLM Provider selection (no hardcoded default)
        env_provider = os.getenv("LLM_PROVIDER", "").strip().lower()
        if env_provider:
            self.LLM_PROVIDER: str = env_provider
        else:
            # Auto-detect available provider from active credentials / endpoints
            if self.OPENAI_API_KEY:
                self.LLM_PROVIDER = "openai"
            elif self.ANTHROPIC_API_KEY:
                self.LLM_PROVIDER = "anthropic"
            elif self.DEEPSEEK_API_KEY:
                self.LLM_PROVIDER = "deepseek"
            elif self.GROQ_API_KEY:
                self.LLM_PROVIDER = "groq"
            elif self.GOOGLE_API_KEY:
                self.LLM_PROVIDER = "google"
            elif self.MISTRAL_API_KEY:
                self.LLM_PROVIDER = "mistral"
            elif self.OPENROUTER_API_KEY:
                self.LLM_PROVIDER = "openrouter"
            elif self.GITHUB_TOKEN:
                self.LLM_PROVIDER = "github"
            elif self.OLLAMA_BASE_URL:
                self.LLM_PROVIDER = "ollama"
            elif self.LLM_BASE_URL:
                self.LLM_PROVIDER = "custom"
            else:
                self.LLM_PROVIDER = "auto"
        self.LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
        self.LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "750"))

        # Embedding settings
        self.EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "64"))

        # Search settings
        self.RETRIEVAL_INITIAL_K: int = int(os.getenv("RETRIEVAL_INITIAL_K", "20"))
        self.RETRIEVAL_FINAL_K: int = int(os.getenv("RETRIEVAL_FINAL_K", "5"))
        self.BM25_WEIGHT: float = float(os.getenv("BM25_WEIGHT", "0.3"))
        self.DENSE_WEIGHT: float = float(os.getenv("DENSE_WEIGHT", "0.7"))
        self.RRF_K: int = int(os.getenv("RRF_K", "60"))

        # Re-ranker settings
        self.RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
        self.RERANKER_ENABLED: bool = (
            os.getenv("RERANKER_ENABLED", os.getenv("ENABLE_RERANKER", "false")).lower() == "true"
        )

        # Chunking settings
        self.CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
        self.CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

        # OCR settings
        self.OCR_ENABLED: bool = os.getenv("OCR_ENABLED", "false").lower() == "true"
        self.OCR_MIN_TEXT_LENGTH: int = int(os.getenv("OCR_MIN_TEXT_LENGTH", "30"))

        # Background processing settings
        self.CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0").strip()
        self.CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0").strip()
        self.CELERY_TASK_ALWAYS_EAGER: bool = os.getenv("CELERY_TASK_ALWAYS_EAGER", "false").lower() in ("true", "1", "yes")
        self.JOB_TIMEOUT_SECONDS: int = int(os.getenv("JOB_TIMEOUT_SECONDS", "3600"))
        self.ASYNC_WORKER_CONCURRENCY: int = int(os.getenv("ASYNC_WORKER_CONCURRENCY", "4"))

        # Database settings (PostgreSQL + pgvector)
        self.DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

        # Application settings
        self.APP_NAME: str = os.getenv("APP_NAME", "Veridocs")
        self.APP_VERSION: str = "1.0.0"
        self.MAX_SESSIONS: int = int(os.getenv("MAX_SESSIONS", "200"))
        self.MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
        self.ALLOWED_EXTENSIONS: set = {".pdf", ".docx", ".txt"}

        # File upload directory
        self.UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")

        # CORS allowed origins
        self.CORS_ORIGINS: list = [
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000"
            ).split(",")
            if origin.strip()
        ]

        # Environment & Auth mode
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
        self.AUTH_MODE: str = os.getenv(
            "AUTH_MODE", "demo" if self.ENVIRONMENT != "production" else "gateway"
        ).lower()

        # Security keys and headers
        self.AUTH_SECRET_KEY: str = os.getenv("AUTH_SECRET_KEY", "").strip()
        self.ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "").strip()
        self.REQUIRE_API_KEY: bool = os.getenv("REQUIRE_API_KEY", "false").lower() in ("true", "1", "yes")
        self.API_KEY: str = os.getenv("API_KEY", "").strip()
        self.TOKEN_EXPIRE_HOURS: int = int(os.getenv("TOKEN_EXPIRE_HOURS", "24"))
        self.GATEWAY_USER_HEADER: str = os.getenv("GATEWAY_USER_HEADER", "X-Consumer-Custom-ID")
        self.GATEWAY_ROLE_HEADER: str = os.getenv("GATEWAY_ROLE_HEADER", "X-Consumer-Role")
        self.GATEWAY_SHARED_SECRET: str = os.getenv("GATEWAY_SHARED_SECRET", "").strip()
        self.GATEWAY_SECRET_HEADER: str = os.getenv("GATEWAY_SECRET_HEADER", "X-Gateway-Secret")

        # Rate limiting
        self.RATE_LIMITING_ENABLED: bool = os.getenv("RATE_LIMITING_ENABLED", "true").lower() in ("true", "1", "yes")
        self.UPLOAD_RATE_LIMIT: int = int(os.getenv("UPLOAD_RATE_LIMIT", "60"))
        self.QUERY_RATE_LIMIT: int = int(os.getenv("QUERY_RATE_LIMIT", "180"))

        # Retention & cleanup
        self.RETENTION_HOURS: int = int(os.getenv("RETENTION_HOURS", "24"))
        self.AUTO_CLEANUP_ENABLED: bool = os.getenv("AUTO_CLEANUP_ENABLED", "true").lower() in ("true", "1", "yes")
        self.CLEANUP_INTERVAL_MINUTES: int = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "60"))

    def get_available_llm_providers(self) -> dict:
        """Return dict of available LLM providers based on configured credentials and endpoints."""
        return {
            "openai": bool(self.OPENAI_API_KEY),
            "anthropic": bool(self.ANTHROPIC_API_KEY),
            "deepseek": bool(self.DEEPSEEK_API_KEY),
            "groq": bool(self.GROQ_API_KEY),
            "google": bool(self.GOOGLE_API_KEY),
            "mistral": bool(self.MISTRAL_API_KEY),
            "openrouter": bool(self.OPENROUTER_API_KEY),
            "github": bool(self.GITHUB_TOKEN),
            "ollama": bool(self.OLLAMA_BASE_URL),
            "custom": bool(self.LLM_BASE_URL),
        }

    def validate_production_configuration(self):
        """Validate critical security settings in production."""
        is_prod = self.ENVIRONMENT == "production" or self.AUTH_MODE == "gateway"
        if is_prod:
            insecure_placeholders = {
                "veridocs-default-secret-key-change-in-production",
                "change-me",
                "secret",
                "password",
                "default",
            }
            if not self.AUTH_SECRET_KEY:
                raise RuntimeError(
                    "FATAL SECURITY CONFIGURATION: AUTH_SECRET_KEY is required in production/gateway mode "
                    "but was not set. Define a strong secret of at least 32 characters in your environment."
                )
            if len(self.AUTH_SECRET_KEY) < 32:
                raise RuntimeError(
                    f"FATAL SECURITY CONFIGURATION: AUTH_SECRET_KEY is too short ({len(self.AUTH_SECRET_KEY)} chars). "
                    "Production deployments require at least 32 characters for HMAC-SHA256 signing security."
                )
            if self.AUTH_SECRET_KEY.lower() in insecure_placeholders:
                raise RuntimeError(
                    "FATAL SECURITY CONFIGURATION: AUTH_SECRET_KEY is set to an insecure default placeholder. "
                    "You must provide a unique, random secret in production."
                )

            if self.ENVIRONMENT == "production":
                if not self.DATABASE_URL or not self.DATABASE_URL.strip():
                    raise RuntimeError(
                        "FATAL DATABASE CONFIGURATION: DATABASE_URL is required when ENVIRONMENT=production. "
                        "Multi-worker production nodes require a shared PostgreSQL + pgvector database. "
                        "Refusing to start in production with ephemeral in-memory storage to prevent worker divergence."
                    )

            if self.AUTH_MODE == "gateway":
                allow_unprotected = os.getenv("ALLOW_UNPROTECTED_GATEWAY_HEADERS", "false").lower() in ("true", "1", "yes")
                if not self.GATEWAY_SHARED_SECRET and not self.REQUIRE_API_KEY and not allow_unprotected:
                    raise RuntimeError(
                        "FATAL SECURITY CONFIGURATION: When AUTH_MODE=gateway in production, GATEWAY_SHARED_SECRET "
                        "(or REQUIRE_API_KEY=true) must be configured to verify that gateway identity headers "
                        f"({self.GATEWAY_USER_HEADER}) originate from an authentic gateway rather than directly from an "
                        "untrusted client. If network isolation (e.g. private VPC, ingress firewall) guarantees the "
                        "backend cannot be reached directly from the public internet, set ALLOW_UNPROTECTED_GATEWAY_HEADERS=true."
                    )


@lru_cache()
def get_settings() -> Settings:
    """Return the cached settings object."""
    return Settings()


class FastEmbeddingWrapper:
    """Local embedding wrapper using FastEmbed."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        if model_name == "all-MiniLM-L6-v2":
            model_name = "sentence-transformers/all-MiniLM-L6-v2"
        logger.info(f"Loading embedding model: {model_name}")
        from fastembed import TextEmbedding
        try:
            self._model = TextEmbedding(model_name=model_name, threads=1)
        except TypeError:
            self._model = TextEmbedding(model_name=model_name)

    def encode(self, texts, batch_size: int = 32, **kwargs):
        """Encode text into float32 numpy vectors."""
        if isinstance(texts, str):
            texts = [texts]
        embeddings = list(self._model.embed(texts, batch_size=batch_size))
        return np.array(embeddings, dtype=np.float32)


class DeterministicOfflineEmbedding:
    """Zero-dependency offline deterministic embedding generator for air-gapped/offline runtime."""

    def encode(self, texts, **kwargs):
        if isinstance(texts, str):
            texts = [texts]
        vectors = []
        for text in texts:
            seed = int(hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
            rng = np.random.RandomState(seed)
            vec = rng.randn(384).astype(np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)


class ModelRegistry:
    """Loads and caches models in memory."""

    _instance: Optional["ModelRegistry"] = None
    _embedding_model = None
    _reranker_model = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            with self._lock:
                if self._embedding_model is None:
                    settings = get_settings()
                    try:
                        self._embedding_model = FastEmbeddingWrapper(settings.EMBEDDING_MODEL)
                    except Exception as e:
                        logger.warning(
                            f"FastEmbed model load notice ({e}). Falling back to deterministic offline embedding engine."
                        )
                        self._embedding_model = DeterministicOfflineEmbedding()
        return self._embedding_model

    @property
    def reranker_model(self):
        if self._reranker_model is None:
            settings = get_settings()
            if not settings.RERANKER_ENABLED:
                return None
            with self._lock:
                if self._reranker_model is None:
                    if not settings.RERANKER_ENABLED:
                        return None
                    try:
                        try:
                            from fastembed.rerank.cross_encoder import TextCrossEncoder
                        except ImportError:
                            from fastembed import TextCrossEncoder
                        logger.info(f"Loading reranker model: {settings.RERANKER_MODEL}")
                        try:
                            self._reranker_model = TextCrossEncoder(model_name=settings.RERANKER_MODEL, threads=1)
                        except TypeError:
                            self._reranker_model = TextCrossEncoder(model_name=settings.RERANKER_MODEL)
                    except Exception as e:
                        logger.warning(f"Reranker unavailable: {e}")
                        return None
        return self._reranker_model


def get_model_registry() -> ModelRegistry:
    """Return the global ModelRegistry singleton."""
    return ModelRegistry()
