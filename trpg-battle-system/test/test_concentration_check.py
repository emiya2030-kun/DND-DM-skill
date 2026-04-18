"""专注检定测试：覆盖请求生成、优势结算、失败打断专注和完整入口。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import (
    AppendEvent,
    ExecuteConcentrationCheck,
    RequestConcentrationCheck,
    ResolveConcentrationCheck,
    ResolveConcentrationResult,
)


def build_target() -> EncounterEntity:
    """构造专注检定测试用目标。"""
    return EncounterEntity(
        entity_id="ent_pc_eric_001",
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"con": 2},
        proficiency_bonus=3,
        save_proficiencies=["con"],
        combat_flags={"is_active": True, "is_defeated": False, "is_concentrating": True},
    )


def build_source() -> EncounterEntity:
    """构造造成伤害的来源实体。"""
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
    """构造专注检定测试用 encounter。"""
    target = build_target()
    source = build_source()
    return Encounter(
        encounter_id="enc_concentration_test",
        name="Concentration Test Encounter",
        status="active",
        round=1,
        current_entity_id=target.entity_id,
        turn_order=[target.entity_id, source.entity_id],
        entities={target.entity_id: target, source.entity_id: source},
        map=EncounterMap(
            map_id="map_concentration_test",
            name="Concentration Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class ConcentrationCheckTests(unittest.TestCase):
    def test_request_concentration_check_builds_dc_from_damage(self) -> None:
        """测试专注检定请求会根据实际伤害计算 save_dc。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = RequestConcentrationCheck(repo).execute(
                encounter_id="enc_concentration_test",
                target_id="ent_pc_eric_001",
                damage_taken=18,
                source_entity_id="ent_enemy_iron_duster_001",
            )

            self.assertEqual(request.roll_type, "concentration_check")
            self.assertEqual(request.context["save_dc"], 10)
            self.assertEqual(request.context["save_ability"], "con")
            self.assertEqual(request.context["vantage"], "normal")
            repo.close()

    def test_request_concentration_check_grants_advantage_with_eldritch_mind(self) -> None:
        """测试魔能意志会让专注检定具有优势。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target = encounter.entities["ent_pc_eric_001"]
            target.class_features = {
                "warlock": {
                    "level": 2,
                    "eldritch_invocations": {
                        "selected": [{"invocation_id": "eldritch_mind"}],
                    },
                },
            }
            repo.save(encounter)

            request = RequestConcentrationCheck(repo).execute(
                encounter_id="enc_concentration_test",
                target_id="ent_pc_eric_001",
                damage_taken=18,
            )

            self.assertEqual(request.context["vantage"], "advantage")
            repo.close()

    def test_resolve_concentration_check_uses_advantage(self) -> None:
        """测试优势专注检定会取两次 d20 中更高的结果。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = RequestConcentrationCheck(repo).execute(
                encounter_id="enc_concentration_test",
                target_id="ent_pc_eric_001",
                damage_taken=12,
                vantage="advantage",
            )
            result = ResolveConcentrationCheck(repo).execute(
                encounter_id="enc_concentration_test",
                roll_request=request,
                base_rolls=[7, 15],
            )

            self.assertEqual(result.final_total, 20)
            self.assertEqual(result.metadata["chosen_roll"], 15)
            self.assertEqual(result.metadata["check_bonus"], 5)
            repo.close()

    def test_resolve_concentration_check_uses_class_template_save_proficiency(self) -> None:
        """测试职业模板提供的 CON 豁免熟练也会作用于专注检定。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target = encounter.entities["ent_pc_eric_001"]
            target.class_features = {"sorcerer": {"level": 1}}
            target.save_proficiencies = []
            repo.save(encounter)

            request = RequestConcentrationCheck(repo).execute(
                encounter_id="enc_concentration_test",
                target_id="ent_pc_eric_001",
                damage_taken=12,
            )
            result = ResolveConcentrationCheck(repo).execute(
                encounter_id="enc_concentration_test",
                roll_request=request,
                base_rolls=[10],
            )

            self.assertEqual(result.final_total, 15)
            self.assertTrue(result.metadata["check_bonus_breakdown"]["is_proficient"])
            self.assertEqual(result.metadata["check_bonus_breakdown"]["proficiency_bonus_applied"], 3)
            repo.close()

    def test_resolve_concentration_result_breaks_concentration_on_failure(self) -> None:
        """测试专注检定失败时会把 is_concentrating 改成 False。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            request = RequestConcentrationCheck(encounter_repo).execute(
                encounter_id="enc_concentration_test",
                target_id="ent_pc_eric_001",
                damage_taken=24,
            )
            roll_result = ResolveConcentrationCheck(encounter_repo).execute(
                encounter_id="enc_concentration_test",
                roll_request=request,
                base_rolls=[3],
            )
            result = ResolveConcentrationResult(encounter_repo, append_event).execute(
                encounter_id="enc_concentration_test",
                roll_request=request,
                roll_result=roll_result,
            )

            updated = encounter_repo.get("enc_concentration_test")
            assert updated is not None
            self.assertFalse(result["success"])
            self.assertFalse(updated.entities["ent_pc_eric_001"].combat_flags["is_concentrating"])
            self.assertIn("break_event_id", result)
            encounter_repo.close()
            event_repo.close()

    def test_execute_concentration_check_runs_full_flow(self) -> None:
        """测试完整入口会串起请求、结算和专注状态更新。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteConcentrationCheck(
                RequestConcentrationCheck(encounter_repo),
                ResolveConcentrationCheck(encounter_repo),
                ResolveConcentrationResult(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_concentration_test",
                target_id="ent_pc_eric_001",
                damage_taken=18,
                base_rolls=[4],
                source_entity_id="ent_enemy_iron_duster_001",
            )

            updated = encounter_repo.get("enc_concentration_test")
            assert updated is not None
            self.assertEqual(result["request"]["context"]["save_dc"], 10)
            self.assertEqual(result["roll_result"]["final_total"], 9)
            self.assertFalse(result["resolution"]["success"])
            self.assertFalse(updated.entities["ent_pc_eric_001"].combat_flags["is_concentrating"])
            self.assertEqual(len(event_repo.list_by_encounter("enc_concentration_test")), 2)
            encounter_repo.close()
            event_repo.close()

    def test_execute_concentration_check_can_include_latest_encounter_state(self) -> None:
        """测试完整专注检定入口只在最外层返回最新前端状态。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ExecuteConcentrationCheck(
                RequestConcentrationCheck(encounter_repo),
                ResolveConcentrationCheck(encounter_repo),
                ResolveConcentrationResult(encounter_repo, append_event),
            )

            result = service.execute(
                encounter_id="enc_concentration_test",
                target_id="ent_pc_eric_001",
                damage_taken=18,
                base_rolls=[4],
                source_entity_id="ent_enemy_iron_duster_001",
                include_encounter_state=True,
            )

            self.assertIn("encounter_state", result)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_concentration_test")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["conditions"], "无状态")
            encounter_repo.close()
            event_repo.close()

    def test_resolve_concentration_result_clears_attached_spell_runtime_on_failure(self) -> None:
        """测试专注失败会清掉该施法者专注法术实例挂出的状态与持续效果。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_iron_duster_001"]
            target.conditions = ["paralyzed"]
            target.turn_effects = [
                {
                    "effect_id": "effect_hold_person_001",
                    "name": "Hold Person Ongoing Save",
                    "source_entity_id": "ent_pc_eric_001",
                    "source_name": "Eric",
                    "source_ref": "hold_person",
                    "trigger": "end_of_turn",
                    "save": {"ability": "wis", "dc": 13, "on_success_remove_effect": True},
                    "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": ["paralyzed"]},
                    "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                    "remove_after_trigger": False,
                }
            ]
            encounter.spell_instances = [
                {
                    "instance_id": "spell_hold_person_001",
                    "spell_id": "hold_person",
                    "spell_name": "Hold Person",
                    "caster_entity_id": "ent_pc_eric_001",
                    "caster_name": "Eric",
                    "cast_level": 2,
                    "concentration": {"required": True, "active": True},
                    "targets": [
                        {
                            "entity_id": "ent_enemy_iron_duster_001",
                            "applied_conditions": ["paralyzed"],
                            "turn_effect_ids": ["effect_hold_person_001"],
                        }
                    ],
                    "lifecycle": {"status": "active", "started_round": 1},
                    "special_runtime": {},
                }
            ]
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            request = RequestConcentrationCheck(encounter_repo).execute(
                encounter_id="enc_concentration_test",
                target_id="ent_pc_eric_001",
                damage_taken=24,
            )
            roll_result = ResolveConcentrationCheck(encounter_repo).execute(
                encounter_id="enc_concentration_test",
                roll_request=request,
                base_rolls=[3],
            )

            ResolveConcentrationResult(encounter_repo, append_event).execute(
                encounter_id="enc_concentration_test",
                roll_request=request,
                roll_result=roll_result,
            )

            updated = encounter_repo.get("enc_concentration_test")
            assert updated is not None
            self.assertFalse(updated.entities["ent_pc_eric_001"].combat_flags["is_concentrating"])
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, [])
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].turn_effects, [])
            self.assertFalse(updated.spell_instances[0]["concentration"]["active"])
            self.assertEqual(updated.spell_instances[0]["lifecycle"]["status"], "ended")
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
