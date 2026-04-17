from __future__ import annotations

from typing import Any

from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.events.append_event import AppendEvent


class AbilityCheckResult:
    def __init__(self, encounter_repository: EncounterRepository, append_event: AppendEvent):
        self.encounter_repository = encounter_repository
        self.append_event = append_event

    def execute(
        self,
        *,
        encounter_id: str,
        roll_request: RollRequest,
        roll_result: RollResult,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        dc = roll_request.context.get("dc")
        if not isinstance(dc, int):
            raise ValueError("roll_request.context.dc must be an integer")

        success = roll_result.final_total >= dc
        result = {
            "encounter_id": encounter_id,
            "actor_id": roll_result.actor_entity_id,
            "check_type": roll_request.context.get("check_type"),
            "check": roll_request.context.get("check"),
            "dc": dc,
            "final_total": roll_result.final_total,
            "success": success,
            "failed": not success,
            "vantage": roll_result.metadata.get("vantage"),
            "chosen_roll": roll_result.metadata.get("chosen_roll"),
            "bonus_breakdown": roll_result.metadata.get("check_bonus_breakdown"),
            "comparison": {
                "left_label": "ability_check_total",
                "left_value": roll_result.final_total,
                "operator": ">=",
                "right_label": "dc",
                "right_value": dc,
                "passed": success,
            },
        }

        event = self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="ability_check_resolved",
            actor_entity_id=roll_result.actor_entity_id,
            request_id=roll_request.request_id,
            payload=result,
        )
        result["event_id"] = event.event_id
        return result
