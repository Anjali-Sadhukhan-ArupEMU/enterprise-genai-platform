"""Admin API routes — config management, Foundry models, Entra groups.

Endpoints:
  GET    /api/v1/admin/config          — Load admin config
  POST   /api/v1/admin/config          — Save admin config
  GET    /api/v1/admin/foundry-models  — List models from Foundry (mock fallback)
  GET    /api/v1/admin/entra-groups    — List Entra ID groups (mock fallback)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from backend.auth.entra import UserContext, require_role
from backend.models.schemas import (
    AdminConfig,
    EntraGroup,
    FoundryModel,
    Persona,
    TaskType,
)
from backend.storage.admin_config import AdminConfigStore

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# ── Singleton store ───────────────────────────────────────────────────


def get_admin_store() -> AdminConfigStore:
    # Delegate to the central DI factory so admin saves are visible to the
    # chat orchestrator (single shared instance).
    from backend.api.dependencies import get_admin_config_store
    return get_admin_config_store()


# ── Mock data (used when Foundry / Entra not connected) ───────────────

MOCK_FOUNDRY_MODELS: list[FoundryModel] = [
    FoundryModel(model_id="gpt-4.1", display_name="GPT-4.1", provider="azure_openai"),
    FoundryModel(model_id="gpt-4.1-mini", display_name="GPT-4.1 Mini", provider="azure_openai"),
    FoundryModel(model_id="gpt-4.1-nano", display_name="GPT-4.1 Nano", provider="azure_openai"),
    FoundryModel(model_id="gpt-4o", display_name="GPT-4o", provider="azure_openai"),
    FoundryModel(model_id="gpt-4o-mini", display_name="GPT-4o Mini", provider="azure_openai"),
    FoundryModel(model_id="deepseek-r1", display_name="DeepSeek R1", provider="azure_openai"),
    FoundryModel(model_id="mistral-large", display_name="Mistral Large", provider="azure_openai"),
    FoundryModel(model_id="llama-3.3-70b", display_name="Llama 3.3 70B", provider="azure_openai"),
]

MOCK_ENTRA_GROUPS: list[EntraGroup] = [
    EntraGroup(group_id="grp-basic-001", display_name="AI-BasicUsers", member_count=45),
    EntraGroup(group_id="grp-power-002", display_name="AI-PowerUsers", member_count=12),
    EntraGroup(group_id="grp-dev-003", display_name="AI-Developers", member_count=8),
    EntraGroup(group_id="grp-exec-004", display_name="AI-Executives", member_count=5),
]


# ── Endpoints ─────────────────────────────────────────────────────────


@admin_router.get("/config", response_model=AdminConfig)
async def get_config(
    _user: UserContext = Depends(require_role("admin")),
    store: AdminConfigStore = Depends(get_admin_store),
):
    """Load the current admin config."""
    return await store.get()


@admin_router.post("/config", response_model=AdminConfig)
async def save_config(
    config: AdminConfig,
    user: UserContext = Depends(require_role("admin")),
    store: AdminConfigStore = Depends(get_admin_store),
):
    """Save admin config (group → model + prompt mappings)."""
    config.updated_by = user.user_id
    await store.save(config)
    logger.info("Admin config saved by %s — %d groups", user.user_id, len(config.groups))
    return config


@admin_router.get("/foundry-models", response_model=list[FoundryModel])
async def list_foundry_models(
    _user: UserContext = Depends(require_role("admin")),
):
    """List models from Azure AI Foundry. Returns mock data when not connected."""
    # TODO: Replace with real Foundry API call when connection is configured
    # from backend.config import get_settings
    # settings = get_settings()
    # if settings.foundry_endpoint:
    #     return await fetch_foundry_models(settings)
    return MOCK_FOUNDRY_MODELS


@admin_router.get("/entra-groups", response_model=list[EntraGroup])
async def list_entra_groups(
    _user: UserContext = Depends(require_role("admin")),
):
    """List Entra ID groups. Returns mock data when not connected."""
    # TODO: Replace with Microsoft Graph API call when Entra is configured
    # from backend.config import get_settings
    # settings = get_settings()
    # if settings.entra_client_id:
    #     return await fetch_entra_groups(settings)
    return MOCK_ENTRA_GROUPS


@admin_router.get("/personas")
async def list_personas(
    _user: UserContext = Depends(require_role("admin")),
):
    """List available personas and the task templates they can be routed to."""
    return {
        "personas": [p.value for p in Persona],
        "tasks": [t.value for t in TaskType],
    }


@admin_router.post("/reload-prompts", status_code=204)
async def reload_prompts(
    _user: UserContext = Depends(require_role("admin")),
):
    """Reload prompt templates and persona mappings from disk."""
    from backend.api.dependencies import get_persona_resolver, get_template_loader
    get_template_loader().reload()
    get_persona_resolver().reload()
