"""仓储层测试：覆盖 encounter 在 TinyDB 中的持久化行为。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository


def build_entity(entity_id: str = "ent_ally_eric_001") -> EncounterEntity:
    """构造仓储测试用的最小合法实体。"""
    return EncounterEntity(
        entity_id=entity_id,
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 15, "y": 19},
        hp={"current": 80, "max": 80, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=17,
    )


def build_encounter() -> Encounter:
    """构造仓储测试用的最小合法 encounter 快照。"""
    entity = build_entity()
    return Encounter(
        encounter_id="enc_repo_test",
        name="Repository Test Encounter",
        status="active",
        round=1,
        current_entity_id=entity.entity_id,
        turn_order=[entity.entity_id],
        entities={entity.entity_id: entity},
        map=EncounterMap(
            map_id="map_repo_test",
            name="Repo Test Map",
            description="A map for repository tests.",
            width=10,
            height=10,
        ),
    )


class EncounterRepositoryTests(unittest.TestCase):
    def test_save_and_get_encounter(self) -> None:
        """测试保存后再读取 encounter，关键字段应保持一致。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()

            repo.save(encounter)
            loaded = repo.get(encounter.encounter_id)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.encounter_id, encounter.encounter_id)
            self.assertEqual(loaded.current_entity_id, encounter.current_entity_id)
            repo.close()

    def test_delete_encounter(self) -> None:
        """测试删除 encounter 后，后续读取应返回空。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()

            repo.save(encounter)
            removed = repo.delete(encounter.encounter_id)

            self.assertEqual(removed, 1)
            self.assertIsNone(repo.get(encounter.encounter_id))
            repo.close()


if __name__ == "__main__":
    unittest.main()
