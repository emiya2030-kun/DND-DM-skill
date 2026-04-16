"""事件仓储测试：覆盖事件追加、去重和按 encounter 查询。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Event
from tools.repositories import EventRepository


def build_event(event_id: str = "evt_test_001", encounter_id: str = "enc_event_test") -> Event:
    """构造测试用的最小合法事件。"""
    return Event(
        event_id=event_id,
        encounter_id=encounter_id,
        round=1,
        event_type="turn_started",
        actor_entity_id="ent_ally_eric_001",
        payload={"note": "Turn begins"},
        created_at="2026-04-13T12:00:00+09:00",
    )


class EventRepositoryTests(unittest.TestCase):
    def test_append_and_get_event(self) -> None:
        """测试 append 后可以按 event_id 读回同一条事件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EventRepository(Path(tmp_dir) / "events.json")
            event = build_event()

            repo.append(event)
            loaded = repo.get(event.event_id)

            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.event_id, event.event_id)
            self.assertEqual(loaded.event_type, "turn_started")
            repo.close()

    def test_append_rejects_duplicate_event_id(self) -> None:
        """测试 append-only 行为会拒绝重复的 event_id。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EventRepository(Path(tmp_dir) / "events.json")
            event = build_event()

            repo.append(event)
            with self.assertRaises(ValueError):
                repo.append(event)
            repo.close()

    def test_list_by_encounter_keeps_append_order(self) -> None:
        """测试同一 encounter 的事件会按追加顺序返回。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EventRepository(Path(tmp_dir) / "events.json")
            first = build_event("evt_test_001", "enc_event_test")
            second = Event(
                event_id="evt_test_002",
                encounter_id="enc_event_test",
                round=1,
                event_type="attack_resolved",
                actor_entity_id="ent_ally_eric_001",
                target_entity_id="ent_enemy_goblin_001",
                payload={"hit": True},
                created_at="2026-04-13T12:00:01+09:00",
            )

            repo.append(first)
            repo.append(second)
            events = repo.list_by_encounter("enc_event_test")

            self.assertEqual([event.event_id for event in events], ["evt_test_001", "evt_test_002"])
            repo.close()


if __name__ == "__main__":
    unittest.main()
