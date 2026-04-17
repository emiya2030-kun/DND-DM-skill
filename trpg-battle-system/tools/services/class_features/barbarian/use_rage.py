from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.move_encounter_entity import MoveEncounterEntity


class UseRage:
    def __init__(
        self,
        encounter_repository: EncounterRepository,
        move_service: MoveEncounterEntity | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.move_service = move_service or MoveEncounterEntity(encounter_repository)
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        entity_id: str,
        extend_only: bool = False,
        pounce_path: list[list[int]] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, entity_id)
        self._ensure_actor_turn(encounter, entity_id)
        self._ensure_bonus_action_available(actor)
        self._ensure_not_heavy_armor(actor)

        barbarian = ensure_barbarian_runtime(actor)
        rage = barbarian["rage"]

        if extend_only:
            if not rage.get("active"):
                raise ValueError("rage_not_active")
        else:
            remaining = int(rage.get("remaining", 0) or 0)
            if remaining <= 0:
                raise ValueError("rage_no_remaining_uses")
            rage["remaining"] = remaining - 1
            rage["active"] = True
            if bool(actor.combat_flags.get("is_concentrating")):
                actor.combat_flags["is_concentrating"] = False

        actor.action_economy["bonus_action_used"] = True
        actor.combat_flags["rage_extended_by_bonus_action_this_turn"] = True
        rage["ends_at_turn_end_of"] = actor.entity_id

        if pounce_path:
            final_step = pounce_path[-1]
            if (
                not isinstance(final_step, list)
                or len(final_step) != 2
                or not isinstance(final_step[0], int)
                or not isinstance(final_step[1], int)
            ):
                raise ValueError("invalid_pounce_path")
            self.move_service.execute(
                encounter_id=encounter_id,
                entity_id=entity_id,
                target_position={"x": final_step[0], "y": final_step[1]},
                free_movement_feet=max(0, int(actor.speed.get("walk", 0) / 2)),
            )
            encounter = self._get_encounter_or_raise(encounter_id)

        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "entity_id": entity_id,
            "class_feature_result": {
                "rage": {
                    "active": True,
                    "extend_only": extend_only,
                    "instinctive_pounce_used": bool(pounce_path),
                }
            },
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

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

    def _ensure_actor_turn(self, encounter: Encounter, entity_id: str) -> None:
        if encounter.current_entity_id != entity_id:
            raise ValueError("not_actor_turn")

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _ensure_not_heavy_armor(self, actor: EncounterEntity) -> None:
        armor = actor.equipped_armor
        if not isinstance(armor, dict):
            return
        category = armor.get("category")
        if isinstance(category, str) and category.strip().lower() == "heavy":
            raise ValueError("rage_blocked_by_heavy_armor")
