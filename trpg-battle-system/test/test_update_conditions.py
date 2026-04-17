"""Condition 更新测试：覆盖施加、移除和重复操作。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, UpdateConditions


def build_target() -> EncounterEntity:
    """构造 condition 测试里的目标实体。"""
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
    """构造 condition 测试用 encounter。"""
    target = build_target()
    return Encounter(
        encounter_id="enc_condition_test",
        name="Condition Test Encounter",
        status="active",
        round=1,
        current_entity_id=target.entity_id,
        turn_order=[target.entity_id],
        entities={target.entity_id: target},
        map=EncounterMap(
            map_id="map_condition_test",
            name="Condition Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def build_release_encounter() -> Encounter:
    grappler = EncounterEntity(
        entity_id="ent_actor_001",
        name="Sabur",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        combat_flags={
            "active_grapple": {
                "target_entity_id": "ent_target_001",
                "escape_dc": 13,
                "source_condition": "grappled:ent_actor_001",
                "movement_speed_halved": True,
            }
        },
    )
    target = EncounterEntity(
        entity_id="ent_target_001",
        name="Raider",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 3, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 0},
        initiative=10,
        conditions=["grappled:ent_actor_001"],
    )
    return Encounter(
        encounter_id="enc_release_test",
        name="Release Test Encounter",
        status="active",
        round=1,
        current_entity_id=grappler.entity_id,
        turn_order=[grappler.entity_id, target.entity_id],
        entities={grappler.entity_id: grappler, target.entity_id: target},
        map=EncounterMap(
            map_id="map_release_test",
            name="Release Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class UpdateConditionsTests(unittest.TestCase):
    def test_execute_applies_condition(self) -> None:
        """测试 apply 会把 condition 写进实体快照并追加事件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="Blinded",
                operation="apply",
                reason="Blindness/Deafness",
            )

            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["blinded"])
            self.assertTrue(result["changed"])
            self.assertEqual(result["event_type"], "condition_applied")
            encounter_repo.close()
            event_repo.close()

    def test_execute_remove_condition(self) -> None:
        """测试 remove 会从实体快照里移除已有 condition。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_iron_duster_001"].conditions = ["blinded", "prone"]
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="BLINDED",
                operation="remove",
            )

            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["prone"])
            self.assertTrue(result["changed"])
            self.assertEqual(result["event_type"], "condition_removed")
            encounter_repo.close()
            event_repo.close()

    def test_execute_apply_existing_condition_returns_unchanged(self) -> None:
        """测试重复施加同一 condition 时不会重复写入快照。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_iron_duster_001"].conditions = ["blinded"]
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="blinded",
                operation="apply",
            )

            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["blinded"])
            self.assertFalse(result["changed"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_can_include_latest_encounter_state(self) -> None:
        """测试 condition 更新结果里可以附带最新前端状态。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="Blinded",
                operation="apply",
                include_encounter_state=True,
            )

            self.assertIn("encounter_state", result)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_condition_test")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["conditions"], "blinded")
            encounter_repo.close()
            event_repo.close()

    def test_execute_handles_sourced_condition(self) -> None:
        """带来源的 condition 应当可以施加与移除。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            source_condition = "frightened:ent_enemy_dragon_001"
            apply_result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition=source_condition,
                operation="apply",
            )
            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertIn(source_condition, updated.entities["ent_enemy_iron_duster_001"].conditions)
            self.assertTrue(apply_result["changed"])

            remove_result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition=source_condition,
                operation="remove",
            )
            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertNotIn(source_condition, updated.entities["ent_enemy_iron_duster_001"].conditions)
            self.assertTrue(remove_result["changed"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_increments_exhaustion_level(self) -> None:
        """调用 apply exhaustion 时应当递增级别。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            for expected_level in (1, 2, 3):
                result = service.execute(
                    encounter_id="enc_condition_test",
                    target_id="ent_enemy_iron_duster_001",
                    condition="exhaustion",
                    operation="apply",
                )
                updated = encounter_repo.get("enc_condition_test")
                assert updated is not None
                self.assertEqual(
                    updated.entities["ent_enemy_iron_duster_001"].conditions,
                    [f"exhaustion:{expected_level}"],
                )
                self.assertTrue(result["changed"])

            encounter_repo.close()
            event_repo.close()

    def test_execute_decrements_exhaustion_level_and_removes(self) -> None:
        """remove exhaustion 应当逐级减弱并最终清除。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_iron_duster_001"].conditions = ["exhaustion:3"]
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            for expected_level in (2, 1):
                result = service.execute(
                    encounter_id="enc_condition_test",
                    target_id="ent_enemy_iron_duster_001",
                    condition="exhaustion",
                    operation="remove",
                )
                updated = encounter_repo.get("enc_condition_test")
                assert updated is not None
                self.assertEqual(
                    updated.entities["ent_enemy_iron_duster_001"].conditions,
                    [f"exhaustion:{expected_level}"],
                )
                self.assertTrue(result["changed"])

            final_result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="exhaustion",
                operation="remove",
            )
            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, [])
            self.assertTrue(final_result["changed"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_sets_exhaustion_level_directly(self) -> None:
        """apply exhaustion:3 应该直接覆盖当前级别。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_iron_duster_001"].conditions = ["exhaustion:1"]
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="exhaustion:3",
                operation="apply",
            )
            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertEqual(
                updated.entities["ent_enemy_iron_duster_001"].conditions,
                ["exhaustion:3"],
            )
            self.assertTrue(result["changed"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_exhaustion_six_defeats_target(self) -> None:
        """到达 exhaustion 6 应将 HP 归零并标记失败。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_iron_duster_001"].conditions = ["exhaustion:5"]
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="exhaustion",
                operation="apply",
            )
            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            entity = updated.entities["ent_enemy_iron_duster_001"]
            self.assertEqual(entity.hp["current"], 0)
            self.assertTrue(entity.combat_flags.get("is_defeated"))
            self.assertEqual(entity.conditions, ["exhaustion:6"])
            self.assertTrue(result["changed"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_poisoned_not_applied_to_petrified_target(self) -> None:
        """石化目标无法被 poisoned 影响。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_iron_duster_001"].conditions = ["petrified"]
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="poisoned",
                operation="apply",
            )
            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_iron_duster_001"].conditions, ["petrified"])
            self.assertFalse(result["changed"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_handles_legacy_bare_exhaustion(self) -> None:
        """遇到旧存档里的 bare 'exhaustion' 时仍能升级级别。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_iron_duster_001"].conditions = ["exhaustion"]
            encounter_repo.save(encounter)

            service = UpdateConditions(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_condition_test",
                target_id="ent_enemy_iron_duster_001",
                condition="exhaustion",
                operation="apply",
            )
            updated = encounter_repo.get("enc_condition_test")
            assert updated is not None
            self.assertEqual(
                updated.entities["ent_enemy_iron_duster_001"].conditions,
                ["exhaustion:2"],
            )
            self.assertTrue(result["changed"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_releases_active_grapple_when_grappler_becomes_incapacitated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_release_encounter())

            UpdateConditions(encounter_repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_release_test",
                target_id="ent_actor_001",
                condition="incapacitated",
                operation="apply",
            )

            updated = encounter_repo.get("enc_release_test")
            assert updated is not None
            self.assertNotIn("grappled:ent_actor_001", updated.entities["ent_target_001"].conditions)
            self.assertNotIn("active_grapple", updated.entities["ent_actor_001"].combat_flags)
            encounter_repo.close()
            event_repo.close()

    def test_execute_releases_active_grapple_when_target_condition_is_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_release_encounter())

            UpdateConditions(encounter_repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_release_test",
                target_id="ent_target_001",
                condition="grappled:ent_actor_001",
                operation="remove",
            )

            updated = encounter_repo.get("enc_release_test")
            assert updated is not None
            self.assertNotIn("active_grapple", updated.entities["ent_actor_001"].combat_flags)
            encounter_repo.close()
            event_repo.close()
