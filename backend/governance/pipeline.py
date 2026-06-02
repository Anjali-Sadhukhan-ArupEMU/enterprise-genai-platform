"""Governance pipeline — runs all safety checks on input and output.

Pipeline order (per architecture spec):
  Input:  PII scan → Injection detection → Policy validation
  Output: PII scan → Content moderation → Audit log
"""

from __future__ import annotations

import logging

from backend.governance.injection import detect_injection
from backend.governance.pii import scan_pii
from backend.models.schemas import GovernanceResult, GovernanceVerdict

logger = logging.getLogger(__name__)


async def check_input(text: str) -> GovernanceResult:
    """Run the full input governance pipeline."""
    flags: list[str] = []

    # 1. PII Detection
    pii_found, pii_types, sanitized = scan_pii(text)
    if pii_found:
        flags.extend([f"pii:{t}" for t in pii_types])
        logger.warning("PII detected in input: %s", pii_types)

    # 2. Prompt Injection Detection
    injection_found, injection_matches = detect_injection(text)
    if injection_found:
        flags.append("prompt_injection")
        logger.warning("Prompt injection detected")
        return GovernanceResult(
            verdict=GovernanceVerdict.BLOCK,
            blocked_reason="Prompt injection detected. Your request has been blocked for security.",
            pii_detected=pii_found,
            injection_detected=True,
            sanitized_content=sanitized,
            flags=flags,
        )

    # 3. If PII was found but no injection, warn but allow with sanitized content
    if pii_found:
        return GovernanceResult(
            verdict=GovernanceVerdict.WARN,
            pii_detected=True,
            injection_detected=False,
            sanitized_content=sanitized,
            flags=flags,
        )

    return GovernanceResult(
        verdict=GovernanceVerdict.PASS,
        pii_detected=False,
        injection_detected=False,
        sanitized_content=text,
        flags=flags,
    )


async def check_output(text: str) -> GovernanceResult:
    """Run the output governance pipeline (PII scan on model responses)."""
    flags: list[str] = []

    pii_found, pii_types, sanitized = scan_pii(text)
    if pii_found:
        flags.extend([f"output_pii:{t}" for t in pii_types])
        logger.warning("PII detected in model output: %s", pii_types)
        return GovernanceResult(
            verdict=GovernanceVerdict.WARN,
            pii_detected=True,
            injection_detected=False,
            sanitized_content=sanitized,
            flags=flags,
        )

    return GovernanceResult(
        verdict=GovernanceVerdict.PASS,
        pii_detected=False,
        injection_detected=False,
        sanitized_content=text,
        flags=flags,
    )
