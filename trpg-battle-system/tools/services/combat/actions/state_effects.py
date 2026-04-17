from __future__ import annotations

from typing import Any


def _ensure_turn_effects(entity: Any) -> list[dict[str, Any]]:
    turn_effects = getattr(entity, "turn_effects", None)
    if not isinstance(turn_effects, list):
        entity.turn_effects = []
    return entity.turn_effects


def clear_turn_effect_type(entity: Any, effect_type: str) -> None:
    turn_effects = _ensure_turn_effects(entity)
    entity.turn_effects = [
        effect
        for effect in turn_effects
        if not (isinstance(effect, dict) and effect.get("effect_type") == effect_type)
    ]


def add_or_replace_turn_effect(entity: Any, effect: dict[str, Any]) -> None:
    effect_type = str(effect.get("effect_type") or "").strip()
    if not effect_type:
        raise ValueError("turn_effect.effect_type is required")
    clear_turn_effect_type(entity, effect_type)
    _ensure_turn_effects(entity).append(effect)


def has_disengage_effect(entity: Any) -> bool:
    return any(
        isinstance(effect, dict) and effect.get("effect_type") == "disengage"
        for effect in _ensure_turn_effects(entity)
    )


def has_dodge_effect(entity: Any) -> bool:
    return any(
        isinstance(effect, dict) and effect.get("effect_type") == "dodge"
        for effect in _ensure_turn_effects(entity)
    )
