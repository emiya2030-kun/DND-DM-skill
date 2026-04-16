from __future__ import annotations

from typing import Any

from tools.services.combat.rules.concentration.request_concentration_check import RequestConcentrationCheck
from tools.services.combat.rules.concentration.resolve_concentration_check import ResolveConcentrationCheck
from tools.services.combat.rules.concentration.resolve_concentration_result import ResolveConcentrationResult
from tools.services.encounter.get_encounter_state import GetEncounterState


class ExecuteConcentrationCheck:
    """把一次完整专注检定流程收口成一个统一入口。"""

    def __init__(
        self,
        request_concentration_check: RequestConcentrationCheck,
        resolve_concentration_check: ResolveConcentrationCheck,
        resolve_concentration_result: ResolveConcentrationResult,
    ):
        self.request_concentration_check = request_concentration_check
        self.resolve_concentration_check = resolve_concentration_check
        self.resolve_concentration_result = resolve_concentration_result

    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        damage_taken: int,
        base_rolls: list[int],
        vantage: str = "normal",
        source_entity_id: str | None = None,
        reason: str | None = None,
        additional_bonus: int = 0,
        include_encounter_state: bool = False,
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
    ) -> dict[str, Any]:
        """执行一次完整专注检定。"""
        request = self.request_concentration_check.execute(
            encounter_id=encounter_id,
            target_id=target_id,
            damage_taken=damage_taken,
            vantage=vantage,
            source_entity_id=source_entity_id,
            reason=reason,
        )
        roll_result = self.resolve_concentration_check.execute(
            encounter_id=encounter_id,
            roll_request=request,
            base_rolls=base_rolls,
            additional_bonus=additional_bonus,
            metadata=metadata,
            rolled_at=rolled_at,
        )
        resolution = self.resolve_concentration_result.execute(
            encounter_id=encounter_id,
            roll_request=request,
            roll_result=roll_result,
        )

        result = {
            "request": request.to_dict(),
            "roll_result": roll_result.to_dict(),
            "resolution": resolution,
        }
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.request_concentration_check.encounter_repository).execute(
                encounter_id
            )
        return result
