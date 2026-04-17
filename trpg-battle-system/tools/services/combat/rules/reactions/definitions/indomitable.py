from __future__ import annotations

import random
from typing import Any
from uuid import uuid4

from tools.models.roll_request import RollRequest
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow


class ResolveIndomitableReaction:
    """Resolve the fighter Indomitable failed-save reroll."""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        resolve_saving_throw: ResolveSavingThrow | None = None,
    ) -> None:
        self.encounter_repository = encounter_repository
        self.resolve_saving_throw = resolve_saving_throw or ResolveSavingThrow(encounter_repository)

    def execute(
        self,
        *,
        encounter_id: str,
        request: dict[str, Any],
        final_total: int | None = None,
        dice_rolls: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        actor_entity_id = str(request.get("actor_entity_id") or "")
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError("indomitable_actor_not_found")

        fighter = actor.class_features.get("fighter") if isinstance(actor.class_features, dict) else None
        if not isinstance(fighter, dict):
            raise ValueError("indomitable_not_available")

        indomitable_state = fighter.get("indomitable")
        if not isinstance(indomitable_state, dict):
            raise ValueError("indomitable_not_available")
        remaining_uses = indomitable_state.get("remaining_uses")
        if isinstance(remaining_uses, bool) or not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("indomitable_no_remaining_uses")

        fighter_level = fighter.get("fighter_level", fighter.get("level", 0))
        if isinstance(fighter_level, bool) or not isinstance(fighter_level, int) or fighter_level <= 0:
            raise ValueError("fighter_level_invalid")

        payload = request.get("payload")
        payload_data = payload if isinstance(payload, dict) else {}
        save_ability = str(payload_data.get("save_ability") or "").strip().lower()
        if not save_ability:
            raise ValueError("indomitable_save_ability_missing")
        save_dc = payload_data.get("save_dc")
        if isinstance(save_dc, bool) or not isinstance(save_dc, int):
            raise ValueError("indomitable_save_dc_missing")
        vantage = str(payload_data.get("vantage") or "normal").strip().lower()

        reroll_request = RollRequest(
            request_id=f"req_indomitable_{uuid4().hex[:12]}",
            encounter_id=encounter_id,
            actor_entity_id=actor.entity_id,
            target_entity_id=actor.entity_id,
            roll_type="saving_throw",
            formula="1d20+save_modifier",
            reason=f"{actor.name} uses Indomitable",
            context={
                "save_ability": save_ability,
                "save_dc": save_dc,
                "vantage": vantage,
            },
        )

        base_rolls = self._resolve_base_rolls(vantage=vantage, dice_rolls=dice_rolls)
        save_result = self.resolve_saving_throw.execute(
            encounter_id=encounter_id,
            roll_request=reroll_request,
            base_rolls=base_rolls,
            additional_bonus=fighter_level,
            metadata={
                "source": "class_feature",
                "reaction_type": "indomitable",
                "fighter_level_bonus": fighter_level,
            },
        )

        indomitable_state["remaining_uses"] = remaining_uses - 1
        self.encounter_repository.save(encounter)

        return {
            "resolution_mode": "standalone",
            "reaction_result": {
                "status": "rerolled",
                "save": {
                    "request_id": save_result.request_id,
                    "save_ability": save_ability,
                    "dc": save_dc,
                    "final_total": save_result.final_total,
                    "success": save_result.final_total >= save_dc,
                    "fighter_level_bonus": fighter_level,
                    "dice_rolls": save_result.dice_rolls,
                    "metadata": save_result.metadata,
                },
            },
        }

    def _resolve_base_rolls(self, *, vantage: str, dice_rolls: dict[str, Any] | None) -> list[int]:
        if isinstance(dice_rolls, dict):
            raw_base_rolls = dice_rolls.get("base_rolls")
            if isinstance(raw_base_rolls, list) and raw_base_rolls:
                return [int(roll) for roll in raw_base_rolls]

        if vantage in {"advantage", "disadvantage"}:
            return [random.randint(1, 20), random.randint(1, 20)]
        return [random.randint(1, 20)]
