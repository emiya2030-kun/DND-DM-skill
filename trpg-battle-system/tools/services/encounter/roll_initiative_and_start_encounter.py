from __future__ import annotations

import re
from random import random, randint
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.class_features.shared import get_class_runtime
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.turns.start_turn import StartTurn


class RollInitiativeAndStartEncounter:
    """为当前遭遇战中的参战实体掷先攻，并启动首回合。"""

    _FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")

    def __init__(self, repository: EncounterRepository):
        self.repository = repository

    def execute(
        self,
        encounter_id: str,
        initiative_options: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        rolled_rows: list[dict[str, Any]] = []
        initiative_feature_results: list[dict[str, Any]] = []
        for entity_id, entity in encounter.entities.items():
            persistent_rage_result = self._apply_persistent_rage_restore_if_available(entity=entity)
            if persistent_rage_result is not None:
                initiative_feature_results.append(persistent_rage_result)
            option = (initiative_options or {}).get(entity_id, {})
            metabolism_result = self._apply_uncanny_metabolism_if_requested(entity=entity, option=option)
            if metabolism_result is not None:
                initiative_feature_results.append(metabolism_result)
            modifier = int(entity.ability_mods.get("dex", 0))
            vantage = "normal"
            barbarian = ensure_barbarian_runtime(entity) if entity.class_features.get("barbarian") else {}
            if barbarian.get("feral_instinct", {}).get("enabled"):
                roll = max(randint(1, 20), randint(1, 20))
                vantage = "advantage"
            else:
                roll = randint(1, 20)
            tiebreak = round(random(), 2)
            total = roll + modifier
            entity.initiative = total
            rolled_rows.append(
                {
                    "entity_id": entity_id,
                    "name": entity.name,
                    "initiative_roll": roll,
                    "initiative_modifier": modifier,
                    "initiative_total": total,
                    "initiative_tiebreak_decimal": tiebreak,
                    "vantage": vantage,
                }
            )

        rolled_rows.sort(
            key=lambda row: (
                row["initiative_total"],
                row["initiative_modifier"],
                row["initiative_tiebreak_decimal"],
            ),
            reverse=True,
        )
        encounter.turn_order = [row["entity_id"] for row in rolled_rows]
        encounter.current_entity_id = encounter.turn_order[0] if encounter.turn_order else None
        self.repository.save(encounter)

        started = StartTurn(self.repository).execute(encounter_id)

        return {
            "encounter_id": encounter_id,
            "turn_order": list(started.turn_order),
            "current_entity_id": started.current_entity_id,
            "initiative_feature_results": initiative_feature_results,
            "initiative_results": [
                {
                    "entity_id": row["entity_id"],
                    "name": row["name"],
                    "initiative_roll": row["initiative_roll"],
                    "initiative_modifier": row["initiative_modifier"],
                    "initiative_total": row["initiative_total"],
                    "vantage": row["vantage"],
                }
                for row in rolled_rows
            ],
        }

    def _apply_persistent_rage_restore_if_available(self, *, entity: Any) -> dict[str, Any] | None:
        if not entity.class_features.get("barbarian"):
            return None

        barbarian = ensure_barbarian_runtime(entity)
        rage = barbarian.get("rage")
        if not isinstance(rage, dict) or not bool(rage.get("persistent_rage")):
            return None
        if bool(rage.get("restored_on_initiative_this_long_rest")):
            return None

        max_uses = rage.get("max")
        remaining = rage.get("remaining")
        if not isinstance(max_uses, int) or not isinstance(remaining, int):
            return None
        if remaining >= max_uses:
            return None

        rage["remaining"] = max_uses
        rage["restored_on_initiative_this_long_rest"] = True
        return {
            "entity_id": entity.entity_id,
            "feature_id": "barbarian.persistent_rage",
            "rage_restored_to": max_uses,
        }

    def execute_with_state(
        self,
        encounter_id: str,
        initiative_options: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result = self.execute(encounter_id, initiative_options=initiative_options)
        result["encounter_state"] = GetEncounterState(self.repository).execute(encounter_id)
        return result

    def _apply_uncanny_metabolism_if_requested(
        self,
        *,
        entity: Any,
        option: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not bool(option.get("use_uncanny_metabolism")):
            return None

        monk_runtime = get_class_runtime(entity, "monk")
        if not monk_runtime:
            raise ValueError("uncanny_metabolism_requires_monk_runtime")

        metabolism_runtime = monk_runtime.get("uncanny_metabolism")
        if not isinstance(metabolism_runtime, dict) or not bool(metabolism_runtime.get("available")):
            raise ValueError("uncanny_metabolism_unavailable")

        focus_points = monk_runtime.get("focus_points")
        if not isinstance(focus_points, dict):
            raise ValueError("uncanny_metabolism_requires_focus_points")
        max_points = focus_points.get("max")
        remaining_points = focus_points.get("remaining")
        if not isinstance(max_points, int) or not isinstance(remaining_points, int):
            raise ValueError("uncanny_metabolism_requires_focus_points")

        martial_arts_die = monk_runtime.get("martial_arts_die")
        if not isinstance(martial_arts_die, str) or not martial_arts_die.strip():
            raise ValueError("uncanny_metabolism_requires_martial_arts_die")

        monk_level = monk_runtime.get("level", 0)
        if not isinstance(monk_level, int):
            raise ValueError("uncanny_metabolism_requires_monk_level")

        healing_roll = self._roll_formula_once(martial_arts_die)
        healing_total = healing_roll + monk_level
        focus_points["remaining"] = max_points
        entity.hp["current"] = min(entity.hp["max"], entity.hp["current"] + healing_total)
        metabolism_runtime["available"] = False
        return {
            "entity_id": entity.entity_id,
            "feature_id": "monk.uncanny_metabolism",
            "focus_points_restored_to": max_points,
            "healing_roll": healing_roll,
            "healing_total": healing_total,
        }

    def _roll_formula_once(self, formula: str) -> int:
        match = self._FORMULA_RE.match(formula.strip())
        if match is None:
            raise ValueError("invalid_uncanny_metabolism_formula")
        count = int(match.group(1))
        sides = int(match.group(2))
        modifier = int(match.group(3) or 0)
        return sum(randint(1, sides) for _ in range(count)) + modifier
