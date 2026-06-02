"""Telemetry and structured logging.

Configures OpenTelemetry tracing + structured logging for App Insights.
Falls back to console logging when App Insights is not configured.
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

logger = logging.getLogger("genai_platform")


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Silence noisy SDK loggers. DefaultAzureCredential intentionally probes
    # multiple credential sources and logs the unavailable ones at DEBUG — not
    # actual errors. The httpx/httpcore loggers spam request internals.
    for noisy in (
        "azure.identity",
        "azure.core.pipeline.policies.http_logging_policy",
        "httpx",
        "httpcore",
        "urllib3",
        "openai._base_client",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def setup_opentelemetry(connection_string: str | None = None) -> None:
    """Initialize OpenTelemetry with Azure Monitor exporter.

    Called at app startup if App Insights connection string is available.
    """
    if not connection_string:
        logger.info("No App Insights connection string — telemetry goes to console")
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=connection_string)
        logger.info("OpenTelemetry configured for Azure Monitor")
    except ImportError:
        logger.warning("azure-monitor-opentelemetry not installed — skipping")


class RequestMetrics:
    """Collects per-request metrics for dashboards."""

    def __init__(self) -> None:
        self._start: float = 0

    def start(self) -> None:
        self._start = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000

    def log_chat_request(
        self,
        user_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        success: bool,
    ) -> None:
        logger.info(
            "CHAT_REQUEST user=%s model=%s prompt_tokens=%d completion_tokens=%d "
            "latency_ms=%.1f success=%s",
            user_id,
            model,
            prompt_tokens,
            completion_tokens,
            latency_ms,
            success,
        )
