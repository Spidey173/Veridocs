"""
Centralized configuration for the Veridocs platform.
Singleton pattern for model loading and environment management.
"""

import os
# Constrain thread pools to 1 thread to prevent OOM crash on multi-core cloud containers
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = "1"

from functools import lru_cache
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        # === API Keys ===
        self.GOOGLE_API_KEY: str = (os.getenv("GOOGLE_API_KEY", "") or os.getenv("GOOGLE", "") or os.getenv("google", "")).strip()
        self.GROQ_API_KEY: str = (os.getenv("GROQ_API_KEY", "")).strip()
        self.GROQ_MODEL: str = (os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")).strip()
        self.OPENROUTER_API_KEY: str = (os.getenv("OPENROUTER_API_KEY", "")).strip()
        self.GITHUB_TOKEN: str = (os.getenv("GITHUB_TOKEN", "") or os.getenv("GITHUB_API_KEY", "") or os.getenv("GITHUB", "") or os.getenv("github", "")).strip()

        # === LLM Configuration ===
        _has_groq = bool(self.GROQ_API_KEY)
        _has_github = bool(self.GITHUB_TOKEN)
        _has_google = bool(self.GOOGLE_API_KEY)
        if _has_groq:
            _default_provider = "groq"
        elif _has_github and not _has_google:
            _default_provider = "github"
        else:
            _default_provider = "google"
        self.LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", _default_provider).lower()
        self.LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
        self.LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1500"))

        # === Embedding Configuration ===
        self.EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.EMBEDDING_BATCH_SIZE: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

        # === Retrieval Configuration ===
        self.RETRIEVAL_INITIAL_K: int = int(os.getenv("RETRIEVAL_INITIAL_K", "20"))
        self.RETRIEVAL_FINAL_K: int = int(os.getenv("RETRIEVAL_FINAL_K", "5"))
        self.BM25_WEIGHT: float = float(os.getenv("BM25_WEIGHT", "0.3"))
        self.DENSE_WEIGHT: float = float(os.getenv("DENSE_WEIGHT", "0.7"))
        self.RRF_K: int = int(os.getenv("RRF_K", "60"))

        # === Re-ranker Configuration ===
        self.RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
        self.RERANKER_ENABLED: bool = os.getenv("RERANKER_ENABLED", "true").lower() == "true"

        # === Chunking Configuration ===
        self.CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
        self.CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

        # === OCR Configuration ===
        self.OCR_ENABLED: bool = os.getenv("OCR_ENABLED", "false").lower() == "true"
        self.OCR_MIN_TEXT_LENGTH: int = int(os.getenv("OCR_MIN_TEXT_LENGTH", "30"))

        # === Application ===
        self.APP_NAME: str = os.getenv("APP_NAME", "Veridocs")
        self.APP_VERSION: str = "2.0.0"
        self.MAX_SESSIONS: int = int(os.getenv("MAX_SESSIONS", "200"))
        self.MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
        self.ALLOWED_EXTENSIONS: set = {".pdf", ".docx", ".txt"}

        # === Upload Storage ===
        self.UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")

        # === CORS ===
        self.CORS_ORIGINS: list = [
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS",
                "http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000,http://127.0.0.1:8000"
            ).split(",")
            if origin.strip()
        ]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings singleton."""
    return Settings()


# === Lightweight FastEmbed Wrapper ===

class FastEmbeddingWrapper:
    """
    Lightweight CPU embedding wrapper using FastEmbed (ONNX runtime).
    Zero PyTorch, zero CUDA, ~70MB RAM, 100% local, drop-in replacement for SentenceTransformer.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        import logging
        logger = logging.getLogger(__name__)
        if model_name == "all-MiniLM-L6-v2":
            model_name = "sentence-transformers/all-MiniLM-L6-v2"
        logger.info(f"Initializing FastEmbed ONNX model: {model_name}")
        from fastembed import TextEmbedding
        try:
            self._model = TextEmbedding(model_name=model_name, threads=1)
        except TypeError:
            self._model = TextEmbedding(model_name=model_name)
        logger.info("FastEmbed ONNX model loaded successfully (zero-torch, single-thread)")

    def encode(self, texts, batch_size: int = 32, **kwargs):
        """Encode text or list of texts into float32 numpy embeddings."""
        import numpy as np
        if isinstance(texts, str):
            texts = [texts]
        embeddings = list(self._model.embed(texts, batch_size=batch_size))
        return np.array(embeddings, dtype=np.float32)


# === Singleton Model Registry ===

class ModelRegistry:
    """
    Singleton registry for ML models to prevent re-loading.
    Models are loaded lazily on first access.
    """

    _instance: Optional["ModelRegistry"] = None
    _embedding_model = None
    _reranker_model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            import logging
            logger = logging.getLogger(__name__)
            settings = get_settings()
            try:
                self._embedding_model = FastEmbeddingWrapper(settings.EMBEDDING_MODEL)
            except ImportError:
                logger.info("FastEmbed not installed, falling back to SentenceTransformer...")
                try:
                    from sentence_transformers import SentenceTransformer
                    self._embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
                except Exception as e:
                    logger.error(f"Failed to load embedding model: {e}")
                    raise
        return self._embedding_model

    @property
    def reranker_model(self):
        if self._reranker_model is None:
            settings = get_settings()
            if not settings.RERANKER_ENABLED:
                return None
            try:
                from fastembed import TextCrossEncoder
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Loading FastEmbed CrossEncoder: {settings.RERANKER_MODEL}")
                try:
                    self._reranker_model = TextCrossEncoder(model_name=settings.RERANKER_MODEL, threads=1)
                except TypeError:
                    self._reranker_model = TextCrossEncoder(model_name=settings.RERANKER_MODEL)
                logger.info("FastEmbed CrossEncoder loaded successfully")
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Re-ranking disabled or model unavailable: {e}")
                return None
        return self._reranker_model


def get_model_registry() -> ModelRegistry:
    """Get the singleton model registry."""
    return ModelRegistry()
