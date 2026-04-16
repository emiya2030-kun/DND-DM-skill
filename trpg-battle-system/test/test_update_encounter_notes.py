"""遭遇战笔记测试：覆盖新增、更新和移除特殊说明。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, UpdateEncounterNotes


def build_entity() -> EncounterEntity:
    """构造笔记测试需要的最小实体。"""
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
    """构造笔记测试用 encounter。"""
    entity = build_entity()
    return Encounter(
        encounter_id="enc_note_test",
        name="Note Test Encounter",
        status="active",
        round=1,
        current_entity_id=entity.entity_id,
        turn_order=[entity.entity_id],
        entities={entity.entity_id: entity},
        map=EncounterMap(
            map_id="map_note_test",
            name="Note Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class UpdateEncounterNotesTests(unittest.TestCase):
    def test_execute_adds_note(self) -> None:
        """测试 add 会把 note 追加到 encounter_notes。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = UpdateEncounterNotes(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_note_test",
                action="add",
                note="Iron Duster 对力量检定具有劣势。",
                entity_id="ent_enemy_iron_duster_001",
            )

            updated = encounter_repo.get("enc_note_test")
            assert updated is not None
            self.assertEqual(len(updated.encounter_notes), 1)
            self.assertEqual(updated.encounter_notes[0]["note"], "Iron Duster 对力量检定具有劣势。")
            self.assertEqual(result["event_type"], "encounter_note_added")
            encounter_repo.close()
            event_repo.close()

    def test_execute_updates_existing_note(self) -> None:
        """测试 update 会原地更新指定 note_id 的内容。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.encounter_notes = [
                {
                    "note_id": "note_001",
                    "entity_id": "ent_enemy_iron_duster_001",
                    "note": "旧说明",
                }
            ]
            encounter_repo.save(encounter)

            service = UpdateEncounterNotes(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_note_test",
                action="update",
                note_id="note_001",
                note="新说明",
                entity_id="ent_enemy_iron_duster_001",
            )

            updated = encounter_repo.get("enc_note_test")
            assert updated is not None
            self.assertEqual(updated.encounter_notes[0]["note"], "新说明")
            self.assertEqual(result["event_type"], "encounter_note_updated")
            encounter_repo.close()
            event_repo.close()

    def test_execute_removes_note(self) -> None:
        """测试 remove 会从 encounter_notes 删除对应记录。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.encounter_notes = [
                {
                    "note_id": "note_001",
                    "entity_id": "ent_enemy_iron_duster_001",
                    "note": "旧说明",
                }
            ]
            encounter_repo.save(encounter)

            service = UpdateEncounterNotes(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_note_test",
                action="remove",
                note_id="note_001",
            )

            updated = encounter_repo.get("enc_note_test")
            assert updated is not None
            self.assertEqual(updated.encounter_notes, [])
            self.assertEqual(result["event_type"], "encounter_note_removed")
            encounter_repo.close()
            event_repo.close()

    def test_execute_can_include_latest_encounter_state(self) -> None:
        """测试笔记更新结果里可以附带最新前端状态。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = UpdateEncounterNotes(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_note_test",
                action="add",
                note="新的战场备注",
                entity_id="ent_enemy_iron_duster_001",
                include_encounter_state=True,
            )

            self.assertIn("encounter_state", result)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_note_test")
            self.assertEqual(result["encounter_state"]["encounter_notes"][0]["note"], "新的战场备注")
            encounter_repo.close()
            event_repo.close()
