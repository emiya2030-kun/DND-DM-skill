from __future__ import annotations

from typing import Any

from tools.services.combat.save_spell.resolve_saving_throw import ResolveSavingThrow
from tools.services.combat.save_spell.saving_throw_request import SavingThrowRequest
from tools.services.combat.save_spell.saving_throw_result import SavingThrowResult
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
    ):
        self.encounter_cast_spell = encounter_cast_spell
        self.saving_throw_request = saving_throw_request
        self.resolve_saving_throw = resolve_saving_throw
        self.saving_throw_result = saving_throw_result

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
