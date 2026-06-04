"""Admin config storage — persists group→models→prompt mappings to Cosmos DB.

Data model: ONE Cosmos document per Entra group, with id ``group::{group_id}``
(container partition key ``/id``). Each document is a ``GroupModelConfig``:
a single Entra group mapped to many selectable models plus one system prompt.

Cosmos is the single source of truth. There is no in-memory fallback: if
Cosmos is not configured or unreachable, operations raise so the failure is
surfaced to the caller (and the admin UI) instead of being silently lost.
"""

from __future__ import annotations

import logging
from datetime import datetime

from backend.config import Settings, get_settings
from backend.models.schemas import AdminConfig, GroupModelConfig

logger = logging.getLogger(__name__)

# Document-id prefix that namespaces per-group config docs in the container.
_GROUP_DOC_PREFIX = "group::"


def _group_doc_id(group_id: str) -> str:
    return f"{_GROUP_DOC_PREFIX}{group_id}"


class AdminConfigStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._cosmos_client = None
        self._init_cosmos()

    def _init_cosmos(self) -> None:
        if not self._settings.cosmos_endpoint:
            raise RuntimeError(
                "COSMOS_ENDPOINT is not configured — admin config requires Cosmos DB."
            )

        from azure.cosmos.aio import CosmosClient

        if self._settings.cosmos_key:
            self._cosmos_client = CosmosClient(
                self._settings.cosmos_endpoint,
                credential=self._settings.cosmos_key,
            )
        else:
            from azure.identity.aio import DefaultAzureCredential

            self._cosmos_client = CosmosClient(
                self._settings.cosmos_endpoint,
                credential=DefaultAzureCredential(),
            )
        logger.info("Admin config Cosmos client initialized")

    def _container(self):
        db = self._cosmos_client.get_database_client(self._settings.cosmos_database)
        return db.get_container_client(self._settings.cosmos_admin_config_container)

    # ── Aggregate read (orchestrator / admin overview) ────────────────────

    async def get(self) -> AdminConfig:
        """Assemble the full admin config from all per-group documents."""
        groups = await self.list_groups()
        return AdminConfig(groups=groups)

    async def list_groups(self) -> list[GroupModelConfig]:
        container = self._container()
        query = "SELECT * FROM c WHERE STARTSWITH(c.id, @prefix)"
        params = [{"name": "@prefix", "value": _GROUP_DOC_PREFIX}]
        items = [item async for item in container.query_items(query=query, parameters=params)]
        groups = [GroupModelConfig(**item) for item in items]
        groups.sort(key=lambda g: g.group_name.lower())
        return groups

    # ── Per-group CRUD ────────────────────────────────────────────────────

    async def get_group(self, group_id: str) -> GroupModelConfig | None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        doc_id = _group_doc_id(group_id)
        container = self._container()
        try:
            item = await container.read_item(item=doc_id, partition_key=doc_id)
        except CosmosResourceNotFoundError:
            return None
        return GroupModelConfig(**item)

    async def save_group(self, config: GroupModelConfig) -> GroupModelConfig:
        if not config.group_id:
            raise ValueError("group_id is required to save a group config.")
        config.updated_at = datetime.utcnow()
        doc = config.model_dump(mode="json")
        doc["id"] = _group_doc_id(config.group_id)
        await self._container().upsert_item(doc)
        return config

    async def delete_group(self, group_id: str) -> None:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        doc_id = _group_doc_id(group_id)
        try:
            await self._container().delete_item(item=doc_id, partition_key=doc_id)
        except CosmosResourceNotFoundError:
            return


