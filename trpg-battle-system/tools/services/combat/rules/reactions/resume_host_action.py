from __future__ import annotations

from typing import Any, TYPE_CHECKING

from tools.models.roll_request import RollRequest
from tools.models.roll_result import RollResult
from tools.repositories.encounter_repository import EncounterRepository
from tools.services.checks.ability_check_result import AbilityCheckResult
from tools.services.combat.save_spell.saving_throw_result import SavingThrowResult
from tools.services.combat.shared.update_conditions import UpdateConditions
from tools.services.combat.shared.update_encounter_notes import UpdateEncounterNotes
from tools.services.combat.shared.update_hp import UpdateHp
from tools.services.events.append_event import AppendEvent

if TYPE_CHECKING:
    from tools.services.combat.attack.execute_attack import ExecuteAttack
    from tools.services.spells.encounter_cast_spell import EncounterCastSpell


class ResumeHostAction:
    """Placeholder for host action resume logic (Task 4 minimal stub)."""

    def __init__(
        self,
        encounter_repository: EncounterRepository,
        append_event: AppendEvent,
        execute_attack: "ExecuteAttack",
        encounter_cast_spell: "EncounterCastSpell",
    ) -> None:
        self.encounter_repository = encounter_repository
        self.ability_check_result = AbilityCheckResult(encounter_repository, append_event)
        self.saving_throw_result = SavingThrowResult(
            encounter_repository,
            append_event,
            UpdateHp(encounter_repository, append_event),
            UpdateConditions(encounter_repository, append_event),
            UpdateEncounterNotes(encounter_repository, append_event),
        )
        self.execute_attack = execute_attack
        self.encounter_cast_spell = encounter_cast_spell

    def execute(
        self,
        *,
        encounter_id: str,
        pending_window: dict[str, Any] | None,
        reaction_result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(pending_window, dict):
            raise ValueError("pending_reaction_window_not_found")
        host_action_type = pending_window.get("host_action_type")
        snapshot = pending_window.get("host_action_snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("host_action_snapshot_missing")

        if host_action_type == "attack":
            force_replay_attack_roll = bool(snapshot.get("force_replay_attack_roll"))
            return {
                "status": "resumed",
                "encounter_id": encounter_id,
                "host_action_result": self.execute_attack.execute(
                    encounter_id=encounter_id,
                    actor_id=snapshot.get("actor_id"),
                    target_id=snapshot.get("target_id"),
                    weapon_id=snapshot.get("weapon_id"),
                    final_total=None if force_replay_attack_roll else snapshot.get("final_total"),
                    dice_rolls=None if force_replay_attack_roll else snapshot.get("dice_rolls"),
                    damage_rolls=snapshot.get("damage_rolls"),
                    vantage=snapshot.get("vantage", "normal") or "normal",
                    description=snapshot.get("description"),
                    attack_mode=snapshot.get("attack_mode"),
                    grip_mode=snapshot.get("grip_mode"),
                    allow_out_of_turn_actor=bool(snapshot.get("allow_out_of_turn_actor", False)),
                    consume_action=bool(snapshot.get("consume_action", True)),
                    consume_reaction=bool(snapshot.get("consume_reaction", False)),
                    pending_flat_damage_reduction=snapshot.get("pending_flat_damage_reduction"),
                    pending_damage_multiplier=snapshot.get("pending_damage_multiplier"),
                    host_action_id=snapshot.get("attack_id"),
                    skip_reaction_window=True,
                ),
                "pending_window": pending_window,
            }

        if host_action_type == "ability_check":
            roll_request_data = snapshot.get("roll_request")
            roll_result_data = snapshot.get("roll_result")
            if not isinstance(roll_request_data, dict):
                raise ValueError("ability_check_roll_request_missing")
            if not isinstance(roll_result_data, dict):
                raise ValueError("ability_check_roll_result_missing")

            roll_request = RollRequest.from_dict(dict(roll_request_data))
            resolved_roll_result = RollResult.from_dict(dict(roll_result_data))
            feature_key: str | None = None
            if isinstance(reaction_result, dict):
                final_total = reaction_result.get("final_total")
                if isinstance(final_total, int) and not isinstance(final_total, bool):
                    resolved_roll_result.final_total = final_total
                raw_feature_key = reaction_result.get("feature_key")
                if isinstance(raw_feature_key, str) and raw_feature_key.strip():
                    feature_key = raw_feature_key.strip()
                else:
                    feature_key = "tactical_mind"
                resolved_roll_result.metadata[feature_key] = dict(reaction_result)

            outcome = self.ability_check_result.execute(
                encounter_id=encounter_id,
                roll_request=roll_request,
                roll_result=resolved_roll_result,
            )
            host_action_result: dict[str, Any] = {
                "encounter_id": encounter_id,
                "actor_id": resolved_roll_result.actor_entity_id,
                "check_type": roll_request.context.get("check_type"),
                "check": snapshot.get("check"),
                "normalized_check": snapshot.get("normalized_check", roll_request.context.get("check")),
                "request": roll_request.to_dict(),
                "roll_result": resolved_roll_result.to_dict(),
                **outcome,
            }
            if isinstance(reaction_result, dict) and isinstance(feature_key, str):
                host_action_result["class_feature_result"] = {feature_key: dict(reaction_result)}
            return {
                "status": "resumed",
                "encounter_id": encounter_id,
                "host_action_result": host_action_result,
                "pending_window": pending_window,
            }

        if host_action_type == "spell_cast":
            return {
                "status": "resumed",
                "encounter_id": encounter_id,
                "host_action_result": self.encounter_cast_spell.execute(
                    encounter_id=encounter_id,
                    actor_id=snapshot.get("actor_id"),
                    spell_id=snapshot.get("spell_id"),
                    target_ids=snapshot.get("target_ids"),
                    target_point=snapshot.get("target_point"),
                    cast_level=snapshot.get("cast_level"),
                    allow_out_of_turn_actor=bool(snapshot.get("allow_out_of_turn_actor", False)),
                    skip_reaction_window=True,
                ),
                "pending_window": pending_window,
            }

        if host_action_type == "save":
            roll_request_data = snapshot.get("roll_request")
            roll_result_data = snapshot.get("roll_result")
            if not isinstance(roll_request_data, dict):
                raise ValueError("save_roll_request_missing")
            if not isinstance(roll_result_data, dict):
                raise ValueError("save_roll_result_missing")

            roll_request = RollRequest.from_dict(dict(roll_request_data))
            resolved_roll_result = RollResult.from_dict(dict(roll_result_data))
            feature_key: str | None = None
            if isinstance(reaction_result, dict):
                save_roll_result = reaction_result.get("save_roll_result")
                if isinstance(save_roll_result, dict):
                    resolved_roll_result = RollResult.from_dict(dict(save_roll_result))
                    resolved_roll_result.request_id = roll_request.request_id
                else:
                    final_total = reaction_result.get("final_total")
                    if isinstance(final_total, int) and not isinstance(final_total, bool):
                        resolved_roll_result.final_total = final_total
                raw_feature_key = reaction_result.get("feature_key")
                if isinstance(raw_feature_key, str) and raw_feature_key.strip():
                    feature_key = raw_feature_key.strip()
                    resolved_roll_result.metadata[feature_key] = dict(reaction_result)

            result_args = snapshot.get("saving_throw_result_args")
            if not isinstance(result_args, dict):
                raise ValueError("saving_throw_result_args_missing")

            resolution = self.saving_throw_result.execute(
                encounter_id=encounter_id,
                roll_request=roll_request,
                roll_result=resolved_roll_result,
                **dict(result_args),
            )
            host_action_result: dict[str, Any] = {
                "cast": snapshot.get("cast"),
                "request": roll_request.to_dict(),
                "roll_result": resolved_roll_result.to_dict(),
                "resolution": resolution,
            }
            if isinstance(feature_key, str):
                host_action_result["class_feature_result"] = {feature_key: dict(reaction_result)}
            return {
                "status": "resumed",
                "encounter_id": encounter_id,
                "host_action_result": host_action_result,
                "pending_window": pending_window,
            }

        raise ValueError("unsupported_host_action_type")
