from __future__ import annotations

import random
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.actions import find_help_ability_check_effect, remove_turn_effect_by_id
from tools.services.checks.ability_check_request import AbilityCheckRequest
from tools.services.checks.ability_check_result import AbilityCheckResult
from tools.services.checks.check_catalog import normalize_check_name
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
        class_feature_options: dict[str, Any] | None = None,
        reason: str | None = None,
        include_encounter_state: bool = False,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")

        normalized_check_type = str(check_type).strip().lower()
        normalized_check = normalize_check_name(normalized_check_type, str(check))
        help_effect = find_help_ability_check_effect(
            actor=actor,
            check_type=normalized_check_type,
            check_key=normalized_check,
        )
        effective_vantage = vantage
        if help_effect is not None and str(vantage or "normal").strip().lower() == "normal":
            effective_vantage = "advantage"

        request = self.request_service.execute(
            encounter_id=encounter_id,
            actor_id=actor_id,
            check_type=check_type,
            check=check,
            dc=dc,
            vantage=effective_vantage,
            reason=reason,
        )
        base_rolls = [random.randint(1, 20)]
        if effective_vantage in {"advantage", "disadvantage"}:
            base_rolls.append(random.randint(1, 20))
        roll_result = self.resolve_service.execute(
            encounter_id=encounter_id,
            roll_request=request,
            base_rolls=base_rolls,
            additional_bonus=additional_bonus,
            metadata={
                "class_feature_options": class_feature_options or {},
                **(
                    {"tactical_mind_bonus_roll": random.randint(1, 10)}
                    if isinstance(class_feature_options, dict) and class_feature_options.get("tactical_mind")
                    else {}
                ),
            },
        )
        outcome = self.result_service.execute(
            encounter_id=encounter_id,
            roll_request=request,
            roll_result=roll_result,
        )
        if help_effect is not None:
            updated = self.encounter_repository.get(encounter_id)
            if updated is not None:
                updated_actor = updated.entities.get(actor_id)
                if updated_actor is not None:
                    effect_id = help_effect.get("effect_id")
                    if isinstance(effect_id, str) and effect_id.strip():
                        remove_turn_effect_by_id(updated_actor, effect_id.strip())
                        self.encounter_repository.save(updated)

        result: dict[str, Any] = {
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "check_type": check_type,
            "request": request.to_dict(),
            "roll_result": roll_result.to_dict(),
            **outcome,
        }
        tactical_mind = roll_result.metadata.get("tactical_mind")
        if isinstance(tactical_mind, dict):
            result["class_feature_result"] = {"tactical_mind": tactical_mind}
        result["check"] = check
        result["normalized_check"] = request.context["check"]
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.encounter_repository).execute(encounter_id)
        return result
