"""Tests for resolving a reaction option via the reaction window."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository, SpellDefinitionRepository
from tools.services import (
    AppendEvent,
    AttackRollRequest,
    AttackRollResult,
    ExecuteAttack,
    UpdateHp,
)
from tools.services.combat.rules.reactions.resolve_reaction_option import ResolveReactionOption
from tools.services.spells.encounter_cast_spell import EncounterCastSpell


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


def build_shield_target() -> EncounterEntity:
    target = build_target()
    target.side = "ally"
    target.controller = "player"
    target.entity_id = "ent_ally_wizard_001"
    target.name = "Wizard"
    target.ac = 12
    target.action_economy = {"reaction_used": False}
    target.resources = {"spell_slots": {"1": {"max": 1, "remaining": 1}}}
    target.spells = [{"spell_id": "shield", "name": "Shield", "level": 1}]
    return target


def build_counterspell_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_counter_001",
        name="Counter Mage",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 4, "y": 4},
        hp={"current": 16, "max": 16, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=11,
        action_economy={"reaction_used": False},
        resources={"spell_slots": {"3": {"max": 1, "remaining": 1}}},
        spells=[{"spell_id": "counterspell", "name": "Counterspell", "level": 3}],
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
    def _build_service(
        self,
        encounter_repo: EncounterRepository,
        event_repo: EventRepository,
        spell_repo: Optional[SpellDefinitionRepository] = None,
    ) -> ResolveReactionOption:
        append_event = AppendEvent(event_repo)
        execute_attack = ExecuteAttack(
            AttackRollRequest(encounter_repo),
            AttackRollResult(encounter_repo, append_event, UpdateHp(encounter_repo, append_event)),
        )
        encounter_cast_spell = EncounterCastSpell(
            encounter_repo,
            append_event,
            spell_definition_repository=spell_repo,
        )
        return ResolveReactionOption(
            encounter_repo,
            append_event,
            execute_attack,
            encounter_cast_spell=encounter_cast_spell,
        )

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

    def test_execute_resolves_shield_and_resumes_attack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            attacker = build_attacker()
            target = build_shield_target()
            encounter = Encounter(
                encounter_id="enc_react_shield_test",
                name="Reaction Shield Encounter",
                status="active",
                round=1,
                current_entity_id=attacker.entity_id,
                turn_order=[attacker.entity_id, target.entity_id],
                entities={attacker.entity_id: attacker, target.entity_id: target},
                map=EncounterMap(
                    map_id="map_react_shield_test",
                    name="Reaction Shield Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
                reaction_requests=[
                    {
                        "request_id": "react_shield_001",
                        "reaction_type": "shield",
                        "template_type": "targeted_defense_rewrite",
                        "trigger_type": "attack_declared",
                        "status": "pending",
                        "actor_entity_id": target.entity_id,
                        "target_entity_id": target.entity_id,
                        "ask_player": True,
                        "auto_resolve": False,
                        "payload": {},
                    }
                ],
                pending_reaction_window={
                    "window_id": "rw_attack_declared_001",
                    "status": "waiting_reaction",
                    "trigger_event_id": "evt_attack_declared_001",
                    "trigger_type": "attack_declared",
                    "blocking": True,
                    "host_action_type": "attack",
                    "host_action_id": "atk_001",
                    "host_action_snapshot": {
                        "actor_id": attacker.entity_id,
                        "target_id": target.entity_id,
                        "weapon_id": "rapier",
                        "final_total": 17,
                        "dice_rolls": {"base_rolls": [12], "modifier": 5},
                        "damage_rolls": [{"source": "weapon:rapier:part_0", "rolls": [6]}],
                        "attack_mode": "default",
                        "grip_mode": "default",
                        "vantage": "normal",
                        "description": "Rapier attack",
                    },
                    "choice_groups": [
                        {
                            "group_id": f"rg_{target.entity_id}",
                            "actor_entity_id": target.entity_id,
                            "ask_player": True,
                            "status": "pending",
                            "resource_pool": "reaction",
                            "group_priority": 100,
                            "trigger_sequence": 1,
                            "relationship_rank": 1,
                            "tie_break_key": target.entity_id,
                            "options": [
                                {
                                    "option_id": "opt_shield_001",
                                    "reaction_type": "shield",
                                    "template_type": "targeted_defense_rewrite",
                                    "request_id": "react_shield_001",
                                    "label": "Shield",
                                    "status": "pending",
                                }
                            ],
                        }
                    ],
                    "resolved_group_ids": [],
                },
            )
            encounter_repo.save(encounter)

            service = self._build_service(encounter_repo, event_repo)
            result = service.execute(
                encounter_id="enc_react_shield_test",
                window_id="rw_attack_declared_001",
                group_id=f"rg_{target.entity_id}",
                option_id="opt_shield_001",
                final_total=0,
                dice_rolls={"base_rolls": [1], "modifier": -1},
            )

            self.assertEqual(result["reaction_type"], "shield")
            self.assertEqual(result["resolution_mode"], "rewrite_host_action")
            host_result = result.get("host_action_result")
            self.assertIsInstance(host_result, dict)
            self.assertIn("request", host_result)
            self.assertIn("resolution", host_result)
            encounter_repo.close()
            event_repo.close()

    def test_execute_resolves_counterspell_and_resumes_spell_cast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "fireball": {
                                "id": "fireball",
                                "name": "Fireball",
                                "level": 3,
                                "base": {"level": 3, "casting_time": "1 action", "concentration": False},
                                "resolution": {"activation": "action"},
                                "targeting": {"type": "area_sphere", "allowed_target_types": ["creature"]},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            caster = build_attacker()
            caster.entity_id = "ent_enemy_mage_001"
            caster.name = "Enemy Mage"
            caster.side = "enemy"
            caster.controller = "gm"
            caster.resources = {"spell_slots": {"3": {"max": 1, "remaining": 1}}}
            caster.spells = [{"spell_id": "fireball", "name": "Fireball", "level": 3}]
            counterspeller = build_counterspell_actor()
            encounter = Encounter(
                encounter_id="enc_react_counterspell_test",
                name="Reaction Counterspell Encounter",
                status="active",
                round=1,
                current_entity_id=caster.entity_id,
                turn_order=[caster.entity_id, counterspeller.entity_id],
                entities={caster.entity_id: caster, counterspeller.entity_id: counterspeller},
                map=EncounterMap(
                    map_id="map_react_counterspell_test",
                    name="Reaction Counterspell Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
                reaction_requests=[
                    {
                        "request_id": "react_counter_001",
                        "reaction_type": "counterspell",
                        "template_type": "cast_interrupt_contest",
                        "trigger_type": "spell_declared",
                        "status": "pending",
                        "actor_entity_id": counterspeller.entity_id,
                        "target_entity_id": caster.entity_id,
                        "ask_player": True,
                        "auto_resolve": False,
                        "payload": {},
                    }
                ],
                pending_reaction_window={
                    "window_id": "rw_spell_declared_001",
                    "status": "waiting_reaction",
                    "trigger_event_id": "evt_spell_declared_001",
                    "trigger_type": "spell_declared",
                    "blocking": True,
                    "host_action_type": "spell_cast",
                    "host_action_id": "spell_001",
                    "host_action_snapshot": {
                        "actor_id": caster.entity_id,
                        "spell_id": "fireball",
                        "cast_level": 3,
                        "target_ids": [],
                        "target_point": {"x": 2, "y": 2},
                        "allow_out_of_turn_actor": False,
                    },
                    "choice_groups": [
                        {
                            "group_id": f"rg_{counterspeller.entity_id}",
                            "actor_entity_id": counterspeller.entity_id,
                            "ask_player": True,
                            "status": "pending",
                            "resource_pool": "reaction",
                            "group_priority": 100,
                            "trigger_sequence": 1,
                            "relationship_rank": 1,
                            "tie_break_key": counterspeller.entity_id,
                            "options": [
                                {
                                    "option_id": "opt_counter_001",
                                    "reaction_type": "counterspell",
                                    "template_type": "cast_interrupt_contest",
                                    "request_id": "react_counter_001",
                                    "label": "Counterspell",
                                    "status": "pending",
                                }
                            ],
                        }
                    ],
                    "resolved_group_ids": [],
                },
            )
            encounter_repo.save(encounter)

            service = self._build_service(encounter_repo, event_repo, spell_repo)
            result = service.execute(
                encounter_id="enc_react_counterspell_test",
                window_id="rw_spell_declared_001",
                group_id=f"rg_{counterspeller.entity_id}",
                option_id="opt_counter_001",
                final_total=0,
                dice_rolls={"base_rolls": [1], "modifier": -1},
            )

            self.assertEqual(result["reaction_type"], "counterspell")
            self.assertEqual(result["resolution_mode"], "rewrite_host_action")
            host_result = result.get("host_action_result")
            self.assertIsInstance(host_result, dict)
            self.assertEqual(host_result.get("spell_id"), "fireball")
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
