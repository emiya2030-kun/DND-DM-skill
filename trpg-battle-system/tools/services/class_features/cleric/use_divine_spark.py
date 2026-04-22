from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_cleric_runtime
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class UseDivineSpark:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.update_hp = UpdateHp(encounter_repository, append_event)
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        target_id: str,
        mode: str,
        rolled_value: int,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_id, label="actor")
        target = self._get_entity_or_raise(encounter, target_id, label="target")

        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._ensure_within_range(actor, target, maximum_feet=30)

        normalized_mode = self._normalize_mode(mode)
        if not isinstance(rolled_value, int) or rolled_value < 0:
            raise ValueError("divine_spark_rolled_value_invalid")

        cleric = ensure_cleric_runtime(actor)
        channel_divinity = cleric.get("channel_divinity")
        divine_spark = cleric.get("divine_spark")
        if not isinstance(channel_divinity, dict) or not bool(channel_divinity.get("enabled")):
            raise ValueError("divine_spark_not_available")
        if not isinstance(divine_spark, dict) or not bool(divine_spark.get("enabled")):
            raise ValueError("divine_spark_not_available")

        remaining_uses = channel_divinity.get("remaining_uses")
        if not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("divine_spark_no_remaining_uses")

        wisdom_modifier = int(actor.ability_mods.get("wis", 0) or 0)
        total_points = rolled_value + wisdom_modifier
        if total_points <= 0:
            raise ValueError("divine_spark_no_effect")

        hp_change = -total_points if normalized_mode == "heal" else total_points
        reason = "cleric_divine_spark_heal" if normalized_mode == "heal" else "cleric_divine_spark_damage"
        hp_result = self.update_hp.execute(
            encounter_id=encounter_id,
            target_id=target_id,
            hp_change=hp_change,
            reason=reason,
            damage_type="radiant" if normalized_mode == "damage" else None,
            source_entity_id=actor_id,
        )

        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_id, label="actor")
        cleric = ensure_cleric_runtime(actor)
        channel_divinity = cleric.get("channel_divinity")
        if not isinstance(channel_divinity, dict):
            raise ValueError("divine_spark_not_available")

        actor.action_economy["action_used"] = True
        channel_divinity["remaining_uses"] = remaining_uses - 1
        self.encounter_repository.save(encounter)

        self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="class_feature_divine_spark_used",
            actor_entity_id=actor_id,
            target_entity_id=target_id,
            payload={
                "class_feature_id": "cleric.divine_spark",
                "mode": normalized_mode,
                "rolled_value": rolled_value,
                "wisdom_modifier": wisdom_modifier,
                "total_points": total_points,
                "remaining_uses": channel_divinity["remaining_uses"],
            },
        )

        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "target_id": target_id,
            "mode": normalized_mode,
            "rolled_value": rolled_value,
            "wisdom_modifier": wisdom_modifier,
            "total_points": total_points,
            "remaining_uses": channel_divinity["remaining_uses"],
            "hp_result": hp_result,
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str, *, label: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"{label} '{entity_id}' not found in encounter")
        return entity

    def _ensure_actor_turn(self, encounter: Encounter, actor_id: str) -> None:
        if encounter.current_entity_id != actor_id:
            raise ValueError("not_actor_turn")

    def _ensure_action_available(self, actor: EncounterEntity) -> None:
        if bool(actor.action_economy.get("action_used")):
            raise ValueError("action_already_used")

    def _ensure_within_range(self, actor: EncounterEntity, target: EncounterEntity, *, maximum_feet: int) -> None:
        dx = abs(actor.position["x"] - target.position["x"])
        dy = abs(actor.position["y"] - target.position["y"])
        if max(dx, dy) * 5 > maximum_feet:
            raise ValueError("divine_spark_target_out_of_range")

    def _normalize_mode(self, mode: str) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in {"heal", "damage"}:
            raise ValueError("divine_spark_mode_invalid")
        return normalized
