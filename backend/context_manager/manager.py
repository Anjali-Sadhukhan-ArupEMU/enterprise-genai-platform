"""Conversation context manager.

Handles:
  - Multi-turn message history
  - Token budget management per model
  - Context window truncation
  - Conversation summarization (Phase 2)
"""

from __future__ import annotations

import logging
from copy import deepcopy

from backend.models.schemas import ChatMessage, Conversation, Role

logger = logging.getLogger(__name__)

# Rough estimate: 1 token ≈ 4 chars for English text
_CHARS_PER_TOKEN = 4

# Reserve tokens for system prompt + response
_SYSTEM_RESERVE = 500
_RESPONSE_RESERVE = 2048


def estimate_tokens(text: str) -> int:
    """Rough token estimate. Use tiktoken for precise counts in production."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def estimate_message_tokens(messages: list[ChatMessage]) -> int:
    return sum(estimate_tokens(m.content) + 4 for m in messages)  # +4 per-message overhead


class ConversationContextManager:
    """Builds the messages payload for a model call, respecting token limits."""

    def __init__(
        self,
        system_prompt: str = "You are a helpful enterprise AI assistant.",
    ) -> None:
        self._system_prompt = system_prompt

    def build_messages(
        self,
        conversation: Conversation,
        max_model_tokens: int,
    ) -> list[dict[str, str]]:
        """Build the messages list, truncating history to fit the model's context window.

        Strategy:
          1. Always include system prompt
          2. Always include the latest user message
          3. Fill remaining budget with recent history (newest first)
        """
        budget = max_model_tokens - _SYSTEM_RESERVE - _RESPONSE_RESERVE
        if budget <= 0:
            budget = max_model_tokens // 2

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt}
        ]

        history = conversation.messages
        if not history:
            return messages

        # Latest message is always included
        latest = history[-1]
        budget -= estimate_tokens(latest.content) + 4

        # Fill from most recent backwards
        included: list[ChatMessage] = []
        for msg in reversed(history[:-1]):
            msg_tokens = estimate_tokens(msg.content) + 4
            if budget - msg_tokens < 0:
                break
            included.append(msg)
            budget -= msg_tokens

        # Reverse to chronological order
        included.reverse()

        for msg in included:
            messages.append({"role": msg.role.value, "content": msg.content})

        messages.append({"role": latest.role.value, "content": latest.content})

        logger.debug(
            "Built context: %d messages, ~%d tokens used",
            len(messages),
            max_model_tokens - budget,
        )
        return messages
