from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import resolve_entity_save_proficiencies


class ResolveConcentrationCheck:
    """把专注检定的原始 d20 结果结算成最终总值。"""

    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        roll_request: RollRequest,
        base_rolls: list[int],
        additional_bonus: int = 0,
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
    ) -> RollResult:
        """根据优势/劣势和 CON 豁免加值计算专注检定最终结果。"""
        encounter = self._get_encounter_or_raise(encounter_id)
        self._validate_roll_request(encounter_id, roll_request)

        target = self._get_entity_or_raise(encounter, roll_request.actor_entity_id)
        vantage = roll_request.context.get("vantage", "normal")
        normalized_vantage = self._normalize_vantage(vantage)
        normalized_rolls = self._normalize_base_rolls(base_rolls, normalized_vantage)

        con_modifier = target.ability_mods.get("con", 0)
        if not isinstance(con_modifier, int):
            raise ValueError("ability_mods['con'] must be an integer")

        is_proficient = "con" in resolve_entity_save_proficiencies(target)
        proficiency_bonus_applied = target.proficiency_bonus if is_proficient else 0
        check_bonus = con_modifier + proficiency_bonus_applied + additional_bonus
        chosen_roll = self._choose_roll(normalized_rolls, normalized_vantage)
        final_total = chosen_roll + check_bonus

        result_metadata = dict(metadata or {})
        result_metadata.update(
            {
                "vantage": normalized_vantage,
                "chosen_roll": chosen_roll,
                "check_bonus": check_bonus,
                "check_bonus_breakdown": {
                    "ability_modifier": con_modifier,
                    "is_proficient": is_proficient,
                    "proficiency_bonus_applied": proficiency_bonus_applied,
                    "additional_bonus": additional_bonus,
                },
            }
        )

        return RollResult(
            request_id=roll_request.request_id,
            encounter_id=encounter_id,
            actor_entity_id=target.entity_id,
            target_entity_id=target.entity_id,
            roll_type="concentration_check",
            final_total=final_total,
            dice_rolls={
                "base_rolls": normalized_rolls,
                "chosen_roll": chosen_roll,
                "ability_modifier": con_modifier,
                "proficiency_bonus": proficiency_bonus_applied,
                "additional_bonus": additional_bonus,
                "check_bonus": check_bonus,
            },
            metadata=result_metadata,
            rolled_at=rolled_at,
        )

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

    def _validate_roll_request(self, encounter_id: str, roll_request: RollRequest) -> None:
        if roll_request.encounter_id != encounter_id:
            raise ValueError("roll_request.encounter_id does not match encounter_id")
        if roll_request.roll_type != "concentration_check":
            raise ValueError("roll_request must use concentration_check")

    def _normalize_vantage(self, vantage: str) -> str:
        if vantage not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("vantage must be 'normal', 'advantage', or 'disadvantage'")
        return vantage

    def _normalize_base_rolls(self, base_rolls: list[int], vantage: str) -> list[int]:
        if not isinstance(base_rolls, list) or not base_rolls:
            raise ValueError("base_rolls must be a non-empty list")
        normalized_rolls: list[int] = []
        for roll in base_rolls:
            if not isinstance(roll, int) or roll < 1 or roll > 20:
                raise ValueError("each base roll must be an integer between 1 and 20")
            normalized_rolls.append(roll)
        required_count = 1 if vantage == "normal" else 2
        if len(normalized_rolls) != required_count:
            raise ValueError(f"{vantage} concentration check requires {required_count} d20 roll(s)")
        return normalized_rolls

    def _choose_roll(self, base_rolls: list[int], vantage: str) -> int:
        if vantage == "advantage":
            return max(base_rolls)
        if vantage == "disadvantage":
            return min(base_rolls)
        return base_rolls[0]
