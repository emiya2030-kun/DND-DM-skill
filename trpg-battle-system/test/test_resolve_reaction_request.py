"""通用反应请求执行测试：第一版只覆盖借机攻击。"""

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
    ExecuteAttack,
    ResolveReactionRequest,
    UpdateHp,
)


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_eric_001",
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 4, "y": 4},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"str": 1, "dex": 3, "con": 1, "int": 0, "wis": 0, "cha": 2},
        proficiency_bonus=2,
        weapons=[
            {
                "weapon_id": "rapier",
                "name": "Rapier",
                "attack_bonus": 5,
                "damage": [{"formula": "1d8+3", "type": "piercing"}],
                "properties": ["finesse"],
                "range": {"normal": 5, "long": 5},
            }
        ],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
    )


def build_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_orc_001",
        name="Orc",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 5, "y": 4},
        hp={"current": 15, "max": 15, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
    )


def build_encounter() -> Encounter:
    actor = build_actor()
    target = build_target()
    return Encounter(
        encounter_id="enc_react_test",
        name="Reaction Request Encounter",
        status="active",
        round=1,
        current_entity_id=target.entity_id,
        turn_order=[target.entity_id, actor.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(
            map_id="map_react_test",
            name="Reaction Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
        reaction_requests=[
            {
                "request_id": "react_001",
                "reaction_type": "opportunity_attack",
                "trigger_type": "leave_melee_reach",
                "status": "pending",
                "actor_entity_id": actor.entity_id,
                "actor_name": actor.name,
                "target_entity_id": target.entity_id,
                "target_name": target.name,
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
        pending_reaction_window={
            "window_id": "rw_leave_reach_001",
            "status": "waiting_reaction",
            "trigger_event_id": "evt_leave_reach_001",
            "trigger_type": "leave_reach",
            "blocking": True,
            "host_action_type": "move",
            "host_action_id": "move_001",
            "host_action_snapshot": {"phase": "before_leave_reach"},
            "choice_groups": [
                {
                    "group_id": f"rg_{actor.entity_id}",
                    "actor_entity_id": actor.entity_id,
                    "ask_player": True,
                    "status": "pending",
                    "resource_pool": "reaction",
                    "group_priority": 100,
                    "trigger_sequence": 1,
                    "relationship_rank": 1,
                    "tie_break_key": actor.entity_id,
                    "options": [
                        {
                            "option_id": "opt_opp_001",
                            "reaction_type": "opportunity_attack",
                            "template_type": "leave_reach_interrupt",
                            "request_id": "react_001",
                            "label": "Opportunity Attack",
                            "status": "pending",
                        }
                    ],
                }
            ],
            "resolved_group_ids": [],
        },
    )


class ResolveReactionRequestTests(unittest.TestCase):
    def test_execute_resolves_opportunity_attack_and_spends_reaction_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            append_event = AppendEvent(event_repo)
            service = ResolveReactionRequest(
                encounter_repo,
                append_event,
                ExecuteAttack(
                    AttackRollRequest(encounter_repo),
                    AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
                ),
            )

            result = service.execute(
                encounter_id="enc_react_test",
                request_id="react_001",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
            )

            updated = encounter_repo.get("enc_react_test")
            assert updated is not None
            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["reaction_used"])
            self.assertFalse(updated.entities["ent_ally_eric_001"].action_economy.get("action_used", False))
            self.assertEqual(updated.reaction_requests[0]["status"], "resolved")
            self.assertEqual(result["reaction_type"], "opportunity_attack")
            self.assertEqual(result["encounter_state"]["reaction_requests"][0]["status"], "resolved")
            self.assertEqual(result["window_status"], "closed")
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
