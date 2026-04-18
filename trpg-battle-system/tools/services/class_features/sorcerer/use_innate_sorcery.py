from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_sorcerer_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseInnateSorcery:
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
        innate_sorcery = sorcerer.get("innate_sorcery")
        if not isinstance(innate_sorcery, dict) or not bool(innate_sorcery.get("enabled")):
            raise ValueError("innate_sorcery_not_available")
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")
        if bool(innate_sorcery.get("active")):
            raise ValueError("innate_sorcery_already_active")

        used_sorcery_points = False
        uses_current = int(innate_sorcery.get("uses_current", 0) or 0)
        if uses_current > 0:
            innate_sorcery["uses_current"] = uses_current - 1
        else:
            sorcery_points = sorcerer.get("sorcery_points")
            if int(sorcerer.get("level", 0) or 0) < 7:
                raise ValueError("innate_sorcery_no_uses_remaining")
            if not isinstance(sorcery_points, dict) or int(sorcery_points.get("current", 0) or 0) < 2:
                raise ValueError("innate_sorcery_requires_sorcery_points")
            sorcery_points["current"] = int(sorcery_points.get("current", 0) or 0) - 2
            used_sorcery_points = True

        innate_sorcery["active"] = True
        innate_sorcery["expires_at_turn"] = {"rounds_remaining": 10}
        actor.action_economy["bonus_action_used"] = True

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "innate_sorcery": {
                    "active": True,
                    "uses_current": int(innate_sorcery.get("uses_current", 0) or 0),
                    "used_sorcery_points": used_sorcery_points,
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
