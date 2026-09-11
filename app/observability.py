"""Structured logging + Prometheus metrics. Kept separate from main.py
so the wiring is easy to find/extend without touching app startup logic."""
from __future__ import annotations

import json
import logging
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_COUNTER = Counter(
    "http_requests_total", "Total HTTP requests handled", ["route", "method", "status"]
)
PIPELINE_LATENCY = Histogram(
    "pipeline_latency_seconds",
    "End-to-end pipeline latency (decode -> diarize -> embed -> ASR -> merge)",
    ["mode"],
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str) -> logging.Logger:
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    root.handlers = [handler]
    return logging.getLogger("meeting-speaker-adaptation")


def metrics_response() -> tuple[bytes, str]:
    """Returns (body, content_type) for the /metrics route."""
    return generate_latest(), CONTENT_TYPE_LATEST


class timed:
    """Small context manager: `with timed(PIPELINE_LATENCY, mode="batch"): ...`"""

    def __init__(self, histogram: Histogram, **labels):
        self._histogram = histogram.labels(**labels) if labels else histogram
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self._histogram.observe(time.perf_counter() - self._start)
