from __future__ import annotations

import math
import random
import re
from typing import Any
from uuid import uuid4

from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.class_features.shared.warlock_invocations import (
    has_selected_warlock_invocation,
    resolve_gaze_of_two_minds_origin,
)
from tools.services.combat.attack.attack_roll_result import AttackRollResult
from tools.services.combat.damage import ResolveDamageParts
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow
from tools.services.combat.save_spell.saving_throw_request import SavingThrowRequest
from tools.services.combat.save_spell.saving_throw_result import SavingThrowResult
from tools.services.combat.shared.update_conditions import UpdateConditions
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.movement_rules import get_center_position, get_occupied_cells
from tools.services.encounter.resolve_forced_movement import ResolveForcedMovement
from tools.services.events.append_event import AppendEvent
from tools.services.spells.area_geometry import (
    build_spell_area_overlay,
    collect_circle_cells,
    collect_entities_in_cells,
)
from tools.services.spells.build_spell_instance import build_spell_instance
from tools.services.spells.encounter_cast_spell import EncounterCastSpell
from tools.services.spells.spell_request import SpellRequest


class ExecuteSpell:
    """统一施法入口：先做 SpellRequest，再声明施法并扣资源。"""

    _FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")

    def __init__(
        self,
        *,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        spell_request: SpellRequest,
        encounter_cast_spell: EncounterCastSpell | None = None,
    ):
        self.encounter_repository = encounter_repository
        self.append_event = append_event
        self.spell_request = spell_request
        self.encounter_cast_spell = encounter_cast_spell or EncounterCastSpell(
            encounter_repository,
            append_event,
            spell_definition_repository=self.spell_request.spell_definition_repository,
        )
        self.saving_throw_request = SavingThrowRequest(
            encounter_repository,
            spell_definition_repository=self.spell_request.spell_definition_repository,
        )
        self.resolve_saving_throw = ResolveSavingThrow(encounter_repository)
        self.update_hp = UpdateHp(encounter_repository, append_event)
        self.attack_roll_result = AttackRollResult(
            encounter_repository,
            append_event,
            update_hp=self.update_hp,
        )
        self.resolve_forced_movement = ResolveForcedMovement(encounter_repository, append_event)
        self.resolve_damage_parts = ResolveDamageParts()
        self.saving_throw_result = SavingThrowResult(
            encounter_repository,
            append_event,
            update_hp=self.update_hp,
            update_conditions=UpdateConditions(encounter_repository, append_event),
        )
        self.get_encounter_state = GetEncounterState(encounter_repository)

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        request_result = self.spell_request.execute(
            encounter_id=kwargs["encounter_id"],
            actor_id=kwargs["actor_id"],
            spell_id=kwargs["spell_id"],
            cast_level=kwargs["cast_level"],
            target_entity_ids=kwargs.get("target_entity_ids"),
            target_point=kwargs.get("target_point"),
            declared_action_cost=kwargs.get("declared_action_cost"),
            context=kwargs.get("context"),
            allow_out_of_turn_actor=bool(kwargs.get("allow_out_of_turn_actor", False)),
        )
        if not request_result.get("ok"):
            return request_result

        encounter_id = kwargs["encounter_id"]
        spell_definition = request_result.get("spell_definition")
        prepared_save_damage: dict[str, Any] | None = None
        prepared_save_condition: dict[str, Any] | None = None
        prepared_heal_spell: dict[str, Any] | None = None
        prepared_attack_spell: dict[str, Any] | None = None
        if self._is_save_damage_area_spell(spell_definition):
            prepared_save_damage = self._prepare_save_damage_resolution(
                encounter_id=encounter_id,
                actor_id=request_result["actor_id"],
                spell_id=request_result["spell_id"],
                spell_definition=spell_definition,
                target_point=request_result.get("target_point"),
                save_rolls=kwargs.get("save_rolls"),
                damage_rolls=kwargs.get("damage_rolls"),
            )
            if not prepared_save_damage.get("ok"):
                return prepared_save_damage
        elif self._is_save_condition_spell(spell_definition):
            prepared_save_condition = self._prepare_save_condition_resolution(
                target_ids=request_result.get("target_entity_ids"),
                save_rolls=kwargs.get("save_rolls"),
            )
            if not prepared_save_condition.get("ok"):
                return prepared_save_condition
        elif self._is_heal_spell(spell_definition):
            prepared_heal_spell = self._prepare_heal_spell_resolution(
                encounter_id=encounter_id,
                actor_id=request_result["actor_id"],
                spell_definition=spell_definition,
                target_ids=request_result.get("target_entity_ids"),
                upcast_delta=request_result.get("upcast_delta"),
            )
            if not prepared_heal_spell.get("ok"):
                return prepared_heal_spell
        elif self._is_attack_roll_spell(spell_definition):
            prepared_attack_spell = self._prepare_attack_spell_resolution(
                encounter_id=encounter_id,
                actor_id=request_result["actor_id"],
                spell_definition=spell_definition,
                target_ids=request_result.get("target_entity_ids"),
                resolved_scaling=request_result.get("resolved_scaling"),
                spell_origin_entity_id=request_result.get("spell_origin_entity_id"),
                attack_rolls=kwargs.get("attack_rolls"),
                damage_rolls=kwargs.get("damage_rolls"),
            )
            if not prepared_attack_spell.get("ok"):
                return prepared_attack_spell

        cast_result = self.encounter_cast_spell.execute(
            encounter_id=encounter_id,
            actor_id=request_result["actor_id"],
            spell_id=request_result["spell_id"],
            target_ids=request_result.get("target_entity_ids") or [],
            target_point=request_result.get("target_point"),
            cast_level=request_result["cast_level"],
            include_encounter_state=False,
            apply_no_roll_immediate_effects=self._is_no_roll_spell(spell_definition),
            allow_out_of_turn_actor=bool(kwargs.get("allow_out_of_turn_actor", False)),
        )
        if cast_result.get("status") == "waiting_reaction":
            return cast_result

        if prepared_save_damage is not None:
            target_ids = prepared_save_damage["target_ids"]
            save_roll_index = prepared_save_damage["save_roll_index"]
            normalized_damage_rolls = prepared_save_damage["damage_rolls"]
            if normalized_damage_rolls is None:
                normalized_damage_rolls = self._build_auto_outcome_damage_rolls(
                    spell_definition=spell_definition,
                    outcome_key="on_failed_save",
                    is_critical_hit=False,
                )
            target_resolutions: list[dict[str, Any]] = []
            for target_id in target_ids:
                roll_input = save_roll_index.get(target_id)
                vantage = roll_input.get("vantage", "normal") if isinstance(roll_input, dict) else "normal"
                roll_request = self.saving_throw_request.execute(
                    encounter_id=encounter_id,
                    target_id=target_id,
                    spell_id=request_result["spell_id"],
                    vantage=vantage if isinstance(vantage, str) else "normal",
                    description=f"{cast_result.get('spell_name', request_result['spell_id'])} area save",
                )
                if not isinstance(roll_input, dict):
                    roll_input = self._build_auto_save_roll_input(vantage=roll_request.context.get("vantage", "normal"))
                roll_result = self.resolve_saving_throw.execute(
                    encounter_id=encounter_id,
                    roll_request=roll_request,
                    base_roll=roll_input.get("base_roll"),
                    base_rolls=roll_input.get("base_rolls"),
                    additional_bonus=roll_input.get("additional_bonus", 0),
                    voluntary_fail=bool(roll_input.get("voluntary_fail", False)),
                )
                resolution = self.saving_throw_result.execute(
                    encounter_id=encounter_id,
                    roll_request=roll_request,
                    roll_result=roll_result,
                    spell_definition=spell_definition,
                    damage_rolls=normalized_damage_rolls,
                    cast_level=cast_result["cast_level"],
                    damage_reason=cast_result.get("spell_name") or request_result["spell_id"],
                    concentration_vantage="normal",
                )
                target_resolutions.append(
                    {
                        "target_id": target_id,
                        "save": {
                            "success": resolution["success"],
                            "failed": resolution["failed"],
                            "save_dc": resolution["save_dc"],
                            "final_total": resolution["final_total"],
                            "ability": resolution.get("save_ability"),
                        },
                        "damage_resolution": resolution.get("damage_resolution"),
                        "hp_update": resolution.get("hp_update"),
                    }
                )
            self._store_spell_area_overlay(
                encounter_id=encounter_id,
                spell_definition=spell_definition,
                target_point=request_result.get("target_point"),
            )
            return {
                "encounter_id": cast_result["encounter_id"],
                "actor_id": request_result["actor_id"],
                "spell_id": cast_result["spell_id"],
                "cast_level": cast_result["cast_level"],
                "resource_update": cast_result.get("slot_consumed"),
                "spell_resolution": {
                    "mode": "save_damage",
                    "resolution_mode": "save_damage",
                    "targets": target_resolutions,
                },
                "encounter_state": self.get_encounter_state.execute(encounter_id),
            }

        if prepared_save_condition is not None:
            target_ids = prepared_save_condition["target_ids"]
            save_roll_index = prepared_save_condition["save_roll_index"]
            target_resolutions: list[dict[str, Any]] = []
            failed_targets: list[dict[str, Any]] = []
            temporary_instance_ids: list[str] = []
            for target_id in target_ids:
                roll_input = save_roll_index.get(target_id)
                vantage = roll_input.get("vantage", "normal") if isinstance(roll_input, dict) else "normal"
                roll_request = self.saving_throw_request.execute(
                    encounter_id=encounter_id,
                    target_id=target_id,
                    spell_id=request_result["spell_id"],
                    vantage=vantage if isinstance(vantage, str) else "normal",
                    description=f"{cast_result.get('spell_name', request_result['spell_id'])} save",
                )
                if not isinstance(roll_input, dict):
                    roll_input = self._build_auto_save_roll_input(vantage=roll_request.context.get("vantage", "normal"))
                roll_result = self.resolve_saving_throw.execute(
                    encounter_id=encounter_id,
                    roll_request=roll_request,
                    base_roll=roll_input.get("base_roll"),
                    base_rolls=roll_input.get("base_rolls"),
                    additional_bonus=roll_input.get("additional_bonus", 0),
                    voluntary_fail=bool(roll_input.get("voluntary_fail", False)),
                )
                resolution = self.saving_throw_result.execute(
                    encounter_id=encounter_id,
                    roll_request=roll_request,
                    roll_result=roll_result,
                    spell_definition=spell_definition,
                    cast_level=cast_result["cast_level"],
                    damage_reason=cast_result.get("spell_name") or request_result["spell_id"],
                    concentration_vantage="normal",
                )
                conditions_applied = self._extract_conditions_applied(resolution.get("condition_updates"))
                turn_effect_updates = resolution.get("turn_effect_updates")
                if not isinstance(turn_effect_updates, list):
                    turn_effect_updates = []
                turn_effect_ids = [
                    update.get("effect_id")
                    for update in turn_effect_updates
                    if isinstance(update, dict) and isinstance(update.get("effect_id"), str)
                ]
                temporary_instance_id = None
                spell_instance = resolution.get("spell_instance")
                if isinstance(spell_instance, dict):
                    raw_instance_id = spell_instance.get("instance_id")
                    if isinstance(raw_instance_id, str) and raw_instance_id.strip():
                        temporary_instance_id = raw_instance_id.strip()
                if temporary_instance_id is not None:
                    temporary_instance_ids.append(temporary_instance_id)
                if resolution.get("failed"):
                    failed_targets.append(
                        {
                            "target_id": target_id,
                            "applied_conditions": conditions_applied,
                            "turn_effect_ids": turn_effect_ids,
                        }
                    )
                target_resolutions.append(
                    {
                        "target_id": target_id,
                        "save": {
                            "success": resolution["success"],
                            "failed": resolution["failed"],
                            "save_dc": resolution["save_dc"],
                            "final_total": resolution["final_total"],
                            "ability": resolution.get("save_ability"),
                        },
                        "conditions_applied": conditions_applied,
                        "turn_effect_updates": turn_effect_updates,
                    }
                )

            spell_instance = self._finalize_multi_target_spell_instance(
                encounter_id=encounter_id,
                spell_definition=spell_definition,
                caster_entity_id=request_result["actor_id"],
                cast_level=cast_result["cast_level"],
                failed_targets=failed_targets,
                temporary_instance_ids=temporary_instance_ids,
            )
            spell_resolution: dict[str, Any] = {
                "mode": "save_condition",
                "resolution_mode": "save_condition",
                "targets": target_resolutions,
            }
            if spell_instance is not None:
                spell_resolution["spell_instance"] = spell_instance
            return {
                "encounter_id": cast_result["encounter_id"],
                "actor_id": request_result["actor_id"],
                "spell_id": cast_result["spell_id"],
                "cast_level": cast_result["cast_level"],
                "resource_update": cast_result.get("slot_consumed"),
                "spell_resolution": spell_resolution,
                "encounter_state": self.get_encounter_state.execute(encounter_id),
            }

        if prepared_heal_spell is not None:
            target_id = prepared_heal_spell["target_id"]
            healing_rolls = prepared_heal_spell["healing_rolls"]
            healing_total = prepared_heal_spell["healing_total"]
            hp_update = self.update_hp.execute(
                encounter_id=encounter_id,
                target_id=target_id,
                hp_change=-healing_total,
                reason=cast_result.get("spell_name") or request_result["spell_id"],
                source_entity_id=request_result["actor_id"],
            )
            return {
                "encounter_id": cast_result["encounter_id"],
                "actor_id": request_result["actor_id"],
                "spell_id": cast_result["spell_id"],
                "cast_level": cast_result["cast_level"],
                "resource_update": cast_result.get("slot_consumed"),
                "spell_resolution": {
                    "mode": "heal",
                    "resolution_mode": "heal",
                    "target_id": target_id,
                    "healing_rolls": healing_rolls,
                    "healing_total": healing_total,
                    "hp_update": hp_update,
                },
                "encounter_state": self.get_encounter_state.execute(encounter_id),
            }

        if prepared_attack_spell is not None:
            target_resolutions: list[dict[str, Any]] = []
            spell_name = cast_result.get("spell_name") or request_result["spell_id"]
            for beam in prepared_attack_spell["beams"]:
                attack_roll = beam["attack_roll"]
                if not isinstance(attack_roll, dict):
                    attack_roll = self._build_auto_attack_roll_entry(actor=prepared_attack_spell["actor"])
                roll_result = RollResult(
                    request_id=f"spell_attack_{uuid4().hex}",
                    encounter_id=encounter_id,
                    actor_entity_id=request_result["actor_id"],
                    target_entity_id=beam["target_id"],
                    roll_type="spell_attack",
                    final_total=attack_roll["final_total"],
                    dice_rolls=attack_roll["dice_rolls"],
                    metadata={},
                )
                attack_resolution = self.attack_roll_result.execute(
                    encounter_id=encounter_id,
                    roll_result=roll_result,
                    attack_name=spell_name,
                    attack_kind="spell_attack",
                )
                beam_result: dict[str, Any] = {
                    "beam_index": beam["beam_index"],
                    "target_id": beam["target_id"],
                    "attack": {
                        "hit": attack_resolution["hit"],
                        "is_critical_hit": attack_resolution["is_critical_hit"],
                        "final_total": attack_resolution["final_total"],
                        "target_ac": attack_resolution["target_ac"],
                    },
                }
                if attack_resolution["hit"]:
                    damage_parts = self._build_attack_spell_damage_parts(
                        spell_definition=spell_definition,
                        resolved_scaling=request_result.get("resolved_scaling"),
                        actor_id=request_result["actor_id"],
                        actor=prepared_attack_spell["actor"],
                        target=beam["target"],
                    )
                    expected_sources = [part["source"] for part in damage_parts]
                    damage_rolls = beam["damage_rolls"]
                    if damage_rolls is None:
                        damage_rolls = self._build_auto_damage_rolls_from_parts(
                            damage_parts=damage_parts,
                            is_critical_hit=attack_resolution["is_critical_hit"],
                        )
                    indexed_rolls = self._index_damage_rolls_for_spell_target(
                        expected_sources=expected_sources,
                        damage_rolls=damage_rolls,
                    )
                    damage_resolution = self.resolve_damage_parts.execute(
                        damage_parts=damage_parts,
                        is_critical_hit=attack_resolution["is_critical_hit"],
                        rolled_values=[indexed_rolls[source] for source in expected_sources],
                        resistances=beam["target"].resistances,
                        immunities=beam["target"].immunities,
                        vulnerabilities=beam["target"].vulnerabilities,
                    )
                    hp_update = self.update_hp.execute(
                        encounter_id=encounter_id,
                        target_id=beam["target_id"],
                        hp_change=damage_resolution["total_damage"],
                        reason=f"{spell_name} damage",
                        damage_type=None,
                        source_entity_id=request_result["actor_id"],
                        concentration_vantage="normal",
                    )
                    beam_result["damage_resolution"] = damage_resolution
                    beam_result["hp_update"] = hp_update
                    forced_movement = self._resolve_attack_spell_on_hit_forced_movement(
                        encounter_id=encounter_id,
                        spell_definition=spell_definition,
                        actor=prepared_attack_spell["actor"],
                        target=beam["target"],
                    )
                    if forced_movement is not None:
                        beam_result["forced_movement"] = forced_movement
                target_resolutions.append(beam_result)

            return {
                "encounter_id": cast_result["encounter_id"],
                "actor_id": request_result["actor_id"],
                "spell_id": cast_result["spell_id"],
                "cast_level": cast_result["cast_level"],
                "resource_update": cast_result.get("slot_consumed"),
                "spell_resolution": {
                    "mode": "attack",
                    "resolution_mode": "attack",
                    "beam_count": prepared_attack_spell["beam_count"],
                    "targets": target_resolutions,
                },
                "encounter_state": self.get_encounter_state.execute(encounter_id),
            }

        if self._is_no_roll_spell(spell_definition):
            return {
                "encounter_id": cast_result["encounter_id"],
                "actor_id": request_result["actor_id"],
                "spell_id": cast_result["spell_id"],
                "cast_level": cast_result["cast_level"],
                "resource_update": cast_result.get("slot_consumed"),
                "spell_resolution": {
                    "mode": "apply_spell_instance",
                    "resolution_mode": "apply_spell_instance",
                    "turn_effect_updates": cast_result.get("turn_effect_updates") or [],
                    "spell_instance": cast_result.get("spell_instance"),
                },
                "encounter_state": self.get_encounter_state.execute(encounter_id),
            }

        return {
            "encounter_id": cast_result["encounter_id"],
            "actor_id": request_result["actor_id"],
            "spell_id": cast_result["spell_id"],
            "cast_level": cast_result["cast_level"],
            "resource_update": cast_result.get("slot_consumed"),
            "spell_resolution": {"mode": "declared_only"},
            "encounter_state": self.get_encounter_state.execute(encounter_id),
        }

    def _is_save_damage_area_spell(self, spell_definition: Any) -> bool:
        if not isinstance(spell_definition, dict):
            return False
        targeting = spell_definition.get("targeting")
        if not isinstance(targeting, dict):
            return False
        if targeting.get("type") != "area_sphere":
            return False
        resolution = spell_definition.get("resolution")
        if not isinstance(resolution, dict):
            return False
        if resolution.get("mode") not in {"save", "save_damage"}:
            return False
        save_ability = spell_definition.get("save_ability")
        if not isinstance(save_ability, str) or not save_ability.strip():
            return False
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            return False
        failed_outcome = on_cast.get("on_failed_save")
        successful_outcome = on_cast.get("on_successful_save")
        if not isinstance(failed_outcome, dict) or not isinstance(successful_outcome, dict):
            return False
        damage_parts = failed_outcome.get("damage_parts")
        return isinstance(damage_parts, list) and len(damage_parts) > 0

    def _is_save_condition_spell(self, spell_definition: Any) -> bool:
        if not isinstance(spell_definition, dict):
            return False
        resolution = spell_definition.get("resolution")
        if not isinstance(resolution, dict):
            return False
        if resolution.get("mode") not in {"save", "save_condition"}:
            return False
        save_ability = spell_definition.get("save_ability")
        if not isinstance(save_ability, str) or not save_ability.strip():
            return False
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            return False
        failed_outcome = on_cast.get("on_failed_save")
        success_outcome = on_cast.get("on_successful_save")
        if not isinstance(failed_outcome, dict) or not isinstance(success_outcome, dict):
            return False
        apply_conditions = failed_outcome.get("apply_conditions")
        apply_turn_effects = failed_outcome.get("apply_turn_effects")
        has_conditions = isinstance(apply_conditions, list) and len(apply_conditions) > 0
        has_turn_effects = isinstance(apply_turn_effects, list) and len(apply_turn_effects) > 0
        return has_conditions or has_turn_effects

    def _is_attack_roll_spell(self, spell_definition: Any) -> bool:
        if not isinstance(spell_definition, dict):
            return False
        resolution = spell_definition.get("resolution")
        if not isinstance(resolution, dict):
            return False
        return resolution.get("mode") == "attack_roll" or bool(spell_definition.get("requires_attack_roll"))

    def _is_heal_spell(self, spell_definition: Any) -> bool:
        if not isinstance(spell_definition, dict):
            return False
        resolution = spell_definition.get("resolution")
        if not isinstance(resolution, dict):
            return False
        return resolution.get("mode") == "heal"

    def _is_no_roll_spell(self, spell_definition: Any) -> bool:
        if not isinstance(spell_definition, dict):
            return False
        resolution = spell_definition.get("resolution")
        if not isinstance(resolution, dict):
            return False
        return resolution.get("mode") == "no_roll"

    def _prepare_heal_spell_resolution(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spell_definition: dict[str, Any],
        target_ids: Any,
        upcast_delta: Any,
    ) -> dict[str, Any]:
        normalized_target_ids = [target_id for target_id in (target_ids or []) if isinstance(target_id, str) and target_id]
        if len(normalized_target_ids) != 1:
            return self._error(
                "invalid_heal_target_count",
                "治疗法术必须指定 1 个目标",
            )

        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")

        healing_rolls = self._build_auto_healing_rolls(
            actor=actor,
            spell_definition=spell_definition,
            upcast_delta=upcast_delta,
        )
        return {
            "ok": True,
            "target_id": normalized_target_ids[0],
            "healing_rolls": healing_rolls,
            "healing_total": healing_rolls["total"],
        }

    def _prepare_save_condition_resolution(
        self,
        *,
        target_ids: Any,
        save_rolls: Any,
    ) -> dict[str, Any]:
        normalized_target_ids: list[str] = []
        seen_target_ids: set[str] = set()
        for raw_target_id in target_ids or []:
            if not isinstance(raw_target_id, str):
                continue
            target_id = raw_target_id.strip()
            if not target_id or target_id in seen_target_ids:
                continue
            seen_target_ids.add(target_id)
            normalized_target_ids.append(target_id)
        try:
            save_roll_index = self._index_save_rolls(save_rolls)
        except ValueError as exc:
            return self._error(
                "invalid_save_rolls",
                "save_rolls 格式不合法",
                detail=str(exc),
            )
        return {
            "ok": True,
            "target_ids": normalized_target_ids,
            "save_roll_index": save_roll_index,
        }

    def _prepare_attack_spell_resolution(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spell_definition: dict[str, Any],
        target_ids: Any,
        resolved_scaling: Any,
        spell_origin_entity_id: Any,
        attack_rolls: Any,
        damage_rolls: Any,
    ) -> dict[str, Any]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        actor = encounter.entities.get(actor_id)
        if actor is None:
            raise ValueError(f"actor '{actor_id}' not found in encounter")
        spell_origin = resolve_gaze_of_two_minds_origin(encounter, actor)
        origin_actor = encounter.entities.get(spell_origin_entity_id) if isinstance(spell_origin_entity_id, str) else None
        if origin_actor is None:
            origin_actor = spell_origin.get("origin_entity") or actor

        normalized_target_ids = [target_id for target_id in (target_ids or []) if isinstance(target_id, str) and target_id]
        beam_count = 1
        if isinstance(resolved_scaling, dict):
            maybe_beam_count = resolved_scaling.get("beam_count")
            if isinstance(maybe_beam_count, int) and maybe_beam_count > 0:
                beam_count = maybe_beam_count

        try:
            attack_roll_entries = self._normalize_attack_roll_entries(
                target_ids=normalized_target_ids,
                attack_rolls=attack_rolls,
            )
        except ValueError as exc:
            return self._error("invalid_attack_rolls", "attack_rolls 格式不合法", detail=str(exc))
        try:
            damage_roll_entries = self._normalize_spell_damage_roll_entries(
                target_ids=normalized_target_ids,
                damage_rolls=damage_rolls,
            )
        except ValueError as exc:
            return self._error("invalid_damage_rolls", "damage_rolls 格式不合法", detail=str(exc))

        beams: list[dict[str, Any]] = []
        for index, target_id in enumerate(normalized_target_ids):
            target = encounter.entities.get(target_id)
            if target is None:
                return self._error("invalid_target", f"目标 {target_id} 不存在", target_id=target_id)
            try:
                self._ensure_attack_spell_target_is_legal(
                    encounter=encounter,
                    actor=origin_actor,
                    target=target,
                    spell_definition=spell_definition,
                )
            except ValueError as exc:
                reason = str(exc)
                if reason == "target_out_of_range":
                    return self._error(
                        "target_out_of_range",
                        f"法术目标 {target_id} 超出射程",
                        target_id=target_id,
                    )
                if reason == "blocked_by_line_of_sight":
                    return self._error(
                        "blocked_by_line_of_sight",
                        f"法术目标 {target_id} 视线被阻挡",
                        target_id=target_id,
                    )
                raise
            beams.append(
                {
                    "beam_index": index + 1,
                    "target_id": target_id,
                    "target": target,
                    "attack_roll": attack_roll_entries[index],
                    "damage_rolls": damage_roll_entries[index],
                }
            )
            if (
                isinstance(attack_roll_entries[index], dict)
                and attack_roll_entries[index]["final_total"] >= target.ac
                and damage_roll_entries[index] is None
            ):
                return self._error(
                    "missing_damage_rolls",
                    f"缺少目标 {target_id} 的伤害骰结果",
                    missing_target_ids=[target_id],
                )

        return {
            "ok": True,
            "beam_count": beam_count,
            "actor": actor,
            "beams": beams,
        }

    def _extract_conditions_applied(self, condition_updates: Any) -> list[str]:
        if not isinstance(condition_updates, list):
            return []
        conditions: list[str] = []
        for item in condition_updates:
            if not isinstance(item, dict):
                continue
            condition = item.get("condition")
            if isinstance(condition, str) and condition.strip():
                conditions.append(condition.strip())
        return conditions

    def _finalize_multi_target_spell_instance(
        self,
        *,
        encounter_id: str,
        spell_definition: Any,
        caster_entity_id: str,
        cast_level: int,
        failed_targets: list[dict[str, Any]],
        temporary_instance_ids: list[str],
    ) -> dict[str, Any] | None:
        if not isinstance(spell_definition, dict):
            return None
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        temporary_instance_id_set = {
            instance_id.strip()
            for instance_id in temporary_instance_ids
            if isinstance(instance_id, str) and instance_id.strip()
        }
        if temporary_instance_id_set:
            encounter.spell_instances = [
                instance
                for instance in encounter.spell_instances
                if not (
                    isinstance(instance, dict)
                    and isinstance(instance.get("instance_id"), str)
                    and instance["instance_id"] in temporary_instance_id_set
                )
            ]

        if not failed_targets:
            self.encounter_repository.save(encounter)
            return None

        caster = encounter.entities.get(caster_entity_id)
        if caster is None:
            raise ValueError(f"caster '{caster_entity_id}' not found in encounter")

        instance_targets: list[dict[str, Any]] = []
        for item in failed_targets:
            if not isinstance(item, dict):
                continue
            target_id = item.get("target_id")
            if not isinstance(target_id, str) or not target_id.strip():
                continue
            applied_conditions = item.get("applied_conditions")
            if not isinstance(applied_conditions, list):
                applied_conditions = []
            turn_effect_ids = item.get("turn_effect_ids")
            if not isinstance(turn_effect_ids, list):
                turn_effect_ids = []
            instance_targets.append(
                {
                    "entity_id": target_id,
                    "applied_conditions": list(applied_conditions),
                    "turn_effect_ids": list(turn_effect_ids),
                }
            )

        if not instance_targets:
            self.encounter_repository.save(encounter)
            return None

        instance = build_spell_instance(
            spell_definition=spell_definition,
            caster=caster,
            cast_level=cast_level,
            targets=instance_targets,
            started_round=encounter.round,
        )
        encounter.spell_instances.append(instance)
        self.encounter_repository.save(encounter)
        return instance

    def _prepare_save_damage_resolution(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spell_id: str,
        spell_definition: dict[str, Any],
        target_point: Any,
        save_rolls: Any,
        damage_rolls: Any,
    ) -> dict[str, Any]:
        if not self._is_valid_target_point(target_point):
            return self._error("invalid_target_point", "area 法术必须提供包含 int x/y 的 target_point")

        try:
            target_ids = self._resolve_area_sphere_target_ids(
                encounter_id=encounter_id,
                actor_id=actor_id,
                spell_definition=spell_definition,
                target_point=target_point,
            )
        except ValueError as exc:
            message = str(exc)
            if "target_point" in message:
                return self._error("invalid_target_point", "area 法术必须提供包含 int x/y 的 target_point")
            return self._error(
                "invalid_area_targeting",
                "区域目标解析失败",
                detail=message,
            )

        try:
            save_roll_index = self._index_save_rolls(save_rolls)
        except ValueError as exc:
            return self._error(
                "invalid_save_rolls",
                "save_rolls 格式不合法",
                detail=str(exc),
            )
        try:
            normalized_damage_rolls = self._normalize_damage_rolls_for_outcome(
                spell_definition=spell_definition,
                damage_rolls=damage_rolls,
            )
        except ValueError as exc:
            return self._error(
                "invalid_damage_rolls",
                "damage_rolls 必须是 int 列表或 dict 列表",
                detail=str(exc),
            )

        return {
            "ok": True,
            "target_ids": target_ids,
            "save_roll_index": save_roll_index,
            "damage_rolls": normalized_damage_rolls,
            "spell_id": spell_id,
        }

    def _normalize_attack_roll_entries(
        self,
        *,
        target_ids: list[str],
        attack_rolls: Any,
    ) -> list[dict[str, Any]]:
        if attack_rolls is None:
            return [None for _ in target_ids]
        if isinstance(attack_rolls, dict):
            duplicate_targets = {target_id for target_id in target_ids if target_ids.count(target_id) > 1}
            if duplicate_targets:
                raise ValueError("duplicate_target_ids_require_list_attack_rolls")
            entries: list[dict[str, Any]] = []
            for target_id in target_ids:
                item = attack_rolls.get(target_id)
                if not isinstance(item, dict):
                    raise ValueError(f"missing_attack_roll_for_target:{target_id}")
                entries.append(self._normalize_attack_roll_item(item))
            return entries
        if isinstance(attack_rolls, list):
            if len(attack_rolls) != len(target_ids):
                raise ValueError("attack_rolls_length_mismatch")
            return [self._normalize_attack_roll_item(item) for item in attack_rolls]
        raise ValueError("attack_rolls must be a dict or list")

    def _normalize_attack_roll_item(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("attack_roll_item_must_be_dict")
        final_total = item.get("final_total")
        if not isinstance(final_total, int):
            raise ValueError("attack_roll.final_total must be int")
        dice_rolls = item.get("dice_rolls")
        if not isinstance(dice_rolls, dict):
            raise ValueError("attack_roll.dice_rolls must be dict")
        return {
            "final_total": final_total,
            "dice_rolls": dice_rolls,
        }

    def _normalize_spell_damage_roll_entries(
        self,
        *,
        target_ids: list[str],
        damage_rolls: Any,
    ) -> list[Any]:
        if isinstance(damage_rolls, dict):
            duplicate_targets = {target_id for target_id in target_ids if target_ids.count(target_id) > 1}
            if duplicate_targets:
                raise ValueError("duplicate_target_ids_require_list_damage_rolls")
            entries: list[Any] = []
            for target_id in target_ids:
                entries.append(damage_rolls.get(target_id))
            return entries
        if isinstance(damage_rolls, list):
            if len(damage_rolls) != len(target_ids):
                raise ValueError("damage_rolls_length_mismatch")
            return list(damage_rolls)
        if damage_rolls is None:
            return [None for _ in target_ids]
        raise ValueError("damage_rolls must be a dict or list")

    def _build_attack_spell_damage_parts(
        self,
        *,
        spell_definition: dict[str, Any],
        resolved_scaling: Any,
        actor_id: str,
        actor: Any,
        target: Any,
    ) -> list[dict[str, Any]]:
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            raise ValueError("spell_definition.on_cast must be a dict")
        on_hit = on_cast.get("on_hit")
        if not isinstance(on_hit, dict):
            raise ValueError("attack spell on_hit must be a dict")
        raw_damage_parts = on_hit.get("damage_parts")
        if not isinstance(raw_damage_parts, list) or not raw_damage_parts:
            raise ValueError("attack spell on_hit.damage_parts must be a non-empty list")

        replace_formula = None
        if isinstance(resolved_scaling, dict):
            maybe_replace_formula = resolved_scaling.get("replace_formula")
            if isinstance(maybe_replace_formula, str) and maybe_replace_formula.strip():
                replace_formula = maybe_replace_formula.strip()

        damage_parts: list[dict[str, Any]] = []
        for index, part in enumerate(raw_damage_parts):
            if not isinstance(part, dict):
                raise ValueError(f"attack spell damage part at index {index} must be a dict")
            formula = part.get("formula")
            if not isinstance(formula, str) or not formula.strip():
                raise ValueError(f"attack spell damage part at index {index} has invalid formula")
            damage_parts.append(
                {
                    "source": str(part.get("source") or f"spell:{spell_definition.get('id')}:on_hit:part_{index}"),
                    "formula": replace_formula if index == 0 and replace_formula is not None else formula.strip(),
                    "damage_type": part.get("damage_type"),
                }
            )

        damage_parts.extend(self._build_target_effect_damage_parts(actor_id=actor_id, target=target))
        damage_parts.extend(
            self._build_warlock_invocation_damage_parts(
                spell_definition=spell_definition,
                actor=actor,
            )
        )
        return damage_parts

    def _build_target_effect_damage_parts(self, *, actor_id: str, target: Any) -> list[dict[str, Any]]:
        raw_effects = getattr(target, "turn_effects", [])
        if not isinstance(raw_effects, list):
            return []

        damage_parts: list[dict[str, Any]] = []
        for effect in raw_effects:
            if not isinstance(effect, dict):
                continue
            if effect.get("source_entity_id") != actor_id:
                continue
            raw_parts = effect.get("attack_bonus_damage_parts")
            if not isinstance(raw_parts, list):
                continue
            effect_id = str(effect.get("effect_id") or "effect")
            for index, part in enumerate(raw_parts):
                if not isinstance(part, dict):
                    raise ValueError(f"turn_effect '{effect_id}' has invalid damage part at index {index}")
                formula = part.get("formula")
                if not isinstance(formula, str) or not formula.strip():
                    raise ValueError(f"turn_effect '{effect_id}' has invalid damage formula at part {index}")
                damage_parts.append(
                    {
                        "source": f"effect:{effect_id}:part_{index}",
                        "formula": formula.strip(),
                        "damage_type": part.get("damage_type"),
                    }
                )
        return damage_parts

    def _build_warlock_invocation_damage_parts(
        self,
        *,
        spell_definition: dict[str, Any],
        actor: Any,
    ) -> list[dict[str, Any]]:
        spell_id = str(spell_definition.get("id") or "").strip().lower()
        if not spell_id:
            return []
        if not has_selected_warlock_invocation(actor, "agonizing_blast", spell_id=spell_id):
            return []

        ability_mods = getattr(actor, "ability_mods", {}) or {}
        charisma_modifier = ability_mods.get("cha", 0)
        if isinstance(charisma_modifier, bool) or not isinstance(charisma_modifier, int):
            charisma_modifier = 0
        return [
            {
                "source": f"warlock:agonizing_blast:{spell_id}",
                "formula": str(charisma_modifier),
                "damage_type": self._infer_primary_damage_type(spell_definition),
            }
        ]

    def _infer_primary_damage_type(self, spell_definition: dict[str, Any]) -> str | None:
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            return None
        on_hit = on_cast.get("on_hit")
        if not isinstance(on_hit, dict):
            return None
        raw_damage_parts = on_hit.get("damage_parts")
        if not isinstance(raw_damage_parts, list) or not raw_damage_parts:
            return None
        first_part = raw_damage_parts[0]
        if not isinstance(first_part, dict):
            return None
        damage_type = first_part.get("damage_type")
        return damage_type if isinstance(damage_type, str) and damage_type.strip() else None

    def _resolve_attack_spell_on_hit_forced_movement(
        self,
        *,
        encounter_id: str,
        spell_definition: dict[str, Any],
        actor: Any,
        target: Any,
    ) -> dict[str, Any] | None:
        spell_id = str(spell_definition.get("id") or "").strip().lower()
        if spell_id and has_selected_warlock_invocation(actor, "repelling_blast", spell_id=spell_id):
            forced_movement = self._resolve_linear_push(
                encounter_id=encounter_id,
                actor=actor,
                target=target,
                steps=2,
                reason="warlock_repelling_blast",
            )
            if forced_movement.get("status") == "resolved":
                return forced_movement
        return None

    def _resolve_linear_push(
        self,
        *,
        encounter_id: str,
        actor: Any,
        target: Any,
        steps: int,
        reason: str,
    ) -> dict[str, Any]:
        if str(getattr(target, "size", "medium")).lower() not in {"tiny", "small", "medium", "large"}:
            return {"status": "no_effect", "reason": "target_too_large"}

        path = self._build_push_path(actor=actor, target=target, steps=steps)
        forced_result = self.resolve_forced_movement.execute(
            encounter_id=encounter_id,
            entity_id=target.entity_id,
            path=path,
            reason=reason,
            source_entity_id=actor.entity_id,
        )
        return {
            "status": "resolved",
            "target_entity_id": target.entity_id,
            "target_name": target.name,
            "start_position": forced_result["start_position"],
            "final_position": forced_result["final_position"],
            "attempted_path": forced_result["attempted_path"],
            "resolved_path": forced_result["resolved_path"],
            "moved_feet": forced_result["moved_feet"],
            "blocked": forced_result["blocked"],
            "block_reason": forced_result["block_reason"],
            "reason": forced_result["reason"],
        }

    def _build_push_path(self, *, actor: Any, target: Any, steps: int) -> list[dict[str, int]]:
        actor_center = get_center_position(actor)
        target_center = get_center_position(target)
        dx = self._normalize_axis_delta(target_center["x"] - actor_center["x"])
        dy = self._normalize_axis_delta(target_center["y"] - actor_center["y"])
        if dx == 0 and dy == 0:
            dx = 1

        anchor = {"x": target.position["x"], "y": target.position["y"]}
        path: list[dict[str, int]] = []
        for _ in range(max(0, steps)):
            anchor = {"x": anchor["x"] + dx, "y": anchor["y"] + dy}
            path.append(dict(anchor))
        return path

    def _normalize_axis_delta(self, value: float) -> int:
        if value > 0:
            return 1
        if value < 0:
            return -1
        return 0

    def _index_damage_rolls_for_spell_target(
        self,
        *,
        expected_sources: list[str],
        damage_rolls: Any,
    ) -> dict[str, list[int]]:
        if isinstance(damage_rolls, list) and all(isinstance(item, int) for item in damage_rolls):
            if len(expected_sources) != 1:
                raise ValueError("simple_damage_roll_list_requires_single_damage_part")
            return {expected_sources[0]: damage_rolls}

        if isinstance(damage_rolls, list):
            indexed: dict[str, list[int]] = {}
            for item in damage_rolls:
                if not isinstance(item, dict):
                    raise ValueError("damage_roll_item_must_be_dict")
                source = item.get("source")
                if not isinstance(source, str) or not source.strip():
                    raise ValueError("damage_roll_source_must_be_non_empty_string")
                rolls = item.get("rolls")
                if not isinstance(rolls, list) or not all(isinstance(roll, int) for roll in rolls):
                    raise ValueError("damage_roll.rolls must be int list")
                indexed[source] = rolls
            missing_sources = [source for source in expected_sources if source not in indexed]
            if missing_sources:
                raise ValueError(f"missing_damage_roll_sources:{','.join(missing_sources)}")
            unknown_sources = [source for source in indexed if source not in set(expected_sources)]
            if unknown_sources:
                raise ValueError(f"unknown_damage_roll_sources:{','.join(unknown_sources)}")
            return indexed

        raise ValueError("damage_rolls_per_target must be int list or source-indexed dict list")

    def _ensure_attack_spell_target_is_legal(
        self,
        *,
        encounter: Any,
        actor: Any,
        target: Any,
        spell_definition: dict[str, Any],
    ) -> None:
        targeting = spell_definition.get("targeting")
        if not isinstance(targeting, dict):
            return

        range_feet = targeting.get("range_feet")
        if isinstance(range_feet, int) and range_feet > 0:
            distance_feet = self._distance_feet(actor, target)
            if distance_feet > range_feet:
                raise ValueError("target_out_of_range")

        if bool(targeting.get("requires_line_of_sight")):
            self._ensure_line_of_sight(encounter=encounter, actor=actor, target=target)

    def _distance_feet(self, source: Any, target: Any) -> int:
        source_center = get_center_position(source)
        target_center = get_center_position(target)
        dx = abs(source_center["x"] - target_center["x"])
        dy = abs(source_center["y"] - target_center["y"])
        return math.ceil(max(dx, dy)) * 5

    def _ensure_line_of_sight(self, *, encounter: Any, actor: Any, target: Any) -> None:
        blocking_cells = {
            (terrain["x"], terrain["y"])
            for terrain in encounter.map.terrain
            if isinstance(terrain.get("x"), int)
            and isinstance(terrain.get("y"), int)
            and (terrain.get("blocks_los") or terrain.get("type") == "wall")
        }
        if not blocking_cells:
            return

        actor_cells = get_occupied_cells(actor)
        target_cells = get_occupied_cells(target)
        source = get_center_position(actor)
        destination = get_center_position(target)
        steps = max(int(math.ceil(max(abs(destination["x"] - source["x"]), abs(destination["y"] - source["y"])) * 4)), 1)

        for index in range(1, steps):
            ratio = index / steps
            sample_x = source["x"] + (destination["x"] - source["x"]) * ratio
            sample_y = source["y"] + (destination["y"] - source["y"]) * ratio
            cell = (math.floor(sample_x + 0.5), math.floor(sample_y + 0.5))
            if cell in actor_cells or cell in target_cells:
                continue
            if cell in blocking_cells:
                raise ValueError("blocked_by_line_of_sight")

    def _resolve_area_sphere_target_ids(
        self,
        *,
        encounter_id: str,
        actor_id: str,
        spell_definition: dict[str, Any],
        target_point: dict[str, Any],
    ) -> list[str]:
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        targeting = spell_definition.get("targeting", {})
        radius_feet = targeting.get("radius_feet")
        if not isinstance(radius_feet, int) or radius_feet < 0:
            raise ValueError("area_sphere spell requires integer radius_feet >= 0")
        allowed_target_types = self._normalize_allowed_target_types(targeting.get("allowed_target_types"))
        covered_cells = collect_circle_cells(
            map_width=encounter.map.width,
            map_height=encounter.map.height,
            target_point=target_point,
            radius_feet=radius_feet,
            grid_size_feet=encounter.map.grid_size_feet,
        )

        target_ids: list[str] = []
        for entity_id in collect_entities_in_cells(encounter=encounter, covered_cells=covered_cells):
            if entity_id == actor_id:
                continue
            entity = encounter.entities.get(entity_id)
            if entity is None:
                continue
            if not self._is_allowed_area_target(entity=entity, allowed_target_types=allowed_target_types):
                continue
            target_ids.append(entity_id)
        return target_ids

    def _store_spell_area_overlay(
        self,
        *,
        encounter_id: str,
        spell_definition: dict[str, Any] | None,
        target_point: Any,
    ) -> None:
        if not isinstance(spell_definition, dict):
            return
        if not self._is_valid_target_point(target_point):
            return
        area_template = spell_definition.get("area_template")
        if not isinstance(area_template, dict):
            return
        radius_feet = area_template.get("radius_feet")
        if not isinstance(radius_feet, int) or radius_feet <= 0:
            return
        encounter = self.encounter_repository.get(encounter_id)
        if encounter is None:
            return
        localization = spell_definition.get("localization")
        spell_name = spell_definition.get("name") or spell_definition.get("id") or "未知法术"
        if isinstance(localization, dict):
            spell_name = localization.get("name_zh") or spell_name
        overlay = build_spell_area_overlay(
            overlay_id=f"overlay_spell_{uuid4().hex[:12]}",
            spell_id=str(spell_definition.get("id") or spell_definition.get("spell_id") or ""),
            spell_name=str(spell_name),
            target_point=target_point,
            radius_feet=radius_feet,
            grid_size_feet=encounter.map.grid_size_feet,
            persistence=str(area_template.get("persistence") or "instant"),
        )
        notes = [
            note
            for note in encounter.encounter_notes
            if not (isinstance(note, dict) and note.get("type") == "spell_area_overlay")
        ]
        notes.append(
            {
                "type": "spell_area_overlay",
                "payload": overlay,
            }
        )
        encounter.encounter_notes = notes
        self.encounter_repository.save(encounter)

    def _normalize_allowed_target_types(self, raw_allowed_target_types: Any) -> set[str]:
        if not isinstance(raw_allowed_target_types, list):
            return set()
        return {str(item).strip().lower() for item in raw_allowed_target_types if isinstance(item, str)}

    def _is_allowed_area_target(self, *, entity: Any, allowed_target_types: set[str]) -> bool:
        if not allowed_target_types:
            return True
        resolved_entity_type = self._resolve_entity_type(entity=entity)
        if "creature" in allowed_target_types:
            return self._is_creature_target(entity=entity, resolved_entity_type=resolved_entity_type)
        if isinstance(resolved_entity_type, str) and resolved_entity_type in allowed_target_types:
            return True
        if "humanoid" in allowed_target_types:
            return self._is_humanoid_target(entity=entity, resolved_entity_type=resolved_entity_type)
        return False

    def _is_creature_target(self, *, entity: Any, resolved_entity_type: str | None) -> bool:
        non_creature_types = {"object", "hazard", "terrain", "trap", "zone", "effect", "environment"}
        if isinstance(resolved_entity_type, str):
            return resolved_entity_type not in non_creature_types
        category = getattr(entity, "category", None)
        if isinstance(category, str) and category.strip().lower() in {"pc", "npc", "monster", "summon"}:
            return True
        return False

    def _is_humanoid_target(self, *, entity: Any, resolved_entity_type: str | None) -> bool:
        if resolved_entity_type == "humanoid":
            return True
        category = getattr(entity, "category", None)
        if isinstance(category, str):
            return category.strip().lower() in {"pc", "npc"}
        return False

    def _resolve_entity_type(self, *, entity: Any) -> str | None:
        source_ref = getattr(entity, "source_ref", None)
        if isinstance(source_ref, dict):
            for key in ("entity_type", "creature_type", "monster_type", "target_type"):
                raw_value = source_ref.get(key)
                if isinstance(raw_value, str) and raw_value.strip():
                    return raw_value.strip().lower()
        return None

    def _is_valid_target_point(self, target_point: Any) -> bool:
        if not isinstance(target_point, dict):
            return False
        return self._is_int_coordinate(target_point.get("x")) and self._is_int_coordinate(target_point.get("y"))

    def _is_int_coordinate(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    def _error(self, error_code: str, message: str, **extra: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error_code": error_code,
            "message": message,
        }
        payload.update(extra)
        return payload

    def _index_save_rolls(self, save_rolls: Any) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        if isinstance(save_rolls, dict):
            for target_id, value in save_rolls.items():
                if not isinstance(target_id, str) or not target_id.strip():
                    continue
                normalized = self._normalize_single_save_roll(value)
                if normalized is not None:
                    indexed[target_id] = normalized
            return indexed

        if not isinstance(save_rolls, list):
            return indexed

        for item in save_rolls:
            if not isinstance(item, dict):
                continue
            target_id = item.get("target_id")
            if not isinstance(target_id, str) or not target_id.strip():
                continue
            normalized = self._normalize_single_save_roll(item)
            if normalized is not None:
                indexed[target_id] = normalized
        return indexed

    def _normalize_single_save_roll(self, raw: Any) -> dict[str, Any] | None:
        if isinstance(raw, int):
            return {"base_roll": raw}
        if isinstance(raw, list):
            return {"base_rolls": raw}
        if not isinstance(raw, dict):
            return None
        if "base_roll" in raw and "base_rolls" in raw:
            raise ValueError("save_roll cannot contain both base_roll and base_rolls")
        if "base_roll" in raw:
            return {
                "base_roll": raw.get("base_roll"),
                "additional_bonus": raw.get("additional_bonus", 0),
                "voluntary_fail": raw.get("voluntary_fail", False),
                "vantage": raw.get("vantage", "normal"),
            }
        if "base_rolls" in raw:
            return {
                "base_rolls": raw.get("base_rolls"),
                "additional_bonus": raw.get("additional_bonus", 0),
                "voluntary_fail": raw.get("voluntary_fail", False),
                "vantage": raw.get("vantage", "normal"),
            }
        return None

    def _normalize_damage_rolls_for_outcome(
        self,
        *,
        spell_definition: dict[str, Any],
        damage_rolls: Any,
    ) -> list[dict[str, Any]] | None:
        if damage_rolls is None:
            return None
        if isinstance(damage_rolls, list) and all(isinstance(item, dict) for item in damage_rolls):
            return damage_rolls
        if isinstance(damage_rolls, list) and all(isinstance(item, int) for item in damage_rolls):
            source = self._resolve_primary_failed_damage_source(spell_definition)
            return [{"source": source, "rolls": damage_rolls}]
        raise ValueError("damage_rolls must be a list of int or a list of dict")

    def _resolve_primary_failed_damage_source(self, spell_definition: dict[str, Any]) -> str:
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            raise ValueError("spell_definition.on_cast must be a dict")
        failed_outcome = on_cast.get("on_failed_save")
        if not isinstance(failed_outcome, dict):
            raise ValueError("spell_definition.on_cast.on_failed_save must be a dict")
        damage_parts = failed_outcome.get("damage_parts")
        if not isinstance(damage_parts, list) or not damage_parts:
            raise ValueError("spell_definition.on_cast.on_failed_save.damage_parts must be a non-empty list")
        first_part = damage_parts[0]
        if not isinstance(first_part, dict):
            raise ValueError("failed_save damage part must be a dict")
        source = first_part.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("failed_save damage part source must be a non-empty string")
        return source

    def _build_auto_save_roll_input(self, *, vantage: Any) -> dict[str, Any]:
        normalized_vantage = vantage if isinstance(vantage, str) else "normal"
        if normalized_vantage in {"advantage", "disadvantage"}:
            return {
                "base_rolls": [random.randint(1, 20), random.randint(1, 20)],
                "vantage": normalized_vantage,
            }
        return {
            "base_roll": random.randint(1, 20),
            "vantage": "normal",
        }

    def _build_auto_attack_roll_entry(self, *, actor: Any) -> dict[str, Any]:
        modifier = self._resolve_spell_attack_modifier(actor=actor)
        base_roll = random.randint(1, 20)
        return {
            "final_total": base_roll + modifier,
            "dice_rolls": {
                "base_rolls": [base_roll],
                "chosen_roll": base_roll,
                "modifier": modifier,
            },
        }

    def _build_auto_healing_rolls(
        self,
        *,
        actor: Any,
        spell_definition: dict[str, Any],
        upcast_delta: Any,
    ) -> dict[str, Any]:
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            raise ValueError("spell_definition.on_cast must be a dict")
        healing_parts = on_cast.get("healing_parts")
        if not isinstance(healing_parts, list) or not healing_parts:
            raise ValueError("spell_definition.on_cast.healing_parts must be a non-empty list")

        base_rolls: list[int] = []
        scaling_rolls: list[int] = []
        total = 0
        spellcasting_modifier = self._resolve_spellcasting_modifier(actor=actor)

        for part in healing_parts:
            if not isinstance(part, dict):
                continue
            formula = str(part.get("formula") or "").strip()
            dice_count, die_size = self._parse_damage_formula(formula)
            rolls = [random.randint(1, die_size) for _ in range(dice_count)]
            base_rolls.extend(rolls)
            total += sum(rolls)
            if bool(part.get("include_spellcasting_modifier")):
                total += spellcasting_modifier

        scaling = spell_definition.get("scaling")
        slot_level_bonus = scaling.get("slot_level_bonus") if isinstance(scaling, dict) else None
        additional_healing_parts = slot_level_bonus.get("additional_healing_parts") if isinstance(slot_level_bonus, dict) else None
        normalized_upcast_delta = upcast_delta if isinstance(upcast_delta, int) and upcast_delta > 0 else 0
        if isinstance(additional_healing_parts, list) and normalized_upcast_delta > 0:
            for part in additional_healing_parts:
                if not isinstance(part, dict):
                    continue
                formula_per_extra_level = str(part.get("formula_per_extra_level") or "").strip()
                dice_count, die_size = self._parse_damage_formula(formula_per_extra_level)
                for _ in range(normalized_upcast_delta):
                    rolls = [random.randint(1, die_size) for _ in range(dice_count)]
                    scaling_rolls.extend(rolls)
                    total += sum(rolls)

        return {
            "base_rolls": base_rolls,
            "scaling_rolls": scaling_rolls,
            "spellcasting_modifier": spellcasting_modifier,
            "total": total,
        }

    def _resolve_spell_attack_modifier(self, *, actor: Any) -> int:
        source_ref = getattr(actor, "source_ref", None)
        if not isinstance(source_ref, dict):
            raise ValueError("caster.source_ref is required to calculate spell attack modifier")
        spellcasting_ability = source_ref.get("spellcasting_ability")
        if not isinstance(spellcasting_ability, str) or not spellcasting_ability.strip():
            raise ValueError("caster.source_ref.spellcasting_ability is required to calculate spell attack modifier")
        ability_modifier = getattr(actor, "ability_mods", {}).get(spellcasting_ability)
        if not isinstance(ability_modifier, int):
            raise ValueError(f"ability_mods['{spellcasting_ability}'] is required to calculate spell attack modifier")
        proficiency_bonus = getattr(actor, "proficiency_bonus", 0)
        if not isinstance(proficiency_bonus, int):
            proficiency_bonus = 0
        return ability_modifier + proficiency_bonus

    def _resolve_spellcasting_modifier(self, *, actor: Any) -> int:
        source_ref = getattr(actor, "source_ref", None)
        if not isinstance(source_ref, dict):
            return 0
        spellcasting_ability = source_ref.get("spellcasting_ability")
        if not isinstance(spellcasting_ability, str) or not spellcasting_ability.strip():
            return 0
        ability_modifier = getattr(actor, "ability_mods", {}).get(spellcasting_ability)
        if not isinstance(ability_modifier, int):
            return 0
        return ability_modifier

    def _build_auto_damage_rolls_from_parts(
        self,
        *,
        damage_parts: list[dict[str, Any]],
        is_critical_hit: bool,
    ) -> list[dict[str, Any]]:
        auto_rolls: list[dict[str, Any]] = []
        for part in damage_parts:
            formula = str(part.get("formula") or "").strip()
            dice_count, die_size = self._parse_damage_formula(formula)
            effective_dice_count = dice_count * 2 if is_critical_hit else dice_count
            auto_rolls.append(
                {
                    "source": part.get("source"),
                    "rolls": [random.randint(1, die_size) for _ in range(effective_dice_count)],
                }
            )
        return auto_rolls

    def _build_auto_outcome_damage_rolls(
        self,
        *,
        spell_definition: dict[str, Any],
        outcome_key: str,
        is_critical_hit: bool,
    ) -> list[dict[str, Any]]:
        on_cast = spell_definition.get("on_cast")
        if not isinstance(on_cast, dict):
            raise ValueError("spell_definition.on_cast must be a dict")
        outcome = on_cast.get(outcome_key)
        if not isinstance(outcome, dict):
            raise ValueError(f"spell_definition.on_cast.{outcome_key} must be a dict")
        raw_damage_parts = outcome.get("damage_parts")
        if not isinstance(raw_damage_parts, list) or not raw_damage_parts:
            raise ValueError(f"spell_definition.on_cast.{outcome_key}.damage_parts must be a non-empty list")

        damage_parts: list[dict[str, Any]] = []
        for index, part in enumerate(raw_damage_parts):
            if not isinstance(part, dict):
                raise ValueError(f"{outcome_key} damage part at index {index} must be a dict")
            formula = str(part.get("formula") or "").strip()
            damage_parts.append(
                {
                    "source": str(part.get("source") or f"spell:{spell_definition.get('id')}:{outcome_key}:part_{index}"),
                    "formula": formula,
                    "damage_type": part.get("damage_type"),
                }
            )

        return self._build_auto_damage_rolls_from_parts(
            damage_parts=damage_parts,
            is_critical_hit=is_critical_hit,
        )

    def _parse_damage_formula(self, formula: str) -> tuple[int, int]:
        match = self._FORMULA_RE.match(formula)
        if match is None:
            raise ValueError("invalid_damage_formula")
        dice_count = int(match.group(1))
        die_size = int(match.group(2))
        if dice_count <= 0 or die_size <= 0:
            raise ValueError("invalid_damage_formula")
        return dice_count, die_size
