from __future__ import annotations

from typing import Any

KNOWN_CLASS_IDS = {
    "barbarian",
    "bard",
    "cleric",
    "druid",
    "fighter",
    "monk",
    "paladin",
    "ranger",
    "rogue",
    "sorcerer",
    "warlock",
    "wizard",
}

SPELL_PREPARATION_MODES = {
    "bard": "level_up_one",
    "cleric": "long_rest_any",
    "druid": "long_rest_any",
    "paladin": "long_rest_one",
    "ranger": "long_rest_one",
    "sorcerer": "level_up_one",
    "warlock": "level_up_one",
    "wizard": "long_rest_any",
}


def normalize_class_name(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().lower()
    if normalized not in KNOWN_CLASS_IDS:
        return None
    return normalized


def collect_always_prepared_spells(value: Any) -> list[str]:
    collected: list[str] = []
    _collect_always_prepared_spells_recursive(value, collected)
    return _unique_spell_ids(collected)


def normalize_entity_spellcasting_schema(
    *,
    source_ref: dict[str, Any] | None,
    initial_class_name: str | None,
    class_features: dict[str, Any] | None,
    spells: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized_source_ref = source_ref if isinstance(source_ref, dict) else {}
    normalized_class_features = _normalize_class_features_dict(class_features)
    primary_class_name = _resolve_primary_class_name(
        source_ref=normalized_source_ref,
        initial_class_name=initial_class_name,
        class_features=normalized_class_features,
    )
    source_level = _resolve_source_level(normalized_source_ref)
    normalized_spells = _normalize_spell_entries(spells, primary_class_name=primary_class_name)

    if primary_class_name in SPELL_PREPARATION_MODES:
        bucket = normalized_class_features.setdefault(primary_class_name, {})
        if source_level > 0 and not isinstance(bucket.get("level"), int):
            bucket["level"] = source_level

    for class_id, bucket in list(normalized_class_features.items()):
        if not isinstance(bucket, dict):
            continue
        normalized_class_features[class_id] = _normalize_spellcasting_bucket(
            class_id=class_id,
            bucket=bucket,
            spells=normalized_spells,
        )

    return normalized_class_features, normalized_spells


def _normalize_class_features_dict(class_features: dict[str, Any] | None) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if not isinstance(class_features, dict):
        return normalized
    for raw_key, raw_value in class_features.items():
        if not isinstance(raw_value, dict):
            continue
        normalized_key = normalize_class_name(raw_key) or str(raw_key)
        existing = normalized.get(normalized_key)
        if isinstance(existing, dict):
            merged = dict(existing)
            merged.update(raw_value)
            normalized[normalized_key] = merged
            continue
        normalized[normalized_key] = dict(raw_value)
    return normalized


def _resolve_primary_class_name(
    *,
    source_ref: dict[str, Any],
    initial_class_name: str | None,
    class_features: dict[str, Any],
) -> str | None:
    for candidate in (
        normalize_class_name(source_ref.get("class_name")),
        normalize_class_name(initial_class_name),
    ):
        if candidate is not None:
            return candidate
    recognized = [key for key in class_features.keys() if key in KNOWN_CLASS_IDS]
    if len(recognized) == 1:
        return recognized[0]
    return None


def _resolve_source_level(source_ref: dict[str, Any]) -> int:
    for key in ("level", "caster_level"):
        value = source_ref.get(key)
        if isinstance(value, int) and value > 0:
            return value
    return 0


def _normalize_spell_entries(
    spells: list[dict[str, Any]] | None,
    *,
    primary_class_name: str | None,
) -> list[dict[str, Any]]:
    normalized_spells: list[dict[str, Any]] = []
    if not isinstance(spells, list):
        return normalized_spells
    for raw_spell in spells:
        if not isinstance(raw_spell, dict):
            continue
        normalized_spell = dict(raw_spell)
        if primary_class_name is not None:
            has_explicit_class = any(
                isinstance(normalized_spell.get(key), str) and str(normalized_spell.get(key)).strip()
                for key in ("casting_class", "source_class")
            )
            if not has_explicit_class:
                classes = normalized_spell.get("classes")
                if not isinstance(classes, list) or not classes:
                    normalized_spell["casting_class"] = primary_class_name
        normalized_spells.append(normalized_spell)
    return normalized_spells


def _normalize_spellcasting_bucket(
    *,
    class_id: str,
    bucket: dict[str, Any],
    spells: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_bucket = dict(bucket)
    if class_id not in SPELL_PREPARATION_MODES:
        return normalized_bucket

    explicit_mode = normalized_bucket.get("spell_preparation_mode")
    if isinstance(explicit_mode, str) and explicit_mode.strip():
        normalized_bucket["spell_preparation_mode"] = explicit_mode.strip().lower()
    else:
        normalized_bucket["spell_preparation_mode"] = SPELL_PREPARATION_MODES[class_id]

    normalized_bucket["always_prepared_spells"] = collect_always_prepared_spells(normalized_bucket)

    prepared_spells = normalized_bucket.get("prepared_spells")
    if isinstance(prepared_spells, list):
        normalized_bucket["prepared_spells"] = _unique_spell_ids(prepared_spells)
    else:
        normalized_bucket["prepared_spells"] = _infer_prepared_spells_from_known_spells(spells=spells, class_id=class_id)
    return normalized_bucket


def _infer_prepared_spells_from_known_spells(*, spells: list[dict[str, Any]], class_id: str) -> list[str]:
    prepared: list[str] = []
    for spell in spells:
        if not isinstance(spell, dict):
            continue
        spell_id = spell.get("spell_id")
        if not isinstance(spell_id, str) or not spell_id.strip():
            continue
        level = spell.get("level")
        if not isinstance(level, int) or level <= 0:
            continue
        casting_class = normalize_class_name(spell.get("casting_class"))
        if casting_class is None:
            casting_class = normalize_class_name(spell.get("source_class"))
        if casting_class is None:
            classes = spell.get("classes")
            if isinstance(classes, list) and len(classes) == 1:
                casting_class = normalize_class_name(classes[0])
        if casting_class != class_id:
            continue
        prepared.append(spell_id.strip())
    return _unique_spell_ids(prepared)


def _collect_always_prepared_spells_recursive(value: Any, collected: list[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "always_prepared_spells" and isinstance(nested, list):
                collected.extend(_unique_spell_ids(nested))
                continue
            _collect_always_prepared_spells_recursive(nested, collected)
        return
    if isinstance(value, list):
        for nested in value:
            _collect_always_prepared_spells_recursive(nested, collected)


def _unique_spell_ids(items: list[Any]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str) or not item.strip():
            continue
        spell_id = item.strip()
        if spell_id in seen:
            continue
        seen.add(spell_id)
        normalized.append(spell_id)
    return normalized
