from __future__ import annotations

from typing import Any

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository


class ResolveProtectionReaction:
    """Rewrites the triggering attack to disadvantage and grants brief protection coverage."""

    def __init__(self, encounter_repository: EncounterRepository) -> None:
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        request: dict[str, Any],
        option_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del option_payload
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, str(request.get("actor_entity_id")))
        target = self._get_entity_or_raise(encounter, str(request.get("target_entity_id")))
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if actor.action_economy.get("reaction_used"):
            raise ValueError("protection_reaction_already_used")

        pending_window = encounter.pending_reaction_window
        if not isinstance(pending_window, dict):
            raise ValueError("pending_reaction_window_not_found")
        host_snapshot = pending_window.get("host_action_snapshot")
        if not isinstance(host_snapshot, dict):
            raise ValueError("host_action_snapshot_missing")

        actor.action_economy["reaction_used"] = True
        host_snapshot["vantage"] = "disadvantage"
        host_snapshot["force_replay_attack_roll"] = True
        target.turn_effects.append(
            {
                "effect_id": f"effect_protection_{actor.entity_id}",
                "effect_type": "protection",
                "name": "Protection",
                "source_entity_id": actor.entity_id,
                "target_entity_id": target.entity_id,
                "expires_on": "source_next_turn_start",
            }
        )
        self.encounter_repository.save(encounter)
        return {
            "resolution_mode": "rewrite_host_action",
            "reaction_result": {
                "status": "protection_armed",
                "actor_entity_id": actor.entity_id,
                "target_entity_id": target.entity_id,
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
