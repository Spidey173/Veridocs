"""
Prometheus and OpenTelemetry-compatible metrics telemetry for Veridocs.
Tracks request throughput, latencies, LLM token invocations, vector searches, and session counts.
Exposes standard Prometheus exposition format without requiring heavy external client dependencies.
"""

import time
import threading
from typing import Dict, Tuple


class MetricsRegistry:
    """Thread-safe in-process metrics aggregator exposing standard Prometheus exposition format."""

    def __init__(self):
        self._lock = threading.Lock()
        # Counters: (name, label_tuple) -> count
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], int] = {}
        # Latency accumulators: (name, endpoint) -> (sum_seconds, count)
        self._latencies: Dict[str, Tuple[float, int]] = {}
        # Gauges
        self._gauges: Dict[str, float] = {}

    def inc_counter(self, name: str, labels: Dict[str, str], value: int = 1) -> None:
        """Increment a labeled counter metric."""
        label_key = tuple(sorted(labels.items()))
        key = (name, label_key)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + value

    def record_latency(self, endpoint: str, duration_seconds: float) -> None:
        """Record an endpoint execution duration."""
        with self._lock:
            total_time, count = self._latencies.get(endpoint, (0.0, 0))
            self._latencies[endpoint] = (total_time + duration_seconds, count + 1)

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value."""
        with self._lock:
            self._gauges[name] = value

    def export_prometheus(self) -> str:
        """Render metrics in Prometheus text exposition format (version 0.0.4)."""
        lines = [
            "# HELP veridocs_http_requests_total Total HTTP requests processed by endpoint and status.",
            "# TYPE veridocs_http_requests_total counter",
        ]

        with self._lock:
            # Output HTTP and general counters
            for (name, label_tuple), count in sorted(self._counters.items()):
                label_str = ",".join(f'{k}="{v}"' for k, v in label_tuple)
                if label_str:
                    lines.append(f"{name}{{{label_str}}} {count}")
                else:
                    lines.append(f"{name} {count}")

            lines.append("")
            lines.append("# HELP veridocs_http_request_duration_seconds Total time spent in HTTP requests by endpoint.")
            lines.append("# TYPE veridocs_http_request_duration_seconds summary")
            for endpoint, (total_time, count) in sorted(self._latencies.items()):
                lines.append(f'veridocs_http_request_duration_seconds_sum{{endpoint="{endpoint}"}} {total_time:.4f}')
                lines.append(f'veridocs_http_request_duration_seconds_count{{endpoint="{endpoint}"}} {count}')

            lines.append("")
            lines.append("# HELP veridocs_active_sessions Number of active sessions loaded in memory.")
            lines.append("# TYPE veridocs_active_sessions gauge")
            for name, val in sorted(self._gauges.items()):
                lines.append(f"{name} {val}")

        lines.append("")
        return "\n".join(lines)


# Global singleton metrics registry
metrics = MetricsRegistry()

