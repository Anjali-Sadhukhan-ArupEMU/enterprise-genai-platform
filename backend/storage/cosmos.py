"""Cosmos DB storage for conversations and sessions.

Uses azure-cosmos async client. Falls back to in-memory store
when Cosmos is not configured (local development).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from backend.config import Settings, get_settings
from backend.models.schemas import (
    ChatMessage,
    Conversation,
    ConversationSummary,
    PaginatedConversations,
)

logger = logging.getLogger(__name__)


class ConversationStore:
    """Abstract conversation persistence.

    Phase 1: in-memory dict (works without Cosmos).
    Production: swap _storage calls to azure.cosmos.aio.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._memory: dict[str, Conversation] = {}
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
                # Managed Identity
                from azure.identity.aio import DefaultAzureCredential

                self._cosmos_client = CosmosClient(
                    self._settings.cosmos_endpoint,
                    credential=DefaultAzureCredential(),
                )
            logger.info("Cosmos DB client initialized")
        except Exception:
            logger.warning("Cosmos DB unavailable — using in-memory store")
            self._cosmos_client = None

    async def get(self, conversation_id: str, user_id: str) -> Conversation | None:
        if self._cosmos_client:
            return await self._cosmos_get(conversation_id, user_id)
        return self._memory.get(conversation_id)

    async def save(self, conversation: Conversation) -> None:
        conversation.updated_at = datetime.utcnow()
        if self._cosmos_client:
            await self._cosmos_upsert(conversation)
        else:
            self._memory[conversation.id] = conversation

    async def delete(self, conversation_id: str, user_id: str) -> bool:
        if self._cosmos_client:
            return await self._cosmos_delete(conversation_id, user_id)
        return self._memory.pop(conversation_id, None) is not None

    async def list_for_user(
        self, user_id: str, page: int = 1, page_size: int = 20
    ) -> PaginatedConversations:
        if self._cosmos_client:
            return await self._cosmos_list(user_id, page, page_size)

        # In-memory fallback
        user_convos = sorted(
            (c for c in self._memory.values() if c.user_id == user_id),
            key=lambda c: c.updated_at,
            reverse=True,
        )
        total = len(user_convos)
        start = (page - 1) * page_size
        page_items = user_convos[start : start + page_size]

        return PaginatedConversations(
            items=[
                ConversationSummary(
                    id=c.id,
                    title=c.title or c.messages[0].content[:50] if c.messages else "New conversation",
                    created_at=c.created_at,
                    updated_at=c.updated_at,
                    message_count=len(c.messages),
                )
                for c in page_items
            ],
            total=total,
            page=page,
            page_size=page_size,
            has_next=start + page_size < total,
        )

    def create_conversation(self, user_id: str) -> Conversation:
        return Conversation(user_id=user_id)

    # ── Cosmos DB operations ──────────────────────────────────────────────

    async def _cosmos_get(self, conversation_id: str, user_id: str) -> Conversation | None:
        try:
            db = self._cosmos_client.get_database_client(self._settings.cosmos_database)
            container = db.get_container_client(self._settings.cosmos_conversations_container)
            item = await container.read_item(item=conversation_id, partition_key=user_id)
            return Conversation(**item)
        except Exception:
            return None

    async def _cosmos_upsert(self, conversation: Conversation) -> None:
        db = self._cosmos_client.get_database_client(self._settings.cosmos_database)
        container = db.get_container_client(self._settings.cosmos_conversations_container)
        doc = conversation.model_dump(mode="json")
        doc["id"] = conversation.id
        await container.upsert_item(doc)

    async def _cosmos_delete(self, conversation_id: str, user_id: str) -> bool:
        try:
            db = self._cosmos_client.get_database_client(self._settings.cosmos_database)
            container = db.get_container_client(self._settings.cosmos_conversations_container)
            await container.delete_item(item=conversation_id, partition_key=user_id)
            return True
        except Exception:
            return False

    async def _cosmos_list(
        self, user_id: str, page: int, page_size: int
    ) -> PaginatedConversations:
        db = self._cosmos_client.get_database_client(self._settings.cosmos_database)
        container = db.get_container_client(self._settings.cosmos_conversations_container)

        query = "SELECT * FROM c WHERE c.user_id = @uid ORDER BY c.updated_at DESC"
        params = [{"name": "@uid", "value": user_id}]
        offset = (page - 1) * page_size

        items = []
        async for item in container.query_items(
            query=query, parameters=params, max_item_count=page_size
        ):
            items.append(item)
            if len(items) >= page_size:
                break

        # Count query
        count_query = "SELECT VALUE COUNT(1) FROM c WHERE c.user_id = @uid"
        total = 0
        async for count in container.query_items(query=count_query, parameters=params):
            total = count

        return PaginatedConversations(
            items=[
                ConversationSummary(
                    id=i["id"],
                    title=i.get("title", ""),
                    created_at=i["created_at"],
                    updated_at=i["updated_at"],
                    message_count=len(i.get("messages", [])),
                )
                for i in items
            ],
            total=total,
            page=page,
            page_size=page_size,
            has_next=offset + page_size < total,
        )
