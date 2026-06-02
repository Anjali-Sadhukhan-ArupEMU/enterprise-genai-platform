"""Application configuration loaded from environment variables.

All secrets come from environment (Key Vault in production).
No secrets in code.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────────────
    app_name: str = "Enterprise GenAI Platform"
    app_version: str = "0.1.0"
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:3000"]

    # ── Entra ID / Auth ───────────────────────────────────────────────────
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_authority: str = ""

    # ── Azure OpenAI ──────────────────────────────────────────────────────
    azure_openai_endpoint: str = ""
    azure_openai_api_version: str = "2024-10-21"
    # Deployment name on the Azure OpenAI resource (the name you gave it
    # in the portal). When set, all routing_config model_ids are mapped to
    # this single deployment — useful for cost-controlled testing with one
    # model. Leave empty in multi-deployment production setups.
    azure_openai_deployment: str = ""
    # Force MI even when an API key is set (e.g. CI smoke tests).
    azure_openai_use_managed_identity: bool = False
    # API key — fallback for local dev only. Empty in prod (use MI).
    azure_openai_api_key: str = ""

    # ── Azure AI Foundry project ──────────────────────────────────────────
    # Set when using non-OpenAI Foundry models (Llama, Mistral, DeepSeek)
    # via azure-ai-inference / azure-ai-projects SDK. OpenAI calls still use
    # azure_openai_endpoint above.
    foundry_project_endpoint: str = ""
    # ── Usage / cost dashboard ───────────────────────────────────
    # Drives the in-app dashboard's progress bar. Default = MSDN VS Enterprise
    # monthly credit (~₹12,500). Set to your real budget cap.
    monthly_budget_inr: float = 12500.0
    # USD→INR conversion used to render Azure's USD-priced model costs in INR.
    usd_to_inr: float = 83.0    # Master switch for the sidebar Usage panel. Frontend reads this from
    # /api/v1/usage/summary and hides the panel when false.
    usage_dashboard_enabled: bool = True    # ── Cosmos DB ─────────────────────────────────────────────────────────
    cosmos_endpoint: str = ""
    cosmos_key: str = ""  # empty when using Managed Identity
    cosmos_database: str = "genai_platform"
    cosmos_conversations_container: str = "conversations"

    # ── Azure Data Lake Storage ───────────────────────────────────────────
    adls_account_url: str = ""
    adls_audit_container: str = "audit"
    adls_analytics_container: str = "analytics"

    # ── Azure AI Content Safety ───────────────────────────────────────────
    content_safety_endpoint: str = ""
    content_safety_key: str = ""

    # ── Redis (optional semantic cache) ───────────────────────────────────
    redis_url: str = ""

    # ── Web grounding (gated Bing search) ─────────────────────────────────
    # Master switch. When false the gate never fires and no search runs.
    web_search_enabled: bool = True
    # Grounding with Bing Search via an Azure AI Foundry connection. When the
    # connection id + endpoint are set, the real provider is used; otherwise a
    # mock provider serves canned results so the gate stays testable in dev.
    bing_grounding_connection_id: str = ""
    bing_grounding_endpoint: str = ""
    # Max sources to fetch per grounded turn (cost ∝ this for some tiers).
    web_search_max_results: int = 4

    # ── Routing config ────────────────────────────────────────────────────
    routing_config_path: str = "config/routing_config.json"

    # ── Rate limits (per-user defaults) ───────────────────────────────────
    default_requests_per_minute: int = 30
    default_daily_token_budget: int = 500_000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
