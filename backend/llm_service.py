import json
import logging
import asyncio
import time
import re
from typing import List, Dict, AsyncGenerator, Optional, Tuple, Callable, Any

from config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ANSWER_SYSTEM_PROMPT = """You are Veridocs, a document assistant.
You answer questions based on the provided context from uploaded documents.

RULES:
1. Only use information from the provided context.
2. Cite your sources using [Page X] notation inline with your answer.
3. If the answer is not in the context, say "I cannot find this information in the uploaded documents."
4. Be precise and clear.
5. Use markdown formatting where appropriate.
"""

ANSWER_PROMPT_TEMPLATE = """Context from uploaded documents:

{context}

---

Question: {question}

Provide an answer based on the context above."""

MULTI_TURN_PROMPT_TEMPLATE = """Context from uploaded documents:

{context}

---

Conversation History:
{history}

Current Question: {question}

Provide an answer based on the context and conversation history."""

SUMMARY_PROMPT = """Analyze the following document content and provide a structured summary.

Document Content:
{content}

Provide your response as a JSON object with this exact structure:
{{
    "purpose": "Brief description of the document's main purpose (1-2 sentences)",
    "key_findings": ["Finding 1", "Finding 2", "Finding 3"],
    "risks": ["Risk 1", "Risk 2"],
    "conclusions": ["Conclusion 1", "Conclusion 2"]
}}

Return ONLY valid JSON."""

QUESTIONS_PROMPT = """Based on the following document content, generate 10 relevant questions about it.

Document Content:
{content}

Return ONLY a JSON array of question strings:
["Question 1?", "Question 2?", ...]"""

SUMMARY_AND_QUESTIONS_PROMPT = """Analyze the following document content and provide both a summary and 4-5 suggested questions.

Document Content:
{content}

Provide your response as a valid JSON object with this exact structure:
{{
    "purpose": "Brief description of the document's main purpose (1-2 sentences)",
    "key_findings": ["Finding 1", "Finding 2", "Finding 3"],
    "risks": ["Risk 1", "Risk 2"],
    "conclusions": ["Conclusion 1", "Conclusion 2"],
    "suggested_questions": ["Question 1?", "Question 2?", "Question 3?", "Question 4?"]
}}

Return ONLY valid JSON."""


class FreeLLMService:
    """Handles communication with LLM providers (Google, Groq, OpenRouter, GitHub)."""

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
        """Format retrieved chunks into a context string."""
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
        """Format conversation history into a string."""
        if not history:
            return ""
        parts = []
        for msg in history[-6:]:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    def generate_answer(
        self,
        question: str,
        context_chunks: List[Dict],
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Generate a complete answer to the question."""
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
            def _call_google():
                response = self.client.generate_content(
                    [{"role": "user", "parts": [{"text": ANSWER_SYSTEM_PROMPT + "\n\n" + prompt}]}]
                )
                return response.text.strip()
            return self._with_retry(_call_google)

        elif self.provider in ["groq", "openrouter", "github"]:
            def _call_openai_compat():
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
            return self._with_retry(_call_openai_compat)

    @staticmethod
    def _with_retry(func: Callable[[], Any], max_retries: int = 3, initial_delay: float = 0.5) -> Any:
        """Retry a function on temporary network or rate limit errors."""
        delay = initial_delay
        last_exception = None
        for attempt in range(max_retries):
            try:
                return func()
            except Exception as e:
                last_exception = e
                err_str = str(e).lower()
                is_transient = any(
                    term in err_str
                    for term in ["rate limit", "429", "timeout", "temporarily unavailable", "503", "connection reset", "econnreset"]
                )
                if not is_transient or attempt == max_retries - 1:
                    raise
                logger.warning(f"Temporary LLM error (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
        if last_exception:
            raise last_exception

    async def generate_answer_stream(
        self,
        question: str,
        context_chunks: List[Dict],
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """Stream the generated answer token-by-token."""
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
            async for token in self._stream_google(prompt):
                yield token

        elif self.provider in ["groq", "openrouter", "github"]:
            async for token in self._stream_openai_compat(prompt):
                yield token

    async def _stream_google(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream tokens from Google Gemini."""
        try:
            response = await asyncio.to_thread(
                self.client.generate_content,
                [{"role": "user", "parts": [{"text": ANSWER_SYSTEM_PROMPT + "\n\n" + prompt}]}],
                stream=True
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
                    await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"Google streaming error: {e}")
            raise

    async def _stream_openai_compat(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream tokens from OpenAI-compatible APIs."""
        try:
            stream = await asyncio.to_thread(
                self.client.chat.completions.create,
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
                    await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"Streaming error ({self.provider}): {e}")
            raise

    def generate_summary(self, chunks: List[Dict]) -> Dict:
        """Generate a summary of the document."""
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
            logger.warning("Failed to parse summary JSON")
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
        """Generate sample questions that can be answered by the document."""
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

            json_match = re.search(r'\[.*\]', raw, re.DOTALL)
            if json_match:
                questions = json.loads(json_match.group())
                return [q for q in questions if isinstance(q, str)][:15]
            else:
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
        """Generate both summary and sample questions in a single call."""
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
            logger.error(f"Insights generation error: {e}")
            return {
                "purpose": "Unable to generate summary at this time.",
                "key_findings": [],
                "risks": [],
                "conclusions": []
            }, default_qs
