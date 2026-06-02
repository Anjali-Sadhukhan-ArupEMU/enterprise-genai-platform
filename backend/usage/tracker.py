"""In-memory usage tracker for the live dashboard.

Holds the last N usage records and exposes monthly / today / last-query
aggregates. Survives the process lifetime only — production should back this
with Cosmos / ADLS reads from `AuditLogger.log_usage`.
"""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from backend.models.schemas import UsageRecord

_MAX_RECORDS = 1000
_HYDRATE_DAYS = 30

logger = logging.getLogger(__name__)


class UsageTracker:
    def __init__(self, monthly_budget_inr: float, usd_to_inr: float) -> None:
        self._lock = threading.Lock()
        self._monthly_budget_inr = monthly_budget_inr
        self._usd_to_inr = usd_to_inr
        self._records: list[dict[str, Any]] = []
        self._last_query: dict[str, Any] | None = None

    def record(self, usage: UsageRecord, latency_ms: float) -> None:
        total = usage.prompt_tokens + usage.completion_tokens
        cost_inr = usage.cost_estimate * self._usd_to_inr
        entry = {
            "timestamp": usage.timestamp,
            "model": usage.model,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": total,
            "cost_usd": usage.cost_estimate,
            "cost_inr": cost_inr,
            "latency_ms": latency_ms,
        }
        with self._lock:
            self._records.append(entry)
            if len(self._records) > _MAX_RECORDS:
                self._records.pop(0)
            self._last_query = entry

    def hydrate_from_logs(self, log_dir: Path) -> int:
        """Rebuild state from local usage_*.jsonl files written by AuditLogger.

        Called once at startup so restart doesn't zero the dashboard.
        Returns the number of records loaded.
        """
        if not log_dir.exists():
            return 0
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            days=_HYDRATE_DAYS
        )
        loaded: list[dict[str, Any]] = []
        for jsonl_file in sorted(log_dir.glob("usage_*.jsonl")):
            try:
                with jsonl_file.open(encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        try:
                            ts = datetime.fromisoformat(rec["timestamp"])
                            if ts.tzinfo is not None:
                                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
                        except Exception:
                            continue
                        if ts < cutoff:
                            continue
                        prompt = int(rec.get("prompt_tokens", 0))
                        completion = int(rec.get("completion_tokens", 0))
                        cost_usd = float(rec.get("cost_estimate", 0.0))
                        loaded.append(
                            {
                                "timestamp": ts,
                                "model": rec.get("model", "unknown"),
                                "prompt_tokens": prompt,
                                "completion_tokens": completion,
                                "total_tokens": prompt + completion,
                                "cost_usd": cost_usd,
                                "cost_inr": cost_usd * self._usd_to_inr,
                                "latency_ms": float(rec.get("latency_ms", 0.0)),
                            }
                        )
            except OSError:
                continue

        if not loaded:
            return 0

        loaded.sort(key=lambda r: r["timestamp"])
        if len(loaded) > _MAX_RECORDS:
            loaded = loaded[-_MAX_RECORDS:]

        with self._lock:
            self._records = loaded
            self._last_query = loaded[-1]

        logger.info(
            "UsageTracker hydrated %d records from %s (last %d days)",
            len(loaded),
            log_dir,
            _HYDRATE_DAYS,
        )
        return len(loaded)

    def get_summary(self) -> dict[str, Any]:
        with self._lock:
            # UsageRecord.timestamp is naive UTC (datetime.utcnow); match it.
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            monthly = [r for r in self._records if r["timestamp"] >= month_start]
            today = [r for r in self._records if r["timestamp"] >= today_start]

            monthly_cost_inr = sum(r["cost_inr"] for r in monthly)
            monthly_tokens = sum(r["total_tokens"] for r in monthly)
            today_cost_inr = sum(r["cost_inr"] for r in today)
            today_tokens = sum(r["total_tokens"] for r in today)

            by_model: dict[str, dict[str, float]] = defaultdict(
                lambda: {"tokens": 0, "cost_inr": 0.0, "requests": 0}
            )
            for r in monthly:
                m = by_model[r["model"]]
                m["tokens"] += r["total_tokens"]
                m["cost_inr"] += r["cost_inr"]
                m["requests"] += 1

            last = self._last_query
            last_serialised = None
            if last is not None:
                last_serialised = {
                    "timestamp": last["timestamp"].isoformat(),
                    "model": last["model"],
                    "prompt_tokens": last["prompt_tokens"],
                    "completion_tokens": last["completion_tokens"],
                    "total_tokens": last["total_tokens"],
                    "cost_usd": round(last["cost_usd"], 6),
                    "cost_inr": round(last["cost_inr"], 4),
                    "latency_ms": round(last["latency_ms"], 1),
                }

            return {
                "currency": "INR",
                "usd_to_inr": self._usd_to_inr,
                "monthly_budget_inr": self._monthly_budget_inr,
                "monthly": {
                    "spent_inr": round(monthly_cost_inr, 4),
                    "remaining_inr": round(
                        max(0.0, self._monthly_budget_inr - monthly_cost_inr), 4
                    ),
                    "pct_used": round(
                        min(
                            100.0,
                            (monthly_cost_inr / self._monthly_budget_inr) * 100
                            if self._monthly_budget_inr > 0
                            else 0.0,
                        ),
                        2,
                    ),
                    "tokens": monthly_tokens,
                    "requests": len(monthly),
                },
                "today": {
                    "spent_inr": round(today_cost_inr, 4),
                    "tokens": today_tokens,
                    "requests": len(today),
                },
                "last_query": last_serialised,
                "by_model": sorted(
                    [
                        {
                            "model": k,
                            "tokens": int(v["tokens"]),
                            "cost_inr": round(v["cost_inr"], 4),
                            "requests": int(v["requests"]),
                        }
                        for k, v in by_model.items()
                    ],
                    key=lambda x: -x["cost_inr"],
                )[:5],
            }
