from __future__ import annotations

import random
import re
from typing import Any

from tools.repositories.encounter_repository import EncounterRepository


class ResolveBardicInspirationReaction:
    _FORMULA_RE = re.compile(r"^1d(\d+)$")

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
            raise ValueError("bardic_inspiration_actor_not_found")

        combat_flags = actor.combat_flags if isinstance(actor.combat_flags, dict) else {}
        inspiration = combat_flags.get("bardic_inspiration")
        if not isinstance(inspiration, dict):
            raise ValueError("bardic_inspiration_not_available")

        payload = request.get("payload")
        payload_data = payload if isinstance(payload, dict) else {}
        dc = payload_data.get("dc")
        current_total = payload_data.get("current_total")
        if isinstance(dc, bool) or not isinstance(dc, int):
            raise ValueError("bardic_inspiration_dc_missing")
        if isinstance(current_total, bool) or not isinstance(current_total, int):
            raise ValueError("bardic_inspiration_current_total_missing")

        die_formula = str(payload_data.get("bonus_formula") or inspiration.get("die") or "").strip().lower()
        match = self._FORMULA_RE.match(die_formula)
        if match is None:
            raise ValueError("bardic_inspiration_bonus_formula_invalid")
        die_sides = int(match.group(1))

        bonus_roll = self._resolve_bonus_roll(die_sides=die_sides, dice_rolls=dice_rolls)
        retry_total = current_total + bonus_roll
        combat_flags.pop("bardic_inspiration", None)
        self.encounter_repository.save(encounter)

        return {
            "resolution_mode": "rewrite_host_action",
            "reaction_result": {
                "status": "boosted",
                "feature_key": "bardic_inspiration",
                "used": True,
                "bonus_roll": bonus_roll,
                "original_total": current_total,
                "retry_total": retry_total,
                "final_total": retry_total,
                "dc": dc,
                "die": die_formula,
                "source_entity_id": payload_data.get("source_entity_id", inspiration.get("source_entity_id")),
                "source_name": payload_data.get("source_name", inspiration.get("source_name")),
            },
        }

    def _resolve_bonus_roll(self, *, die_sides: int, dice_rolls: dict[str, Any] | None) -> int:
        if isinstance(dice_rolls, dict):
            base_rolls = dice_rolls.get("base_rolls")
            if isinstance(base_rolls, list) and base_rolls:
                first_roll = base_rolls[0]
                if isinstance(first_roll, int) and not isinstance(first_roll, bool):
                    return first_roll
        return random.randint(1, die_sides)
