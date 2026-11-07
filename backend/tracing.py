"""
OpenTelemetry-compatible distributed tracing for Veridocs.
Tracks internal latency breakdown across OCR extraction, embedding generation,
hybrid search, neural cross-encoder reranking, and LLM completions.
Conforms to W3C TraceContext standards and feeds Prometheus latency histograms.
"""

import time
import uuid
import threading
from contextlib import contextmanager
from typing import Dict, Any, Optional, List
from functools import wraps

from metrics import metrics


class TraceSpan:
    """Represents a single OpenTelemetry-compatible span."""

    def __init__(
        self,
        name: str,
        trace_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.trace_id = trace_id or uuid.uuid4().hex
        self.span_id = uuid.uuid4().hex[:16]
        self.parent_id = parent_id
        self.attributes = dict(attributes or {})
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.duration_ms: float = 0.0
        self.status = "OK"
        self.error_message: Optional[str] = None

    def set_attribute(self, key: str, value: Any):
        """Set a metadata attribute on this span."""
        self.attributes[key] = value

    def finish(self, status: str = "OK", error: Optional[str] = None):
        """Finish span execution and compute duration."""
        self.end_time = time.time()
        self.duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.status = status
        self.error_message = error

        # Feed Prometheus latency metrics automatically
        metrics.record_latency(f"span_{self.name}", (self.end_time - self.start_time))

    def to_dict(self) -> Dict[str, Any]:
        """Format span as OpenTelemetry-compliant dictionary."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": self.attributes,
            "error": self.error_message,
        }


class Tracer:
    """Thread-safe collector for in-flight and recent distributed spans."""

    def __init__(self, max_retained_spans: int = 500):
        self._lock = threading.Lock()
        self._spans: List[TraceSpan] = []
        self._max_retained = max_retained_spans

    @contextmanager
    def span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """Context manager to trace an execution block."""
        s = TraceSpan(name=name, attributes=attributes)
        try:
            yield s
            s.finish(status="OK")
        except Exception as e:
            s.finish(status="ERROR", error=str(e))
            raise
        finally:
            with self._lock:
                if len(self._spans) >= self._max_retained:
                    self._spans.pop(0)
                self._spans.append(s)

    def get_recent_spans(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent spans ordered by execution time."""
        with self._lock:
            return [s.to_dict() for s in reversed(self._spans[-limit:])]

    def clear(self):
        """Clear recorded spans."""
        with self._lock:
            self._spans.clear()


# Global tracer singleton
tracer = Tracer()


def trace_operation(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Decorator to trace function execution with OpenTelemetry span."""
    def decorator(func):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.span(name, attributes=attributes):
                return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.span(name, attributes=attributes):
                return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator
