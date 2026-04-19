from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter
from tools.models.encounter_entity import EncounterEntity
from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.checks.check_catalog import SKILL_TO_ABILITY
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime
from tools.services.class_features.shared import (
    ensure_ranger_runtime,
    ensure_rogue_runtime,
    get_fighter_runtime,
    has_skill_expertise,
    has_skill_proficiency,
    resolve_entity_skill_proficiencies,
)
from tools.services.combat.rules.conditions import ConditionRuntime
from tools.services.combat.rules.conditions.condition_parser import parse_condition


class ResolveAbilityCheck:
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
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
    ) -> RollResult:
        encounter = self._get_encounter_or_raise(encounter_id)
        self._validate_roll_request(encounter_id, roll_request)
        actor = self._get_entity_or_raise(encounter, roll_request.actor_entity_id)

        check_type = str(roll_request.context["check"])
        requested_check_type = str(roll_request.context["check_type"])
        requested_vantage = self._normalize_vantage(roll_request.context.get("vantage", "normal"))
        class_feature_options = self._normalize_class_feature_options(
            roll_request.context.get("class_feature_options"),
        )
        resolved_ability = self._resolve_check_ability(
            actor=actor,
            check_type=requested_check_type,
            check=check_type,
            class_feature_options=class_feature_options,
        )
        final_vantage = self._resolve_vantage(
            actor=actor,
            requested_vantage=requested_vantage,
            resolved_ability=resolved_ability,
        )
        normalized_rolls = self._normalize_base_rolls(base_roll, base_rolls)
        self._ensure_roll_count_for_vantage(normalized_rolls, final_vantage)
        chosen_roll = self._choose_roll(normalized_rolls, final_vantage)
        chosen_roll = self._apply_reliable_talent(
            actor=actor,
            check_type=requested_check_type,
            check=check_type,
            chosen_roll=chosen_roll,
        )
        runtime = self._safe_condition_runtime(actor.conditions)
        exhaustion_penalty = runtime.get_d20_penalty()
        check_bonus, breakdown = self._resolve_bonus(
            actor=actor,
            check_type=requested_check_type,
            check=check_type,
            additional_bonus=additional_bonus,
            resolved_ability=resolved_ability,
        )
        final_total = chosen_roll + check_bonus - exhaustion_penalty
        final_total = self._apply_indomitable_might(
            actor=actor,
            resolved_ability=resolved_ability,
            current_total=final_total,
        )
        dc = roll_request.context.get("dc")
        if not isinstance(dc, int):
            raise ValueError("roll_request.context.dc must be an integer")

        result_metadata = dict(metadata or {})
        result_metadata.update(
            {
                "check_type": requested_check_type,
                "check": check_type,
                "vantage": final_vantage,
                "requested_vantage": requested_vantage,
                "chosen_roll": chosen_roll,
                "check_bonus": check_bonus,
                "check_bonus_breakdown": breakdown,
                "d20_penalty": exhaustion_penalty,
            }
        )
        final_total, tactical_mind_metadata = self._apply_tactical_mind(
            encounter=encounter,
            actor=actor,
            dc=dc,
            current_total=final_total,
            metadata=result_metadata,
        )
        if tactical_mind_metadata is not None:
            result_metadata["tactical_mind"] = tactical_mind_metadata

        return RollResult(
            request_id=roll_request.request_id,
            encounter_id=encounter_id,
            actor_entity_id=actor.entity_id,
            roll_type="ability_check",
            final_total=final_total,
            dice_rolls={
                "base_rolls": normalized_rolls,
                "chosen_roll": chosen_roll,
                "check_bonus": check_bonus,
                "additional_bonus": additional_bonus,
                "d20_penalty": exhaustion_penalty,
            },
            metadata=result_metadata,
            rolled_at=rolled_at,
        )

    def _apply_tactical_mind(
        self,
        *,
        encounter: Encounter,
        actor: EncounterEntity,
        dc: int,
        current_total: int,
        metadata: dict[str, Any],
    ) -> tuple[int, dict[str, Any] | None]:
        raw_options = metadata.get("class_feature_options")
        if not isinstance(raw_options, dict) or not raw_options.get("tactical_mind"):
            return current_total, None
        if current_total >= dc:
            return current_total, {
                "used": False,
                "bonus_roll": 0,
                "consumed_second_wind": False,
                "reason": "check_already_succeeded",
            }

        fighter = get_fighter_runtime(actor)
        if not fighter:
            raise ValueError("tactical_mind_requires_fighter_runtime")
        second_wind = fighter.get("second_wind")
        if not isinstance(second_wind, dict):
            raise ValueError("tactical_mind_requires_second_wind")
        remaining_uses = second_wind.get("remaining_uses")
        if not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("tactical_mind_requires_second_wind")

        override_bonus_roll = metadata.get("tactical_mind_bonus_roll")
        if isinstance(override_bonus_roll, int) and not isinstance(override_bonus_roll, bool):
            bonus_roll = override_bonus_roll
        else:
            import random

            bonus_roll = random.randint(1, 10)

        retry_total = current_total + bonus_roll
        consumed = retry_total >= dc
        if consumed:
            second_wind["remaining_uses"] = remaining_uses - 1
            self.encounter_repository.save(encounter)
        return retry_total, {
            "used": True,
            "bonus_roll": bonus_roll,
            "consumed_second_wind": consumed,
            "retry_total": retry_total,
            "original_total": current_total,
        }

    def _resolve_bonus(
        self,
        *,
        actor: EncounterEntity,
        check_type: str,
        check: str,
        additional_bonus: int,
        resolved_ability: str,
    ) -> tuple[int, dict[str, Any]]:
        if not isinstance(additional_bonus, int):
            raise ValueError("additional_bonus must be an integer")

        if check_type == "ability":
            ability_modifier = int(actor.ability_mods.get(resolved_ability, 0))
            return ability_modifier + additional_bonus, {
                "source": "ability_modifier",
                "ability": resolved_ability,
                "ability_modifier": ability_modifier,
                "additional_bonus": additional_bonus,
            }

        default_ability = SKILL_TO_ABILITY[check]
        if resolved_ability == default_ability and check in actor.skill_modifiers and isinstance(actor.skill_modifiers[check], int):
            skill_modifier = int(actor.skill_modifiers[check])
            return skill_modifier + additional_bonus, {
                "source": "skill_modifier",
                "ability": resolved_ability,
                "skill_modifier": skill_modifier,
                "additional_bonus": additional_bonus,
            }

        ability_modifier = int(actor.ability_mods.get(resolved_ability, 0))
        is_proficient = has_skill_proficiency(actor, check)
        proficiency_multiplier = 2 if is_proficient and has_skill_expertise(actor, check) else 1
        proficiency_bonus = int(actor.proficiency_bonus) * proficiency_multiplier if is_proficient else 0
        return ability_modifier + proficiency_bonus + additional_bonus, {
            "source": "ability_plus_proficiency",
            "ability": resolved_ability,
            "ability_modifier": ability_modifier,
            "is_proficient": is_proficient,
            "proficiency_multiplier": proficiency_multiplier,
            "proficiency_bonus_applied": proficiency_bonus,
            "additional_bonus": additional_bonus,
        }

    def _apply_reliable_talent(
        self,
        *,
        actor: EncounterEntity,
        check_type: str,
        check: str,
        chosen_roll: int,
    ) -> int:
        if check_type != "skill":
            return chosen_roll
        if not has_skill_proficiency(actor, check):
            return chosen_roll
        rogue_runtime = ensure_rogue_runtime(actor)
        reliable_talent = rogue_runtime.get("reliable_talent")
        if not isinstance(reliable_talent, dict) or not reliable_talent.get("enabled"):
            return chosen_roll
        return max(chosen_roll, 10)

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _validate_roll_request(self, encounter_id: str, roll_request: RollRequest) -> None:
        if roll_request.encounter_id != encounter_id:
            raise ValueError("roll_request.encounter_id does not match encounter_id")
        if roll_request.roll_type != "ability_check":
            raise ValueError("roll_request must use ability_check")

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> EncounterEntity:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _normalize_vantage(self, vantage: Any) -> str:
        if vantage not in {"normal", "advantage", "disadvantage"}:
            raise ValueError("roll_request.context.vantage must be 'normal', 'advantage', or 'disadvantage'")
        return str(vantage)

    def _normalize_class_feature_options(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        return {}

    def _resolve_check_ability(
        self,
        *,
        actor: EncounterEntity,
        check_type: str,
        check: str,
        class_feature_options: dict[str, Any],
    ) -> str:
        if check_type == "ability":
            return check

        resolved_ability = SKILL_TO_ABILITY[check]
        if not bool(class_feature_options.get("primal_knowledge")):
            return resolved_ability

        barbarian = ensure_barbarian_runtime(actor)
        primal_knowledge = barbarian.get("primal_knowledge")
        rage = barbarian.get("rage")
        if not isinstance(primal_knowledge, dict) or not bool(primal_knowledge.get("enabled")):
            return resolved_ability
        if not isinstance(rage, dict) or not bool(rage.get("active")):
            return resolved_ability

        if check in {"acrobatics", "intimidation", "perception", "stealth", "survival"}:
            return "str"
        return resolved_ability

    def _resolve_vantage(
        self,
        *,
        actor: EncounterEntity,
        requested_vantage: str,
        resolved_ability: str,
    ) -> str:
        advantage_sources: list[str] = []
        disadvantage_sources: list[str] = []
        if requested_vantage == "advantage":
            advantage_sources.append("requested_advantage")
        elif requested_vantage == "disadvantage":
            disadvantage_sources.append("requested_disadvantage")

        barbarian = ensure_barbarian_runtime(actor)
        rage = barbarian.get("rage")
        if resolved_ability == "str" and isinstance(rage, dict) and bool(rage.get("active")):
            advantage_sources.append("barbarian_rage_strength_advantage")

        if advantage_sources and disadvantage_sources:
            return "normal"
        if advantage_sources:
            return "advantage"
        if disadvantage_sources:
            return "disadvantage"
        return "normal"

    def _apply_indomitable_might(
        self,
        *,
        actor: EncounterEntity,
        resolved_ability: str,
        current_total: int,
    ) -> int:
        if resolved_ability != "str":
            return current_total
        barbarian = ensure_barbarian_runtime(actor)
        indomitable_might = barbarian.get("indomitable_might")
        if not isinstance(indomitable_might, dict) or not bool(indomitable_might.get("enabled")):
            return current_total
        strength_score = actor.ability_scores.get("str")
        if isinstance(strength_score, int) and not isinstance(strength_score, bool):
            return max(current_total, strength_score)
        return current_total

    def _normalize_base_rolls(self, base_roll: int | None, base_rolls: list[int] | None) -> list[int]:
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
            raise ValueError("ability check cannot use more than 2 d20 rolls")
        return normalized_rolls

    def _ensure_roll_count_for_vantage(self, rolls: list[int], vantage: str) -> None:
        if vantage == "normal":
            if len(rolls) not in {1, 2}:
                raise ValueError("normal ability check requires 1 or 2 rolls")
            return
        if len(rolls) != 2:
            raise ValueError(f"{vantage} ability check requires 2 rolls")

    def _choose_roll(self, base_rolls: list[int], vantage: str) -> int:
        if vantage == "advantage":
            return max(base_rolls)
        if vantage == "disadvantage":
            return min(base_rolls)
        return base_rolls[0]

    def _safe_condition_runtime(self, conditions: list[str]) -> ConditionRuntime:
        validated: list[str] = []
        for condition in conditions:
            try:
                parse_condition(condition)
            except ValueError:
                continue
            validated.append(condition)
        return ConditionRuntime(validated)
