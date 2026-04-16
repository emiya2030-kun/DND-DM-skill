from __future__ import annotations

from typing import Any

from tools.models import Encounter


def end_concentration_spell_instances(
    *,
    encounter: Encounter,
    caster_entity_id: str,
    reason: str,
) -> dict[str, Any]:
    ended_instance_ids: list[str] = []
    removed_conditions: list[dict[str, str]] = []
    removed_turn_effects: list[dict[str, str]] = []

    for instance in encounter.spell_instances:
        if not _is_matching_active_concentration_instance(instance, caster_entity_id):
            continue

        for target in instance.get("targets", []):
            target_id = target.get("entity_id")
            if not isinstance(target_id, str):
                continue
            entity = encounter.entities.get(target_id)
            if entity is None:
                continue

            for condition in target.get("applied_conditions", []):
                if not isinstance(condition, str):
                    continue
                if condition in entity.conditions:
                    entity.conditions.remove(condition)
                    removed_conditions.append({"target_id": target_id, "condition": condition})

            turn_effect_ids = {
                effect_id for effect_id in target.get("turn_effect_ids", []) if isinstance(effect_id, str)
            }
            if turn_effect_ids:
                retained_effects = []
                for effect in entity.turn_effects:
                    effect_id = effect.get("effect_id")
                    if isinstance(effect_id, str) and effect_id in turn_effect_ids:
                        removed_turn_effects.append({"target_id": target_id, "effect_id": effect_id})
                        continue
                    retained_effects.append(effect)
                entity.turn_effects = retained_effects

        instance.setdefault("concentration", {})["active"] = False
        lifecycle = instance.setdefault("lifecycle", {})
        lifecycle["status"] = "ended"
        lifecycle["end_reason"] = reason
        ended_instance_ids.append(str(instance.get("instance_id") or ""))

    return {
        "ended_instance_ids": [instance_id for instance_id in ended_instance_ids if instance_id],
        "removed_conditions": removed_conditions,
        "removed_turn_effects": removed_turn_effects,
    }


def _is_matching_active_concentration_instance(instance: dict[str, Any], caster_entity_id: str) -> bool:
    if instance.get("caster_entity_id") != caster_entity_id:
        return False

    concentration = instance.get("concentration", {})
    if not isinstance(concentration, dict):
        return False
    if not concentration.get("required") or not concentration.get("active"):
        return False

    lifecycle = instance.get("lifecycle", {})
    if not isinstance(lifecycle, dict):
        return False
    return lifecycle.get("status") == "active"
