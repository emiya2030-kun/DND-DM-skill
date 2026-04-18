from __future__ import annotations

from typing import Any


def get_class_runtime(entity_or_class_features: Any, class_id: str) -> dict[str, Any]:
    class_features = _read_class_features(entity_or_class_features)
    bucket = class_features.get(class_id)
    if isinstance(bucket, dict):
        return bucket
    return {}


def ensure_class_runtime(entity_or_class_features: Any, class_id: str) -> dict[str, Any]:
    class_features = _ensure_class_features(entity_or_class_features)
    bucket = class_features.get(class_id)
    if isinstance(bucket, dict):
        return bucket
    class_features[class_id] = {}
    return class_features[class_id]


def get_fighter_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    return get_class_runtime(entity_or_class_features, "fighter")


def ensure_fighter_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    return ensure_class_runtime(entity_or_class_features, "fighter")


def get_monk_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "monk")
    if not runtime:
        return {}
    return ensure_monk_runtime(entity_or_class_features)


def ensure_monk_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    monk = ensure_class_runtime(entity_or_class_features, "monk")
    level = int(monk.get("level", 0) or 0)

    explicit_martial_arts_die = monk.get("martial_arts_die")
    monk["martial_arts_die"] = (
        _resolve_monk_martial_arts_die(level)
        if level > 0
        else explicit_martial_arts_die if isinstance(explicit_martial_arts_die, str) and explicit_martial_arts_die.strip() else "1d6"
    )
    explicit_unarmored_movement = monk.get("unarmored_movement_bonus_feet")
    monk["unarmored_movement_bonus_feet"] = (
        _resolve_monk_unarmored_movement_bonus(level)
        if level > 0
        else explicit_unarmored_movement if isinstance(explicit_unarmored_movement, int) else 0
    )

    focus_points = monk.setdefault("focus_points", {})
    focus_points["max"] = _resolve_monk_focus_points_max(level) if level > 0 else int(focus_points.get("max", 0) or 0)
    remaining = focus_points.get("remaining")
    focus_points["remaining"] = remaining if isinstance(remaining, int) else focus_points["max"]

    martial_arts = monk.setdefault("martial_arts", {})
    explicit_martial_arts_enabled = martial_arts.get("enabled")
    martial_arts["enabled"] = explicit_martial_arts_enabled if isinstance(explicit_martial_arts_enabled, bool) else level >= 1
    if not isinstance(martial_arts.get("grapple_dc_ability"), str):
        martial_arts["grapple_dc_ability"] = "dex"

    uncanny_metabolism = monk.setdefault("uncanny_metabolism", {})
    explicit_uncanny_metabolism_available = uncanny_metabolism.get("available")
    uncanny_metabolism["available"] = (
        explicit_uncanny_metabolism_available
        if isinstance(explicit_uncanny_metabolism_available, bool)
        else level >= 2
    )

    deflect_attacks = monk.setdefault("deflect_attacks", {})
    explicit_deflect_attacks_enabled = deflect_attacks.get("enabled")
    deflect_attacks["enabled"] = bool(explicit_deflect_attacks_enabled) or level >= 3

    slow_fall = monk.setdefault("slow_fall", {})
    explicit_slow_fall_enabled = slow_fall.get("enabled")
    slow_fall["enabled"] = bool(explicit_slow_fall_enabled) or level >= 4

    stunning_strike = monk.setdefault("stunning_strike", {})
    explicit_stunning_strike_enabled = stunning_strike.get("enabled")
    stunning_strike["enabled"] = bool(explicit_stunning_strike_enabled) or level >= 5
    if not isinstance(stunning_strike.get("max_per_turn"), int):
        stunning_strike["max_per_turn"] = 1
    stunning_strike.setdefault("uses_this_turn", 0)

    empowered_strikes = monk.setdefault("empowered_strikes", {})
    explicit_empowered_strikes_enabled = empowered_strikes.get("enabled")
    empowered_strikes["enabled"] = bool(explicit_empowered_strikes_enabled) or level >= 6

    evasion = monk.setdefault("evasion", {})
    explicit_evasion_enabled = evasion.get("enabled")
    evasion["enabled"] = bool(explicit_evasion_enabled) or level >= 7

    heightened_focus = monk.setdefault("heightened_focus", {})
    explicit_heightened_focus_enabled = heightened_focus.get("enabled")
    heightened_focus["enabled"] = bool(explicit_heightened_focus_enabled) or level >= 10

    deflect_energy = monk.setdefault("deflect_energy", {})
    explicit_deflect_energy_enabled = deflect_energy.get("enabled")
    deflect_energy["enabled"] = bool(explicit_deflect_energy_enabled) or level >= 13

    return monk


def get_barbarian_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    return get_class_runtime(entity_or_class_features, "barbarian")


def ensure_barbarian_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    return ensure_class_runtime(entity_or_class_features, "barbarian")


def get_paladin_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "paladin")
    if not runtime:
        return {}
    return ensure_paladin_runtime(entity_or_class_features)


def ensure_paladin_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    paladin = ensure_class_runtime(entity_or_class_features, "paladin")
    level = int(paladin.get("level", 0) or 0)

    lay_on_hands = paladin.setdefault("lay_on_hands", {})
    lay_on_hands["pool_max"] = level * 5 if level > 0 else int(lay_on_hands.get("pool_max", 0) or 0)
    pool_remaining = lay_on_hands.get("pool_remaining")
    lay_on_hands["pool_remaining"] = pool_remaining if isinstance(pool_remaining, int) else lay_on_hands["pool_max"]

    divine_smite = paladin.setdefault("divine_smite", {})
    explicit_divine_smite_enabled = divine_smite.get("enabled")
    divine_smite["enabled"] = explicit_divine_smite_enabled if isinstance(explicit_divine_smite_enabled, bool) else level >= 2

    aura_of_protection = paladin.setdefault("aura_of_protection", {})
    explicit_aura_enabled = aura_of_protection.get("enabled")
    aura_of_protection["enabled"] = explicit_aura_enabled if isinstance(explicit_aura_enabled, bool) else level >= 6
    radius_feet = aura_of_protection.get("radius_feet")
    aura_of_protection["radius_feet"] = radius_feet if isinstance(radius_feet, int) else 10

    radiant_strikes = paladin.setdefault("radiant_strikes", {})
    explicit_radiant_strikes_enabled = radiant_strikes.get("enabled")
    radiant_strikes["enabled"] = (
        explicit_radiant_strikes_enabled if isinstance(explicit_radiant_strikes_enabled, bool) else level >= 11
    )

    return paladin


def _read_class_features(entity_or_class_features: Any) -> dict[str, Any]:
    if isinstance(entity_or_class_features, dict):
        class_features = entity_or_class_features.get("class_features")
        if isinstance(class_features, dict):
            return class_features
        return {}

    class_features = getattr(entity_or_class_features, "class_features", None)
    if isinstance(class_features, dict):
        return class_features
    return {}


def _ensure_class_features(entity_or_class_features: Any) -> dict[str, Any]:
    if isinstance(entity_or_class_features, dict):
        class_features = entity_or_class_features.get("class_features")
        if isinstance(class_features, dict):
            return class_features
        entity_or_class_features["class_features"] = {}
        return entity_or_class_features["class_features"]

    class_features = getattr(entity_or_class_features, "class_features", None)
    if isinstance(class_features, dict):
        return class_features

    setattr(entity_or_class_features, "class_features", {})
    return entity_or_class_features.class_features


def _resolve_monk_martial_arts_die(level: int) -> str:
    if level >= 17:
        return "1d12"
    if level >= 11:
        return "1d10"
    if level >= 5:
        return "1d8"
    return "1d6"


def _resolve_monk_focus_points_max(level: int) -> int:
    return level if level >= 2 else 0


def _resolve_monk_unarmored_movement_bonus(level: int) -> int:
    if level >= 18:
        return 30
    if level >= 14:
        return 25
    if level >= 10:
        return 20
    if level >= 6:
        return 15
    if level >= 2:
        return 10
    return 0
