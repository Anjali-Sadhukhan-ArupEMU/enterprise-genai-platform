"""API routes — all endpoints defined per architecture spec.

Endpoints:
  POST   /api/v1/chat                 — Unified chat (stream via ?stream=true)
  GET    /api/v1/conversations        — Paginated conversation list
  DELETE /api/v1/conversations/{id}   — GDPR delete
  GET    /api/v1/models               — Available models for user
  GET    /api/v1/health               — Health check
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from backend.api.dependencies import (
    get_audit_logger,
    get_chat_orchestrator,
    get_conversation_store,
    get_model_router,
    get_provider_registry,
)
from backend.api.admin_routes import get_admin_store
from backend.auth.entra import UserContext, get_current_user
from backend.models.schemas import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    HealthStatus,
    ModelInfo,
    PaginatedConversations,
)
from backend.orchestration.chat import ChatOrchestrator
from backend.proxy.registry import ProviderRegistry
from backend.routing.router import ModelRouter
from backend.storage.adls import AuditLogger
from backend.storage.admin_config import AdminConfigStore
from backend.storage.cosmos import ConversationStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1")

_start_time = time.time()


# ── Chat ──────────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    stream: bool = Query(False),
    user: UserContext = Depends(get_current_user),
    orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator),
):
    """Unified chat endpoint. Use ?stream=true for SSE streaming."""
    if stream or request.stream:
        return StreamingResponse(
            orchestrator.handle_stream(request, user),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    return await orchestrator.handle_chat(request, user)


# ── Conversations ─────────────────────────────────────────────────────────


@router.get("/conversations", response_model=PaginatedConversations)
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: UserContext = Depends(get_current_user),
    store: ConversationStore = Depends(get_conversation_store),
):
    return await store.list_for_user(user.user_id, page, page_size)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user: UserContext = Depends(get_current_user),
    store: ConversationStore = Depends(get_conversation_store),
):
    deleted = await store.delete(conversation_id, user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


# ── Models ────────────────────────────────────────────────────────────────


@router.get("/models", response_model=list[ModelInfo])
async def list_models(
    user: UserContext = Depends(get_current_user),
    model_router: ModelRouter = Depends(get_model_router),
    admin_store: AdminConfigStore = Depends(get_admin_store),
):
    available_models = model_router.list_models(user.roles)
    config = await admin_store.get()

    if not config.groups:
        return available_models

    # If any group hides models from users, return empty list → UI shows "Auto"
    # and the router picks the best model behind the scenes.
    if any(not group.models_visible_to_users for group in config.groups):
        return []

    allowed_model_ids = {
        model_id for group in config.groups for model_id in group.model_ids
    }

    return [m for m in available_models if m.model_id in allowed_model_ids]


# ── Health ────────────────────────────────────────────────────────────────


@router.get("/health", response_model=HealthStatus)
async def health(
    registry: ProviderRegistry = Depends(get_provider_registry),
):
    model_health = await registry.health_check_all()
    all_healthy = all(model_health.values()) if model_health else True
    return HealthStatus(
        status="healthy" if all_healthy else "degraded",
        version="0.1.0",
        uptime_seconds=time.time() - _start_time,
        models=model_health,
        storage={},  # Phase 2: add Cosmos / ADLS health
    )


# ── Usage summary (live dashboard) ────────────────────────────────────────

@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def submit_feedback(
    feedback: FeedbackRequest,
    user: UserContext = Depends(get_current_user),
    audit: AuditLogger = Depends(get_audit_logger),
):
    """Capture thumbs-up/down + optional categories and free-text comment.

    Persisted via AuditLogger (ADLS in prod, logs/feedback_*.jsonl in dev).
    """
    if feedback.rating not in ("up", "down"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rating must be 'up' or 'down'",
        )
    record = feedback.model_dump(mode="json")
    record["user_id"] = user.user_id
    record["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    await audit.log_feedback(record)
