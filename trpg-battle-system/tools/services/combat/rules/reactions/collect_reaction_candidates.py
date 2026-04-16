from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tools.models import Encounter

if TYPE_CHECKING:
    from tools.repositories import EncounterRepository
    from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository


class CollectReactionCandidates:
    """Pulls candidate actors and definitions for a trigger event."""

    def __init__(
        self,
        encounter_repository: "EncounterRepository",
        definition_repository: "ReactionDefinitionRepository",
    ) -> None:
        self.encounter_repository = encounter_repository
        self.definition_repository = definition_repository

    def execute(self, *, encounter: Encounter, trigger_event: dict[str, Any]) -> list[dict[str, Any]]:
        trigger_type = str(trigger_event.get("trigger_type", ""))
        definitions = self.definition_repository.list_by_trigger_type(trigger_type)
        if trigger_type == "attack_declared":
            target_id = trigger_event.get("target_entity_id")
            if not isinstance(target_id, str) or target_id not in encounter.entities:
                return []

            return [
                {
                    "actor_entity_id": target_id,
                    "reaction_definition": definition,
                }
                for definition in definitions
            ]

        return []
