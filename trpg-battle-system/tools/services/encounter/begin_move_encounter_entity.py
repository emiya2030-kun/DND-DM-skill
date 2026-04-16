from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.rules.conditions import ConditionRuntime
from tools.services.combat.rules.conditions.condition_parser import parse_condition
from tools.services.combat.rules.opportunity_attacks import build_opportunity_request
from tools.services.combat.attack.weapon_mastery_effects import get_weapon_mastery_speed_penalty
from tools.services.combat.shared.turn_actor_guard import (
    get_entity_or_raise,
    resolve_current_turn_actor_or_raise,
)
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.movement_rules import (
    MovementValidationResult,
    get_center_position,
    validate_movement_path,
)
from tools.services.events.append_event import AppendEvent


class BeginMoveEncounterEntity:
    """开启一次可能被反应中断的移动流程。"""

    def __init__(self, repository: EncounterRepository, append_event: AppendEvent | None = None):
        self.repository = repository
        self.append_event = append_event

    def execute_with_state(
        self,
        *,
        encounter_id: str,
        entity_id: str,
        target_position: dict[str, int],
        count_movement: bool = True,
        use_dash: bool = False,
        allow_out_of_turn_actor: bool = False,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        mover = resolve_current_turn_actor_or_raise(
            encounter,
            actor_id=entity_id,
            allow_out_of_turn_actor=allow_out_of_turn_actor,
            entity_label="entity",
        )
        start_position = {"x": mover.position["x"], "y": mover.position["y"]}
        result = validate_movement_path(
            encounter=encounter,
            entity_id=entity_id,
            target_position=target_position,
            count_movement=count_movement,
            use_dash=use_dash,
        )
        self._ensure_movement_available(mover, result, use_dash)

        first_trigger = self._find_first_opportunity_trigger(encounter, mover, result)
        if first_trigger is None:
            mover.position = {"x": target_position["x"], "y": target_position["y"]}
            self._apply_movement_progress(mover, result.feet_cost, use_dash, count_movement)
            self.repository.save(encounter)
            return {
                "encounter_id": encounter_id,
                "entity_id": entity_id,
                "movement_status": "completed",
                "reaction_requests": [],
                "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
            }

        mover.position = dict(first_trigger["trigger_position"])
        self._apply_movement_progress(mover, int(first_trigger["feet_spent_before_trigger"]), use_dash, count_movement)
        request = first_trigger["request"]
        encounter.reaction_requests.append(request)
        encounter.pending_movement = {
            "movement_id": f"move_{uuid4().hex[:12]}",
            "entity_id": mover.entity_id,
            "start_position": start_position,
            "target_position": {"x": target_position["x"], "y": target_position["y"]},
            "current_position": dict(first_trigger["trigger_position"]),
            "remaining_path": first_trigger["remaining_path"],
            "count_movement": count_movement,
            "use_dash": use_dash,
            "status": "waiting_reaction",
            "waiting_request_id": request["request_id"],
        }
        self.repository.save(encounter)
        return {
            "encounter_id": encounter_id,
            "entity_id": entity_id,
            "movement_status": "waiting_reaction",
            "reaction_requests": [request],
            "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
        }

    def _find_first_opportunity_trigger(
        self,
        encounter: Encounter,
        mover: EncounterEntity,
        movement: MovementValidationResult,
        *,
        ignored_actor_entity_ids_for_first_step: set[str] | None = None,
    ) -> dict[str, Any] | None:
        current_anchor = {"x": mover.position["x"], "y": mover.position["y"]}
        feet_spent_before_trigger = 0
        ignored_ids = ignored_actor_entity_ids_for_first_step or set()
        for index, step in enumerate(movement.path):
            next_anchor = step.anchor
            for candidate in encounter.entities.values():
                if candidate.entity_id == mover.entity_id:
                    continue
                if index == 0 and candidate.entity_id in ignored_ids:
                    continue
                if not self._is_enemy_pair(mover, candidate):
                    continue
                if bool(candidate.action_economy.get("reaction_used")):
                    continue
                if not self._can_make_opportunity_attack(candidate):
                    continue
                weapon = self._get_first_melee_weapon(candidate)
                if weapon is None:
                    continue
                if self._leaves_melee_reach(candidate, mover, current_anchor, next_anchor):
                    return {
                        "trigger_position": dict(current_anchor),
                        "feet_spent_before_trigger": feet_spent_before_trigger,
                        "remaining_path": [dict(path_step.anchor) for path_step in movement.path[index:]],
                        "request": build_opportunity_request(
                            actor=candidate,
                            target=mover,
                            trigger_position=dict(current_anchor),
                            weapon={"weapon_id": weapon["weapon_id"], "name": weapon["name"]},
                        ),
                    }
            feet_spent_before_trigger += step.feet_cost
            current_anchor = dict(next_anchor)
        return None

    def _leaves_melee_reach(
        self,
        attacker: EncounterEntity,
        mover: EncounterEntity,
        current_anchor: dict[str, int],
        next_anchor: dict[str, int],
    ) -> bool:
        attacker_center = get_center_position(attacker)
        current_center = get_center_position(mover, current_anchor)
        next_center = get_center_position(mover, next_anchor)
        return self._distance_feet(attacker_center, current_center) <= 5 and self._distance_feet(attacker_center, next_center) > 5

    def _distance_feet(self, source: dict[str, float], target: dict[str, float]) -> int:
        dx = abs(source["x"] - target["x"])
        dy = abs(source["y"] - target["y"])
        return int(max(dx, dy) * 5)

    def _is_enemy_pair(self, mover: EncounterEntity, candidate: EncounterEntity) -> bool:
        return mover.side != candidate.side

    def _get_first_melee_weapon(self, entity: EncounterEntity) -> dict[str, Any] | None:
        for weapon in entity.weapons:
            weapon_range = weapon.get("range", {})
            normal_range = int(weapon_range.get("normal", 0) or 0)
            if normal_range <= 10:
                return weapon
        return None

    def _can_make_opportunity_attack(self, entity: EncounterEntity) -> bool:
        runtime = self._safe_condition_runtime(entity.conditions)
        blocked = {"incapacitated", "paralyzed", "petrified", "stunned", "unconscious"}
        return not any(runtime.has(condition) for condition in blocked)

    def _safe_condition_runtime(self, conditions: list[str] | None) -> ConditionRuntime:
        validated: list[str] = []
        if conditions is None:
            return ConditionRuntime(validated)
        for condition in conditions:
            try:
                parse_condition(condition)
            except (ValueError, TypeError, AttributeError):
                continue
            validated.append(condition)
        return ConditionRuntime(validated)

    def _ensure_movement_available(
        self,
        mover: EncounterEntity,
        movement: MovementValidationResult,
        use_dash: bool,
    ) -> None:
        runtime = self._safe_condition_runtime(mover.conditions)
        exhaustion_penalty = runtime.get_speed_penalty_feet()
        mastery_speed_penalty = get_weapon_mastery_speed_penalty(mover)
        distance_already_moved = self._movement_spent_feet(mover)
        effective_walk_speed = max(0, mover.speed["walk"] - exhaustion_penalty - mastery_speed_penalty)
        total_available_movement = effective_walk_speed * (2 if use_dash else 1)
        available_movement = max(0, total_available_movement - distance_already_moved)
        if movement.feet_cost > available_movement:
            raise ValueError("insufficient_movement")

    def _movement_spent_feet(self, entity: EncounterEntity) -> int:
        if entity.speed["remaining"] >= entity.speed["walk"]:
            return 0
        combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
        tracked_value = combat_flags.get("movement_spent_feet")
        if isinstance(tracked_value, int) and tracked_value >= 0:
            return tracked_value
        return max(0, entity.speed["walk"] - entity.speed["remaining"])

    def _apply_movement_progress(
        self,
        mover: EncounterEntity,
        feet_spent_delta: int,
        use_dash: bool,
        count_movement: bool,
    ) -> None:
        if not count_movement:
            return
        runtime = self._safe_condition_runtime(mover.conditions)
        exhaustion_penalty = runtime.get_speed_penalty_feet()
        mastery_speed_penalty = get_weapon_mastery_speed_penalty(mover)
        effective_walk_speed = max(0, mover.speed["walk"] - exhaustion_penalty - mastery_speed_penalty)
        spent_before = self._movement_spent_feet(mover)
        spent_after = spent_before + feet_spent_delta
        mover.combat_flags["movement_spent_feet"] = spent_after
        mover.speed["remaining"] = max(0, effective_walk_speed - min(spent_after, effective_walk_speed))
        if use_dash and spent_after > effective_walk_speed:
            mover.speed["remaining"] = 0

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        return get_entity_or_raise(encounter, entity_id, entity_label="entity")
