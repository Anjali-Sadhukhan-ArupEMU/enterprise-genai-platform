"""Web grounding providers.

The orchestrator calls a `WebSearchProvider` *only* when the gate decides a
query needs fresh / external information (the "gated" pattern). Two providers:

* `BingGroundingProvider` — Grounding with Bing Search via an Azure AI Foundry
  connection. Used when `bing_grounding_connection_id` + `bing_grounding_endpoint`
  are configured. The standalone Bing Search APIs were retired (Aug 2025); this
  talks to the Foundry-hosted grounding tool. When not configured, it returns an
  empty citation list (logged) so a chat turn never breaks — there is no mock
  grounding data.

It returns a list of `Citation` (title/url/snippet). The orchestrator turns
those into a grounding system block and surfaces them to the UI.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from backend.config import Settings
from backend.models.schemas import Citation

logger = logging.getLogger(__name__)


class WebSearchError(RuntimeError):
    """Raised when a grounding call fails. The orchestrator degrades gracefully."""


class WebSearchProvider(ABC):
    """Common contract for all grounding providers."""

    name: str = "web_search"

    @abstractmethod
    async def search(self, query: str, *, count: int = 4) -> list[Citation]:
        """Return up to `count` sources for `query`. Never raises to the caller
        on routine failure — returns an empty list instead (logged)."""
        raise NotImplementedError


class BingGroundingProvider(WebSearchProvider):
    """Grounding with Bing Search via an Azure AI Foundry connection.

    Kept dependency-light: the Foundry agents SDK is imported lazily so the app
    boots without it when grounding is unconfigured. On any error this returns
    an empty list (logged) so a failed search never breaks a chat turn.
    """

    name = "bing_grounding"

    def __init__(self, settings: Settings) -> None:
        self._endpoint = settings.bing_grounding_endpoint
        self._connection_id = settings.bing_grounding_connection_id

    async def search(self, query: str, *, count: int = 4) -> list[Citation]:
        if not (self._endpoint and self._connection_id):
            logger.warning("BingGroundingProvider used without full configuration")
            return []
        try:
            return await self._search_impl(query, count)
        except Exception:  # pragma: no cover - network/SDK errors
            logger.exception("Bing grounding call failed")
            return []

    async def _search_impl(self, query: str, count: int) -> list[Citation]:
        # Lazy import — the azure-ai-* SDKs are optional at runtime.
        from azure.ai.agents.models import BingGroundingTool  # type: ignore
        from azure.ai.projects.aio import AIProjectClient  # type: ignore
        from azure.identity.aio import DefaultAzureCredential  # type: ignore

        async with DefaultAzureCredential() as credential, AIProjectClient(
            endpoint=self._endpoint, credential=credential
        ) as client:
            tool = BingGroundingTool(connection_id=self._connection_id, count=count)
            agent = await client.agents.create_agent(
                model="gpt-4o-mini",
                name="web-grounding",
                instructions=(
                    "Search the web and return only factual, cited results for the query."
                ),
                tools=tool.definitions,
            )
            thread = await client.agents.threads.create()
            await client.agents.messages.create(
                thread_id=thread.id, role="user", content=query
            )
            run = await client.agents.runs.create_and_process(
                thread_id=thread.id, agent_id=agent.id
            )
            if getattr(run, "status", None) == "failed":
                logger.warning(
                    "Bing grounding run failed: %s", getattr(run, "last_error", None)
                )
            citations = await self._extract_citations(client, thread.id, count)
            # Best-effort cleanup of the ephemeral agent.
            try:
                await client.agents.delete_agent(agent.id)
            except Exception:  # pragma: no cover
                pass
            return citations

    @staticmethod
    async def _extract_citations(client, thread_id, count: int) -> list[Citation]:  # type: ignore[no-untyped-def]
        # Read URL citation annotations off the assistant messages. The agents
        # SDK exposes them as `message.url_citation_annotations`; kept defensive
        # so a schema change degrades to "no citations" rather than raising.
        citations: list[Citation] = []
        seen: set[str] = set()
        try:
            messages = client.agents.messages.list(thread_id=thread_id)
            async for msg in messages:
                if getattr(msg, "role", None) != "assistant":
                    continue
                BingGroundingProvider._collect_from_message(msg, citations, seen, count)
                if len(citations) >= count:
                    break
        except Exception:  # pragma: no cover - SDK/schema variance
            logger.exception("Failed to parse Bing grounding citations")
        return citations[:count]

    @staticmethod
    def _collect_from_message(msg, citations, seen, count: int) -> None:  # type: ignore[no-untyped-def]
        for ann in getattr(msg, "url_citation_annotations", []) or []:
            uc = getattr(ann, "url_citation", None)
            url = getattr(uc, "url", "") if uc is not None else ""
            if not url or url in seen:
                continue
            seen.add(url)
            citations.append(
                Citation(
                    title=getattr(uc, "title", "") or url,
                    url=url,
                    snippet=getattr(ann, "text", "") or "",
                )
            )
            if len(citations) >= count:
                return


def build_web_search_provider(settings: Settings) -> WebSearchProvider:
    """Always use the real Bing grounding provider.

    When Bing is unconfigured it returns an empty citation list (logged) rather
    than mock data, so the gated web-search pipeline degrades gracefully.
    """
    if settings.bing_grounding_connection_id and settings.bing_grounding_endpoint:
        logger.info("Web grounding: using BingGroundingProvider")
    else:
        logger.warning(
            "Web grounding: Bing not configured — searches return no citations"
        )
    return BingGroundingProvider(settings)
