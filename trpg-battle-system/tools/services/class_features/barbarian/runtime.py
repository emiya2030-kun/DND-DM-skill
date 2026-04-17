from __future__ import annotations

from typing import Any

from tools.services.class_features.shared.runtime import ensure_class_runtime, get_class_runtime


def get_barbarian_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "barbarian")
    if not runtime:
        return {}
    return ensure_barbarian_runtime(entity_or_class_features)


def ensure_barbarian_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    barbarian = ensure_class_runtime(entity_or_class_features, "barbarian")
    level = int(barbarian.get("level", 0) or 0)

    rage = barbarian.setdefault("rage", {})
    rage_max = _resolve_rage_uses(level)
    rage["max"] = rage_max
    remaining = rage.get("remaining")
    rage["remaining"] = remaining if isinstance(remaining, int) else rage_max
    rage.setdefault("active", False)
    rage.setdefault("ends_at_turn_end_of", None)
    rage["persistent_rage"] = level >= 15
    rage.setdefault("restored_on_initiative_this_long_rest", False)

    barbarian["rage_damage_bonus"] = _resolve_rage_damage_bonus(level)
    barbarian["weapon_mastery_count"] = _resolve_weapon_mastery_count(level)

    danger_sense = barbarian.setdefault("danger_sense", {})
    danger_sense["enabled"] = level >= 2

    reckless_attack = barbarian.setdefault("reckless_attack", {})
    reckless_attack["enabled"] = level >= 2
    reckless_attack.setdefault("declared_this_turn", False)
    reckless_attack.setdefault("active_until_turn_start_of", None)

    primal_knowledge = barbarian.setdefault("primal_knowledge", {})
    primal_knowledge["enabled"] = level >= 3

    feral_instinct = barbarian.setdefault("feral_instinct", {})
    feral_instinct["enabled"] = level >= 7

    instinctive_pounce = barbarian.setdefault("instinctive_pounce", {})
    instinctive_pounce["enabled"] = level >= 7

    brutal_strike = barbarian.setdefault("brutal_strike", {})
    brutal_strike["enabled"] = level >= 9
    brutal_strike["extra_damage_dice"] = "2d10" if level >= 17 else "1d10"
    brutal_strike["max_effects"] = 2 if level >= 17 else 1

    relentless_rage = barbarian.setdefault("relentless_rage", {})
    relentless_rage["enabled"] = level >= 11
    current_dc = relentless_rage.get("current_dc")
    relentless_rage["current_dc"] = current_dc if isinstance(current_dc, int) else 10

    indomitable_might = barbarian.setdefault("indomitable_might", {})
    indomitable_might["enabled"] = level >= 18

    return barbarian


def _resolve_rage_uses(level: int) -> int:
    if level >= 17:
        return 6
    if level >= 12:
        return 5
    if level >= 6:
        return 4
    if level >= 3:
        return 3
    return 2


def _resolve_rage_damage_bonus(level: int) -> int:
    if level >= 16:
        return 4
    if level >= 9:
        return 3
    return 2


def _resolve_weapon_mastery_count(level: int) -> int:
    if level >= 10:
        return 4
    if level >= 4:
        return 3
    return 2
