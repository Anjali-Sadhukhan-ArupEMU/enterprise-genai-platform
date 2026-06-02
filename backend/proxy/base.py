"""Base model provider interface.

Every LLM provider (Azure OpenAI, Foundry, DeepSeek, etc.) implements
this ABC so the proxy layer can call any backend through a single contract.
"""

from __future__ import annotations

import abc
from collections.abc import AsyncIterator

from backend.models.schemas import ModelProviderRequest, ModelProviderResponse


class BaseModelProvider(abc.ABC):
    """Abstract base for all model provider adapters."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        ...

    @abc.abstractmethod
    async def complete(self, request: ModelProviderRequest) -> ModelProviderResponse:
        """Non-streaming completion."""
        ...

    @abc.abstractmethod
    async def stream(self, request: ModelProviderRequest) -> AsyncIterator[str]:
        """Streaming completion — yields content chunks."""
        ...

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider endpoint is reachable and healthy."""
        ...
