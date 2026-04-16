"""完整豁免型法术执行测试：覆盖 outcome、结构化伤害与成长。"""

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
    EncounterCastSpell,
    ExecuteSaveSpell,
    ResolveSavingThrow,
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
        "fireball": {
            "id": "fireball",
            "name": "Fireball",
            "level": 3,
            "save_ability": "dex",
            "failed_save_outcome": {
                "damage_parts": [
                    {
                        "source": "spell:fireball:failed:part_0",
                        "formula": "8d6",
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
                "slot_level_bonus": {
                    "base_slot_level": 3,
                    "additional_damage_parts": [
                        {
                            "source": "spell:fireball:slot_scaling",
                            "formula_per_extra_level": "1d6",
                            "damage_type": "fire",
                        }
                    ],
                },
            },
        },
    }


def build_caster() -> EncounterEntity:
    """构造完整豁免型法术测试用施法者。"""
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
        resources={
            "spell_slots": {
                "1": {"max": 4, "remaining": 4},
                "2": {"max": 3, "remaining": 3},
                "3": {"max": 2, "remaining": 2},
                "4": {"max": 1, "remaining": 1},
            }
        },
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
            {
                "spell_id": "fireball",
                "name": "Fireball",
                "level": 3,
                "save_ability": "dex",
                "requires_attack_roll": False,
                "spell_definition": spell_definitions["fireball"],
            },
        ],
    )


def build_target() -> EncounterEntity:
    """构造完整豁免型法术测试用目标。"""
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
        ability_mods={"con": 2, "dex": 2},
        proficiency_bonus=2,
        save_proficiencies=[],
    )


def build_encounter() -> Encounter:
    """构造完整豁免型法术测试用 encounter。"""
    caster = build_caster()
    target = build_target()
    return Encounter(
        encounter_id="enc_execute_save_spell_test",
        name="Execute Save Spell Test Encounter",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, target.entity_id],
        entities={caster.entity_id: caster, target.entity_id: target},
        map=EncounterMap(
            map_id="map_execute_save_spell_test",
            name="Execute Save Spell Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class ExecuteSaveSpellTests(unittest.TestCase):
    def test_execute_runs_full_failed_save_flow(self) -> None:
        """测试完整入口会串起施法、豁免失败、condition 和 note 更新。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_conditions=UpdateConditions(encounter_repo, append_event),
                    update_encounter_notes=UpdateEncounterNotes(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="blindness_deafness",
                base_roll=6,
                note_on_failed_save="Iron Duster 现在被致盲了！",
                conditions_on_failed_save=["blinded"],
            )

            updated = encounter_repo.get("enc_execute_save_spell_test")
            self.assertIsNotNone(updated)

            self.assertEqual(result["cast"]["spell_name"], "Blindness/Deafness")
            self.assertEqual(result["request"]["context"]["save_dc"], 13)
            self.assertEqual(result["roll_result"]["final_total"], 8)
            self.assertFalse(result["resolution"]["success"])
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["blinded"])
            self.assertEqual(updated.encounter_notes[0]["note"], "Iron Duster 现在被致盲了！")
            self.assertEqual(len(event_repo.list_by_encounter("enc_execute_save_spell_test")), 4)

    def test_execute_runs_full_success_flow_with_structured_damage(self) -> None:
        """测试完整入口会在豁免成功时按 damage_rolls + outcome 继续造成半伤。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
                base_roll=15,
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
            )

            updated = encounter_repo.get("enc_execute_save_spell_test")
            self.assertIsNotNone(updated)

            self.assertTrue(result["resolution"]["success"])
            self.assertEqual(result["resolution"]["selected_outcome"], "successful_save")
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 7)
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].hp["current"], 11)
            self.assertEqual(len(event_repo.list_by_encounter("enc_execute_save_spell_test")), 3)

    def test_execute_runs_failed_save_condition_only_outcome(self) -> None:
        """测试豁免失败且仅附状态的 outcome 会自动加 condition。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_conditions=UpdateConditions(encounter_repo, append_event),
                    update_encounter_notes=UpdateEncounterNotes(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="blindness_deafness",
                base_roll=6,
            )

            updated = encounter_repo.get("enc_execute_save_spell_test")
            self.assertIsNotNone(updated)

            self.assertFalse(result["resolution"]["success"])
            self.assertEqual(result["resolution"]["selected_outcome"], "failed_save")
            self.assertNotIn("damage_resolution", result["resolution"])
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["blinded"])

    def test_execute_can_use_global_hold_person_template_and_attach_turn_effect(self) -> None:
        """测试完整入口可直接用全局模板，并在失败时挂上回合末再豁免效果。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.spells = []
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_conditions=UpdateConditions(encounter_repo, append_event),
                    update_encounter_notes=UpdateEncounterNotes(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="hold_person",
                cast_level=2,
                base_roll=4,
            )

            updated = encounter_repo.get("enc_execute_save_spell_test")
            self.assertIsNotNone(updated)
            target = updated.entities["ent_enemy_iron_duster_001"]

            self.assertFalse(result["resolution"]["success"])
            self.assertEqual(target.conditions, ["paralyzed"])
            self.assertEqual(len(target.turn_effects), 1)
            self.assertEqual(target.turn_effects[0]["trigger"], "end_of_turn")
            self.assertEqual(target.turn_effects[0]["save"]["dc"], 13)
            self.assertEqual(len(updated.spell_instances), 1)
            self.assertEqual(updated.spell_instances[0]["spell_id"], "hold_person")
            self.assertEqual(updated.spell_instances[0]["targets"][0]["entity_id"], "ent_enemy_iron_duster_001")
            self.assertEqual(
                updated.spell_instances[0]["targets"][0]["turn_effect_ids"],
                [target.turn_effects[0]["effect_id"]],
            )

    def test_execute_applies_cantrip_scaling_before_damage_resolution(self) -> None:
        """测试戏法会先按施法者等级成长，再进入伤害分解。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.source_ref["caster_level"] = 5
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="sacred_flame",
                base_roll=4,
                damage_rolls=[
                    {"source": "spell:sacred_flame:failed:part_0", "rolls": [6, 7]},
                ],
            )

            self.assertEqual(
                result["resolution"]["damage_resolution"]["parts"][0]["resolved_formula"],
                "2d8",
            )
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 13)

    def test_execute_applies_slot_level_bonus_damage_parts(self) -> None:
        """测试高环施法会追加 slot scaling 的伤害段。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="fireball",
                cast_level=4,
                base_roll=5,
                damage_rolls=[
                    {"source": "spell:fireball:failed:part_0", "rolls": [6, 5, 4, 3, 2, 1, 6, 5]},
                    {"source": "spell:fireball:slot_scaling", "rolls": [4]},
                ],
            )

            self.assertEqual(len(result["resolution"]["damage_resolution"]["parts"]), 2)
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 36)

    def test_execute_ignores_invalid_damage_rolls_when_successful_outcome_has_no_damage(self) -> None:
        """测试成功无伤时即使 damage_rolls 非法 source，也应被忽略。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="sacred_flame",
                base_roll=15,
                damage_rolls=[
                    {"source": "spell:sacred_flame:failed:part_9", "rolls": [4]},
                ],
            )

            self.assertTrue(result["resolution"]["success"])
            self.assertEqual(result["resolution"]["selected_outcome"], "successful_save")
            self.assertNotIn("damage_resolution", result["resolution"])
            self.assertNotIn("hp_update", result["resolution"])

    def test_execute_keeps_outcome_path_when_only_damage_metadata_is_provided(self) -> None:
        """测试完整入口仅传 damage_reason / damage_type 时，仍走 outcome 主路径。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
                base_roll=6,
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
                damage_reason="燃烧之手火焰灼烧",
                damage_type="fire",
            )

            self.assertEqual(result["resolution"]["selected_outcome"], "failed_save")
            self.assertEqual(result["resolution"]["damage_resolution"]["total_damage"], 15)
            self.assertEqual(result["resolution"]["hp_update"]["reason"], "燃烧之手火焰灼烧")
            self.assertIsNone(result["resolution"]["hp_update"]["damage_type"])

    def test_execute_supports_advantage_saving_throw(self) -> None:
        """测试完整豁免法术入口支持优势豁免。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
                base_rolls=[3, 16],
                vantage="advantage",
                hp_change_on_failed_save=8,
                hp_change_on_success=4,
                damage_reason="Burning Hands damage",
                damage_type="fire",
            )

            self.assertEqual(result["request"]["context"]["vantage"], "advantage")
            self.assertEqual(result["roll_result"]["dice_rolls"]["chosen_roll"], 16)
            self.assertEqual(result["resolution"]["vantage"], "advantage")
            self.assertTrue(result["resolution"]["success"])

    def test_execute_can_include_latest_encounter_state(self) -> None:
        """测试完整豁免法术入口只在最外层返回最新前端状态。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="burning_hands",
                base_roll=15,
                hp_change_on_failed_save=8,
                hp_change_on_success=4,
                damage_reason="Burning Hands damage",
                damage_type="fire",
                include_encounter_state=True,
            )

            self.assertIn("encounter_state", result)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_execute_save_spell_test")
            self.assertEqual(result["encounter_state"]["turn_order"][1]["hp"], "14/18 HP (78%) [HEALTHY]")

    def test_execute_save_spell_auto_fails_for_paralyzed_target(self) -> None:
        """测试 ExecuteSaveSpell 会在目标麻痹时直接算失败。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_iron_duster_001"]
            target.conditions = ["paralyzed"]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id=target.entity_id,
                spell_id="burning_hands",
                base_roll=20,
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
                damage_reason="Burn",
            )

            self.assertFalse(result["resolution"]["success"])
            self.assertEqual(result["roll_result"]["final_total"], 0)
            self.assertTrue(result["roll_result"]["metadata"]["auto_fail"])

    def test_execute_save_spell_applies_exhaustion_penalty(self) -> None:
        """测试 ExecuteSaveSpell 会把疲劳 D20 惩罚反映在 Final Total 上。"""
        with make_repositories() as (encounter_repo, event_repo):
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_iron_duster_001"]
            target.conditions = ["exhaustion:2"]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, append_event),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    append_event,
                    update_hp=UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_execute_save_spell_test",
                target_id=target.entity_id,
                spell_id="burning_hands",
                base_roll=17,
                damage_rolls=[
                    {"source": "spell:burning_hands:failed:part_0", "rolls": [6, 5, 4]},
                ],
                damage_reason="Burn",
            )

            self.assertTrue(result["resolution"]["success"])
            self.assertEqual(result["roll_result"]["final_total"], 15)
            self.assertEqual(result["roll_result"]["metadata"]["d20_penalty"], 4)


if __name__ == "__main__":
    unittest.main()
