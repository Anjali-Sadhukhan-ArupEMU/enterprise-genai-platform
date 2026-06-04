"""Admin API routes — config management, Foundry models, Entra groups.

Endpoints:
  GET    /api/v1/admin/config          — Load admin config
  POST   /api/v1/admin/config          — Save admin config
  GET    /api/v1/admin/foundry-models  — List live Foundry deployments
  GET    /api/v1/admin/entra-groups    — List real Entra ID security groups (Microsoft Graph)
  POST   /api/v1/admin/generate-prompt — LLM-generate a persona-tailored system prompt
"""

from __future__ import annotations

import logging

import httpx
from azure.identity import DefaultAzureCredential
from fastapi import APIRouter, Depends, HTTPException

from backend.auth.entra import UserContext, require_role
from backend.config import Settings, get_settings
from backend.models.schemas import (
    AdminConfig,
    EntraGroup,
    FoundryModel,
    GeneratePromptRequest,
    GeneratePromptResponse,
    GroupModelConfig,
    ModelProviderRequest,
    Persona,
    TaskType,
)
from backend.storage.admin_config import AdminConfigStore

logger = logging.getLogger(__name__)

admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Data-plane scope + API version for listing Azure OpenAI / Foundry deployments.
_COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
_DEPLOYMENTS_API_VERSION = "2023-03-15-preview"

# Microsoft Graph — used to list real Entra ID security groups.
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Persona catalogue used to steer the LLM when generating system prompts.
# Keys are the persona identifiers exposed to the admin UI as suggestion
# cards. The first three align with the built-in routing personas; the 7th
# "developer" persona is for builders who call the platform from their own apps.
_PERSONA_CATALOGUE: dict[str, dict[str, str]] = {
    "casual": {
        "label": "Casual Opportunistic User",
        "description": (
            "Low-medium usage. Drafts emails, summarises text, asks general "
            "queries. Often unaware of approved tools. Needs encouraging, "
            "simple, friendly guidance and gentle nudges toward approved tooling."
        ),
    },
    "productivity": {
        "label": "Productivity Power User",
        "description": (
            "Medium-high usage. Drafts and analyses work documents, generates "
            "formal content (design notes, RAID logs). Values speed, flexibility "
            "and accuracy. Needs structured, thorough, professional output."
        ),
    },
    "leadership": {
        "label": "Leadership / Decision Support User",
        "description": (
            "Low-medium usage focused on insight generation, summarising, and "
            "strategic thinking. Wants concise, critical analysis delivered "
            "swiftly while avoiding process complexity. Needs executive tone."
        ),
    },
    "developer": {
        "label": "Developer / Builder (Own Application)",
        "description": (
            "Technical builder who integrates the platform's models into their "
            "own applications. Needs API integration help, code samples, and "
            "best practices, plus the recommended model and endpoint to call."
        ),
    },
}
_DEFAULT_PERSONA_LABEL = "General Enterprise User"

# ── Singleton store ───────────────────────────────────────────────────


def get_admin_store() -> AdminConfigStore:
    # Delegate to the central DI factory so admin saves are visible to the
    # chat orchestrator (single shared instance).
    from backend.api.dependencies import get_admin_config_store
    return get_admin_config_store()


# ── Foundry deployment discovery ──────────────────────────────────────

# Cache the credential — DefaultAzureCredential is safe to reuse.
_credential: DefaultAzureCredential | None = None


def _get_credential() -> DefaultAzureCredential:
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential(
            exclude_interactive_browser_credential=False
        )
    return _credential


async def _fetch_foundry_deployments(settings: Settings) -> list[FoundryModel]:
    """Return the live model deployments on the configured Foundry/OpenAI account.

    Uses the data-plane `GET {endpoint}/openai/deployments` listing with a
    Managed Identity bearer token. Returns an empty list (never raises) when
    the endpoint is unset or the call fails, so callers can fall back.
    """
    endpoint = (settings.azure_openai_endpoint or "").rstrip("/")
    if not endpoint:
        return []

    url = f"{endpoint}/openai/deployments?api-version={_DEPLOYMENTS_API_VERSION}"
    try:
        token = _get_credential().get_token(_COGNITIVE_SERVICES_SCOPE).token
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url, headers={"Authorization": f"Bearer {token}"}
            )
            resp.raise_for_status()
            data = resp.json().get("data", [])
    except Exception as exc:  # noqa: BLE001 — degrade gracefully for the admin UI
        logger.warning("Failed to list Foundry deployments: %s", exc)
        return []

    seen: set[str] = set()
    models: list[FoundryModel] = []
    for d in data:
        # Only surface successful deployments.
        if d.get("status") not in (None, "succeeded"):
            continue
        deployment_name = d.get("id") or d.get("name") or ""
        model_name = d.get("model") or deployment_name
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        models.append(
            FoundryModel(
                model_id=model_name,
                display_name=deployment_name or model_name,
                provider="azure_openai",
                deployed=True,
            )
        )
    models.sort(key=lambda m: m.model_id)
    logger.info("Discovered %d Foundry deployments", len(models))
    return models


async def _fetch_entra_groups() -> list[EntraGroup]:
    """Return real Entra ID security groups via Microsoft Graph.

    Uses the signed-in/managed identity (DefaultAzureCredential) with the
    Graph `.default` scope. Lists security-enabled groups and best-effort
    resolves each group's member count. Raises on failure so the caller can
    surface a clear error (no mock fallback).
    """
    token = _get_credential().get_token(_GRAPH_SCOPE).token
    headers = {"Authorization": f"Bearer {token}"}
    url = (
        f"{_GRAPH_BASE}/groups"
        "?$filter=securityEnabled eq true"
        "&$select=id,displayName"
        "&$top=999"
    )

    groups: list[EntraGroup] = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        while url:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
            for g in payload.get("value", []):
                gid = g.get("id")
                if not gid:
                    continue
                count = 0
                try:
                    c = await client.get(
                        f"{_GRAPH_BASE}/groups/{gid}/members/$count",
                        headers={**headers, "ConsistencyLevel": "eventual"},
                    )
                    if c.status_code == 200:
                        count = int(c.text or 0)
                except Exception:  # noqa: BLE001 — member count is best-effort
                    count = 0
                groups.append(
                    EntraGroup(
                        group_id=gid,
                        display_name=g.get("displayName", gid),
                        member_count=count,
                    )
                )
            url = payload.get("@odata.nextLink")

    groups.sort(key=lambda g: g.display_name.lower())
    logger.info("Discovered %d Entra security groups", len(groups))
    return groups


# ── Endpoints ─────────────────────────────────────────────────────────


@admin_router.get("/config", response_model=AdminConfig)
async def get_config(
    _user: UserContext = Depends(require_role("admin")),
    store: AdminConfigStore = Depends(get_admin_store),
):
    """Load the aggregated admin config (all per-group documents)."""
    return await store.get()


@admin_router.get("/config/groups", response_model=list[GroupModelConfig])
async def list_group_configs(
    _user: UserContext = Depends(require_role("admin")),
    store: AdminConfigStore = Depends(get_admin_store),
):
    """List every saved per-group config document."""
    return await store.list_groups()


@admin_router.post("/config/group", response_model=GroupModelConfig)
async def save_group_config(
    config: GroupModelConfig,
    user: UserContext = Depends(require_role("admin")),
    store: AdminConfigStore = Depends(get_admin_store),
):
    """Create or update the config for a single Entra group (its own document)."""
    if not config.group_id:
        raise HTTPException(status_code=400, detail="group_id is required.")
    config.updated_by = user.email or user.name or user.user_id
    saved = await store.save_group(config)
    logger.info(
        "Group config saved by %s — group=%s (%s), %d models",
        user.user_id, config.group_name, config.group_id, len(config.model_ids),
    )
    return saved


@admin_router.delete("/config/group/{group_id}", status_code=204)
async def delete_group_config(
    group_id: str,
    user: UserContext = Depends(require_role("admin")),
    store: AdminConfigStore = Depends(get_admin_store),
):
    """Delete the config document for a single Entra group."""
    await store.delete_group(group_id)
    logger.info("Group config deleted by %s — group=%s", user.user_id, group_id)



@admin_router.get("/foundry-models", response_model=list[FoundryModel])
async def list_foundry_models(
    _user: UserContext = Depends(require_role("admin")),
):
    """List models actually deployed in Azure AI Foundry (admin-only).

    Queries the data-plane deployments endpoint with Managed Identity and
    returns only live deployments. No static catalogue/mock fallback.
    """
    settings = get_settings()
    live = await _fetch_foundry_deployments(settings)
    return sorted(live, key=lambda m: m.model_id)


@admin_router.get("/entra-groups", response_model=list[EntraGroup])
async def list_entra_groups(
    _user: UserContext = Depends(require_role("admin")),
):
    """List real Entra ID security groups via Microsoft Graph."""
    try:
        return await _fetch_entra_groups()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to fetch Entra groups")
        raise HTTPException(
            status_code=502,
            detail="Unable to list Entra ID groups from Microsoft Graph.",
        ) from exc


def _resolve_persona_key(body: GeneratePromptRequest) -> str:
    """Pick the persona: explicit card selection wins, else infer from group."""
    persona_key = (body.persona or "").strip().lower()
    if persona_key in _PERSONA_CATALOGUE:
        return persona_key
    from backend.api.dependencies import get_persona_resolver

    return get_persona_resolver().resolve([body.group_name]).value


def _build_prompt_messages(
    body: GeneratePromptRequest,
    persona_key: str,
    recommended_model: str | None,
    endpoint: str | None,
) -> list[dict[str, str]]:
    """Compose the system+user messages that steer prompt generation."""
    meta = _PERSONA_CATALOGUE.get(persona_key)
    persona_label = meta["label"] if meta else _DEFAULT_PERSONA_LABEL
    persona_desc = (
        meta["description"]
        if meta
        else "A general enterprise user who needs clear, professional assistance."
    )

    developer_extra = ""
    if persona_key == "developer":
        developer_extra = (
            "\n- This persona builds their own applications. Add a short section "
            "telling them they can call the platform's models directly and that "
            f"the recommended model is '{recommended_model or 'an approved deployment'}' "
            f"via the endpoint '{endpoint or 'the platform API endpoint'}'. "
            "Encourage best-practice API integration, secure key/identity handling, "
            "and concise code-sample guidance."
        )

    user_instructions = (
        "You are an expert prompt engineer for Arup's enterprise AI platform.\n"
        "Write a SYSTEM PROMPT (instructions for an AI assistant — not a reply) "
        "for the user segment below.\n\n"
        f"Entra ID group: {body.group_name or 'Unspecified'}\n"
        f"Persona: {persona_label} — {persona_desc}\n\n"
        "Requirements:\n"
        "- Tailor tone, depth, and guardrails to this persona.\n"
        "- Keep it concise (120-200 words), professional, and ready to paste.\n"
        "- Output ONLY the system prompt text — no markdown headings, no preamble."
        f"{developer_extra}"
    )
    return [
        {
            "role": "system",
            "content": "You write production-ready system prompts for enterprise AI assistants.",
        },
        {"role": "user", "content": user_instructions},
    ]


@admin_router.post("/generate-prompt", response_model=GeneratePromptResponse)
async def generate_prompt(
    body: GeneratePromptRequest,
    _user: UserContext = Depends(require_role("admin")),
):
    """LLM-generate a system prompt tailored to a group's persona.

    The persona is taken from the suggestion card (`body.persona`) when
    provided, otherwise inferred from the Entra group name. For the 7th
    "developer" persona the response also surfaces the recommended model and
    endpoint so builders can call the platform from their own applications.
    """
    from backend.api.dependencies import get_provider_registry

    settings = get_settings()
    persona_key = _resolve_persona_key(body)
    meta = _PERSONA_CATALOGUE.get(persona_key)
    persona_label = meta["label"] if meta else _DEFAULT_PERSONA_LABEL
    is_developer = persona_key == "developer"

    recommended_model = (
        body.model_ids[0]
        if body.model_ids
        else (settings.azure_openai_deployment or None)
    )
    endpoint = settings.azure_openai_endpoint or None

    req = ModelProviderRequest(
        model_id=recommended_model or "",
        messages=_build_prompt_messages(body, persona_key, recommended_model, endpoint),
        temperature=0.6,
        max_tokens=600,
    )

    result = await get_provider_registry().complete("azure_openai", req)
    if not result.success or not result.content.strip():
        raise HTTPException(
            status_code=502,
            detail=result.error or "The model returned an empty prompt.",
        )

    return GeneratePromptResponse(
        persona=persona_key,
        persona_label=persona_label,
        prompt=result.content.strip(),
        recommended_model=recommended_model if is_developer else None,
        endpoint=endpoint if is_developer else None,
    )


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
