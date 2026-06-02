"""Compose the final system prompt from Global + Persona + Task templates.

A per-persona admin override (`PersonaConfig.system_prompt_override`)
replaces the persona section when present.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.models.schemas import Persona, PersonaConfig, TaskType
from backend.orchestration.template_loader import TemplateLoader

_SECTION_SEP = "\n\n---\n\n"


@dataclass(frozen=True)
class ComposedPrompt:
    system_text: str
    template_id: str  # "<task_id>" — the task template drives the most specific identity
    template_version: str  # "g{global_v}-p{persona_v}-t{task_v}"


class PromptComposer:
    def __init__(self, loader: TemplateLoader) -> None:
        self._loader = loader

    def compose(
        self,
        persona: Persona,
        task: TaskType,
        persona_override: PersonaConfig | None = None,
    ) -> ComposedPrompt:
        g = self._loader.get_global()
        p = self._loader.get_persona(persona)
        t = self._loader.get_task(task)

        persona_body = p.body
        persona_version = p.version
        if persona_override and persona_override.system_prompt_override.strip():
            persona_body = persona_override.system_prompt_override
            persona_version = f"{p.version}+admin"

        system_text = _SECTION_SEP.join([g.body.strip(), persona_body.strip(), t.body.strip()])

        return ComposedPrompt(
            system_text=system_text,
            template_id=t.id,
            template_version=f"g{g.version}-p{persona_version}-t{t.version}",
        )
