from __future__ import annotations

import random
from typing import Any

from tools.models.encounter_entity import EncounterEntity


def resolve_death_save(*, target: EncounterEntity) -> dict[str, Any]:
    roll = random.randint(1, 20)
    death_saves = _ensure_death_saves(target)
    successes = _get_counter(death_saves.get("successes"))
    failures = _get_counter(death_saves.get("failures"))

    outcome = "death_save_failure"

    if roll == 20:
        _revive_target(target)
        death_saves["successes"] = 0
        death_saves["failures"] = 0
        outcome = "death_save_revived"
    elif roll == 1:
        failures += 2
        death_saves["failures"] = failures
        if failures >= 3:
            target.combat_flags["is_dead"] = True
            outcome = "death_save_dead"
        else:
            outcome = "death_save_critical_failure"
    elif roll >= 10:
        successes += 1
        death_saves["successes"] = successes
        if successes >= 3:
            _revive_target(target)
            death_saves["successes"] = 0
            death_saves["failures"] = 0
            outcome = "death_save_revived"
        else:
            outcome = "death_save_success"
    else:
        failures += 1
        death_saves["failures"] = failures
        if failures >= 3:
            target.combat_flags["is_dead"] = True
            outcome = "death_save_dead"
        else:
            outcome = "death_save_failure"

    return {
        "type": "death_save",
        "entity_id": target.entity_id,
        "roll": roll,
        "successes": int(death_saves.get("successes", 0)),
        "failures": int(death_saves.get("failures", 0)),
        "outcome": outcome,
    }


def _ensure_death_saves(target: EncounterEntity) -> dict[str, int]:
    combat_flags = target.combat_flags if isinstance(target.combat_flags, dict) else {}
    target.combat_flags = combat_flags
    death_saves = combat_flags.get("death_saves")
    if not isinstance(death_saves, dict):
        death_saves = {"successes": 0, "failures": 0}
        combat_flags["death_saves"] = death_saves
    if "successes" not in death_saves or not isinstance(death_saves.get("successes"), int):
        death_saves["successes"] = 0
    if "failures" not in death_saves or not isinstance(death_saves.get("failures"), int):
        death_saves["failures"] = 0
    return death_saves


def _get_counter(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _revive_target(target: EncounterEntity) -> None:
    target.hp["current"] = min(target.hp["max"], 1)
    target.combat_flags["is_dead"] = False
    if "unconscious" in target.conditions:
        target.conditions.remove("unconscious")
