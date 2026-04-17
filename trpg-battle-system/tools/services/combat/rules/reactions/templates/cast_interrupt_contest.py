from __future__ import annotations

import random
from typing import Any

from tools.models import Encounter
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared import resolve_entity_save_proficiencies


class CastInterruptContest:
    """Resolve Counterspell-style interruption by forcing the caster to make a CON save."""

    def __init__(self, encounter_repository: EncounterRepository) -> None:
        self.encounter_repository = encounter_repository

    def execute(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        encounter = self._get_encounter_or_raise(encounter_id)
        actor = self._get_entity_or_raise(encounter, actor_entity_id)
        if target_entity_id is None:
            raise ValueError("counterspell_target_required")
        target = self._get_entity_or_raise(encounter, target_entity_id)

        pending_window = encounter.pending_reaction_window
        if not isinstance(pending_window, dict):
            raise ValueError("pending_reaction_window_not_found")
        host_snapshot = pending_window.get("host_action_snapshot")
        if not isinstance(host_snapshot, dict):
            raise ValueError("host_action_snapshot_missing")

        slot_consumed = self._consume_counterspell_resources(actor)
        save = self._roll_counterspell_save(actor=actor, target=target)

        if save["success"]:
            self.encounter_repository.save(encounter)
            return {
                "resolution_mode": "rewrite_host_action",
                "reaction_result": {
                    "status": "save_succeeded",
                    "actor_entity_id": actor_entity_id,
                    "target_entity_id": target_entity_id,
                    "payload": payload or {},
                    "slot_consumed": slot_consumed,
                    "save": save,
                },
            }

        action_cost = self._resolve_host_action_cost(host_snapshot)
        self._consume_host_action(target, action_cost)
        self.encounter_repository.save(encounter)
        return {
            "resolution_mode": "cancel_host_action",
            "reaction_result": {
                "status": "countered",
                "actor_entity_id": actor_entity_id,
                "target_entity_id": target_entity_id,
                "payload": payload or {},
                "slot_consumed": slot_consumed,
                "save": save,
                "cancelled_spell_id": host_snapshot.get("spell_id"),
                "wasted_action_cost": action_cost,
            },
        }

    def _get_encounter_or_raise(self, encounter_id: str) -> Encounter:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        return encounter

    def _get_entity_or_raise(self, encounter: Encounter, entity_id: str):
        entity = encounter.entities.get(entity_id)
        if entity is None:
            raise ValueError(f"entity '{entity_id}' not found in encounter")
        return entity

    def _consume_counterspell_resources(self, actor: Any) -> dict[str, Any]:
        if not isinstance(actor.action_economy, dict):
            actor.action_economy = {}
        actor.action_economy["reaction_used"] = True

        resources = actor.resources if isinstance(actor.resources, dict) else {}
        spell_slots = resources.get("spell_slots")
        if not isinstance(spell_slots, dict):
            raise ValueError("counterspell_requires_spell_slots")

        available_levels: list[int] = []
        for raw_level, slot_info in spell_slots.items():
            if not isinstance(slot_info, dict):
                continue
            remaining = slot_info.get("remaining")
            if not isinstance(remaining, int) or remaining <= 0:
                continue
            try:
                level = int(raw_level)
            except (TypeError, ValueError):
                continue
            if level >= 3:
                available_levels.append(level)
        if not available_levels:
            raise ValueError("counterspell_requires_level_3_or_higher_slot")

        slot_level = min(available_levels)
        slot_key = str(slot_level)
        slot_info = spell_slots[slot_key]
        before = int(slot_info["remaining"])
        slot_info["remaining"] = before - 1
        return {
            "slot_level": slot_level,
            "remaining_before": before,
            "remaining_after": slot_info["remaining"],
        }

    def _roll_counterspell_save(self, *, actor: Any, target: Any) -> dict[str, Any]:
        save_dc = self._resolve_counterspell_save_dc(actor)
        base_roll = random.randint(1, 20)
        con_mod = self._resolve_target_con_modifier(target)
        proficiency_bonus = self._resolve_target_save_proficiency_bonus(target, "con")
        final_total = base_roll + con_mod + proficiency_bonus
        return {
            "ability": "con",
            "save_dc": save_dc,
            "base_roll": base_roll,
            "modifier": con_mod,
            "proficiency_bonus": proficiency_bonus,
            "final_total": final_total,
            "success": final_total >= save_dc,
        }

    def _resolve_counterspell_save_dc(self, actor: Any) -> int:
        source_ref = actor.source_ref if isinstance(actor.source_ref, dict) else {}
        spellcasting_ability = source_ref.get("spellcasting_ability")
        if not isinstance(spellcasting_ability, str) or not spellcasting_ability.strip():
            raise ValueError("counterspell_actor_missing_spellcasting_ability")
        ability_mods = actor.ability_mods if isinstance(actor.ability_mods, dict) else {}
        ability_mod = ability_mods.get(spellcasting_ability)
        if not isinstance(ability_mod, int):
            raise ValueError("counterspell_actor_missing_spellcasting_modifier")
        proficiency_bonus = getattr(actor, "proficiency_bonus", 0)
        if not isinstance(proficiency_bonus, int):
            raise ValueError("counterspell_actor_invalid_proficiency_bonus")
        return 8 + proficiency_bonus + ability_mod

    def _resolve_target_con_modifier(self, target: Any) -> int:
        ability_mods = target.ability_mods if isinstance(target.ability_mods, dict) else {}
        con_mod = ability_mods.get("con", 0)
        if not isinstance(con_mod, int):
            raise ValueError("counterspelled_caster_missing_con_modifier")
        return con_mod

    def _resolve_target_save_proficiency_bonus(self, target: Any, ability: str) -> int:
        save_proficiencies = resolve_entity_save_proficiencies(target)
        if ability not in save_proficiencies:
            return 0
        proficiency_bonus = getattr(target, "proficiency_bonus", 0)
        if not isinstance(proficiency_bonus, int):
            raise ValueError("counterspelled_caster_invalid_proficiency_bonus")
        return proficiency_bonus

    def _resolve_host_action_cost(self, host_snapshot: dict[str, Any]) -> str:
        action_cost = host_snapshot.get("action_cost")
        if not isinstance(action_cost, str) or not action_cost.strip():
            return "action"
        normalized = action_cost.strip().lower()
        if normalized not in {"action", "bonus_action", "reaction"}:
            return "action"
        return normalized

    def _consume_host_action(self, target: Any, action_cost: str) -> None:
        if not isinstance(target.action_economy, dict):
            target.action_economy = {}
        if action_cost == "action":
            target.action_economy["action_used"] = True
            return
        if action_cost == "bonus_action":
            target.action_economy["bonus_action_used"] = True
            return
        target.action_economy["reaction_used"] = True
