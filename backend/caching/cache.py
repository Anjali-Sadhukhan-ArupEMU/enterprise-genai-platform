"""Semantic caching stub.

Phase 1: no-op (pass-through).
Phase 2: integrate APIM semantic caching or Redis embedding cache.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SemanticCache:
    """Placeholder for future semantic caching layer."""

    def __init__(self, redis_url: str = "") -> None:
        self._enabled = bool(redis_url)
        if self._enabled:
            logger.info("Semantic cache enabled (Redis)")
        else:
            logger.info("Semantic cache disabled — pass-through mode")

    async def get(self, prompt: str) -> str | None:
        """Look up a cached response for a semantically similar prompt."""
        if not self._enabled:
            return None
        # Phase 2: compute embedding, vector search in Redis
        return None

    async def set(self, prompt: str, response: str, ttl_seconds: int = 3600) -> None:
        """Cache a response for future similar prompts."""
        if not self._enabled:
            return
        # Phase 2: store embedding + response in Redis
