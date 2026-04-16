from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.events.append_event import AppendEvent
from tools.services.spells.end_concentration_spell_instances import end_concentration_spell_instances


class ResolveConcentrationResult:
    """根据专注检定结果判断是否保持专注."""

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
        """结算一次专注检定,并在失败时打断专注."""
        encounter = self._get_encounter_or_raise(encounter_id)
        self._validate_inputs(encounter_id, roll_request, roll_result)

        target = self._get_entity_or_raise(encounter, roll_request.actor_entity_id)
        is_concentrating_before = bool(target.combat_flags.get("is_concentrating"))
        save_dc = roll_request.context.get("save_dc")
        if not isinstance(save_dc, int):
            raise ValueError("roll_request.context.save_dc must be an integer")

        success = roll_result.final_total >= save_dc
        spell_cleanup: dict[str, Any] | None = None
        if is_concentrating_before and not success:
            target.combat_flags["is_concentrating"] = False
            spell_cleanup = end_concentration_spell_instances(
                encounter=encounter,
                caster_entity_id=target.entity_id,
                reason="concentration_broken",
            )
            self.encounter_repository.save(encounter)

        result = {
            "encounter_id": encounter_id,
            "target_entity_id": target.entity_id,
            "damage_taken": roll_request.context.get("damage_taken"),
            "save_dc": save_dc,
            "final_total": roll_result.final_total,
            "check_bonus": roll_result.metadata.get("check_bonus"),
            "check_bonus_breakdown": roll_result.metadata.get("check_bonus_breakdown"),
            "vantage": roll_result.metadata.get("vantage"),
            "chosen_roll": roll_result.metadata.get("chosen_roll"),
            "success": success,
            "failed": not success,
            "is_concentrating_before": is_concentrating_before,
            "is_concentrating_after": bool(target.combat_flags.get("is_concentrating")),
            "comparison": {
                "left_label": "concentration_total",
                "left_value": roll_result.final_total,
                "operator": ">=",
                "right_label": "save_dc",
                "right_value": save_dc,
                "passed": success,
            },
        }
        if spell_cleanup is not None:
            result["spell_cleanup"] = spell_cleanup

        resolved_event = self.append_event.execute(
            encounter_id=encounter_id,
            round=encounter.round,
            event_type="concentration_check_resolved",
            actor_entity_id=target.entity_id,
            target_entity_id=target.entity_id,
            request_id=roll_request.request_id,
            payload=result,
        )
        result["event_id"] = resolved_event.event_id

        if is_concentrating_before and not success:
            broken_event = self.append_event.execute(
                encounter_id=encounter_id,
                round=encounter.round,
                event_type="concentration_broken",
                actor_entity_id=target.entity_id,
                target_entity_id=target.entity_id,
                request_id=roll_request.request_id,
                payload={
                    "target_entity_id": target.entity_id,
                    "reason": "failed concentration check",
                },
            )
            result["break_event_id"] = broken_event.event_id

        return result

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _validate_inputs(
        self,
        encounter_id: str,
        roll_request: RollRequest,
        roll_result: RollResult,
    ) -> None:
        if roll_request.encounter_id != encounter_id:
            raise ValueError("roll_request.encounter_id does not match encounter_id")
        if roll_result.encounter_id != encounter_id:
            raise ValueError("roll_result.encounter_id does not match encounter_id")
        if roll_request.roll_type != "concentration_check":
            raise ValueError("roll_request must use concentration_check")
        if roll_result.roll_type != "concentration_check":
            raise ValueError("roll_result must use concentration_check")
        if roll_request.request_id != roll_result.request_id:
            raise ValueError("roll_request.request_id does not match roll_result.request_id")
        if roll_request.actor_entity_id != roll_result.actor_entity_id:
            raise ValueError("roll_request.actor_entity_id does not match roll_result.actor_entity_id")
