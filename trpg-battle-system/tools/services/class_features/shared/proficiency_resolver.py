"""Resolve combat proficiency defaults and overrides from entity class features."""

from __future__ import annotations

from typing import Any

_WEAPON_ORDER = ["simple", "martial"]
_ARMOR_ORDER = ["light", "medium", "heavy", "shield"]


def resolve_entity_proficiencies(entity_or_class_features: Any) -> dict[str, list[str]]:
    class_features = _extract_class_features(entity_or_class_features)
    fighter = class_features.get("fighter")

    weapon_proficiencies: set[str] = set()
    armor_training: set[str] = set()

    if isinstance(fighter, dict):
        weapon_proficiencies.update(_WEAPON_ORDER)
        armor_training.update(_ARMOR_ORDER)
        _merge_string_list(weapon_proficiencies, fighter.get("weapon_proficiencies"))
        _merge_string_list(armor_training, fighter.get("armor_training"))

    return {
        "weapon_proficiencies": _ordered(weapon_proficiencies, _WEAPON_ORDER),
        "armor_training": _ordered(armor_training, _ARMOR_ORDER),
    }


def _extract_class_features(entity_or_class_features: Any) -> dict[str, Any]:
    if isinstance(entity_or_class_features, dict):
        class_features = entity_or_class_features.get("class_features")
        if isinstance(class_features, dict):
            return class_features
        return {}

    class_features = getattr(entity_or_class_features, "class_features", None)
    if isinstance(class_features, dict):
        return class_features
    return {}


def _merge_string_list(target: set[str], values: Any) -> None:
    if not isinstance(values, list):
        return

    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized:
            target.add(normalized)


def _ordered(source: set[str], order: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()

    for key in order:
        if key in source and key not in seen:
            ordered.append(key)
            seen.add(key)

    extras = sorted(source - seen)
    ordered.extend(extras)
    return ordered
