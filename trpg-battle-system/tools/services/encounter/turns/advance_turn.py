from __future__ import annotations

from tools.models.encounter import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.turns.turn_engine import advance_turn


class AdvanceTurn:
    """遭遇战回合推进入口。"""

    def __init__(self, repository: EncounterRepository):
        self.repository = repository

    def execute(self, encounter_id: str) -> Encounter:
        encounter = self.repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        updated = advance_turn(encounter)
        return self.repository.save(updated)

    def execute_with_state(self, encounter_id: str) -> dict[str, object]:
        updated = self.execute(encounter_id)
        return {
            "encounter_id": updated.encounter_id,
            "encounter_state": GetEncounterState(self.repository).execute(encounter_id),
        }
