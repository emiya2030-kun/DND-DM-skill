from __future__ import annotations

from tools.services.class_features.shared.runtime import ensure_class_runtime

_SNEAK_ATTACK_THRESHOLDS = (
    (19, "10d6"),
    (17, "9d6"),
    (15, "8d6"),
    (13, "7d6"),
    (11, "6d6"),
    (9, "5d6"),
    (7, "4d6"),
    (5, "3d6"),
    (3, "2d6"),
    (1, "1d6"),
)


def resolve_rogue_sneak_attack_dice(level: int) -> str:
    for threshold, dice in _SNEAK_ATTACK_THRESHOLDS:
        if level >= threshold:
            return dice
    return "1d6"


def ensure_rogue_runtime(entity_or_class_features: object) -> dict:
    rogue = ensure_class_runtime(entity_or_class_features, "rogue")
    level = rogue.get("level", 0)
    if isinstance(level, bool) or not isinstance(level, int):
        level = 0

    rogue.setdefault("expertise", {"skills": []})
    sneak_attack = rogue.setdefault("sneak_attack", {})
    sneak_attack["damage_dice"] = resolve_rogue_sneak_attack_dice(level)
    sneak_attack["used_this_turn"] = bool(sneak_attack.get("used_this_turn", False))

    rogue.setdefault(
        "steady_aim",
        {
            "enabled": level >= 3,
            "used_this_turn": False,
            "grants_advantage_on_next_attack": False,
        },
    )
    rogue["steady_aim"]["enabled"] = level >= 3

    rogue.setdefault(
        "cunning_strike",
        {
            "enabled": level >= 5,
            "max_effects_per_hit": 2 if level >= 11 else 1,
        },
    )
    rogue["cunning_strike"]["enabled"] = level >= 5
    rogue["cunning_strike"]["max_effects_per_hit"] = 2 if level >= 11 else 1

    rogue.setdefault("uncanny_dodge", {"enabled": level >= 5})
    rogue["uncanny_dodge"]["enabled"] = level >= 5

    rogue.setdefault("reliable_talent", {"enabled": level >= 7})
    rogue["reliable_talent"]["enabled"] = level >= 7

    rogue.setdefault("slippery_mind", {"enabled": level >= 15})
    rogue["slippery_mind"]["enabled"] = level >= 15

    rogue.setdefault("elusive", {"enabled": level >= 18})
    rogue["elusive"]["enabled"] = level >= 18
    return rogue
