"""Pydantic models for the Enterprise GenAI Platform.

Defines the standardized request/response contracts used across all layers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ChatMode(str, Enum):
    QUICK = "quick"
    DEEP = "deep"
    CODE = "code"
    CREATIVE = "creative"


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class GovernanceVerdict(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    WARN = "warn"


class Persona(str, Enum):
    CASUAL = "casual"
    PRODUCTIVITY = "productivity"
    LEADERSHIP = "leadership"


class TaskType(str, Enum):
    SUMMARIZATION = "summarization"
    EMAIL_SUMMARIZATION = "email_summarization"
    MEETING_MINUTES = "meeting_minutes"
    DOCUMENT_ANALYSIS = "document_analysis"
    ANALYSIS = "analysis"
    CODING = "coding"
    GENERAL = "general"


class TaskSource(str, Enum):
    USER = "user"
    HEURISTIC = "heuristic"
    LLM = "llm"
    MODE_MAP = "mode_map"
    DEFAULT = "default"


# ---------------------------------------------------------------------------
# Chat Messages
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: Role
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Chat Request / Response
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    mode: ChatMode = ChatMode.QUICK
    stream: bool = False
    # Optional overrides — wins over auto-detection / persona resolution.
    task: TaskType | None = None
    persona: Persona | None = None
    # Force web grounding on/off for this request (None = let the gate decide).
    web_search: bool | None = None


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class Citation(BaseModel):
    """A single web source surfaced by the grounding tool."""
    title: str = ""
    url: str = ""
    snippet: str = ""


class ChatResponse(BaseModel):
    success: bool
    conversation_id: str
    message: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    error: str | None = None
    # Web grounding (gated) — populated only when a search was performed.
    web_search_used: bool = False
    citations: list[Citation] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    model_used: str = ""
    total_tokens: int = 0


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class PaginatedConversations(BaseModel):
    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int
    has_next: bool


# ---------------------------------------------------------------------------
# Governance
# ---------------------------------------------------------------------------

class GovernanceResult(BaseModel):
    verdict: GovernanceVerdict
    blocked_reason: str | None = None
    pii_detected: bool = False
    injection_detected: bool = False
    sanitized_content: str = ""
    flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Model Routing
# ---------------------------------------------------------------------------

class ModelInfo(BaseModel):
    model_id: str
    provider: str
    display_name: str
    max_tokens: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    is_healthy: bool = True
    supported_modes: list[ChatMode] = Field(default_factory=list)


class RoutingDecision(BaseModel):
    selected_model: ModelInfo
    reason: str
    fallback_model: ModelInfo | None = None


# ---------------------------------------------------------------------------
# Model Provider
# ---------------------------------------------------------------------------

class ModelProviderRequest(BaseModel):
    model_id: str
    messages: list[dict[str, str]]
    # None = let the model use its full output capacity (no cap).
    max_tokens: int | None = None
    temperature: float = 0.7
    stream: bool = False


class ModelProviderResponse(BaseModel):
    success: bool
    content: str = ""
    model: str = ""
    usage: TokenUsage = Field(default_factory=TokenUsage)
    latency_ms: float = 0.0
    error: str | None = None


# ---------------------------------------------------------------------------
# Health & Usage
# ---------------------------------------------------------------------------

class HealthStatus(BaseModel):
    status: str  # "healthy" | "degraded" | "unhealthy"
    version: str
    uptime_seconds: float
    models: dict[str, bool] = Field(default_factory=dict)
    storage: dict[str, bool] = Field(default_factory=dict)


class UsageRecord(BaseModel):
    user_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_estimate: float
    latency_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    # Orchestration telemetry (optional — populated by ChatOrchestrator)
    persona: Persona | None = None
    task: TaskType | None = None
    task_source: TaskSource | None = None
    template_id: str | None = None
    template_version: str | None = None
    classifier_confidence: float | None = None
    # Web grounding telemetry
    web_search_used: bool = False
    web_search_results: int | None = None


class UsageSummary(BaseModel):
    total_requests: int
    total_tokens: int
    estimated_cost: float
    period_start: datetime
    period_end: datetime
    by_model: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    conversation_id: str | None = None
    message_index: int | None = None
    rating: str  # "up" | "down"
    categories: list[str] = Field(default_factory=list)
    comment: str = ""
    model: str = ""


# ---------------------------------------------------------------------------
# Admin Config (Group → Models + Prompt mapping)
# ---------------------------------------------------------------------------

class GroupModelConfig(BaseModel):
    """Configuration for a single Entra ID group."""
    group_name: str
    group_id: str = ""
    model_ids: list[str]
    models_visible_to_users: bool = True
    system_prompt: str = ""


class PersonaTaskRoute(BaseModel):
    """Ordered list of preferred models for a (persona, task) pair."""
    task: TaskType
    preferred_model_ids: list[str] = Field(default_factory=list)


class PersonaConfig(BaseModel):
    """Configuration for a single persona (mapped from one or more Entra groups)."""
    persona: Persona
    entra_group_ids: list[str] = Field(default_factory=list)
    entra_group_names: list[str] = Field(default_factory=list)
    priority: int = 100  # lower wins on multi-group membership
    allowed_model_ids: list[str] = Field(default_factory=list)
    routes: list[PersonaTaskRoute] = Field(default_factory=list)
    system_prompt_override: str = ""
    # Gated web grounding: None = use built-in per-persona default.
    web_search_enabled: bool | None = None


class PromptTemplate(BaseModel):
    """A versioned prompt fragment loaded from config/prompts/."""
    id: str
    version: str
    body: str
    scope: str  # "global" | "persona" | "task"
    key: str = ""  # persona name or task name; empty for global


class AdminConfig(BaseModel):
    """Full admin configuration saved to Cosmos DB."""
    id: str = "admin_config"
    groups: list[GroupModelConfig] = Field(default_factory=list)
    # New persona-based config (preferred when present). Legacy `groups` is
    # kept for backward compatibility; orchestrator uses `personas` first.
    personas: list[PersonaConfig] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = ""


class FoundryModel(BaseModel):
    """Model available from Azure AI Foundry."""
    model_id: str
    display_name: str
    provider: str = "azure_openai"


class EntraGroup(BaseModel):
    """Entra ID group info."""
    group_id: str
    display_name: str
    member_count: int = 0


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ip_address: str = ""
