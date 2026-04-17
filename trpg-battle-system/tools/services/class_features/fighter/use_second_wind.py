from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared.runtime import get_fighter_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseSecondWind:
    """结算 Fighter 的 Second Wind 并返回 Tactical Shift 的移动额度。"""

    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        healing_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)

        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_bonus_action_available(actor)

        fighter_state = get_fighter_runtime(actor)
        second_wind = fighter_state.get("second_wind")
        if not isinstance(second_wind, dict):
            raise ValueError("second_wind_not_available")
        remaining_uses = second_wind.get("remaining_uses")
        if not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("second_wind_no_remaining_uses")

        healed_hp = self._resolve_healing_amount(healing_roll, fighter_state)
        hp_before = actor.hp["current"]
        actor.hp["current"] = min(actor.hp["max"], hp_before + healed_hp)
        actor.action_economy["bonus_action_used"] = True
        second_wind["remaining_uses"] = remaining_uses - 1

        self.encounter_repository.save(encounter)
        self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type="class_feature_second_wind_used",
            actor_entity_id=actor.entity_id,
            target_entity_id=actor.entity_id,
            payload={
                "class_feature_id": "fighter.second_wind",
                "hp_before": hp_before,
                "hp_after": actor.hp["current"],
                "healing_applied": actor.hp["current"] - hp_before,
                "remaining_uses": second_wind["remaining_uses"],
            },
        )

        return {
            "encounter_id": encounter.encounter_id,
            "actor_id": actor.entity_id,
            "class_feature_result": {
                "healing": {
                    "roll_total": self._sum_rolls(healing_roll),
                    "fighter_level": self._fighter_level(fighter_state),
                    "total": healed_hp,
                    "hp_before": hp_before,
                    "hp_after": actor.hp["current"],
                },
                "free_movement_after_second_wind": {
                    "feet": actor.speed["walk"] // 2,
                    "ignore_opportunity_attacks": True,
                },
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

    def _ensure_bonus_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("bonus_action_used")):
            raise ValueError("bonus_action_already_used")

    def _resolve_healing_amount(self, healing_roll: dict[str, Any] | None, fighter_state: dict[str, Any]) -> int:
        return self._sum_rolls(healing_roll) + self._fighter_level(fighter_state)

    def _sum_rolls(self, healing_roll: dict[str, Any] | None) -> int:
        if healing_roll is None:
            return 0
        rolls = healing_roll.get("rolls") if isinstance(healing_roll, dict) else None
        if not isinstance(rolls, list):
            raise ValueError("healing_roll.rolls must be a list")
        total = 0
        for roll in rolls:
            if not isinstance(roll, int):
                raise ValueError("healing_roll.rolls must contain integers")
            total += roll
        return total

    def _fighter_level(self, fighter_state: dict[str, Any]) -> int:
        level = fighter_state.get("level", fighter_state.get("fighter_level", 0))
        if not isinstance(level, int) or level < 0:
            raise ValueError("fighter_level_invalid")
        return level
