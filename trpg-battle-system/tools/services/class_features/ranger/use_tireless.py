from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_ranger_runtime
from tools.services.combat.shared.grant_temporary_hp import GrantTemporaryHp
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseTireless:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.get_encounter_state = GetEncounterState(encounter_repository)
        self.grant_temporary_hp = GrantTemporaryHp(encounter_repository, append_event)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        temp_hp_roll: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)

        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)

        ranger = ensure_ranger_runtime(actor)
        tireless = ranger.get("tireless")
        if not isinstance(tireless, dict) or not bool(tireless.get("enabled")):
            raise ValueError("tireless_not_available")

        remaining_uses = tireless.get("temp_hp_uses_remaining")
        if not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("tireless_no_remaining_uses")

        rolled_total = self._sum_rolls(temp_hp_roll)
        wisdom_modifier = max(1, int(actor.ability_mods.get("wis", 0) or 0))
        gained_temp_hp = rolled_total + wisdom_modifier
        previous_temp_hp = int(actor.hp.get("temp", 0) or 0)
        actor.action_economy["action_used"] = True
        tireless["temp_hp_uses_remaining"] = remaining_uses - 1
        self.encounter_repository.save(encounter)

        temp_hp_result = self.grant_temporary_hp.execute(
            encounter_id=encounter_id,
            target_id=actor.entity_id,
            temp_hp_amount=gained_temp_hp,
            reason="ranger_tireless",
            source_entity_id=actor.entity_id,
            mode="auto_higher",
        )

        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_actor_or_raise(encounter, actor_id)
        self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type="class_feature_tireless_used",
            actor_entity_id=actor.entity_id,
            target_entity_id=actor.entity_id,
            payload={
                "class_feature_id": "ranger.tireless",
                "temp_hp_roll_total": rolled_total,
                "wisdom_modifier": wisdom_modifier,
                "temp_hp_gained": gained_temp_hp,
                "temp_hp_before": previous_temp_hp,
                "temp_hp_after": temp_hp_result["temp_hp_after"],
                "temp_hp_decision": temp_hp_result["decision"],
                "uses_remaining": tireless["temp_hp_uses_remaining"],
            },
        )

        return {
            "encounter_id": encounter.encounter_id,
            "actor_id": actor.entity_id,
            "class_feature_result": {
                "tireless": {
                    "temp_hp_roll_total": rolled_total,
                    "wisdom_modifier": wisdom_modifier,
                    "temp_hp_gained": gained_temp_hp,
                    "temp_hp_before": previous_temp_hp,
                    "temp_hp_after": temp_hp_result["temp_hp_after"],
                    "temp_hp_decision": temp_hp_result["decision"],
                    "uses_remaining": tireless["temp_hp_uses_remaining"],
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

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")

    def _sum_rolls(self, temp_hp_roll: dict[str, Any] | None) -> int:
        if temp_hp_roll is None:
            return 0
        rolls = temp_hp_roll.get("rolls") if isinstance(temp_hp_roll, dict) else None
        if not isinstance(rolls, list):
            raise ValueError("temp_hp_roll.rolls must be a list")
        total = 0
        for roll in rolls:
            if not isinstance(roll, int):
                raise ValueError("temp_hp_roll.rolls must contain integers")
            total += roll
        return total
