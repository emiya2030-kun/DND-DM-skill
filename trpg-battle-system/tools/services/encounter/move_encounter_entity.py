from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.rules.conditions import ConditionRuntime
from tools.services.combat.rules.conditions.condition_parser import parse_condition
from tools.services.combat.attack.weapon_mastery_effects import get_weapon_mastery_speed_penalty
from tools.services.combat.shared.turn_actor_guard import resolve_current_turn_actor_or_raise
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent
from tools.services.encounter.movement_rules import get_occupied_cells, validate_movement_path
from tools.services.encounter.zones import resolve_zone_effects


class MoveEncounterEntity:
    """带规则校验的 encounter 实体移动服务。"""

    def __init__(self, repository: EncounterRepository, append_event: AppendEvent | None = None):
        self.repository = repository
        self.append_event = append_event

    def execute(
        self,
        encounter_id: str,
        entity_id: str,
        target_position: dict[str, int],
        *,
        count_movement: bool = True,
        use_dash: bool = False,
        allow_out_of_turn_actor: bool = False,
        free_movement_feet: int = 0,
    ) -> Encounter:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        entity = resolve_current_turn_actor_or_raise(
            encounter,
            actor_id=entity_id,
            allow_out_of_turn_actor=allow_out_of_turn_actor,
            entity_label="entity",
        )
        start_position = {"x": entity.position["x"], "y": entity.position["y"]}
        start_cells = get_occupied_cells(entity)

        if not isinstance(target_position, dict) or "x" not in target_position or "y" not in target_position:
            raise ValueError("invalid_target_position")
        if not isinstance(target_position["x"], int) or not isinstance(target_position["y"], int):
            raise ValueError("invalid_target_position")

        result = validate_movement_path(
            encounter=encounter,
            entity_id=entity_id,
            target_position=target_position,
            count_movement=count_movement,
            use_dash=use_dash,
        )

        runtime = self._safe_condition_runtime(entity.conditions)
        exhaustion_penalty = runtime.get_speed_penalty_feet()
        mastery_speed_penalty = get_weapon_mastery_speed_penalty(entity)
        distance_already_moved = self._movement_spent_feet(entity)
        effective_walk_speed = max(0, entity.speed["walk"] - exhaustion_penalty - mastery_speed_penalty)
        total_available_movement = effective_walk_speed * (2 if use_dash else 1)
        available_movement = max(0, total_available_movement - distance_already_moved)
        usable_free_movement_feet = max(0, free_movement_feet)
        if result.feet_cost > available_movement + usable_free_movement_feet:
            raise ValueError("insufficient_movement")

        entity.position["x"] = target_position["x"]
        entity.position["y"] = target_position["y"]
        if count_movement:
            counted_cost = max(0, result.feet_cost - usable_free_movement_feet)
            spent_after_move = distance_already_moved + counted_cost
            combat_flags = self._ensure_combat_flags_dict(entity)
            combat_flags["movement_spent_feet"] = spent_after_move
            entity.speed["remaining"] = max(0, effective_walk_speed - min(spent_after_move, effective_walk_speed))

        zone_effect_resolutions = resolve_zone_effects(
            encounter=encounter,
            entity_id=entity_id,
            trigger="enter",
            movement_history=[start_cells, *[set(step.occupied_cells) for step in result.path]],
        )

        saved = self.repository.save(encounter)
        self._append_movement_event(
            encounter=encounter,
            entity_id=entity_id,
            start_position=start_position,
            target_position={"x": target_position["x"], "y": target_position["y"]},
            result=result,
        )
        self._append_zone_effect_events(encounter=saved, resolutions=zone_effect_resolutions)
        return saved

    def execute_with_state(
        self,
        encounter_id: str,
        entity_id: str,
        target_position: dict[str, int],
        *,
        count_movement: bool = True,
        use_dash: bool = False,
        allow_out_of_turn_actor: bool = False,
        free_movement_feet: int = 0,
    ) -> dict[str, Any]:
        updated = self.execute(
            encounter_id=encounter_id,
            entity_id=entity_id,
            target_position=target_position,
            count_movement=count_movement,
            use_dash=use_dash,
            allow_out_of_turn_actor=allow_out_of_turn_actor,
            free_movement_feet=free_movement_feet,
        )
        current_entity = updated.entities[entity_id]
        return {
            "encounter_id": encounter_id,
            "entity_id": entity_id,
            "position": {"x": current_entity.position["x"], "y": current_entity.position["y"]},
            "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
        }

    def _append_zone_effect_events(self, *, encounter: Encounter, resolutions: list[dict[str, object]]) -> None:
        if self.append_event is None:
            return
        for resolution in resolutions:
            if not isinstance(resolution, dict):
                continue
            zone_id = resolution.get("zone_id")
            trigger = resolution.get("trigger")
            if not isinstance(zone_id, str) or not isinstance(trigger, str):
                continue
            self.append_event.execute(
                encounter_id=encounter.encounter_id,
                round=encounter.round,
                event_type="zone_effect_resolved",
                actor_entity_id=resolution.get("source_entity_id"),
                target_entity_id=resolution.get("target_entity_id"),
                payload=dict(resolution),
            )

    def _append_movement_event(
        self,
        *,
        encounter: Encounter,
        entity_id: str,
        start_position: dict[str, int],
        target_position: dict[str, int],
        result: Any,
    ) -> None:
        if self.append_event is None:
            return

        self.append_event.execute(
            encounter_id=encounter.encounter_id,
            round=encounter.round,
            event_type="movement_resolved",
            actor_entity_id=entity_id,
            payload={
                "from_position": start_position,
                "to_position": target_position,
                "feet_cost": result.feet_cost,
                "used_dash": result.used_dash,
                "movement_counted": result.movement_counted,
                "path": [step.anchor for step in result.path],
            },
        )

    def _safe_condition_runtime(self, conditions: list[str] | None) -> ConditionRuntime:
        validated: list[str] = []
        for condition in self._normalize_condition_values(conditions):
            try:
                parse_condition(condition)
            except (ValueError, TypeError, AttributeError):
                continue
            validated.append(condition)
        return ConditionRuntime(validated)

    def _normalize_condition_values(self, conditions: object) -> list[object]:
        if conditions is None:
            return []
        if isinstance(conditions, str):
            return [conditions]
        if isinstance(conditions, (list, tuple, set)):
            return list(conditions)
        return []

    def _movement_spent_feet(self, entity: Any) -> int:
        if entity.speed["remaining"] >= entity.speed["walk"]:
            return 0
        combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
        tracked_value = combat_flags.get("movement_spent_feet")
        if isinstance(tracked_value, int) and tracked_value >= 0:
            return tracked_value
        return max(0, entity.speed["walk"] - entity.speed["remaining"])

    def _ensure_combat_flags_dict(self, entity: Any) -> dict[str, Any]:
        if not isinstance(entity.combat_flags, dict):
            entity.combat_flags = {}
        return entity.combat_flags
