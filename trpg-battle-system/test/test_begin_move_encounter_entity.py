from __future__ import annotations

"""阻塞式移动测试：覆盖移动途中生成借机请求。"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

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


def build_encounter_with_enemy_reactor_and_player_mover() -> Encounter:
    reactor = build_entity(
        "ent_enemy_guard_001",
        name="Guard",
        x=4,
        y=4,
        side="enemy",
        controller="gm",
        initiative=15,
        weapons=[
            {
                "weapon_id": "shortsword",
                "name": "Shortsword",
                "attack_bonus": 4,
                "damage": [{"formula": "1d6+2", "type": "piercing"}],
                "range": {"normal": 5, "long": 5},
                "properties": ["finesse"],
            }
        ],
    )
    mover = build_entity(
        "ent_ally_lia_001",
        name="Lia",
        x=5,
        y=4,
        side="ally",
        controller="player",
        initiative=12,
    )
    return Encounter(
        encounter_id="enc_begin_move_enemy_react_test",
        name="Begin Move Enemy React Encounter",
        status="active",
        round=1,
        current_entity_id=mover.entity_id,
        turn_order=[mover.entity_id, reactor.entity_id],
        entities={mover.entity_id: mover, reactor.entity_id: reactor},
        map=EncounterMap(
            map_id="map_begin_move_enemy_react_test",
            name="Begin Move Enemy React Map",
            description="A small combat room.",
            width=12,
            height=12,
        ),
    )


class BeginMoveEncounterEntityTests(unittest.TestCase):
    def test_execute_rejects_non_current_turn_entity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter_with_player_and_moving_enemy()
            ally = build_entity(
                "ent_ally_lia_001",
                name="Lia",
                x=3,
                y=4,
                side="ally",
                controller="companion_npc",
                initiative=13,
            )
            encounter.entities[ally.entity_id] = ally
            encounter.turn_order.insert(1, ally.entity_id)
            repo.save(encounter)

            service = BeginMoveEncounterEntity(repo, AppendEvent(event_repo))
            with self.assertRaisesRegex(ValueError, "actor_not_current_turn_entity"):
                service.execute_with_state(
                    encounter_id="enc_begin_move_test",
                    entity_id=ally.entity_id,
                    target_position={"x": 4, "y": 4},
                )
            repo.close()
            event_repo.close()

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
            self.assertEqual(updated.pending_reaction_window["trigger_type"], "leave_reach")
            self.assertEqual(
                updated.pending_reaction_window["choice_groups"][0]["options"][0]["reaction_type"],
                "opportunity_attack",
            )
            self.assertEqual(updated.reaction_requests[0]["reaction_type"], "opportunity_attack")
            self.assertEqual(updated.reaction_requests[0]["actor_entity_id"], "ent_ally_eric_001")
            self.assertEqual(updated.reaction_requests[0]["target_entity_id"], "ent_enemy_orc_001")
            self.assertEqual(updated.reaction_requests[0]["actor_name"], "Eric")
            self.assertEqual(updated.reaction_requests[0]["target_name"], "Orc")
            self.assertEqual(updated.reaction_requests[0]["source_event_type"], "movement_trigger_check")
            self.assertIsNone(updated.reaction_requests[0]["source_event_id"])
            self.assertEqual(updated.reaction_requests[0]["payload"]["weapon_id"], "rapier")
            self.assertEqual(result["movement_status"], "waiting_reaction")
            self.assertEqual(result["reaction_requests"][0]["status"], "pending")
            self.assertEqual(result["encounter_state"]["pending_reaction_window"]["trigger_type"], "leave_reach")
            repo.close()
            event_repo.close()

    def test_execute_keeps_non_player_reactor_request_auto_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter_with_enemy_reactor_and_player_mover())

            service = BeginMoveEncounterEntity(repo, AppendEvent(event_repo))
            result = service.execute_with_state(
                encounter_id="enc_begin_move_enemy_react_test",
                entity_id="ent_ally_lia_001",
                target_position={"x": 8, "y": 4},
            )

            updated = repo.get("enc_begin_move_enemy_react_test")
            assert updated is not None
            self.assertEqual(result["movement_status"], "waiting_reaction")
            self.assertFalse(updated.reaction_requests[0]["ask_player"])
            self.assertTrue(updated.reaction_requests[0]["auto_resolve"])
            self.assertFalse(updated.pending_reaction_window["choice_groups"][0]["ask_player"])
            self.assertEqual(updated.reaction_requests[0]["actor_name"], "Guard")
            self.assertEqual(updated.reaction_requests[0]["target_name"], "Lia")
            self.assertEqual(updated.reaction_requests[0]["source_event_type"], "movement_trigger_check")
            self.assertIsNone(updated.reaction_requests[0]["source_event_id"])
            self.assertEqual(updated.reaction_requests[0]["payload"]["weapon_id"], "shortsword")
            repo.close()
            event_repo.close()

    def test_begin_move_ignores_opportunity_attacks_for_tactical_shift_move(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter_with_player_and_moving_enemy())

            result = BeginMoveEncounterEntity(repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_begin_move_test",
                entity_id="ent_enemy_orc_001",
                target_position={"x": 6, "y": 6},
                ignore_opportunity_attacks_for_this_move=True,
            )

            updated = repo.get("enc_begin_move_test")
            assert updated is not None
            self.assertNotEqual(result["status"], "waiting_reaction")
            self.assertIsNone(updated.pending_movement)
            self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 6, "y": 6})
            repo.close()
            event_repo.close()

    def test_begin_move_tactical_shift_does_not_call_open_reaction_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter_with_player_and_moving_enemy())
            open_reaction_window = Mock()
            open_reaction_window.execute.return_value = {
                "status": "no_reaction",
                "pending_reaction_window": None,
                "reaction_requests": [],
            }
            service = BeginMoveEncounterEntity(
                repo,
                AppendEvent(event_repo),
                open_reaction_window=open_reaction_window,
            )

            result = service.execute_with_state(
                encounter_id="enc_begin_move_test",
                entity_id="ent_enemy_orc_001",
                target_position={"x": 8, "y": 4},
                ignore_opportunity_attacks_for_this_move=True,
            )

            open_reaction_window.execute.assert_not_called()
            self.assertEqual(result["movement_status"], "completed")
            self.assertEqual(result["reaction_requests"], [])
            repo.close()
            event_repo.close()

    def test_begin_move_tactical_shift_flag_only_applies_to_current_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter_with_player_and_moving_enemy())
            service = BeginMoveEncounterEntity(repo, AppendEvent(event_repo))

            first = service.execute_with_state(
                encounter_id="enc_begin_move_test",
                entity_id="ent_enemy_orc_001",
                target_position={"x": 8, "y": 4},
                ignore_opportunity_attacks_for_this_move=True,
            )
            self.assertEqual(first["movement_status"], "completed")

            encounter = repo.get("enc_begin_move_test")
            assert encounter is not None
            encounter.entities["ent_enemy_orc_001"].position = {"x": 5, "y": 4}
            repo.save(encounter)

            second = service.execute_with_state(
                encounter_id="enc_begin_move_test",
                entity_id="ent_enemy_orc_001",
                target_position={"x": 8, "y": 4},
            )
            self.assertEqual(second["movement_status"], "waiting_reaction")
            self.assertTrue(second["reaction_requests"])
            repo.close()
            event_repo.close()

    def test_execute_ignores_opportunity_attacks_when_mover_has_disengage_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter_with_player_and_moving_enemy()
            encounter.entities["ent_enemy_orc_001"].turn_effects = [
                {"effect_id": "effect_disengage_001", "effect_type": "disengage", "name": "Disengage"}
            ]
            repo.save(encounter)

            service = BeginMoveEncounterEntity(repo, AppendEvent(event_repo))
            result = service.execute_with_state(
                encounter_id="enc_begin_move_test",
                entity_id="ent_enemy_orc_001",
                target_position={"x": 8, "y": 4},
            )

            updated = repo.get("enc_begin_move_test")
            assert updated is not None
            self.assertEqual(result["movement_status"], "completed")
            self.assertIsNone(updated.pending_movement)
            self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 8, "y": 4})
            repo.close()
            event_repo.close()

    def test_execute_rejects_grappled_target_self_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter_with_enemy_reactor_and_player_mover()
            encounter.entities["ent_ally_lia_001"].conditions = ["grappled:ent_enemy_guard_001"]
            repo.save(encounter)

            service = BeginMoveEncounterEntity(repo, AppendEvent(event_repo))
            with self.assertRaisesRegex(ValueError, "cannot_move_while_grappled"):
                service.execute_with_state(
                    encounter_id="enc_begin_move_enemy_react_test",
                    entity_id="ent_ally_lia_001",
                    target_position={"x": 8, "y": 4},
                )
            repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
