from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.services.combat.actions import has_disengage_effect
from tools.services.combat.rules.conditions import ConditionRuntime
from tools.services.combat.rules.conditions.condition_parser import parse_condition
from tools.services.encounter.movement_rules import get_center_position, get_occupied_cells, validate_movement_path

@dataclass(frozen=True)
class EngagementPathOption:
    movement: Any
    risk_sources: list[str]

    @property
    def feet_cost(self) -> int:
        return int(self.movement.feet_cost)

    @property
    def is_safe(self) -> bool:
        return not self.risk_sources


def build_enemy_reachable_targets(
    encounter: Encounter,
    actor: EncounterEntity,
    *,
    targets: list[EncounterEntity],
    max_melee_range: int,
    score_target: Callable[[EncounterEntity, int | None], float],
) -> list[dict[str, Any]]:
    reachable_targets: list[dict[str, Any]] = []
    target_by_id: dict[str, EncounterEntity] = {}
    for target in targets:
        target_by_id[target.entity_id] = target
        reachable_targets.extend(
            _project_reachable_target(
                encounter,
                actor,
                target,
                max_melee_range=max_melee_range,
                score=0.0,
            )
        )

    lowest_ac: int | None = None
    if target_by_id:
        lowest_ac = min(target.ac for target in target_by_id.values())
    for item in reachable_targets:
        target = target_by_id.get(str(item["entity_id"]))
        if target is None:
            continue
        item["score"] = score_target(target, lowest_ac)

    reachable_targets.sort(
        key=lambda item: (
            -float(item["score"]),
            0 if bool(item["can_attack_this_turn"]) else 1,
            0 if not bool(item["opportunity_attack_risk"]) else 1,
            int(item["movement_cost_feet"]),
            str(item["entity_id"]),
        )
    )
    return reachable_targets[:2]


def _project_reachable_target(
    encounter: Encounter,
    actor: EncounterEntity,
    target: EncounterEntity,
    *,
    max_melee_range: int,
    score: float,
) -> list[dict[str, Any]]:
    safe_option, risky_option = _find_best_engage_movements(encounter, actor, target, max_melee_range=max_melee_range)
    if safe_option is None and risky_option is None:
        return []

    distance_feet = _distance_feet_between_entities(actor, target)
    remaining_movement = max(0, int(actor.speed.get("remaining", 0) or 0))
    dash_total_movement = remaining_movement + max(0, int(actor.speed.get("walk", 0) or 0))
    move_option = _select_option_within_budget(
        safe_option=safe_option,
        risky_option=risky_option,
        movement_budget=remaining_movement,
    )

    if move_option is not None:
        results = [
            _build_projection(
                target=target,
                score=score,
                distance_feet=distance_feet,
                destination_position=dict(move_option.movement.path[-1].anchor) if move_option.movement.path else dict(actor.position),
                movement_cost_feet=move_option.feet_cost,
                engage_mode="move_and_attack",
                can_attack_this_turn=True,
                requires_action_dash=False,
                requires_action_disengage=False,
                opportunity_attack_risk=bool(move_option.risk_sources),
                risk_sources=move_option.risk_sources,
            )
        ]
        if not move_option.is_safe:
            results.append(
                _build_projection(
                    target=target,
                    score=score,
                    distance_feet=distance_feet,
                    destination_position=dict(move_option.movement.path[-1].anchor) if move_option.movement.path else dict(actor.position),
                    movement_cost_feet=move_option.feet_cost,
                    engage_mode="disengage_to_engage",
                    can_attack_this_turn=False,
                    requires_action_dash=False,
                    requires_action_disengage=True,
                    opportunity_attack_risk=False,
                    risk_sources=[],
                )
            )
        return results

    dash_option = _select_option_within_budget(
        safe_option=safe_option,
        risky_option=risky_option,
        movement_budget=dash_total_movement,
    )
    if dash_option is not None:
        return [
            _build_projection(
                target=target,
                score=score,
                distance_feet=distance_feet,
                destination_position=dict(dash_option.movement.path[-1].anchor) if dash_option.movement.path else dict(actor.position),
                movement_cost_feet=dash_option.feet_cost,
                engage_mode="dash_to_engage",
                can_attack_this_turn=False,
                requires_action_dash=True,
                requires_action_disengage=False,
                opportunity_attack_risk=bool(dash_option.risk_sources),
                risk_sources=dash_option.risk_sources,
            )
        ]

    pressure_option = _find_best_pressure_movement(
        encounter,
        actor,
        target,
        movement_budget=dash_total_movement,
        current_distance_feet=distance_feet,
    )
    if pressure_option is not None:
        return [
            _build_projection(
                target=target,
                score=score,
                distance_feet=distance_feet,
                destination_position=dict(pressure_option.movement.path[-1].anchor) if pressure_option.movement.path else dict(actor.position),
                movement_cost_feet=pressure_option.feet_cost,
                engage_mode="dash_to_engage",
                can_attack_this_turn=False,
                requires_action_dash=True,
                requires_action_disengage=False,
                opportunity_attack_risk=bool(pressure_option.risk_sources),
                risk_sources=pressure_option.risk_sources,
            )
        ]

    return []


def _select_option_within_budget(
    *,
    safe_option: EngagementPathOption | None,
    risky_option: EngagementPathOption | None,
    movement_budget: int,
) -> EngagementPathOption | None:
    if safe_option is not None and safe_option.feet_cost <= movement_budget:
        return safe_option
    if risky_option is not None and risky_option.feet_cost <= movement_budget:
        return risky_option
    return None


def _apply_projection_score(
    base_score: float,
) -> float:
    return round(float(base_score), 2)


def _build_projection(
    *,
    target: EncounterEntity,
    score: float,
    distance_feet: int,
    destination_position: dict[str, int],
    movement_cost_feet: int,
    engage_mode: str,
    can_attack_this_turn: bool,
    requires_action_dash: bool,
    requires_action_disengage: bool,
    opportunity_attack_risk: bool,
    risk_sources: list[str],
) -> dict[str, Any]:
    return {
        "entity_id": target.entity_id,
        "score": score,
        "distance_feet": distance_feet,
        "destination_position": dict(destination_position),
        "movement_cost_feet": movement_cost_feet,
        "can_attack_this_turn": can_attack_this_turn,
        "engage_mode": engage_mode,
        "requires_action_dash": requires_action_dash,
        "requires_action_disengage": requires_action_disengage,
        "opportunity_attack_risk": opportunity_attack_risk,
        "risk_sources": list(risk_sources),
    }


def _find_best_engage_movements(
    encounter: Encounter,
    actor: EncounterEntity,
    target: EncounterEntity,
    *,
    max_melee_range: int,
) -> tuple[EngagementPathOption | None, EngagementPathOption | None]:
    best_safe_option: EngagementPathOption | None = None
    best_risky_option: EngagementPathOption | None = None
    best_safe_anchor: tuple[int, int] | None = None
    best_risky_anchor: tuple[int, int] | None = None

    for anchor in _iter_attack_anchors(encounter, actor, target, max_melee_range=max_melee_range):
        try:
            movement = validate_movement_path(
                encounter,
                actor.entity_id,
                {"x": anchor[0], "y": anchor[1]},
                count_movement=False,
                use_dash=False,
            )
        except ValueError:
            continue
        risk_sources = _find_opportunity_attack_risk_sources(encounter, actor, movement)
        option = EngagementPathOption(movement=movement, risk_sources=risk_sources)
        if option.is_safe:
            if best_safe_option is None or option.feet_cost < best_safe_option.feet_cost or (
                option.feet_cost == best_safe_option.feet_cost and anchor < (best_safe_anchor or anchor)
            ):
                best_safe_option = option
                best_safe_anchor = anchor
            continue
        if best_risky_option is None or option.feet_cost < best_risky_option.feet_cost or (
            option.feet_cost == best_risky_option.feet_cost and anchor < (best_risky_anchor or anchor)
        ):
            best_risky_option = option
            best_risky_anchor = anchor
    return best_safe_option, best_risky_option


def _find_best_pressure_movement(
    encounter: Encounter,
    actor: EncounterEntity,
    target: EncounterEntity,
    *,
    movement_budget: int,
    current_distance_feet: int,
) -> EngagementPathOption | None:
    if movement_budget <= 0:
        return None

    target_center = get_center_position(target)
    best_safe: tuple[int, int, tuple[int, int], EngagementPathOption] | None = None
    best_risky: tuple[int, int, tuple[int, int], EngagementPathOption] | None = None

    for x in range(int(encounter.map.width)):
        for y in range(int(encounter.map.height)):
            anchor = {"x": x, "y": y}
            if anchor == actor.position:
                continue
            try:
                movement = validate_movement_path(
                    encounter,
                    actor.entity_id,
                    anchor,
                    count_movement=False,
                    use_dash=False,
                )
            except ValueError:
                continue
            option = EngagementPathOption(
                movement=movement,
                risk_sources=_find_opportunity_attack_risk_sources(encounter, actor, movement),
            )
            if option.feet_cost > movement_budget:
                continue
            destination_center = get_center_position(actor, anchor)
            distance_after = _distance_feet_between_points(destination_center, target_center)
            if distance_after >= current_distance_feet:
                continue
            sort_key = (distance_after, option.feet_cost, (x, y))
            if option.is_safe:
                if best_safe is None or sort_key < best_safe[:3]:
                    best_safe = (distance_after, option.feet_cost, (x, y), option)
            elif best_risky is None or sort_key < best_risky[:3]:
                best_risky = (distance_after, option.feet_cost, (x, y), option)

    if best_safe is not None:
        return best_safe[3]
    if best_risky is not None:
        return best_risky[3]
    return None


def _iter_attack_anchors(
    encounter: Encounter,
    actor: EncounterEntity,
    target: EncounterEntity,
    *,
    max_melee_range: int,
):
    map_width = int(encounter.map.width)
    map_height = int(encounter.map.height)
    target_cells = get_occupied_cells(target)
    target_center = get_center_position(target)

    for x in range(map_width):
        for y in range(map_height):
            anchor = {"x": x, "y": y}
            occupied_cells = get_occupied_cells(actor, anchor)
            if occupied_cells & target_cells:
                continue
            mover_center = get_center_position(actor, anchor)
            if _distance_feet_between_points(mover_center, target_center) > max_melee_range:
                continue
            yield (x, y)


def _find_opportunity_attack_risk_sources(
    encounter: Encounter,
    actor: EncounterEntity,
    movement,
) -> list[str]:
    if has_disengage_effect(actor):
        return []

    current_anchor = {"x": actor.position["x"], "y": actor.position["y"]}
    risk_sources: list[str] = []
    for step in movement.path:
        next_anchor = step.anchor
        for candidate in encounter.entities.values():
            if candidate.entity_id == actor.entity_id or candidate.side == actor.side:
                continue
            if bool(candidate.action_economy.get("reaction_used")):
                continue
            if not _can_make_opportunity_attack(candidate):
                continue
            if _get_first_melee_weapon(candidate) is None:
                continue
            if _leaves_melee_reach(candidate, actor, current_anchor, next_anchor):
                risk_sources.append(candidate.entity_id)
        current_anchor = dict(next_anchor)
    return sorted(set(risk_sources))


def _leaves_melee_reach(
    attacker: EncounterEntity,
    mover: EncounterEntity,
    current_anchor: dict[str, int],
    next_anchor: dict[str, int],
) -> bool:
    attacker_center = get_center_position(attacker)
    current_center = get_center_position(mover, current_anchor)
    next_center = get_center_position(mover, next_anchor)
    return (
        _distance_feet_between_points(attacker_center, current_center) <= 5
        and _distance_feet_between_points(attacker_center, next_center) > 5
    )


def _get_first_melee_weapon(entity: EncounterEntity) -> dict[str, Any] | None:
    for weapon in entity.weapons:
        if _is_melee_weapon(weapon):
            return weapon
    return None


def _is_melee_weapon(weapon: dict[str, Any]) -> bool:
    kind = str(weapon.get("kind", "")).lower()
    weapon_range = weapon.get("range", {})
    normal_range = weapon_range.get("normal", 0)
    long_range = weapon_range.get("long", normal_range)
    if not isinstance(normal_range, int) or normal_range <= 0:
        return False
    kind_missing = kind == ""
    return kind == "melee" or (
        kind_missing and isinstance(long_range, int) and long_range <= 10 and normal_range <= 10
    )


def _can_make_opportunity_attack(entity: EncounterEntity) -> bool:
    runtime = _safe_condition_runtime(entity.conditions)
    blocked = {"incapacitated", "paralyzed", "petrified", "stunned", "unconscious"}
    return not any(runtime.has(condition) for condition in blocked)


def _safe_condition_runtime(conditions: list[str] | None) -> ConditionRuntime:
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


def _distance_feet_between_entities(source: EncounterEntity, target: EncounterEntity) -> int:
    return _distance_feet_between_points(get_center_position(source), get_center_position(target))


def _distance_feet_between_points(source: dict[str, float], target: dict[str, float]) -> int:
    dx = abs(source["x"] - target["x"])
    dy = abs(source["y"] - target["y"])
    return int(max(dx, dy) * 5)
