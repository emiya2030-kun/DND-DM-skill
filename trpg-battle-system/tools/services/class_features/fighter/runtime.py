from __future__ import annotations

from typing import Any

from tools.services.class_features.shared.runtime import ensure_class_runtime, get_class_runtime


def get_fighter_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    runtime = get_class_runtime(entity_or_class_features, "fighter")
    if not runtime:
        return {}
    return ensure_fighter_runtime(entity_or_class_features)


def ensure_fighter_runtime(entity_or_class_features: Any) -> dict[str, Any]:
    fighter = ensure_class_runtime(entity_or_class_features, "fighter")
    level = _resolve_level(fighter)

    fighter["fighter_level"] = level
    fighter["weapon_mastery_count"] = (
        _resolve_weapon_mastery_count(level)
        if level > 0
        else _coerce_non_negative_int(fighter.get("weapon_mastery_count"), default=0)
    )
    fighter["extra_attack_count"] = (
        _resolve_extra_attack_count(level)
        if level > 0
        else _coerce_non_negative_int(fighter.get("extra_attack_count"), default=1)
    )
    fighter["extra_attack_sources"] = [{"source": "fighter", "attack_count": fighter["extra_attack_count"]}]

    fighting_style = fighter.setdefault("fighting_style", {})
    explicit_fighting_style_enabled = fighting_style.get("enabled")
    fighting_style["enabled"] = (
        explicit_fighting_style_enabled if isinstance(explicit_fighting_style_enabled, bool) else level >= 1
    )

    second_wind = fighter.setdefault("second_wind", {})
    explicit_second_wind_enabled = second_wind.get("enabled")
    second_wind["enabled"] = (
        explicit_second_wind_enabled if isinstance(explicit_second_wind_enabled, bool) else level >= 1
    )
    second_wind["max_uses"] = (
        _resolve_second_wind_uses(level)
        if level > 0
        else _coerce_non_negative_int(second_wind.get("max_uses"), default=0)
    )
    remaining_second_wind = second_wind.get("remaining_uses")
    second_wind["remaining_uses"] = (
        remaining_second_wind if isinstance(remaining_second_wind, int) else second_wind["max_uses"]
    )
    second_wind["recovery"] = "short_or_long_rest" if level >= 1 else None
    second_wind["short_rest_restore_uses"] = 1 if level >= 1 else 0

    tactical_mind = fighter.setdefault("tactical_mind", {})
    explicit_tactical_mind_enabled = tactical_mind.get("enabled")
    tactical_mind["enabled"] = (
        explicit_tactical_mind_enabled if isinstance(explicit_tactical_mind_enabled, bool) else level >= 2
    )
    tactical_mind["die"] = "1d10" if level >= 2 else None

    tactical_shift = fighter.setdefault("tactical_shift", {})
    explicit_tactical_shift_enabled = tactical_shift.get("enabled")
    tactical_shift["enabled"] = (
        explicit_tactical_shift_enabled if isinstance(explicit_tactical_shift_enabled, bool) else level >= 2
    )
    tactical_shift["movement_feet_formula"] = "half_speed" if level >= 2 else None
    tactical_shift["ignore_opportunity_attacks"] = level >= 2

    action_surge = fighter.setdefault("action_surge", {})
    explicit_action_surge_enabled = action_surge.get("enabled")
    action_surge["enabled"] = (
        explicit_action_surge_enabled if isinstance(explicit_action_surge_enabled, bool) else level >= 2
    )
    action_surge["max_uses"] = (
        _resolve_action_surge_uses(level)
        if level > 0
        else _coerce_non_negative_int(action_surge.get("max_uses"), default=0)
    )
    remaining_action_surge = action_surge.get("remaining_uses")
    action_surge["remaining_uses"] = (
        remaining_action_surge if isinstance(remaining_action_surge, int) else action_surge["max_uses"]
    )
    used_this_turn = action_surge.get("used_this_turn")
    action_surge["used_this_turn"] = used_this_turn if isinstance(used_this_turn, bool) else False
    action_surge["recovery"] = "short_or_long_rest" if level >= 2 else None

    indomitable = fighter.setdefault("indomitable", {})
    explicit_indomitable_enabled = indomitable.get("enabled")
    indomitable["enabled"] = (
        explicit_indomitable_enabled if isinstance(explicit_indomitable_enabled, bool) else level >= 9
    )
    indomitable["max_uses"] = (
        _resolve_indomitable_uses(level)
        if level > 0
        else _coerce_non_negative_int(indomitable.get("max_uses"), default=0)
    )
    remaining_indomitable = indomitable.get("remaining_uses")
    indomitable["remaining_uses"] = (
        remaining_indomitable if isinstance(remaining_indomitable, int) else indomitable["max_uses"]
    )
    indomitable["recovery"] = "long_rest" if level >= 9 else None
    indomitable["fighter_level_bonus"] = level if level >= 9 else 0

    tactical_master = fighter.setdefault("tactical_master", {})
    explicit_tactical_master_root = fighter.get("tactical_master_enabled")
    explicit_tactical_master_enabled = tactical_master.get("enabled")
    tactical_master["enabled"] = (
        explicit_tactical_master_root
        if isinstance(explicit_tactical_master_root, bool)
        else explicit_tactical_master_enabled
        if isinstance(explicit_tactical_master_enabled, bool)
        else level >= 9
    )
    tactical_master["mastery_options"] = ["push", "sap", "slow"] if level >= 9 else []
    fighter["tactical_master_enabled"] = bool(tactical_master["enabled"])

    studied_attacks_feature = fighter.setdefault("studied_attacks_feature", {})
    explicit_studied_attacks_enabled = studied_attacks_feature.get("enabled")
    studied_attacks_feature["enabled"] = (
        explicit_studied_attacks_enabled if isinstance(explicit_studied_attacks_enabled, bool) else level >= 13
    )

    studied_attacks = fighter.get("studied_attacks")
    fighter["studied_attacks"] = list(studied_attacks) if isinstance(studied_attacks, list) else []

    turn_counters = fighter.get("turn_counters")
    fighter["turn_counters"] = dict(turn_counters) if isinstance(turn_counters, dict) else {}
    attack_action_attacks_used = fighter["turn_counters"].get("attack_action_attacks_used")
    fighter["turn_counters"]["attack_action_attacks_used"] = (
        attack_action_attacks_used
        if isinstance(attack_action_attacks_used, int) and attack_action_attacks_used >= 0
        else 0
    )

    temporary_bonuses = fighter.get("temporary_bonuses")
    fighter["temporary_bonuses"] = dict(temporary_bonuses) if isinstance(temporary_bonuses, dict) else {}
    extra_non_magic_action_available = fighter["temporary_bonuses"].get("extra_non_magic_action_available")
    fighter["temporary_bonuses"]["extra_non_magic_action_available"] = (
        extra_non_magic_action_available
        if isinstance(extra_non_magic_action_available, int) and extra_non_magic_action_available >= 0
        else 0
    )

    return fighter


def _resolve_level(fighter: dict[str, Any]) -> int:
    level = fighter.get("level", fighter.get("fighter_level", 0))
    if isinstance(level, bool) or not isinstance(level, int):
        return 0
    return max(0, level)


def _resolve_second_wind_uses(level: int) -> int:
    if level >= 17:
        return 4
    if level >= 10:
        return 3
    return 2 if level >= 1 else 0


def _resolve_action_surge_uses(level: int) -> int:
    if level >= 17:
        return 2
    return 1 if level >= 2 else 0


def _resolve_indomitable_uses(level: int) -> int:
    if level >= 17:
        return 3
    if level >= 13:
        return 2
    return 1 if level >= 9 else 0


def _resolve_extra_attack_count(level: int) -> int:
    if level >= 20:
        return 4
    if level >= 11:
        return 3
    if level >= 5:
        return 2
    return 1


def _resolve_weapon_mastery_count(level: int) -> int:
    if level >= 16:
        return 6
    if level >= 10:
        return 5
    if level >= 4:
        return 4
    return 3 if level >= 1 else 0


def _coerce_non_negative_int(value: Any, *, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return default
    return value
