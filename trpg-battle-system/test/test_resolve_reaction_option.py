"""Tests for resolving a reaction option via the reaction window."""

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
    UpdateHp,
)
from tools.services.combat.rules.reactions.resolve_reaction_option import ResolveReactionOption


def build_attacker() -> EncounterEntity:
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


def build_secondary_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_lina_002",
        name="Lina",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 3, "y": 4},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
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


def build_encounter(*, include_second_group: bool) -> Encounter:
    attacker = build_attacker()
    target = build_target()
    entities = {attacker.entity_id: attacker, target.entity_id: target}
    reaction_requests = [
        {
            "request_id": "react_001",
            "reaction_type": "opportunity_attack",
            "template_type": "leave_reach_interrupt",
            "trigger_type": "leave_reach",
            "status": "pending",
            "actor_entity_id": attacker.entity_id,
            "target_entity_id": target.entity_id,
            "ask_player": True,
            "auto_resolve": False,
            "payload": {"weapon_id": "rapier"},
        },
        {
            "request_id": "react_002",
            "reaction_type": "shield",
            "template_type": "targeted_defense_rewrite",
            "trigger_type": "leave_reach",
            "status": "pending",
            "actor_entity_id": attacker.entity_id,
            "target_entity_id": target.entity_id,
            "ask_player": True,
            "auto_resolve": False,
            "payload": {},
        },
    ]

    choice_groups = [
        {
            "group_id": f"rg_{attacker.entity_id}",
            "actor_entity_id": attacker.entity_id,
            "ask_player": True,
            "status": "pending",
            "resource_pool": "reaction",
            "group_priority": 100,
            "trigger_sequence": 1,
            "relationship_rank": 1,
            "tie_break_key": attacker.entity_id,
            "options": [
                {
                    "option_id": "opt_opp_001",
                    "reaction_type": "opportunity_attack",
                    "template_type": "leave_reach_interrupt",
                    "request_id": "react_001",
                    "label": "Opportunity Attack",
                    "status": "pending",
                },
                {
                    "option_id": "opt_shield_001",
                    "reaction_type": "shield",
                    "template_type": "targeted_defense_rewrite",
                    "request_id": "react_002",
                    "label": "Shield",
                    "status": "pending",
                },
            ],
        }
    ]

    if include_second_group:
        secondary = build_secondary_actor()
        entities[secondary.entity_id] = secondary
        reaction_requests.append(
            {
                "request_id": "react_003",
                "reaction_type": "shield",
                "template_type": "targeted_defense_rewrite",
                "trigger_type": "leave_reach",
                "status": "pending",
                "actor_entity_id": secondary.entity_id,
                "target_entity_id": target.entity_id,
                "ask_player": True,
                "auto_resolve": False,
                "payload": {},
            }
        )
        choice_groups.append(
            {
                "group_id": f"rg_{secondary.entity_id}",
                "actor_entity_id": secondary.entity_id,
                "ask_player": True,
                "status": "pending",
                "resource_pool": "reaction",
                "group_priority": 100,
                "trigger_sequence": 2,
                "relationship_rank": 1,
                "tie_break_key": secondary.entity_id,
                "options": [
                    {
                        "option_id": "opt_shield_002",
                        "reaction_type": "shield",
                        "template_type": "targeted_defense_rewrite",
                        "request_id": "react_003",
                        "label": "Shield",
                        "status": "pending",
                    }
                ],
            }
        )

    return Encounter(
        encounter_id="enc_react_option_test",
        name="Reaction Option Encounter",
        status="active",
        round=1,
        current_entity_id=target.entity_id,
        turn_order=[target.entity_id, attacker.entity_id],
        entities=entities,
        map=EncounterMap(
            map_id="map_react_option_test",
            name="Reaction Option Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
        reaction_requests=reaction_requests,
        pending_reaction_window={
            "window_id": "rw_leave_reach_001",
            "status": "waiting_reaction",
            "trigger_event_id": "evt_leave_reach_001",
            "trigger_type": "leave_reach",
            "blocking": True,
            "host_action_type": "move",
            "host_action_id": "move_001",
            "host_action_snapshot": {"phase": "before_leave_reach"},
            "choice_groups": choice_groups,
            "resolved_group_ids": [],
        },
    )


class ResolveReactionOptionTests(unittest.TestCase):
    def _build_service(self, encounter_repo: EncounterRepository, event_repo: EventRepository) -> ResolveReactionOption:
        append_event = AppendEvent(event_repo)
        execute_attack = ExecuteAttack(
            AttackRollRequest(encounter_repo),
            AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
        )
        return ResolveReactionOption(encounter_repo, append_event, execute_attack)

    def test_execute_resolves_option_and_updates_group_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(include_second_group=True))

            service = self._build_service(encounter_repo, event_repo)
            result = service.execute(
                encounter_id="enc_react_option_test",
                window_id="rw_leave_reach_001",
                group_id="rg_ent_ally_eric_001",
                option_id="opt_opp_001",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
            )

            updated = encounter_repo.get("enc_react_option_test")
            assert updated is not None
            pending = updated.pending_reaction_window
            assert isinstance(pending, dict)
            groups = {group["group_id"]: group for group in pending["choice_groups"]}
            resolved_group = groups["rg_ent_ally_eric_001"]
            self.assertEqual(resolved_group["status"], "resolved")
            resolved_options = {opt["option_id"]: opt for opt in resolved_group["options"]}
            self.assertEqual(resolved_options["opt_opp_001"]["status"], "resolved")
            self.assertEqual(resolved_options["opt_shield_001"]["status"], "declined")
            self.assertIn("rg_ent_ally_eric_001", pending["resolved_group_ids"])
            self.assertTrue(updated.entities["ent_ally_eric_001"].action_economy["reaction_used"])
            self.assertEqual(updated.reaction_requests[0]["status"], "resolved")
            self.assertEqual(updated.reaction_requests[1]["status"], "declined")
            self.assertEqual(result["reaction_type"], "opportunity_attack")
            self.assertEqual(result["window_status"], "waiting_reaction")
            self.assertEqual(result["resolution_mode"], "append_followup_action")
            self.assertEqual(result["window_id"], "rw_leave_reach_001")
            self.assertIn("event_id", result)
            self.assertIn("attack_result", result)
            encounter_repo.close()
            event_repo.close()

    def test_execute_closes_window_when_no_pending_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(include_second_group=False))

            service = self._build_service(encounter_repo, event_repo)
            result = service.execute(
                encounter_id="enc_react_option_test",
                window_id="rw_leave_reach_001",
                group_id="rg_ent_ally_eric_001",
                option_id="opt_opp_001",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
                damage_rolls=[{"source": "weapon:rapier:part_0", "rolls": [6]}],
            )

            updated = encounter_repo.get("enc_react_option_test")
            assert updated is not None
            self.assertIsNone(updated.pending_reaction_window)
            self.assertEqual(result["window_status"], "closed")
            self.assertEqual(result["resolution_mode"], "append_followup_action")
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
