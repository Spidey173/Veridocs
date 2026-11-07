"""
Thread-safe Token and Request Rate Limiter implementing a sliding-window counter.
Protects downstream LLM providers (Gemini, Groq, OpenAI, Anthropic) from TPM/RPM rate limits.
"""

import time
import threading
import logging
from typing import List, Tuple, Optional
from config import get_settings

logger = logging.getLogger(__name__)


class SlidingWindowTokenLimiter:
    """Sliding-window token and request rate limiter with proactive budgeting."""

    def __init__(self, max_tpm: Optional[int] = None, max_rpm: Optional[int] = None, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self.max_tpm = max_tpm
        self.max_rpm = max_rpm
        self._history: List[Tuple[float, int]] = []  # (timestamp, token_count)
        self._lock = threading.Lock()

    def _cleanup(self, now: float) -> None:
        """Evict events outside the current sliding window."""
        cutoff = now - self.window_seconds
        while self._history and self._history[0][0] <= cutoff:
            self._history.pop(0)

    def current_usage(self) -> Tuple[int, int]:
        """Return (current_tokens, current_requests) in the active window."""
        now = time.time()
        with self._lock:
            self._cleanup(now)
            total_tokens = sum(tokens for _, tokens in self._history)
            total_requests = len(self._history)
            return total_tokens, total_requests

    def can_consume(self, estimated_tokens: int = 1) -> bool:
        """Check if estimated tokens and 1 request fit within TPM/RPM limits without consuming."""
        settings = get_settings()
        max_tpm = self.max_tpm if self.max_tpm is not None else getattr(settings, "LLM_MAX_TPM", 30000)
        max_rpm = self.max_rpm if self.max_rpm is not None else getattr(settings, "LLM_MAX_RPM", 60)

        now = time.time()
        with self._lock:
            self._cleanup(now)
            current_tokens = sum(tokens for _, tokens in self._history)
            current_requests = len(self._history)

            if current_requests + 1 > max_rpm:
                logger.warning(f"Rate limiter: RPM capacity reached ({current_requests}/{max_rpm})")
                return False

            if current_tokens + estimated_tokens > max_tpm:
                logger.warning(f"Rate limiter: TPM capacity reached ({current_tokens + estimated_tokens}/{max_tpm})")
                return False

            return True

    def consume(self, estimated_tokens: int = 1) -> bool:
        """Attempt to consume tokens. Returns True if accepted, False if rate-limited."""
        settings = get_settings()
        max_tpm = self.max_tpm if self.max_tpm is not None else getattr(settings, "LLM_MAX_TPM", 30000)
        max_rpm = self.max_rpm if self.max_rpm is not None else getattr(settings, "LLM_MAX_RPM", 60)

        now = time.time()
        with self._lock:
            self._cleanup(now)
            current_tokens = sum(tokens for _, tokens in self._history)
            current_requests = len(self._history)

            if current_requests + 1 > max_rpm or current_tokens + estimated_tokens > max_tpm:
                return False

            self._history.append((now, estimated_tokens))
            return True

    def reset(self) -> None:
        """Clear all rate limit history (useful for tests)."""
        with self._lock:
            self._history.clear()


# Global singleton limiter for external LLM calls
_global_llm_token_limiter = SlidingWindowTokenLimiter()


def get_token_limiter() -> SlidingWindowTokenLimiter:
    """Return the global sliding-window LLM token limiter."""
    return _global_llm_token_limiter
