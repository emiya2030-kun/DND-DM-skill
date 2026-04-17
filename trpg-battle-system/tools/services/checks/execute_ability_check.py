from __future__ import annotations

import random
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository
from tools.services.checks.ability_check_request import AbilityCheckRequest
from tools.services.checks.ability_check_result import AbilityCheckResult
from tools.services.checks.resolve_ability_check import ResolveAbilityCheck
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.events.append_event import AppendEvent


class ExecuteAbilityCheck:
    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
    ):
        self.encounter_repository = encounter_repository
        self.request_service = AbilityCheckRequest(encounter_repository)
        self.resolve_service = ResolveAbilityCheck(encounter_repository)
        self.result_service = AbilityCheckResult(encounter_repository, append_event)

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        check_type: str,
        check: str,
        dc: int,
        vantage: str = "normal",
        additional_bonus: int = 0,
        reason: str | None = None,
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        request = self.request_service.execute(
            encounter_id=encounter_id,
            actor_id=actor_id,
            check_type=check_type,
            check=check,
            dc=dc,
            vantage=vantage,
            reason=reason,
        )
        base_rolls = [random.randint(1, 20)]
        if vantage in {"advantage", "disadvantage"}:
            base_rolls.append(random.randint(1, 20))
        roll_result = self.resolve_service.execute(
            encounter_id=encounter_id,
            roll_request=request,
            base_rolls=base_rolls,
            additional_bonus=additional_bonus,
        )
        outcome = self.result_service.execute(
            encounter_id=encounter_id,
            roll_request=request,
            roll_result=roll_result,
        )

        result: dict[str, Any] = {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "check_type": check_type,
            "request": request.to_dict(),
            "roll_result": roll_result.to_dict(),
            **outcome,
        }
        result["check"] = check
        result["normalized_check"] = request.context["check"]
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return result
