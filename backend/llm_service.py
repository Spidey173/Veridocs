import json
import logging
import asyncio
import time
import re
from typing import List, Dict, AsyncGenerator, Optional, Tuple, Callable, Any

from config import get_settings
from tracing import tracer

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

SUPPORTED_PROVIDERS = {
    "openai",
    "anthropic",
    "deepseek",
    "groq",
    "google",
    "gemini",
    "mistral",
    "openrouter",
    "github",
    "ollama",
    "custom",
    "offline",
    "mock",
}

OPENAI_COMPAT_PROVIDERS = {
    "openai",
    "deepseek",
    "groq",
    "mistral",
    "openrouter",
    "github",
    "ollama",
    "custom",
}


class FreeLLMService:
    """Universal multi-provider LLM service supporting any LLM provider:
    - OpenAI (gpt-4o, gpt-4o-mini, o1, o3-mini)
    - Anthropic (Claude 3.5 Sonnet, Claude 3.5 Haiku)
    - DeepSeek (deepseek-chat, deepseek-reasoner)
    - Groq (llama-3.3-70b-versatile, mixtral-8x7b)
    - Google Gemini (gemini-2.5-flash, gemini-1.5-pro)
    - Ollama / Local (llama3.2, mistral, deepseek-r1 - no API key required)
    - Mistral AI (mistral-small, mistral-large)
    - OpenRouter (any model)
    - GitHub Models (gpt-4o, llama-3.1)
    - Custom / Any OpenAI-compatible endpoint (vLLM, LM Studio, Azure OpenAI)
    - Offline / Mock fallback (deterministic extractive Q&A when no external LLM is configured)
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        settings = get_settings()
        self.settings = settings

        # 1. Resolve provider (no forced default)
        chosen_provider = provider or settings.LLM_PROVIDER
        if not chosen_provider or chosen_provider.lower() in ("auto", "none"):
            available = settings.get_available_llm_providers()
            active_keys = [k for k, v in available.items() if v]
            if active_keys:
                chosen_provider = active_keys[0]
            else:
                chosen_provider = "offline"

        self.provider = chosen_provider.lower()
        if self.provider == "gemini":
            self.provider = "google"

        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider: {self.provider}. "
                f"Choose 'openai', 'groq', 'deepseek', 'google', 'anthropic', 'mistral', 'openrouter', 'github', 'ollama', 'custom', or 'offline'."
            )

        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.client = None

        # 2. Configure provider clients
        if self.provider == "google":
            import google.generativeai as genai
            key = api_key or settings.GOOGLE_API_KEY
            if not key:
                raise ValueError("GOOGLE_API_KEY environment variable not set")
            genai.configure(api_key=key)
            self.model = model or "gemini-2.5-flash"
            self.client = genai.GenerativeModel(self.model)

        elif self.provider == "anthropic":
            key = api_key or settings.ANTHROPIC_API_KEY
            if not key:
                raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=key)
                self.model = model or settings.ANTHROPIC_MODEL or "claude-3-5-haiku-20241022"
            except ImportError:
                raise ValueError("Anthropic library not installed. Install via: pip install anthropic")

        elif self.provider in OPENAI_COMPAT_PROVIDERS:
            from openai import OpenAI
            key = None
            endpoint = None
            default_model = "gpt-4o-mini"
            extra_headers = None

            if self.provider == "openai":
                key = api_key or settings.OPENAI_API_KEY
                if not key:
                    raise ValueError("OPENAI_API_KEY environment variable not set")
                endpoint = base_url or None
                default_model = settings.OPENAI_MODEL or "gpt-4o-mini"

            elif self.provider == "deepseek":
                key = api_key or settings.DEEPSEEK_API_KEY
                if not key:
                    raise ValueError("DEEPSEEK_API_KEY environment variable not set")
                endpoint = base_url or "https://api.deepseek.com"
                default_model = settings.DEEPSEEK_MODEL or "deepseek-chat"

            elif self.provider == "groq":
                key = api_key or settings.GROQ_API_KEY
                if not key:
                    raise ValueError("GROQ_API_KEY environment variable not set")
                endpoint = base_url or "https://api.groq.com/openai/v1"
                default_model = settings.GROQ_MODEL or "llama-3.3-70b-versatile"

            elif self.provider == "mistral":
                key = api_key or settings.MISTRAL_API_KEY
                if not key:
                    raise ValueError("MISTRAL_API_KEY environment variable not set")
                endpoint = base_url or "https://api.mistral.ai/v1"
                default_model = settings.MISTRAL_MODEL or "mistral-small-latest"

            elif self.provider == "openrouter":
                key = api_key or settings.OPENROUTER_API_KEY
                if not key:
                    raise ValueError("OPENROUTER_API_KEY environment variable not set")
                endpoint = base_url or "https://openrouter.ai/api/v1"
                default_model = settings.OPENROUTER_MODEL or "deepseek/deepseek-r1:free"
                extra_headers = {"HTTP-Referer": "http://localhost:8000", "X-Title": "Veridocs"}

            elif self.provider == "github":
                key = api_key or settings.GITHUB_TOKEN
                if not key:
                    raise ValueError("GITHUB_TOKEN or GITHUB_API_KEY environment variable not set")
                endpoint = base_url or "https://models.inference.ai.azure.com"
                default_model = settings.GITHUB_MODEL or "gpt-4o-mini"

            elif self.provider == "ollama":
                key = api_key or "ollama"
                endpoint = base_url or settings.OLLAMA_BASE_URL or "http://localhost:11434/v1"
                default_model = settings.OLLAMA_MODEL or "llama3.2"

            elif self.provider == "custom":
                endpoint = base_url or settings.LLM_BASE_URL
                if not endpoint:
                    raise ValueError("LLM_BASE_URL (or CUSTOM_LLM_URL) environment variable not set for custom provider")
                key = api_key or settings.LLM_API_KEY or "custom"
                default_model = settings.LLM_MODEL or "default"

            self.model = model or default_model
            self.client = OpenAI(
                base_url=endpoint,
                api_key=key,
                default_headers=extra_headers
            )

        elif self.provider in ("offline", "mock"):
            self.model = model or "offline-deterministic"
            self.client = None

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

    def _generate_offline_answer(self, question: str, chunks: List[Dict]) -> str:
        """Deterministic, extractive fallback answer generation without external API dependencies."""
        if not chunks:
            return "I cannot find this information in the uploaded documents."
        top_chunks = chunks[:3]
        sentences = []
        for c in top_chunks:
            p = c.get("page", 1)
            txt = c.get("text", "").strip()
            first_sentence = re.split(r'(?<=[.!?])\s+', txt)[0]
            if first_sentence:
                sentences.append(f"{first_sentence} [Page {p}]")
        if not sentences:
            return "I cannot find this information in the uploaded documents."
        return "Based on the uploaded documents: " + " ".join(sentences)

    async def _stream_offline(self, answer: str) -> AsyncGenerator[str, None]:
        """Stream offline answer tokens."""
        words = answer.split(" ")
        for i, word in enumerate(words):
            token = word + (" " if i < len(words) - 1 else "")
            yield token
            await asyncio.sleep(0.01)

    def _generate_offline_summary(self, chunks: List[Dict]) -> Dict:
        """Deterministic offline summary."""
        if not chunks:
            return {
                "purpose": "Document analysis summary.",
                "key_findings": ["Document processed successfully."],
                "risks": [],
                "conclusions": ["Ready for question answering and verification."]
            }
        first = chunks[0]
        title = first.get("source_file", "Uploaded Document")
        return {
            "purpose": f"Analysis and intelligence extracted from {title}.",
            "key_findings": [c.get("text", "")[:120].strip() for c in chunks[:3] if c.get("text")],
            "risks": ["Verify highlighted figures against underlying citations."],
            "conclusions": ["Document indexed and verified with coordinate visual grounding."]
        }

    def _generate_offline_questions(self, chunks: List[Dict]) -> List[str]:
        """Deterministic offline suggested questions."""
        questions = []
        for c in chunks[:4]:
            sec = c.get("section")
            if sec:
                questions.append(f"What are the details regarding {sec}?")
        if not questions:
            questions = [
                "What is the primary topic of this document?",
                "What are the key financial or operational figures reported?",
                "Are there any compliance or liability risks outlined?",
                "What are the conclusions or next steps specified?"
            ]
        return questions[:5]

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

        with tracer.span("llm.generate_answer", attributes={"provider": self.provider, "model": str(self.model), "chunk_count": len(context_chunks)}):
            if self.provider == "google":
                def _call_google():
                    response = self.client.generate_content(
                        [{"role": "user", "parts": [{"text": ANSWER_SYSTEM_PROMPT + "\n\n" + prompt}]}]
                    )
                    return response.text.strip()
                return self._with_retry(_call_google)

            elif self.provider == "anthropic":
                def _call_anthropic():
                    response = self.client.messages.create(
                        model=self.model,
                        system=ANSWER_SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=self.settings.LLM_TEMPERATURE,
                        max_tokens=self.settings.LLM_MAX_TOKENS
                    )
                    return response.content[0].text.strip()
                return self._with_retry(_call_anthropic)

            elif self.provider in OPENAI_COMPAT_PROVIDERS:
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

            elif self.provider in ("offline", "mock"):
                return self._generate_offline_answer(question, context_chunks)

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

        elif self.provider == "anthropic":
            async for token in self._stream_anthropic(prompt):
                yield token

        elif self.provider in OPENAI_COMPAT_PROVIDERS:
            async for token in self._stream_openai_compat(prompt):
                yield token

        elif self.provider in ("offline", "mock"):
            answer = self._generate_offline_answer(question, context_chunks)
            async for token in self._stream_offline(answer):
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

    async def _stream_anthropic(self, prompt: str) -> AsyncGenerator[str, None]:
        """Stream tokens from Anthropic Claude."""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.settings.LLM_MAX_TOKENS,
                system=ANSWER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.settings.LLM_TEMPERATURE
            ) as stream:
                for text in stream.text_stream:
                    yield text
                    await asyncio.sleep(0)
        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
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
        if self.provider in ("offline", "mock"):
            return self._generate_offline_summary(chunks)

        content_parts = []
        for c in chunks[:15]:
            content_parts.append(f"[Page {c['page']}] {c['text']}")
        content = "\n\n".join(content_parts)

        prompt = SUMMARY_PROMPT.format(content=content)

        try:
            if self.provider == "google":
                response = self.client.generate_content(prompt)
                raw = response.text.strip()
            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=1000
                )
                raw = response.content[0].text.strip()
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
        if self.provider in ("offline", "mock"):
            return self._generate_offline_questions(chunks)

        content_parts = []
        for c in chunks[:10]:
            content_parts.append(f"[Page {c['page']}] {c['text']}")
        content = "\n\n".join(content_parts)

        prompt = QUESTIONS_PROMPT.format(content=content)

        try:
            if self.provider == "google":
                response = self.client.generate_content(prompt)
                raw = response.text.strip()
            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=800
                )
                raw = response.content[0].text.strip()
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
        if self.provider in ("offline", "mock"):
            return self._generate_offline_summary(chunks), self._generate_offline_questions(chunks)

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
            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=1000
                )
                raw = response.content[0].text.strip()
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
