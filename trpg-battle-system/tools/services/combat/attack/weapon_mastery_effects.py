from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models import Encounter, EncounterEntity
from tools.models.roll_request import RollRequest
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow
from tools.services.encounter.movement_rules import get_center_position
from tools.services.encounter.resolve_forced_movement import ResolveForcedMovement


def collect_attack_roll_weapon_mastery_modifiers(
    *,
    actor: EncounterEntity,
    target: EncounterEntity,
) -> dict[str, Any]:
    advantage_sources: list[str] = []
    disadvantage_sources: list[str] = []
    consumed_effect_ids: list[str] = []

    for effect in actor.turn_effects:
        if not _is_weapon_mastery_effect(effect):
            continue
        effect_id = str(effect.get("effect_id") or "")
        mastery = str(effect.get("mastery") or "").lower()
        if mastery == "vex" and effect.get("target_entity_id") == target.entity_id:
            advantage_sources.append(f"mastery_vex:{effect_id}")
            if effect_id:
                consumed_effect_ids.append(effect_id)
        elif mastery == "sap":
            disadvantage_sources.append(f"mastery_sap:{effect_id}")
            if effect_id:
                consumed_effect_ids.append(effect_id)

    return {
        "advantage_sources": advantage_sources,
        "disadvantage_sources": disadvantage_sources,
        "consumed_effect_ids": consumed_effect_ids,
    }


def consume_attack_roll_weapon_mastery_effects(*, actor: EncounterEntity, effect_ids: list[str]) -> list[str]:
    if not effect_ids:
        return []
    effect_id_set = {effect_id for effect_id in effect_ids if isinstance(effect_id, str) and effect_id}
    if not effect_id_set:
        return []

    removed: list[str] = []
    retained: list[dict[str, Any]] = []
    for effect in actor.turn_effects:
        effect_id = str(effect.get("effect_id") or "")
        if effect_id in effect_id_set and _is_weapon_mastery_effect(effect):
            removed.append(effect_id)
            continue
        retained.append(effect)
    actor.turn_effects = retained
    return removed


def apply_weapon_mastery_on_hit(
    *,
    encounter: Encounter,
    encounter_id: str,
    actor: EncounterEntity,
    target: EncounterEntity,
    attack_context: dict[str, Any],
    resolution: dict[str, Any],
    mastery_rolls: dict[str, Any] | None,
    resolve_saving_throw: ResolveSavingThrow,
    resolve_forced_movement: ResolveForcedMovement,
) -> dict[str, Any]:
    mastery = str(attack_context.get("weapon_mastery") or "").lower()
    if mastery not in {"vex", "sap", "slow", "topple", "graze", "push"}:
        return {"applied_effects": []}

    if not resolution.get("hit"):
        if mastery == "graze":
            return {"applied_effects": [], "graze": _build_graze_result(attack_context)}
        return {"applied_effects": []}

    damage_dealt = _resolve_damage_dealt(resolution)
    applied: list[dict[str, Any]] = []
    results: dict[str, Any] = {"applied_effects": applied}
    mastery_rolls = mastery_rolls or {}

    if mastery == "vex" and damage_dealt > 0:
        _remove_matching_mastery_effects(
            entity=actor,
            mastery="vex",
            source_entity_id=actor.entity_id,
            target_entity_id=target.entity_id,
        )
        effect = _build_mastery_effect(
            mastery="vex",
            name="Vex",
            source_entity_id=actor.entity_id,
            source_name=actor.name,
            target_entity_id=target.entity_id,
            source_ref=str(attack_context.get("attack_name") or attack_context.get("weapon_id") or "weapon"),
            expires_on="end_of_source_turn",
        )
        actor.turn_effects.append(effect)
        applied.append(effect)
    elif mastery == "sap":
        _remove_matching_mastery_effects(
            entity=target,
            mastery="sap",
            source_entity_id=actor.entity_id,
            target_entity_id=target.entity_id,
        )
        effect = _build_mastery_effect(
            mastery="sap",
            name="Sap",
            source_entity_id=actor.entity_id,
            source_name=actor.name,
            target_entity_id=target.entity_id,
            source_ref=str(attack_context.get("attack_name") or attack_context.get("weapon_id") or "weapon"),
            expires_on="start_of_source_turn",
        )
        target.turn_effects.append(effect)
        applied.append(effect)
    elif mastery == "slow" and damage_dealt > 0:
        already_slowed = get_weapon_mastery_speed_penalty(target) > 0
        _remove_matching_mastery_effects(
            entity=target,
            mastery="slow",
            source_entity_id=actor.entity_id,
            target_entity_id=target.entity_id,
        )
        effect = _build_mastery_effect(
            mastery="slow",
            name="Slow",
            source_entity_id=actor.entity_id,
            source_name=actor.name,
            target_entity_id=target.entity_id,
            source_ref=str(attack_context.get("attack_name") or attack_context.get("weapon_id") or "weapon"),
            expires_on="start_of_source_turn",
        )
        effect["speed_penalty_feet"] = 10
        target.turn_effects.append(effect)
        if not already_slowed:
            _capture_actual_movement_spent(target)
            target.speed["remaining"] = max(0, target.speed["remaining"] - 10)
        applied.append(effect)
    elif mastery == "topple":
        topple_result = _resolve_topple(
            encounter_id=encounter_id,
            actor=actor,
            target=target,
            attack_context=attack_context,
            mastery_roll=mastery_rolls.get("topple"),
            resolve_saving_throw=resolve_saving_throw,
        )
        results["topple"] = topple_result
    elif mastery == "push":
        results["push"] = _resolve_push(
            encounter_id=encounter_id,
            actor=actor,
            target=target,
            attack_context=attack_context,
            damage_dealt=damage_dealt,
            resolve_forced_movement=resolve_forced_movement,
        )

    return results


def remove_expired_weapon_mastery_effects(
    *,
    encounter: Encounter,
    source_entity_id: str,
    timing: str,
) -> list[dict[str, str]]:
    removed: list[dict[str, str]] = []
    for entity in encounter.entities.values():
        retained: list[dict[str, Any]] = []
        for effect in entity.turn_effects:
            if (
                _is_weapon_mastery_effect(effect)
                and effect.get("source_entity_id") == source_entity_id
                and effect.get("expires_on") == timing
            ):
                removed.append(
                    {
                        "target_entity_id": entity.entity_id,
                        "effect_id": str(effect.get("effect_id") or ""),
                        "mastery": str(effect.get("mastery") or ""),
                    }
                )
                continue
            retained.append(effect)
        entity.turn_effects = retained
    return removed


def get_weapon_mastery_speed_penalty(entity: EncounterEntity) -> int:
    penalties = [
        int(effect.get("speed_penalty_feet", 0) or 0)
        for effect in entity.turn_effects
        if _is_weapon_mastery_effect(effect) and str(effect.get("mastery") or "").lower() == "slow"
    ]
    return max(penalties, default=0)


def build_weapon_mastery_effect_labels(entity: EncounterEntity) -> list[str]:
    labels: list[str] = []
    for effect in entity.turn_effects:
        if not _is_weapon_mastery_effect(effect):
            continue
        mastery = str(effect.get("mastery") or "").lower()
        source_name = str(effect.get("source_name") or effect.get("source_entity_id") or "未知来源")
        if mastery == "vex":
            labels.append(f"Vex（来自{source_name}）")
        elif mastery == "sap":
            labels.append(f"Sap（来自{source_name}）")
        elif mastery == "slow":
            labels.append(f"Slow（来自{source_name}）")
    return labels


def _is_weapon_mastery_effect(effect: Any) -> bool:
    return isinstance(effect, dict) and effect.get("effect_type") == "weapon_mastery"


def _build_mastery_effect(
    *,
    mastery: str,
    name: str,
    source_entity_id: str,
    source_name: str,
    target_entity_id: str,
    source_ref: str,
    expires_on: str,
) -> dict[str, Any]:
    return {
        "effect_id": f"effect_mastery_{uuid4().hex[:12]}",
        "effect_type": "weapon_mastery",
        "mastery": mastery,
        "name": name,
        "source_entity_id": source_entity_id,
        "source_name": source_name,
        "target_entity_id": target_entity_id,
        "source_ref": source_ref,
        "expires_on": expires_on,
    }


def _remove_matching_mastery_effects(
    *,
    entity: EncounterEntity,
    mastery: str,
    source_entity_id: str,
    target_entity_id: str,
) -> None:
    retained: list[dict[str, Any]] = []
    for effect in entity.turn_effects:
        if (
            _is_weapon_mastery_effect(effect)
            and str(effect.get("mastery") or "").lower() == mastery
            and effect.get("source_entity_id") == source_entity_id
            and effect.get("target_entity_id") == target_entity_id
        ):
            continue
        retained.append(effect)
    entity.turn_effects = retained


def _resolve_damage_dealt(resolution: dict[str, Any]) -> int:
    damage_resolution = resolution.get("damage_resolution")
    if isinstance(damage_resolution, dict):
        total_damage = damage_resolution.get("total_damage")
        if isinstance(total_damage, int):
            return total_damage
    hp_update = resolution.get("hp_update")
    if isinstance(hp_update, dict):
        hp_change = hp_update.get("hp_change")
        if isinstance(hp_change, int):
            return max(0, hp_change)
    return 0


def _capture_actual_movement_spent(entity: EncounterEntity) -> None:
    combat_flags = entity.combat_flags if isinstance(entity.combat_flags, dict) else {}
    if not isinstance(entity.combat_flags, dict):
        entity.combat_flags = combat_flags
    tracked = combat_flags.get("movement_spent_feet")
    if isinstance(tracked, int) and tracked >= 0:
        return
    combat_flags["movement_spent_feet"] = max(0, entity.speed["walk"] - entity.speed["remaining"])


def _resolve_topple(
    *,
    encounter_id: str,
    actor: EncounterEntity,
    target: EncounterEntity,
    attack_context: dict[str, Any],
    mastery_roll: Any,
    resolve_saving_throw: ResolveSavingThrow,
) -> dict[str, Any]:
    save_dc = 8 + int(attack_context.get("modifier_value", 0) or 0) + int(attack_context.get("proficiency_bonus", 0) or 0)
    result = {
        "status": "pending_save",
        "save_ability": "con",
        "save_dc": save_dc,
        "target_entity_id": target.entity_id,
        "target_name": target.name,
    }
    if not isinstance(mastery_roll, dict):
        return result

    roll_request = RollRequest(
        request_id=f"req_topple_{uuid4().hex[:12]}",
        encounter_id=encounter_id,
        actor_entity_id=target.entity_id,
        target_entity_id=target.entity_id,
        roll_type="saving_throw",
        formula="1d20+save_modifier",
        reason=f"{target.name} makes a CON save against Topple",
        context={
            "save_ability": "con",
            "save_dc": save_dc,
            "vantage": _normalize_vantage(mastery_roll.get("vantage")),
        },
    )
    base_roll = mastery_roll.get("base_roll")
    base_rolls = mastery_roll.get("base_rolls")
    save_result = resolve_saving_throw.execute(
        encounter_id=encounter_id,
        roll_request=roll_request,
        base_roll=base_roll if isinstance(base_roll, int) else None,
        base_rolls=base_rolls if isinstance(base_rolls, list) else None,
        metadata={"source": "weapon_mastery", "mastery": "topple"},
    )
    success = save_result.final_total >= save_dc
    applied_prone = False
    if not success and "prone" not in target.conditions:
        target.conditions.append("prone")
        applied_prone = True
    return {
        "status": "resolved",
        "save": {
            "request_id": save_result.request_id,
            "dc": save_dc,
            "total": save_result.final_total,
            "success": success,
            "dice_rolls": save_result.dice_rolls,
            "metadata": save_result.metadata,
        },
        "applied_prone": applied_prone,
        "save_dc": save_dc,
    }


def _normalize_vantage(value: Any) -> str:
    normalized = str(value or "normal").strip().lower()
    if normalized not in {"normal", "advantage", "disadvantage"}:
        return "normal"
    return normalized


def _build_graze_result(attack_context: dict[str, Any]) -> dict[str, Any]:
    damage = int(attack_context.get("modifier_value", 0) or 0)
    if damage <= 0:
        return {
            "status": "no_effect",
            "damage": 0,
            "damage_type": attack_context.get("primary_damage_type"),
        }
    return {
        "status": "resolved",
        "damage": damage,
        "damage_type": attack_context.get("primary_damage_type"),
    }


def _resolve_push(
    *,
    encounter_id: str,
    actor: EncounterEntity,
    target: EncounterEntity,
    attack_context: dict[str, Any],
    damage_dealt: int,
    resolve_forced_movement: ResolveForcedMovement,
) -> dict[str, Any]:
    if damage_dealt <= 0:
        return {"status": "no_effect", "reason": "no_damage"}
    return resolve_linear_push(
        encounter_id=encounter_id,
        actor=actor,
        target=target,
        resolve_forced_movement=resolve_forced_movement,
        steps=2,
        reason="weapon_mastery_push",
    )


def resolve_linear_push(
    *,
    encounter_id: str,
    actor: EncounterEntity,
    target: EncounterEntity,
    resolve_forced_movement: ResolveForcedMovement,
    steps: int,
    reason: str,
) -> dict[str, Any]:
    if target.size not in {"tiny", "small", "medium", "large"}:
        return {"status": "no_effect", "reason": "target_too_large"}

    path = _build_push_path(actor=actor, target=target, steps=steps)
    forced_result = resolve_forced_movement.execute(
        encounter_id=encounter_id,
        entity_id=target.entity_id,
        path=path,
        reason=reason,
        source_entity_id=actor.entity_id,
    )
    return {
        "status": "resolved",
        "target_entity_id": target.entity_id,
        "target_name": target.name,
        "start_position": forced_result["start_position"],
        "final_position": forced_result["final_position"],
        "attempted_path": forced_result["attempted_path"],
        "resolved_path": forced_result["resolved_path"],
        "moved_feet": forced_result["moved_feet"],
        "blocked": forced_result["blocked"],
        "block_reason": forced_result["block_reason"],
        "reason": forced_result["reason"],
    }


def _build_push_path(
    *,
    actor: EncounterEntity,
    target: EncounterEntity,
    steps: int,
) -> list[dict[str, int]]:
    actor_center = get_center_position(actor)
    target_center = get_center_position(target)
    dx = _normalize_axis_delta(target_center["x"] - actor_center["x"])
    dy = _normalize_axis_delta(target_center["y"] - actor_center["y"])
    if dx == 0 and dy == 0:
        dx = 1

    anchor = {"x": target.position["x"], "y": target.position["y"]}
    path: list[dict[str, int]] = []
    for _ in range(max(0, steps)):
        anchor = {"x": anchor["x"] + dx, "y": anchor["y"] + dy}
        path.append(dict(anchor))
    return path


def _normalize_axis_delta(delta: float) -> int:
    if delta > 0:
        return 1
    if delta < 0:
        return -1
    return 0
