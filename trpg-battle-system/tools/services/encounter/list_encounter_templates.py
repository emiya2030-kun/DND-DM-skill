from __future__ import annotations

from typing import Any

from tools.repositories.encounter_template_repository import EncounterTemplateRepository


class ListEncounterTemplates:
    def __init__(self, encounter_template_repository: EncounterTemplateRepository) -> None:
        self.encounter_template_repository = encounter_template_repository

    def execute(self) -> list[dict[str, Any]]:
        return self.encounter_template_repository.list_templates()
