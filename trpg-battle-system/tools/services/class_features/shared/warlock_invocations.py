from __future__ import annotations

from typing import Any

from tools.services.class_features.shared.runtime import ensure_warlock_runtime

_SIZE_TO_FOOTPRINT = {
    "tiny": (1, 1),
    "small": (1, 1),
    "medium": (1, 1),
    "large": (2, 2),
    "huge": (3, 3),
    "gargantuan": (4, 4),
}


def get_selected_warlock_invocations(entity_or_class_features: Any) -> list[dict[str, Any]]:
    warlock = ensure_warlock_runtime(entity_or_class_features)
    invocations = warlock.get("eldritch_invocations")
    if not isinstance(invocations, dict):
        return []
    selected = invocations.get("selected")
    if not isinstance(selected, list):
        return []
    return [entry for entry in selected if isinstance(entry, dict)]


def find_selected_warlock_invocation(
    entity_or_class_features: Any,
    invocation_id: str,
    *,
    spell_id: str | None = None,
) -> dict[str, Any] | None:
    normalized_invocation_id = str(invocation_id or "").strip().lower()
    normalized_spell_id = str(spell_id or "").strip().lower() or None
    if not normalized_invocation_id:
        return None

    for entry in get_selected_warlock_invocations(entity_or_class_features):
        current_invocation_id = str(entry.get("invocation_id") or entry.get("id") or "").strip().lower()
        if current_invocation_id != normalized_invocation_id:
            continue
        current_spell_id = str(entry.get("spell_id") or "").strip().lower() or None
        if normalized_spell_id is not None and current_spell_id != normalized_spell_id:
            continue
        return entry
    return None


def has_selected_warlock_invocation(
    entity_or_class_features: Any,
    invocation_id: str,
    *,
    spell_id: str | None = None,
) -> bool:
    return find_selected_warlock_invocation(
        entity_or_class_features,
        invocation_id,
        spell_id=spell_id,
    ) is not None


def get_warlock_pact_of_the_blade_state(entity_or_class_features: Any) -> dict[str, Any]:
    warlock = ensure_warlock_runtime(entity_or_class_features)
    pact = warlock.get("pact_of_the_blade")
    if not isinstance(pact, dict):
        return {}
    return pact


def is_bound_pact_weapon(entity_or_class_features: Any, weapon_id: str) -> bool:
    normalized_weapon_id = str(weapon_id or "").strip().lower()
    if not normalized_weapon_id:
        return False
    pact = get_warlock_pact_of_the_blade_state(entity_or_class_features)
    if not bool(pact.get("enabled")):
        return False
    bound_weapon_id = str(pact.get("bound_weapon_id") or "").strip().lower()
    return bool(bound_weapon_id) and bound_weapon_id == normalized_weapon_id


def get_bound_pact_weapon_damage_type_override(entity_or_class_features: Any, weapon_id: str) -> str | None:
    if not is_bound_pact_weapon(entity_or_class_features, weapon_id):
        return None
    pact = get_warlock_pact_of_the_blade_state(entity_or_class_features)
    damage_type = pact.get("damage_type_override")
    if isinstance(damage_type, str) and damage_type.strip():
        return damage_type.strip().lower()
    return None


def uses_charisma_for_pact_weapon(entity_or_class_features: Any, weapon_id: str) -> bool:
    return is_bound_pact_weapon(entity_or_class_features, weapon_id)


def resolve_pact_weapon_attack_count(entity_or_class_features: Any, weapon_id: str) -> int:
    if not is_bound_pact_weapon(entity_or_class_features, weapon_id):
        return 1
    warlock = ensure_warlock_runtime(entity_or_class_features)
    level = int(warlock.get("level", 0) or 0)
    if level >= 12 and has_selected_warlock_invocation(entity_or_class_features, "devouring_blade"):
        return 3
    if level >= 5 and has_selected_warlock_invocation(entity_or_class_features, "thirsting_blade"):
        return 2
    return 1


def can_apply_lifedrinker(entity_or_class_features: Any, weapon_id: str) -> bool:
    warlock = ensure_warlock_runtime(entity_or_class_features)
    lifedrinker = warlock.get("lifedrinker")
    if not isinstance(lifedrinker, dict) or not bool(lifedrinker.get("enabled")):
        return False
    return is_bound_pact_weapon(entity_or_class_features, weapon_id)


def can_apply_eldritch_smite(entity_or_class_features: Any, weapon_id: str) -> bool:
    warlock = ensure_warlock_runtime(entity_or_class_features)
    eldritch_smite = warlock.get("eldritch_smite")
    if not isinstance(eldritch_smite, dict) or not bool(eldritch_smite.get("enabled")):
        return False
    return is_bound_pact_weapon(entity_or_class_features, weapon_id)


def get_gaze_of_two_minds_state(entity_or_class_features: Any) -> dict[str, Any]:
    warlock = ensure_warlock_runtime(entity_or_class_features)
    gaze = warlock.get("gaze_of_two_minds")
    if not isinstance(gaze, dict):
        return {}
    return gaze


def can_use_gaze_of_two_minds(entity_or_class_features: Any) -> bool:
    gaze = get_gaze_of_two_minds_state(entity_or_class_features)
    return bool(gaze.get("enabled"))


def resolve_gaze_of_two_minds_origin(
    encounter: Any,
    actor: Any,
) -> dict[str, Any]:
    gaze = get_gaze_of_two_minds_state(actor)
    if not isinstance(gaze, dict) or not bool(gaze.get("enabled")):
        return {
            "origin_entity": actor,
            "origin_entity_id": getattr(actor, "entity_id", None),
            "via_link": False,
            "can_cast_via_link": False,
        }

    linked_entity_id = gaze.get("linked_entity_id")
    if not isinstance(linked_entity_id, str) or not linked_entity_id:
        return {
            "origin_entity": actor,
            "origin_entity_id": getattr(actor, "entity_id", None),
            "via_link": False,
            "can_cast_via_link": False,
        }

    linked_entity = encounter.entities.get(linked_entity_id) if hasattr(encounter, "entities") else None
    if linked_entity is None:
        return {
            "origin_entity": actor,
            "origin_entity_id": getattr(actor, "entity_id", None),
            "linked_entity_id": linked_entity_id,
            "via_link": False,
            "can_cast_via_link": False,
            "reason": "linked_entity_missing",
        }

    distance_feet = _distance_feet(actor, linked_entity, encounter)
    can_cast_via_link = distance_feet <= 60
    origin_entity = linked_entity if can_cast_via_link else actor
    return {
        "origin_entity": origin_entity,
        "origin_entity_id": getattr(origin_entity, "entity_id", None),
        "linked_entity_id": linked_entity_id,
        "linked_entity_name": getattr(linked_entity, "name", None),
        "via_link": can_cast_via_link,
        "can_cast_via_link": can_cast_via_link,
        "distance_to_link_feet": distance_feet,
    }


def _distance_feet(source: Any, target: Any, encounter: Any) -> int:
    source_center = _get_center_position(source)
    target_center = _get_center_position(target)
    dx = abs(source_center["x"] - target_center["x"])
    dy = abs(source_center["y"] - target_center["y"])
    grid_size = getattr(getattr(encounter, "map", None), "grid_size_feet", 5)
    return max(dx, dy) * grid_size


def _get_center_position(entity: Any) -> dict[str, float]:
    position = getattr(entity, "position", None)
    if not isinstance(position, dict):
        return {"x": 0.0, "y": 0.0}
    size = str(getattr(entity, "size", "medium") or "medium").strip().lower()
    width, height = _SIZE_TO_FOOTPRINT.get(size, (1, 1))
    return {
        "x": float(position.get("x", 0)) + (width - 1) / 2,
        "y": float(position.get("y", 0)) + (height - 1) / 2,
    }
