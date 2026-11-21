"""
Universal OpenAI-compatible LLM service for Veridocs.
Works with any hosted OpenAI endpoint (OpenAI, Groq, DeepSeek, etc.) or local Ollama.
No external provider-specific SDK bloat.
"""

import os
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from openai import OpenAI

from config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Veridocs AI, a precise document intelligence assistant.
Your answers must be grounded strictly in the provided document context.
For every key factual statement, include a citation marker like [Page X] or [Page X: filename.pdf] referencing where in the document that information was found.
If the provided excerpts do not contain enough information to answer the question, state honestly that the information was not found in the uploaded documents. Do not speculate or invent facts."""


class LLMService:
    """Unified OpenAI-compatible LLM client driven by LLM_BASE_URL, LLM_API_KEY, LLM_MODEL."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.LLM_BASE_URL or "").strip()
        self.api_key = (api_key or settings.LLM_API_KEY or "").strip()
        self.model = (model or settings.LLM_MODEL or "gpt-4o-mini").strip()
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS

        self.client: Optional[OpenAI] = None
        if self.is_configured():
            try:
                self.client = OpenAI(
                    base_url=self.base_url or None,
                    api_key=self.api_key or "not-needed",
                    timeout=30.0,
                )
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                self.client = None

    def is_configured(self) -> bool:
        """Check if LLM credentials/endpoint are configured."""
        if not self.base_url and not self.api_key:
            return False
        # If localhost/ollama, api_key is optional
        if "localhost" in self.base_url or "127.0.0.1" in self.base_url:
            return True
        return bool(self.api_key)

    def _build_messages(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]] = None
    ) -> List[Dict[str, str]]:
        """Construct messages payload including system prompt, context chunks, and history."""
        context_parts = []
        for c in chunks:
            src = c.get("source_file", "Document")
            page = c.get("page", 1)
            text = c.get("text", "").strip()
            context_parts.append(f"--- [Document: {src} | Page {page}] ---\n{text}")

        context_str = "\n\n".join(context_parts)
        user_content = f"CONTEXT EXCERPTS:\n{context_str}\n\nQUESTION:\n{question}"

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if history:
            for msg in history[-6:]:
                role = msg.get("role", "user")
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": msg.get("content", "")})

        messages.append({"role": "user", "content": user_content})
        return messages

    def generate_answer(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Synchronously generate an answer using the configured LLM."""
        if not self.is_configured() or not self.client:
            raise ValueError(
                "No LLM configured. Please set LLM_BASE_URL and LLM_API_KEY in .env, or use the API Key button in the UI."
            )

        messages = self._build_messages(question, chunks, history)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise RuntimeError(f"LLM request failed: {str(e)}")

    async def generate_answer_stream(
        self,
        question: str,
        chunks: List[Dict[str, Any]],
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream answer tokens from the configured LLM."""
        if not self.is_configured() or not self.client:
            yield (
                "⚠️ **No LLM is configured.**\n\n"
                "To enable streaming answers, configure your credentials in `.env` or click the **API Key** button in the header:\n\n"
                "**Option A: Hosted (Groq / Together / DeepSeek / OpenAI-compatible)**\n"
                "```env\n"
                "LLM_BASE_URL=https://api.groq.com/openai/v1\n"
                "LLM_API_KEY=your_key_here\n"
                "LLM_MODEL=llama-3.3-70b-versatile\n"
                "```\n\n"
                "**Option B: Standard OpenAI**\n"
                "```env\n"
                "OPENAI_API_KEY=sk-your-openai-key\n"
                "```\n\n"
                "**Option C: Local Ollama (Zero cost, private)**\n"
                "```env\n"
                "OLLAMA_BASE_URL=http://localhost:11434/v1\n"
                "OLLAMA_MODEL=llama3.2\n"
                "```"
            )
            return

        messages = self._build_messages(question, chunks, history)
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            yield f"\n\n[Error from LLM provider: {str(e)}]"


def get_llm_service(
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMService:
    return LLMService(base_url=base_url, api_key=api_key, model=model)
