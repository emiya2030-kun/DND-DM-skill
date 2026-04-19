from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from tools.repositories.encounter_repository import EncounterRepository
from tools.repositories.encounter_template_repository import EncounterTemplateRepository


class SaveEncounterTemplate:
    def __init__(
        self,
        encounter_repository: EncounterRepository,
        encounter_template_repository: EncounterTemplateRepository,
    ) -> None:
        self.encounter_repository = encounter_repository
        self.encounter_template_repository = encounter_template_repository

    def execute(self, *, encounter_id: str, template_name: str) -> dict[str, Any]:
        normalized_name = self._normalize_template_name(template_name)
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        for template in self.encounter_template_repository.list_templates():
            if str(template.get("name") or "") == normalized_name:
                raise ValueError(f"template name '{normalized_name}' already exists")
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "template_id": f"tpl_{uuid4().hex[:12]}",
            "name": normalized_name,
            "source_encounter_id": encounter.encounter_id,
            "snapshot": encounter.to_dict(),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        return self.encounter_template_repository.save(record)

    def _normalize_template_name(self, template_name: str) -> str:
        normalized_name = str(template_name or "").strip()
        if not normalized_name:
            raise ValueError("template_name must be a non-empty string")
        return normalized_name
