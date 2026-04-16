"""事件服务测试：覆盖自动生成和按 encounter 聚合事件。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import EventRepository
from tools.services import AppendEvent


class AppendEventTests(unittest.TestCase):
    def test_execute_generates_event_id_and_timestamp(self) -> None:
        """测试 execute 默认会补齐 event_id 和 created_at。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EventRepository(Path(tmp_dir) / "events.json")
            service = AppendEvent(repo)

            event = service.execute(
                encounter_id="enc_event_test",
                round=1,
                event_type="turn_started",
                actor_entity_id="ent_ally_eric_001",
                payload={"note": "Turn begins"},
            )

            self.assertTrue(event.event_id.startswith("evt_"))
            self.assertIsNotNone(event.created_at)
            repo.close()

    def test_execute_can_list_events_by_encounter(self) -> None:
        """测试服务层可以按 encounter 返回聚合后的事件列表。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EventRepository(Path(tmp_dir) / "events.json")
            service = AppendEvent(repo)

            service.execute(
                encounter_id="enc_event_test",
                round=1,
                event_type="turn_started",
                actor_entity_id="ent_ally_eric_001",
            )
            service.execute(
                encounter_id="enc_event_test",
                round=1,
                event_type="movement_resolved",
                actor_entity_id="ent_ally_eric_001",
                payload={"from": "(2,2)", "to": "(3,2)"},
            )
            service.execute(
                encounter_id="enc_other_test",
                round=1,
                event_type="turn_started",
                actor_entity_id="ent_enemy_goblin_001",
            )

            events = service.list_by_encounter("enc_event_test")

            self.assertEqual(len(events), 2)
            self.assertEqual([event.event_type for event in events], ["turn_started", "movement_resolved"])
            repo.close()


if __name__ == "__main__":
    unittest.main()
