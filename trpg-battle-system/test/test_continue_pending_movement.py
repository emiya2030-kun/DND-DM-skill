from __future__ import annotations

"""阻塞式移动恢复测试：覆盖跳过借机、再次触发借机和中断停点。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, ContinuePendingMovement


def build_entity(
    entity_id: str,
    *,
    name: str,
    x: int,
    y: int,
    side: str,
    controller: str,
    initiative: int,
    hp_current: int = 20,
    weapons: list[dict] | None = None,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side=side,
        category="pc" if side == "ally" else "monster",
        controller=controller,
        position={"x": x, "y": y},
        hp={"current": hp_current, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=initiative,
        weapons=weapons or [],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        combat_flags={"is_active": True, "is_defeated": hp_current <= 0},
    )


def build_melee_weapon(weapon_id: str, name: str) -> dict:
    return {
        "weapon_id": weapon_id,
        "name": name,
        "attack_bonus": 5,
        "damage": [{"formula": "1d8+3", "type": "piercing"}],
        "range": {"normal": 5, "long": 5},
        "properties": ["finesse"],
    }


def build_waiting_reaction_encounter(*, second_reactor: bool = False, mover_hp: int = 20, request_status: str = "pending") -> Encounter:
    eric = build_entity(
        "ent_ally_eric_001",
        name="Eric",
        x=4,
        y=4,
        side="ally",
        controller="player",
        initiative=15,
        weapons=[build_melee_weapon("rapier", "Rapier")],
    )
    entities: dict[str, EncounterEntity] = {eric.entity_id: eric}

    if second_reactor:
        nora = build_entity(
            "ent_ally_nora_001",
            name="Nora",
            x=8,
            y=4,
            side="ally",
            controller="player",
            initiative=13,
            weapons=[build_melee_weapon("shortsword", "Shortsword")],
        )
        entities[nora.entity_id] = nora

    mover = build_entity(
        "ent_enemy_orc_001",
        name="Orc",
        x=5,
        y=4,
        side="enemy",
        controller="gm",
        initiative=12,
        hp_current=mover_hp,
    )
    entities[mover.entity_id] = mover

    target_position = {"x": 10 if second_reactor else 8, "y": 4}
    remaining_path = (
        [{"x": 6, "y": 4}, {"x": 7, "y": 4}, {"x": 8, "y": 4}, {"x": 9, "y": 4}, {"x": 10, "y": 4}]
        if second_reactor
        else [{"x": 6, "y": 4}, {"x": 7, "y": 4}, {"x": 8, "y": 4}]
    )

    return Encounter(
        encounter_id="enc_continue_move_test",
        name="Continue Move Test Encounter",
        status="active",
        round=1,
        current_entity_id=mover.entity_id,
        turn_order=[mover.entity_id, eric.entity_id] + (["ent_ally_nora_001"] if second_reactor else []),
        entities=entities,
        map=EncounterMap(
            map_id="map_continue_move_test",
            name="Continue Move Test Map",
            description="A small combat room.",
            width=12,
            height=12,
        ),
        reaction_requests=[
            {
                "request_id": "react_001",
                "reaction_type": "opportunity_attack",
                "trigger_type": "leave_melee_reach",
                "status": request_status,
                "actor_entity_id": eric.entity_id,
                "actor_name": eric.name,
                "target_entity_id": mover.entity_id,
                "target_name": mover.name,
                "ask_player": True,
                "auto_resolve": False,
                "source_event_type": "movement_trigger_check",
                "source_event_id": None,
                "payload": {
                    "weapon_id": "rapier",
                    "weapon_name": "Rapier",
                    "trigger_position": {"x": 5, "y": 4},
                    "reason": "目标离开了你的近战触及",
                },
            }
        ],
        pending_movement={
            "movement_id": "move_001",
            "entity_id": mover.entity_id,
            "start_position": {"x": 5, "y": 4},
            "target_position": target_position,
            "current_position": {"x": 5, "y": 4},
            "remaining_path": remaining_path,
            "count_movement": True,
            "use_dash": False,
            "status": "waiting_reaction",
            "waiting_request_id": "react_001",
        },
    )


class ContinuePendingMovementTests(unittest.TestCase):
    def test_execute_expires_pending_request_and_finishes_move_when_player_skips_reaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_waiting_reaction_encounter())

            result = ContinuePendingMovement(repo, AppendEvent(event_repo)).execute_with_state(
                encounter_id="enc_continue_move_test"
            )

            updated = repo.get("enc_continue_move_test")
            assert updated is not None
            self.assertIsNone(updated.pending_movement)
            self.assertEqual(updated.reaction_requests[0]["status"], "expired")
            self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 8, "y": 4})
            self.assertEqual(result["movement_status"], "completed")
            repo.close()
            event_repo.close()

    def test_execute_pauses_again_when_remaining_path_triggers_second_opportunity_attack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_waiting_reaction_encounter(second_reactor=True))

            result = ContinuePendingMovement(repo, AppendEvent(event_repo)).execute_with_state(
                encounter_id="enc_continue_move_test"
            )

            updated = repo.get("enc_continue_move_test")
            assert updated is not None
            self.assertEqual(updated.reaction_requests[0]["status"], "expired")
            self.assertEqual(len(updated.reaction_requests), 2)
            self.assertEqual(updated.reaction_requests[1]["status"], "pending")
            self.assertEqual(updated.reaction_requests[1]["actor_entity_id"], "ent_ally_nora_001")
            self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 9, "y": 4})
            self.assertEqual(updated.pending_movement["status"], "waiting_reaction")
            self.assertEqual(updated.pending_movement["current_position"], {"x": 9, "y": 4})
            self.assertEqual(result["movement_status"], "waiting_reaction")
            repo.close()
            event_repo.close()

    def test_execute_interrupts_when_mover_was_dropped_by_reaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_waiting_reaction_encounter(mover_hp=0, request_status="resolved"))

            result = ContinuePendingMovement(repo, AppendEvent(event_repo)).execute_with_state(
                encounter_id="enc_continue_move_test"
            )

            updated = repo.get("enc_continue_move_test")
            assert updated is not None
            self.assertIsNone(updated.pending_movement)
            self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 5, "y": 4})
            self.assertEqual(updated.reaction_requests[0]["status"], "resolved")
            self.assertEqual(result["movement_status"], "interrupted")
            repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
