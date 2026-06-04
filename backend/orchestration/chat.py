"""Chat orchestration — the main business-logic pipeline.

Coordinates:
  1. Governance check (input)
  2. Context management
  3. Model routing
  4. Model invocation (via proxy)
  5. Governance check (output)
  6. Audit logging
  7. Response assembly
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator

from backend.auth.entra import UserContext
from backend.caching.cache import SemanticCache
from backend.context_manager.manager import ConversationContextManager, estimate_tokens
from backend.governance.pipeline import check_input, check_output
from backend.models.schemas import (
    AuditEntry,
    ChatMessage,
    ChatMode,
    ChatRequest,
    ChatResponse,
    Citation,
    GovernanceVerdict,
    ModelProviderRequest,
    Persona,
    PersonaConfig,
    Role,
    TaskSource,
    TaskType,
    TokenUsage,
    UsageRecord,
)
from backend.orchestration.persona import PersonaResolver
from backend.orchestration.prompt_composer import ComposedPrompt, PromptComposer
from backend.orchestration.task_classifier import ClassifierResult, TaskClassifier
from backend.proxy.registry import ProviderRegistry
from backend.routing.router import ModelRouter
from backend.storage.adls import AuditLogger
from backend.storage.admin_config import AdminConfigStore
from backend.storage.cosmos import ConversationStore
from backend.telemetry.logger import RequestMetrics
from backend.tools.web_search import WebSearchProvider
from backend.tools.web_search_gate import WebSearchDecision, WebSearchGate

logger = logging.getLogger(__name__)


# ChatMode → TaskType for non-QUICK modes (strict user-selected modes
# skip classification and map directly).
_MODE_TO_TASK: dict[ChatMode, TaskType] = {
    ChatMode.DEEP: TaskType.ANALYSIS,
    ChatMode.CODE: TaskType.CODING,
    ChatMode.CREATIVE: TaskType.GENERAL,
}


class ChatOrchestrator:
    def __init__(
        self,
        provider_registry: ProviderRegistry,
        model_router: ModelRouter,
        conversation_store: ConversationStore,
        audit_logger: AuditLogger,
        context_manager: ConversationContextManager,
        semantic_cache: SemanticCache,
        persona_resolver: PersonaResolver,
        task_classifier: TaskClassifier,
        prompt_composer: PromptComposer,
        admin_config_store: AdminConfigStore,
        web_search_gate: WebSearchGate,
        web_search_provider: WebSearchProvider,
    ) -> None:
        self._providers = provider_registry
        self._router = model_router
        self._store = conversation_store
        self._audit = audit_logger
        self._context = context_manager
        self._cache = semantic_cache
        self._personas = persona_resolver
        self._classifier = task_classifier
        self._composer = prompt_composer
        self._admin = admin_config_store
        self._web_gate = web_search_gate
        self._web_search = web_search_provider
        self._metrics = RequestMetrics()

    # ── Orchestration helpers (persona / task / prompt) ──────────────────

    def _resolve_persona(self, request: ChatRequest, user: UserContext) -> Persona:
        if request.persona is not None:
            return request.persona
        return self._personas.resolve(user.groups)

    async def _resolve_task(
        self, request: ChatRequest, user_text: str
    ) -> ClassifierResult:
        if request.task is not None:
            return ClassifierResult(request.task, 1.0, TaskSource.USER)
        if request.mode != ChatMode.QUICK:
            mapped = _MODE_TO_TASK.get(request.mode, TaskType.GENERAL)
            return ClassifierResult(mapped, 1.0, TaskSource.MODE_MAP)
        return await self._classifier.classify(user_text)

    async def _resolve_persona_config(self, persona: Persona) -> PersonaConfig | None:
        admin_cfg = await self._admin.get()
        for p in admin_cfg.personas:
            if p.persona == persona:
                return p
        return None

    @staticmethod
    def _inject_system_prompt(
        messages: list[dict[str, str]], system_text: str
    ) -> list[dict[str, str]]:
        """Prepend (or merge into) the system message. Not persisted to history."""
        if not system_text:
            return messages
        if messages and messages[0].get("role") == "system":
            merged = system_text.strip() + "\n\n" + messages[0].get("content", "")
            return [{"role": "system", "content": merged}, *messages[1:]]
        return [{"role": "system", "content": system_text}, *messages]

    async def _maybe_web_search(
        self,
        *,
        request: ChatRequest,
        user_text: str,
        persona: Persona,
        task: TaskType,
        persona_config: PersonaConfig | None,
    ) -> tuple[WebSearchDecision, list[Citation]]:
        """Run the gate; search only if it fires. Never raises to the caller."""
        decision = self._web_gate.decide(
            text=user_text,
            persona=persona,
            task=task,
            persona_config=persona_config,
            request_override=request.web_search,
        )
        if not decision.search:
            logger.info("web_search skipped: %s", decision.reason)
            return decision, []
        try:
            count = self._settings_max_results()
            citations = await self._web_search.search(decision.query, count=count)
            logger.info(
                "web_search fired (%s) → %d sources", decision.reason, len(citations)
            )
            return decision, citations
        except Exception:
            logger.exception("web_search failed — continuing without grounding")
            return decision, []

    @staticmethod
    def _settings_max_results() -> int:
        from backend.config import get_settings

        return get_settings().web_search_max_results

    @staticmethod
    def _build_grounding_block(citations: list[Citation]) -> str:
        """Render citations into a system block the model can ground on."""
        if not citations:
            return ""
        lines = [
            "You have been given fresh web search results. Use them to answer "
            "and cite sources inline as [n]. If they don't cover the question, "
            "say so rather than guessing.",
            "",
            "WEB SEARCH RESULTS:",
        ]
        for i, c in enumerate(citations, start=1):
            lines.append(f"[{i}] {c.title}\n{c.url}\n{c.snippet}".strip())
        return "\n".join(lines)


    async def handle_chat(
        self, request: ChatRequest, user: UserContext
    ) -> ChatResponse:
        """Full non-streaming chat pipeline."""
        self._metrics.start()

        # ── 1. Input governance ───────────────────────────────────────────
        gov_result = await check_input(request.message)
        if gov_result.verdict == GovernanceVerdict.BLOCK:
            return ChatResponse(
                success=False,
                conversation_id=request.conversation_id or "",
                error=gov_result.blocked_reason,
            )

        user_text = gov_result.sanitized_content

        # ── 2. Semantic cache lookup ──────────────────────────────────────
        # Skip the cache for time-sensitive queries so grounded answers stay fresh.
        bypass_cache = request.web_search is True or self._web_gate.has_external_signal(
            user_text
        )
        cached = None if bypass_cache else await self._cache.get(user_text)
        if cached:
            conv_id = request.conversation_id or str(uuid.uuid4())
            return ChatResponse(
                success=True,
                conversation_id=conv_id,
                message=cached,
                model="cache",
                latency_ms=self._metrics.elapsed_ms(),
            )

        # ── 3. Load / create conversation ─────────────────────────────────
        if request.conversation_id:
            conversation = await self._store.get(request.conversation_id, user.user_id)
            if not conversation:
                conversation = self._store.create_conversation(user.user_id)
                conversation.id = request.conversation_id
        else:
            conversation = self._store.create_conversation(user.user_id)

        # Append user message
        conversation.messages.append(
            ChatMessage(role=Role.USER, content=user_text)
        )

        # ── 3a. Resolve persona, task, and compose system prompt ──────────
        persona = self._resolve_persona(request, user)
        classification = await self._resolve_task(request, user_text)
        persona_config = await self._resolve_persona_config(persona)
        composed = self._composer.compose(persona, classification.task, persona_config)

        # ── 3b. Gated web grounding ──────────────────────────────────────
        web_decision, citations = await self._maybe_web_search(
            request=request,
            user_text=user_text,
            persona=persona,
            task=classification.task,
            persona_config=persona_config,
        )

        # ── 4. Route to model (per-(persona, task) preferences) ──────────
        estimated = estimate_tokens(user_text)
        routing = self._router.route_for_task(
            persona=persona,
            task=classification.task,
            estimated_tokens=estimated,
            persona_config=persona_config,
            fallback_mode=request.mode,
        )
        model = routing.selected_model

        # ── 5. Build context window (+ inject composed system prompt) ────
        messages = self._context.build_messages(conversation, model.max_tokens)
        messages = self._inject_system_prompt(messages, composed.system_text)
        grounding = self._build_grounding_block(citations)
        if grounding:
            messages = self._inject_system_prompt(messages, grounding)


        # ── 6. Call model ─────────────────────────────────────────────────
        provider_req = ModelProviderRequest(
            model_id=model.model_id,
            messages=messages,

        )
        response = await self._providers.complete(model.provider, provider_req)

        # ── 7. Failover if primary fails ──────────────────────────────────
        if not response.success and routing.fallback_model:
            logger.warning("Primary model failed, trying fallback: %s", routing.fallback_model.model_id)
            fallback = routing.fallback_model
            provider_req.model_id = fallback.model_id
            response = await self._providers.complete(fallback.provider, provider_req)

        if not response.success:
            return ChatResponse(
                success=False,
                conversation_id=conversation.id,
                error=response.error or "Model invocation failed",
                latency_ms=self._metrics.elapsed_ms(),
            )

        # ── 8. Output governance ──────────────────────────────────────────
        output_gov = await check_output(response.content)
        final_content = output_gov.sanitized_content

        # ── 9. Persist conversation ───────────────────────────────────────
        conversation.messages.append(
            ChatMessage(role=Role.ASSISTANT, content=final_content)
        )
        conversation.model_used = response.model
        conversation.total_tokens += response.usage.total_tokens
        if not conversation.title and len(conversation.messages) >= 2:
            conversation.title = conversation.messages[0].content[:80]
        await self._store.save(conversation)

        # ── 10. Cache response ────────────────────────────────────────────
        # Never cache grounded answers — they depend on live web results.
        if not citations:
            await self._cache.set(user_text, final_content)

        # ── 11. Audit + telemetry ─────────────────────────────────────────
        latency = self._metrics.elapsed_ms()
        self._metrics.log_chat_request(
            user_id=user.user_id,
            model=response.model,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            latency_ms=latency,
            success=True,
        )
        await self._audit.log_audit(
            AuditEntry(
                user_id=user.user_id,
                action="chat",
                details={
                    "conversation_id": conversation.id,
                    "model": response.model,
                    "mode": request.mode.value,
                    "tokens": response.usage.total_tokens,
                    "governance_flags": gov_result.flags + output_gov.flags,
                    "persona": persona.value,
                    "task": classification.task.value,
                    "task_source": classification.source.value,
                    "template_id": composed.template_id,
                    "template_version": composed.template_version,
                    "classifier_confidence": classification.confidence,
                    "web_search_used": bool(citations),
                    "web_search_reason": web_decision.reason,
                    "web_search_results": len(citations),
                },
            )
        )
        await self._audit.log_usage(
            UsageRecord(
                user_id=user.user_id,
                model=response.model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                cost_estimate=(
                    response.usage.prompt_tokens * model.cost_per_1k_input / 1000
                    + response.usage.completion_tokens * model.cost_per_1k_output / 1000
                ),
                latency_ms=latency,
                persona=persona,
                task=classification.task,
                task_source=classification.source,
                template_id=composed.template_id,
                template_version=composed.template_version,
                classifier_confidence=classification.confidence,
                web_search_used=bool(citations),
                web_search_results=len(citations),
            )
        )

        return ChatResponse(
            success=True,
            conversation_id=conversation.id,
            message=final_content,
            model=response.model,
            usage=response.usage,
            latency_ms=latency,
            web_search_used=bool(citations),
            citations=citations,
        )

    async def handle_stream(
        self, request: ChatRequest, user: UserContext
    ) -> AsyncIterator[str]:
        """Streaming chat pipeline — yields SSE-formatted chunks."""
        import json as _json
        self._metrics.start()
        # ── 1. Input governance ───────────────────────────────────────────
        gov_result = await check_input(request.message)
        if gov_result.verdict == GovernanceVerdict.BLOCK:
            yield f"data: {_json.dumps({'error': gov_result.blocked_reason})}\n\n"
            yield "data: [DONE]\n\n"
            return

        user_text = gov_result.sanitized_content

        # ── 2. Load / create conversation ─────────────────────────────────
        if request.conversation_id:
            conversation = await self._store.get(request.conversation_id, user.user_id)
            if not conversation:
                conversation = self._store.create_conversation(user.user_id)
                conversation.id = request.conversation_id
        else:
            conversation = self._store.create_conversation(user.user_id)

        conversation.messages.append(
            ChatMessage(role=Role.USER, content=user_text)
        )

        # ── 3. Persona + task + composed prompt ───────────────────────────
        persona = self._resolve_persona(request, user)
        classification = await self._resolve_task(request, user_text)
        persona_config = await self._resolve_persona_config(persona)
        composed = self._composer.compose(persona, classification.task, persona_config)

        # ── 3b. Gated web grounding (emit SSE status while searching) ─────
        web_decision = self._web_gate.decide(
            text=user_text,
            persona=persona,
            task=classification.task,
            persona_config=persona_config,
            request_override=request.web_search,
        )
        citations: list[Citation] = []
        if web_decision.search:
            yield f"data: {_json.dumps({'status': 'web_search', 'message': 'Searching the web…'})}\n\n"
            try:
                citations = await self._web_search.search(
                    web_decision.query, count=self._settings_max_results()
                )
            except Exception:
                logger.exception("web_search failed during stream — continuing")
            if citations:
                cite_payload = [c.model_dump() for c in citations]
                yield f"data: {_json.dumps({'citations': cite_payload})}\n\n"

        # ── 4. Route ──────────────────────────────────────────────────────
        estimated = estimate_tokens(user_text)
        routing = self._router.route_for_task(
            persona=persona,
            task=classification.task,
            estimated_tokens=estimated,
            persona_config=persona_config,
            fallback_mode=request.mode,
        )
        model = routing.selected_model
        messages = self._context.build_messages(conversation, model.max_tokens)
        messages = self._inject_system_prompt(messages, composed.system_text)
        grounding = self._build_grounding_block(citations)
        if grounding:
            messages = self._inject_system_prompt(messages, grounding)

        provider_req = ModelProviderRequest(
            model_id=model.model_id,
            messages=messages,
            stream=True,
        )

        # ── 4. Stream from model ──────────────────────────────────────────
        full_response: list[str] = []
        try:
            async for chunk in self._providers.stream(model.provider, provider_req):
                full_response.append(chunk)
                yield f"data: {_json.dumps({'content': chunk, 'model': model.model_id})}\n\n"
        except Exception as exc:
            logger.exception("Streaming error")
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"

        # ── 5. Output governance on buffered response ─────────────────────
        complete_text = "".join(full_response)
        output_gov = await check_output(complete_text)
        if output_gov.pii_detected:
            logger.warning("PII detected in streamed output — logged for review")

        # ── 6. Persist ────────────────────────────────────────────────────
        conversation.messages.append(
            ChatMessage(role=Role.ASSISTANT, content=complete_text)
        )
        if not conversation.title:
            conversation.title = conversation.messages[0].content[:80]
        await self._store.save(conversation)
        # ── 7. Estimated usage tracking (streaming API doesn't return counts) ─
        prompt_tokens = sum(estimate_tokens(m.get("content", "")) for m in messages)
        completion_tokens = estimate_tokens(complete_text)
        cost_estimate = (
            prompt_tokens * model.cost_per_1k_input / 1000
            + completion_tokens * model.cost_per_1k_output / 1000
        )
        usage_record = UsageRecord(
            user_id=user.user_id,
            model=model.model_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_estimate=cost_estimate,
            latency_ms=self._metrics.elapsed_ms(),
            persona=persona,
            task=classification.task,
            task_source=classification.source,
            template_id=composed.template_id,
            template_version=composed.template_version,
            classifier_confidence=classification.confidence,
            web_search_used=bool(citations),
            web_search_results=len(citations),
        )
        await self._audit.log_usage(usage_record)
        yield "data: [DONE]\n\n"
