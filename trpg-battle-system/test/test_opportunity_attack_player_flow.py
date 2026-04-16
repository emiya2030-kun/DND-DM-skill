from __future__ import annotations

"""玩家确认型借机攻击完整链路测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import (
    AppendEvent,
    AttackRollRequest,
    AttackRollResult,
    BeginMoveEncounterEntity,
    ContinuePendingMovement,
    ExecuteAttack,
    ResolveReactionRequest,
    UpdateHp,
)


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
        ability_mods={"str": 1, "dex": 3, "con": 1, "int": 0, "wis": 0, "cha": 2},
        proficiency_bonus=2,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        combat_flags={"is_active": True, "is_defeated": hp_current <= 0},
    )


def build_melee_weapon() -> dict:
    return {
        "weapon_id": "rapier",
        "name": "Rapier",
        "attack_bonus": 5,
        "damage": [{"formula": "1d8+3", "type": "piercing"}],
        "range": {"normal": 5, "long": 5},
        "properties": ["finesse"],
    }


def build_encounter(*, mover_hp: int = 20) -> Encounter:
    player = build_entity(
        "ent_ally_eric_001",
        name="Eric",
        x=4,
        y=4,
        side="ally",
        controller="player",
        initiative=15,
        weapons=[build_melee_weapon()],
    )
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
    return Encounter(
        encounter_id="enc_opportunity_flow_test",
        name="Opportunity Flow Test",
        status="active",
        round=1,
        current_entity_id=mover.entity_id,
        turn_order=[mover.entity_id, player.entity_id],
        entities={mover.entity_id: mover, player.entity_id: player},
        map=EncounterMap(
            map_id="map_opportunity_flow_test",
            name="Opportunity Flow Test Map",
            description="A small combat room.",
            width=12,
            height=12,
        ),
    )


class OpportunityAttackPlayerFlowTests(unittest.TestCase):
    def _build_services(self, encounter_repo: EncounterRepository, event_repo: EventRepository):
        append_event = AppendEvent(event_repo)
        execute_attack = ExecuteAttack(
            AttackRollRequest(encounter_repo),
            AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
        )
        return (
            BeginMoveEncounterEntity(encounter_repo, append_event),
            ResolveReactionRequest(encounter_repo, append_event, execute_attack),
            ContinuePendingMovement(encounter_repo, append_event),
        )

    def test_player_accepts_opportunity_attack_then_movement_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())
            begin_move, resolve_request, continue_move = self._build_services(encounter_repo, event_repo)

            begin_result = begin_move.execute_with_state(
                encounter_id="enc_opportunity_flow_test",
                entity_id="ent_enemy_orc_001",
                target_position={"x": 8, "y": 4},
            )
            self.assertEqual(begin_result["movement_status"], "waiting_reaction")
            self.assertTrue(begin_result["reaction_requests"][0]["ask_player"])

            react_result = resolve_request.execute(
                encounter_id="enc_opportunity_flow_test",
                request_id=begin_result["reaction_requests"][0]["request_id"],
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [2]}],
            )
            self.assertEqual(react_result["encounter_state"]["reaction_requests"][0]["status"], "resolved")
            self.assertEqual(react_result["resolution_mode"], "append_followup_action")

            continue_result = continue_move.execute_with_state(encounter_id="enc_opportunity_flow_test")
            updated = encounter_repo.get("enc_opportunity_flow_test")
            assert updated is not None
            self.assertEqual(continue_result["movement_status"], "completed")
            self.assertIsNone(updated.pending_movement)
            self.assertEqual(updated.entities["ent_enemy_orc_001"].position, {"x": 8, "y": 4})
            self.assertEqual(updated.reaction_requests[0]["status"], "resolved")
            encounter_repo.close()
            event_repo.close()

    def test_player_accepts_opportunity_attack_and_knocks_target_down_before_move_finishes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(mover_hp=5))
            begin_move, resolve_request, continue_move = self._build_services(encounter_repo, event_repo)

            begin_result = begin_move.execute_with_state(
                encounter_id="enc_opportunity_flow_test",
                entity_id="ent_enemy_orc_001",
                target_position={"x": 8, "y": 4},
            )
            request_id = begin_result["reaction_requests"][0]["request_id"]

            resolve_request.execute(
                encounter_id="enc_opportunity_flow_test",
                request_id=request_id,
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
            )

            continue_result = continue_move.execute_with_state(encounter_id="enc_opportunity_flow_test")
            updated = encounter_repo.get("enc_opportunity_flow_test")
            assert updated is not None
            self.assertEqual(continue_result["movement_status"], "interrupted")
            self.assertIsNone(updated.pending_movement)
            self.assertNotIn("ent_enemy_orc_001", updated.entities)
            self.assertNotIn("ent_enemy_orc_001", updated.turn_order)
            self.assertEqual(getattr(updated.map, "remains", [])[0]["icon"], "💀")
            self.assertEqual(getattr(updated.map, "remains", [])[0]["position"], {"x": 5, "y": 4})
            self.assertEqual(updated.reaction_requests[0]["status"], "resolved")
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
