"""Prompt injection detection.

Lightweight heuristic detection for Phase 1.
Phase 2+: integrate Azure AI Content Safety or a fine-tuned classifier.
"""

from __future__ import annotations

import re

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?above\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"<\|im_end\|>", re.IGNORECASE),
    re.compile(r"\bDAN\b.*\bjailbreak\b", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+(are|have)\s+no\s+restrictions", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+have\s+no\s+(guidelines|rules)", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+(system|initial)\s+prompt", re.IGNORECASE),
]


def detect_injection(text: str) -> tuple[bool, list[str]]:
    """Return (injection_detected, matched_pattern_descriptions)."""
    matches: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            matches.append(pattern.pattern)
    return bool(matches), matches
