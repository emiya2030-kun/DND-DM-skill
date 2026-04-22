from __future__ import annotations

import random
from typing import Any
from uuid import uuid4

from tools.models.roll_request import RollRequest
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_bard_runtime
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow


class ResolveCountercharmReaction:
    """Resolve the bard Countercharm failed-save reroll."""

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
            raise ValueError("countercharm_actor_not_found")
        if bool(actor.action_economy.get("reaction_used")):
            raise ValueError("countercharm_reaction_already_used")

        bard = ensure_bard_runtime(actor)
        countercharm = bard.get("countercharm")
        if not isinstance(countercharm, dict) or not bool(countercharm.get("enabled")):
            raise ValueError("countercharm_not_available")

        payload = request.get("payload")
        payload_data = payload if isinstance(payload, dict) else {}
        target_entity_id = str(payload_data.get("target_entity_id") or request.get("target_entity_id") or "")
        target = encounter.entities.get(target_entity_id)
        if target is None:
            raise ValueError("countercharm_target_not_found")
        if actor.side != target.side:
            raise ValueError("countercharm_target_not_ally")

        radius_feet = countercharm.get("range_feet", 30)
        if not isinstance(radius_feet, int):
            radius_feet = 30
        if self._distance_feet(actor, target) > radius_feet:
            raise ValueError("countercharm_target_out_of_range")

        save_ability = str(payload_data.get("save_ability") or "").strip().lower()
        if not save_ability:
            raise ValueError("countercharm_save_ability_missing")
        save_dc = payload_data.get("save_dc")
        if isinstance(save_dc, bool) or not isinstance(save_dc, int):
            raise ValueError("countercharm_save_dc_missing")

        reroll_request = RollRequest(
            request_id=f"req_countercharm_{uuid4().hex[:12]}",
            encounter_id=encounter_id,
            actor_entity_id=target.entity_id,
            target_entity_id=target.entity_id,
            roll_type="saving_throw",
            formula="1d20+save_modifier",
            reason=f"{target.name} uses Countercharm",
            context={
                "save_ability": save_ability,
                "save_dc": save_dc,
                "vantage": "advantage",
            },
        )

        save_result = self.resolve_saving_throw.execute(
            encounter_id=encounter_id,
            roll_request=reroll_request,
            base_rolls=self._resolve_base_rolls(dice_rolls=dice_rolls),
            metadata={
                "source": "class_feature",
                "reaction_type": "countercharm",
                "countercharm_actor_id": actor.entity_id,
                "countercharm_target_id": target.entity_id,
            },
        )

        actor.action_economy["reaction_used"] = True
        self.encounter_repository.save(encounter)

        return {
            "resolution_mode": "rewrite_host_action",
            "reaction_result": {
                "status": "rerolled",
                "feature_key": "countercharm",
                "actor_entity_id": actor.entity_id,
                "target_entity_id": target.entity_id,
                "final_total": save_result.final_total,
                "save_roll_result": save_result.to_dict(),
                "save": {
                    "request_id": save_result.request_id,
                    "save_ability": save_ability,
                    "dc": save_dc,
                    "final_total": save_result.final_total,
                    "success": save_result.final_total >= save_dc,
                    "dice_rolls": save_result.dice_rolls,
                    "metadata": save_result.metadata,
                },
            },
        }

    def _resolve_base_rolls(self, *, dice_rolls: dict[str, Any] | None) -> list[int]:
        if isinstance(dice_rolls, dict):
            raw_base_rolls = dice_rolls.get("base_rolls")
            if isinstance(raw_base_rolls, list) and raw_base_rolls:
                rolls = [int(roll) for roll in raw_base_rolls]
                if len(rolls) >= 2:
                    return rolls[:2]
                if len(rolls) == 1:
                    return [rolls[0], random.randint(1, 20)]
        return [random.randint(1, 20), random.randint(1, 20)]

    def _distance_feet(self, source: Any, target: Any) -> int:
        dx = abs(int(source.position["x"]) - int(target.position["x"]))
        dy = abs(int(source.position["y"]) - int(target.position["y"]))
        return max(dx, dy) * 5
