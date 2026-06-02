"""Loads versioned prompt templates from `config/prompts/`.

Layout:
  config/prompts/global.yaml
  config/prompts/personas/<persona>.yaml
  config/prompts/tasks/<task>.yaml

Fails loudly at startup if a required template is missing or malformed —
runtime callers can rely on `get_persona()` / `get_task()` returning a value.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from backend.models.schemas import Persona, PromptTemplate, TaskType

logger = logging.getLogger(__name__)

_DEFAULT_PROMPTS_DIR = "config/prompts"


class TemplateLoadError(RuntimeError):
    pass


class TemplateLoader:
    def __init__(self, prompts_dir: str | None = None) -> None:
        self._dir = Path(prompts_dir or _DEFAULT_PROMPTS_DIR)
        self._global: PromptTemplate | None = None
        self._personas: dict[Persona, PromptTemplate] = {}
        self._tasks: dict[TaskType, PromptTemplate] = {}
        self.load()

    def load(self) -> None:
        if not self._dir.exists():
            raise TemplateLoadError(f"Prompts directory not found: {self._dir}")

        # Global
        global_path = self._dir / "global.yaml"
        if not global_path.exists():
            raise TemplateLoadError(f"Missing required template: {global_path}")
        self._global = self._read(global_path, scope="global")

        # Personas — one file per Persona enum value (required)
        personas_dir = self._dir / "personas"
        if not personas_dir.exists():
            raise TemplateLoadError(f"Missing required directory: {personas_dir}")
        personas: dict[Persona, PromptTemplate] = {}
        for persona in Persona:
            path = personas_dir / f"{persona.value}.yaml"
            if not path.exists():
                raise TemplateLoadError(f"Missing persona template: {path}")
            personas[persona] = self._read(path, scope="persona", key=persona.value)
        self._personas = personas

        # Tasks — one file per TaskType enum value (required)
        tasks_dir = self._dir / "tasks"
        if not tasks_dir.exists():
            raise TemplateLoadError(f"Missing required directory: {tasks_dir}")
        tasks: dict[TaskType, PromptTemplate] = {}
        for task in TaskType:
            path = tasks_dir / f"{task.value}.yaml"
            if not path.exists():
                raise TemplateLoadError(f"Missing task template: {path}")
            tasks[task] = self._read(path, scope="task", key=task.value)
        self._tasks = tasks

        logger.info(
            "TemplateLoader loaded global + %d personas + %d tasks",
            len(self._personas),
            len(self._tasks),
        )

    def reload(self) -> None:
        self.load()

    def _read(self, path: Path, scope: str, key: str = "") -> PromptTemplate:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise TemplateLoadError(f"Invalid YAML in {path}: {exc}") from exc

        body = data.get("body", "")
        if not body or not str(body).strip():
            raise TemplateLoadError(f"Template {path} has empty body")

        return PromptTemplate(
            id=str(data.get("id") or f"{scope}/{key or path.stem}"),
            version=str(data.get("version", "1")),
            body=str(body),
            scope=scope,
            key=key,
        )

    def get_global(self) -> PromptTemplate:
        assert self._global is not None  # guaranteed by load()
        return self._global

    def get_persona(self, persona: Persona) -> PromptTemplate:
        return self._personas[persona]

    def get_task(self, task: TaskType) -> PromptTemplate:
        return self._tasks[task]
