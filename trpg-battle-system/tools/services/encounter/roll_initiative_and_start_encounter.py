from __future__ import annotations

from random import random, randint
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.turns.start_turn import StartTurn


class RollInitiativeAndStartEncounter:
    """为当前遭遇战中的参战实体掷先攻，并启动首回合。"""

    def __init__(self, repository: EncounterRepository):
        self.repository = repository

    def execute(self, encounter_id: str) -> dict[str, Any]:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        rolled_rows: list[dict[str, Any]] = []
        for entity_id, entity in encounter.entities.items():
            modifier = int(entity.ability_mods.get("dex", 0))
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
            "initiative_results": [
                {
                    "entity_id": row["entity_id"],
                    "name": row["name"],
                    "initiative_roll": row["initiative_roll"],
                    "initiative_modifier": row["initiative_modifier"],
                    "initiative_total": row["initiative_total"],
                }
                for row in rolled_rows
            ],
        }

    def execute_with_state(self, encounter_id: str) -> dict[str, Any]:
        result = self.execute(encounter_id)
        result["encounter_state"] = GetEncounterState(self.repository).execute(encounter_id)
        return result
