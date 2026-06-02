"""Provider registry — single entry-point for all model providers.

New providers are registered once; the rest of the app accesses models
through this registry without knowing which SDK or endpoint is used.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from backend.models.schemas import ModelProviderRequest, ModelProviderResponse
from backend.proxy.base import BaseModelProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Maps provider names to BaseModelProvider instances."""

    def __init__(self) -> None:
        self._providers: dict[str, BaseModelProvider] = {}

    def register(self, provider: BaseModelProvider) -> None:
        self._providers[provider.provider_name] = provider
        logger.info("Registered model provider: %s", provider.provider_name)

    def get(self, provider_name: str) -> BaseModelProvider:
        provider = self._providers.get(provider_name)
        if not provider:
            raise ValueError(f"Unknown provider: {provider_name}")
        return provider

    async def complete(
        self, provider_name: str, request: ModelProviderRequest
    ) -> ModelProviderResponse:
        return await self.get(provider_name).complete(request)

    async def stream(
        self, provider_name: str, request: ModelProviderRequest
    ) -> AsyncIterator[str]:
        async for chunk in self.get(provider_name).stream(request):
            yield chunk

    async def health_check_all(self) -> dict[str, bool]:
        results: dict[str, bool] = {}
        for name, provider in self._providers.items():
            results[name] = await provider.health_check()
        return results

    @property
    def provider_names(self) -> list[str]:
        return list(self._providers.keys())
