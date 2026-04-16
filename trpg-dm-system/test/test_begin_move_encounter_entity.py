from __future__ import annotations

"""阻塞式移动测试：覆盖移动途中生成借机请求。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, BeginMoveEncounterEntity


def build_entity(
    entity_id: str,
    *,
    name: str,
    x: int,
    y: int,
    side: str,
    controller: str,
    initiative: int,
    weapons: list[dict] | None = None,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side=side,
        category="pc" if side == "ally" else "monster",
        controller=controller,
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=initiative,
        weapons=weapons or [],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        combat_flags={"is_active": True, "is_defeated": False},
    )


def build_encounter_with_player_and_moving_enemy() -> Encounter:
    player = build_entity(
        "ent_ally_eric_001",
        name="Eric",
        x=4,
        y=4,
        side="ally",
        controller="player",
        initiative=15,
        weapons=[
            {
                "weapon_id": "rapier",
                "name": "Rapier",
                "attack_bonus": 5,
                "damage": [{"formula": "1d8+3", "type": "piercing"}],
                "range": {"normal": 5, "long": 5},
                "properties": ["finesse"],
            }
        ],
    )
    mover = build_entity(
        "ent_enemy_orc_001",
        name="Orc",
        x=5,
        y=4,
        side="enemy",
        controller="gm",
        initiative=12,
    )
    return Encounter(
        encounter_id="enc_begin_move_test",
        name="Begin Move Test Encounter",
        status="active",
        round=1,
        current_entity_id=mover.entity_id,
        turn_order=[mover.entity_id, player.entity_id],
        entities={mover.entity_id: mover, player.entity_id: player},
        map=EncounterMap(
            map_id="map_begin_move_test",
            name="Begin Move Test Map",
            description="A small combat room.",
            width=12,
            height=12,
        ),
    )


class BeginMoveEncounterEntityTests(unittest.TestCase):
    def test_execute_creates_pending_movement_and_reaction_request_when_enemy_leaves_player_reach(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter_with_player_and_moving_enemy())

            service = BeginMoveEncounterEntity(repo, AppendEvent(event_repo))
            result = service.execute_with_state(
                encounter_id="enc_begin_move_test",
                entity_id="ent_enemy_orc_001",
                target_position={"x": 8, "y": 4},
            )

            updated = repo.get("enc_begin_move_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 5, "y": 4})
            self.assertEqual(updated.pending_movement["status"], "waiting_reaction")
            self.assertEqual(updated.pending_movement["current_position"], {"x": 5, "y": 4})
            self.assertEqual(updated.reaction_requests[0]["reaction_type"], "opportunity_attack")
            self.assertEqual(updated.reaction_requests[0]["actor_entity_id"], "ent_ally_eric_001")
            self.assertEqual(updated.reaction_requests[0]["target_entity_id"], "ent_enemy_orc_001")
            self.assertEqual(result["movement_status"], "waiting_reaction")
            self.assertEqual(result["reaction_requests"][0]["status"], "pending")
            repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
