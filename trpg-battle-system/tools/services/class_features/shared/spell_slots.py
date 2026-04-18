from __future__ import annotations

from typing import Any

from tools.services.class_features.shared.runtime import ensure_sorcerer_runtime

MULTICLASS_SPELL_SLOTS: dict[int, dict[str, int]] = {
    1: {"1": 2},
    2: {"1": 3},
    3: {"1": 4, "2": 2},
    4: {"1": 4, "2": 3},
    5: {"1": 4, "2": 3, "3": 2},
    6: {"1": 4, "2": 3, "3": 3},
    7: {"1": 4, "2": 3, "3": 3, "4": 1},
    8: {"1": 4, "2": 3, "3": 3, "4": 2},
    9: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    10: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    11: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    12: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    13: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    14: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    15: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    16: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    17: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1, "9": 1},
    18: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 1, "7": 1, "8": 1, "9": 1},
    19: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 1, "8": 1, "9": 1},
    20: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 3, "6": 2, "7": 2, "8": 1, "9": 1},
}

FULL_CASTER_CLASSES = {"bard", "cleric", "druid", "sorcerer", "wizard"}
HALF_CASTER_CLASSES = {"paladin", "ranger"}
THIRD_CASTER_SUBCLASSES = {
    "fighter": {"eldritch_knight"},
    "rogue": {"arcane_trickster"},
}
WARLOCK_PACT_MAGIC: dict[int, dict[str, int]] = {
    1: {"slot_level": 1, "max": 1},
    2: {"slot_level": 1, "max": 2},
    3: {"slot_level": 2, "max": 2},
    4: {"slot_level": 2, "max": 2},
    5: {"slot_level": 3, "max": 2},
    6: {"slot_level": 3, "max": 2},
    7: {"slot_level": 4, "max": 2},
    8: {"slot_level": 4, "max": 2},
    9: {"slot_level": 5, "max": 2},
    10: {"slot_level": 5, "max": 2},
    11: {"slot_level": 5, "max": 3},
    12: {"slot_level": 5, "max": 3},
    13: {"slot_level": 5, "max": 3},
    14: {"slot_level": 5, "max": 3},
    15: {"slot_level": 5, "max": 3},
    16: {"slot_level": 5, "max": 3},
    17: {"slot_level": 5, "max": 4},
    18: {"slot_level": 5, "max": 4},
    19: {"slot_level": 5, "max": 4},
    20: {"slot_level": 5, "max": 4},
}


def ensure_spell_slots_runtime(entity: Any) -> dict[str, Any]:
    class_features = getattr(entity, "class_features", None)
    if not isinstance(class_features, dict):
        return {
            "multiclass_caster_level": 0,
            "spell_slots": _read_existing_spell_slots(entity),
            "pact_magic_slots": _read_existing_pact_magic_slots(entity),
        }

    multiclass_caster_level = _resolve_multiclass_caster_level(class_features)
    warlock_level = _resolve_class_level(class_features.get("warlock"))
    derived_slots = MULTICLASS_SPELL_SLOTS.get(multiclass_caster_level, {})
    derived_pact_magic = WARLOCK_PACT_MAGIC.get(warlock_level)
    if not _has_slot_progression_features(class_features):
        return {
            "multiclass_caster_level": multiclass_caster_level,
            "spell_slots": _read_existing_spell_slots(entity),
            "pact_magic_slots": _read_existing_pact_magic_slots(entity),
        }

    resources = getattr(entity, "resources", None)
    if not isinstance(resources, dict):
        resources = {}
        setattr(entity, "resources", resources)

    existing_spell_slots = _read_existing_spell_slots(entity)
    existing_pact_magic_slots = _read_existing_pact_magic_slots(entity)
    normalized_spell_slots: dict[str, dict[str, int]] = {}
    for level_key, max_uses in derived_slots.items():
        existing_slot = existing_spell_slots.get(level_key)
        remaining = existing_slot.get("remaining") if isinstance(existing_slot, dict) else None
        normalized_spell_slots[level_key] = {
            "max": max_uses,
            "remaining": remaining if isinstance(remaining, int) else max_uses,
        }
    normalized_pact_magic_slots: dict[str, int] = {}
    if isinstance(derived_pact_magic, dict):
        remaining = existing_pact_magic_slots.get("remaining")
        maximum = derived_pact_magic["max"]
        normalized_pact_magic_slots = {
            "slot_level": derived_pact_magic["slot_level"],
            "max": maximum,
            "remaining": remaining if isinstance(remaining, int) else maximum,
        }
    resources["spell_slots"] = normalized_spell_slots
    resources["pact_magic_slots"] = normalized_pact_magic_slots
    return {
        "multiclass_caster_level": multiclass_caster_level,
        "spell_slots": normalized_spell_slots,
        "pact_magic_slots": normalized_pact_magic_slots,
    }


def _read_existing_spell_slots(entity: Any) -> dict[str, dict[str, int]]:
    resources = getattr(entity, "resources", None)
    if not isinstance(resources, dict):
        return {}
    spell_slots = resources.get("spell_slots")
    if not isinstance(spell_slots, dict):
        return {}
    normalized: dict[str, dict[str, int]] = {}
    for level_key, slot_info in spell_slots.items():
        if not isinstance(slot_info, dict):
            continue
        maximum = slot_info.get("max")
        remaining = slot_info.get("remaining")
        if not isinstance(maximum, int) or not isinstance(remaining, int):
            continue
        normalized[str(level_key)] = {"max": maximum, "remaining": remaining}
    return normalized


def _read_existing_pact_magic_slots(entity: Any) -> dict[str, int]:
    resources = getattr(entity, "resources", None)
    if not isinstance(resources, dict):
        return {}
    pact_magic_slots = resources.get("pact_magic_slots")
    if not isinstance(pact_magic_slots, dict):
        return {}
    slot_level = pact_magic_slots.get("slot_level")
    maximum = pact_magic_slots.get("max")
    remaining = pact_magic_slots.get("remaining")
    if not isinstance(slot_level, int) or slot_level < 1:
        return {}
    if not isinstance(maximum, int) or not isinstance(remaining, int):
        return {}
    return {
        "slot_level": slot_level,
        "max": maximum,
        "remaining": remaining,
    }


def build_available_spell_slots_view(entity: Any) -> dict[str, int]:
    ensure_spell_slots_runtime(entity)
    combined: dict[str, int] = {}
    for level_key, slot_info in _read_existing_spell_slots(entity).items():
        combined[level_key] = int(slot_info.get("remaining", 0))
    pact_magic_slots = _read_existing_pact_magic_slots(entity)
    if pact_magic_slots:
        level_key = str(pact_magic_slots["slot_level"])
        combined[level_key] = combined.get(level_key, 0) + int(pact_magic_slots.get("remaining", 0))
    return combined


def has_exact_spell_slot(entity: Any, slot_level: int) -> bool:
    ensure_spell_slots_runtime(entity)
    slot_key = str(slot_level)
    shared_slot = _read_existing_spell_slots(entity).get(slot_key)
    if isinstance(shared_slot, dict):
        remaining = shared_slot.get("remaining")
        if isinstance(remaining, int) and remaining > 0:
            return True
    pact_magic_slots = _read_existing_pact_magic_slots(entity)
    if pact_magic_slots.get("slot_level") == slot_level and int(pact_magic_slots.get("remaining", 0)) > 0:
        return True
    return False


def has_any_spell_slot(entity: Any, *, minimum_level: int) -> bool:
    ensure_spell_slots_runtime(entity)
    for level_key, slot in _read_existing_spell_slots(entity).items():
        remaining = slot.get("remaining")
        if not isinstance(remaining, int) or remaining <= 0:
            continue
        if int(level_key) >= minimum_level:
            return True
    pact_magic_slots = _read_existing_pact_magic_slots(entity)
    if (
        isinstance(pact_magic_slots.get("slot_level"), int)
        and pact_magic_slots["slot_level"] >= minimum_level
        and int(pact_magic_slots.get("remaining", 0)) > 0
    ):
        return True
    return False


def consume_exact_spell_slot(entity: Any, slot_level: int) -> dict[str, Any]:
    ensure_spell_slots_runtime(entity)
    resources = getattr(entity, "resources", {})
    spell_slots = resources.get("spell_slots") if isinstance(resources, dict) else None
    if isinstance(spell_slots, dict):
        slot_key = str(slot_level)
        slot_info = spell_slots.get(slot_key)
        if isinstance(slot_info, dict):
            remaining = slot_info.get("remaining")
            if isinstance(remaining, int) and remaining > 0:
                slot_info["remaining"] = remaining - 1
                return {
                    "slot_level": slot_level,
                    "resource_pool": "spell_slots",
                    "remaining_before": remaining,
                    "remaining_after": slot_info["remaining"],
                }

    pact_magic_slots = resources.get("pact_magic_slots") if isinstance(resources, dict) else None
    if isinstance(pact_magic_slots, dict):
        pact_slot_level = pact_magic_slots.get("slot_level")
        remaining = pact_magic_slots.get("remaining")
        if pact_slot_level == slot_level and isinstance(remaining, int) and remaining > 0:
            pact_magic_slots["remaining"] = remaining - 1
            return {
                "slot_level": slot_level,
                "resource_pool": "pact_magic_slots",
                "remaining_before": remaining,
                "remaining_after": pact_magic_slots["remaining"],
            }
    raise ValueError(f"spell slot level '{slot_level}' is not available")


def consume_lowest_available_spell_slot(entity: Any, *, minimum_level: int) -> dict[str, Any]:
    ensure_spell_slots_runtime(entity)
    resources = getattr(entity, "resources", {})
    candidates: list[tuple[int, int, str]] = []

    spell_slots = resources.get("spell_slots") if isinstance(resources, dict) else None
    if isinstance(spell_slots, dict):
        for raw_level, slot_info in spell_slots.items():
            if not isinstance(slot_info, dict):
                continue
            remaining = slot_info.get("remaining")
            if not isinstance(remaining, int) or remaining <= 0:
                continue
            level = int(raw_level)
            if level >= minimum_level:
                candidates.append((level, 0, "spell_slots"))

    pact_magic_slots = resources.get("pact_magic_slots") if isinstance(resources, dict) else None
    if isinstance(pact_magic_slots, dict):
        level = pact_magic_slots.get("slot_level")
        remaining = pact_magic_slots.get("remaining")
        if isinstance(level, int) and level >= minimum_level and isinstance(remaining, int) and remaining > 0:
            candidates.append((level, 1, "pact_magic_slots"))

    if not candidates:
        raise ValueError(f"spell slot level '{minimum_level}' is not available")

    slot_level, _, resource_pool = sorted(candidates)[0]
    if resource_pool == "spell_slots":
        return consume_exact_spell_slot(entity, slot_level)

    before = int(pact_magic_slots["remaining"])
    pact_magic_slots["remaining"] = before - 1
    return {
        "slot_level": slot_level,
        "resource_pool": "pact_magic_slots",
        "remaining_before": before,
        "remaining_after": pact_magic_slots["remaining"],
    }


def restore_consumed_spell_slot(entity: Any, slot_consumed: dict[str, Any] | None) -> None:
    if slot_consumed is None:
        return
    resources = getattr(entity, "resources", {})
    if not isinstance(resources, dict):
        return
    remaining_before = slot_consumed.get("remaining_before")
    if not isinstance(remaining_before, int):
        return
    resource_pool = slot_consumed.get("resource_pool")
    if resource_pool == "spell_slots":
        spell_slots = resources.get("spell_slots")
        slot_key = str(slot_consumed.get("slot_level"))
        if isinstance(spell_slots, dict):
            slot_info = spell_slots.get(slot_key)
            if isinstance(slot_info, dict):
                slot_info["remaining"] = remaining_before
        return
    if resource_pool == "pact_magic_slots":
        pact_magic_slots = resources.get("pact_magic_slots")
        if isinstance(pact_magic_slots, dict):
            pact_magic_slots["remaining"] = remaining_before


def add_created_spell_slot(entity: Any, *, slot_level: int, amount: int = 1) -> dict[str, Any]:
    if slot_level < 1 or amount < 1:
        raise ValueError("created_spell_slot_invalid")
    ensure_spell_slots_runtime(entity)
    sorcerer = ensure_sorcerer_runtime(entity)
    resources = getattr(entity, "resources", {})
    if not isinstance(resources, dict):
        resources = {}
        setattr(entity, "resources", resources)
    spell_slots = resources.setdefault("spell_slots", {})
    slot_key = str(slot_level)
    slot_info = spell_slots.setdefault(slot_key, {"max": 0, "remaining": 0})
    if not isinstance(slot_info, dict):
        slot_info = {"max": 0, "remaining": 0}
        spell_slots[slot_key] = slot_info

    remaining_before = int(slot_info.get("remaining", 0) or 0)
    slot_info["remaining"] = remaining_before + amount

    created_spell_slots = sorcerer.setdefault("created_spell_slots", {})
    created_spell_slots[slot_key] = int(created_spell_slots.get(slot_key, 0) or 0) + amount
    return {
        "slot_level": slot_level,
        "remaining_before": remaining_before,
        "remaining_after": slot_info["remaining"],
        "created_amount": created_spell_slots[slot_key],
    }


def clear_created_spell_slots(entity: Any) -> dict[str, int]:
    ensure_spell_slots_runtime(entity)
    sorcerer = ensure_sorcerer_runtime(entity)
    created_spell_slots = sorcerer.get("created_spell_slots")
    resources = getattr(entity, "resources", {})
    spell_slots = resources.get("spell_slots") if isinstance(resources, dict) else None
    if not isinstance(created_spell_slots, dict) or not isinstance(spell_slots, dict):
        return {}

    cleared: dict[str, int] = {}
    for slot_key, created_amount in list(created_spell_slots.items()):
        if not isinstance(created_amount, int) or created_amount <= 0:
            created_spell_slots[str(slot_key)] = 0
            continue
        slot_info = spell_slots.get(str(slot_key))
        if isinstance(slot_info, dict):
            remaining = int(slot_info.get("remaining", 0) or 0)
            slot_info["remaining"] = max(0, remaining - created_amount)
        created_spell_slots[str(slot_key)] = 0
        cleared[str(slot_key)] = created_amount
    return cleared


def _has_slot_progression_features(class_features: dict[str, Any]) -> bool:
    if _resolve_class_level(class_features.get("warlock")) > 0:
        return True
    for class_id in FULL_CASTER_CLASSES | HALF_CASTER_CLASSES:
        if _resolve_class_level(class_features.get(class_id)) > 0:
            return True
    for class_id, subclass_ids in THIRD_CASTER_SUBCLASSES.items():
        bucket = class_features.get(class_id)
        if _resolve_class_level(bucket) > 0 and _is_matching_subclass(bucket, subclass_ids):
            return True
    return False


def _resolve_multiclass_caster_level(class_features: dict[str, Any]) -> int:
    total = 0
    for class_id in FULL_CASTER_CLASSES:
        total += _resolve_class_level(class_features.get(class_id))
    for class_id in HALF_CASTER_CLASSES:
        level = _resolve_class_level(class_features.get(class_id))
        total += (level + 1) // 2
    for class_id, subclass_ids in THIRD_CASTER_SUBCLASSES.items():
        bucket = class_features.get(class_id)
        level = _resolve_class_level(bucket)
        if level <= 0 or not _is_matching_subclass(bucket, subclass_ids):
            continue
        total += level // 3
    return total


def _resolve_class_level(bucket: Any) -> int:
    if not isinstance(bucket, dict):
        return 0
    level = bucket.get("level")
    if isinstance(level, bool) or not isinstance(level, int) or level < 0:
        return 0
    return level


def _is_matching_subclass(bucket: Any, expected_ids: set[str]) -> bool:
    if not isinstance(bucket, dict):
        return False
    for key in ("subclass_id", "subclass", "subclass_name", "archetype"):
        value = bucket.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = value.strip().lower().replace(" ", "_")
        if normalized in expected_ids:
            return True
    return False
