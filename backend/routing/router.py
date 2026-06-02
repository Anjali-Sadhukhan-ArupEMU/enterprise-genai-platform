"""Model router — selects the best model based on mode, cost, and health.

Phase 1 routing logic (per architecture):
  - Route by user-selected mode (quick / deep / code / creative)
  - Route by token count
  - Health-aware failover

Phase 2 (optional): ML-based complexity classification.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.config import Settings, get_settings
from backend.models.schemas import (
    ChatMode,
    ModelInfo,
    Persona,
    PersonaConfig,
    RoutingDecision,
    TaskType,
)

logger = logging.getLogger(__name__)

# Default model catalog — overridden by config/routing_config.json at runtime
_DEFAULT_MODELS: list[dict] = [
    {
        "model_id": "gpt-4o-mini",
        "provider": "azure_openai",
        "display_name": "GPT-4o Mini",
        "max_tokens": 128_000,
        "cost_per_1k_input": 0.00015,
        "cost_per_1k_output": 0.0006,
        "supported_modes": ["quick"],
    },
    {
        "model_id": "gpt-4o",
        "provider": "azure_openai",
        "display_name": "GPT-4o",
        "max_tokens": 128_000,
        "cost_per_1k_input": 0.0025,
        "cost_per_1k_output": 0.01,
        "supported_modes": ["deep", "code", "creative"],
    },
]


class ModelRouter:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._models: list[ModelInfo] = []
        self._health: dict[str, bool] = {}
        self._load_config()

    def _load_config(self) -> None:
        config_path = Path(self._settings.routing_config_path)
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                raw_models = data.get("models", _DEFAULT_MODELS)
            except Exception:
                logger.warning("Failed to load routing config, using defaults")
                raw_models = _DEFAULT_MODELS
        else:
            raw_models = _DEFAULT_MODELS

        self._models = [ModelInfo(**m, is_healthy=True) for m in raw_models]
        logger.info("Loaded %d model definitions", len(self._models))

    def reload_config(self) -> None:
        self._load_config()

    def update_health(self, statuses: dict[str, bool]) -> None:
        """Update model health from provider health checks."""
        for model in self._models:
            if model.provider in statuses:
                model.is_healthy = statuses[model.provider]
        self._health = statuses

    def route(self, mode: ChatMode, estimated_tokens: int = 0) -> RoutingDecision:
        """Select the best model for the given mode and token estimate."""
        # Filter healthy models that support the requested mode
        candidates = [
            m for m in self._models
            if m.is_healthy and mode in m.supported_modes
        ]

        if not candidates:
            # Fallback: any healthy model
            candidates = [m for m in self._models if m.is_healthy]

        if not candidates:
            # All models unhealthy — pick first model as last resort
            candidates = self._models[:1]

        # Sort by cost (cheapest first)
        candidates.sort(key=lambda m: m.cost_per_1k_input)

        selected = candidates[0]
        fallback = candidates[1] if len(candidates) > 1 else None

        reason = f"Mode={mode.value}, cheapest healthy model"
        if estimated_tokens > selected.max_tokens:
            # If token estimate exceeds selected model's limit,
            # pick model with largest context window
            candidates.sort(key=lambda m: m.max_tokens, reverse=True)
            selected = candidates[0]
            fallback = candidates[1] if len(candidates) > 1 else None
            reason = f"Mode={mode.value}, largest context window for {estimated_tokens} tokens"

        return RoutingDecision(
            selected_model=selected,
            reason=reason,
            fallback_model=fallback,
        )

    def list_models(self, user_roles: list[str] | None = None) -> list[ModelInfo]:
        """List models available to the user."""
        # Phase 1: all models visible; Phase 2: filter by role/department
        return [m for m in self._models if m.is_healthy]

    def route_for_task(
        self,
        persona: Persona,
        task: TaskType,
        estimated_tokens: int = 0,
        persona_config: PersonaConfig | None = None,
        fallback_mode: ChatMode = ChatMode.QUICK,
    ) -> RoutingDecision:
        """Select a model using per-(persona, task) admin preferences.

        Resolution order:
          1. If `persona_config` has a matching `PersonaTaskRoute`, walk the
             preferred_model_ids in order, pick the first healthy one.
          2. If none of the preferred models are healthy/known, fall back to
             persona_config.allowed_model_ids (cheapest healthy).
          3. If no persona_config at all, fall back to legacy `route(mode, ...)`.
        """
        by_id = {m.model_id: m for m in self._models}

        preferred = self._healthy_preferred(persona_config, task, by_id, estimated_tokens)
        if preferred:
            selected, fallback = preferred[0], (preferred[1] if len(preferred) > 1 else None)
            return RoutingDecision(
                selected_model=selected,
                reason=f"Persona={persona.value}, task={task.value}, preferred model #1",
                fallback_model=fallback,
            )

        allowed = self._cheapest_allowed(persona_config, by_id)
        if allowed:
            selected, fallback = allowed[0], (allowed[1] if len(allowed) > 1 else None)
            return RoutingDecision(
                selected_model=selected,
                reason=f"Persona={persona.value}, task={task.value}, cheapest allowed",
                fallback_model=fallback,
            )

        return self.route(fallback_mode, estimated_tokens)

    @staticmethod
    def _healthy_preferred(
        persona_config: PersonaConfig | None,
        task: TaskType,
        by_id: dict[str, ModelInfo],
        estimated_tokens: int,
    ) -> list[ModelInfo]:
        if not persona_config:
            return []
        preferred_ids: list[str] = []
        for r in persona_config.routes:
            if r.task == task:
                preferred_ids = list(r.preferred_model_ids)
                break
        healthy = [by_id[mid] for mid in preferred_ids if mid in by_id and by_id[mid].is_healthy]
        if estimated_tokens > 0:
            fitting = [m for m in healthy if m.max_tokens >= estimated_tokens]
            return fitting or healthy
        return healthy

    @staticmethod
    def _cheapest_allowed(
        persona_config: PersonaConfig | None,
        by_id: dict[str, ModelInfo],
    ) -> list[ModelInfo]:
        if not persona_config or not persona_config.allowed_model_ids:
            return []
        allowed = [
            by_id[mid] for mid in persona_config.allowed_model_ids
            if mid in by_id and by_id[mid].is_healthy
        ]
        allowed.sort(key=lambda m: m.cost_per_1k_input)
        return allowed
