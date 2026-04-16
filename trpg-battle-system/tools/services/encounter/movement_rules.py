from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.services.combat.rules.conditions import ConditionRuntime, ZERO_SPEED_CONDITIONS
from tools.services.combat.rules.conditions.condition_parser import parse_condition

SIZE_TO_FOOTPRINT = {
    "tiny": (1, 1),
    "small": (1, 1),
    "medium": (1, 1),
    "large": (2, 2),
    "huge": (3, 3),
    "gargantuan": (4, 4),
}
DIFFICULT_TERRAIN_TYPE = "difficult_terrain"
WALL_TERRAIN_TYPE = "wall"
SHARED_DESTINATION_SIZES = {"tiny", "small"}
ORTHOGONAL_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL_DIRECTIONS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
ALL_DIRECTIONS = ORTHOGONAL_DIRECTIONS + DIAGONAL_DIRECTIONS


@dataclass(frozen=True)
class MovementStep:
    anchor: dict[str, int]
    occupied_cells: set[tuple[int, int]]
    feet_cost: int
    movement_kind: str


@dataclass(frozen=True)
class MovementValidationResult:
    path: list[MovementStep]
    feet_cost: int
    used_dash: bool
    movement_counted: bool
    blocked_reason: str | None = None


def get_footprint_size(entity: EncounterEntity) -> tuple[int, int]:
    return SIZE_TO_FOOTPRINT[entity.size]


def get_occupied_cells(entity: EncounterEntity, anchor: dict[str, int] | None = None) -> set[tuple[int, int]]:
    anchor_position = entity.position if anchor is None else anchor
    width, height = get_footprint_size(entity)
    return {
        (anchor_position["x"] + dx, anchor_position["y"] + dy)
        for dx in range(width)
        for dy in range(height)
    }


def get_center_position(entity: EncounterEntity, anchor: dict[str, int] | None = None) -> dict[str, float]:
    anchor_position = entity.position if anchor is None else anchor
    width, height = get_footprint_size(entity)
    return {
        "x": anchor_position["x"] + (width - 1) / 2,
        "y": anchor_position["y"] + (height - 1) / 2,
    }


def calculate_step_costs(start: tuple[int, int], anchors: list[tuple[int, int]]) -> list[int]:
    costs: list[int] = []
    previous = start
    diagonal_toggle = 0
    for current in anchors:
        movement_kind = classify_step(previous, current)
        cost, diagonal_toggle = calculate_step_cost(movement_kind, diagonal_toggle, enters_difficult=False)
        costs.append(cost)
        previous = current
    return costs


def validate_movement_path(
    encounter: Encounter,
    entity_id: str,
    target_position: dict[str, int],
    *,
    count_movement: bool,
    use_dash: bool,
) -> MovementValidationResult:
    mover = _get_entity_or_raise(encounter, entity_id)
    if not isinstance(target_position, dict) or "x" not in target_position or "y" not in target_position:
        raise ValueError("invalid_target_position")
    if not isinstance(target_position["x"], int) or not isinstance(target_position["y"], int):
        raise ValueError("invalid_target_position")

    start_anchor = (mover.position["x"], mover.position["y"])
    target_anchor = (target_position["x"], target_position["y"])
    start_cells = get_occupied_cells(mover)
    target_cells = get_occupied_cells(mover, target_position)

    _ensure_cells_within_map(encounter, target_cells)
    _ensure_no_wall_collision(encounter, target_cells)
    _ensure_destination_occupancy_is_legal(encounter, mover, target_cells)

    if start_anchor == target_anchor:
        return MovementValidationResult(
            path=[],
            feet_cost=0,
            used_dash=use_dash,
            movement_counted=count_movement,
            blocked_reason=None,
        )

    runtime = _safe_condition_runtime(mover.conditions)
    _ensure_entity_can_move(runtime)
    is_prone = runtime.has("prone")
    frightened_centers = _build_frightened_source_centers(encounter, runtime)
    _ensure_target_not_closer_to_frightened_source(mover, start_anchor, target_anchor, frightened_centers)

    queue: list[tuple[int, int, int, tuple[int, int], int]] = []
    best_cost: dict[tuple[tuple[int, int], int], int] = {(start_anchor, 0): 0}
    came_from: dict[tuple[tuple[int, int], int], tuple[tuple[tuple[int, int], int], MovementStep]] = {}
    sequence = 0
    heappush(queue, (0, _heuristic(start_anchor, target_anchor), sequence, start_anchor, 0))

    while queue:
        total_cost, _, _, current_anchor, diagonal_toggle = heappop(queue)
        state_key = (current_anchor, diagonal_toggle)
        if total_cost != best_cost.get(state_key):
            continue

        if current_anchor == target_anchor:
            path = _reconstruct_path(came_from, state_key)
            return MovementValidationResult(
                path=path,
                feet_cost=total_cost,
                used_dash=use_dash,
                movement_counted=count_movement,
                blocked_reason=None,
            )

        current_cells = get_occupied_cells(mover, {"x": current_anchor[0], "y": current_anchor[1]})
        for dx, dy in ALL_DIRECTIONS:
            next_anchor = (current_anchor[0] + dx, current_anchor[1] + dy)
            next_anchor_dict = {"x": next_anchor[0], "y": next_anchor[1]}
            next_cells = get_occupied_cells(mover, next_anchor_dict)

            if not _cells_within_map(encounter, next_cells):
                continue
            if _cells_hit_wall(encounter, next_cells):
                continue

            if not _is_step_allowed_by_frightened_rules(mover, current_anchor, next_anchor, frightened_centers):
                continue

            is_final_step = next_anchor == target_anchor
            if not _is_occupancy_legal(encounter, mover, next_cells, allow_end_overlap=is_final_step):
                continue

            movement_kind = classify_step(current_anchor, next_anchor)
            enters_difficult = _enters_difficult_terrain(encounter, current_cells, next_cells)
            step_cost, next_diagonal_toggle = calculate_step_cost(movement_kind, diagonal_toggle, enters_difficult)
            if is_prone:
                step_cost *= 2
            next_cost = total_cost + step_cost
            next_state_key = (next_anchor, next_diagonal_toggle)

            if next_cost >= best_cost.get(next_state_key, float("inf")):
                continue

            step = MovementStep(
                anchor=next_anchor_dict,
                occupied_cells=next_cells,
                feet_cost=step_cost,
                movement_kind=movement_kind,
            )
            best_cost[next_state_key] = next_cost
            came_from[next_state_key] = (state_key, step)
            sequence += 1
            heappush(
                queue,
                (next_cost, next_cost + _heuristic(next_anchor, target_anchor), sequence, next_anchor, next_diagonal_toggle),
            )

    raise ValueError("no_legal_path")


def classify_step(previous: tuple[int, int], current: tuple[int, int]) -> str:
    return "diagonal" if previous[0] != current[0] and previous[1] != current[1] else "orthogonal"


def calculate_step_cost(movement_kind: str, diagonal_toggle: int, enters_difficult: bool) -> tuple[int, int]:
    if movement_kind == "diagonal":
        base_cost = 5 if diagonal_toggle == 0 else 10
        next_toggle = 1 - diagonal_toggle
    else:
        base_cost = 5
        next_toggle = 0
    return (base_cost * 2 if enters_difficult else base_cost, next_toggle)


def _ensure_entity_can_move(runtime: ConditionRuntime) -> None:
    if any(runtime.has(condition) for condition in ZERO_SPEED_CONDITIONS):
        raise ValueError("movement_blocked_by_condition")


def _safe_condition_runtime(conditions: list[str] | None) -> ConditionRuntime:
    validated: list[str] = []
    for condition in _normalize_condition_values(conditions):
        try:
            parse_condition(condition)
        except (ValueError, TypeError, AttributeError):
            continue
        validated.append(condition)
    return ConditionRuntime(validated)


def _normalize_condition_values(conditions: object) -> list[object]:
    if conditions is None:
        return []
    if isinstance(conditions, str):
        return [conditions]
    if isinstance(conditions, (list, tuple, set)):
        return list(conditions)
    return []


def _build_frightened_source_centers(encounter: Encounter, runtime: ConditionRuntime) -> list[dict[str, float]]:
    centers: list[dict[str, float]] = []
    for source_id in runtime.sources_for("frightened"):
        source_entity = encounter.entities.get(source_id)
        if source_entity is None:
            continue
        centers.append(get_center_position(source_entity))
    return centers


def _ensure_target_not_closer_to_frightened_source(
    mover: EncounterEntity,
    start_anchor: tuple[int, int],
    target_anchor: tuple[int, int],
    frightened_sources: list[dict[str, float]],
) -> None:
    if not frightened_sources:
        return
    start_center = get_center_position(mover, {"x": start_anchor[0], "y": start_anchor[1]})
    target_center = get_center_position(mover, {"x": target_anchor[0], "y": target_anchor[1]})
    for source in frightened_sources:
        start_distance = _tile_distance_to_target(start_center, source)
        target_distance = _tile_distance_to_target(target_center, source)
        if target_distance < start_distance:
            raise ValueError("blocked_by_frightened_source")


def _is_step_allowed_by_frightened_rules(
    mover: EncounterEntity,
    current_anchor: tuple[int, int],
    next_anchor: tuple[int, int],
    frightened_sources: list[dict[str, float]],
) -> bool:
    if not frightened_sources:
        return True
    current_center = get_center_position(mover, {"x": current_anchor[0], "y": current_anchor[1]})
    next_center = get_center_position(mover, {"x": next_anchor[0], "y": next_anchor[1]})
    for source in frightened_sources:
        current_distance = _tile_distance_to_target(current_center, source)
        next_distance = _tile_distance_to_target(next_center, source)
        if next_distance < current_distance:
            return False
    return True


def _tile_distance_to_target(position: dict[str, float], target: dict[str, float]) -> float:
    dx = abs(position["x"] - target["x"])
    dy = abs(position["y"] - target["y"])
    return max(dx, dy)


def _get_entity_or_raise(encounter: Encounter, entity_id: str) -> EncounterEntity:
    entity = encounter.entities.get(entity_id)
    if entity is None:
        raise ValueError(f"entity '{entity_id}' not found in encounter")
    return entity


def _terrain_cells(encounter: Encounter, terrain_type: str) -> set[tuple[int, int]]:
    return {
        (terrain["x"], terrain["y"])
        for terrain in encounter.map.terrain
        if terrain.get("type") == terrain_type and isinstance(terrain.get("x"), int) and isinstance(terrain.get("y"), int)
    }


def _cells_within_map(encounter: Encounter, cells: set[tuple[int, int]]) -> bool:
    return all(1 <= x <= encounter.map.width and 1 <= y <= encounter.map.height for x, y in cells)


def _ensure_cells_within_map(encounter: Encounter, cells: set[tuple[int, int]]) -> None:
    if not _cells_within_map(encounter, cells):
        raise ValueError("out_of_bounds")


def _cells_hit_wall(encounter: Encounter, cells: set[tuple[int, int]]) -> bool:
    wall_cells = _terrain_cells(encounter, WALL_TERRAIN_TYPE)
    return any(cell in wall_cells for cell in cells)


def _ensure_no_wall_collision(encounter: Encounter, cells: set[tuple[int, int]]) -> None:
    if _cells_hit_wall(encounter, cells):
        raise ValueError("blocked_by_wall")


def _enters_difficult_terrain(
    encounter: Encounter,
    previous_cells: set[tuple[int, int]],
    next_cells: set[tuple[int, int]],
) -> bool:
    difficult_cells = _terrain_cells(encounter, DIFFICULT_TERRAIN_TYPE) | _zone_cells_treated_as_difficult(encounter)
    entered_cells = next_cells - previous_cells
    return any(cell in difficult_cells for cell in entered_cells)


def _zone_cells_treated_as_difficult(encounter: Encounter) -> set[tuple[int, int]]:
    difficult_cells: set[tuple[int, int]] = set()
    for zone in encounter.map.zones:
        if not isinstance(zone, dict):
            continue
        runtime = zone.get("runtime")
        if not isinstance(runtime, dict):
            continue
        movement_modifier = runtime.get("movement_modifier")
        if not isinstance(movement_modifier, dict):
            continue
        if not bool(movement_modifier.get("treat_as_difficult_terrain")):
            continue
        for cell in zone.get("cells", []):
            if not isinstance(cell, list) or len(cell) != 2:
                continue
            x, y = cell
            if isinstance(x, int) and isinstance(y, int):
                difficult_cells.add((x, y))
    return difficult_cells


def _iter_other_entities(encounter: Encounter, mover: EncounterEntity) -> list[EncounterEntity]:
    return [entity for entity in encounter.entities.values() if entity.entity_id != mover.entity_id]


def _ensure_destination_occupancy_is_legal(
    encounter: Encounter,
    mover: EncounterEntity,
    cells: set[tuple[int, int]],
) -> None:
    if not _is_occupancy_legal(encounter, mover, cells, allow_end_overlap=True):
        overlapping_entities = _get_overlapping_entities(encounter, mover, cells)
        if any(entity.side != mover.side for entity in overlapping_entities):
            raise ValueError("blocked_by_enemy")
        raise ValueError("blocked_by_occupied_destination")


def _get_overlapping_entities(
    encounter: Encounter,
    mover: EncounterEntity,
    cells: set[tuple[int, int]],
) -> list[EncounterEntity]:
    overlapping_entities: list[EncounterEntity] = []
    for entity in _iter_other_entities(encounter, mover):
        if get_occupied_cells(entity) & cells:
            overlapping_entities.append(entity)
    return overlapping_entities


def _is_occupancy_legal(
    encounter: Encounter,
    mover: EncounterEntity,
    cells: set[tuple[int, int]],
    *,
    allow_end_overlap: bool,
) -> bool:
    for entity in _iter_other_entities(encounter, mover):
        overlap = get_occupied_cells(entity) & cells
        if not overlap:
            continue
        if entity.side != mover.side:
            return False
        if allow_end_overlap and entity.size in SHARED_DESTINATION_SIZES:
            continue
        if allow_end_overlap:
            return False
    return True


def _heuristic(current: tuple[int, int], target: tuple[int, int]) -> int:
    return max(abs(target[0] - current[0]), abs(target[1] - current[1])) * 5


def _reconstruct_path(
    came_from: dict[tuple[tuple[int, int], int], tuple[tuple[tuple[int, int], int], MovementStep]],
    state_key: tuple[tuple[int, int], int],
) -> list[MovementStep]:
    reversed_steps: list[MovementStep] = []
    current = state_key
    while current in came_from:
        previous_state, step = came_from[current]
        reversed_steps.append(step)
        current = previous_state
    reversed_steps.reverse()
    return reversed_steps
