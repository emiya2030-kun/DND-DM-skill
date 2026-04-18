from __future__ import annotations

import random
import re
from typing import Any

_FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")
_FLAT_RE = re.compile(r"^[+]?(\d+)$")

TRANSMUTED_DAMAGE_TYPES = {"acid", "cold", "fire", "lightning", "poison", "thunder"}


def normalize_transmuted_damage_type(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized not in TRANSMUTED_DAMAGE_TYPES:
        return None
    return normalized


def spell_supports_extended_spell(spell_definition: dict[str, Any]) -> bool:
    base = spell_definition.get("base")
    if not isinstance(base, dict):
        return False
    if bool(base.get("concentration")):
        return True
    duration = base.get("duration")
    if not isinstance(duration, str):
        return False
    lowered = duration.strip().lower()
    return any(token in lowered for token in ("minute", "hour", "day", "month", "year"))


def spell_supports_twinned_spell(spell_definition: dict[str, Any]) -> bool:
    targeting = spell_definition.get("targeting")
    if not isinstance(targeting, dict) or targeting.get("type") != "single_target":
        return False
    scaling = spell_definition.get("scaling")
    if not isinstance(scaling, dict):
        return False
    slot_level_bonus = scaling.get("slot_level_bonus")
    if not isinstance(slot_level_bonus, dict):
        return False
    additional_targets = slot_level_bonus.get("additional_targets_per_extra_level")
    return isinstance(additional_targets, int) and additional_targets > 0


def spell_supports_transmuted_spell(spell_definition: dict[str, Any]) -> bool:
    return bool(_collect_transmutable_damage_sources(spell_definition))


def apply_transmuted_damage_parts(
    *,
    damage_parts: list[dict[str, Any]],
    replacement_damage_type: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    normalized_type = normalize_transmuted_damage_type(replacement_damage_type)
    copied_parts = [dict(part) for part in damage_parts]
    if normalized_type is None:
        return copied_parts, None

    changed_sources: list[str] = []
    for part in copied_parts:
        current_type = part.get("damage_type")
        if isinstance(current_type, str) and current_type.strip().lower() in TRANSMUTED_DAMAGE_TYPES:
            part["damage_type"] = normalized_type
            source = part.get("source")
            if isinstance(source, str) and source.strip():
                changed_sources.append(source.strip())

    if not changed_sources:
        return copied_parts, None
    return (
        copied_parts,
        {
            "metamagic_id": "transmuted_spell",
            "applied": True,
            "replacement_damage_type": normalized_type,
            "changed_sources": changed_sources,
        },
    )


def apply_empowered_spell_to_damage_rolls(
    *,
    damage_parts: list[dict[str, Any]],
    indexed_rolls: dict[str, list[int]],
    charisma_modifier: int,
) -> tuple[dict[str, list[int]], dict[str, Any] | None]:
    reroll_limit = max(1, int(charisma_modifier or 0))
    updated_rolls = {source: list(rolls) for source, rolls in indexed_rolls.items()}

    candidates: list[dict[str, Any]] = []
    for part_order, part in enumerate(damage_parts):
        source = part.get("source")
        if not isinstance(source, str) or source not in updated_rolls:
            continue
        parsed = _parse_formula(str(part.get("formula") or ""))
        if parsed is None:
            continue
        dice_count, die_size, _ = parsed
        if dice_count <= 0:
            continue
        average = (die_size + 1) / 2
        rolls = updated_rolls[source]
        for roll_index, roll_value in enumerate(rolls):
            if roll_value >= average:
                continue
            candidates.append(
                {
                    "source": source,
                    "roll_index": roll_index,
                    "old_value": roll_value,
                    "die_size": die_size,
                    "gain": average - roll_value,
                    "part_order": part_order,
                }
            )

    if not candidates:
        return updated_rolls, None

    candidates.sort(key=lambda item: (-item["gain"], item["part_order"], item["roll_index"]))
    rerolls: list[dict[str, Any]] = []
    for candidate in candidates[:reroll_limit]:
        new_value = random.randint(1, candidate["die_size"])
        updated_rolls[candidate["source"]][candidate["roll_index"]] = new_value
        rerolls.append(
            {
                "source": candidate["source"],
                "roll_index": candidate["roll_index"],
                "old_value": candidate["old_value"],
                "new_value": new_value,
            }
        )

    return (
        updated_rolls,
        {
            "metamagic_id": "empowered_spell",
            "applied": True,
            "rerolled_count": len(rerolls),
            "rerolls": rerolls,
        },
    )


def reroll_missed_spell_attack(
    *,
    attack_roll: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    dice_rolls = attack_roll.get("dice_rolls")
    if not isinstance(dice_rolls, dict):
        return attack_roll, None

    chosen_roll = dice_rolls.get("chosen_roll")
    modifier = dice_rolls.get("modifier")
    if not isinstance(chosen_roll, int):
        base_rolls = dice_rolls.get("base_rolls")
        if isinstance(base_rolls, list) and base_rolls and isinstance(base_rolls[0], int):
            chosen_roll = base_rolls[0]
    if not isinstance(chosen_roll, int):
        return attack_roll, None
    if not isinstance(modifier, int):
        final_total = attack_roll.get("final_total")
        if not isinstance(final_total, int):
            return attack_roll, None
        modifier = final_total - chosen_roll

    new_roll = random.randint(1, 20)
    updated = {
        "final_total": new_roll + modifier,
        "dice_rolls": {
            **dice_rolls,
            "base_rolls": [new_roll],
            "chosen_roll": new_roll,
            "modifier": modifier,
            "rerolled_from": chosen_roll,
        },
    }
    return (
        updated,
        {
            "metamagic_id": "seeking_spell",
            "applied": True,
            "old_roll": chosen_roll,
            "new_roll": new_roll,
        },
    )


def _collect_transmutable_damage_sources(spell_definition: dict[str, Any]) -> list[str]:
    on_cast = spell_definition.get("on_cast")
    if not isinstance(on_cast, dict):
        return []

    sources: list[str] = []
    for outcome_key in ("on_hit", "on_failed_save", "on_successful_save"):
        outcome = on_cast.get(outcome_key)
        if not isinstance(outcome, dict):
            continue
        raw_damage_parts = outcome.get("damage_parts")
        if not isinstance(raw_damage_parts, list):
            continue
        for part in raw_damage_parts:
            if not isinstance(part, dict):
                continue
            damage_type = part.get("damage_type")
            if isinstance(damage_type, str) and damage_type.strip().lower() in TRANSMUTED_DAMAGE_TYPES:
                source = part.get("source")
                if isinstance(source, str) and source.strip():
                    sources.append(source.strip())
    return sources


def _parse_formula(formula: str) -> tuple[int, int, int] | None:
    match = _FORMULA_RE.match(formula)
    if match is not None:
        return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)
    flat_match = _FLAT_RE.match(formula)
    if flat_match is not None:
        return 0, 1, int(flat_match.group(1))
    return None
