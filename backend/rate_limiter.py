"""
Thread-safe Token and Request Rate Limiter implementing sliding-window counters.
Protects downstream LLM providers from TPM/RPM rate limits and provides distributed
HTTP rate limiting for API endpoints backed by Redis with in-memory fallback.
"""

import time
import threading
import logging
from typing import List, Tuple, Optional, Dict
from fastapi import HTTPException, Request

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


class HttpRateLimiter:
    """
    Sliding window HTTP rate limiter supporting distributed Redis backend
    with automatic in-memory fallback for local development and single-node instances.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._history: Dict[str, List[float]] = {}
        self._last_cleanup = time.time()
        self._redis_client = None
        self._init_redis()

    def _init_redis(self):
        try:
            settings = get_settings()
            backend_url = getattr(settings, "CELERY_RESULT_BACKEND", None) or getattr(settings, "REDIS_URL", None)
            if backend_url and backend_url.startswith("redis://"):
                import redis
                client = redis.from_url(
                    backend_url,
                    socket_timeout=0.8,
                    socket_connect_timeout=0.8,
                )
                if client.ping():
                    self._redis_client = client
                    logger.info("HttpRateLimiter initialized with distributed Redis backend.")
        except Exception as e:
            logger.debug(f"HttpRateLimiter using in-memory mode: {e}")
            self._redis_client = None

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        # 1. Distributed Redis sliding window if available
        if self._redis_client is not None:
            try:
                redis_key = f"ratelimit:{key}"
                pipe = self._redis_client.pipeline()
                pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
                pipe.zcard(redis_key)
                pipe.zadd(redis_key, {str(now): now})
                pipe.expire(redis_key, int(window_seconds) + 10)
                _, count, _, _ = pipe.execute()
                return count < max_requests
            except Exception as e:
                logger.debug(f"Redis rate check failed, falling back to in-memory: {e}")
                self._redis_client = None

        # 2. Thread-safe in-memory sliding window fallback
        with self._lock:
            if now - self._last_cleanup > 300:
                expired_threshold = now - 3600
                keys_to_delete = [
                    k for k, timestamps in self._history.items()
                    if not timestamps or timestamps[-1] < expired_threshold
                ]
                for k in keys_to_delete:
                    del self._history[k]
                self._last_cleanup = now

            timestamps = self._history.setdefault(key, [])
            cutoff = now - window_seconds
            valid_timestamps = [t for t in timestamps if t > cutoff]
            self._history[key] = valid_timestamps

            if len(valid_timestamps) >= max_requests:
                return False

            valid_timestamps.append(now)
            return True

    def clear(self):
        """Reset rate limiter state (used in test fixtures)."""
        with self._lock:
            self._history.clear()
        if self._redis_client is not None:
            try:
                keys = self._redis_client.keys("ratelimit:*")
                if keys:
                    self._redis_client.delete(*keys)
            except Exception:
                pass


# Backward-compatible alias for existing tests and main.py
InMemoryRateLimiter = HttpRateLimiter
_http_rate_limiter = HttpRateLimiter()


def get_http_rate_limiter() -> HttpRateLimiter:
    return _http_rate_limiter


def enforce_rate_limit(request: Request, key_suffix: str, max_requests: int = 60, window_seconds: int = 60):
    """Check that the request rate is within limits."""
    settings = get_settings()
    if not settings.RATE_LIMITING_ENABLED:
        return
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown_client")
    )
    limiter_key = f"{client_ip}:{key_suffix}"
    if not _http_rate_limiter.check(limiter_key, max_requests=max_requests, window_seconds=window_seconds):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({max_requests} requests per {window_seconds}s).",
            headers={"Retry-After": str(window_seconds)}
        )
