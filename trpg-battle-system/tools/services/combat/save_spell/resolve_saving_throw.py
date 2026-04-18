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
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.class_features.shared import ensure_paladin_runtime, resolve_entity_save_proficiencies


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
        save_dc = roll_request.context.get("save_dc")
        auto_success = bool(roll_request.context.get("auto_success"))
        requested_vantage = self._normalize_vantage(roll_request.context.get("vantage", "normal"))
        if not isinstance(save_ability, str) or not save_ability.strip():
            raise ValueError("roll_request.context.save_ability must be a non-empty string")
        if not isinstance(save_dc, int):
            raise ValueError("roll_request.context.save_dc must be an integer")
        if not isinstance(additional_bonus, int):
            raise ValueError("additional_bonus must be an integer")

        normalized_save_ability = save_ability.strip().lower()
        runtime = self._safe_condition_runtime(target.conditions)
        final_vantage, condition_disadvantages = self._resolve_vantage_with_conditions(
            requested_vantage,
            normalized_save_ability,
            runtime,
            target,
        )
        normalized_rolls = self._normalize_base_rolls(base_roll, base_rolls)
        self._ensure_roll_count_for_vantage(normalized_rolls, final_vantage)
        ability_modifier = target.ability_mods.get(normalized_save_ability, 0)
        if not isinstance(ability_modifier, int):
            raise ValueError(f"ability_mods['{normalized_save_ability}'] must be an integer")

        is_proficient = normalized_save_ability in resolve_entity_save_proficiencies(target)
        proficiency_bonus_applied = target.proficiency_bonus if is_proficient else 0
        aura_of_protection_bonus, aura_of_protection_source = self._resolve_aura_of_protection_bonus(
            encounter=encounter,
            target=target,
        )
        save_bonus = ability_modifier + proficiency_bonus_applied + additional_bonus + aura_of_protection_bonus
        chosen_roll = self._choose_roll(normalized_rolls, final_vantage)
        auto_fail = self._should_auto_fail(normalized_save_ability, runtime)
        exhaustion_penalty = runtime.get_d20_penalty()
        if voluntary_fail or auto_fail:
            final_total = 0
        elif auto_success:
            final_total = save_dc
        else:
            final_total = chosen_roll + save_bonus - exhaustion_penalty
            final_total = self._apply_indomitable_might(
                target=target,
                save_ability=normalized_save_ability,
                current_total=final_total,
            )

        result_metadata = dict(metadata or {})
        result_metadata.update(
            {
                "voluntary_fail": voluntary_fail,
                "auto_fail": auto_fail,
                "auto_success": auto_success,
                "save_ability": normalized_save_ability,
                "save_modifier": ability_modifier + proficiency_bonus_applied,
                "vantage": final_vantage,
                "rolled_vantage": requested_vantage,
                "condition_disadvantages": condition_disadvantages,
                "chosen_roll": chosen_roll,
                "save_bonus": save_bonus,
                "d20_penalty": exhaustion_penalty,
                "aura_of_protection_bonus": aura_of_protection_bonus,
                "aura_of_protection_source": aura_of_protection_source,
                "save_bonus_breakdown": {
                    "ability_modifier": ability_modifier,
                    "is_proficient": is_proficient,
                    "proficiency_bonus_applied": proficiency_bonus_applied,
                    "additional_bonus": additional_bonus,
                    "aura_of_protection_bonus": aura_of_protection_bonus,
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
                "aura_of_protection_bonus": aura_of_protection_bonus,
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
        target: EncounterEntity,
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
        if self._has_barbarian_rage_strength_advantage(target=target, save_ability=save_ability):
            advantage_sources.append("barbarian_rage_strength_save_advantage")

        if advantage_sources and disadvantage_sources:
            final_vantage = "normal"
        elif advantage_sources:
            final_vantage = "advantage"
        elif disadvantage_sources:
            final_vantage = "disadvantage"
        else:
            final_vantage = "normal"

        return final_vantage, condition_disadvantages

    def _has_barbarian_rage_strength_advantage(self, *, target: EncounterEntity, save_ability: str) -> bool:
        if save_ability != "str":
            return False
        barbarian = ensure_barbarian_runtime(target)
        rage = barbarian.get("rage")
        return isinstance(rage, dict) and bool(rage.get("active"))

    def _resolve_aura_of_protection_bonus(
        self,
        *,
        encounter: Encounter,
        target: EncounterEntity,
    ) -> tuple[int, str | None]:
        best_bonus = 0
        best_source: str | None = None

        for entity in encounter.entities.values():
            if entity.side != target.side:
                continue

            class_features = entity.class_features if isinstance(entity.class_features, dict) else {}
            if "paladin" not in class_features:
                continue
            paladin = ensure_paladin_runtime(entity)
            aura = paladin.get("aura_of_protection")
            if not isinstance(aura, dict) or not bool(aura.get("enabled")):
                continue
            if self._safe_condition_runtime(entity.conditions).has("incapacitated"):
                continue

            radius_feet = aura.get("radius_feet", 10)
            if not isinstance(radius_feet, int) or radius_feet < 0:
                radius_feet = 10
            if self._distance_feet(entity, target) > radius_feet:
                continue

            charisma_modifier = entity.ability_mods.get("cha", 0)
            if isinstance(charisma_modifier, bool) or not isinstance(charisma_modifier, int):
                charisma_modifier = 0
            bonus = max(1, charisma_modifier)
            if bonus > best_bonus:
                best_bonus = bonus
                best_source = entity.entity_id

        return best_bonus, best_source

    def _apply_indomitable_might(
        self,
        *,
        target: EncounterEntity,
        save_ability: str,
        current_total: int,
    ) -> int:
        if save_ability != "str":
            return current_total
        barbarian = ensure_barbarian_runtime(target)
        indomitable_might = barbarian.get("indomitable_might")
        if not isinstance(indomitable_might, dict) or not bool(indomitable_might.get("enabled")):
            return current_total
        strength_score = target.ability_scores.get("str")
        if isinstance(strength_score, int) and not isinstance(strength_score, bool):
            return max(current_total, strength_score)
        return current_total

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

    def _distance_feet(self, source: EncounterEntity, target: EncounterEntity) -> int:
        dx = abs(source.position["x"] - target.position["x"])
        dy = abs(source.position["y"] - target.position["y"])
        return max(dx, dy) * 5

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity
