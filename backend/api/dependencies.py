"""FastAPI dependencies — wires up all components as singletons."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from backend.caching.cache import SemanticCache
from backend.config import get_settings
from backend.context_manager.manager import ConversationContextManager
from backend.orchestration.chat import ChatOrchestrator
from backend.orchestration.persona import PersonaResolver
from backend.orchestration.prompt_composer import PromptComposer
from backend.orchestration.task_classifier import TaskClassifier
from backend.orchestration.template_loader import TemplateLoader
from backend.proxy.azure_openai import AzureOpenAIProvider
from backend.proxy.mock import MockProvider
from backend.proxy.registry import ProviderRegistry
from backend.routing.router import ModelRouter
from backend.storage.adls import AuditLogger
from backend.storage.admin_config import AdminConfigStore
from backend.storage.cosmos import ConversationStore
from backend.tools.web_search import WebSearchProvider, build_web_search_provider
from backend.tools.web_search_gate import WebSearchGate
from backend.usage.tracker import UsageTracker


@lru_cache
def get_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    settings = get_settings()
    if settings.azure_openai_endpoint:
        registry.register(AzureOpenAIProvider(settings))
    else:
        registry.register(MockProvider())
    return registry


@lru_cache
def get_model_router() -> ModelRouter:
    return ModelRouter()


@lru_cache
def get_conversation_store() -> ConversationStore:
    return ConversationStore()


@lru_cache
def get_audit_logger() -> AuditLogger:
    return AuditLogger()


@lru_cache
def get_context_manager() -> ConversationContextManager:
    return ConversationContextManager()


@lru_cache
def get_semantic_cache() -> SemanticCache:
    return SemanticCache(get_settings().redis_url)


@lru_cache
def get_usage_tracker() -> UsageTracker:
    s = get_settings()
    tracker = UsageTracker(monthly_budget_inr=s.monthly_budget_inr, usd_to_inr=s.usd_to_inr)
    # Replay local audit logs so the dashboard survives backend restarts.
    # ADLS-backed setups still hydrate from the local mirror written by AuditLogger.
    tracker.hydrate_from_logs(Path("logs"))
    return tracker


@lru_cache
def get_admin_config_store() -> AdminConfigStore:
    return AdminConfigStore()


@lru_cache
def get_template_loader() -> TemplateLoader:
    return TemplateLoader()


@lru_cache
def get_persona_resolver() -> PersonaResolver:
    return PersonaResolver()


@lru_cache
def get_task_classifier() -> TaskClassifier:
    return TaskClassifier(provider_registry=get_provider_registry())


@lru_cache
def get_prompt_composer() -> PromptComposer:
    return PromptComposer(loader=get_template_loader())


@lru_cache
def get_web_search_provider() -> WebSearchProvider:
    return build_web_search_provider(get_settings())


@lru_cache
def get_web_search_gate() -> WebSearchGate:
    return WebSearchGate(get_settings())


@lru_cache
def get_chat_orchestrator() -> ChatOrchestrator:
    return ChatOrchestrator(
        provider_registry=get_provider_registry(),
        model_router=get_model_router(),
        conversation_store=get_conversation_store(),
        audit_logger=get_audit_logger(),
        context_manager=get_context_manager(),
        semantic_cache=get_semantic_cache(),
        usage_tracker=get_usage_tracker(),
        persona_resolver=get_persona_resolver(),
        task_classifier=get_task_classifier(),
        prompt_composer=get_prompt_composer(),
        admin_config_store=get_admin_config_store(),
        web_search_gate=get_web_search_gate(),
        web_search_provider=get_web_search_provider(),
    )
