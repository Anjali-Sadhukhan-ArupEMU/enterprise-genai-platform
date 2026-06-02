"""Task classification — heuristic-first, LLM fallback on low confidence.

`TaskClassifier.classify(text)` returns `(task, confidence, source)`.

Order:
  1. Heuristic (keyword/regex tables) — returns confidence 0.0-1.0
  2. If confidence < `confidence_threshold`, call a small LLM and parse JSON
     `{"task": "...", "confidence": 0.0-1.0}`. Errors fall through to `general`.

Results are cached in-process by SHA-256 of the prompt prefix.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import OrderedDict
from dataclasses import dataclass

from backend.models.schemas import (
    ModelProviderRequest,
    TaskSource,
    TaskType,
)
from backend.proxy.registry import ProviderRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifierResult:
    task: TaskType
    confidence: float
    source: TaskSource


# ── Heuristic rules ────────────────────────────────────────────────────────
# Ordered: more specific tasks first. Each rule is (TaskType, regex pattern).

_HEURISTIC_RULES: list[tuple[TaskType, re.Pattern[str]]] = [
    # Email summarization — must come before generic summarization
    (TaskType.EMAIL_SUMMARIZATION, re.compile(
        r"\b(email|e-mail|inbox|thread|reply chain|forwarded message|"
        r"from:.*\bto:|subject:)\b", re.IGNORECASE)),
    # Meeting minutes
    (TaskType.MEETING_MINUTES, re.compile(
        r"\b(meeting|minutes|stand[- ]?up|action items?|decisions? from|"
        r"agenda|attendees|transcript)\b", re.IGNORECASE)),
    # Document analysis — contracts, RFPs, specs, reports
    (TaskType.DOCUMENT_ANALYSIS, re.compile(
        r"\b(contract|clause|rfp|tender|bid document|specification|spec sheet|"
        r"report|whitepaper|review (?:this|the) document|analy[sz]e (?:this|the) (?:document|pdf|contract))\b",
        re.IGNORECASE)),
    # Coding
    (TaskType.CODING, re.compile(
        r"\b(code|function|class|method|bug|stack trace|exception|"
        r"python|javascript|typescript|java|c\+\+|c#|sql|bash|powershell|"
        r"refactor|implement|debug|fix this|regex|api endpoint)\b|```",
        re.IGNORECASE)),
    # Analysis — comparison, evaluation
    (TaskType.ANALYSIS, re.compile(
        r"\b(compare|comparison|versus|vs\.?|trade[- ]?offs?|evaluate|"
        r"pros and cons|which (?:is )?(?:better|best)|rank|score|"
        r"recommend (?:between|which)|scenario)\b", re.IGNORECASE)),
    # Summarization (catch-all summarization)
    (TaskType.SUMMARIZATION, re.compile(
        r"\b(summari[sz]e|summary|tl;dr|tldr|recap|brief me|key points?|"
        r"main takeaways?)\b", re.IGNORECASE)),
]

_LLM_PROMPT = """You are a classifier. Read the user request and return JSON only.

Pick exactly one task from:
- summarization (general text summarization)
- email_summarization (analyzing an email or thread)
- meeting_minutes (extracting decisions/actions from a meeting)
- document_analysis (analyzing a contract, RFP, report, or specification)
- analysis (comparing options, evaluating trade-offs)
- coding (writing, debugging, or refactoring code)
- general (none of the above)

Respond with JSON only, no prose:
{"task": "<one of the above>", "confidence": <number 0.0-1.0>}

User request:
"""


class TaskClassifier:
    def __init__(
        self,
        provider_registry: ProviderRegistry | None = None,
        classifier_model_id: str = "gpt-4o-mini",
        classifier_provider: str = "azure_openai",
        confidence_threshold: float = 0.6,
        cache_size: int = 512,
    ) -> None:
        self._registry = provider_registry
        self._model_id = classifier_model_id
        self._provider = classifier_provider
        self._threshold = confidence_threshold
        self._cache: OrderedDict[str, ClassifierResult] = OrderedDict()
        self._cache_size = cache_size

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.sha256(text[:512].strip().lower().encode("utf-8")).hexdigest()

    def _cache_get(self, key: str) -> ClassifierResult | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _cache_put(self, key: str, value: ClassifierResult) -> None:
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def heuristic(self, text: str) -> ClassifierResult:
        """Pure-function heuristic pass. Exposed for testing."""
        if not text or not text.strip():
            return ClassifierResult(TaskType.GENERAL, 0.0, TaskSource.HEURISTIC)

        for task, pattern in _HEURISTIC_RULES:
            matches = pattern.findall(text)
            if matches:
                # Confidence scales with match count, capped at 0.9
                confidence = min(0.55 + 0.1 * len(matches), 0.9)
                return ClassifierResult(task, confidence, TaskSource.HEURISTIC)

        return ClassifierResult(TaskType.GENERAL, 0.3, TaskSource.HEURISTIC)

    async def _classify_with_llm(self, text: str) -> ClassifierResult | None:
        if not self._registry:
            return None
        try:
            req = ModelProviderRequest(
                model_id=self._model_id,
                messages=[
                    {"role": "system", "content": _LLM_PROMPT},
                    {"role": "user", "content": text[:2000]},
                ],
                max_tokens=64,
                temperature=0.0,
            )
            response = await self._registry.complete(self._provider, req)
            if not response.success or not response.content:
                return None

            content = response.content.strip()
            # Strip markdown code fences if the model wrapped JSON in them
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
                content = re.sub(r"\s*```$", "", content)

            data = json.loads(content)
            task = TaskType(data.get("task", "general"))
            confidence = float(data.get("confidence", 0.5))
            return ClassifierResult(task, confidence, TaskSource.LLM)
        except ValueError as exc:
            logger.warning("LLM classifier parse error: %s", exc)
            return None
        except Exception:
            logger.exception("LLM classifier call failed")
            return None

    async def classify(self, text: str) -> ClassifierResult:
        """Classify the user message. Always returns a result; never raises."""
        key = self._cache_key(text)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        heuristic_result = self.heuristic(text)
        if heuristic_result.confidence >= self._threshold:
            self._cache_put(key, heuristic_result)
            return heuristic_result

        llm_result = await self._classify_with_llm(text)
        result = llm_result if llm_result is not None else heuristic_result
        self._cache_put(key, result)
        return result
