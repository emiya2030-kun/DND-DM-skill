from __future__ import annotations

from typing import Any

from tools.services.class_features.shared.runtime import ensure_warlock_runtime


def get_selected_invocations(entity_or_class_features: Any) -> list[dict[str, Any]]:
    warlock = ensure_warlock_runtime(entity_or_class_features)
    invocations = warlock.get("eldritch_invocations")
    if not isinstance(invocations, dict):
        return []
    selected = invocations.get("selected")
    if not isinstance(selected, list):
        return []
    return [entry for entry in selected if isinstance(entry, dict)]


def find_selected_invocation(
    entity_or_class_features: Any,
    invocation_id: str,
    *,
    spell_id: str | None = None,
) -> dict[str, Any] | None:
    normalized_invocation_id = str(invocation_id or "").strip().lower()
    normalized_spell_id = str(spell_id or "").strip().lower() or None
    if not normalized_invocation_id:
        return None

    for entry in get_selected_invocations(entity_or_class_features):
        current_invocation_id = str(entry.get("invocation_id") or entry.get("id") or "").strip().lower()
        if current_invocation_id != normalized_invocation_id:
            continue
        current_spell_id = str(entry.get("spell_id") or "").strip().lower() or None
        if normalized_spell_id is not None and current_spell_id != normalized_spell_id:
            continue
        return entry
    return None


def has_selected_invocation(
    entity_or_class_features: Any,
    invocation_id: str,
    *,
    spell_id: str | None = None,
) -> bool:
    return find_selected_invocation(
        entity_or_class_features,
        invocation_id,
        spell_id=spell_id,
    ) is not None
