"""Tests for resolving a reaction option via the reaction window."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

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
from tools.services.combat.rules.reactions.definitions import indomitable as indomitable_module
from tools.services.combat.rules.reactions.templates import cast_interrupt_contest as cast_interrupt_contest_module
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
        source_ref={"spellcasting_ability": "int"},
        ability_mods={"str": 0, "dex": 2, "con": 1, "int": 4, "wis": 1, "cha": 0},
        proficiency_bonus=3,
        action_economy={"reaction_used": False},
        resources={"spell_slots": {"3": {"max": 1, "remaining": 1}}},
        spells=[{"spell_id": "counterspell", "name": "Counterspell", "level": 3}],
    )


def build_indomitable_fighter() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_fighter_009",
        name="Fighter",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 4, "y": 4},
        hp={"current": 28, "max": 28, "temp": 0},
        ac=17,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        ability_scores={"str": 18, "dex": 10, "con": 16, "int": 10, "wis": 12, "cha": 8},
        ability_mods={"str": 4, "dex": 0, "con": 3, "int": 0, "wis": 1, "cha": -1},
        proficiency_bonus=4,
        save_proficiencies=["str", "con"],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": True},
        class_features={
            "fighter": {
                "fighter_level": 9,
                "indomitable": {"remaining_uses": 1, "max_uses": 1},
            }
        },
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

    def test_resolve_indomitable_rerolls_save_and_adds_fighter_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            fighter = build_indomitable_fighter()
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_indomitable_option_test",
                    name="Indomitable Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=fighter.entity_id,
                    turn_order=[fighter.entity_id],
                    entities={fighter.entity_id: fighter},
                    map=EncounterMap(
                        map_id="map_indomitable_option_test",
                        name="Indomitable Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_indomitable_001",
                            "reaction_type": "indomitable",
                            "template_type": "failed_save_reroll",
                            "trigger_type": "failed_save",
                            "status": "pending",
                            "actor_entity_id": fighter.entity_id,
                            "target_entity_id": fighter.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {
                                "save_ability": "wis",
                                "save_dc": 15,
                                "vantage": "normal",
                            },
                        }
                    ],
                    pending_reaction_window={
                        "window_id": "rw_failed_save_001",
                        "status": "waiting_reaction",
                        "trigger_event_id": "evt_failed_save_001",
                        "trigger_type": "failed_save",
                        "blocking": True,
                        "host_action_type": "save",
                        "host_action_id": "save_001",
                        "host_action_snapshot": {
                            "phase": "after_failed_save",
                            "target_entity_id": fighter.entity_id,
                            "save_ability": "wis",
                            "save_dc": 15,
                        },
                        "choice_groups": [
                            {
                                "group_id": f"rg_{fighter.entity_id}",
                                "actor_entity_id": fighter.entity_id,
                                "ask_player": True,
                                "status": "pending",
                                "resource_pool": "class_feature",
                                "group_priority": 100,
                                "trigger_sequence": 1,
                                "relationship_rank": 1,
                                "tie_break_key": fighter.entity_id,
                                "options": [
                                    {
                                        "option_id": "opt_indomitable_001",
                                        "reaction_type": "indomitable",
                                        "template_type": "failed_save_reroll",
                                        "request_id": "react_indomitable_001",
                                        "label": "Indomitable",
                                        "status": "pending",
                                    }
                                ],
                            }
                        ],
                        "resolved_group_ids": [],
                    },
                )
            )

            service = self._build_service(encounter_repo, event_repo)
            with patch.object(indomitable_module.random, "randint", side_effect=[7]):
                result = service.execute(
                    encounter_id="enc_indomitable_option_test",
                    window_id="rw_failed_save_001",
                    group_id=f"rg_{fighter.entity_id}",
                    option_id="opt_indomitable_001",
                    final_total=0,
                    dice_rolls={},
                )

            updated = encounter_repo.get("enc_indomitable_option_test")
            assert updated is not None
            fighter_state = updated.entities[fighter.entity_id].class_features["fighter"]
            self.assertEqual(result["reaction_type"], "indomitable")
            self.assertEqual(result["resolution_mode"], "standalone")
            self.assertEqual(result["reaction_result"]["status"], "rerolled")
            self.assertEqual(result["reaction_result"]["save"]["fighter_level_bonus"], 9)
            self.assertTrue(result["reaction_result"]["save"]["success"])
            self.assertEqual(result["reaction_result"]["save"]["final_total"], 17)
            self.assertEqual(fighter_state["indomitable"]["remaining_uses"], 0)
            self.assertTrue(updated.entities[fighter.entity_id].action_economy["reaction_used"])
            encounter_repo.close()
            event_repo.close()

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
                        "final_total": 16,
                        "dice_rolls": {"base_rolls": [11], "modifier": 5},
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
            self.assertFalse(host_result["resolution"]["hit"])
            self.assertEqual(host_result["resolution"]["target_ac"], 17)

            updated = encounter_repo.get("enc_react_shield_test")
            assert updated is not None
            updated_target = updated.entities[target.entity_id]
            self.assertTrue(updated_target.action_economy["reaction_used"])
            self.assertEqual(updated_target.resources["spell_slots"]["1"]["remaining"], 0)
            self.assertEqual(updated_target.ac, 17)
            self.assertEqual(len(updated_target.turn_effects), 1)
            self.assertEqual(updated_target.turn_effects[0]["effect_type"], "shield_ac_bonus")
            self.assertEqual(updated_target.turn_effects[0]["trigger"], "start_of_turn")
            encounter_repo.close()
            event_repo.close()

    def test_execute_resolves_counterspell_and_cancels_spell_on_failed_con_save(self) -> None:
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
            caster.source_ref = {"spellcasting_ability": "int"}
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
                        "spell_level": 3,
                        "cast_level": 3,
                        "target_ids": [],
                        "target_point": {"x": 2, "y": 2},
                        "action_cost": "action",
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
            with patch.object(cast_interrupt_contest_module.random, "randint", return_value=4):
                result = service.execute(
                    encounter_id="enc_react_counterspell_test",
                    window_id="rw_spell_declared_001",
                    group_id=f"rg_{counterspeller.entity_id}",
                    option_id="opt_counter_001",
                    final_total=0,
                    dice_rolls={"base_rolls": [1], "modifier": -1},
                )

            self.assertEqual(result["reaction_type"], "counterspell")
            self.assertEqual(result["resolution_mode"], "cancel_host_action")
            self.assertIsNone(result.get("host_action_result"))
            self.assertEqual(result["reaction_result"]["status"], "countered")
            self.assertFalse(result["reaction_result"]["save"]["success"])

            updated = encounter_repo.get("enc_react_counterspell_test")
            assert updated is not None
            self.assertTrue(updated.entities[counterspeller.entity_id].action_economy["reaction_used"])
            self.assertEqual(updated.entities[counterspeller.entity_id].resources["spell_slots"]["3"]["remaining"], 0)
            self.assertEqual(updated.entities[caster.entity_id].resources["spell_slots"]["3"]["remaining"], 1)
            self.assertTrue(updated.entities[caster.entity_id].action_economy["action_used"])
            self.assertIsNone(updated.pending_reaction_window)
            encounter_repo.close()
            event_repo.close()

    def test_execute_resolves_counterspell_and_resumes_spell_on_successful_con_save(self) -> None:
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
            caster.source_ref = {"spellcasting_ability": "int"}
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
                        "spell_level": 3,
                        "cast_level": 3,
                        "target_ids": [],
                        "target_point": {"x": 2, "y": 2},
                        "action_cost": "action",
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
            with patch.object(cast_interrupt_contest_module.random, "randint", return_value=19):
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
            self.assertEqual(result["reaction_result"]["status"], "save_succeeded")
            self.assertTrue(result["reaction_result"]["save"]["success"])
            host_result = result.get("host_action_result")
            self.assertIsInstance(host_result, dict)
            self.assertEqual(host_result.get("spell_id"), "fireball")

            updated = encounter_repo.get("enc_react_counterspell_test")
            assert updated is not None
            self.assertTrue(updated.entities[counterspeller.entity_id].action_economy["reaction_used"])
            self.assertEqual(updated.entities[counterspeller.entity_id].resources["spell_slots"]["3"]["remaining"], 0)
            self.assertEqual(updated.entities[caster.entity_id].resources["spell_slots"]["3"]["remaining"], 0)
            self.assertTrue(updated.entities[caster.entity_id].action_economy["action_used"])
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
