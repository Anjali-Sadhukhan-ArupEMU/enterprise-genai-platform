"""PII detection utilities.

Phase 1: regex-based PII detection for common patterns.
Phase 2+: swap in Azure AI Content Safety PII endpoint for managed detection.
"""

from __future__ import annotations

import re

# Compiled once at module load
_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d[ -]*?){13,19}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("phone_us", re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("ip_address", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]

_MASK = "[REDACTED]"


def scan_pii(text: str) -> tuple[bool, list[str], str]:
    """Return (pii_found, list_of_types, sanitized_text)."""
    found_types: list[str] = []
    sanitized = text
    for pii_type, pattern in _PII_PATTERNS:
        if pattern.search(sanitized):
            found_types.append(pii_type)
            sanitized = pattern.sub(_MASK, sanitized)
    return bool(found_types), found_types, sanitized
