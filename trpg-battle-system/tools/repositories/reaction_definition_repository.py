from __future__ import annotations

from typing import Any

from tools.services.combat.rules.reactions.reaction_definitions import REACTION_DEFINITIONS


class ReactionDefinitionRepository:
    """Reads reaction definitions from the local reaction rules modules."""

    def get(self, reaction_type: str) -> dict[str, Any]:
        definition = REACTION_DEFINITIONS.get(reaction_type)
        if definition is None:
            raise ValueError(f"reaction_definition '{reaction_type}' not found")
        return dict(definition)

    def list_by_trigger_type(self, trigger_type: str) -> list[dict[str, Any]]:
        return [
            dict(definition)
            for definition in REACTION_DEFINITIONS.values()
            if definition.get("trigger_type") == trigger_type
        ]
