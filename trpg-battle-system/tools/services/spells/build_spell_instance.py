from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models import EncounterEntity


def build_spell_instance(
    *,
    spell_definition: dict[str, Any],
    caster: EncounterEntity,
    cast_level: int,
    targets: list[dict[str, Any]],
    started_round: int,
) -> dict[str, Any]:
    if not isinstance(spell_definition, dict):
        raise ValueError("spell_definition must be a dict")
    if not isinstance(cast_level, int) or cast_level < 0:
        raise ValueError("cast_level must be an integer >= 0")
    if not isinstance(started_round, int) or started_round < 1:
        raise ValueError("started_round must be an integer >= 1")
    if not isinstance(targets, list):
        raise ValueError("targets must be a list")

    base = spell_definition.get("base")
    concentration_required = False
    if isinstance(base, dict):
        concentration_required = bool(base.get("concentration"))

    normalized_targets: list[dict[str, Any]] = []
    for index, item in enumerate(targets):
        if not isinstance(item, dict):
            raise ValueError(f"targets[{index}] must be a dict")
        entity_id = item.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise ValueError(f"targets[{index}].entity_id must be a non-empty string")
        applied_conditions = item.get("applied_conditions", [])
        if not isinstance(applied_conditions, list):
            raise ValueError(f"targets[{index}].applied_conditions must be a list")
        turn_effect_ids = item.get("turn_effect_ids", [])
        if not isinstance(turn_effect_ids, list):
            raise ValueError(f"targets[{index}].turn_effect_ids must be a list")
        normalized_targets.append(
            {
                "entity_id": entity_id.strip(),
                "applied_conditions": list(applied_conditions),
                "turn_effect_ids": list(turn_effect_ids),
            }
        )

    special_runtime = _build_special_runtime(spell_definition=spell_definition, targets=normalized_targets)

    return {
        "instance_id": f"spell_{uuid4().hex[:12]}",
        "spell_id": str(spell_definition.get("id") or spell_definition.get("spell_id") or ""),
        "spell_name": str(spell_definition.get("name") or spell_definition.get("id") or ""),
        "caster_entity_id": caster.entity_id,
        "caster_name": caster.name,
        "cast_level": cast_level,
        "concentration": {
            "required": concentration_required,
            "active": concentration_required,
        },
        "targets": normalized_targets,
        "lifecycle": {
            "status": "active",
            "started_round": started_round,
        },
        "special_runtime": special_runtime,
    }


def _build_special_runtime(
    *,
    spell_definition: dict[str, Any],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime: dict[str, Any] = {"linked_zone_ids": []}
    spell_id = str(spell_definition.get("id") or spell_definition.get("spell_id") or "")
    if spell_id in {"find_steed", "find_familiar"}:
        runtime.update(
            {
                "summon_mode": "persistent_entity",
                "summon_entity_ids": [],
                "replace_previous_from_same_caster": True,
            }
        )
        return runtime

    special_rules = spell_definition.get("special_rules")
    if not isinstance(special_rules, dict):
        return runtime

    retarget_rule = special_rules.get("retarget_on_target_drop_to_zero")
    if not isinstance(retarget_rule, dict) or not bool(retarget_rule.get("enabled")):
        return runtime

    current_target_id = targets[0]["entity_id"] if targets else None
    runtime.update(
        {
            "retargetable": True,
            "retarget_available": False,
            "current_target_id": current_target_id,
            "retarget_activation": retarget_rule.get("activation"),
            "retarget_trigger": "target_drop_to_zero",
        }
    )
    return runtime
