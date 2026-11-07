"""
Comprehensive unit tests for llm_service.py:
- Universal multi-provider support (OpenAI, Anthropic, DeepSeek, Groq, Google, Ollama, Mistral, OpenRouter, GitHub, Custom, Offline)
- No forced/hardcoded default LLM; dynamic auto-detection
- Per-request overrides (provider, model, api_key, base_url)
- Offline extractive fallback when zero credentials configured
- Error handling with diagnostic guidance
- Context and conversation history construction
- Structured JSON summary and suggested questions parsing
"""

from unittest.mock import MagicMock, patch
import pytest

from llm_service import FreeLLMService
from config import get_settings, Settings


class TestUniversalLLMService:
    def test_unsupported_provider_raises_informative_error(self):
        """Verify initializing with unsupported provider raises ValueError with list of options."""
        with pytest.raises(ValueError, match="Unsupported provider: invalid_xyz"):
            FreeLLMService(provider="invalid_xyz")

    def test_no_default_llm_auto_detects_available_provider(self, monkeypatch):
        """Verify that when no provider is specified, it auto-detects from whichever key is present."""
        settings = get_settings()
        monkeypatch.setattr(settings, "LLM_PROVIDER", "auto")
        monkeypatch.setattr(settings, "GOOGLE_API_KEY", "")
        monkeypatch.setattr(settings, "GROQ_API_KEY", "")
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
        monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")
        monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "")
        monkeypatch.setattr(settings, "LLM_BASE_URL", "")

        # 1. When OpenAI key is present -> auto-selects openai
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test-openai")
        service_openai = FreeLLMService()
        assert service_openai.provider == "openai"
        assert service_openai.client is not None

        # 2. When Groq key is present -> auto-selects groq
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk-test-groq")
        service_groq = FreeLLMService()
        assert service_groq.provider == "groq"

        # 3. When DeepSeek key is present -> auto-selects deepseek
        monkeypatch.setattr(settings, "GROQ_API_KEY", "")
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "sk-test-deepseek")
        service_ds = FreeLLMService()
        assert service_ds.provider == "deepseek"

    def test_offline_fallback_when_zero_credentials_configured(self, monkeypatch):
        """Verify that when no provider is set and no API keys exist, it gracefully defaults to offline mode."""
        settings = get_settings()
        monkeypatch.setattr(settings, "LLM_PROVIDER", "auto")
        monkeypatch.setattr(settings, "GOOGLE_API_KEY", "")
        monkeypatch.setattr(settings, "GROQ_API_KEY", "")
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
        monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
        monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "")
        monkeypatch.setattr(settings, "LLM_BASE_URL", "")

        # Must not raise an error; should resolve to offline
        service = FreeLLMService()
        assert service.provider == "offline"
        assert service.model == "offline-deterministic"

        # Test offline answer generation
        chunks = [
            {"page": 1, "text": "Veridocs is an AI document assistant that verifies claims.", "source_file": "manual.pdf"},
            {"page": 2, "text": "It supports cross-document contradiction auditing.", "source_file": "manual.pdf"}
        ]
        answer = service.generate_answer("What is Veridocs?", chunks)
        assert "Veridocs is an AI document assistant" in answer
        assert "[Page 1]" in answer

    def test_explicit_missing_api_keys_raise_specific_errors(self, monkeypatch):
        """Verify ValueError is raised with the exact missing environment variable when explicitly requested."""
        settings = get_settings()
        monkeypatch.setattr(settings, "GOOGLE_API_KEY", "")
        monkeypatch.setattr(settings, "GROQ_API_KEY", "")
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
        monkeypatch.setattr(settings, "MISTRAL_API_KEY", "")
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "")
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")

        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            FreeLLMService(provider="google")

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            FreeLLMService(provider="openai")

        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            FreeLLMService(provider="groq")

        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
            FreeLLMService(provider="deepseek")

        with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
            FreeLLMService(provider="mistral")

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            FreeLLMService(provider="openrouter")

        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            FreeLLMService(provider="github")

        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            FreeLLMService(provider="anthropic")

    def test_per_request_api_key_override(self, monkeypatch):
        """Verify passing api_key in constructor overrides missing environment variables."""
        settings = get_settings()
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        monkeypatch.setattr(settings, "GROQ_API_KEY", "")

        # Providing api_key explicitly succeeds even if environment is blank
        service = FreeLLMService(provider="openai", api_key="sk-request-provided-key")
        assert service.provider == "openai"
        assert service.client.api_key == "sk-request-provided-key"

        service_groq = FreeLLMService(provider="groq", api_key="gsk-request-key")
        assert service_groq.provider == "groq"

    def test_ollama_local_requires_no_api_key(self):
        """Verify local Ollama provider initializes without any API key."""
        service = FreeLLMService(provider="ollama", base_url="http://localhost:11434/v1")
        assert service.provider == "ollama"
        assert service.model == "llama3.2"
        assert str(service.client.base_url) == "http://localhost:11434/v1/"

    def test_custom_openai_compatible_endpoint(self):
        """Verify custom provider configures any arbitrary OpenAI-compatible endpoint."""
        service = FreeLLMService(
            provider="custom",
            base_url="http://vllm-cluster.internal:8000/v1",
            api_key="internal-token",
            model="meta-llama/Llama-3-70B"
        )
        assert service.provider == "custom"
        assert service.model == "meta-llama/Llama-3-70B"
        assert "vllm-cluster.internal:8000" in str(service.client.base_url)

    def test_build_context(self):
        """Verify context string construction from chunks."""
        service = FreeLLMService.__new__(FreeLLMService)
        chunks = [
            {"page": 1, "text": "First page text", "source_file": "doc1.pdf", "section": "Intro"},
            {"page": 2, "text": "Second page text", "source_file": "doc1.pdf"},
        ]
        context = service._build_context(chunks)
        assert "[Page 1 | doc1.pdf | Section: Intro]" in context
        assert "First page text" in context
        assert "[Page 2 | doc1.pdf]" in context
        assert "Second page text" in context

    def test_build_history_str(self):
        """Verify conversation history formatting."""
        service = FreeLLMService.__new__(FreeLLMService)
        history = [
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is artificial intelligence."},
        ]
        history_str = service._build_history_str(history)
        assert "User: What is AI?" in history_str
        assert "Assistant: AI is artificial intelligence." in history_str

    def test_generate_answer_google(self):
        """Verify Google provider answer generation."""
        service = FreeLLMService.__new__(FreeLLMService)
        service.provider = "google"
        service.model = "gemini-2.5-flash"
        service.settings = get_settings()
        service.client = MagicMock()

        mock_resp = MagicMock()
        mock_resp.text = "Veridocs answers questions [Page 1]."
        service.client.generate_content.return_value = mock_resp

        chunks = [{"page": 1, "text": "Veridocs content", "source_file": "doc.pdf"}]
        answer = service.generate_answer("How does it work?", chunks)

        assert answer == "Veridocs answers questions [Page 1]."
        service.client.generate_content.assert_called_once()

    def test_generate_answer_openai_compatible(self):
        """Verify OpenAI-compatible provider answer generation (OpenAI, DeepSeek, Groq, Ollama, etc.)."""
        service = FreeLLMService.__new__(FreeLLMService)
        service.provider = "openai"
        service.model = "gpt-4o-mini"
        service.settings = get_settings()
        service.client = MagicMock()

        mock_choice = MagicMock()
        mock_choice.message.content = "Answer from OpenAI [Page 1]."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        service.client.chat.completions.create.return_value = mock_completion

        chunks = [{"page": 1, "text": "Context text"}]
        answer = service.generate_answer("Question", chunks)

        assert answer == "Answer from OpenAI [Page 1]."
        service.client.chat.completions.create.assert_called_once()

    def test_generate_answer_anthropic(self):
        """Verify Anthropic Claude message creation pattern."""
        service = FreeLLMService.__new__(FreeLLMService)
        service.provider = "anthropic"
        service.model = "claude-3-5-haiku-20241022"
        service.settings = get_settings()
        service.client = MagicMock()

        mock_text = MagicMock()
        mock_text.text = "Answer from Anthropic Claude [Page 2]."
        mock_resp = MagicMock()
        mock_resp.content = [mock_text]
        service.client.messages.create.return_value = mock_resp

        chunks = [{"page": 2, "text": "Claude context"}]
        answer = service.generate_answer("Question for Claude", chunks)

        assert answer == "Answer from Anthropic Claude [Page 2]."
        service.client.messages.create.assert_called_once()

    def test_generate_summary_json(self):
        """Verify parsing structured summary JSON from LLM response."""
        service = FreeLLMService.__new__(FreeLLMService)
        service.provider = "groq"
        service.model = "llama-3.3-70b-versatile"
        service.settings = get_settings()
        service.client = MagicMock()

        mock_choice = MagicMock()
        mock_choice.message.content = '```json\n{"purpose": "Doc Purpose", "key_findings": ["F1"], "risks": [], "conclusions": ["C1"]}\n```'
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        service.client.chat.completions.create.return_value = mock_completion

        summary = service.generate_summary([{"page": 1, "text": "text"}])
        assert summary["purpose"] == "Doc Purpose"
        assert summary["key_findings"] == ["F1"]
        assert summary["conclusions"] == ["C1"]

    def test_generate_suggested_questions(self):
        """Verify parsing suggested questions list from LLM response."""
        service = FreeLLMService.__new__(FreeLLMService)
        service.provider = "openai"
        service.model = "gpt-4o-mini"
        service.settings = get_settings()
        service.client = MagicMock()

        mock_choice = MagicMock()
        mock_choice.message.content = '["What is Veridocs?", "How to deploy?"]'
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        service.client.chat.completions.create.return_value = mock_completion

        questions = service.generate_suggested_questions([{"page": 1, "text": "text"}])
        assert len(questions) == 2
        assert "What is Veridocs?" in questions

    @pytest.mark.asyncio
    async def test_offline_streaming(self):
        """Verify offline token streaming produces tokens sequentially."""
        service = FreeLLMService(provider="offline")
        tokens = []
        chunks = [{"page": 1, "text": "Sample text for offline streaming."}]
        async for token in service.generate_answer_stream("What is this?", chunks):
            tokens.append(token)
        assert len(tokens) > 0
        full_text = "".join(tokens)
        assert "Sample text" in full_text
