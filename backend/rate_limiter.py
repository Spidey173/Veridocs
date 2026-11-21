"""
Lightweight in-memory sliding window rate limiter for public demo abuse protection.
Tracks requests per IP per hour.
"""

import time
from collections import defaultdict
from typing import Dict, List, Optional
from config import get_settings


class SlidingWindowLimiter:
    def __init__(self):
        self._history: Dict[str, List[float]] = defaultdict(list)

    def check(self, key: str, max_requests: int, window_seconds: float = 3600.0) -> Optional[str]:
        """
        Check if request is allowed. Returns an error message if exceeded, or None if permitted.
        """
        now = time.time()
        cutoff = now - window_seconds

        # Filter out expired timestamps
        timestamps = [t for t in self._history[key] if t > cutoff]
        self._history[key] = timestamps

        if len(timestamps) >= max_requests:
            remaining = int(timestamps[0] + window_seconds - now)
            return f"Rate limit reached ({max_requests} requests per hour). Resets in {max(1, remaining // 60)} minutes. You can supply your own API key in the UI to bypass server limits."

        timestamps.append(now)
        return None

    def reset(self):
        self._history.clear()


_limiter = SlidingWindowLimiter()


def check_rate_limit(client_ip: str, action: str = "query", has_custom_key: bool = False) -> Optional[str]:
    """
    Check rate limit for client IP. Custom user keys bypass query rate limits.
    """
    if has_custom_key and action == "query":
        return None  # BYOK users are exempt from server query limits

    settings = get_settings()
    if action == "upload":
        limit = settings.RATE_LIMIT_UPLOAD_PER_HOUR
        return _limiter.check(f"upload:{client_ip}", max_requests=limit)
    else:
        limit = settings.RATE_LIMIT_QUERY_PER_HOUR
        return _limiter.check(f"query:{client_ip}", max_requests=limit)
