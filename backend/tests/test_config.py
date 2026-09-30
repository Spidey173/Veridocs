"""
Unit tests for config.py Settings and ModelRegistry.
"""

from unittest.mock import MagicMock, patch
import pytest

from config import Settings, get_settings, ModelRegistry, get_model_registry


class TestConfig:
    def test_default_settings(self):
        """Verify default configuration values."""
        settings = Settings()
        assert settings.APP_NAME == "Veridocs"
        assert settings.APP_VERSION == "2.0.0"
        assert settings.RETRIEVAL_INITIAL_K == 20
        assert settings.RETRIEVAL_FINAL_K == 5
        assert settings.BM25_WEIGHT == 0.3
        assert settings.DENSE_WEIGHT == 0.7
        assert settings.CHUNK_SIZE == 500
        assert settings.CHUNK_OVERLAP == 50
        assert settings.ALLOWED_EXTENSIONS == {".pdf", ".docx", ".txt"}
        assert settings.MAX_FILE_SIZE_MB == 50

    def test_settings_env_overrides(self, monkeypatch):
        """Verify settings pick up environment variable overrides on instantiation."""
        monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
        monkeypatch.setenv("MAX_SESSIONS", "50")
        monkeypatch.setenv("CHUNK_SIZE", "1000")
        monkeypatch.setenv("RERANKER_ENABLED", "false")
        monkeypatch.setenv("APP_NAME", "CustomVeridocs")

        settings = Settings()
        assert settings.LLM_TEMPERATURE == 0.7
        assert settings.MAX_SESSIONS == 50
        assert settings.CHUNK_SIZE == 1000
        assert settings.RERANKER_ENABLED is False
        assert settings.APP_NAME == "CustomVeridocs"

    def test_settings_singleton_cache(self):
        """Verify get_settings returns the same cached instance."""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_model_registry_singleton(self):
        """Verify ModelRegistry is a singleton."""
        r1 = ModelRegistry()
        r2 = ModelRegistry()
        r3 = get_model_registry()
        assert r1 is r2
        assert r2 is r3

    def test_reranker_disabled_returns_none(self, monkeypatch):
        """Verify reranker_model returns None when RERANKER_ENABLED is false."""
        registry = get_model_registry()
        settings = get_settings()
        monkeypatch.setattr(settings, "RERANKER_ENABLED", False)
        monkeypatch.setattr(registry, "_reranker_model", None)
        assert registry.reranker_model is None
