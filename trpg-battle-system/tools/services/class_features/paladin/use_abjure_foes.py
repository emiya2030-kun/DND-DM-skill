from __future__ import annotations

import math
import random
from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_paladin_runtime, resolve_entity_save_proficiencies
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.movement_rules import get_center_position, get_occupied_cells


class UseAbjureFoes:
    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        target_ids: list[str],
        save_rolls: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_id, label="actor")
        self._ensure_actor_turn(encounter, actor_id)
        self._ensure_action_available(actor)
        self._validate_target_ids(target_ids)

        paladin = ensure_paladin_runtime(actor)
        level = int(paladin.get("level", 0) or 0)
        if level < 9:
            raise ValueError("abjure_foes_unavailable")

        channel_divinity = paladin.get("channel_divinity")
        if not isinstance(channel_divinity, dict):
            raise ValueError("channel_divinity_unavailable")
        remaining_uses = int(channel_divinity.get("remaining_uses", 0) or 0)
        if remaining_uses <= 0:
            raise ValueError("channel_divinity_depleted")

        max_targets = max(1, int(actor.ability_mods.get("cha", 0) or 0))
        if len(target_ids) > max_targets:
            raise ValueError("too_many_targets")

        save_dc = 8 + int(actor.proficiency_bonus or 0) + int(actor.ability_mods.get("cha", 0) or 0)
        results: list[dict[str, Any]] = []

        for target_id in target_ids:
            target = self._get_entity_or_raise(encounter, target_id, label="target")
            self._validate_target(encounter=encounter, actor=actor, target=target)
            if self._is_covered_by_aura_of_courage(encounter=encounter, target=target):
                results.append({"target_id": target_id, "outcome": "suppressed_by_aura_of_courage"})
                continue
            save_total = self._resolve_save_total(target=target, target_id=target_id, save_rolls=save_rolls)
            if save_total < save_dc:
                frightened_condition = f"frightened:{actor.entity_id}"
                if frightened_condition not in target.conditions:
                    target.conditions.append(frightened_condition)
                target.turn_effects.append(
                    {
                        "effect_id": f"effect_abjure_foes_{uuid4().hex[:12]}",
                        "effect_type": "abjure_foes_restriction",
                        "source_entity_id": actor.entity_id,
                        "source_ref": "paladin:abjure_foes",
                        "ends_on_damage": True,
                        "duration_rounds": 10,
                    }
                )
                results.append({"target_id": target_id, "outcome": "failed_save", "save_total": save_total})
            else:
                results.append({"target_id": target_id, "outcome": "saved", "save_total": save_total})

        actor.action_economy["action_used"] = True
        channel_divinity["remaining_uses"] = remaining_uses - 1
        self.encounter_repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "action_consumed": True,
            "channel_divinity_remaining": channel_divinity["remaining_uses"],
            "save_dc": save_dc,
            "targets": results,
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

    def _validate_target_ids(self, target_ids: list[str]) -> None:
        if not isinstance(target_ids, list) or not target_ids:
            raise ValueError("target_ids_invalid")
        normalized: set[str] = set()
        for target_id in target_ids:
            if not isinstance(target_id, str) or not target_id.strip():
                raise ValueError("target_ids_invalid")
            if target_id in normalized:
                raise ValueError("duplicate_target_ids")
            normalized.add(target_id)

    def _validate_target(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        target: EncounterEntity,
    ) -> None:
        if target.entity_id == actor.entity_id:
            raise ValueError("target_must_be_other_creature")
        if target.side == actor.side:
            raise ValueError("target_must_be_enemy")
        if self._distance_feet(actor, target) > 60:
            raise ValueError("target_out_of_range")
        self._ensure_line_of_sight(encounter=encounter, actor=actor, target=target)

    def _resolve_save_total(
        self,
        *,
        target: EncounterEntity,
        target_id: str,
        save_rolls: dict[str, int] | None,
    ) -> int:
        if isinstance(save_rolls, dict) and target_id in save_rolls:
            base_roll = int(save_rolls[target_id])
        else:
            base_roll = random.randint(1, 20)
        wisdom_mod = int(target.ability_mods.get("wis", 0) or 0)
        proficiency_bonus = int(target.proficiency_bonus or 0) if "wis" in resolve_entity_save_proficiencies(target) else 0
        return base_roll + wisdom_mod + proficiency_bonus

    def _distance_feet(self, actor: EncounterEntity, target: EncounterEntity) -> int:
        dx = abs(actor.position["x"] - target.position["x"])
        dy = abs(actor.position["y"] - target.position["y"])
        return max(dx, dy) * 5

    def _ensure_line_of_sight(self, *, encounter: Encounter, actor: EncounterEntity, target: EncounterEntity) -> None:
        blocking_cells = {
            (terrain["x"], terrain["y"])
            for terrain in encounter.map.terrain
            if isinstance(terrain.get("x"), int)
            and isinstance(terrain.get("y"), int)
            and (terrain.get("blocks_los") or terrain.get("type") == "wall")
        }
        if not blocking_cells:
            return

        actor_cells = get_occupied_cells(actor)
        target_cells = get_occupied_cells(target)
        source = get_center_position(actor)
        destination = get_center_position(target)
        steps = max(int(math.ceil(max(abs(destination["x"] - source["x"]), abs(destination["y"] - source["y"])) * 4)), 1)

        for index in range(1, steps):
            ratio = index / steps
            sample_x = source["x"] + (destination["x"] - source["x"]) * ratio
            sample_y = source["y"] + (destination["y"] - source["y"]) * ratio
            cell = (math.floor(sample_x + 0.5), math.floor(sample_y + 0.5))
            if cell in actor_cells or cell in target_cells:
                continue
            if cell in blocking_cells:
                raise ValueError("blocked_by_line_of_sight")

    def _is_covered_by_aura_of_courage(self, *, encounter: Encounter, target: EncounterEntity) -> bool:
        for entity in encounter.entities.values():
            if entity.entity_id == target.entity_id:
                continue
            if entity.side != target.side:
                continue
            if isinstance(entity.conditions, list) and "incapacitated" in entity.conditions:
                continue
            paladin = ensure_paladin_runtime(entity)
            aura = paladin.get("aura_of_courage")
            if not isinstance(aura, dict) or not bool(aura.get("enabled")):
                continue
            radius_feet = int(aura.get("radius_feet", 10) or 10)
            if self._distance_feet(entity, target) <= radius_feet:
                return True
        return False
