"""Azure OpenAI model provider implementation.

Uses the openai Python SDK configured for Azure endpoints.
Auth precedence (cheap-to-cost-aware):
  1. Managed Identity / DefaultAzureCredential — preferred everywhere
     (App Service / Container Apps / local dev with `az login`).
  2. API key — only if explicitly set (local dev fallback).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

from backend.config import Settings, get_settings
from backend.models.schemas import (
    ModelProviderRequest,
    ModelProviderResponse,
    TokenUsage,
)
from backend.proxy.base import BaseModelProvider

logger = logging.getLogger(__name__)

_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"


class AzureOpenAIProvider(BaseModelProvider):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

        use_mi = (
            self._settings.azure_openai_use_managed_identity
            or not self._settings.azure_openai_api_key
        )

        if use_mi:
            credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=False
            )
            token_provider = get_bearer_token_provider(
                credential, _COGNITIVE_SERVICES_SCOPE
            )
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self._settings.azure_openai_endpoint,
                azure_ad_token_provider=token_provider,
                api_version=self._settings.azure_openai_api_version,
            )
            logger.info("Azure OpenAI auth: Managed Identity (DefaultAzureCredential)")
        else:
            self._client = AsyncAzureOpenAI(
                azure_endpoint=self._settings.azure_openai_endpoint,
                api_key=self._settings.azure_openai_api_key,
                api_version=self._settings.azure_openai_api_version,
            )
            logger.info("Azure OpenAI auth: API key (dev fallback)")

        self._default_deployment = (
            self._settings.azure_openai_deployment or ""
        )

    def _resolve_deployment(self, model_id: str) -> str:
        return self._default_deployment or model_id

    @property
    def provider_name(self) -> str:
        return "azure_openai"

    async def complete(self, request: ModelProviderRequest) -> ModelProviderResponse:
        start = time.perf_counter()
        deployment = self._resolve_deployment(request.model_id)
        kwargs: dict[str, object] = {
            "model": deployment,
            "messages": request.messages,
            "temperature": request.temperature,
            "stream": False,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        try:
            response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
            elapsed = (time.perf_counter() - start) * 1000
            choice = response.choices[0]
            usage = response.usage
            return ModelProviderResponse(
                success=True,
                content=choice.message.content or "",
                model=response.model,
                usage=TokenUsage(
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    total_tokens=usage.total_tokens if usage else 0,
                ),
                latency_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            logger.exception("Azure OpenAI completion failed")
            return ModelProviderResponse(
                success=False,
                error=str(exc),
                latency_ms=elapsed,
            )

    async def stream(self, request: ModelProviderRequest) -> AsyncIterator[str]:
        deployment = self._resolve_deployment(request.model_id)
        kwargs: dict[str, object] = {
            "model": deployment,
            "messages": request.messages,
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        try:
            response = await self._client.chat.completions.create(**kwargs)  # type: ignore[arg-type]
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception:
            logger.exception("Azure OpenAI stream failed")
            yield "[ERROR] Model streaming failed."

    async def health_check(self) -> bool:
        deployment = self._default_deployment
        if not deployment:
            # No deployment configured — can't reliably probe; assume healthy
            # so router fallback logic isn't tripped during local dev.
            return True
        try:
            resp = await self._client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            return bool(resp.choices)
        except Exception:
            logger.warning("Azure OpenAI health check failed")
            return False
