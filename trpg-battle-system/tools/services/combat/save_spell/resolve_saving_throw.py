from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.rules.conditions import (
    AUTO_FAIL_STRENGTH_DEX_SAVES,
    ConditionRuntime,
    DEX_SAVE_DISADVANTAGE_CONDITIONS,
)
from tools.services.combat.rules.conditions.condition_parser import parse_condition
from tools.services.class_features.shared import resolve_entity_save_proficiencies


class ResolveSavingThrow:
    """根据目标实体数据，自动计算一次豁免检定的最终总值。"""

    def __init__(self, encounter_repository: EncounterRepository):
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        roll_request: RollRequest,
        base_roll: int | None = None,
        base_rolls: list[int] | None = None,
        additional_bonus: int = 0,
        voluntary_fail: bool = False,
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
    ) -> RollResult:
        """把目标的 d20 原始点数结算成最终豁免结果。

        第一版只按基础规则计算：
        - 属性调整值
        - 若该豁免熟练，则加熟练加值
        - 额外临时加值

        这样能让上层只传入原始 d20 结果，后续判定和叙述都能拿到结构化数值。
        """
        encounter = self._get_encounter_or_raise(encounter_id)
        self._validate_roll_request(encounter_id, roll_request)

        target = self._get_entity_or_raise(encounter, roll_request.actor_entity_id)
        save_ability = roll_request.context.get("save_ability")
        requested_vantage = self._normalize_vantage(roll_request.context.get("vantage", "normal"))
        if not isinstance(save_ability, str) or not save_ability.strip():
            raise ValueError("roll_request.context.save_ability must be a non-empty string")
        if not isinstance(additional_bonus, int):
            raise ValueError("additional_bonus must be an integer")

        normalized_save_ability = save_ability.strip().lower()
        runtime = self._safe_condition_runtime(target.conditions)
        final_vantage, condition_disadvantages = self._resolve_vantage_with_conditions(
            requested_vantage,
            normalized_save_ability,
            runtime,
        )
        normalized_rolls = self._normalize_base_rolls(base_roll, base_rolls)
        self._ensure_roll_count_for_vantage(normalized_rolls, final_vantage)
        ability_modifier = target.ability_mods.get(normalized_save_ability, 0)
        if not isinstance(ability_modifier, int):
            raise ValueError(f"ability_mods['{normalized_save_ability}'] must be an integer")

        is_proficient = normalized_save_ability in resolve_entity_save_proficiencies(target)
        proficiency_bonus_applied = target.proficiency_bonus if is_proficient else 0
        save_bonus = ability_modifier + proficiency_bonus_applied + additional_bonus
        chosen_roll = self._choose_roll(normalized_rolls, final_vantage)
        auto_fail = self._should_auto_fail(normalized_save_ability, runtime)
        exhaustion_penalty = runtime.get_d20_penalty()
        if voluntary_fail or auto_fail:
            final_total = 0
        else:
            final_total = chosen_roll + save_bonus - exhaustion_penalty

        result_metadata = dict(metadata or {})
        result_metadata.update(
            {
                "voluntary_fail": voluntary_fail,
                "auto_fail": auto_fail,
                "save_ability": normalized_save_ability,
                "save_modifier": ability_modifier + proficiency_bonus_applied,
                "vantage": final_vantage,
                "rolled_vantage": requested_vantage,
                "condition_disadvantages": condition_disadvantages,
                "chosen_roll": chosen_roll,
                "save_bonus": save_bonus,
                "d20_penalty": exhaustion_penalty,
                "save_bonus_breakdown": {
                    "ability_modifier": ability_modifier,
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
            roll_type="saving_throw",
            final_total=final_total,
            dice_rolls={
                "base_rolls": normalized_rolls,
                "chosen_roll": chosen_roll,
                "ability_modifier": ability_modifier,
                "proficiency_bonus": proficiency_bonus_applied,
                "additional_bonus": additional_bonus,
                "save_bonus": save_bonus,
                "d20_penalty": exhaustion_penalty,
            },
            metadata=result_metadata,
            rolled_at=rolled_at,
        )

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _validate_roll_request(self, encounter_id: str, roll_request: RollRequest) -> None:
        if roll_request.encounter_id != encounter_id:
            raise ValueError("roll_request.encounter_id does not match encounter_id")
        if roll_request.roll_type != "saving_throw":
            raise ValueError("roll_request must use saving_throw")

    def _resolve_vantage_with_conditions(
        self,
        requested_vantage: str,
        save_ability: str,
        runtime: ConditionRuntime,
    ) -> tuple[str, list[str]]:
        advantage_sources: list[str] = []
        disadvantage_sources: list[str] = []
        condition_disadvantages: list[str] = []

        if requested_vantage == "advantage":
            advantage_sources.append("requested_advantage")
        elif requested_vantage == "disadvantage":
            disadvantage_sources.append("requested_disadvantage")

        if save_ability == "dex":
            for condition in DEX_SAVE_DISADVANTAGE_CONDITIONS:
                if runtime.has(condition):
                    disadvantage_sources.append(f"condition_{condition}")
                    condition_disadvantages.append(condition)

        if advantage_sources and disadvantage_sources:
            final_vantage = "normal"
        elif advantage_sources:
            final_vantage = "advantage"
        elif disadvantage_sources:
            final_vantage = "disadvantage"
        else:
            final_vantage = "normal"

        return final_vantage, condition_disadvantages

    def _normalize_vantage(self, vantage: Any) -> str:
        if vantage not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("roll_request.context.vantage must be 'normal', 'advantage', or 'disadvantage'")
        return str(vantage)

    def _normalize_base_rolls(
        self,
        base_roll: int | None,
        base_rolls: list[int] | None,
    ) -> list[int]:
        raw_rolls: list[int]
        if base_rolls is not None:
            raw_rolls = base_rolls
        elif base_roll is not None:
            raw_rolls = [base_roll]
        else:
            raise ValueError("base_roll or base_rolls is required")

        normalized_rolls: list[int] = []
        for roll in raw_rolls:
            if not isinstance(roll, int) or roll < 1 or roll > 20:
                raise ValueError("each base roll must be an integer between 1 and 20")
            normalized_rolls.append(roll)

        if len(normalized_rolls) > 2:
            raise ValueError("saving throw cannot use more than 2 d20 rolls")
        return normalized_rolls

    def _ensure_roll_count_for_vantage(self, rolls: list[int], vantage: str) -> None:
        if vantage == "normal":
            if len(rolls) not in {1, 2}:
                raise ValueError("normal saving throw requires 1 or 2 rolls")
        else:
            if len(rolls) != 2:
                raise ValueError(f"{vantage} saving throw requires 2 rolls")

    def _safe_condition_runtime(self, conditions: list[str]) -> ConditionRuntime:
        validated: list[str] = []
        for condition in conditions:
            try:
                parse_condition(condition)
            except ValueError:
                continue
            validated.append(condition)
        return ConditionRuntime(validated)

    def _choose_roll(self, base_rolls: list[int], vantage: str) -> int:
        if vantage == "advantage":
            return max(base_rolls)
        if vantage == "disadvantage":
            return min(base_rolls)
        return base_rolls[0]

    def _should_auto_fail(self, save_ability: str, runtime: ConditionRuntime) -> bool:
        if save_ability not in {"str", "dex"}:
            return False
        return any(runtime.has(condition) for condition in AUTO_FAIL_STRENGTH_DEX_SAVES)

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity
