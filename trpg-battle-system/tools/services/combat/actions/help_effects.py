from __future__ import annotations

from typing import Any


def _ensure_turn_effects(entity: Any) -> list[dict[str, Any]]:
    turn_effects = getattr(entity, "turn_effects", None)
    if not isinstance(turn_effects, list):
        entity.turn_effects = []
    return entity.turn_effects


def remove_turn_effect_by_id(entity: Any, effect_id: str) -> None:
    entity.turn_effects = [
        effect
        for effect in _ensure_turn_effects(entity)
        if not (isinstance(effect, dict) and effect.get("effect_id") == effect_id)
    ]


def find_help_attack_effect(*, target: Any, attacker: Any) -> dict[str, Any] | None:
    for effect in _ensure_turn_effects(target):
        if not isinstance(effect, dict):
            continue
        if effect.get("effect_type") != "help_attack":
            continue
        if int(effect.get("remaining_uses", 0) or 0) <= 0:
            continue
        if effect.get("source_side") != getattr(attacker, "side", None):
            continue
        return effect
    return None


def find_help_ability_check_effect(*, actor: Any, check_type: str, check_key: str) -> dict[str, Any] | None:
    normalized_check_type = str(check_type or "").strip().lower()
    normalized_check_key = str(check_key or "").strip().lower()
    for effect in _ensure_turn_effects(actor):
        if not isinstance(effect, dict):
            continue
        if effect.get("effect_type") != "help_ability_check":
            continue
        if int(effect.get("remaining_uses", 0) or 0) <= 0:
            continue
        help_check = effect.get("help_check") or {}
        if str(help_check.get("check_type") or "").strip().lower() != normalized_check_type:
            continue
        if str(help_check.get("check_key") or "").strip().lower() != normalized_check_key:
            continue
        return effect
    return None
