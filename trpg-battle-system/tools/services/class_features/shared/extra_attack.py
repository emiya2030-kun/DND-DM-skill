from __future__ import annotations

from typing import Any


def resolve_extra_attack_count(class_features: dict[str, Any]) -> int:
    fighter = class_features.get("fighter")
    if not isinstance(fighter, dict):
        return 1

    highest_count = 1
    highest_count = max(highest_count, _coerce_attack_count(fighter.get("extra_attack_count")))

    for source in fighter.get("extra_attack_sources", []):
        if not isinstance(source, dict):
            continue
        highest_count = max(highest_count, _coerce_attack_count(source.get("attack_count")))

    return highest_count


def _coerce_attack_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if not isinstance(value, int):
        return 0
    return value
