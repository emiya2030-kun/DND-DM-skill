"""豁免结算测试：覆盖旧接口兼容与 outcome 新主路径红灯。"""

import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import (
    AppendEvent,
    ResolveSavingThrow,
    RequestConcentrationCheck,
    SavingThrowRequest,
    SavingThrowResult,
    UpdateConditions,
    UpdateEncounterNotes,
    UpdateHp,
)


@contextmanager
def make_repositories() -> Iterator[tuple[EncounterRepository, EventRepository]]:
    """创建测试仓储，并确保在临时目录释放前关闭文件句柄。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        try:
            yield encounter_repo, event_repo
        finally:
            try:
                encounter_repo.close()
            finally:
                event_repo.close()


def build_spell_definitions() -> dict[str, dict]:
    """构造豁免型法术 outcome 测试模板。"""
    return {
        "blindness_deafness": {
            "id": "blindness_deafness",
            "name": "Blindness/Deafness",
            "level": 2,
            "save_ability": "con",
            "failed_save_outcome": {
                "damage_parts": [],
                "conditions": ["blinded"],
                "note": None,
            },
            "successful_save_outcome": {
                "damage_parts": [],
                "conditions": [],
                "note": None,
            },
            "scaling": {
                "cantrip_by_level": None,
                "slot_level_bonus": None,
            },
        },
        "burning_hands": {
            "id": "burning_hands",
            "name": "Burning Hands",
            "level": 1,
            "save_ability": "dex",
            "failed_save_outcome": {
                "damage_parts": [
                    {
                        "source": "spell:burning_hands:failed:part_0",
                        "formula": "3d6",
                        "damage_type": "fire",
                    }
                ],
                "conditions": [],
                "note": None,
            },
            "successful_save_outcome": {
                "damage_parts_mode": "same_as_failed",
                "damage_multiplier": 0.5,
                "conditions": [],
                "note": None,
            },
            "scaling": {
                "cantrip_by_level": None,
                "slot_level_bonus": None,
            },
        },
        "sacred_flame": {
            "id": "sacred_flame",
            "name": "Sacred Flame",
            "level": 0,
            "save_ability": "dex",
            "failed_save_outcome": {
                "damage_parts": [
                    {
                        "source": "spell:sacred_flame:failed:part_0",
                        "formula": "1d8",
                        "damage_type": "radiant",
                    }
                ],
                "conditions": [],
                "note": None,
            },
            "successful_save_outcome": {
                "damage_parts": [],
                "conditions": [],
                "note": None,
            },
            "scaling": {
                "cantrip_by_level": [
                    {"caster_level": 5, "replace_formula": "2d8"},
                    {"caster_level": 11, "replace_formula": "3d8"},
                    {"caster_level": 17, "replace_formula": "4d8"},
                ],
                "slot_level_bonus": None,
            },
        },
    }


def build_caster() -> EncounterEntity:
    """构造豁免结算测试用施法者。"""
    spell_definitions = build_spell_definitions()
    return EncounterEntity(
        entity_id="ent_ally_eric_001",
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        source_ref={
            "spellcasting_ability": "cha",
            "caster_level": 3,
            "spell_definitions": spell_definitions,
        },
        ability_mods={"cha": 3},
        proficiency_bonus=2,
        spells=[
            {
                "spell_id": "blindness_deafness",
                "name": "Blindness/Deafness",
                "level": 2,
                "save_ability": "con",
                "requires_attack_roll": False,
                "spell_definition": spell_definitions["blindness_deafness"],
            },
            {
                "spell_id": "burning_hands",
                "name": "Burning Hands",
                "level": 1,
                "save_ability": "dex",
                "requires_attack_roll": False,
                "half_on_success": True,
                "spell_definition": spell_definitions["burning_hands"],
            },
            {
                "spell_id": "sacred_flame",
                "name": "Sacred Flame",
                "level": 0,
                "save_ability": "dex",
                "requires_attack_roll": False,
                "spell_definition": spell_definitions["sacred_flame"],
            },
        ],
    )


def build_target() -> EncounterEntity:
    """构造豁免结算测试用目标。"""
    return EncounterEntity(
        entity_id="ent_enemy_iron_duster_001",
        name="Iron Duster",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 4, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
    )


def build_encounter() -> Encounter:
    """构造豁免结算测试用 encounter。"""
    caster = build_caster()
    target = build_target()
    return Encounter(
        encounter_id="enc_save_result_test",
        name="Saving Throw Result Test Encounter",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, target.entity_id],
        entities={caster.entity_id: caster, target.entity_id: target},
        map=EncounterMap(
            map_id="map_save_result_test",
            name="Saving Throw Result Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class SavingThrowResultTests(unittest.TestCase):
    def test_execute_on_failed_save_applies_condition_and_note(self) -> None:
        """测试目标豁免失败后，会自动加 condition 和 encounter note。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="blindness_deafness",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_conditions=UpdateConditions(encounter_repo, append_event),
                update_encounter_notes=UpdateEncounterNotes(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=6,
                ),
                conditions_on_failed_save=["blinded"],
                note_on_failed_save="Iron Duster 现在被致盲了！",
            )

            updated = encounter_repo.get("enc_save_result_test")
            self.assertIsNotNone(updated)
            self.assertFalse(result["success"])
            self.assertEqual(result["comparison"]["left_value"], 6)
            self.assertEqual(result["comparison"]["right_value"], 13)
            self.assertFalse(result["comparison"]["passed"])
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["blinded"])
            self.assertEqual(updated.encounter_notes[0]["note"], "Iron Duster 现在被致盲了！")
            self.assertEqual(len(result["condition_updates"]), 1)

    def test_execute_on_success_can_apply_reduced_damage(self) -> None:
        """测试目标豁免成功后，仍可按半伤等规则继续扣血。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=15,
                ),
                hp_change_on_failed_save=8,
                hp_change_on_success=4,
                damage_reason="Burning Hands damage",
                damage_type="fire",
            )

            updated = encounter_repo.get("enc_save_result_test")
            self.assertIsNotNone(updated)
            self.assertTrue(result["success"])
            self.assertEqual(result["comparison"]["left_value"], 15)
            self.assertEqual(result["comparison"]["right_value"], 13)
            self.assertTrue(result["comparison"]["passed"])
            self.assertEqual(result["vantage"], "normal")
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].hp["current"], 14)
            self.assertEqual(result["hp_update"]["event_type"], "damage_applied")

    def test_execute_exposes_advantage_info(self) -> None:
        """测试豁免结算结果会保留优势和实际采用的骰值。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
                vantage="advantage",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_rolls=[4, 17],
                ),
                hp_change_on_failed_save=8,
                hp_change_on_success=4,
                damage_reason="Burning Hands damage",
                damage_type="fire",
            )

            self.assertEqual(result["vantage"], "advantage")
            self.assertEqual(result["chosen_roll"], 17)
            self.assertTrue(result["success"])

    def test_execute_auto_creates_concentration_request_after_damage(self) -> None:
        """测试豁免型法术造成伤害后，如果目标正在专注，会自动生成专注检定请求。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_iron_duster_001"]
            target.combat_flags = {"is_active": True, "is_defeated": False, "is_concentrating": True}
            target.ability_mods = {"dex": 2, "con": 1}
            target.save_proficiencies = ["con"]
            target.proficiency_bonus = 2
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(
                    encounter_repo,
                    append_event,
                    RequestConcentrationCheck(encounter_repo),
                ),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=15,
                ),
                hp_change_on_failed_save=8,
                hp_change_on_success=4,
                damage_reason="Burning Hands damage",
                damage_type="fire",
                concentration_vantage="disadvantage",
            )

            self.assertEqual(result["hp_update"]["concentration_check_request"]["roll_type"], "concentration_check")
            self.assertEqual(
                result["hp_update"]["concentration_check_request"]["context"]["vantage"],
                "disadvantage",
            )

    def test_execute_resolves_failed_outcome_damage_parts(self) -> None:
        """测试失败 outcome 会走 damage_parts 结算与扣血。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=6,
                ),
                spell_definition=build_spell_definitions()["burning_hands"],
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
            )

            updated = encounter_repo.get("enc_save_result_test")
            self.assertIsNotNone(updated)

            self.assertFalse(result["success"])
            self.assertEqual(result["selected_outcome"], "failed_save")
            self.assertEqual(result["damage_resolution"]["total_damage"], 15)
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].hp["current"], 3)

    def test_execute_resolves_successful_half_damage_outcome(self) -> None:
        """测试成功 outcome 可以按同骰半伤结算。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=15,
                ),
                spell_definition=build_spell_definitions()["burning_hands"],
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
            )

            updated = encounter_repo.get("enc_save_result_test")
            self.assertIsNotNone(updated)

            self.assertTrue(result["success"])
            self.assertEqual(result["selected_outcome"], "successful_save")
            self.assertEqual(result["damage_resolution"]["total_damage"], 7)
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].hp["current"], 11)

    def test_execute_resolves_failed_outcome_condition_only(self) -> None:
        """测试失败 outcome 仅状态时不会出现伤害分解。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="blindness_deafness",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_conditions=UpdateConditions(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=6,
                ),
                spell_definition=build_spell_definitions()["blindness_deafness"],
            )

            updated = encounter_repo.get("enc_save_result_test")
            self.assertIsNotNone(updated)

            self.assertFalse(result["success"])
            self.assertEqual(result["selected_outcome"], "failed_save")
            self.assertNotIn("damage_resolution", result)
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["blinded"])

    def test_execute_resolves_successful_outcome_without_damage(self) -> None:
        """测试成功无伤 outcome 会忽略非法 damage_rolls。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="sacred_flame",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=15,
                ),
                spell_definition=build_spell_definitions()["sacred_flame"],
                damage_rolls=[
                    {"source": "spell:sacred_flame:failed:part_9", "rolls": [4]},
                ],
            )

            updated = encounter_repo.get("enc_save_result_test")
            self.assertIsNotNone(updated)

            self.assertTrue(result["success"])
            self.assertEqual(result["selected_outcome"], "successful_save")
            self.assertNotIn("damage_resolution", result)
            self.assertNotIn("hp_update", result)
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].hp["current"], 18)

    def test_execute_keeps_outcome_path_when_only_damage_metadata_is_provided(self) -> None:
        """测试仅传 damage_reason / damage_type 时，仍走 outcome 主路径。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=6,
                ),
                spell_definition=build_spell_definitions()["burning_hands"],
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
                damage_reason="燃烧之手火焰灼烧",
                damage_type="fire",
            )

            self.assertEqual(result["selected_outcome"], "failed_save")
            self.assertEqual(result["damage_resolution"]["total_damage"], 15)
            self.assertEqual(result["hp_update"]["reason"], "燃烧之手火焰灼烧")
            self.assertIsNone(result["hp_update"]["damage_type"])

    def test_execute_rejects_mixing_spell_definition_with_legacy_effect_inputs(self) -> None:
        """测试显式传模板时，不能再混用旧效果字段。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            with self.assertRaisesRegex(
                ValueError,
                "spell_definition cannot be combined with legacy save spell effect inputs",
            ):
                service.execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    roll_result=ResolveSavingThrow(encounter_repo).execute(
                        encounter_id="enc_save_result_test",
                        roll_request=request,
                        base_roll=6,
                    ),
                    spell_definition=build_spell_definitions()["burning_hands"],
                    damage_rolls=[
                        {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                    ],
                    hp_change_on_failed_save=8,
                )

    def test_execute_rejects_unknown_damage_roll_source_for_damage_outcome(self) -> None:
        """测试需要伤害时，非法 source 会报错。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            with self.assertRaisesRegex(ValueError, "unknown_damage_roll_sources: spell:burning_hands:failed:part_9"):
                service.execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    roll_result=ResolveSavingThrow(encounter_repo).execute(
                        encounter_id="enc_save_result_test",
                        roll_request=request,
                        base_roll=6,
                    ),
                    spell_definition=build_spell_definitions()["burning_hands"],
                    damage_rolls=[
                        {"source": "spell:burning_hands:failed:part_9", "rolls": [4]},
                    ],
                )

    def test_execute_auto_fails_for_paralyzed_target(self) -> None:
        """测试 SavingThrowResult 会正确记录虚弱目标的自动失败。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_iron_duster_001"]
            target.conditions = ["paralyzed"]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id=target.entity_id,
                spell_id="burning_hands",
            )
            service = SavingThrowResult(
                encounter_repo,
                append_event,
                update_hp=UpdateHp(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=20,
                ),
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
                damage_reason="Burn",
            )

            self.assertFalse(result["success"])
            self.assertEqual(result["final_total"], 0)
            self.assertEqual(result["comparison"]["left_value"], 0)

    def test_execute_reflects_exhaustion_penalty_on_success(self) -> None:
        """测试疲劳等级会降低豁免总值但仍能通过检定。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_iron_duster_001"]
            target.conditions = ["exhaustion:2"]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            request = SavingThrowRequest(encounter_repo).execute(
                encounter_id="enc_save_result_test",
                target_id=target.entity_id,
                spell_id="burning_hands",
            )
            service = SavingThrowResult(encounter_repo, append_event)

            result = service.execute(
                encounter_id="enc_save_result_test",
                roll_request=request,
                roll_result=ResolveSavingThrow(encounter_repo).execute(
                    encounter_id="enc_save_result_test",
                    roll_request=request,
                    base_roll=17,
                ),
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
                damage_reason="Burn",
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["final_total"], 13)
            self.assertEqual(result["comparison"]["left_value"], 13)
