"""攻击掷骰结算测试：覆盖命中、未命中和暴击判定。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap, RollResult
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, AttackRollResult, RequestConcentrationCheck, UpdateHp


def build_player() -> EncounterEntity:
    """构造当前回合的攻击者。"""
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
    )


def build_target() -> EncounterEntity:
    """构造被攻击目标。"""
    return EncounterEntity(
        entity_id="ent_enemy_goblin_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 3, "y": 2},
        hp={"current": 7, "max": 7, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_encounter() -> Encounter:
    """构造攻击结算测试用的最小 encounter。"""
    player = build_player()
    target = build_target()
    return Encounter(
        encounter_id="enc_attack_test",
        name="Attack Test Encounter",
        status="active",
        round=1,
        current_entity_id=player.entity_id,
        turn_order=[player.entity_id, target.entity_id],
        entities={player.entity_id: player, target.entity_id: target},
        map=EncounterMap(
            map_id="map_attack_test",
            name="Attack Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class AttackRollResultTests(unittest.TestCase):
    def test_execute_marks_hit_and_appends_event(self) -> None:
        """测试最终值高于 AC 时会判定命中并写入 attack_resolved 事件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = AttackRollResult(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_attack_test",
                attack_name="Rapier",
                roll_result=RollResult(
                    request_id="req_attack_001",
                    encounter_id="enc_attack_test",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    roll_type="attack_roll",
                    final_total=17,
                    dice_rolls={"base_rolls": [14], "modifier": 3},
                ),
            )

            self.assertTrue(result["hit"])
            self.assertTrue(result["needs_damage_roll"])
            self.assertEqual(result["comparison"]["left_value"], 17)
            self.assertEqual(result["comparison"]["right_value"], 13)
            self.assertTrue(result["comparison"]["passed"])
            self.assertEqual(event_repo.list_by_encounter("enc_attack_test")[0].event_type, "attack_resolved")
            encounter_repo.close()
            event_repo.close()

    def test_execute_can_auto_apply_damage_after_hit(self) -> None:
        """测试命中后如果传入 hp_change，会自动调用 UpdateHp 扣血。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            update_hp = UpdateHp(encounter_repo, append_event)
            service = AttackRollResult(encounter_repo, append_event, update_hp)
            result = service.execute(
                encounter_id="enc_attack_test",
                attack_name="Rapier",
                hp_change=4,
                damage_reason="Rapier damage",
                damage_type="piercing",
                roll_result=RollResult(
                    request_id="req_attack_001b",
                    encounter_id="enc_attack_test",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    roll_type="attack_roll",
                    final_total=17,
                    dice_rolls={"base_rolls": [14], "modifier": 3},
                ),
            )

            updated = encounter_repo.get("enc_attack_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 3)
            self.assertEqual(result["hp_update"]["event_type"], "damage_applied")
            self.assertEqual(len(event_repo.list_by_encounter("enc_attack_test")), 2)
            encounter_repo.close()
            event_repo.close()

    def test_execute_marks_miss_when_below_target_ac(self) -> None:
        """测试最终值低于 AC 时会判定未命中。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = AttackRollResult(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_attack_test",
                roll_result=RollResult(
                    request_id="req_attack_002",
                    encounter_id="enc_attack_test",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    roll_type="attack_roll",
                    final_total=8,
                    dice_rolls={"base_rolls": [5], "modifier": 3},
                ),
            )

            self.assertFalse(result["hit"])
            self.assertFalse(result["needs_damage_roll"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_does_not_apply_damage_on_miss(self) -> None:
        """测试未命中时即使传入 hp_change，也不会自动扣血。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            update_hp = UpdateHp(encounter_repo, append_event)
            service = AttackRollResult(encounter_repo, append_event, update_hp)
            result = service.execute(
                encounter_id="enc_attack_test",
                hp_change=4,
                damage_reason="Missed attack should not apply damage",
                damage_type="piercing",
                roll_result=RollResult(
                    request_id="req_attack_002b",
                    encounter_id="enc_attack_test",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    roll_type="attack_roll",
                    final_total=8,
                    dice_rolls={"base_rolls": [5], "modifier": 3},
                ),
            )

            updated = encounter_repo.get("enc_attack_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 7)
            self.assertNotIn("hp_update", result)
            self.assertEqual(len(event_repo.list_by_encounter("enc_attack_test")), 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_marks_critical_hit_from_base_roll(self) -> None:
        """测试原始 d20 为 20 时会判定暴击。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = AttackRollResult(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_attack_test",
                roll_result=RollResult(
                    request_id="req_attack_003",
                    encounter_id="enc_attack_test",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    roll_type="attack_roll",
                    final_total=23,
                    dice_rolls={"base_rolls": [20], "modifier": 3},
                ),
            )

            self.assertTrue(result["is_critical_hit"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_rejects_actor_outside_current_turn(self) -> None:
        """测试不是当前行动者时不允许结算攻击掷骰。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.current_entity_id = "ent_enemy_goblin_001"
            encounter_repo.save(encounter)

            service = AttackRollResult(encounter_repo, AppendEvent(event_repo))
            with self.assertRaises(ValueError):
                service.execute(
                    encounter_id="enc_attack_test",
                    roll_result=RollResult(
                        request_id="req_attack_004",
                        encounter_id="enc_attack_test",
                        actor_entity_id="ent_ally_eric_001",
                        target_entity_id="ent_enemy_goblin_001",
                        roll_type="attack_roll",
                        final_total=17,
                        dice_rolls={"base_rolls": [14], "modifier": 3},
                    ),
                )
            encounter_repo.close()
            event_repo.close()

    def test_execute_auto_creates_concentration_request_after_damage(self) -> None:
        """测试攻击命中后如果目标正在专注，会在 hp_update 里生成专注检定请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_goblin_001"]
            target.combat_flags = {"is_active": True, "is_defeated": False, "is_concentrating": True}
            target.ability_mods = {"con": 1}
            target.save_proficiencies = ["con"]
            target.proficiency_bonus = 2
            encounter_repo.save(encounter)

            append_event = AppendEvent(event_repo)
            update_hp = UpdateHp(encounter_repo, append_event, RequestConcentrationCheck(encounter_repo))
            service = AttackRollResult(encounter_repo, append_event, update_hp)
            result = service.execute(
                encounter_id="enc_attack_test",
                attack_name="Rapier",
                hp_change=4,
                damage_reason="Rapier damage",
                damage_type="piercing",
                concentration_vantage="advantage",
                roll_result=RollResult(
                    request_id="req_attack_concentration",
                    encounter_id="enc_attack_test",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    roll_type="attack_roll",
                    final_total=17,
                    dice_rolls={"base_rolls": [14], "modifier": 3},
                ),
            )

            self.assertEqual(result["hp_update"]["concentration_check_request"]["roll_type"], "concentration_check")
            self.assertEqual(result["hp_update"]["concentration_check_request"]["context"]["vantage"], "advantage")
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
