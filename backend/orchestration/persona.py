"""Persona resolution from Entra group membership.

Reads `config/personas.yaml` at startup. Resolves a `UserContext`'s groups
to a single `Persona` using priority order (lower wins). Unknown groups
fall through to the configured default.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from backend.config import Settings, get_settings
from backend.models.schemas import Persona

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = "config/personas.yaml"


class PersonaResolver:
    def __init__(self, config_path: str | None = None, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._config_path = Path(config_path or _DEFAULT_CONFIG_PATH)
        self._default: Persona = Persona.CASUAL
        # Ordered list of (priority, persona, group_names_lower, group_ids)
        self._mappings: list[tuple[int, Persona, set[str], set[str]]] = []
        self._load()

    def _load(self) -> None:
        if not self._config_path.exists():
            logger.warning("personas.yaml not found at %s — using built-in defaults", self._config_path)
            self._default = Persona.CASUAL
            self._mappings = []
            return

        data = yaml.safe_load(self._config_path.read_text(encoding="utf-8")) or {}
        default_str = data.get("default_persona", "casual")
        try:
            self._default = Persona(default_str)
        except ValueError:
            logger.error("Unknown default_persona '%s' — falling back to casual", default_str)
            self._default = Persona.CASUAL

        mappings: list[tuple[int, Persona, set[str], set[str]]] = []
        for entry in data.get("mappings", []):
            try:
                persona = Persona(entry["persona"])
            except (KeyError, ValueError):
                logger.warning("Skipping invalid persona entry: %s", entry)
                continue
            priority = int(entry.get("priority", 100))
            names = {str(n).strip().lower() for n in entry.get("group_names", []) if n}
            ids = {str(i).strip() for i in entry.get("group_ids", []) if i}
            mappings.append((priority, persona, names, ids))

        mappings.sort(key=lambda m: m[0])
        self._mappings = mappings
        logger.info("PersonaResolver loaded %d mappings, default=%s", len(mappings), self._default.value)

    def reload(self) -> None:
        self._load()

    def resolve(self, groups: list[str]) -> Persona:
        """Pick the persona for the given Entra group memberships.

        `groups` may contain display names or object IDs (Entra returns IDs;
        APIM may forward names). Matching is case-insensitive on names.
        """
        if not groups:
            return self._default

        user_names = {str(g).strip().lower() for g in groups if g}
        user_ids = {str(g).strip() for g in groups if g}

        for _priority, persona, names, ids in self._mappings:
            if names & user_names or ids & user_ids:
                return persona

        return self._default

    @property
    def default(self) -> Persona:
        return self._default
