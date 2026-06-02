"""Web-search gate — decides *whether* a query needs web grounding.

This is the core of the "gated" pattern: instead of grounding every turn
(expensive) or relying on the model to admit ignorance (unreliable), a cheap
deterministic check fires the search only when the query likely needs fresh or
external facts.

Decision order (first decisive rule wins):
  1. Master kill-switch (`settings.web_search_enabled`).
  2. Per-request override (`ChatRequest.web_search`).
  3. Per-persona enablement (admin `PersonaConfig.web_search_enabled`, else a
     built-in per-persona default).
  4. Task suppression — tasks that operate on *provided* content (summarize an
     email, take meeting minutes, analyse a pasted contract) don't need the web
     unless the text also has a strong temporal/external signal.
  5. Heuristic signal match — temporal words, news/markets/weather, explicit
     "search the web", or a URL.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from backend.config import Settings, get_settings
from backend.models.schemas import Persona, PersonaConfig, TaskType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebSearchDecision:
    search: bool
    reason: str
    query: str = ""
    signals: tuple[str, ...] = ()


# Built-in defaults when no admin PersonaConfig exists for the persona.
_PERSONA_DEFAULT_ENABLED: dict[Persona, bool] = {
    Persona.CASUAL: False,
    Persona.PRODUCTIVITY: True,
    Persona.LEADERSHIP: True,
}

# Tasks that work on user-provided content — grounding is suppressed unless a
# strong temporal/external signal is also present.
_CONTENT_BOUND_TASKS: frozenset[TaskType] = frozenset(
    {
        TaskType.SUMMARIZATION,
        TaskType.EMAIL_SUMMARIZATION,
        TaskType.MEETING_MINUTES,
        TaskType.DOCUMENT_ANALYSIS,
        TaskType.CODING,
    }
)

# Heuristic signal patterns. Each is (label, compiled regex).
_SIGNAL_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("explicit", re.compile(
        r"\b(search (?:the )?web|google (?:it|this)|look (?:this )?up|"
        r"web search|browse|find online|on the internet)\b", re.IGNORECASE)),
    ("temporal", re.compile(
        r"\b(latest|current(?:ly)?|today|tonight|right now|as of (?:now|today)|"
        r"this (?:week|month|year)|recent(?:ly)?|up[- ]?to[- ]?date|"
        r"yesterday|breaking|just (?:announced|released)|newest)\b", re.IGNORECASE)),
    ("news", re.compile(
        r"\b(news|headline|announcement|press release|event|happening|"
        r"who won|election|score)\b", re.IGNORECASE)),
    ("markets", re.compile(
        r"\b(stock|share price|market cap|exchange rate|forex|crypto|bitcoin|"
        r"ethereum|interest rate|inflation|gdp|earnings)\b", re.IGNORECASE)),
    ("pricing", re.compile(
        r"\b(price|pricing|cost of|how much (?:is|does)|cheapest|deal)\b",
        re.IGNORECASE)),
    ("weather", re.compile(
        r"\b(weather|forecast|temperature outside|rain today|will it rain)\b",
        re.IGNORECASE)),
    ("year", re.compile(r"\b(20(2[5-9]|3\d))\b")),
    ("url", re.compile(r"https?://\S+", re.IGNORECASE)),
]


class WebSearchGate:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _persona_enabled(self, persona: Persona, cfg: PersonaConfig | None) -> bool:
        if cfg is not None and cfg.web_search_enabled is not None:
            return cfg.web_search_enabled
        return _PERSONA_DEFAULT_ENABLED.get(persona, False)

    @staticmethod
    def _match_signals(text: str) -> list[str]:
        return [label for label, pat in _SIGNAL_RULES if pat.search(text)]

    def has_external_signal(self, text: str) -> bool:
        """Cheap check (no persona/task) used to bypass the semantic cache for
        time-sensitive queries so we never serve stale grounded answers."""
        if not self._settings.web_search_enabled:
            return False
        return bool(self._match_signals(text or ""))


    def decide(
        self,
        *,
        text: str,
        persona: Persona,
        task: TaskType,
        persona_config: PersonaConfig | None,
        request_override: bool | None,
    ) -> WebSearchDecision:
        # 1. Master kill-switch.
        if not self._settings.web_search_enabled:
            return WebSearchDecision(False, "web_search disabled globally")

        # 2. Per-request override wins (user toggled it on/off explicitly).
        if request_override is not None:
            return WebSearchDecision(
                request_override,
                f"request override → {request_override}",
                query=text.strip() if request_override else "",
            )

        # 3. Persona must allow it.
        if not self._persona_enabled(persona, persona_config):
            return WebSearchDecision(False, f"persona '{persona.value}' has web search off")

        signals = self._match_signals(text or "")

        # 4. Content-bound tasks need a temporal/external signal to override.
        strong = {"explicit", "temporal", "news", "markets", "year", "url"}
        if task in _CONTENT_BOUND_TASKS and not (set(signals) & strong):
            return WebSearchDecision(
                False,
                f"content-bound task '{task.value}' without external signal",
                signals=tuple(signals),
            )

        # 5. Fire only when at least one signal matched.
        if signals:
            return WebSearchDecision(
                True,
                f"matched signals: {', '.join(signals)}",
                query=text.strip(),
                signals=tuple(signals),
            )

        return WebSearchDecision(False, "no external-info signal", signals=())
