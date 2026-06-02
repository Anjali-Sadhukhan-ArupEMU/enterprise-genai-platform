"""Admin config storage — persists group-model-prompt mappings.

Falls back to in-memory store when Cosmos is not configured.
"""

from __future__ import annotations

import logging
from datetime import datetime

from backend.config import Settings, get_settings
from backend.models.schemas import AdminConfig

logger = logging.getLogger(__name__)


class AdminConfigStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._memory: AdminConfig | None = None
        self._cosmos_client = None

        if self._settings.cosmos_endpoint:
            self._init_cosmos()

    def _init_cosmos(self) -> None:
        try:
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
        except Exception:
            logger.warning("Cosmos DB unavailable for admin config — using in-memory")
            self._cosmos_client = None

    async def get(self) -> AdminConfig:
        if self._cosmos_client:
            return await self._cosmos_get()
        return self._memory or AdminConfig()

    async def save(self, config: AdminConfig) -> None:
        config.updated_at = datetime.utcnow()
        if self._cosmos_client:
            await self._cosmos_upsert(config)
        else:
            self._memory = config

    async def _cosmos_get(self) -> AdminConfig:
        try:
            db = self._cosmos_client.get_database_client(self._settings.cosmos_database)
            container = db.get_container_client("admin_config")
            item = await container.read_item(item="admin_config", partition_key="admin_config")
            return AdminConfig(**item)
        except Exception:
            return AdminConfig()

    async def _cosmos_upsert(self, config: AdminConfig) -> None:
        db = self._cosmos_client.get_database_client(self._settings.cosmos_database)
        container = db.get_container_client("admin_config")
        doc = config.model_dump(mode="json")
        doc["id"] = "admin_config"
        await container.upsert_item(doc)
