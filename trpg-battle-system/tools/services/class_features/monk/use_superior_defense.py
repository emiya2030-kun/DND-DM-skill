from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_monk_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState

_SUPERIOR_DEFENSE_DAMAGE_TYPES = [
    "acid",
    "bludgeoning",
    "cold",
    "fire",
    "lightning",
    "necrotic",
    "piercing",
    "poison",
    "psychic",
    "radiant",
    "slashing",
    "thunder",
]


class UseSuperiorDefense:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)

        monk = ensure_monk_runtime(actor)
        superior_defense = monk.get("superior_defense")
        if not isinstance(superior_defense, dict) or not bool(superior_defense.get("enabled")):
            raise ValueError("superior_defense_not_available")
        if bool(superior_defense.get("active")):
            raise ValueError("superior_defense_already_active")

        focus_points = monk.get("focus_points")
        if not isinstance(focus_points, dict):
            raise ValueError("superior_defense_requires_focus_points")
        remaining = focus_points.get("remaining")
        focus_cost = superior_defense.get("focus_cost")
        if not isinstance(remaining, int) or not isinstance(focus_cost, int) or remaining < focus_cost:
            raise ValueError("superior_defense_requires_focus_points")

        focus_points["remaining"] = remaining - focus_cost
        superior_defense["active"] = True
        superior_defense["remaining_rounds"] = int(superior_defense.get("duration_rounds", 10) or 10)

        existing_resistances = {
            str(value).strip().lower() for value in actor.resistances if isinstance(value, str) and str(value).strip()
        }
        added_resistances = [damage_type for damage_type in _SUPERIOR_DEFENSE_DAMAGE_TYPES if damage_type not in existing_resistances]
        actor.resistances = sorted(existing_resistances.union(_SUPERIOR_DEFENSE_DAMAGE_TYPES))
        superior_defense["added_resistances"] = added_resistances

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "class_feature_result": {
                "superior_defense": {
                    "focus_spent": focus_cost,
                    "remaining_rounds": superior_defense["remaining_rounds"],
                    "added_resistances": list(added_resistances),
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

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")
