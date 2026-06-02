"""ADLS (Azure Data Lake Storage) client for audit logs and analytics.

Appends JSON-lines to date-partitioned paths for low-cost, append-only storage.
Falls back to local file logging when ADLS is not configured.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from backend.config import Settings, get_settings
from backend.models.schemas import AuditEntry, UsageRecord

logger = logging.getLogger(__name__)


class AuditLogger:
    """Appends audit and usage records to ADLS or local files."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._adls_client = None
        self._local_dir = Path("logs")

        if self._settings.adls_account_url:
            self._init_adls()
        else:
            self._local_dir.mkdir(exist_ok=True)

    def _init_adls(self) -> None:
        try:
            from azure.storage.filedatalake.aio import DataLakeServiceClient
            from azure.identity.aio import DefaultAzureCredential

            self._adls_client = DataLakeServiceClient(
                account_url=self._settings.adls_account_url,
                credential=DefaultAzureCredential(),
            )
            logger.info("ADLS client initialized")
        except Exception:
            logger.warning("ADLS unavailable — audit logs go to local files")

    async def log_audit(self, entry: AuditEntry) -> None:
        record = entry.model_dump(mode="json")
        if self._adls_client:
            await self._append_to_adls(
                self._settings.adls_audit_container,
                f"audit/{entry.timestamp:%Y/%m/%d}/events.jsonl",
                record,
            )
        else:
            self._append_local("audit", record)

    async def log_usage(self, usage: UsageRecord) -> None:
        record = usage.model_dump(mode="json")
        if self._adls_client:
            await self._append_to_adls(
                self._settings.adls_analytics_container,
                f"usage/{usage.timestamp:%Y/%m/%d}/records.jsonl",
                record,
            )
        else:
            self._append_local("usage", record)

    async def log_feedback(self, record: dict) -> None:
        if self._adls_client:
            today = datetime.utcnow().strftime("%Y/%m/%d")
            await self._append_to_adls(
                self._settings.adls_analytics_container,
                f"feedback/{today}/records.jsonl",
                record,
            )
        else:
            self._append_local("feedback", record)

    async def _append_to_adls(
        self, container: str, path: str, record: dict
    ) -> None:
        try:
            fs_client = self._adls_client.get_file_system_client(container)
            file_client = fs_client.get_file_client(path)
            data = json.dumps(record, default=str) + "\n"
            try:
                props = await file_client.get_file_properties()
                offset = props.size
            except Exception:
                await file_client.create_file()
                offset = 0
            await file_client.append_data(data.encode(), offset=offset, length=len(data))
            await file_client.flush_data(offset + len(data))
        except Exception:
            logger.exception("Failed to write to ADLS")

    def _append_local(self, category: str, record: dict) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        path = self._local_dir / f"{category}_{today}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
