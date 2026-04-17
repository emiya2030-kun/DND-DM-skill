from __future__ import annotations

from typing import Any


def fighter_has_studied_attacks(class_features: dict[str, Any]) -> bool:
    fighter = class_features.get("fighter")
    if not isinstance(fighter, dict):
        return False
    level = fighter.get("fighter_level", fighter.get("level", 0))
    if isinstance(level, bool) or not isinstance(level, int):
        return False
    return level >= 13


def add_or_refresh_studied_attack_mark(
    class_features: dict[str, Any],
    target_entity_id: str,
) -> dict[str, Any]:
    fighter = class_features.get("fighter")
    if not isinstance(fighter, dict):
        fighter = {}
        class_features["fighter"] = fighter

    marks = fighter.get("studied_attacks")
    if not isinstance(marks, list):
        marks = []
        fighter["studied_attacks"] = marks

    for mark in marks:
        if not isinstance(mark, dict):
            continue
        if mark.get("target_entity_id") != target_entity_id:
            continue
        mark["expires_at"] = "end_of_next_turn"
        mark["consumed"] = False
        return mark

    new_mark = {
        "target_entity_id": target_entity_id,
        "expires_at": "end_of_next_turn",
        "consumed": False,
    }
    marks.append(new_mark)
    return new_mark


def has_unconsumed_studied_attack_mark(
    class_features: dict[str, Any],
    target_entity_id: str,
) -> bool:
    mark = get_unconsumed_studied_attack_mark(class_features, target_entity_id)
    return isinstance(mark, dict)


def get_unconsumed_studied_attack_mark(
    class_features: dict[str, Any],
    target_entity_id: str,
) -> dict[str, Any] | None:
    fighter = class_features.get("fighter")
    if not isinstance(fighter, dict):
        return None

    marks = fighter.get("studied_attacks")
    if not isinstance(marks, list):
        return None

    for mark in marks:
        if not isinstance(mark, dict):
            continue
        if mark.get("target_entity_id") != target_entity_id:
            continue
        if bool(mark.get("consumed")):
            continue
        return mark
    return None


def consume_studied_attack_mark(
    class_features: dict[str, Any],
    target_entity_id: str,
) -> bool:
    mark = get_unconsumed_studied_attack_mark(class_features, target_entity_id)
    if not isinstance(mark, dict):
        return False
    mark["consumed"] = True
    return True
