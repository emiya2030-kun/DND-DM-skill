from __future__ import annotations

from typing import Any

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository


class ResolveInterceptionReaction:
    """Arms a pending flat damage reduction for the resumed host attack."""

    def __init__(self, encounter_repository: EncounterRepository) -> None:
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        request: dict[str, Any],
        option_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, str(request.get("actor_entity_id")))
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if actor.action_economy.get("reaction_used"):
            raise ValueError("interception_reaction_already_used")

        reduction_roll = 0
        if isinstance(option_payload, dict):
            reduction_roll = option_payload.get("reduction_roll", 0)
        if not isinstance(reduction_roll, int):
            raise ValueError("interception_reduction_roll_invalid")

        pending_window = encounter.pending_reaction_window
        if not isinstance(pending_window, dict):
            raise ValueError("pending_reaction_window_not_found")
        host_snapshot = pending_window.get("host_action_snapshot")
        if not isinstance(host_snapshot, dict):
            raise ValueError("host_action_snapshot_missing")

        total_reduction = reduction_roll + int(actor.proficiency_bonus or 0)
        actor.action_economy["reaction_used"] = True
        host_snapshot["pending_flat_damage_reduction"] = total_reduction
        self.encounter_repository.save(encounter)
        return {
            "resolution_mode": "rewrite_host_action",
            "reaction_result": {
                "status": "interception_armed",
                "actor_entity_id": actor.entity_id,
                "damage_reduction_total": total_reduction,
            },
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> Any:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity
