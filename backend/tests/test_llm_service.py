"""
Unit tests for llm_service.py multi-provider gateway, prompt building, and response parsing.
"""

from unittest.mock import MagicMock, patch
import pytest

from llm_service import FreeLLMService
from config import get_settings


class TestLLMService:
    def test_unsupported_provider(self):
        """Verify initializing with unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            FreeLLMService(provider="invalid_provider")

    def test_missing_api_keys(self, monkeypatch):
        """Verify ValueError is raised when required API key is missing."""
        settings = get_settings()
        monkeypatch.setattr(settings, "GOOGLE_API_KEY", "")
        monkeypatch.setattr(settings, "GROQ_API_KEY", "")
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(settings, "GITHUB_TOKEN", "")

        with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
            FreeLLMService(provider="google")

        with pytest.raises(ValueError, match="GROQ_API_KEY"):
            FreeLLMService(provider="groq")

        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            FreeLLMService(provider="openrouter")

        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            FreeLLMService(provider="github")

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
        """Verify history formatting."""
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
        """Verify Groq/OpenRouter/GitHub provider answer generation."""
        service = FreeLLMService.__new__(FreeLLMService)
        service.provider = "groq"
        service.model = "llama-3.3-70b-versatile"
        service.settings = get_settings()
        service.client = MagicMock()

        mock_choice = MagicMock()
        mock_choice.message.content = "Answer from Groq."
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        service.client.chat.completions.create.return_value = mock_completion

        chunks = [{"page": 1, "text": "Context text"}]
        answer = service.generate_answer("Question", chunks)

        assert answer == "Answer from Groq."
        service.client.chat.completions.create.assert_called_once()

    def test_generate_summary_json(self):
        """Verify parsing structured summary JSON."""
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
        """Verify parsing suggested questions list."""
        service = FreeLLMService.__new__(FreeLLMService)
        service.provider = "groq"
        service.model = "llama-3.3-70b-versatile"
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
