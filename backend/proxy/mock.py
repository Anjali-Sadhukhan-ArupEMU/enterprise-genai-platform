"""Mock model provider for local development without Azure OpenAI."""

from __future__ import annotations

import time
import asyncio
from collections.abc import AsyncIterator

from backend.models.schemas import (
    ModelProviderRequest,
    ModelProviderResponse,
    TokenUsage,
)
from backend.proxy.base import BaseModelProvider


class MockProvider(BaseModelProvider):
    """Echoes back user messages for local testing."""

    @property
    def provider_name(self) -> str:
        return "azure_openai"  # matches routing config provider name

    async def complete(self, request: ModelProviderRequest) -> ModelProviderResponse:
        start = time.perf_counter()
        last_msg = request.messages[-1]["content"] if request.messages else ""
        reply = f"[Mock Response] You said: {last_msg}"
        elapsed = (time.perf_counter() - start) * 1000
        return ModelProviderResponse(
            success=True,
            content=reply,
            model=request.model_id,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            latency_ms=elapsed,
        )

    async def stream(self, request: ModelProviderRequest) -> AsyncIterator[str]:
        last_msg = request.messages[-1]["content"] if request.messages else ""
        reply = f"[Mock Response] You said: {last_msg}"
        for word in reply.split(" "):
            yield word + " "
            await asyncio.sleep(0.05)

    async def health_check(self) -> bool:
        return True
