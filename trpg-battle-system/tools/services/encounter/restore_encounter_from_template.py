from __future__ import annotations

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.encounter_template_repository import EncounterTemplateRepository


class RestoreEncounterFromTemplate:
    def __init__(
        self,
        encounter_repository: EncounterRepository,
        encounter_template_repository: EncounterTemplateRepository,
    ) -> None:
        self.encounter_repository = encounter_repository
        self.encounter_template_repository = encounter_template_repository

    def execute(self, *, template_id: str, target_encounter_id: str) -> Encounter:
        template = self.encounter_template_repository.get(template_id)
        if template is None:
            raise ValueError(f"template '{template_id}' not found")
        snapshot = template.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError(f"template '{template_id}' snapshot is invalid")
        encounter_data = dict(snapshot)
        encounter_data["encounter_id"] = target_encounter_id
        encounter = Encounter.from_dict(encounter_data)
        self.encounter_repository.save(encounter)
        return encounter
