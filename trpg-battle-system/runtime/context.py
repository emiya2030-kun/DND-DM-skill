from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.repositories import (
    EncounterRepository,
    EventRepository,
    EntityDefinitionRepository,
    SpellDefinitionRepository,
)
from tools.services import GetEncounterState


@dataclass
class BattleRuntimeContext:
    encounter_repository: EncounterRepository
    event_repository: EventRepository
    entity_definition_repository: EntityDefinitionRepository
    spell_definition_repository: SpellDefinitionRepository

    def get_encounter_state(self, encounter_id: str) -> dict[str, Any]:
        return GetEncounterState(
            self.encounter_repository,
            event_repository=self.event_repository,
        ).execute(encounter_id)

    def close(self) -> None:
        self.encounter_repository.close()
        self.event_repository.close()


def build_runtime_context(*, data_dir: Path | None = None) -> BattleRuntimeContext:
    if data_dir is None:
        return BattleRuntimeContext(
            encounter_repository=EncounterRepository(),
            event_repository=EventRepository(),
            entity_definition_repository=EntityDefinitionRepository(),
            spell_definition_repository=SpellDefinitionRepository(),
        )

    return BattleRuntimeContext(
        encounter_repository=EncounterRepository(data_dir / "encounters.json"),
        event_repository=EventRepository(data_dir / "events.json"),
        entity_definition_repository=EntityDefinitionRepository(),
        spell_definition_repository=SpellDefinitionRepository(),
    )
