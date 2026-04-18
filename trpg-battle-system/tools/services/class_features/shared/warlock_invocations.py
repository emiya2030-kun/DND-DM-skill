from __future__ import annotations

from typing import Any

from tools.services.class_features.shared.runtime import ensure_warlock_runtime


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
