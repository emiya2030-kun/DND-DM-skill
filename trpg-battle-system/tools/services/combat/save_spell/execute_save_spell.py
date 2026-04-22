from __future__ import annotations

from typing import Any

from tools.repositories.reaction_definition_repository import ReactionDefinitionRepository
from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow
from tools.services.combat.save_spell.saving_throw_request import SavingThrowRequest
from tools.services.combat.save_spell.saving_throw_result import SavingThrowResult
from tools.services.combat.rules.reactions import OpenReactionWindow
from tools.services.encounter.get_encounter_state import GetEncounterState
from tools.services.spells.encounter_cast_spell import EncounterCastSpell


class ExecuteSaveSpell:
    """把一次单目标豁免型法术流程收口成一个统一入口。"""

    def __init__(
        self,
        encounter_cast_spell: EncounterCastSpell,
        saving_throw_request: SavingThrowRequest,
        resolve_saving_throw: ResolveSavingThrow,
        saving_throw_result: SavingThrowResult,
        open_reaction_window: OpenReactionWindow | None = None,
    ):
        self.encounter_cast_spell = encounter_cast_spell
        self.saving_throw_request = saving_throw_request
        self.resolve_saving_throw = resolve_saving_throw
        self.saving_throw_result = saving_throw_result
        self.open_reaction_window = open_reaction_window or OpenReactionWindow(
            encounter_repository=saving_throw_request.encounter_repository,
            definition_repository=ReactionDefinitionRepository(),
        )

    def execute(
        self,
        *,
        encounter_id: str,
        target_id: str,
        spell_id: str,
        base_roll: int | None = None,
        base_rolls: list[int] | None = None,
        damage_rolls: list[dict[str, Any]] | None = None,
        vantage: str = "normal",
        cast_level: int | None = None,
        description: str | None = None,
        additional_bonus: int = 0,
        voluntary_fail: bool = False,
        hp_change_on_failed_save: int | None = None,
        hp_change_on_success: int | None = None,
        damage_reason: str | None = None,
        damage_type: str | None = None,
        concentration_vantage: str = "normal",
        conditions_on_failed_save: list[str] | None = None,
        conditions_on_success: list[str] | None = None,
        note_on_failed_save: str | None = None,
        note_on_success: str | None = None,
        metamagic_options: dict[str, Any] | None = None,
        include_encounter_state: bool = False,
        metadata: dict[str, Any] | None = None,
        rolled_at: str | None = None,
    ) -> dict[str, Any]:
        """执行一次完整的单目标豁免型法术。

        当前版本只收口单目标链路：
        1. 声明施法并扣资源
        2. 生成豁免请求
        3. 根据目标数据自动算出豁免最终值
        4. 结算成功/失败及后续影响
        """
        cast = self.encounter_cast_spell.execute(
            encounter_id=encounter_id,
            spell_id=spell_id,
            target_ids=[target_id],
            cast_level=cast_level,
            reason=description,
            metamagic_options=metamagic_options,
        )

        request = self.saving_throw_request.execute(
            encounter_id=encounter_id,
            target_id=target_id,
            spell_id=spell_id,
            vantage=vantage,
            description=description,
            metamagic=cast.get("metamagic"),
        )

        roll_result = self.resolve_saving_throw.execute(
            encounter_id=encounter_id,
            roll_request=request,
            base_roll=base_roll,
            base_rolls=base_rolls,
            additional_bonus=additional_bonus,
            voluntary_fail=voluntary_fail,
            metadata=metadata,
            rolled_at=rolled_at,
        )

        reaction_window = self._maybe_open_failed_save_window(
            encounter_id=encounter_id,
            cast=cast,
            request=request,
            roll_result=roll_result,
            spell_definition=request.context.get("spell_definition"),
            damage_rolls=damage_rolls,
            cast_level=cast["cast_level"],
            hp_change_on_failed_save=hp_change_on_failed_save,
            hp_change_on_success=hp_change_on_success,
            damage_reason=damage_reason,
            damage_type=damage_type,
            concentration_vantage=concentration_vantage,
            conditions_on_failed_save=conditions_on_failed_save,
            conditions_on_success=conditions_on_success,
            note_on_failed_save=note_on_failed_save,
            note_on_success=note_on_success,
        )
        if reaction_window is not None:
            result = {
                "status": "waiting_reaction",
                "cast": cast,
                "request": request.to_dict(),
                "roll_result": roll_result.to_dict(),
                "pending_reaction_window": reaction_window["pending_reaction_window"],
                "reaction_requests": reaction_window["reaction_requests"],
            }
            if include_encounter_state:
                result["encounter_state"] = GetEncounterState(self.saving_throw_request.encounter_repository).execute(encounter_id)
            return result

        spell_definition = request.context.get("spell_definition")
        resolution = self.saving_throw_result.execute(
            encounter_id=encounter_id,
            roll_request=request,
            roll_result=roll_result,
            spell_definition=self._select_spell_definition_for_resolution(
                spell_definition=spell_definition,
                hp_change_on_failed_save=hp_change_on_failed_save,
                hp_change_on_success=hp_change_on_success,
                conditions_on_failed_save=conditions_on_failed_save,
                conditions_on_success=conditions_on_success,
                note_on_failed_save=note_on_failed_save,
                note_on_success=note_on_success,
            ),
            damage_rolls=damage_rolls,
            cast_level=cast["cast_level"],
            hp_change_on_failed_save=hp_change_on_failed_save,
            hp_change_on_success=hp_change_on_success,
            damage_reason=damage_reason,
            damage_type=damage_type,
            concentration_vantage=concentration_vantage,
            conditions_on_failed_save=conditions_on_failed_save,
            conditions_on_success=conditions_on_success,
            note_on_failed_save=note_on_failed_save,
            note_on_success=note_on_success,
        )

        result = {
            "cast": cast,
            "request": request.to_dict(),
            "roll_result": roll_result.to_dict(),
            "resolution": resolution,
        }
        if include_encounter_state:
            result["encounter_state"] = GetEncounterState(self.saving_throw_request.encounter_repository).execute(encounter_id)
        return result

    def _maybe_open_failed_save_window(
        self,
        *,
        encounter_id: str,
        cast: dict[str, Any],
        request: Any,
        roll_result: Any,
        spell_definition: Any,
        damage_rolls: list[dict[str, Any]] | None,
        cast_level: int | None,
        hp_change_on_failed_save: int | None,
        hp_change_on_success: int | None,
        damage_reason: str | None,
        damage_type: str | None,
        concentration_vantage: str,
        conditions_on_failed_save: list[str] | None,
        conditions_on_success: list[str] | None,
        note_on_failed_save: str | None,
        note_on_success: str | None,
    ) -> dict[str, Any] | None:
        save_dc = request.context.get("save_dc")
        if not isinstance(save_dc, int) or roll_result.final_total >= save_dc:
            return None

        encounter = self.saving_throw_request.encounter_repository.get(encounter_id)
        if encounter is None:
            raise ValueError(f"encounter '{encounter_id}' not found")
        target = encounter.entities.get(request.actor_entity_id)
        if target is None:
            raise ValueError(f"target '{request.actor_entity_id}' not found in encounter")

        countercharm_conditions = self._resolve_countercharm_conditions(
            spell_definition=spell_definition,
            conditions_on_failed_save=conditions_on_failed_save,
        )
        request_payloads: dict[str, dict[str, Any]] = {
            target.entity_id: {
                "indomitable": {
                    "save_ability": request.context.get("save_ability"),
                    "save_dc": save_dc,
                    "vantage": request.context.get("vantage", "normal"),
                }
            }
        }
        if countercharm_conditions:
            for entity in encounter.entities.values():
                if entity.entity_id == target.entity_id or entity.side != target.side:
                    continue
                request_payloads[entity.entity_id] = {
                    "countercharm": {
                        "target_entity_id": target.entity_id,
                        "save_ability": request.context.get("save_ability"),
                        "save_dc": save_dc,
                        "vantage": request.context.get("vantage", "normal"),
                    }
                }

        trigger_event = {
            "event_id": f"evt_failed_save_{request.request_id}",
            "trigger_type": "failed_save",
            "host_action_type": "save",
            "host_action_id": request.request_id,
            "host_action_snapshot": {
                "phase": "after_failed_save",
                "target_entity_id": target.entity_id,
                "save_ability": request.context.get("save_ability"),
                "save_dc": save_dc,
                "countercharm_trigger_conditions": countercharm_conditions,
                "cast": cast,
                "roll_request": request.to_dict(),
                "roll_result": roll_result.to_dict(),
                "saving_throw_result_args": {
                    "spell_definition": self._select_spell_definition_for_resolution(
                        spell_definition=spell_definition,
                        hp_change_on_failed_save=hp_change_on_failed_save,
                        hp_change_on_success=hp_change_on_success,
                        conditions_on_failed_save=conditions_on_failed_save,
                        conditions_on_success=conditions_on_success,
                        note_on_failed_save=note_on_failed_save,
                        note_on_success=note_on_success,
                    ),
                    "damage_rolls": damage_rolls,
                    "cast_level": cast_level,
                    "hp_change_on_failed_save": hp_change_on_failed_save,
                    "hp_change_on_success": hp_change_on_success,
                    "damage_reason": damage_reason,
                    "damage_type": damage_type,
                    "concentration_vantage": concentration_vantage,
                    "conditions_on_failed_save": conditions_on_failed_save,
                    "conditions_on_success": conditions_on_success,
                    "note_on_failed_save": note_on_failed_save,
                    "note_on_success": note_on_success,
                },
            },
            "target_entity_id": target.entity_id,
            "request_payloads": request_payloads,
        }
        result = self.open_reaction_window.execute(encounter_id=encounter_id, trigger_event=trigger_event)
        if result.get("status") != "waiting_reaction":
            return None
        return result

    def _resolve_countercharm_conditions(
        self,
        *,
        spell_definition: Any,
        conditions_on_failed_save: list[str] | None,
    ) -> list[str]:
        resolved: list[str] = []
        if isinstance(spell_definition, dict):
            failed_outcome = spell_definition.get("failed_save_outcome")
            if isinstance(failed_outcome, dict):
                raw_conditions = failed_outcome.get("apply_conditions", failed_outcome.get("conditions", []))
                if isinstance(raw_conditions, list):
                    for condition in raw_conditions:
                        if isinstance(condition, str) and condition.strip():
                            resolved.append(condition.strip().lower())
        if isinstance(conditions_on_failed_save, list):
            for condition in conditions_on_failed_save:
                if isinstance(condition, str) and condition.strip():
                    resolved.append(condition.strip().lower())
        return [condition for condition in dict.fromkeys(resolved) if condition in {"charmed", "frightened"}]

    def _select_spell_definition_for_resolution(
        self,
        *,
        spell_definition: Any,
        hp_change_on_failed_save: int | None,
        hp_change_on_success: int | None,
        conditions_on_failed_save: list[str] | None,
        conditions_on_success: list[str] | None,
        note_on_failed_save: str | None,
        note_on_success: str | None,
    ) -> dict[str, Any] | None:
        if not isinstance(spell_definition, dict):
            return None
        if self._has_legacy_effect_inputs(
            hp_change_on_failed_save=hp_change_on_failed_save,
            hp_change_on_success=hp_change_on_success,
            conditions_on_failed_save=conditions_on_failed_save,
            conditions_on_success=conditions_on_success,
            note_on_failed_save=note_on_failed_save,
            note_on_success=note_on_success,
        ):
            return None
        return spell_definition

    def _has_legacy_effect_inputs(
        self,
        *,
        hp_change_on_failed_save: int | None,
        hp_change_on_success: int | None,
        conditions_on_failed_save: list[str] | None,
        conditions_on_success: list[str] | None,
        note_on_failed_save: str | None,
        note_on_success: str | None,
    ) -> bool:
        return any(
            [
                hp_change_on_failed_save is not None,
                hp_change_on_success is not None,
                bool(conditions_on_failed_save),
                bool(conditions_on_success),
                note_on_failed_save is not None,
                note_on_success is not None,
            ]
        )
