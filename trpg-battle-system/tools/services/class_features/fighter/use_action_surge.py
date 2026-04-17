from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared.runtime import get_fighter_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState


class UseActionSurge:
    """结算 Fighter 的 Action Surge，授予额外非魔法动作额度。"""

    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, *, encounter_id: str, actor_id: str) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self._ensure_actor_turn(encounter, actor_id)

        fighter = get_fighter_runtime(actor)
        action_surge = fighter.get("action_surge")
        if not isinstance(action_surge, dict):
            raise ValueError("action_surge_not_available")

        remaining_uses = action_surge.get("remaining_uses")
        if not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("action_surge_no_remaining_uses")
        if bool(action_surge.get("used_this_turn")):
            raise ValueError("action_surge_already_used_this_turn")

        temporary_bonuses = fighter.get("temporary_bonuses")
        if not isinstance(temporary_bonuses, dict):
            raise ValueError("fighter_temporary_bonuses_missing")
        extra_actions = temporary_bonuses.get("extra_non_magic_action_available")
        if not isinstance(extra_actions, int):
            raise ValueError("fighter_extra_non_magic_action_available_invalid")

        temporary_bonuses["extra_non_magic_action_available"] = extra_actions + 1
        action_surge["remaining_uses"] = remaining_uses - 1
        action_surge["used_this_turn"] = True

        self.encounter_repository.save(encounter)

        return {
            "encounter_id": encounter.encounter_id,
            "actor_id": actor.entity_id,
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
