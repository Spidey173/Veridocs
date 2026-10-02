"""
Enhanced LLM Service for Veridocs.
Features: streaming responses, multi-turn conversations, structured citations,
document summarization, and suggested questions generation.
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, AsyncGenerator, Optional, Tuple

from config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Prompt Templates
# ──────────────────────────────────────────────

ANSWER_SYSTEM_PROMPT = """You are Veridocs, a highly accurate document intelligence assistant.
You answer questions based SOLELY on the provided context from uploaded documents.

RULES:
1. Only use information from the provided context.
2. Cite your sources using [Page X] notation inline with your answer.
3. If the answer is not in the context, say "I cannot find this information in the uploaded documents."
4. Be precise, thorough, and well-structured.
5. Use markdown formatting for clarity (bold, lists, headers where appropriate).
6. When multiple sources support a point, cite all of them.
"""

ANSWER_PROMPT_TEMPLATE = """Context from uploaded documents:

{context}

---

Question: {question}

Provide a comprehensive, well-cited answer based on the context above."""

MULTI_TURN_PROMPT_TEMPLATE = """Context from uploaded documents:

{context}

---

Conversation History:
{history}

Current Question: {question}

Provide a comprehensive, well-cited answer. Reference the conversation history for context if relevant."""

SUMMARY_PROMPT = """Analyze the following document content and provide a structured executive summary.

Document Content:
{content}

Provide your response as a JSON object with this exact structure:
{{
    "purpose": "Brief description of the document's main purpose (1-2 sentences)",
    "key_findings": ["Finding 1", "Finding 2", "Finding 3"],
    "risks": ["Risk 1", "Risk 2"],
    "conclusions": ["Conclusion 1", "Conclusion 2"]
}}

Be specific and draw directly from the content. If a category doesn't apply, use an empty list."""

QUESTIONS_PROMPT = """Based on the following document content, generate 10 highly relevant questions
that a reader would want to ask about this document.

Document Content:
{content}

Generate questions that:
1. Cover the most important topics in the document
2. Range from factual to analytical
3. Would help someone understand the document deeply
4. Are specific enough to be answered from the document

Return ONLY a JSON array of question strings, like:
["Question 1?", "Question 2?", ...]"""

SUMMARY_AND_QUESTIONS_PROMPT = """Analyze the following document content and provide both a structured executive summary and 6-8 relevant suggested questions.

Document Content:
{content}

Provide your response as a valid JSON object with this exact structure:
{{
    "purpose": "Brief description of the document's main purpose (1-2 sentences)",
    "key_findings": ["Finding 1", "Finding 2", "Finding 3"],
    "risks": ["Risk 1", "Risk 2"],
    "conclusions": ["Conclusion 1", "Conclusion 2"],
    "suggested_questions": ["Question 1?", "Question 2?", "Question 3?", "Question 4?", "Question 5?"]
}}

Be specific and draw directly from the content. If a category does not apply, use an empty list. Return ONLY the valid JSON object."""


# ──────────────────────────────────────────────
# LLM Service
# ──────────────────────────────────────────────

class FreeLLMService:
    """
    Multi-provider LLM service with streaming support.

    Supported providers:
    - 'google' : Google Gemini (free tier)
    - 'groq'   : Groq (fast inference)
    - 'openrouter': OpenRouter (many free models)
    - 'github' : GitHub Models
    """

    def __init__(self, provider: str = None, model: str = None):
        settings = get_settings()
        self.provider = (provider or settings.LLM_PROVIDER).lower()
        self.model = model
        self.settings = settings

        if self.provider == "google":
            import google.generativeai as genai
            api_key = settings.GOOGLE_API_KEY
            if not api_key:
                raise ValueError("GOOGLE_API_KEY environment variable not set")
            genai.configure(api_key=api_key)
            self.model = model or "gemini-2.5-flash"
            self.client = genai.GenerativeModel(self.model)

        elif self.provider == "groq":
            from groq import Groq
            api_key = settings.GROQ_API_KEY
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable not set")
            self.model = model or getattr(settings, "GROQ_MODEL", "qwen/qwen3.8-27b") or "qwen/qwen3.8-27b"
            self.client = Groq(api_key=api_key)

        elif self.provider == "openrouter":
            from openai import OpenAI
            api_key = settings.OPENROUTER_API_KEY
            if not api_key:
                raise ValueError("OPENROUTER_API_KEY environment variable not set")
            self.model = model or "deepseek/deepseek-r1:free"
            self.client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                default_headers={
                    "HTTP-Referer": "http://localhost:8000",
                    "X-Title": "Veridocs"
                }
            )

        elif self.provider == "github":
            from openai import OpenAI
            api_key = settings.GITHUB_TOKEN
            if not api_key:
                raise ValueError("GITHUB_TOKEN or GITHUB_API_KEY environment variable not set")
            self.model = model or "gpt-4o-mini"
            self.client = OpenAI(
                base_url="https://models.inference.ai.azure.com",
                api_key=api_key
            )

        else:
            raise ValueError(
                f"Unsupported provider: {self.provider}. "
                f"Choose 'google', 'groq', 'openrouter', or 'github'."
            )

    def _build_context(self, chunks: List[Dict]) -> str:
        """Build context string from retrieved chunks with metadata."""
        context_parts = []
        for c in chunks:
            source = c.get("source_file", "Document")
            section = c.get("section", "")
            section_str = f" | Section: {section}" if section else ""
            context_parts.append(
                f"[Page {c['page']} | {source}{section_str}]\n{c['text']}"
            )
        return "\n\n---\n\n".join(context_parts)

    def _build_history_str(self, history: List[Dict[str, str]]) -> str:
        """Format conversation history for prompt."""
        if not history:
            return ""
        parts = []
        for msg in history[-6:]:  # Keep last 6 messages for context window
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    # ──────────────────────────────
    # Standard (non-streaming) answer
    # ──────────────────────────────

    def generate_answer(
        self,
        question: str,
        context_chunks: List[Dict],
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Generate an answer using the selected provider."""
        context_text = self._build_context(context_chunks)

        if history:
            history_str = self._build_history_str(history)
            prompt = MULTI_TURN_PROMPT_TEMPLATE.format(
                context=context_text,
                history=history_str,
                question=question
            )
        else:
            prompt = ANSWER_PROMPT_TEMPLATE.format(
                context=context_text,
                question=question
            )

        if self.provider == "google":
            response = self.client.generate_content(
                [{"role": "user", "parts": [{"text": ANSWER_SYSTEM_PROMPT + "\n\n" + prompt}]}]
            )
            return response.text.strip()

        elif self.provider in ["groq", "openrouter", "github"]:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.settings.LLM_TEMPERATURE,
                max_tokens=self.settings.LLM_MAX_TOKENS
            )
            return response.choices[0].message.content.strip()

    # ──────────────────────────────
    # Streaming answer
    # ──────────────────────────────

    async def generate_answer_stream(
        self,
        question: str,
        context_chunks: List[Dict],
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Generate answer with token-by-token streaming.
        Yields individual text tokens.
        """
        context_text = self._build_context(context_chunks)

        if history:
            history_str = self._build_history_str(history)
            prompt = MULTI_TURN_PROMPT_TEMPLATE.format(
                context=context_text,
                history=history_str,
                question=question
            )
        else:
            prompt = ANSWER_PROMPT_TEMPLATE.format(
                context=context_text,
                question=question
            )

        if self.provider == "google":
            yield await self._stream_google(prompt)

        elif self.provider in ["groq", "openrouter", "github"]:
            async for token in self._stream_openai_compat(prompt):
                yield token

    async def _stream_google(self, prompt: str) -> str:
        """Stream from Google Gemini (uses generate_content with stream=True)."""
        try:
            response = self.client.generate_content(
                [{"role": "user", "parts": [{"text": ANSWER_SYSTEM_PROMPT + "\n\n" + prompt}]}],
                stream=True
            )
            full_text = ""
            for chunk in response:
                if chunk.text:
                    full_text += chunk.text
            return full_text
        except Exception as e:
            logger.error(f"Google streaming error: {e}")
            raise

    async def _stream_openai_compat(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream from OpenAI-compatible APIs (Groq, OpenRouter, GitHub)."""
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.settings.LLM_TEMPERATURE,
                max_tokens=self.settings.LLM_MAX_TOKENS,
                stream=True
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"Streaming error ({self.provider}): {e}")
            raise

    # ──────────────────────────────
    # Document analysis utilities
    # ──────────────────────────────

    def generate_summary(self, chunks: List[Dict]) -> Dict:
        """
        Generate an executive summary of the document.
        Returns structured summary dict.
        """
        # Use first ~15 chunks for summary to stay within context limits
        content_parts = []
        for c in chunks[:15]:
            content_parts.append(f"[Page {c['page']}] {c['text']}")
        content = "\n\n".join(content_parts)

        prompt = SUMMARY_PROMPT.format(content=content)

        try:
            if self.provider == "google":
                response = self.client.generate_content(prompt)
                raw = response.text.strip()
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=1000
                )
                raw = response.choices[0].message.content.strip()

            # Parse JSON response
            # Try to extract JSON from response (handle markdown code blocks)
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {
                    "purpose": raw[:500],
                    "key_findings": [],
                    "risks": [],
                    "conclusions": []
                }

        except json.JSONDecodeError:
            logger.warning("Failed to parse summary JSON, returning raw text")
            return {
                "purpose": raw[:500] if 'raw' in dir() else "Summary generation failed",
                "key_findings": [],
                "risks": [],
                "conclusions": []
            }
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            return {
                "purpose": "Unable to generate summary at this time.",
                "key_findings": [],
                "risks": [],
                "conclusions": []
            }

    def generate_suggested_questions(self, chunks: List[Dict]) -> List[str]:
        """Generate suggested questions based on document content."""
        content_parts = []
        for c in chunks[:10]:
            content_parts.append(f"[Page {c['page']}] {c['text']}")
        content = "\n\n".join(content_parts)

        prompt = QUESTIONS_PROMPT.format(content=content)

        try:
            if self.provider == "google":
                response = self.client.generate_content(prompt)
                raw = response.text.strip()
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=800
                )
                raw = response.choices[0].message.content.strip()

            # Parse JSON array
            json_match = re.search(r'\[.*\]', raw, re.DOTALL)
            if json_match:
                questions = json.loads(json_match.group())
                return [q for q in questions if isinstance(q, str)][:15]
            else:
                # Fallback: split by newlines
                return [line.strip().lstrip('0123456789.-) ') for line in raw.split('\n') if '?' in line][:10]

        except Exception as e:
            logger.error(f"Question generation error: {e}")
            return [
                "What is the main topic of this document?",
                "What are the key findings?",
                "Can you summarize the conclusions?",
                "What are the most important data points?",
                "Are there any risks or concerns mentioned?"
            ]

    def generate_summary_and_questions(self, chunks: List[Dict]) -> Tuple[Dict, List[str]]:
        """
        Generate both executive summary and suggested questions in a single LLM call.
        Eliminates duplicate round-trips and speeds up insights generation by 2x.
        """
        content_parts = []
        for c in chunks[:12]:
            content_parts.append(f"[Page {c['page']}] {c['text']}")
        content = "\n\n".join(content_parts)

        prompt = SUMMARY_AND_QUESTIONS_PROMPT.format(content=content)

        default_qs = [
            "What is the main topic of this document?",
            "What are the key findings or conclusions?",
            "Can you provide a brief summary?",
            "What are the most important data points?",
            "Are there any risks or concerns mentioned?",
        ]

        try:
            if self.provider == "google":
                response = self.client.generate_content(prompt)
                raw = response.text.strip()
            else:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1000
                )
                raw = response.choices[0].message.content.strip()

            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                summary = {
                    "purpose": parsed.get("purpose", ""),
                    "key_findings": parsed.get("key_findings", []),
                    "risks": parsed.get("risks", []),
                    "conclusions": parsed.get("conclusions", [])
                }
                questions = parsed.get("suggested_questions", [])
                if not questions or not isinstance(questions, list):
                    questions = default_qs
                return summary, [q for q in questions if isinstance(q, str)][:10]
            else:
                return {
                    "purpose": raw[:500],
                    "key_findings": [],
                    "risks": [],
                    "conclusions": []
                }, default_qs
        except Exception as e:
            logger.error(f"Unified insights generation error: {e}")
            return {
                "purpose": "Unable to generate summary at this time.",
                "key_findings": [],
                "risks": [],
                "conclusions": []
            }, default_qs


# Need re import for summary parsing
import re