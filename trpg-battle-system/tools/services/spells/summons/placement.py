from __future__ import annotations

import math
from typing import Any

from tools.models import Encounter, EncounterEntity
from tools.services.encounter.movement_rules import SIZE_TO_FOOTPRINT, get_center_position, get_occupied_cells


def resolve_summon_target_point(
    *,
    encounter: Encounter,
    caster: EncounterEntity,
    summon_size: str,
    range_feet: int,
    target_point: dict[str, Any] | None,
    default_mode: str,
    out_of_range_error_code: str,
    missing_target_point_error_code: str,
) -> dict[str, int | str]:
    normalized_target_point = _normalize_target_point(target_point)
    if normalized_target_point is not None:
        if not _is_target_point_within_range(
            encounter=encounter,
            caster=caster,
            target_point=normalized_target_point,
            range_feet=range_feet,
        ):
            raise ValueError(out_of_range_error_code)
        if not _is_summon_target_point_legal(
            encounter=encounter,
            target_point=normalized_target_point,
            summon_size=summon_size,
        ):
            raise ValueError("summon_target_point_illegal")
        return normalized_target_point

    if default_mode != "adjacent_open_space":
        raise ValueError(missing_target_point_error_code)

    default_target_point = _find_adjacent_open_space(
        encounter=encounter,
        caster=caster,
        summon_size=summon_size,
    )
    if default_target_point is None:
        raise ValueError(missing_target_point_error_code)
    return default_target_point


def _normalize_target_point(target_point: dict[str, Any] | None) -> dict[str, int | str] | None:
    if not isinstance(target_point, dict):
        return None
    x = target_point.get("x")
    y = target_point.get("y")
    if not isinstance(x, int) or isinstance(x, bool) or not isinstance(y, int) or isinstance(y, bool):
        return None
    anchor = target_point.get("anchor", "cell_center")
    if anchor != "cell_center":
        return None
    return {"x": x, "y": y, "anchor": "cell_center"}


def _is_target_point_within_range(
    *,
    encounter: Encounter,
    caster: EncounterEntity,
    target_point: dict[str, int | str],
    range_feet: int,
) -> bool:
    if range_feet <= 0:
        return True
    caster_center = get_center_position(caster)
    dx = abs(caster_center["x"] - int(target_point["x"]))
    dy = abs(caster_center["y"] - int(target_point["y"]))
    distance_feet = math.ceil(max(dx, dy)) * encounter.map.grid_size_feet
    return distance_feet <= range_feet


def _find_adjacent_open_space(
    *,
    encounter: Encounter,
    caster: EncounterEntity,
    summon_size: str,
) -> dict[str, int | str] | None:
    caster_width, caster_height = SIZE_TO_FOOTPRINT[caster.size]
    summon_width, summon_height = SIZE_TO_FOOTPRINT[summon_size]
    candidate_offsets = (
        (caster_width, 0),
        (-summon_width, 0),
        (0, caster_height),
        (0, -summon_height),
        (caster_width, caster_height),
        (caster_width, -summon_height),
        (-summon_width, caster_height),
        (-summon_width, -summon_height),
    )
    caster_anchor_x = int(caster.position["x"])
    caster_anchor_y = int(caster.position["y"])
    for dx, dy in candidate_offsets:
        candidate = {
            "x": caster_anchor_x + dx,
            "y": caster_anchor_y + dy,
            "anchor": "cell_center",
        }
        if _is_summon_target_point_legal(
            encounter=encounter,
            target_point=candidate,
            summon_size=summon_size,
        ):
            return candidate
    return None


def _is_summon_target_point_legal(
    *,
    encounter: Encounter,
    target_point: dict[str, int | str],
    summon_size: str,
) -> bool:
    summon_width, summon_height = SIZE_TO_FOOTPRINT[summon_size]
    x = int(target_point["x"])
    y = int(target_point["y"])
    summon_cells = {
        (x + dx, y + dy)
        for dx in range(summon_width)
        for dy in range(summon_height)
    }
    if any(
        cell_x < 0 or cell_y < 0 or cell_x >= encounter.map.width or cell_y >= encounter.map.height
        for cell_x, cell_y in summon_cells
    ):
        return False

    blocking_cells = {
        (terrain["x"], terrain["y"])
        for terrain in encounter.map.terrain
        if isinstance(terrain, dict)
        and isinstance(terrain.get("x"), int)
        and isinstance(terrain.get("y"), int)
        and (terrain.get("type") == "wall" or terrain.get("blocks_movement"))
    }
    if summon_cells & blocking_cells:
        return False

    for entity in encounter.entities.values():
        if get_occupied_cells(entity) & summon_cells:
            return False
    return True
