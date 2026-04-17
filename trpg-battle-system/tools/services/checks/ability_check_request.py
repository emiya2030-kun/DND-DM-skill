from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.checks.check_catalog import normalize_check_name


class AbilityCheckRequest:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        check_type: str,
        check: str,
        dc: int,
        vantage: str = "normal",
        reason: str | None = None,
        class_feature_options: dict[str, Any] | None = None,
    ) -> RollRequest:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_id)
        if not isinstance(dc, int):
            raise ValueError("dc must be an integer")
        if vantage not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("vantage must be 'normal', 'advantage', or 'disadvantage'")

        normalized_check_type = str(check_type).strip().lower()
        normalized_check = normalize_check_name(normalized_check_type, str(check))

        return RollRequest(
            request_id=f"req_check_{uuid4().hex[:12]}",
            encounter_id=encounter.encounter_id,
            actor_entity_id=actor.entity_id,
            roll_type="ability_check",
            formula="1d20+check_modifier",
            reason=reason or f"{actor.name} makes a {normalized_check_type} check",
            context={
                "check_type": normalized_check_type,
                "check": normalized_check,
                "dc": dc,
                "vantage": vantage,
                "class_feature_options": dict(class_feature_options or {}),
            },
        )

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity
