from __future__ import annotations

from typing import Any
from uuid import uuid4

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import get_class_runtime


class ResolveDeflectAttacksReaction:
    """Arms a pending monk damage-reduction effect for the resumed host attack."""

    def __init__(self, encounter_repository: EncounterRepository) -> None:
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        request: dict[str, Any],
        option_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, str(request.get("actor_entity_id")))
        monk_runtime = get_class_runtime(actor, "monk")
        if not monk_runtime:
            raise ValueError("deflect_attacks_requires_monk_runtime")
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        if actor.action_economy.get("reaction_used"):
            raise ValueError("deflect_attacks_reaction_already_used")

        level = monk_runtime.get("level", 0)
        dex_mod = actor.ability_mods.get("dex", 0)
        if not isinstance(level, int):
            raise ValueError("deflect_attacks_requires_monk_level")
        if not isinstance(dex_mod, int):
            dex_mod = 0

        payload_data = request.get("payload") if isinstance(request.get("payload"), dict) else {}
        option_data = option_payload if isinstance(option_payload, dict) else {}
        reduction_roll = option_data.get("reduction_roll", 0)
        if not isinstance(reduction_roll, int):
            raise ValueError("deflect_attacks_reduction_roll_invalid")

        redirect_requested = bool(option_data.get("redirect_enabled"))
        if redirect_requested:
            focus = monk_runtime.get("focus_points")
            if not isinstance(focus, dict):
                raise ValueError("deflect_attacks_redirect_requires_focus_points")
            remaining = focus.get("remaining")
            if not isinstance(remaining, int) or remaining <= 0:
                raise ValueError("deflect_attacks_redirect_requires_focus_points")

        pending_window = encounter.pending_reaction_window if isinstance(encounter.pending_reaction_window, dict) else {}
        host_action_id = pending_window.get("host_action_id")
        effect = {
            "effect_id": f"effect_deflect_attacks_{uuid4().hex[:12]}",
            "effect_type": "deflect_attacks_pending",
            "attack_id": host_action_id,
            "damage_reduction_total": reduction_roll + dex_mod + level,
            "redirect_requested": redirect_requested,
            "redirect_target_id": option_data.get("redirect_target_id"),
            "redirect_save_roll": option_data.get("redirect_save_roll"),
            "redirect_damage_rolls": option_data.get("redirect_damage_rolls"),
            "redirect_damage_type": payload_data.get("primary_damage_type"),
            "source_entity_id": actor.entity_id,
            "target_entity_id": actor.entity_id,
        }
        actor.turn_effects.append(effect)
        actor.action_economy["reaction_used"] = True
        self.encounter_repository.save(encounter)
        return {
            "resolution_mode": "rewrite_host_action",
            "reaction_result": {
                "status": "deflect_attacks_armed",
                "actor_entity_id": actor.entity_id,
                "damage_reduction_total": effect["damage_reduction_total"],
                "redirect_requested": redirect_requested,
                "effect_id": effect["effect_id"],
            },
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str) -> Any:
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity
