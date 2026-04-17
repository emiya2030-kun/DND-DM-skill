"""Resolve combat proficiency defaults and overrides from entity class features."""

from __future__ import annotations

from typing import Any

from tools.repositories import ClassProficiencyDefinitionRepository
from tools.services.class_features.rogue import ensure_rogue_runtime

_WEAPON_ORDER = ["simple", "martial", "martial_light", "martial_finesse_or_light"]
_ARMOR_ORDER = ["light", "medium", "heavy", "shield"]
_SAVE_ORDER = ["str", "dex", "con", "int", "wis", "cha"]
_CLASS_PROFICIENCY_REPOSITORY = ClassProficiencyDefinitionRepository()


def resolve_entity_proficiencies(entity_or_class_features: Any) -> dict[str, list[str]]:
    class_features = _extract_class_features(entity_or_class_features)

    weapon_proficiencies: set[str] = set()
    armor_training: set[str] = set()
    save_proficiencies: set[str] = set()

    for class_id, runtime_bucket in class_features.items():
        if not isinstance(class_id, str) or not isinstance(runtime_bucket, dict):
            continue
        template = _CLASS_PROFICIENCY_REPOSITORY.get(class_id.strip().lower())
        if not isinstance(template, dict):
            continue

        _merge_string_list(weapon_proficiencies, template.get("weapon_proficiencies"))
        _merge_string_list(armor_training, template.get("armor_training"))
        _merge_string_list(save_proficiencies, template.get("save_proficiencies"))

        _merge_string_list(weapon_proficiencies, runtime_bucket.get("weapon_proficiencies"))
        _merge_string_list(armor_training, runtime_bucket.get("armor_training"))
        _merge_string_list(save_proficiencies, runtime_bucket.get("save_proficiencies"))

    return {
        "weapon_proficiencies": _ordered(weapon_proficiencies, _WEAPON_ORDER),
        "armor_training": _ordered(armor_training, _ARMOR_ORDER),
        "save_proficiencies": _ordered(save_proficiencies, _SAVE_ORDER),
    }


def resolve_entity_save_proficiencies(entity: Any) -> list[str]:
    resolved = set(resolve_entity_proficiencies(entity)["save_proficiencies"])
    _merge_string_list(resolved, _extract_save_proficiencies(entity))
    rogue_runtime = ensure_rogue_runtime(entity)
    slippery_mind = rogue_runtime.get("slippery_mind")
    if isinstance(slippery_mind, dict) and slippery_mind.get("enabled"):
        resolved.update({"wis", "cha"})
    return _ordered(resolved, _SAVE_ORDER)


def resolve_entity_skill_proficiencies(entity: Any) -> list[str]:
    source_ref = _extract_source_ref(entity)
    proficiencies: set[str] = set()
    _merge_string_list(proficiencies, source_ref.get("skill_proficiencies"))
    return sorted(proficiencies)


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


def _extract_save_proficiencies(entity: Any) -> Any:
    if isinstance(entity, dict):
        return entity.get("save_proficiencies")
    return getattr(entity, "save_proficiencies", [])


def _extract_source_ref(entity: Any) -> dict[str, Any]:
    if isinstance(entity, dict):
        source_ref = entity.get("source_ref")
    else:
        source_ref = getattr(entity, "source_ref", None)
    if isinstance(source_ref, dict):
        return source_ref
    return {}


def _merge_string_list(target: set[str], values: Any) -> None:
    if not isinstance(values, list):
        return

    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
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
