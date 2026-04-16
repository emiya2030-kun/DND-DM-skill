from __future__ import annotations

from typing import Any

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.attack.execute_attack import ExecuteAttack
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class ResolveReactionRequest:
    """处理一个待执行的 reaction request。"""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        execute_attack: ExecuteAttack,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.execute_attack = execute_attack

    def execute(
        self,
        *,
        encounter_id: str,
        request_id: str,
        final_total: int,
        dice_rolls: dict[str, Any],
        damage_rolls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        request = self._get_pending_request_or_raise(encounter, request_id)
        if request.get("reaction_type") != "opportunity_attack":
            raise ValueError("unsupported_reaction_type")

        actor_entity_id = str(request["actor_entity_id"])
        target_entity_id = str(request["target_entity_id"])
        weapon_id = str(request["payload"]["weapon_id"])
        attack_result = self.execute_attack.execute(
            encounter_id=encounter_id,
            actor_id=actor_entity_id,
            target_id=target_entity_id,
            weapon_id=weapon_id,
            final_total=final_total,
            dice_rolls=dice_rolls,
            damage_rolls=damage_rolls,
            consume_action=False,
            consume_reaction=True,
            allow_out_of_turn_actor=True,
        )

        encounter = self._get_encounter_or_raise(encounter_id)
        request = self._get_pending_request_or_raise(encounter, request_id)
        request["status"] = "resolved"
        self.encounter_repository.save(encounter)
        event = self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="reaction_request_resolved",
            actor_entity_id=actor_entity_id,
            target_entity_id=target_entity_id,
            payload={
                "request_id": request_id,
                "reaction_type": request["reaction_type"],
                "weapon_id": weapon_id,
            },
        )
        return {
            "encounter_id": encounter_id,
            "request_id": request_id,
            "reaction_type": request["reaction_type"],
            "attack_result": attack_result,
            "event_id": event.event_id,
            "encounter_state": GetEncounterState(self.encounter_repository).execute(encounter_id),
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_pending_request_or_raise(self, encounter: Encounter, request_id: str) -> dict[str, Any]:
        for request in encounter.reaction_requests:
            if request.get("request_id") == request_id:
                if request.get("status") != "pending":
                    raise ValueError("reaction_request_not_pending")
                return request
        raise ValueError(f"reaction_request '{request_id}' not found")
