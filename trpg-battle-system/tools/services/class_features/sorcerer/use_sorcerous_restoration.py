from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_sorcerer_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseSorcerousRestoration:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        sorcerer = ensure_sorcerer_runtime(actor)
        restoration = sorcerer.get("sorcerous_restoration")
        if not isinstance(restoration, dict) or not bool(restoration.get("enabled")):
            raise ValueError("sorcerous_restoration_not_available")
        if bool(restoration.get("used_since_long_rest")):
            raise ValueError("sorcerous_restoration_already_used")

        level = int(sorcerer.get("level", 0) or 0)
        restore_cap = level // 2
        sorcery_points = sorcerer.get("sorcery_points")
        if not isinstance(sorcery_points, dict):
            raise ValueError("sorcery_points_not_available")
        current = int(sorcery_points.get("current", 0) or 0)
        maximum = int(sorcery_points.get("max", 0) or 0)
        restored = min(restore_cap, max(0, maximum - current))
        sorcery_points["current"] = current + restored
        restoration["used_since_long_rest"] = True

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "sorcerous_restoration": {
                    "restored_points": restored,
                    "sorcery_points_after": sorcery_points["current"],
                    "used_since_long_rest": True,
                }
            },
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_actor_or_raise(self, encounter: Encounter, actor_id: str) -> EncounterEntity:
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")
        return actor
