from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from tools.models import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.services.encounter.movement_rules import get_occupied_cells


def collect_circle_cells(
    *,
    map_width: int,
    map_height: int,
    target_point: dict[str, Any],
    radius_feet: int,
    grid_size_feet: int,
) -> set[tuple[int, int]]:
    if target_point.get("anchor") != "cell_center":
        raise ValueError("unsupported_target_point_anchor")

    center_x = int(target_point["x"])
    center_y = int(target_point["y"])
    radius_tiles = radius_feet / grid_size_feet
    covered: set[tuple[int, int]] = set()
    for y in range(1, map_height + 1):
        for x in range(1, map_width + 1):
            dx = x - center_x
            dy = y - center_y
            if (dx * dx + dy * dy) ** 0.5 <= radius_tiles:
                covered.add((x, y))
    return covered


def collect_entities_in_cells(
    *,
    encounter: Encounter,
    covered_cells: set[tuple[int, int]],
) -> list[str]:
    matched: list[str] = []
    for entity_id, entity in encounter.entities.items():
        occupied_cells = get_occupied_cells(entity)
        if any(cell in covered_cells for cell in occupied_cells):
            matched.append(entity_id)
    return matched


def build_spell_area_overlay(
    *,
    overlay_id: str,
    spell_id: str,
    spell_name: str,
    target_point: dict[str, Any],
    radius_feet: int,
    grid_size_feet: int,
    persistence: str,
) -> dict[str, Any]:
    return {
        "overlay_id": overlay_id,
        "kind": "spell_area_circle",
        "source_spell_id": spell_id,
        "source_spell_name": spell_name,
        "target_point": dict(target_point),
        "radius_feet": radius_feet,
        "radius_tiles": radius_feet / grid_size_feet,
        "persistence": persistence,
    }


def build_spell_zone_instance(
    *,
    encounter: Encounter,
    spell_definition: dict[str, Any],
    caster: EncounterEntity,
    target_point: dict[str, Any],
    persistence: str,
    zone_definition: dict[str, Any] | None = None,
    spell_instance_id: str | None = None,
) -> dict[str, Any]:
    area_template = spell_definition.get("area_template")
    if not isinstance(area_template, dict):
        raise ValueError("missing_area_template")
    radius_feet = area_template.get("radius_feet")
    if not isinstance(radius_feet, int) or radius_feet <= 0:
        raise ValueError("invalid_area_radius")

    covered_cells = collect_circle_cells(
        map_width=encounter.map.width,
        map_height=encounter.map.height,
        target_point=target_point,
        radius_feet=radius_feet,
        grid_size_feet=encounter.map.grid_size_feet,
    )
    zone = deepcopy(zone_definition) if isinstance(zone_definition, dict) else {}
    zone["zone_id"] = f"zone_spell_{uuid4().hex[:12]}"
    zone["type"] = str(zone.get("type") or "spell_area")
    zone["name"] = _resolve_spell_name(spell_definition)
    zone["cells"] = [[x, y] for x, y in sorted(covered_cells, key=lambda item: (item[1], item[0]))]
    zone["note"] = str(zone.get("note") or f"{zone['name']}覆盖区域。")
    runtime = zone.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime.update(
        {
            "source_type": "spell",
            "source_spell_id": str(spell_definition.get("id") or spell_definition.get("spell_id") or ""),
            "source_spell_instance_id": spell_instance_id,
            "source_entity_id": caster.entity_id,
            "source_name": caster.name,
            "target_point": dict(target_point),
            "shape": str(area_template.get("shape") or "sphere"),
            "radius_feet": radius_feet,
            "radius_tiles": radius_feet / encounter.map.grid_size_feet,
            "persistence": persistence,
        }
    )
    zone["runtime"] = runtime
    return zone


def _resolve_spell_name(spell_definition: dict[str, Any]) -> str:
    localization = spell_definition.get("localization")
    if isinstance(localization, dict):
        localized = localization.get("name_zh")
        if isinstance(localized, str) and localized.strip():
            return localized.strip()
    name = spell_definition.get("name") or spell_definition.get("id") or "法术区域"
    return str(name)
