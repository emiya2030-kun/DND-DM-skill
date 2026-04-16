from __future__ import annotations

import random
import re
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from tools.models.roll_result import RollResult
from tools.services.combat.attack.attack_roll_request import AttackRollRequest
from tools.services.combat.attack.attack_roll_result import AttackRollResult
from tools.services.combat.attack.weapon_mastery_effects import (
    apply_weapon_mastery_on_hit,
    consume_attack_roll_weapon_mastery_effects,
)
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow
from tools.services.combat.damage import ResolveDamageParts
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.encounter.resolve_forced_movement import ResolveForcedMovement

if TYPE_CHECKING:
    from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository
    from tools.services.combat.rules.reactions.open_reaction_window import OpenReactionWindow


class ExecuteAttack:
    """把一次完整武器攻击流程收口成一个统一入口。"""

    _FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")

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
        mastery_rolls: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
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
            attack_id = f"atk_{uuid4().hex[:12]}"
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
                },
                "target_entity_id": request.target_entity_id,
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
        if resolution["hit"] and use_structured_damage:
            if prepared_damage_resolution is None:
                raise ValueError("structured_damage_resolution_missing")
            damage_resolution = prepared_damage_resolution
            resolution["damage_resolution"] = damage_resolution
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
                hp_change=hp_change,
                damage_reason=damage_reason,
                damage_type=damage_type,
                is_critical_hit=resolution["is_critical_hit"],
                concentration_vantage=concentration_vantage,
                zero_hp_intent=zero_hp_intent,
                attack_kind=request.context.get("attack_kind"),
            )

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

        self._mark_attack_resource_used(
            encounter_id=encounter_id,
            actor_entity_id=request.actor_entity_id,
            weapon_id=weapon_id,
            attack_context=request.context,
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
            actor_entity_id=actor_entity_id,
            weapon_id=weapon_id,
            weapon=weapon,
            target=target,
            attack_context=attack_context,
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

    def _resolve_primary_damage_formula(self, *, formula: str, modifier_value: int, attack_mode: str) -> str:
        if attack_mode != "light_bonus":
            return self._append_modifier_to_formula_if_needed(formula, modifier_value)
        if modifier_value <= 0:
            return self._append_modifier_to_formula_if_needed(formula, modifier_value)
        stripped_formula = re.sub(rf"\+{modifier_value}$", "", formula)
        if stripped_formula != formula and re.fullmatch(r"\d+d\d+", stripped_formula):
            return stripped_formula
        return formula if not re.fullmatch(r"\d+d\d+", formula) else formula

    def _mark_attack_resource_used(
        self,
        *,
        encounter_id: str,
        actor_entity_id: str,
        weapon_id: str,
        attack_context: dict[str, Any],
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
        actor.action_economy = actor.action_economy if isinstance(actor.action_economy, dict) else {}
        actor.combat_flags = actor.combat_flags if isinstance(actor.combat_flags, dict) else {}
        if consume_action:
            actor.action_economy["action_used"] = True
        if consume_bonus_action:
            actor.action_economy["bonus_action_used"] = True
        if consume_reaction:
            actor.action_economy["reaction_used"] = True
        attack_mode = str(attack_context.get("attack_mode") or "default").lower()
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
        self.attack_roll_request.encounter_repository.save(encounter)

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
