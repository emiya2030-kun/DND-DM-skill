from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.services.combat.attack.attack_roll_request import AttackRollRequest
from tools.services.combat.attack.attack_roll_result import AttackRollResult
from tools.services.combat.attack.weapon_mastery_effects import (
    apply_weapon_mastery_on_hit,
    consume_attack_roll_weapon_mastery_effects,
    get_weapon_mastery_speed_penalty,
    resolve_linear_push,
)
from tools.services.combat.actions import remove_turn_effect_by_id
from tools.services.class_features.shared import (
    add_or_refresh_studied_attack_mark,
    consume_studied_attack_mark,
    ensure_paladin_runtime,
    ensure_rogue_runtime,
    fighter_has_studied_attacks,
    get_class_runtime,
    get_monk_runtime,
    has_fighting_style,
    resolve_entity_save_proficiencies,
    resolve_extra_attack_count,
)
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow
from tools.services.combat.damage import ResolveDamageParts
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.resolve_forced_movement import ResolveForcedMovement
from tools.services.class_features.barbarian.runtime import ensure_barbarian_runtime

if TYPE_CHECKING:
    from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository
    from tools.services.combat.rules.reactions.open_reaction_window import OpenReactionWindow


class ExecuteAttack:
    """把一次完整武器攻击流程收口成一个统一入口。"""

    _FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")
    _FLAT_DAMAGE_RE = re.compile(r"^[+]?(\d+)$")

    def __init__(
        self,
        attack_roll_request: AttackRollRequest,
        attack_roll_result: AttackRollResult,
        update_hp: UpdateHp | None = None,
        resolve_damage_parts: ResolveDamageParts | None = None,
        open_reaction_window: "OpenReactionWindow" | None = None,
        definition_repository: "ReactionDefinitionRepository" | None = None,
    ):
        self.attack_roll_request = attack_roll_request
        self.attack_roll_result = attack_roll_result
        if update_hp is not None and attack_roll_result.update_hp is None:
            attack_roll_result.update_hp = update_hp
        self.update_hp = attack_roll_result.update_hp or update_hp
        self.resolve_damage_parts = resolve_damage_parts or ResolveDamageParts()
        self.resolve_saving_throw = ResolveSavingThrow(self.attack_roll_request.encounter_repository)
        self.resolve_forced_movement = ResolveForcedMovement(
            self.attack_roll_request.encounter_repository,
            self.attack_roll_result.append_event,
        )
        if open_reaction_window is None:
            from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository
            from tools.services.combat.rules.reactions.open_reaction_window import OpenReactionWindow

            definition_repository = definition_repository or ReactionDefinitionRepository()
            open_reaction_window = OpenReactionWindow(self.attack_roll_request.encounter_repository, definition_repository)
        self.open_reaction_window = open_reaction_window
        self._validate_repository_dependencies()

    def execute(
        self,
        *,
        encounter_id: str,
        actor_id: str | None = None,
        target_id: str,
        weapon_id: str,
        final_total: int | None = None,
        dice_rolls: dict[str, Any] | None = None,
        damage_rolls: list[dict[str, Any]] | None = None,
        vantage: str = "normal",
        description: str | None = None,
        attack_mode: str | None = None,
        grip_mode: str | None = None,
        hp_change: int | None = None,
        damage_reason: str | None = None,
        damage_type: str | None = None,
        zero_hp_intent: str | None = None,
        concentration_vantage: str = "normal",
        include_encounter_state: bool = False,
        consume_action: bool = True,
        consume_reaction: bool = False,
        allow_out_of_turn_actor: bool = False,
        mastery_override: str | None = None,
        mastery_rolls: dict[str, Any] | None = None,
        class_feature_options: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
        host_action_id: str | None = None,
        pending_flat_damage_reduction: int | None = None,
        pending_damage_multiplier: float | None = None,
        skip_reaction_window: bool = False,
    ) -> dict[str, Any]:
        """执行一次完整攻击。

        这里的职责是流程编排：
        1. 先根据当前 encounter 生成攻击请求
        2. 再用外部传入的最终掷骰结果组装 RollResult
        3. 最后调用攻击结算，必要时自动接上 HP 更新

        这样做的目的是把 LLM 侧需要串联的步骤收拢到一个入口，
        但底层服务仍然保持可单独测试、可单独复用。
        """
        normalized_attack_mode = str(attack_mode or "default").lower()
        effective_consume_action = consume_action
        effective_consume_bonus_action = False
        if normalized_attack_mode == "light_bonus":
            effective_consume_action = False
            effective_consume_bonus_action = True
        elif normalized_attack_mode in {"martial_arts_bonus", "flurry_of_blows"}:
            effective_consume_action = False
            effective_consume_bonus_action = True

        try:
            request = self.attack_roll_request.execute(
                encounter_id=encounter_id,
                actor_id=actor_id,
                target_id=target_id,
                weapon_id=weapon_id,
                allow_out_of_turn_actor=allow_out_of_turn_actor,
                require_action_available=effective_consume_action,
                vantage=vantage,
                description=description,
                attack_mode=attack_mode,
                grip_mode=grip_mode,
                class_feature_options=class_feature_options,
            )
        except ValueError as error:
            if not self._is_structured_invalid_attack_error(error):
                raise
            return self._build_invalid_attack_result(
                encounter_id=encounter_id,
                actor_id=actor_id,
                target_id=target_id,
                weapon_id=weapon_id,
                error=error,
            )

        self._consume_next_attack_advantage_turn_effects(
            encounter_id=encounter_id,
            target_entity_id=request.target_entity_id,
            effect_ids=request.context.get("next_attack_advantage_turn_effect_ids"),
        )

        self._apply_tactical_master_override(
            encounter_id=encounter_id,
            actor_entity_id=request.actor_entity_id,
            attack_context=request.context,
            mastery_override=mastery_override,
        )

        if normalized_attack_mode == "light_bonus":
            effective_consume_bonus_action = bool(request.context.get("light_bonus_uses_bonus_action", True))

        resolved_attack_roll = self._resolve_attack_roll(
            attack_context=request.context,
            final_total=final_total,
            dice_rolls=dice_rolls,
        )

        target_ac = request.context.get("target_ac")
        attack_hits = isinstance(target_ac, int) and resolved_attack_roll["final_total"] >= target_ac
        if not consume_reaction and not skip_reaction_window and attack_hits:
            attack_id = host_action_id or f"atk_{uuid4().hex[:12]}"
            trigger_event = {
                "event_id": f"evt_attack_declared_{uuid4().hex[:12]}",
                "trigger_type": "attack_declared",
                "host_action_type": "attack",
                "host_action_id": attack_id,
                "host_action_snapshot": {
                    "attack_id": attack_id,
                    "actor_id": request.actor_entity_id,
                    "target_id": request.target_entity_id,
                    "weapon_id": weapon_id,
                    "attack_mode": normalized_attack_mode,
                    "grip_mode": grip_mode or "default",
                    "attack_total": resolved_attack_roll["final_total"],
                    "target_ac_before_reaction": target_ac,
                    "vantage": request.context["vantage"],
                    "phase": "before_hit_locked",
                    "final_total": resolved_attack_roll["final_total"],
                    "dice_rolls": resolved_attack_roll["dice_rolls"],
                    "damage_rolls": damage_rolls,
                    "description": description,
                    "allow_out_of_turn_actor": allow_out_of_turn_actor,
                    "consume_action": effective_consume_action,
                    "consume_reaction": consume_reaction,
                    "primary_damage_type": request.context.get("primary_damage_type"),
                },
                "target_entity_id": request.target_entity_id,
                "request_payloads": {
                    request.target_entity_id: {
                        "primary_damage_type": request.context.get("primary_damage_type"),
                        "source_actor_id": request.actor_entity_id,
                        "weapon_id": weapon_id,
                    }
                },
            }
            window_result = self.open_reaction_window.execute(encounter_id=encounter_id, trigger_event=trigger_event)
            if window_result["status"] == "waiting_reaction":
                return {
                    "status": "waiting_reaction",
                    "pending_reaction_window": window_result["pending_reaction_window"],
                    "reaction_requests": window_result["reaction_requests"],
                    "encounter_state": GetEncounterState(self.attack_roll_request.encounter_repository).execute(
                        encounter_id
                    ),
                }

        roll_result = RollResult(
            request_id=request.request_id,
            encounter_id=request.encounter_id,
            actor_entity_id=request.actor_entity_id,
            target_entity_id=request.target_entity_id,
            roll_type=request.roll_type,
            final_total=resolved_attack_roll["final_total"],
            dice_rolls=resolved_attack_roll["dice_rolls"],
            metadata=metadata or {},
            rolled_at=rolled_at,
        )

        force_critical_on_hit = bool(request.context.get("melee_auto_crit"))

        use_structured_damage = self._should_use_structured_damage(
            damage_rolls=damage_rolls,
            hp_change=hp_change,
            damage_reason=damage_reason,
            damage_type=damage_type,
        )
        prepared_damage_resolution: dict[str, Any] | None = None
        if use_structured_damage:
            prepared_damage_resolution = self._prepare_structured_damage(
                encounter_id=encounter_id,
                actor_entity_id=request.actor_entity_id,
                target_id=target_id,
                weapon_id=weapon_id,
                attack_context=request.context,
                final_total=resolved_attack_roll["final_total"],
                roll_result=roll_result,
                damage_rolls=damage_rolls,
                force_critical_on_hit=force_critical_on_hit,
            )

        resolution = self.attack_roll_result.execute(
            encounter_id=encounter_id,
            roll_result=roll_result,
            attack_name=request.context.get("attack_name"),
            attack_kind=request.context.get("attack_kind"),
            hp_change=None,
            damage_reason=None,
            damage_type=None,
            force_critical_on_hit=force_critical_on_hit,
            concentration_vantage=concentration_vantage,
            enforce_current_turn_actor=not allow_out_of_turn_actor,
        )
        self._consume_help_attack_effect(
            encounter_id=encounter_id,
            target_entity_id=request.target_entity_id,
            effect_id=request.context.get("consumed_help_attack_effect_id"),
        )
        if resolution["hit"] and use_structured_damage:
            if prepared_damage_resolution is None:
                raise ValueError("structured_damage_resolution_missing")
            damage_resolution = prepared_damage_resolution
            deflect_result = self._apply_deflect_attacks_pending_effect(
                encounter_id=encounter_id,
                target_entity_id=target_id,
                host_action_id=host_action_id,
                damage_resolution=damage_resolution,
            )
            if deflect_result is not None:
                resolution["deflect_attacks"] = deflect_result
            interception_result = self._apply_pending_flat_damage_reduction(
                damage_resolution=damage_resolution,
                pending_flat_damage_reduction=pending_flat_damage_reduction,
            )
            if interception_result is not None:
                resolution["interception"] = interception_result
            uncanny_dodge_result = self._apply_pending_damage_multiplier(
                damage_resolution=damage_resolution,
                damage_multiplier=pending_damage_multiplier,
            )
            if uncanny_dodge_result is not None:
                resolution["uncanny_dodge"] = uncanny_dodge_result
            resolution["damage_resolution"] = damage_resolution
            if damage_resolution.get("total_damage", 0):
                resolution["hp_update"] = self._apply_resolved_damage(
                    encounter_id=encounter_id,
                    target_id=target_id,
                    source_entity_id=request.actor_entity_id,
                    attack_name=request.context.get("attack_name") or "Attack",
                    damage_resolution=damage_resolution,
                    is_critical_hit=resolution["is_critical_hit"],
                    concentration_vantage=concentration_vantage,
                    zero_hp_intent=zero_hp_intent,
                    attack_kind=request.context.get("attack_kind"),
                )
        elif resolution["hit"] and hp_change is not None:
            resolution["hp_update"] = self._apply_legacy_damage(
                encounter_id=encounter_id,
                target_id=target_id,
                source_entity_id=request.actor_entity_id,
                attack_name=request.context.get("attack_name") or "Attack",
                hp_change=self._apply_legacy_damage_multiplier(
                    hp_change=hp_change,
                    damage_multiplier=pending_damage_multiplier,
                ),
                damage_reason=damage_reason,
                damage_type=damage_type,
                is_critical_hit=resolution["is_critical_hit"],
                concentration_vantage=concentration_vantage,
                zero_hp_intent=zero_hp_intent,
                attack_kind=request.context.get("attack_kind"),
            )

        cunning_strike_result = self._apply_cunning_strike_effects(
            encounter_id=encounter_id,
            actor_entity_id=request.actor_entity_id,
            target_entity_id=target_id,
            attack_context=request.context,
            resolution=resolution,
        )
        if cunning_strike_result is not None:
            resolution["cunning_strike"] = cunning_strike_result

        mastery_updates = self._apply_weapon_mastery_updates(
            encounter_id=encounter_id,
            actor_entity_id=request.actor_entity_id,
            target_id=target_id,
            attack_context=request.context,
            resolution=resolution,
            mastery_rolls=mastery_rolls,
            resolve_forced_movement=self.resolve_forced_movement,
        )
        graze_update = mastery_updates.get("graze")
        if isinstance(graze_update, dict) and graze_update.get("status") == "resolved":
            resolution["hp_update"] = self.update_hp.execute(
                encounter_id=encounter_id,
                target_id=target_id,
                hp_change=int(graze_update.get("damage", 0) or 0),
                reason=f"{request.context.get('attack_name') or 'Attack'} graze damage",
                damage_type=graze_update.get("damage_type"),
                from_critical_hit=False,
                source_entity_id=request.actor_entity_id,
                attack_kind=request.context.get("attack_kind"),
                zero_hp_intent=zero_hp_intent,
                concentration_vantage=concentration_vantage,
            )
        if any(value for value in mastery_updates.values()):
            resolution["weapon_mastery_updates"] = mastery_updates

        self._apply_studied_attacks_updates(
            encounter_id=encounter_id,
            actor_entity_id=request.actor_entity_id,
            target_entity_id=request.target_entity_id,
            hit=bool(resolution.get("hit")),
            studied_attacks_applied=bool(request.context.get("studied_attacks_applied")),
        )
        self._apply_stunning_strike_updates(
            encounter_id=encounter_id,
            actor_entity_id=request.actor_entity_id,
            target_entity_id=request.target_entity_id,
            attack_context=request.context,
            resolution=resolution,
        )
        self._apply_barbarian_brutal_strike_updates(
            encounter_id=encounter_id,
            actor_entity_id=request.actor_entity_id,
            target_entity_id=request.target_entity_id,
            attack_context=request.context,
            resolution=resolution,
        )

        self._mark_attack_resource_used(
            encounter_id=encounter_id,
            actor_entity_id=request.actor_entity_id,
            target_entity_id=request.target_entity_id,
            weapon_id=weapon_id,
            attack_context=request.context,
            resolution=resolution,
            consume_action=effective_consume_action,
            consume_bonus_action=effective_consume_bonus_action,
            consume_reaction=consume_reaction,
        )

        result = {
            "request": request.to_dict(),
            "roll_result": roll_result.to_dict(),
            "resolution": resolution,
        }
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.attack_roll_request.encounter_repository).execute(encounter_id)
        return result

    def _apply_studied_attacks_updates(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str,
        hit: bool,
        studied_attacks_applied: bool,
    ) -> None:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while applying studied attacks")
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError(
                f"actor '{actor_entity_id}' not part of encounter '{encounter_id}' while applying studied attacks"
            )

        class_features = actor.class_features if isinstance(actor.class_features, dict) else {}
        if not fighter_has_studied_attacks(class_features):
            return

        changed = False
        if studied_attacks_applied:
            changed = consume_studied_attack_mark(class_features, target_entity_id) or changed
        if not hit:
            add_or_refresh_studied_attack_mark(class_features, target_entity_id)
            changed = True

        if changed:
            self.attack_roll_request.encounter_repository.save(encounter)

    def _apply_tactical_master_override(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        attack_context: dict[str, Any],
        mastery_override: str | None,
    ) -> None:
        if mastery_override is None:
            return

        normalized_override = str(mastery_override).strip().lower()
        if normalized_override not in {"push", "sap", "slow"}:
            raise ValueError("invalid_mastery_override")

        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while applying tactical master")
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError(
                f"actor '{actor_entity_id}' not part of encounter '{encounter_id}' while applying tactical master"
            )

        class_features = actor.class_features if isinstance(actor.class_features, dict) else {}
        fighter = class_features.get("fighter")
        if not isinstance(fighter, dict) or not bool(fighter.get("tactical_master_enabled")):
            raise ValueError("invalid_mastery_override")

        base_mastery = str(
            attack_context.get("weapon_mastery_base")
            or attack_context.get("weapon_mastery")
            or ""
        ).strip().lower()
        if not base_mastery:
            raise ValueError("invalid_mastery_override")

        attack_context["weapon_mastery_base"] = base_mastery
        attack_context["weapon_mastery"] = normalized_override

    def _is_structured_invalid_attack_error(self, error: ValueError) -> bool:
        message = str(error)
        known_exact_reasons = {
            "target_out_of_range",
            "blocked_by_line_of_sight",
            "action_already_used",
            "bonus_action_already_used",
            "two_handed_requires_two_free_hands",
            "actor_cannot_attack",
            "actor_cannot_attack_charmed_target",
            "light_bonus_not_available",
            "light_bonus_requires_light_weapon",
            "light_bonus_requires_different_weapon",
            "actor_not_current_turn_entity",
        }
        if message in known_exact_reasons:
            return True
        if message.startswith("entity '") and "not found in encounter" in message:
            return True
        return False

    def _build_invalid_attack_result(
        self,
        *,
        encounter_id: str,
        actor_id: str | None,
        target_id: str,
        weapon_id: str,
        error: ValueError,
    ) -> dict[str, Any]:
        reason = self._normalize_invalid_attack_reason(str(error))
        return {
            "status": "invalid_attack",
            "encounter_id": encounter_id,
            "actor_id": actor_id,
            "target_id": target_id,
            "weapon_id": weapon_id,
            "reason": reason,
            "message_for_llm": self._message_for_invalid_attack(reason),
            "encounter_state": GetEncounterState(self.attack_roll_request.encounter_repository).execute(encounter_id),
        }

    def _normalize_invalid_attack_reason(self, raw_reason: str) -> str:
        if raw_reason.startswith("entity '") and "not found in encounter" in raw_reason:
            return "target_missing"
        return raw_reason

    def _message_for_invalid_attack(self, reason: str) -> str:
        messages = {
            "target_out_of_range": "当前目标不在攻击范围内，请重新选择目标或调整位置。",
            "blocked_by_line_of_sight": "当前无法攻击该目标，因为视线被阻挡。请重新选择目标或位置。",
            "action_already_used": "当前行动者本回合的动作已用完，无法再发动这次攻击。",
            "bonus_action_already_used": "当前行动者本回合的附赠动作已用完，无法再发动这次攻击。",
            "two_handed_requires_two_free_hands": "当前无法用双手持用这把武器，因为至少一只手正被其他物品占用。",
            "actor_cannot_attack": "当前行动者现在无法发动攻击，请改用其他行动。",
            "actor_cannot_attack_charmed_target": "当前行动者无法攻击魅惑源，请重新选择目标。",
            "target_missing": "当前目标已不再是合法攻击目标，请重新选择目标。",
            "light_bonus_not_available": "当前还不能发动轻型额外攻击，请先用另一把轻型武器执行攻击动作。",
            "light_bonus_requires_light_weapon": "轻型额外攻击必须使用另一把轻型武器。",
            "light_bonus_requires_different_weapon": "轻型额外攻击必须改用另一把轻型武器。",
        }
        return messages.get(reason, "当前无法执行这次攻击，请重新确认目标与条件。")

    def _validate_repository_dependencies(self) -> None:
        shared_repository = self.attack_roll_request.encounter_repository
        if self.attack_roll_result.encounter_repository is not shared_repository:
            raise ValueError("execute_attack services must share the same encounter_repository")
        legacy_update_hp = self.attack_roll_result.update_hp
        if legacy_update_hp is not None and legacy_update_hp.encounter_repository is not shared_repository:
            raise ValueError("execute_attack attack_roll_result.update_hp must share the same encounter_repository")
        if self.update_hp is not None and self.update_hp.encounter_repository is not shared_repository:
            raise ValueError("execute_attack update_hp must share the same encounter_repository")
        if self.update_hp is not None and legacy_update_hp is not None and self.update_hp is not legacy_update_hp:
            raise ValueError("execute_attack requires a single shared update_hp service")

    def _should_use_structured_damage(
        self,
        *,
        damage_rolls: list[dict[str, Any]] | None,
        hp_change: int | None,
        damage_reason: str | None,
        damage_type: str | None,
    ) -> bool:
        if any(value is not None for value in (hp_change, damage_reason, damage_type)):
            if damage_rolls:
                raise ValueError("damage_rolls cannot be combined with hp_change, damage_reason, or damage_type")
            return False
        if damage_rolls is not None and not isinstance(damage_rolls, list):
            raise ValueError("damage_rolls must be a list or None")
        if damage_rolls and any(value is not None for value in (hp_change, damage_reason, damage_type)):
            raise ValueError("damage_rolls cannot be combined with hp_change, damage_reason, or damage_type")
        return True

    def _resolve_attack_roll(
        self,
        *,
        attack_context: dict[str, Any],
        final_total: int | None,
        dice_rolls: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if final_total is None and dice_rolls is None:
            return self._build_auto_attack_roll(attack_context=attack_context)
        if final_total is None or dice_rolls is None:
            raise ValueError("final_total and dice_rolls must be provided together")
        return {
            "final_total": final_total,
            "dice_rolls": dice_rolls,
        }

    def _build_auto_attack_roll(self, *, attack_context: dict[str, Any]) -> dict[str, Any]:
        modifier = int(attack_context.get("attack_bonus", 0) or 0)
        vantage = str(attack_context.get("vantage") or "normal").lower()
        if vantage in {"advantage", "disadvantage"}:
            base_rolls = [random.randint(1, 20), random.randint(1, 20)]
            chosen_roll = max(base_rolls) if vantage == "advantage" else min(base_rolls)
        else:
            base_roll = random.randint(1, 20)
            base_rolls = [base_roll]
            chosen_roll = base_roll
            vantage = "normal"
        return {
            "final_total": chosen_roll + modifier,
            "dice_rolls": {
                "base_rolls": base_rolls,
                "chosen_roll": chosen_roll,
                "modifier": modifier,
                "vantage": vantage,
            },
        }

    def _prepare_structured_damage(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_id: str,
        weapon_id: str,
        attack_context: dict[str, Any],
        final_total: int,
        roll_result: RollResult,
        damage_rolls: list[dict[str, Any]] | None,
        force_critical_on_hit: bool,
    ) -> dict[str, Any] | None:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError(f"actor '{actor_entity_id}' not found in encounter")
        target = encounter.entities.get(target_id)
        if target is None:
            raise ValueError(f"target '{target_id}' not found in encounter")
        if final_total < target.ac:
            return None

        weapon = self.attack_roll_request.resolve_weapon_or_raise(actor, weapon_id)

        damage_parts = self._build_weapon_damage_parts(
            encounter_id=encounter_id,
            actor_entity_id=actor_entity_id,
            weapon_id=weapon_id,
            weapon=weapon,
            target=target,
            attack_context=attack_context,
        )
        self._maybe_append_rogue_sneak_attack_damage_part(
            actor=actor,
            attack_context=attack_context,
            damage_parts=damage_parts,
        )
        self._maybe_append_barbarian_rage_damage_part(
            actor=actor,
            attack_context=attack_context,
            damage_parts=damage_parts,
        )
        self._maybe_append_paladin_divine_smite_damage_part(
            actor=actor,
            target=target,
            attack_context=attack_context,
            damage_parts=damage_parts,
        )
        self._maybe_append_barbarian_brutal_strike_damage_part(
            actor=actor,
            attack_context=attack_context,
            damage_parts=damage_parts,
        )
        is_critical_hit = self._is_critical_hit(roll_result)
        if force_critical_on_hit:
            is_critical_hit = True
        if damage_rolls is None:
            damage_rolls = self._build_auto_damage_rolls_from_parts(
                damage_parts=damage_parts,
                is_critical_hit=is_critical_hit,
            )
        indexed_rolls = self._index_damage_rolls(damage_rolls)
        self._apply_great_weapon_fighting_roll_adjustment(
            actor=actor,
            attack_context=attack_context,
            indexed_rolls=indexed_rolls,
        )
        self._supply_implicit_flat_damage_rolls(
            indexed_rolls=indexed_rolls,
            damage_parts=damage_parts,
        )
        expected_sources = [part["source"] for part in damage_parts]
        self._validate_damage_roll_sources(expected_sources=expected_sources, actual_sources=list(indexed_rolls.keys()))
        self._consume_paladin_divine_smite_spell_slot(
            actor=actor,
            attack_context=attack_context,
        )
        self.attack_roll_request.encounter_repository.save(encounter)

        return self.resolve_damage_parts.execute(
            damage_parts=damage_parts,
            is_critical_hit=is_critical_hit,
            rolled_values=[indexed_rolls[source] for source in expected_sources],
            resistances=target.resistances,
            immunities=target.immunities,
            vulnerabilities=target.vulnerabilities,
        )

    def _resolve_weapon_damage(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_id: str,
        weapon_id: str,
        is_critical_hit: bool,
        damage_rolls: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")

        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError(f"actor '{actor_entity_id}' not found in encounter")
        target = encounter.entities.get(target_id)
        if target is None:
            raise ValueError(f"target '{target_id}' not found in encounter")

        weapon = self.attack_roll_request.resolve_weapon_or_raise(actor, weapon_id)

        damage_parts = self._build_weapon_damage_parts(
            encounter_id=encounter_id,
            actor_entity_id=actor_entity_id,
            weapon_id=weapon_id,
            weapon=weapon,
            target=target,
            attack_context={},
        )
        indexed_rolls = self._index_damage_rolls(damage_rolls)
        expected_sources = [part["source"] for part in damage_parts]
        self._validate_damage_roll_sources(expected_sources=expected_sources, actual_sources=list(indexed_rolls.keys()))

        return self.resolve_damage_parts.execute(
            damage_parts=damage_parts,
            is_critical_hit=is_critical_hit,
            rolled_values=[indexed_rolls[source] for source in expected_sources],
            resistances=target.resistances,
            immunities=target.immunities,
            vulnerabilities=target.vulnerabilities,
        )

    def _build_weapon_damage_parts(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        weapon_id: str,
        weapon: dict[str, Any],
        target: Any,
        attack_context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        raw_parts = weapon.get("damage", [])
        grip_mode = str(attack_context.get("grip_mode") or "default").lower()
        if grip_mode == "two_handed" and isinstance(weapon.get("versatile_damage"), dict):
            raw_parts = [weapon["versatile_damage"]]
        if not isinstance(raw_parts, list) or not raw_parts:
            raise ValueError(f"weapon '{weapon_id}' has no damage parts")

        damage_parts: list[dict[str, Any]] = []
        modifier_value = int(attack_context.get("modifier_value", 0) or 0)
        attack_mode = str(attack_context.get("attack_mode") or "default").lower()
        fighting_style_damage_bonus = self._resolve_fighting_style_damage_bonus(
            encounter_id=encounter_id,
            actor_entity_id=actor_entity_id,
            attack_context=attack_context,
        )
        for index, part in enumerate(raw_parts):
            if not isinstance(part, dict):
                raise ValueError(f"weapon '{weapon_id}' has invalid damage part at index {index}")
            formula = part.get("formula")
            if not isinstance(formula, str) or not formula.strip():
                raise ValueError(f"weapon '{weapon_id}' has invalid damage formula at part {index}")
            resolved_formula = formula.strip()
            if index == 0:
                resolved_formula = self._resolve_primary_damage_formula(
                    formula=resolved_formula,
                    modifier_value=modifier_value,
                    attack_mode=attack_mode,
                    keep_light_bonus_modifier=self._should_keep_light_bonus_modifier(
                        encounter_id=encounter_id,
                        actor_entity_id=actor_entity_id,
                        attack_context=attack_context,
                    ),
                )
                if fighting_style_damage_bonus:
                    resolved_formula = self._add_flat_modifier_to_formula(
                        resolved_formula,
                        fighting_style_damage_bonus,
                    )
            damage_parts.append(
                {
                    "source": f"weapon:{weapon_id}:part_{index}",
                    "formula": resolved_formula,
                    "damage_type": part.get("type"),
                }
            )
        damage_parts.extend(self._build_target_effect_damage_parts(actor_entity_id=actor_entity_id, target=target))
        return damage_parts

    def _resolve_fighting_style_damage_bonus(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        attack_context: dict[str, Any],
    ) -> int:
        bonus = self._resolve_dueling_bonus(
            encounter_id=encounter_id,
            actor_entity_id=actor_entity_id,
            attack_context=attack_context,
        )
        if self._is_thrown_weapon_fighting_attack(
            encounter_id=encounter_id,
            actor_entity_id=actor_entity_id,
            attack_context=attack_context,
        ):
            bonus += 2
        return bonus

    def _resolve_dueling_bonus(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        attack_context: dict[str, Any],
    ) -> int:
        encounter = self.attack_roll_request.encounter_repository.get(attack_context.get("encounter_id", ""))
        if encounter is None:
            encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            return 0
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            return 0
        if not has_fighting_style(actor, "dueling"):
            return 0
        if str(attack_context.get("attack_kind") or "").lower() != "melee_weapon":
            return 0
        if str(attack_context.get("grip_mode") or "default").lower() == "two_handed":
            return 0
        if self._is_holding_other_weapon(actor=actor, current_weapon_id=str(attack_context.get("weapon_id") or "")):
            return 0
        return 2

    def _is_thrown_weapon_fighting_attack(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        attack_context: dict[str, Any],
    ) -> bool:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            return False
        actor = encounter.entities.get(actor_entity_id)
        if actor is None or not has_fighting_style(actor, "thrown_weapon_fighting"):
            return False
        if str(attack_context.get("attack_mode") or "").lower() != "thrown":
            return False
        properties = {
            str(entry).strip().lower()
            for entry in attack_context.get("weapon_properties", [])
            if isinstance(entry, str) and entry.strip()
        }
        return "thrown" in properties

    def _should_keep_light_bonus_modifier(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        attack_context: dict[str, Any],
    ) -> bool:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            return False
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            return False
        return has_fighting_style(actor, "two_weapon_fighting")

    def _is_holding_other_weapon(self, *, actor: Any, current_weapon_id: str) -> bool:
        current_id = str(current_weapon_id or "").strip().lower()
        for weapon in getattr(actor, "weapons", []):
            if not isinstance(weapon, dict):
                continue
            slot = str(weapon.get("slot") or "").strip().lower()
            if slot not in {"main_hand", "off_hand", "both_hands"}:
                continue
            weapon_id = str(weapon.get("weapon_id") or "").strip().lower()
            if weapon_id and weapon_id != current_id:
                return True
        return False

    def _apply_great_weapon_fighting_roll_adjustment(
        self,
        *,
        actor: Any,
        attack_context: dict[str, Any],
        indexed_rolls: dict[str, list[int]],
    ) -> None:
        if not has_fighting_style(actor, "great_weapon_fighting"):
            return
        if str(attack_context.get("attack_kind") or "").lower() != "melee_weapon":
            return
        if str(attack_context.get("grip_mode") or "").lower() != "two_handed":
            return
        properties = {
            str(entry).strip().lower()
            for entry in attack_context.get("weapon_properties", [])
            if isinstance(entry, str) and entry.strip()
        }
        if "two_handed" not in properties and "versatile" not in properties:
            return
        weapon_id = str(attack_context.get("weapon_id") or "").strip()
        if not weapon_id:
            return
        source = f"weapon:{weapon_id}:part_0"
        rolls = indexed_rolls.get(source)
        if not isinstance(rolls, list):
            return
        indexed_rolls[source] = [3 if roll in {1, 2} else roll for roll in rolls]

    def _maybe_append_rogue_sneak_attack_damage_part(
        self,
        *,
        actor: Any,
        attack_context: dict[str, Any],
        damage_parts: list[dict[str, Any]],
    ) -> bool:
        options = attack_context.get("class_feature_options")
        if not isinstance(options, dict) or not bool(options.get("sneak_attack")):
            return False

        rogue_runtime = ensure_rogue_runtime(actor)
        sneak_attack = rogue_runtime.get("sneak_attack")
        if not isinstance(sneak_attack, dict):
            return False
        if bool(sneak_attack.get("used_this_turn")):
            return False

        damage_dice = sneak_attack.get("damage_dice")
        if not isinstance(damage_dice, str) or not damage_dice.strip():
            return False
        resolved_formula = self._resolve_cunning_strike_adjusted_sneak_attack_formula(
            base_formula=damage_dice.strip(),
            attack_context=attack_context,
        )
        if resolved_formula is None:
            return False

        damage_parts.append(
            {
                "source": "rogue_sneak_attack",
                "formula": resolved_formula,
                "damage_type": attack_context.get("primary_damage_type"),
            }
        )
        return True

    def _maybe_append_barbarian_rage_damage_part(
        self,
        *,
        actor: Any,
        attack_context: dict[str, Any],
        damage_parts: list[dict[str, Any]],
    ) -> bool:
        barbarian_runtime = ensure_barbarian_runtime(actor)
        rage = barbarian_runtime.get("rage")
        if not isinstance(rage, dict) or not bool(rage.get("active")):
            return False
        if str(attack_context.get("modifier") or "").lower() != "str":
            return False

        rage_damage_bonus = barbarian_runtime.get("rage_damage_bonus")
        if isinstance(rage_damage_bonus, bool) or not isinstance(rage_damage_bonus, int) or rage_damage_bonus <= 0:
            return False

        damage_parts.append(
            {
                "source": "barbarian_rage_damage",
                "formula": str(rage_damage_bonus),
                "damage_type": attack_context.get("primary_damage_type"),
            }
        )
        return True

    def _maybe_append_barbarian_brutal_strike_damage_part(
        self,
        *,
        actor: Any,
        attack_context: dict[str, Any],
        damage_parts: list[dict[str, Any]],
    ) -> bool:
        class_feature_options = attack_context.get("class_feature_options")
        if not isinstance(class_feature_options, dict):
            return False
        brutal_strike = class_feature_options.get("brutal_strike")
        if not isinstance(brutal_strike, dict):
            return False

        barbarian_runtime = ensure_barbarian_runtime(actor)
        brutal_runtime = barbarian_runtime.get("brutal_strike")
        if not isinstance(brutal_runtime, dict) or not bool(brutal_runtime.get("enabled")):
            return False
        extra_damage_dice = brutal_runtime.get("extra_damage_dice")
        if not isinstance(extra_damage_dice, str) or not extra_damage_dice.strip():
            return False

        damage_parts.append(
            {
                "source": "barbarian_brutal_strike",
                "formula": extra_damage_dice.strip(),
                "damage_type": attack_context.get("primary_damage_type"),
            }
        )
        return True

    def _maybe_append_paladin_divine_smite_damage_part(
        self,
        *,
        actor: Any,
        target: Any,
        attack_context: dict[str, Any],
        damage_parts: list[dict[str, Any]],
    ) -> bool:
        class_feature_options = attack_context.get("class_feature_options")
        if not isinstance(class_feature_options, dict):
            return False
        divine_smite = class_feature_options.get("divine_smite")
        if not isinstance(divine_smite, dict):
            return False

        paladin_runtime = ensure_paladin_runtime(actor)
        smite_runtime = paladin_runtime.get("divine_smite")
        if not isinstance(smite_runtime, dict) or not bool(smite_runtime.get("enabled")):
            return False

        attack_kind = str(attack_context.get("attack_kind") or "").lower()
        if attack_kind not in {"melee_weapon", "unarmed_strike"}:
            return False

        slot_level = divine_smite.get("slot_level")
        if isinstance(slot_level, bool) or not isinstance(slot_level, int) or slot_level < 1:
            raise ValueError("divine_smite_invalid_slot_level")
        self._ensure_spell_slot_available(actor=actor, slot_level=slot_level)

        damage_parts.append(
            {
                "source": "paladin_divine_smite",
                "formula": self._resolve_divine_smite_formula(target=target, slot_level=slot_level),
                "damage_type": "radiant",
            }
        )
        return True

    def _resolve_divine_smite_formula(self, *, target: Any, slot_level: int) -> str:
        dice_count = 2 + max(0, slot_level - 1)
        creature_type = self._resolve_target_creature_type(target)
        if creature_type in {"fiend", "undead"}:
            dice_count += 1
        return f"{dice_count}d8"

    def _resolve_target_creature_type(self, target: Any) -> str | None:
        source_ref = getattr(target, "source_ref", {})
        if isinstance(source_ref, dict):
            creature_type = source_ref.get("creature_type")
            if isinstance(creature_type, str) and creature_type.strip():
                return creature_type.strip().lower()

        category = getattr(target, "category", None)
        if isinstance(category, str) and category.strip():
            return category.strip().lower()
        return None

    def _ensure_spell_slot_available(self, *, actor: Any, slot_level: int) -> None:
        resources = getattr(actor, "resources", {})
        spell_slots = resources.get("spell_slots") if isinstance(resources, dict) else None
        if not isinstance(spell_slots, dict):
            raise ValueError("divine_smite_requires_spell_slots")

        slot_key = str(slot_level)
        slot_info = spell_slots.get(slot_key)
        if not isinstance(slot_info, dict):
            raise ValueError("divine_smite_slot_unavailable")
        remaining = slot_info.get("remaining")
        if isinstance(remaining, bool) or not isinstance(remaining, int) or remaining <= 0:
            raise ValueError("divine_smite_slot_unavailable")

    def _consume_paladin_divine_smite_spell_slot(
        self,
        *,
        actor: Any,
        attack_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        class_feature_options = attack_context.get("class_feature_options")
        if not isinstance(class_feature_options, dict):
            return None
        divine_smite = class_feature_options.get("divine_smite")
        if not isinstance(divine_smite, dict):
            return None

        slot_level = divine_smite.get("slot_level")
        if isinstance(slot_level, bool) or not isinstance(slot_level, int) or slot_level < 1:
            raise ValueError("divine_smite_invalid_slot_level")

        resources = getattr(actor, "resources", {})
        spell_slots = resources.get("spell_slots") if isinstance(resources, dict) else None
        if not isinstance(spell_slots, dict):
            raise ValueError("divine_smite_requires_spell_slots")
        slot_info = spell_slots.get(str(slot_level))
        if not isinstance(slot_info, dict):
            raise ValueError("divine_smite_slot_unavailable")
        remaining = slot_info.get("remaining")
        if isinstance(remaining, bool) or not isinstance(remaining, int) or remaining <= 0:
            raise ValueError("divine_smite_slot_unavailable")
        slot_info["remaining"] = remaining - 1
        return {
            "slot_level": slot_level,
            "remaining_before": remaining,
            "remaining_after": slot_info["remaining"],
        }

    def _build_auto_damage_rolls_from_parts(
        self,
        *,
        damage_parts: list[dict[str, Any]],
        is_critical_hit: bool,
    ) -> list[dict[str, Any]]:
        auto_rolls: list[dict[str, Any]] = []
        for part in damage_parts:
            formula = str(part.get("formula") or "").strip()
            dice_count, die_size = self._parse_damage_formula_or_flat(formula)
            effective_dice_count = dice_count * 2 if is_critical_hit else dice_count
            auto_rolls.append(
                {
                    "source": part.get("source"),
                    "rolls": [random.randint(1, die_size) for _ in range(effective_dice_count)],
                }
            )
        return auto_rolls

    def _build_target_effect_damage_parts(self, *, actor_entity_id: str, target: Any) -> list[dict[str, Any]]:
        raw_effects = getattr(target, "turn_effects", [])
        if not isinstance(raw_effects, list):
            return []

        damage_parts: list[dict[str, Any]] = []
        for effect in raw_effects:
            if not isinstance(effect, dict):
                continue
            if effect.get("source_entity_id") != actor_entity_id:
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

    def _index_damage_rolls(self, damage_rolls: list[dict[str, Any]] | None) -> dict[str, list[int]]:
        indexed: dict[str, list[int]] = {}
        for item in damage_rolls or []:
            if not isinstance(item, dict):
                raise ValueError("damage_rolls must contain dict items")
            source = item.get("source")
            if not isinstance(source, str) or not source.strip():
                raise ValueError("damage_roll_source must be a non-empty string")
            if source in indexed:
                raise ValueError(f"duplicate_damage_roll_source: {source}")
            rolls = item.get("rolls", [])
            if not isinstance(rolls, list):
                raise ValueError(f"damage_rolls[{source}] rolls must be a list")
            indexed[source] = rolls
        return indexed

    def _validate_damage_roll_sources(
        self,
        *,
        expected_sources: list[str],
        actual_sources: list[str],
    ) -> None:
        actual_source_set = set(actual_sources)
        expected_source_set = set(expected_sources)

        missing = sorted(source for source in expected_sources if source not in actual_source_set)
        unknown = sorted(source for source in actual_sources if source not in expected_source_set)
        if missing:
            raise ValueError(f"missing_damage_roll_sources: {', '.join(missing)}")
        if unknown:
            raise ValueError(f"unknown_damage_roll_sources: {', '.join(unknown)}")

    def _parse_damage_formula(self, formula: str) -> tuple[int, int]:
        match = self._FORMULA_RE.match(formula)
        if match is None:
            raise ValueError("invalid_damage_formula")
        dice_count = int(match.group(1))
        die_size = int(match.group(2))
        if dice_count <= 0 or die_size <= 0:
            raise ValueError("invalid_damage_formula")
        return dice_count, die_size

    def _parse_damage_formula_or_flat(self, formula: str) -> tuple[int, int]:
        match = self._FORMULA_RE.match(formula)
        if match is not None:
            dice_count = int(match.group(1))
            die_size = int(match.group(2))
            if dice_count <= 0 or die_size <= 0:
                raise ValueError("invalid_damage_formula")
            return dice_count, die_size

        flat_match = self._FLAT_DAMAGE_RE.match(formula)
        if flat_match is not None:
            flat_bonus = int(flat_match.group(1))
            if flat_bonus < 0:
                raise ValueError("invalid_damage_formula")
            return 0, 1
        raise ValueError("invalid_damage_formula")

    def _supply_implicit_flat_damage_rolls(
        self,
        *,
        indexed_rolls: dict[str, list[int]],
        damage_parts: list[dict[str, Any]],
    ) -> None:
        for part in damage_parts:
            if not isinstance(part, dict):
                continue
            source = str(part.get("source") or "").strip()
            if not source or source in indexed_rolls:
                continue
            formula = str(part.get("formula") or "").strip()
            if self._FLAT_DAMAGE_RE.match(formula):
                indexed_rolls[source] = []

    def _resolve_cunning_strike_adjusted_sneak_attack_formula(
        self,
        *,
        base_formula: str,
        attack_context: dict[str, Any],
    ) -> str | None:
        dice_count, die_size = self._parse_damage_formula(base_formula)
        options = attack_context.get("class_feature_options")
        spent_dice = 0
        if isinstance(options, dict):
            cunning_strike = options.get("cunning_strike")
            if isinstance(cunning_strike, dict):
                raw_spent = cunning_strike.get("spent_dice", 0)
                if isinstance(raw_spent, int) and not isinstance(raw_spent, bool):
                    spent_dice = max(0, raw_spent)
        remaining_dice = max(0, dice_count - spent_dice)
        if remaining_dice <= 0:
            return None
        return f"{remaining_dice}d{die_size}"

    def _apply_resolved_damage(
        self,
        *,
        encounter_id: str,
        target_id: str,
        source_entity_id: str,
        attack_name: str,
        damage_resolution: dict[str, Any],
        is_critical_hit: bool,
        concentration_vantage: str,
        zero_hp_intent: str | None,
        attack_kind: str | None,
    ) -> dict[str, Any]:
        if self.update_hp is None:
            raise ValueError("update_hp service is required when resolving attack damage")

        return self.update_hp.execute(
            encounter_id=encounter_id,
            target_id=target_id,
            hp_change=damage_resolution["total_damage"],
            reason=f"{attack_name} damage",
            damage_type=None,
            from_critical_hit=is_critical_hit,
            source_entity_id=source_entity_id,
            attack_kind=attack_kind,
            zero_hp_intent=zero_hp_intent,
            concentration_vantage=concentration_vantage,
        )

    def _apply_legacy_damage(
        self,
        *,
        encounter_id: str,
        target_id: str,
        source_entity_id: str,
        attack_name: str,
        hp_change: int,
        damage_reason: str | None,
        damage_type: str | None,
        is_critical_hit: bool,
        concentration_vantage: str,
        zero_hp_intent: str | None,
        attack_kind: str | None,
    ) -> dict[str, Any]:
        if self.update_hp is None:
            raise ValueError("update_hp service is required when resolving attack damage")

        return self.update_hp.execute(
            encounter_id=encounter_id,
            target_id=target_id,
            hp_change=hp_change,
            reason=damage_reason or attack_name or "Attack damage",
            damage_type=damage_type,
            from_critical_hit=is_critical_hit,
            source_entity_id=source_entity_id,
            attack_kind=attack_kind,
            zero_hp_intent=zero_hp_intent,
            concentration_vantage=concentration_vantage,
        )

    def _is_critical_hit(self, roll_result: RollResult) -> bool:
        if bool(roll_result.metadata.get("is_critical_hit")):
            return True

        base_rolls = roll_result.dice_rolls.get("base_rolls", [])
        return isinstance(base_rolls, list) and 20 in base_rolls

    def _append_modifier_to_formula_if_needed(self, formula: str, modifier_value: int) -> str:
        if modifier_value == 0:
            return formula
        if not re.fullmatch(r"\d+d\d+", formula):
            return formula
        if modifier_value > 0:
            return f"{formula}+{modifier_value}"
        return f"{formula}{modifier_value}"

    def _resolve_primary_damage_formula(
        self,
        *,
        formula: str,
        modifier_value: int,
        attack_mode: str,
        keep_light_bonus_modifier: bool = False,
    ) -> str:
        if attack_mode != "light_bonus":
            return self._append_modifier_to_formula_if_needed(formula, modifier_value)
        if keep_light_bonus_modifier:
            return self._append_modifier_to_formula_if_needed(formula, modifier_value)
        if modifier_value <= 0:
            return self._append_modifier_to_formula_if_needed(formula, modifier_value)
        stripped_formula = re.sub(rf"\+{modifier_value}$", "", formula)
        if stripped_formula != formula and re.fullmatch(r"\d+d\d+", stripped_formula):
            return stripped_formula
        return formula if not re.fullmatch(r"\d+d\d+", formula) else formula

    def _add_flat_modifier_to_formula(self, formula: str, bonus: int) -> str:
        if bonus == 0:
            return formula
        match = re.fullmatch(r"(\d+d\d+)([+-]\d+)?", formula.strip())
        if match is None:
            return formula
        base = match.group(1)
        existing = int(match.group(2) or 0)
        total = existing + bonus
        if total == 0:
            return base
        return f"{base}+{total}" if total > 0 else f"{base}{total}"

    def _apply_deflect_attacks_pending_effect(
        self,
        *,
        encounter_id: str,
        target_entity_id: str,
        host_action_id: str | None,
        damage_resolution: dict[str, Any],
    ) -> dict[str, Any] | None:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while applying deflect attacks")
        target = encounter.entities.get(target_entity_id)
        if target is None:
            return None

        matched_effect = None
        remaining_effects: list[dict[str, Any]] = []
        for effect in target.turn_effects:
            if (
                matched_effect is None
                and isinstance(effect, dict)
                and effect.get("effect_type") == "deflect_attacks_pending"
                and (host_action_id is None or effect.get("attack_id") == host_action_id)
            ):
                matched_effect = dict(effect)
                continue
            remaining_effects.append(effect)
        if matched_effect is None:
            return None

        target.turn_effects = remaining_effects
        prevented = int(matched_effect.get("damage_reduction_total", 0) or 0)
        total_damage = int(damage_resolution.get("total_damage", 0) or 0)
        damage_resolution["total_damage"] = max(0, total_damage - prevented)
        if isinstance(damage_resolution.get("parts"), list):
            remaining_prevention = max(0, prevented)
            for part in damage_resolution["parts"]:
                if not isinstance(part, dict):
                    continue
                adjusted_total = part.get("adjusted_total")
                if isinstance(adjusted_total, int):
                    prevented_here = min(adjusted_total, remaining_prevention)
                    part["adjusted_total"] = max(0, adjusted_total - prevented_here)
                    remaining_prevention -= prevented_here
                total = part.get("total")
                if isinstance(total, int):
                    part["total"] = max(part["adjusted_total"], 0) if isinstance(part.get("adjusted_total"), int) else total

        result: dict[str, Any] = {
            "status": "damage_reduced",
            "damage_prevented": min(total_damage, prevented),
            "remaining_damage": damage_resolution["total_damage"],
        }
        self.attack_roll_request.encounter_repository.save(encounter)
        if damage_resolution["total_damage"] == 0 and bool(matched_effect.get("redirect_requested")):
            redirect_resolution = self._resolve_deflect_attacks_redirect(
                encounter=encounter,
                monk_entity=target,
                effect=matched_effect,
            )
            if redirect_resolution is not None:
                result["redirect_resolution"] = redirect_resolution
        return result

    def _resolve_deflect_attacks_redirect(
        self,
        *,
        encounter: Any,
        monk_entity: Any,
        effect: dict[str, Any],
    ) -> dict[str, Any] | None:
        redirect_target_id = effect.get("redirect_target_id")
        if not isinstance(redirect_target_id, str) or redirect_target_id not in encounter.entities:
            return None
        monk_runtime = get_monk_runtime(monk_entity)
        focus_points = monk_runtime.get("focus_points")
        if not isinstance(focus_points, dict):
            return None
        remaining_focus = focus_points.get("remaining")
        if not isinstance(remaining_focus, int) or remaining_focus <= 0:
            return None

        redirect_target = encounter.entities[redirect_target_id]
        dex_mod = monk_entity.ability_mods.get("dex", 0)
        proficiency_bonus = monk_entity.proficiency_bonus if isinstance(monk_entity.proficiency_bonus, int) else 0
        if not isinstance(dex_mod, int):
            dex_mod = 0
        save_dc = 8 + proficiency_bonus + dex_mod
        save_roll = effect.get("redirect_save_roll", 0)
        save_total = save_roll + int(redirect_target.ability_mods.get("dex", 0) or 0) if isinstance(save_roll, int) else 0
        success = save_total >= save_dc
        if success:
            return {
                "save_dc": save_dc,
                "save_total": save_total,
                "success": True,
                "total_damage": 0,
            }

        martial_arts_die = monk_runtime.get("martial_arts_die")
        if not isinstance(martial_arts_die, str) or not martial_arts_die.strip():
            return None
        base_formula = self._double_die_formula(martial_arts_die.strip())
        base_rolls = effect.get("redirect_damage_rolls")
        if not isinstance(base_rolls, list) or not all(isinstance(item, int) for item in base_rolls):
            base_rolls = self._roll_formula(base_formula)
        total_damage = sum(int(item) for item in base_rolls) + max(0, dex_mod)
        focus_points["remaining"] = remaining_focus - 1
        self.attack_roll_request.encounter_repository.save(encounter)
        self.update_hp.execute(
            encounter_id=encounter.encounter_id,
            target_id=redirect_target_id,
            hp_change=total_damage,
            reason="Deflect Attacks redirect",
            damage_type=effect.get("redirect_damage_type"),
            source_entity_id=monk_entity.entity_id,
        )
        return {
            "save_dc": save_dc,
            "save_total": save_total,
            "success": False,
            "damage_rolls": base_rolls,
            "total_damage": total_damage,
        }

    def _double_die_formula(self, formula: str) -> str:
        match = self._FORMULA_RE.match(formula)
        if match is None:
            raise ValueError("invalid_martial_arts_formula")
        count = int(match.group(1)) * 2
        sides = int(match.group(2))
        return f"{count}d{sides}"

    def _apply_pending_damage_multiplier(
        self,
        *,
        damage_resolution: dict[str, Any],
        damage_multiplier: float | None,
    ) -> dict[str, Any] | None:
        if damage_multiplier is None:
            return None
        if not isinstance(damage_multiplier, (int, float)):
            raise ValueError("pending_damage_multiplier_must_be_numeric")
        if damage_multiplier < 0:
            raise ValueError("pending_damage_multiplier_must_be_positive")
        if float(damage_multiplier) == 1:
            return None

        original_total = int(damage_resolution.get("total_damage", 0) or 0)
        reduced_total = int(original_total * float(damage_multiplier))
        damage_resolution["total_damage"] = reduced_total

        parts = damage_resolution.get("parts")
        if isinstance(parts, list):
            adjusted_parts: list[dict[str, Any] | Any] = []
            for part in parts:
                if not isinstance(part, dict):
                    adjusted_parts.append(part)
                    continue
                adjusted_total = part.get("adjusted_total")
                updated_part = dict(part)
                if isinstance(adjusted_total, int):
                    updated_part["adjusted_total"] = int(adjusted_total * float(damage_multiplier))
                    if isinstance(updated_part.get("total"), int):
                        updated_part["total"] = updated_part["adjusted_total"]
                adjusted_parts.append(updated_part)
            numeric_parts = [
                item for item in adjusted_parts
                if isinstance(item, dict) and isinstance(item.get("adjusted_total"), int)
            ]
            delta = reduced_total - sum(int(item["adjusted_total"]) for item in numeric_parts)
            if delta != 0 and numeric_parts:
                numeric_parts[-1]["adjusted_total"] = max(0, int(numeric_parts[-1]["adjusted_total"]) + delta)
                if isinstance(numeric_parts[-1].get("total"), int):
                    numeric_parts[-1]["total"] = numeric_parts[-1]["adjusted_total"]
            damage_resolution["parts"] = adjusted_parts

        return {
            "status": "damage_halved",
            "damage_multiplier": float(damage_multiplier),
            "original_damage": original_total,
            "reduced_damage": reduced_total,
        }

    def _apply_pending_flat_damage_reduction(
        self,
        *,
        damage_resolution: dict[str, Any],
        pending_flat_damage_reduction: int | None,
    ) -> dict[str, Any] | None:
        if pending_flat_damage_reduction is None:
            return None
        if isinstance(pending_flat_damage_reduction, bool) or not isinstance(pending_flat_damage_reduction, int):
            raise ValueError("pending_flat_damage_reduction_must_be_integer")
        if pending_flat_damage_reduction <= 0:
            return None

        original_total = int(damage_resolution.get("total_damage", 0) or 0)
        reduced_total = max(0, original_total - pending_flat_damage_reduction)
        damage_resolution["total_damage"] = reduced_total

        parts = damage_resolution.get("parts")
        if isinstance(parts, list):
            remaining = pending_flat_damage_reduction
            adjusted_parts: list[dict[str, Any] | Any] = []
            for part in parts:
                if not isinstance(part, dict):
                    adjusted_parts.append(part)
                    continue
                updated_part = dict(part)
                adjusted_total = updated_part.get("adjusted_total")
                if isinstance(adjusted_total, int):
                    reduced_part_total = max(0, adjusted_total - remaining)
                    spent = adjusted_total - reduced_part_total
                    remaining = max(0, remaining - spent)
                    updated_part["adjusted_total"] = reduced_part_total
                    if isinstance(updated_part.get("total"), int):
                        updated_part["total"] = reduced_part_total
                adjusted_parts.append(updated_part)
            damage_resolution["parts"] = adjusted_parts

        return {
            "status": "damage_reduced",
            "original_damage": original_total,
            "damage_reduction": min(original_total, pending_flat_damage_reduction),
            "reduced_damage": reduced_total,
        }

    def _apply_legacy_damage_multiplier(
        self,
        *,
        hp_change: int,
        damage_multiplier: float | None,
    ) -> int:
        if damage_multiplier is None:
            return hp_change
        if not isinstance(damage_multiplier, (int, float)):
            raise ValueError("pending_damage_multiplier_must_be_numeric")
        if damage_multiplier < 0:
            raise ValueError("pending_damage_multiplier_must_be_positive")
        return int(hp_change * float(damage_multiplier))

    def _roll_formula(self, formula: str) -> list[int]:
        match = self._FORMULA_RE.match(formula)
        if match is None:
            raise ValueError("invalid_formula")
        count = int(match.group(1))
        sides = int(match.group(2))
        return [random.randint(1, sides) for _ in range(count)]

    def _apply_cunning_strike_effects(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str,
        attack_context: dict[str, Any],
        resolution: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not bool(resolution.get("hit")):
            return None
        class_feature_options = attack_context.get("class_feature_options")
        if not isinstance(class_feature_options, dict):
            return None
        cunning_strike = class_feature_options.get("cunning_strike")
        if not isinstance(cunning_strike, dict):
            return None
        effects = cunning_strike.get("effects")
        if not isinstance(effects, list) or not effects:
            return None

        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        actor = encounter.entities.get(actor_entity_id)
        target = encounter.entities.get(target_entity_id)
        if actor is None or target is None:
            raise ValueError("cunning_strike_entities_not_found")

        applied_effects: list[dict[str, Any]] = []
        changed = False
        save_dc = 8 + int(actor.proficiency_bonus or 0) + int(actor.ability_mods.get("dex", 0) or 0)

        for effect_option in effects:
            if not isinstance(effect_option, dict):
                continue
            effect_name = str(effect_option.get("effect") or "").strip().lower()
            if effect_name == "trip":
                outcome = self._apply_cunning_strike_trip(
                    target=target,
                    save_dc=save_dc,
                    effect_option=effect_option,
                )
            elif effect_name == "withdraw":
                outcome = {
                    "effect": "withdraw",
                    "status": "movement_available",
                    "withdraw_movement": {
                        "feet": int(actor.speed.get("walk", 0) or 0) // 2,
                        "ignore_opportunity_attacks": True,
                    },
                }
            elif effect_name == "poison":
                outcome = self._apply_cunning_strike_condition_with_save(
                    target=target,
                    effect_name="poison",
                    applied_condition="poisoned",
                    save_ability="con",
                    save_dc=save_dc,
                    effect_option=effect_option,
                    ends_on_next_turn_end=False,
                )
            elif effect_name == "daze":
                outcome = self._apply_cunning_strike_condition_with_save(
                    target=target,
                    effect_name="daze",
                    applied_condition="dazed",
                    save_ability="con",
                    save_dc=save_dc,
                    effect_option=effect_option,
                    ends_on_next_turn_end=True,
                )
            elif effect_name == "knock_out":
                outcome = self._apply_cunning_strike_condition_with_save(
                    target=target,
                    effect_name="knock_out",
                    applied_condition="unconscious",
                    save_ability="con",
                    save_dc=save_dc,
                    effect_option=effect_option,
                    ends_on_next_turn_end=False,
                )
            elif effect_name == "obscure":
                outcome = self._apply_cunning_strike_condition_with_save(
                    target=target,
                    effect_name="obscure",
                    applied_condition="blinded",
                    save_ability="dex",
                    save_dc=save_dc,
                    effect_option=effect_option,
                    ends_on_next_turn_end=True,
                )
            else:
                continue
            applied_effects.append(outcome)
            changed = changed or bool(outcome.get("changed"))

        if changed:
            self.attack_roll_request.encounter_repository.save(encounter)
        return {
            "spent_dice": int(cunning_strike.get("spent_dice", 0) or 0),
            "save_dc": save_dc,
            "applied_effects": applied_effects,
        }

    def _apply_cunning_strike_trip(
        self,
        *,
        target: Any,
        save_dc: int,
        effect_option: dict[str, Any],
    ) -> dict[str, Any]:
        if str(getattr(target, "size", "medium")).lower() not in {"tiny", "small", "medium", "large"}:
            return {"effect": "trip", "status": "invalid_target_size", "changed": False}
        save = self._roll_cunning_strike_save(target=target, ability="dex", save_dc=save_dc, effect_option=effect_option)
        changed = False
        if not save["success"] and "prone" not in target.conditions:
            target.conditions.append("prone")
            changed = True
        return {
            "effect": "trip",
            "status": "applied" if changed else ("saved" if save["success"] else "already_applied"),
            "changed": changed,
            "save": save,
        }

    def _apply_cunning_strike_condition_with_save(
        self,
        *,
        target: Any,
        effect_name: str,
        applied_condition: str,
        save_ability: str,
        save_dc: int,
        effect_option: dict[str, Any],
        ends_on_next_turn_end: bool,
    ) -> dict[str, Any]:
        save = self._roll_cunning_strike_save(
            target=target,
            ability=save_ability,
            save_dc=save_dc,
            effect_option=effect_option,
        )
        if save["success"]:
            return {
                "effect": effect_name,
                "status": "saved",
                "changed": False,
                "save": save,
            }

        changed = False
        if applied_condition not in target.conditions:
            target.conditions.append(applied_condition)
            changed = True
        effect_id = f"effect_cunning_strike_{effect_name}_{uuid4().hex[:12]}"
        if ends_on_next_turn_end:
            target.turn_effects.append(
                {
                    "effect_id": effect_id,
                    "effect_type": f"cunning_strike_{effect_name}",
                    "name": f"Cunning Strike {effect_name}",
                    "source_entity_id": effect_option.get("source_entity_id"),
                    "target_entity_id": target.entity_id,
                    "trigger": "end_of_turn",
                    "save": None,
                    "on_trigger": {
                        "damage_parts": [],
                        "apply_conditions": [],
                        "remove_conditions": [applied_condition],
                    },
                    "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "remove_after_trigger": True,
                }
            )
            changed = True
        else:
            target.turn_effects.append(
                {
                    "effect_id": effect_id,
                    "effect_type": f"cunning_strike_{effect_name}",
                    "name": f"Cunning Strike {effect_name}",
                    "source_entity_id": effect_option.get("source_entity_id"),
                    "target_entity_id": target.entity_id,
                    "trigger": "end_of_turn",
                    "save": {"ability": save_ability, "dc": save_dc, "on_success_remove_effect": True},
                    "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "on_save_success": {
                        "damage_parts": [],
                        "apply_conditions": [],
                        "remove_conditions": [applied_condition],
                    },
                    "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "remove_after_trigger": False,
                }
            )
            changed = True

        return {
            "effect": effect_name,
            "status": "applied",
            "changed": changed,
            "save": save,
            "condition": applied_condition,
            "effect_id": effect_id,
        }

    def _roll_cunning_strike_save(
        self,
        *,
        target: Any,
        ability: str,
        save_dc: int,
        effect_option: dict[str, Any],
    ) -> dict[str, Any]:
        override = effect_option.get("save_roll")
        if isinstance(override, bool):
            override = None
        if isinstance(override, int):
            base_roll = override
        else:
            base_roll = random.randint(1, 20)

        ability_mod = int(target.ability_mods.get(ability, 0) or 0)
        proficiency_bonus = int(target.proficiency_bonus or 0) if ability in resolve_entity_save_proficiencies(target) else 0
        total = base_roll + ability_mod + proficiency_bonus
        return {
            "ability": ability,
            "dc": save_dc,
            "base_roll": base_roll,
            "ability_mod": ability_mod,
            "proficiency_bonus": proficiency_bonus,
            "total": total,
            "success": total >= save_dc,
        }

    def _mark_attack_resource_used(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str,
        weapon_id: str,
        attack_context: dict[str, Any],
        resolution: dict[str, Any],
        consume_action: bool,
        consume_bonus_action: bool,
        consume_reaction: bool,
    ) -> None:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while marking attack resources")
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError(
                f"actor '{actor_entity_id}' not part of encounter '{encounter_id}' when marking attack resources"
            )
        target = encounter.entities.get(target_entity_id)
        actor.action_economy = actor.action_economy if isinstance(actor.action_economy, dict) else {}
        actor.combat_flags = actor.combat_flags if isinstance(actor.combat_flags, dict) else {}
        attack_mode = str(attack_context.get("attack_mode") or "default").lower()
        if consume_action:
            if attack_mode == "light_bonus":
                actor.action_economy["action_used"] = True
            else:
                actor.action_economy["action_used"] = self._consume_attack_action_sequence(actor)
        if consume_bonus_action:
            actor.action_economy["bonus_action_used"] = True
        if consume_reaction:
            actor.action_economy["reaction_used"] = True
        weapon_properties = {str(prop).lower() for prop in attack_context.get("weapon_properties", [])}
        if attack_mode == "light_bonus":
            actor.combat_flags.pop("light_bonus_trigger", None)
        elif consume_action and "light" in weapon_properties:
            actor.combat_flags["light_bonus_trigger"] = {
                "weapon_id": weapon_id,
                "slot": attack_context.get("weapon_slot"),
                "grants_nick": str(attack_context.get("weapon_mastery") or "").lower() == "nick",
            }
        elif consume_action:
            actor.combat_flags.pop("light_bonus_trigger", None)
        self._consume_monk_flurry_focus_if_needed(actor=actor, attack_mode=attack_mode)
        self._mark_rogue_sneak_attack_used_if_applied(
            actor=actor,
            attack_context=attack_context,
            resolution=resolution,
        )
        self._apply_reckless_attack_penalty_if_needed(
            actor=actor,
            attack_context=attack_context,
        )
        self._mark_barbarian_rage_extended_by_attack_if_needed(
            actor=actor,
            target=target,
        )
        self.attack_roll_request.encounter_repository.save(encounter)

    def _apply_reckless_attack_penalty_if_needed(
        self,
        *,
        actor: Any,
        attack_context: dict[str, Any],
    ) -> None:
        class_feature_options = attack_context.get("class_feature_options")
        if not isinstance(class_feature_options, dict) or not bool(class_feature_options.get("reckless_attack")):
            return

        actor.turn_effects = actor.turn_effects if isinstance(actor.turn_effects, list) else []
        actor.turn_effects = [
            effect
            for effect in actor.turn_effects
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") == "barbarian_reckless_defense_penalty"
                and effect.get("source_entity_id") == actor.entity_id
            )
        ]
        actor.turn_effects.append(
            {
                "effect_id": f"effect_reckless_attack_{uuid4().hex[:12]}",
                "effect_type": "barbarian_reckless_defense_penalty",
                "name": "Reckless Attack",
                "source_entity_id": actor.entity_id,
                "source_name": getattr(actor, "name", actor.entity_id),
                "target_entity_id": actor.entity_id,
                "grants_attack_advantage_against_target": True,
                "expires_on": "start_of_source_turn",
            }
        )

    def _mark_barbarian_rage_extended_by_attack_if_needed(
        self,
        *,
        actor: Any,
        target: Any,
    ) -> None:
        if target is None:
            return
        if getattr(actor, "side", None) == getattr(target, "side", None):
            return
        if not actor.class_features.get("barbarian"):
            return
        barbarian = ensure_barbarian_runtime(actor)
        rage = barbarian.get("rage")
        if isinstance(rage, dict) and bool(rage.get("active")):
            actor.combat_flags["rage_extended_by_attack_this_turn"] = True

    def _apply_barbarian_brutal_strike_updates(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str,
        attack_context: dict[str, Any],
        resolution: dict[str, Any],
    ) -> None:
        class_feature_options = attack_context.get("class_feature_options")
        if not isinstance(class_feature_options, dict):
            return
        brutal_option = class_feature_options.get("brutal_strike")
        if not isinstance(brutal_option, dict):
            return

        result_block: dict[str, Any] = {
            "requested": True,
            "status": "not_hit",
            "effects_applied": [],
        }
        if not bool(resolution.get("hit")):
            resolution["brutal_strike"] = result_block
            return

        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while applying brutal strike")
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError(f"actor '{actor_entity_id}' not found in encounter while applying brutal strike")
        target = encounter.entities.get(target_entity_id)
        if target is None:
            result_block["status"] = "target_removed"
            resolution["brutal_strike"] = result_block
            return

        barbarian_runtime = ensure_barbarian_runtime(actor)
        brutal_runtime = barbarian_runtime.get("brutal_strike")
        if not isinstance(brutal_runtime, dict) or not bool(brutal_runtime.get("enabled")):
            raise ValueError("brutal_strike_not_available")

        result_block["status"] = "resolved"
        result_block["extra_damage_formula"] = str(brutal_runtime.get("extra_damage_dice") or "")

        effects = brutal_option.get("effects")
        if not isinstance(effects, list):
            raise ValueError("brutal_strike_requires_effects")

        for effect in effects:
            effect_name = str(effect.get("effect") if isinstance(effect, dict) else effect or "").strip().lower()
            if not effect_name:
                continue
            result_block["effects_applied"].append(effect_name)
            result_block[effect_name] = self._apply_single_barbarian_brutal_strike_effect(
                encounter_id=encounter_id,
                actor=actor,
                target=target,
                effect_name=effect_name,
            )
            if effect_name == "forceful_blow":
                refreshed = self.attack_roll_request.encounter_repository.get(encounter_id)
                if refreshed is None:
                    raise ValueError(f"encounter '{encounter_id}' not found after forceful blow")
                encounter = refreshed
                actor = refreshed.entities.get(actor_entity_id)
                target = refreshed.entities.get(target_entity_id)
                if actor is None or target is None:
                    raise ValueError("forceful_blow_refresh_failed")

        resolution["brutal_strike"] = result_block
        self.attack_roll_request.encounter_repository.save(encounter)

    def _apply_single_barbarian_brutal_strike_effect(
        self,
        *,
        encounter_id: str,
        actor: Any,
        target: Any,
        effect_name: str,
    ) -> dict[str, Any]:
        if effect_name == "forceful_blow":
            push_result = resolve_linear_push(
                encounter_id=encounter_id,
                actor=actor,
                target=target,
                resolve_forced_movement=self.resolve_forced_movement,
                steps=3,
                reason="barbarian_brutal_strike_forceful_blow",
            )
            push_result["free_movement_after_forceful_blow"] = {
                "feet": int(actor.speed.get("walk", 0) or 0) // 2,
                "ignore_opportunity_attacks": True,
            }
            return push_result

        if effect_name == "hamstring_blow":
            self._remove_matching_barbarian_effects(
                entity=target,
                effect_type="barbarian_hamstring_blow",
                source_entity_id=actor.entity_id,
            )
            effect = self._build_barbarian_turn_effect(
                effect_type="barbarian_hamstring_blow",
                name="Hamstring Blow",
                actor=actor,
                target=target,
            )
            effect["speed_penalty_feet"] = 15
            target.turn_effects.append(effect)
            self._apply_barbarian_speed_penalty_to_remaining(target=target, penalty_feet=15)
            return {
                "status": "applied",
                "effect_id": effect["effect_id"],
                "speed_penalty_feet": 15,
                "expires_on": effect["expires_on"],
            }

        if effect_name == "staggering_blow":
            self._remove_matching_barbarian_effects(
                entity=target,
                effect_type="barbarian_staggering_blow",
                source_entity_id=actor.entity_id,
            )
            effect = self._build_barbarian_turn_effect(
                effect_type="barbarian_staggering_blow",
                name="Staggering Blow",
                actor=actor,
                target=target,
            )
            effect["next_save_disadvantage"] = True
            effect["blocks_opportunity_attacks"] = True
            target.turn_effects.append(effect)
            return {
                "status": "applied",
                "effect_id": effect["effect_id"],
                "next_save_disadvantage": True,
                "blocks_opportunity_attacks": True,
                "expires_on": effect["expires_on"],
            }

        if effect_name == "sundering_blow":
            self._remove_matching_barbarian_effects(
                entity=target,
                effect_type="barbarian_sundering_blow",
                source_entity_id=actor.entity_id,
            )
            effect = self._build_barbarian_turn_effect(
                effect_type="barbarian_sundering_blow",
                name="Sundering Blow",
                actor=actor,
                target=target,
            )
            effect["next_attack_bonus"] = 5
            target.turn_effects.append(effect)
            return {
                "status": "applied",
                "effect_id": effect["effect_id"],
                "next_attack_bonus": 5,
                "expires_on": effect["expires_on"],
            }

        raise ValueError("unsupported_brutal_strike_effect")

    def _build_barbarian_turn_effect(
        self,
        *,
        effect_type: str,
        name: str,
        actor: Any,
        target: Any,
    ) -> dict[str, Any]:
        return {
            "effect_id": f"effect_{effect_type}_{uuid4().hex[:12]}",
            "effect_type": effect_type,
            "name": name,
            "source_entity_id": actor.entity_id,
            "source_name": getattr(actor, "name", actor.entity_id),
            "target_entity_id": target.entity_id,
            "expires_on": "start_of_source_turn",
        }

    def _remove_matching_barbarian_effects(
        self,
        *,
        entity: Any,
        effect_type: str,
        source_entity_id: str,
    ) -> None:
        entity.turn_effects = [
            effect
            for effect in getattr(entity, "turn_effects", [])
            if not (
                isinstance(effect, dict)
                and effect.get("effect_type") == effect_type
                and effect.get("source_entity_id") == source_entity_id
            )
        ]

    def _apply_barbarian_speed_penalty_to_remaining(self, *, target: Any, penalty_feet: int) -> None:
        target.combat_flags = target.combat_flags if isinstance(target.combat_flags, dict) else {}
        tracked = target.combat_flags.get("movement_spent_feet")
        if isinstance(tracked, bool) or not isinstance(tracked, int):
            target.combat_flags["movement_spent_feet"] = max(
                0,
                int(target.speed.get("walk", 0) or 0)
                - int(target.speed.get("remaining", 0) or 0)
                - get_weapon_mastery_speed_penalty(target),
            )
        target.speed["remaining"] = max(0, int(target.speed.get("remaining", 0) or 0) - penalty_feet)

    def _consume_monk_flurry_focus_if_needed(self, *, actor: Any, attack_mode: str) -> None:
        if attack_mode != "flurry_of_blows":
            return
        monk_runtime = get_monk_runtime(actor)
        focus_points = monk_runtime.get("focus_points")
        if not isinstance(focus_points, dict):
            return
        remaining = focus_points.get("remaining")
        if isinstance(remaining, bool) or not isinstance(remaining, int):
            return
        if remaining <= 0:
            return
        focus_points["remaining"] = remaining - 1

    def _mark_rogue_sneak_attack_used_if_applied(
        self,
        *,
        actor: Any,
        attack_context: dict[str, Any],
        resolution: dict[str, Any],
    ) -> None:
        if not bool(resolution.get("hit")):
            return
        class_feature_options = attack_context.get("class_feature_options")
        if not isinstance(class_feature_options, dict) or not bool(class_feature_options.get("sneak_attack")):
            return
        damage_resolution = resolution.get("damage_resolution")
        cunning_strike_used = isinstance(class_feature_options.get("cunning_strike"), dict)
        if not isinstance(damage_resolution, dict) and not cunning_strike_used:
            return
        if isinstance(damage_resolution, dict):
            parts = damage_resolution.get("parts")
            if isinstance(parts, list) and any(
                isinstance(part, dict) and part.get("source") == "rogue_sneak_attack"
                for part in parts
            ):
                cunning_strike_used = True
        if not cunning_strike_used:
            return

        rogue_runtime = ensure_rogue_runtime(actor)
        sneak_attack = rogue_runtime.get("sneak_attack")
        if isinstance(sneak_attack, dict):
            sneak_attack["used_this_turn"] = True

    def _apply_stunning_strike_updates(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_entity_id: str,
        attack_context: dict[str, Any],
        resolution: dict[str, Any],
    ) -> None:
        class_feature_options = attack_context.get("class_feature_options")
        if not isinstance(class_feature_options, dict):
            return
        stunning_option = class_feature_options.get("stunning_strike")
        if not isinstance(stunning_option, dict) or not bool(stunning_option.get("enabled")):
            return

        result_block: dict[str, Any] = {
            "requested": True,
            "enabled": True,
            "triggered": False,
            "status": "not_hit",
            "save": None,
            "applied_effects": [],
        }
        if not bool(resolution.get("hit")):
            resolution["stunning_strike"] = result_block
            return

        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while applying stunning strike")
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError(
                f"actor '{actor_entity_id}' not part of encounter '{encounter_id}' while applying stunning strike"
            )
        target = encounter.entities.get(target_entity_id)
        if target is None:
            result_block["status"] = "target_removed"
            resolution["stunning_strike"] = result_block
            return

        monk_runtime = get_monk_runtime(actor)
        if not isinstance(monk_runtime, dict) or not monk_runtime:
            raise ValueError("stunning_strike_requires_monk_runtime")
        focus_points = monk_runtime.get("focus_points")
        if not isinstance(focus_points, dict):
            raise ValueError("stunning_strike_requires_focus_points")
        remaining = focus_points.get("remaining")
        if isinstance(remaining, bool) or not isinstance(remaining, int) or remaining < 1:
            raise ValueError("stunning_strike_focus_points_depleted")
        focus_points["remaining"] = remaining - 1

        stunning_runtime = monk_runtime.get("stunning_strike")
        if not isinstance(stunning_runtime, dict):
            raise ValueError("stunning_strike_requires_runtime")
        uses_this_turn = stunning_runtime.get("uses_this_turn", 0)
        if isinstance(uses_this_turn, bool) or not isinstance(uses_this_turn, int) or uses_this_turn < 0:
            raise ValueError("stunning_strike_runtime_invalid")
        stunning_runtime["uses_this_turn"] = uses_this_turn + 1

        save_dc = 8 + int(actor.proficiency_bonus) + int(actor.ability_mods.get("wis", 0) or 0)
        save_vantage = self._normalize_save_vantage(stunning_option.get("save_vantage"))
        base_roll = stunning_option.get("save_roll")
        save_rolls_raw = stunning_option.get("save_rolls")
        base_roll_input = base_roll if isinstance(base_roll, int) and not isinstance(base_roll, bool) else None
        base_rolls_input = save_rolls_raw if isinstance(save_rolls_raw, list) else None
        if base_roll_input is None and base_rolls_input is None:
            if save_vantage in {"advantage", "disadvantage"}:
                base_rolls_input = [random.randint(1, 20), random.randint(1, 20)]
            else:
                base_roll_input = random.randint(1, 20)

        save_request = RollRequest(
            request_id=f"req_stunning_strike_{uuid4().hex[:12]}",
            encounter_id=encounter_id,
            actor_entity_id=target.entity_id,
            target_entity_id=target.entity_id,
            roll_type="saving_throw",
            formula="1d20+save_modifier",
            reason=f"{target.name} makes a CON save against Stunning Strike",
            context={
                "save_ability": "con",
                "save_dc": save_dc,
                "vantage": save_vantage,
            },
        )
        save_result = self.resolve_saving_throw.execute(
            encounter_id=encounter_id,
            roll_request=save_request,
            base_roll=base_roll_input,
            base_rolls=base_rolls_input,
            metadata={"source": "class_feature", "class_feature": "monk.stunning_strike"},
        )
        save_success = save_result.final_total >= save_dc
        result_block["triggered"] = True
        result_block["save"] = {
            "request_id": save_result.request_id,
            "dc": save_dc,
            "total": save_result.final_total,
            "success": save_success,
            "dice_rolls": save_result.dice_rolls,
            "metadata": save_result.metadata,
        }
        if not save_success:
            applied = False
            if "stunned" not in target.conditions:
                target.conditions.append("stunned")
                applied = True
            result_block["status"] = "failed_save"
            result_block["applied_effects"].append(
                {
                    "type": "condition",
                    "condition": "stunned",
                    "applied": applied,
                }
            )
        else:
            success_effect = {
                "effect_id": f"effect_stunning_strike_{uuid4().hex[:12]}",
                "effect_type": "monk_stunning_strike_success",
                "name": "Stunning Strike - Save Success",
                "source_entity_id": actor.entity_id,
                "source_name": actor.name,
                "target_entity_id": target.entity_id,
                "source_ref": str(attack_context.get("attack_name") or "stunning_strike"),
                "expires_on": "start_of_source_turn",
                "next_attack_advantage_once": True,
                "speed_multiplier": 0.5,
                "trigger": "start_of_turn",
                "remove_after_trigger": True,
            }
            target.turn_effects.append(success_effect)
            result_block["status"] = "successful_save"
            result_block["applied_effects"].append(
                {
                    "type": "turn_effect",
                    "effect_id": success_effect["effect_id"],
                    "effect_type": success_effect["effect_type"],
                    "next_attack_advantage_once": True,
                    "speed_multiplier": 0.5,
                }
            )
        result_block["focus_points_remaining"] = focus_points["remaining"]
        result_block["uses_this_turn"] = stunning_runtime["uses_this_turn"]
        resolution["stunning_strike"] = result_block
        self.attack_roll_request.encounter_repository.save(encounter)

    def _consume_next_attack_advantage_turn_effects(
        self,
        *,
        encounter_id: str,
        target_entity_id: str,
        effect_ids: list[str] | None,
    ) -> None:
        if not isinstance(effect_ids, list):
            return
        effect_id_set = {
            effect_id.strip()
            for effect_id in effect_ids
            if isinstance(effect_id, str) and effect_id.strip()
        }
        if not effect_id_set:
            return

        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while consuming stunning strike advantage effects")
        target = encounter.entities.get(target_entity_id)
        if target is None:
            return

        retained_effects: list[dict[str, Any]] = []
        removed = False
        for effect in getattr(target, "turn_effects", []):
            if (
                isinstance(effect, dict)
                and effect.get("effect_type") == "monk_stunning_strike_success"
                and effect.get("effect_id") in effect_id_set
            ):
                removed = True
                continue
            retained_effects.append(effect)

        if not removed:
            return

        target.turn_effects = retained_effects
        self.attack_roll_request.encounter_repository.save(encounter)

    def _consume_help_attack_effect(
        self,
        *,
        encounter_id: str,
        target_entity_id: str,
        effect_id: str | None,
    ) -> None:
        if not isinstance(effect_id, str) or not effect_id.strip():
            return
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while consuming help attack effect")
        target = encounter.entities.get(target_entity_id)
        if target is None:
            return
        before = len(getattr(target, "turn_effects", []))
        remove_turn_effect_by_id(target, effect_id.strip())
        if len(getattr(target, "turn_effects", [])) == before:
            return
        self.attack_roll_request.encounter_repository.save(encounter)

    def _normalize_save_vantage(self, raw_vantage: Any) -> str:
        normalized = str(raw_vantage or "normal").strip().lower()
        if normalized not in {"normal", "advantage", "disadvantage"}:
            return "normal"
        return normalized

    def _consume_attack_action_sequence(self, actor: Any) -> bool:
        class_features = actor.class_features if isinstance(actor.class_features, dict) else {}
        max_attacks = max(1, resolve_extra_attack_count(class_features))
        used_attacks = self._increment_attack_action_attacks_used(actor)
        return used_attacks >= max_attacks

    def _increment_attack_action_attacks_used(self, actor: Any) -> int:
        class_features = actor.class_features if isinstance(actor.class_features, dict) else {}
        fighter = class_features.get("fighter")
        if not isinstance(fighter, dict):
            return 1

        turn_counters = fighter.get("turn_counters")
        if not isinstance(turn_counters, dict):
            turn_counters = {}
            fighter["turn_counters"] = turn_counters

        used_attacks = turn_counters.get("attack_action_attacks_used")
        if isinstance(used_attacks, bool) or not isinstance(used_attacks, int):
            used_attacks = 0
        used_attacks = max(0, used_attacks) + 1
        turn_counters["attack_action_attacks_used"] = used_attacks
        return used_attacks

    def _apply_weapon_mastery_updates(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        target_id: str,
        attack_context: dict[str, Any],
        resolution: dict[str, Any],
        mastery_rolls: dict[str, Any] | None,
        resolve_forced_movement: ResolveForcedMovement,
    ) -> dict[str, Any]:
        encounter = self.attack_roll_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found while applying weapon mastery effects")
        actor = encounter.entities.get(actor_entity_id)
        if actor is None:
            raise ValueError(f"actor '{actor_entity_id}' not found in encounter while applying weapon mastery effects")
        target = encounter.entities.get(target_id)
        consumed_effect_ids = consume_attack_roll_weapon_mastery_effects(
            actor=actor,
            effect_ids=list(attack_context.get("consumed_mastery_effect_ids", [])),
        )
        mastery_name = str(attack_context.get("weapon_mastery") or "").lower()
        if target is None and mastery_name in {"sap", "slow", "topple", "push"}:
            self.attack_roll_request.encounter_repository.save(encounter)
            return {
                "consumed_effect_ids": consumed_effect_ids,
                "applied_effects": [],
                "skipped": True,
                "skip_reason": "target_removed",
            }
        if target is None and mastery_name == "vex":
            applied_effects: list[dict[str, Any]] = []
            damage_dealt = int(
                (
                    resolution.get("damage_resolution", {}).get("total_damage")
                    if isinstance(resolution.get("damage_resolution"), dict)
                    else 0
                )
                or 0
            )
            if resolution.get("hit") and damage_dealt > 0:
                actor.turn_effects = [
                    effect
                    for effect in actor.turn_effects
                    if not (
                        isinstance(effect, dict)
                        and effect.get("effect_type") == "weapon_mastery"
                        and str(effect.get("mastery") or "").lower() == "vex"
                        and effect.get("source_entity_id") == actor.entity_id
                        and effect.get("target_entity_id") == target_id
                    )
                ]
                effect = {
                    "effect_id": f"effect_mastery_{uuid4().hex[:12]}",
                    "effect_type": "weapon_mastery",
                    "mastery": "vex",
                    "name": "Vex",
                    "source_entity_id": actor.entity_id,
                    "source_name": actor.name,
                    "target_entity_id": target_id,
                    "source_ref": str(attack_context.get("attack_name") or attack_context.get("weapon_id") or "weapon"),
                    "expires_on": "end_of_source_turn",
                }
                actor.turn_effects.append(effect)
                applied_effects.append(effect)
            self.attack_roll_request.encounter_repository.save(encounter)
            return {
                "consumed_effect_ids": consumed_effect_ids,
                "applied_effects": applied_effects,
                "skipped": False,
            }
        self.attack_roll_request.encounter_repository.save(encounter)
        mastery_resolution = apply_weapon_mastery_on_hit(
            encounter=encounter,
            encounter_id=encounter_id,
            actor=actor,
            target=target,
            attack_context=attack_context,
            resolution=resolution,
            mastery_rolls=mastery_rolls,
            resolve_saving_throw=self.resolve_saving_throw,
            resolve_forced_movement=resolve_forced_movement,
        )
        if mastery_name != "push":
            self.attack_roll_request.encounter_repository.save(encounter)
        result = {
            "consumed_effect_ids": consumed_effect_ids,
            "applied_effects": [dict(effect) for effect in mastery_resolution.get("applied_effects", [])],
        }
        for key, value in mastery_resolution.items():
            if key == "applied_effects":
                continue
            result[key] = value
        return result
