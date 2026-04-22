from __future__ import annotations

import random
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import ensure_fighter_runtime


class ResolveTacticalMindReaction:
    """Resolve the fighter Tactical Mind failed-check boost."""

    def __init__(self, encounter_repository: EncounterRepository) -> None:
        self.encounter_repository = encounter_repository

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
            raise ValueError("tactical_mind_actor_not_found")

        fighter = ensure_fighter_runtime(actor)
        if not fighter:
            raise ValueError("tactical_mind_not_available")

        second_wind = fighter.get("second_wind")
        if not isinstance(second_wind, dict):
            raise ValueError("tactical_mind_requires_second_wind")
        remaining_uses = second_wind.get("remaining_uses")
        if isinstance(remaining_uses, bool) or not isinstance(remaining_uses, int) or remaining_uses <= 0:
            raise ValueError("tactical_mind_requires_second_wind")

        payload = request.get("payload")
        payload_data = payload if isinstance(payload, dict) else {}
        dc = payload_data.get("dc")
        current_total = payload_data.get("current_total")
        if isinstance(dc, bool) or not isinstance(dc, int):
            raise ValueError("tactical_mind_dc_missing")
        if isinstance(current_total, bool) or not isinstance(current_total, int):
            raise ValueError("tactical_mind_current_total_missing")

        bonus_roll = random.randint(1, 10)
        retry_total = current_total + bonus_roll
        consumed_second_wind = retry_total >= dc
        if consumed_second_wind:
            second_wind["remaining_uses"] = remaining_uses - 1
            self.encounter_repository.save(encounter)

        return {
            "resolution_mode": "rewrite_host_action",
            "reaction_result": {
                "status": "boosted",
                "used": True,
                "bonus_roll": bonus_roll,
                "original_total": current_total,
                "retry_total": retry_total,
                "final_total": retry_total,
                "dc": dc,
                "consumed_second_wind": consumed_second_wind,
            },
        }
