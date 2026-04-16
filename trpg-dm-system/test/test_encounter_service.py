"""服务层测试：覆盖本地 encounter 管理和回合推进行为。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services import EncounterService


def build_entity(
    entity_id: str,
    *,
    name: str,
    x: int,
    y: int,
    initiative: int = 10,
    size: str = "medium",
) -> EncounterEntity:
    """构造服务层测试用的最小合法实体。"""
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side="ally",
        category="pc",
        controller="player",
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=initiative,
        size=size,
    )


def build_encounter() -> Encounter:
    """构造服务层测试用的基础 encounter。"""
    entity = build_entity("ent_ally_eric_001", name="Eric", x=2, y=2, initiative=15)
    return Encounter(
        encounter_id="enc_service_test",
        name="Service Test Encounter",
        status="active",
        round=1,
        current_entity_id=entity.entity_id,
        turn_order=[entity.entity_id],
        entities={entity.entity_id: entity},
        map=EncounterMap(
            map_id="map_service_test",
            name="Service Test Map",
            description="A map used by service tests.",
            width=8,
            height=8,
        ),
    )


class EncounterServiceTests(unittest.TestCase):
    def test_entity_defaults_size_to_medium(self) -> None:
        """测试 EncounterEntity 默认体型为 medium，并可序列化。"""
        entity = build_entity("ent_size_default", name="Scout", x=2, y=3)

        self.assertEqual(entity.size, "medium")
        self.assertEqual(entity.to_dict()["size"], "medium")

    def test_entity_rejects_unknown_size(self) -> None:
        """测试 EncounterEntity 会拒绝未知体型。"""
        with self.assertRaises(ValueError):
            build_entity("ent_bad_size", name="Weird", x=1, y=1, size="colossal")

    def test_add_entity_can_append_to_turn_order(self) -> None:
        """测试 add_entity 可以把新实体加入 entities 和 turn_order。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            service.create_encounter(encounter)

            added_entity = build_entity("ent_ally_npc_001", name="Companion", x=3, y=3, initiative=12)
            updated = service.add_entity(encounter.encounter_id, added_entity, add_to_turn_order=True)

            self.assertIn(added_entity.entity_id, updated.entities)
            self.assertEqual(updated.turn_order, ["ent_ally_eric_001", "ent_ally_npc_001"])
            repo.close()

    def test_remove_entity_updates_turn_order_and_current_entity(self) -> None:
        """测试 remove_entity 会同步更新 turn_order 和 current_entity_id。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            encounter = service.create_encounter(encounter)
            encounter = service.add_entity(
                encounter.encounter_id,
                build_entity("ent_ally_npc_001", name="Companion", x=3, y=3),
                add_to_turn_order=True,
            )
            encounter = service.set_turn_order(encounter.encounter_id, ["ent_ally_eric_001", "ent_ally_npc_001"])
            encounter = service.set_current_entity(encounter.encounter_id, "ent_ally_eric_001")

            updated = service.remove_entity(encounter.encounter_id, "ent_ally_eric_001")

            self.assertNotIn("ent_ally_eric_001", updated.entities)
            self.assertEqual(updated.turn_order, ["ent_ally_npc_001"])
            self.assertEqual(updated.current_entity_id, "ent_ally_npc_001")
            repo.close()

    def test_set_turn_order_rejects_unknown_entity(self) -> None:
        """测试 set_turn_order 会拒绝不存在的实体 id。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            service.create_encounter(encounter)

            with self.assertRaises(ValueError):
                service.set_turn_order(encounter.encounter_id, ["ent_ally_eric_001", "ent_missing"])
            repo.close()

    def test_advance_turn_moves_to_next_entity(self) -> None:
        """测试 advance_turn 会切换到 turn_order 中的下一个实体。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            encounter = service.create_encounter(encounter)
            service.add_entity(
                encounter.encounter_id,
                build_entity("ent_ally_npc_001", name="Companion", x=3, y=3),
                add_to_turn_order=True,
            )
            stored = repo.get(encounter.encounter_id)
            stored.entities["ent_ally_npc_001"].action_economy = {"action_used": True}
            stored.entities["ent_ally_npc_001"].speed["remaining"] = 0
            stored.entities["ent_ally_npc_001"].combat_flags["movement_spent_feet"] = 30
            repo.save(stored)

            updated = service.advance_turn(encounter.encounter_id)

            self.assertEqual(updated.current_entity_id, "ent_ally_npc_001")
            self.assertEqual(updated.round, 1)
            self.assertTrue(updated.entities["ent_ally_npc_001"].action_economy["action_used"])
            self.assertEqual(updated.entities["ent_ally_npc_001"].speed["remaining"], 0)
            repo.close()

    def test_start_turn_resets_current_entity_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].action_economy = {"action_used": True}
            encounter.entities["ent_ally_eric_001"].speed["remaining"] = 0
            encounter.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"] = 30
            service.create_encounter(encounter)

            updated = service.start_turn(encounter.encounter_id)

            self.assertFalse(updated.entities["ent_ally_eric_001"].action_economy["action_used"])
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 30)
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 0)
            repo.close()

    def test_end_turn_keeps_current_entity_resources_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].action_economy = {"action_used": True}
            encounter.entities["ent_ally_eric_001"].speed["remaining"] = 0
            encounter.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"] = 30
            service.create_encounter(encounter)

            updated = service.end_turn(encounter.encounter_id)

            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["action_used"])
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 0)
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 30)
            repo.close()

    def test_advance_turn_wraps_and_increments_round(self) -> None:
        """测试 advance_turn 在到达末尾时会回到第一个并增加 round。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            encounter = service.create_encounter(encounter)
            encounter = service.add_entity(
                encounter.encounter_id,
                build_entity("ent_ally_npc_001", name="Companion", x=3, y=3),
                add_to_turn_order=True,
            )
            encounter = service.set_current_entity(encounter.encounter_id, "ent_ally_npc_001")

            updated = service.advance_turn(encounter.encounter_id)

            self.assertEqual(updated.current_entity_id, "ent_ally_eric_001")
            self.assertEqual(updated.round, 2)
            repo.close()

    def test_update_entity_position_rejects_out_of_bounds(self) -> None:
        """测试 update_entity_position 会拒绝移动到地图边界之外。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            service.create_encounter(encounter)

            with self.assertRaises(ValueError):
                service.update_entity_position(encounter.encounter_id, "ent_ally_eric_001", 99, 99)
            repo.close()

    def test_update_entity_hp_updates_snapshot(self) -> None:
        """测试 update_entity_hp 可以更新当前 HP 和临时 HP。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            service.create_encounter(encounter)

            updated = service.update_entity_hp(
                encounter.encounter_id,
                "ent_ally_eric_001",
                current_hp=12,
                temp_hp=4,
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].hp["current"], 12)
            self.assertEqual(updated.entities["ent_ally_eric_001"].hp["temp"], 4)
            repo.close()

    def test_advance_turn_with_state_returns_latest_encounter_state(self) -> None:
        """测试 encounter 管理层可以在推进回合后附带最新 state。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = EncounterService(repo)
            encounter = build_encounter()
            encounter = service.create_encounter(encounter)
            service.add_entity(
                encounter.encounter_id,
                build_entity("ent_ally_npc_001", name="Companion", x=3, y=3),
                add_to_turn_order=True,
            )

            result = service.advance_turn_with_state(encounter.encounter_id)

            self.assertEqual(result["encounter_id"], encounter.encounter_id)
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["id"], "ent_ally_npc_001")
            repo.close()


if __name__ == "__main__":
    unittest.main()
