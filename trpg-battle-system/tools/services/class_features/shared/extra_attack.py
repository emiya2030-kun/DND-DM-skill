from __future__ import annotations

from typing import Any


def resolve_extra_attack_count(class_features: dict[str, Any]) -> int:
    highest_count = 1
    fighter = class_features.get("fighter")
    if isinstance(fighter, dict):
        highest_count = max(highest_count, _coerce_attack_count(fighter.get("extra_attack_count")))
        highest_count = max(highest_count, _resolve_fighter_extra_attack_count(fighter))
        for source in fighter.get("extra_attack_sources", []):
            if not isinstance(source, dict):
                continue
            highest_count = max(highest_count, _coerce_attack_count(source.get("attack_count")))

    for class_id in ("barbarian", "monk", "paladin", "ranger"):
        bucket = class_features.get(class_id)
        if not isinstance(bucket, dict):
            continue
        highest_count = max(highest_count, _coerce_attack_count(bucket.get("extra_attack_count")))
        level = bucket.get("level")
        if isinstance(level, int) and not isinstance(level, bool) and level >= 5:
            highest_count = max(highest_count, 2)

    return highest_count


def _coerce_attack_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if not isinstance(value, int):
        return 0
    return value


def _resolve_fighter_extra_attack_count(fighter: dict[str, Any]) -> int:
    level = fighter.get("level", fighter.get("fighter_level"))
    if not isinstance(level, int) or isinstance(level, bool):
        return 0
    if level >= 20:
        return 4
    if level >= 11:
        return 3
    if level >= 5:
        return 2
    return 1
