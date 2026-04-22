"""Resolve combat proficiency defaults and overrides from entity class features."""

from __future__ import annotations

from typing import Any

from tools.repositories import ClassProficiencyDefinitionRepository
from tools.services.class_features.shared.runtime import get_monk_runtime
from tools.services.class_features.rogue import ensure_rogue_runtime
from tools.services.class_features.shared.runtime import ensure_ranger_runtime

_WEAPON_ORDER = ["simple", "martial", "martial_light", "martial_finesse_or_light"]
_ARMOR_ORDER = ["light", "medium", "heavy", "shield"]
_SAVE_ORDER = ["str", "dex", "con", "int", "wis", "cha"]
_CLASS_PROFICIENCY_REPOSITORY = ClassProficiencyDefinitionRepository()
_SKILL_TRAINING_VALUES = {"none", "proficient", "expertise"}


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
    class_features = _extract_class_features(entity)
    resolved: set[str] = set()
    initial_class_name = _resolve_initial_class_name(entity, class_features)
    if initial_class_name is not None:
        template = _CLASS_PROFICIENCY_REPOSITORY.get(initial_class_name)
        if isinstance(template, dict):
            _merge_string_list(resolved, template.get("save_proficiencies"))

    for runtime_bucket in class_features.values():
        if isinstance(runtime_bucket, dict):
            _merge_string_list(resolved, runtime_bucket.get("save_proficiencies"))

    _merge_string_list(resolved, _extract_save_proficiencies(entity))
    rogue_runtime = ensure_rogue_runtime(entity)
    slippery_mind = rogue_runtime.get("slippery_mind")
    if isinstance(slippery_mind, dict) and slippery_mind.get("enabled"):
        resolved.update({"wis", "cha"})
    monk_runtime = get_monk_runtime(entity)
    disciplined_survivor = monk_runtime.get("disciplined_survivor")
    if isinstance(disciplined_survivor, dict) and disciplined_survivor.get("enabled"):
        resolved.update(_SAVE_ORDER)
    return _ordered(resolved, _SAVE_ORDER)


def resolve_entity_skill_proficiencies(entity: Any) -> list[str]:
    skill_training = resolve_entity_skill_training(entity)
    return sorted(
        skill
        for skill, training in skill_training.items()
        if training in {"proficient", "expertise"}
    )


def resolve_entity_skill_training(entity: Any) -> dict[str, str]:
    if isinstance(entity, dict):
        skill_training = entity.get("skill_training")
    else:
        skill_training = getattr(entity, "skill_training", None)

    if not isinstance(skill_training, dict):
        return {}

    normalized: dict[str, str] = {}
    for raw_skill, raw_training in skill_training.items():
        if not isinstance(raw_skill, str) or not raw_skill.strip():
            continue
        if not isinstance(raw_training, str):
            continue
        skill = raw_skill.strip().lower()
        training = raw_training.strip().lower()
        if training in _SKILL_TRAINING_VALUES:
            normalized[skill] = training
    return normalized


def has_skill_proficiency(entity: Any, skill: str) -> bool:
    normalized_skill = str(skill).strip().lower()
    return resolve_entity_skill_training(entity).get(normalized_skill) in {"proficient", "expertise"}


def has_skill_expertise(entity: Any, skill: str) -> bool:
    normalized_skill = str(skill).strip().lower()
    return resolve_entity_skill_training(entity).get(normalized_skill) == "expertise"


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


def _resolve_initial_class_name(entity: Any, class_features: dict[str, Any]) -> str | None:
    if isinstance(entity, dict):
        explicit = entity.get("initial_class_name")
    else:
        explicit = getattr(entity, "initial_class_name", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip().lower()

    source_ref = _extract_source_ref(entity)
    for key in ("initial_class_name", "initial_class", "starting_class", "base_class", "class_name"):
        value = source_ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()

    class_ids = [
        class_id.strip().lower()
        for class_id, runtime_bucket in class_features.items()
        if isinstance(class_id, str) and class_id.strip() and isinstance(runtime_bucket, dict)
    ]
    unique_ids = sorted(set(class_ids))
    if len(unique_ids) == 1:
        return unique_ids[0]
    return None


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
