from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import add_created_spell_slot, ensure_sorcerer_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState

CREATE_SLOT_COSTS = {
    1: {"cost": 2, "min_level": 2},
    2: {"cost": 3, "min_level": 3},
    3: {"cost": 5, "min_level": 5},
    4: {"cost": 6, "min_level": 7},
    5: {"cost": 7, "min_level": 9},
}


class CreateSpellSlotFromSorceryPoints:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        slot_level: int,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        sorcerer = ensure_sorcerer_runtime(actor)
        if int(sorcerer.get("level", 0) or 0) < 2:
            raise ValueError("font_of_magic_not_available")

        rule = CREATE_SLOT_COSTS.get(slot_level)
        if rule is None:
            raise ValueError("invalid_created_spell_slot_level")
        if int(sorcerer.get("level", 0) or 0) < int(rule["min_level"]):
            raise ValueError("created_spell_slot_level_not_available")
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

        sorcery_points = sorcerer.get("sorcery_points")
        if not isinstance(sorcery_points, dict):
            raise ValueError("sorcery_points_not_available")
        current = int(sorcery_points.get("current", 0) or 0)
        if current < int(rule["cost"]):
            raise ValueError("insufficient_sorcery_points")

        sorcery_points["current"] = current - int(rule["cost"])
        add_created_spell_slot(actor, slot_level=slot_level, amount=1)
        actor.action_economy["bonus_action_used"] = True

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "font_of_magic": {
                    "created_slot_level": slot_level,
                    "sorcery_points_after": sorcery_points["current"],
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
