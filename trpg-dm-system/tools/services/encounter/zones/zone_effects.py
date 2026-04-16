from __future__ import annotations

from typing import Any

from tools.models import Encounter, EncounterEntity
from tools.services.encounter import movement_rules
from tools.services.encounter.turns import turn_effects as turn_effect_runtime

ZONE_TRIGGER_TIMINGS = {"enter", "start_of_turn_inside", "end_of_turn_inside"}


def resolve_zone_effects(
    *,
    encounter: Encounter,
    entity_id: str,
    trigger: str,
    movement_history: list[set[tuple[int, int]]] | None = None,
) -> list[dict[str, object]]:
    if trigger not in ZONE_TRIGGER_TIMINGS:
        raise ValueError("invalid_zone_trigger")

    entity = encounter.entities.get(entity_id)
    if entity is None:
        raise ValueError(f"entity '{entity_id}' not found in encounter")

    resolutions: list[dict[str, object]] = []
    current_cells = movement_rules.get_occupied_cells(entity)
    for zone in encounter.map.zones:
        if not isinstance(zone, dict):
            continue
        if not _zone_matches_trigger(zone=zone, trigger=trigger, current_cells=current_cells, movement_history=movement_history):
            continue

        runtime = zone.get("runtime")
        if not isinstance(runtime, dict):
            continue
        for trigger_config in runtime.get("triggers", []):
            if not isinstance(trigger_config, dict):
                continue
            if trigger_config.get("timing") != trigger:
                continue
            trigger_outcome = trigger_config.get("on_trigger")
            if trigger_outcome is None:
                trigger_outcome = trigger_config.get("effect")

            trigger_updates, trigger_damage_resolution = turn_effect_runtime._apply_effect_outcome(  # noqa: SLF001
                encounter=encounter,
                target=entity,
                outcome=trigger_outcome,
                damage_roll_overrides={},
            )
            resolution = {
                "zone_id": zone.get("zone_id"),
                "zone_name": zone.get("name") or zone.get("zone_id") or "未知区域",
                "trigger": trigger,
                "source_entity_id": runtime.get("source_entity_id"),
                "source_name": runtime.get("source_name") or zone.get("name") or "未知区域",
                "target_entity_id": entity.entity_id,
                "target_name": entity.name,
                "save": None,
                "trigger_damage_resolution": trigger_damage_resolution,
                "success_damage_resolution": None,
                "failure_damage_resolution": None,
                "damage_resolution": trigger_damage_resolution,
                "condition_updates": list(trigger_updates),
            }
            save_config = trigger_config.get("save")
            save_success: bool | None = None
            if isinstance(save_config, dict):
                save_result = turn_effect_runtime._resolve_effect_save(  # noqa: SLF001
                    target=entity,
                    effect=trigger_config,
                    save_config=save_config,
                    save_roll_overrides={},
                )
                save_success = bool(save_result.get("success"))
                resolution["save"] = save_result

                outcome_key = "on_save_success" if save_success else "on_save_failure"
                outcome_updates, outcome_damage_resolution = turn_effect_runtime._apply_effect_outcome(  # noqa: SLF001
                    encounter=encounter,
                    target=entity,
                    outcome=trigger_config.get(outcome_key),
                    damage_roll_overrides={},
                )
                resolution["condition_updates"].extend(outcome_updates)
                if save_success:
                    resolution["success_damage_resolution"] = outcome_damage_resolution
                else:
                    resolution["failure_damage_resolution"] = outcome_damage_resolution
                if outcome_damage_resolution is not None:
                    resolution["damage_resolution"] = outcome_damage_resolution
            resolutions.append(resolution)
    return resolutions


def _zone_matches_trigger(
    *,
    zone: dict[str, Any],
    trigger: str,
    current_cells: set[tuple[int, int]],
    movement_history: list[set[tuple[int, int]]] | None,
) -> bool:
    zone_cells = _normalize_zone_cells(zone.get("cells"))
    if not zone_cells:
        return False

    if trigger in {"start_of_turn_inside", "end_of_turn_inside"}:
        return bool(current_cells & zone_cells)
    if trigger == "enter":
        if not isinstance(movement_history, list) or len(movement_history) < 2:
            return False
        previous_inside = bool(movement_history[0] & zone_cells)
        for cells in movement_history[1:]:
            current_inside = bool(cells & zone_cells)
            if current_inside and not previous_inside:
                return True
            previous_inside = current_inside
    return False


def _normalize_zone_cells(value: Any) -> set[tuple[int, int]]:
    if not isinstance(value, list):
        return set()
    normalized: set[tuple[int, int]] = set()
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            continue
        x, y = item
        if isinstance(x, int) and isinstance(y, int):
            normalized.add((x, y))
    return normalized
