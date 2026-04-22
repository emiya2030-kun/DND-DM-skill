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
from tools.services.combat.rules.reactions.definitions import tactical_mind as tactical_mind_module
from tools.services.combat.rules.reactions.definitions import countercharm as countercharm_module
from tools.services.combat.rules.reactions.definitions import disciplined_survivor as disciplined_survivor_module
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


def build_deflect_monk_target() -> EncounterEntity:
    target = build_target()
    target.side = "ally"
    target.controller = "player"
    target.entity_id = "ent_ally_monk_001"
    target.name = "Monk"
    target.ac = 14
    target.action_economy = {"reaction_used": False}
    target.class_features = {
        "monk": {
            "level": 5,
            "focus_points": {"max": 5, "remaining": 3},
            "deflect_attacks": {"enabled": True},
            "martial_arts_die": "1d8",
        }
    }
    return target


def build_uncanny_dodge_target() -> EncounterEntity:
    target = build_target()
    target.side = "ally"
    target.controller = "player"
    target.entity_id = "ent_ally_rogue_001"
    target.name = "Rogue"
    target.ac = 14
    target.action_economy = {"reaction_used": False}
    target.class_features = {
        "rogue": {
            "level": 5,
        }
    }
    return target


def build_interceptor() -> EncounterEntity:
    actor = build_secondary_actor()
    actor.entity_id = "ent_ally_interceptor_001"
    actor.name = "Interceptor"
    actor.position = {"x": 4, "y": 3}
    actor.proficiency_bonus = 3
    actor.weapons = [
        {
            "weapon_id": "longsword",
            "name": "Longsword",
            "category": "martial",
            "kind": "melee",
            "damage": [{"formula": "1d8+3", "type": "slashing"}],
            "properties": [],
            "range": {"normal": 5, "long": 5},
            "slot": "main_hand",
        }
    ]
    actor.class_features = {"fighter": {"level": 1, "fighting_style": {"style_id": "interception"}}}
    return actor


def build_protection_fighter() -> EncounterEntity:
    actor = build_secondary_actor()
    actor.entity_id = "ent_ally_protector_001"
    actor.name = "Protector"
    actor.position = {"x": 4, "y": 3}
    actor.equipped_shield = {"armor_id": "shield"}
    actor.class_features = {"fighter": {"level": 1, "fighting_style": {"style_id": "protection"}}}
    return actor


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


def build_disciplined_survivor_monk() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_monk_014",
        name="Monk",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 4, "y": 4},
        hp={"current": 32, "max": 32, "temp": 0},
        ac=18,
        speed={"walk": 45, "remaining": 45},
        initiative=14,
        ability_scores={"str": 10, "dex": 18, "con": 14, "int": 10, "wis": 16, "cha": 8},
        ability_mods={"str": 0, "dex": 4, "con": 2, "int": 0, "wis": 3, "cha": -1},
        proficiency_bonus=5,
        save_proficiencies=["str", "dex", "con", "int", "wis", "cha"],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": True},
        class_features={
            "monk": {
                "level": 14,
                "focus_points": {"remaining": 2, "max": 14},
            }
        },
    )


def build_tactical_mind_fighter() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_fighter_tm_001",
        name="Sabur",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 21, "max": 21, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        ability_mods={"str": 1, "dex": 3, "wis": 2},
        proficiency_bonus=2,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={
            "fighter": {
                "level": 2,
                "tactical_mind": {"enabled": True},
                "second_wind": {"remaining_uses": 2, "max_uses": 2},
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

    def test_resolve_tactical_mind_rewrites_failed_ability_check_without_spending_reaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            fighter = build_tactical_mind_fighter()
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_tactical_mind_option_test",
                    name="Tactical Mind Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=fighter.entity_id,
                    turn_order=[fighter.entity_id],
                    entities={fighter.entity_id: fighter},
                    map=EncounterMap(
                        map_id="map_tactical_mind_option_test",
                        name="Tactical Mind Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_tactical_mind_001",
                            "reaction_type": "tactical_mind",
                            "template_type": "failed_ability_check_boost",
                            "trigger_type": "failed_ability_check",
                            "status": "pending",
                            "actor_entity_id": fighter.entity_id,
                            "target_entity_id": fighter.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {
                                "dc": 15,
                                "current_total": 7,
                                "bonus_formula": "1d10",
                                "consume_only_on_success": True,
                            },
                        }
                    ],
                    pending_reaction_window={
                        "window_id": "rw_failed_ability_check_001",
                        "status": "waiting_reaction",
                        "trigger_event_id": "evt_failed_ability_check_001",
                        "trigger_type": "failed_ability_check",
                        "blocking": True,
                        "host_action_type": "ability_check",
                        "host_action_id": "ability_check_001",
                        "host_action_snapshot": {
                            "roll_request": {
                                "type": "request_roll",
                                "request_id": "req_ability_001",
                                "encounter_id": "enc_tactical_mind_option_test",
                                "actor_entity_id": fighter.entity_id,
                                "target_entity_id": None,
                                "roll_type": "ability_check",
                                "formula": "1d20+check_modifier",
                                "reason": "Strength check",
                                "context": {
                                    "check_type": "ability",
                                    "check": "str",
                                    "dc": 15,
                                    "vantage": "normal",
                                },
                            },
                            "roll_result": {
                                "type": "roll_result",
                                "request_id": "req_ability_001",
                                "encounter_id": "enc_tactical_mind_option_test",
                                "actor_entity_id": fighter.entity_id,
                                "target_entity_id": None,
                                "roll_type": "ability_check",
                                "final_total": 7,
                                "dice_rolls": {
                                    "base_rolls": [6],
                                    "chosen_roll": 6,
                                    "check_bonus": 1,
                                    "additional_bonus": 0,
                                    "d20_penalty": 0,
                                },
                                "metadata": {
                                    "check_type": "ability",
                                    "check": "str",
                                    "vantage": "normal",
                                    "requested_vantage": "normal",
                                    "chosen_roll": 6,
                                    "check_bonus": 1,
                                    "check_bonus_breakdown": {
                                        "source": "ability_modifier",
                                        "ability": "str",
                                        "ability_modifier": 1,
                                        "additional_bonus": 0,
                                    },
                                    "d20_penalty": 0,
                                },
                                "rolled_at": None,
                            },
                            "check": "力量",
                            "normalized_check": "str",
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
                                        "option_id": "opt_tactical_mind_001",
                                        "reaction_type": "tactical_mind",
                                        "template_type": "failed_ability_check_boost",
                                        "request_id": "react_tactical_mind_001",
                                        "label": "Tactical Mind",
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
            with patch.object(tactical_mind_module.random, "randint", side_effect=[8]):
                result = service.execute(
                    encounter_id="enc_tactical_mind_option_test",
                    window_id="rw_failed_ability_check_001",
                    group_id=f"rg_{fighter.entity_id}",
                    option_id="opt_tactical_mind_001",
                    final_total=0,
                    dice_rolls={},
                )

            updated = encounter_repo.get("enc_tactical_mind_option_test")
            assert updated is not None
            fighter_state = updated.entities[fighter.entity_id].class_features["fighter"]
            self.assertEqual(result["reaction_type"], "tactical_mind")
            self.assertEqual(result["resolution_mode"], "rewrite_host_action")
            self.assertEqual(result["reaction_result"]["bonus_roll"], 8)
            self.assertTrue(result["reaction_result"]["consumed_second_wind"])
            self.assertIsNotNone(result["host_action_result"])
            self.assertTrue(result["host_action_result"]["success"])
            self.assertEqual(result["host_action_result"]["final_total"], 15)
            self.assertEqual(fighter_state["second_wind"]["remaining_uses"], 1)
            self.assertFalse(updated.entities[fighter.entity_id].action_economy["reaction_used"])
            encounter_repo.close()
            event_repo.close()

    def test_resolve_bardic_inspiration_rewrites_failed_ability_check_without_spending_reaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            target = build_shield_target()
            target.entity_id = "ent_bard_target_001"
            target.name = "Bard Target"
            target.action_economy = {"reaction_used": True}
            target.combat_flags["bardic_inspiration"] = {
                "die": "d8",
                "source_entity_id": "ent_bard_001",
                "source_name": "诗人",
            }
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_bardic_inspiration_option_test",
                    name="Bardic Inspiration Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=target.entity_id,
                    turn_order=[target.entity_id],
                    entities={target.entity_id: target},
                    map=EncounterMap(
                        map_id="map_bardic_inspiration_option_test",
                        name="Bardic Inspiration Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_bardic_inspiration_001",
                            "reaction_type": "bardic_inspiration",
                            "template_type": "failed_ability_check_boost",
                            "trigger_type": "failed_ability_check",
                            "status": "pending",
                            "actor_entity_id": target.entity_id,
                            "target_entity_id": target.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {
                                "dc": 15,
                                "current_total": 10,
                                "bonus_formula": "1d8",
                                "source_entity_id": "ent_bard_001",
                                "source_name": "诗人",
                            },
                        }
                    ],
                    pending_reaction_window={
                        "window_id": "rw_failed_ability_check_001",
                        "status": "waiting_reaction",
                        "trigger_event_id": "evt_failed_ability_check_001",
                        "trigger_type": "failed_ability_check",
                        "blocking": True,
                        "host_action_type": "ability_check",
                        "host_action_id": "ability_check_001",
                        "host_action_snapshot": {
                            "roll_request": {
                                "type": "request_roll",
                                "request_id": "req_ability_001",
                                "encounter_id": "enc_bardic_inspiration_option_test",
                                "actor_entity_id": target.entity_id,
                                "target_entity_id": None,
                                "roll_type": "ability_check",
                                "formula": "1d20+check_modifier",
                                "reason": "Dexterity check",
                                "context": {
                                    "check_type": "skill",
                                    "check": "stealth",
                                    "dc": 15,
                                    "vantage": "normal",
                                },
                            },
                            "roll_result": {
                                "type": "roll_result",
                                "request_id": "req_ability_001",
                                "encounter_id": "enc_bardic_inspiration_option_test",
                                "actor_entity_id": target.entity_id,
                                "target_entity_id": None,
                                "roll_type": "ability_check",
                                "final_total": 10,
                                "dice_rolls": {
                                    "base_rolls": [8],
                                    "chosen_roll": 8,
                                    "check_bonus": 2,
                                    "additional_bonus": 0,
                                    "d20_penalty": 0,
                                },
                                "metadata": {
                                    "check_type": "skill",
                                    "check": "stealth",
                                    "vantage": "normal",
                                    "requested_vantage": "normal",
                                    "chosen_roll": 8,
                                    "check_bonus": 2,
                                    "check_bonus_breakdown": {
                                        "source": "skill_modifier",
                                        "ability": "dex",
                                        "skill_modifier": 2,
                                        "additional_bonus": 0,
                                    },
                                    "d20_penalty": 0,
                                },
                                "rolled_at": None,
                            },
                            "check": "隐匿",
                            "normalized_check": "stealth",
                        },
                        "choice_groups": [
                            {
                                "group_id": f"rg_{target.entity_id}",
                                "actor_entity_id": target.entity_id,
                                "ask_player": True,
                                "status": "pending",
                                "resource_pool": "class_feature",
                                "group_priority": 100,
                                "trigger_sequence": 1,
                                "relationship_rank": 1,
                                "tie_break_key": target.entity_id,
                                "options": [
                                    {
                                        "option_id": "opt_bardic_inspiration_001",
                                        "reaction_type": "bardic_inspiration",
                                        "template_type": "failed_ability_check_boost",
                                        "request_id": "react_bardic_inspiration_001",
                                        "label": "Bardic Inspiration",
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
            result = service.execute(
                encounter_id="enc_bardic_inspiration_option_test",
                window_id="rw_failed_ability_check_001",
                group_id=f"rg_{target.entity_id}",
                option_id="opt_bardic_inspiration_001",
                final_total=0,
                dice_rolls={"base_rolls": [6]},
            )

            updated = encounter_repo.get("enc_bardic_inspiration_option_test")
            assert updated is not None
            self.assertEqual(result["reaction_type"], "bardic_inspiration")
            self.assertEqual(result["resolution_mode"], "rewrite_host_action")
            self.assertEqual(result["reaction_result"]["bonus_roll"], 6)
            self.assertIsNotNone(result["host_action_result"])
            self.assertTrue(result["host_action_result"]["success"])
            self.assertEqual(result["host_action_result"]["final_total"], 16)
            self.assertNotIn("bardic_inspiration", updated.entities[target.entity_id].combat_flags)
            self.assertTrue(updated.entities[target.entity_id].action_economy["reaction_used"])
            encounter_repo.close()
            event_repo.close()

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

    def test_resolve_disciplined_survivor_rerolls_save_and_spends_focus_without_reaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            monk = build_disciplined_survivor_monk()
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_disciplined_survivor_option_test",
                    name="Disciplined Survivor Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=monk.entity_id,
                    turn_order=[monk.entity_id],
                    entities={monk.entity_id: monk},
                    map=EncounterMap(
                        map_id="map_disciplined_survivor_option_test",
                        name="Disciplined Survivor Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_disciplined_survivor_001",
                            "reaction_type": "disciplined_survivor",
                            "template_type": "failed_save_reroll",
                            "trigger_type": "failed_save",
                            "status": "pending",
                            "actor_entity_id": monk.entity_id,
                            "target_entity_id": monk.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {
                                "save_ability": "wis",
                                "save_dc": 18,
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
                            "target_entity_id": monk.entity_id,
                            "save_ability": "wis",
                            "save_dc": 18,
                        },
                        "choice_groups": [
                            {
                                "group_id": f"rg_{monk.entity_id}",
                                "actor_entity_id": monk.entity_id,
                                "ask_player": True,
                                "status": "pending",
                                "resource_pool": "class_feature",
                                "group_priority": 100,
                                "trigger_sequence": 1,
                                "relationship_rank": 1,
                                "tie_break_key": monk.entity_id,
                                "options": [
                                    {
                                        "option_id": "opt_disciplined_survivor_001",
                                        "reaction_type": "disciplined_survivor",
                                        "template_type": "failed_save_reroll",
                                        "request_id": "react_disciplined_survivor_001",
                                        "label": "Disciplined Survivor",
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
            with patch.object(disciplined_survivor_module.random, "randint", side_effect=[10]):
                result = service.execute(
                    encounter_id="enc_disciplined_survivor_option_test",
                    window_id="rw_failed_save_001",
                    group_id=f"rg_{monk.entity_id}",
                    option_id="opt_disciplined_survivor_001",
                    final_total=0,
                    dice_rolls={},
                )

            updated = encounter_repo.get("enc_disciplined_survivor_option_test")
            assert updated is not None
            monk_state = updated.entities[monk.entity_id].class_features["monk"]
            self.assertEqual(result["reaction_type"], "disciplined_survivor")
            self.assertEqual(result["resolution_mode"], "standalone")
            self.assertEqual(result["reaction_result"]["status"], "rerolled")
            self.assertTrue(result["reaction_result"]["save"]["success"])
            self.assertEqual(result["reaction_result"]["save"]["final_total"], 18)
            self.assertEqual(monk_state["focus_points"]["remaining"], 1)
            self.assertTrue(updated.entities[monk.entity_id].action_economy["reaction_used"])
            encounter_repo.close()
            event_repo.close()

    def test_resolve_countercharm_rerolls_failed_save_and_resumes_spell_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            bard = build_secondary_actor()
            bard.entity_id = "ent_bard_001"
            bard.name = "Bard"
            bard.position = {"x": 4, "y": 2}
            bard.action_economy = {"reaction_used": False}
            bard.class_features = {"bard": {"level": 7}}

            target = build_shield_target()
            target.entity_id = "ent_countercharm_target_001"
            target.name = "Countercharm Target"
            target.side = "ally"
            target.position = {"x": 7, "y": 2}
            target.ability_mods = {"wis": 1}
            target.proficiency_bonus = 3
            target.save_proficiencies = ["wis"]
            target.action_economy = {"reaction_used": True}
            target.conditions = []
            enemy = build_target()
            enemy.entity_id = "ent_enemy_001"
            enemy.name = "Enemy Caster"
            enemy.side = "enemy"
            enemy.controller = "gm"
            enemy.position = {"x": 2, "y": 2}

            encounter_repo.save(
                Encounter(
                    encounter_id="enc_countercharm_option_test",
                    name="Countercharm Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id="ent_enemy_001",
                    turn_order=["ent_enemy_001", bard.entity_id, target.entity_id],
                    entities={enemy.entity_id: enemy, bard.entity_id: bard, target.entity_id: target},
                    map=EncounterMap(
                        map_id="map_countercharm_option_test",
                        name="Countercharm Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_countercharm_001",
                            "reaction_type": "countercharm",
                            "template_type": "failed_save_reroll",
                            "trigger_type": "failed_save",
                            "status": "pending",
                            "actor_entity_id": bard.entity_id,
                            "target_entity_id": target.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {
                                "target_entity_id": target.entity_id,
                                "save_ability": "wis",
                                "save_dc": 14,
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
                            "target_entity_id": target.entity_id,
                            "save_ability": "wis",
                            "save_dc": 14,
                            "countercharm_trigger_conditions": ["frightened"],
                            "cast": {
                                "spell_id": "fear_burst",
                                "spell_name": "Fear Burst",
                                "cast_level": 2,
                            },
                            "roll_request": {
                                "type": "request_roll",
                                "request_id": "req_save_001",
                                "encounter_id": "enc_countercharm_option_test",
                                "actor_entity_id": target.entity_id,
                                "target_entity_id": target.entity_id,
                                "roll_type": "saving_throw",
                                "formula": "1d20+save_modifier",
                                "reason": "Target makes a WIS save",
                                "context": {
                                    "spell_id": "fear_burst",
                                    "spell_name": "Fear Burst",
                                    "spell_level": 2,
                                    "save_ability": "wis",
                                    "spell_definition": {
                                        "id": "fear_burst",
                                        "name": "Fear Burst",
                                        "level": 2,
                                        "save_ability": "wis",
                                        "failed_save_outcome": {"damage_parts": [], "conditions": ["frightened"], "note": None},
                                        "successful_save_outcome": {"damage_parts": [], "conditions": [], "note": None},
                                    },
                                    "save_dc": 14,
                                    "caster_entity_id": "ent_enemy_001",
                                    "caster_name": "Enemy Caster",
                                    "damage": [],
                                    "half_on_success": False,
                                    "vantage": "normal",
                                    "vantage_sources": {"advantage": [], "disadvantage": []},
                                    "auto_success": False,
                                    "metamagic": {},
                                    "distance_to_target": "25 ft",
                                    "distance_to_target_feet": 25,
                                },
                            },
                            "roll_result": {
                                "type": "roll_result",
                                "request_id": "req_save_001",
                                "encounter_id": "enc_countercharm_option_test",
                                "actor_entity_id": target.entity_id,
                                "target_entity_id": target.entity_id,
                                "roll_type": "saving_throw",
                                "final_total": 9,
                                "dice_rolls": {
                                    "base_rolls": [5],
                                    "chosen_roll": 5,
                                    "ability_modifier": 1,
                                    "proficiency_bonus": 3,
                                    "additional_bonus": 0,
                                    "save_bonus": 4,
                                    "d20_penalty": 0,
                                    "aura_of_protection_bonus": 0,
                                },
                                "metadata": {
                                    "save_ability": "wis",
                                    "vantage": "normal",
                                    "rolled_vantage": "normal",
                                    "chosen_roll": 5,
                                    "save_bonus": 4,
                                    "save_bonus_breakdown": {
                                        "ability_modifier": 1,
                                        "is_proficient": True,
                                        "proficiency_bonus_applied": 3,
                                        "additional_bonus": 0,
                                        "aura_of_protection_bonus": 0,
                                    },
                                },
                                "rolled_at": None,
                            },
                            "saving_throw_result_args": {
                                "spell_definition": {
                                    "id": "fear_burst",
                                    "name": "Fear Burst",
                                    "level": 2,
                                    "save_ability": "wis",
                                    "failed_save_outcome": {"damage_parts": [], "conditions": ["frightened"], "note": None},
                                    "successful_save_outcome": {"damage_parts": [], "conditions": [], "note": None},
                                },
                                "damage_rolls": [],
                                "cast_level": 2,
                                "hp_change_on_failed_save": None,
                                "hp_change_on_success": None,
                                "damage_reason": None,
                                "damage_type": None,
                                "concentration_vantage": "normal",
                                "conditions_on_failed_save": None,
                                "conditions_on_success": None,
                                "note_on_failed_save": None,
                                "note_on_success": None,
                            },
                        },
                        "choice_groups": [
                            {
                                "group_id": f"rg_{bard.entity_id}",
                                "actor_entity_id": bard.entity_id,
                                "ask_player": True,
                                "status": "pending",
                                "resource_pool": "reaction",
                                "group_priority": 100,
                                "trigger_sequence": 1,
                                "relationship_rank": 1,
                                "tie_break_key": bard.entity_id,
                                "options": [
                                    {
                                        "option_id": "opt_countercharm_001",
                                        "reaction_type": "countercharm",
                                        "template_type": "failed_save_reroll",
                                        "request_id": "react_countercharm_001",
                                        "label": "Countercharm",
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
            with patch.object(countercharm_module.random, "randint", side_effect=[4, 16]):
                result = service.execute(
                    encounter_id="enc_countercharm_option_test",
                    window_id="rw_failed_save_001",
                    group_id=f"rg_{bard.entity_id}",
                    option_id="opt_countercharm_001",
                    final_total=0,
                    dice_rolls={},
                )

            updated = encounter_repo.get("enc_countercharm_option_test")
            assert updated is not None
            self.assertEqual(result["reaction_type"], "countercharm")
            self.assertEqual(result["resolution_mode"], "rewrite_host_action")
            self.assertEqual(result["reaction_result"]["save"]["final_total"], 20)
            self.assertIsNotNone(result["host_action_result"])
            self.assertTrue(result["host_action_result"]["resolution"]["success"])
            self.assertEqual(result["host_action_result"]["resolution"]["selected_outcome"], "successful_save")
            self.assertEqual(updated.entities[bard.entity_id].action_economy["reaction_used"], True)
            self.assertNotIn("frightened", updated.entities[target.entity_id].conditions)
            encounter_repo.close()
            event_repo.close()

    def test_execute_resolves_deflect_attacks_and_arms_pending_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            attacker = build_attacker()
            monk = build_deflect_monk_target()
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_deflect_option_test",
                    name="Deflect Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=attacker.entity_id,
                    turn_order=[attacker.entity_id, monk.entity_id],
                    entities={attacker.entity_id: attacker, monk.entity_id: monk},
                    map=EncounterMap(
                        map_id="map_deflect_option_test",
                        name="Deflect Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_deflect_001",
                            "reaction_type": "deflect_attacks",
                            "template_type": "defensive_reaction_reduce_damage",
                            "trigger_type": "attack_declared",
                            "status": "pending",
                            "actor_entity_id": monk.entity_id,
                            "target_entity_id": monk.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {
                                "primary_damage_type": "piercing",
                                "source_actor_id": attacker.entity_id,
                                "weapon_id": "rapier",
                            },
                        }
                    ],
                    pending_reaction_window={
                        "window_id": "rw_attack_declared_001",
                        "status": "waiting_reaction",
                        "trigger_event_id": "evt_attack_declared_001",
                        "trigger_type": "attack_declared",
                        "blocking": True,
                        "host_action_type": "attack",
                        "host_action_id": "attack_deflect_001",
                        "host_action_snapshot": {
                            "attack_id": "attack_deflect_001",
                            "actor_id": attacker.entity_id,
                            "target_id": monk.entity_id,
                            "weapon_id": "rapier",
                            "final_total": 18,
                            "dice_rolls": {"base_rolls": [13], "modifier": 5},
                            "damage_rolls": [{"source": "weapon:rapier:part_0", "rolls": [6]}],
                            "vantage": "normal",
                            "consume_action": True,
                            "consume_reaction": False,
                        },
                        "choice_groups": [
                            {
                                "group_id": f"rg_{monk.entity_id}",
                                "actor_entity_id": monk.entity_id,
                                "ask_player": True,
                                "status": "pending",
                                "resource_pool": "reaction",
                                "group_priority": 100,
                                "trigger_sequence": 1,
                                "relationship_rank": 1,
                                "tie_break_key": monk.entity_id,
                                "options": [
                                    {
                                        "option_id": "opt_deflect_001",
                                        "reaction_type": "deflect_attacks",
                                        "template_type": "defensive_reaction_reduce_damage",
                                        "request_id": "react_deflect_001",
                                        "label": "Deflect Attacks",
                                        "status": "pending",
                                    }
                                ],
                            }
                        ],
                        "resolved_group_ids": [],
                    },
                )
            )

            result = self._build_service(encounter_repo, event_repo).execute(
                encounter_id="enc_deflect_option_test",
                window_id="rw_attack_declared_001",
                group_id=f"rg_{monk.entity_id}",
                option_id="opt_deflect_001",
                final_total=0,
                dice_rolls={},
                option_payload={"reduction_roll": 7},
            )

            updated = encounter_repo.get("enc_deflect_option_test")
            assert updated is not None
            monk = updated.entities["ent_ally_monk_001"]
            self.assertEqual(result["reaction_result"]["status"], "deflect_attacks_armed")
            self.assertTrue(monk.action_economy["reaction_used"])
            self.assertFalse(
                any(effect.get("effect_type") == "deflect_attacks_pending" for effect in monk.turn_effects)
            )
            self.assertEqual(
                result["host_action_result"]["resolution"]["deflect_attacks"]["status"],
                "damage_reduced",
            )
            encounter_repo.close()
            event_repo.close()

    def test_execute_resolves_deflect_energy_on_fire_damage_and_arms_pending_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            attacker = build_attacker()
            monk = build_deflect_monk_target()
            monk.class_features["monk"]["level"] = 13
            monk.class_features["monk"]["deflect_energy"] = {"enabled": True}
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_deflect_energy_option_test",
                    name="Deflect Energy Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=attacker.entity_id,
                    turn_order=[attacker.entity_id, monk.entity_id],
                    entities={attacker.entity_id: attacker, monk.entity_id: monk},
                    map=EncounterMap(
                        map_id="map_deflect_energy_option_test",
                        name="Deflect Energy Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_deflect_energy_001",
                            "reaction_type": "deflect_attacks",
                            "template_type": "defensive_reaction_reduce_damage",
                            "trigger_type": "attack_declared",
                            "status": "pending",
                            "actor_entity_id": monk.entity_id,
                            "target_entity_id": monk.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {
                                "primary_damage_type": "fire",
                                "source_actor_id": attacker.entity_id,
                                "weapon_id": "rapier",
                            },
                        }
                    ],
                    pending_reaction_window={
                        "window_id": "rw_attack_declared_001",
                        "status": "waiting_reaction",
                        "trigger_event_id": "evt_attack_declared_001",
                        "trigger_type": "attack_declared",
                        "blocking": True,
                        "host_action_type": "attack",
                        "host_action_id": "attack_deflect_energy_001",
                        "host_action_snapshot": {
                            "attack_id": "attack_deflect_energy_001",
                            "actor_id": attacker.entity_id,
                            "target_id": monk.entity_id,
                            "weapon_id": "rapier",
                            "final_total": 18,
                            "dice_rolls": {"base_rolls": [13], "modifier": 5},
                            "damage_rolls": [{"source": "weapon:rapier:part_0", "rolls": [6]}],
                            "vantage": "normal",
                            "consume_action": True,
                            "consume_reaction": False,
                            "primary_damage_type": "fire",
                        },
                        "choice_groups": [
                            {
                                "group_id": f"rg_{monk.entity_id}",
                                "actor_entity_id": monk.entity_id,
                                "ask_player": True,
                                "status": "pending",
                                "resource_pool": "reaction",
                                "group_priority": 100,
                                "trigger_sequence": 1,
                                "relationship_rank": 1,
                                "tie_break_key": monk.entity_id,
                                "options": [
                                    {
                                        "option_id": "opt_deflect_energy_001",
                                        "reaction_type": "deflect_attacks",
                                        "template_type": "defensive_reaction_reduce_damage",
                                        "request_id": "react_deflect_energy_001",
                                        "label": "Deflect Attacks",
                                        "status": "pending",
                                    }
                                ],
                            }
                        ],
                        "resolved_group_ids": [],
                    },
                )
            )

            result = self._build_service(encounter_repo, event_repo).execute(
                encounter_id="enc_deflect_energy_option_test",
                window_id="rw_attack_declared_001",
                group_id=f"rg_{monk.entity_id}",
                option_id="opt_deflect_energy_001",
                final_total=0,
                dice_rolls={},
                option_payload={"reduction_roll": 7},
            )

            updated = encounter_repo.get("enc_deflect_energy_option_test")
            assert updated is not None
            self.assertEqual(result["reaction_result"]["status"], "deflect_attacks_armed")
            self.assertEqual(
                result["host_action_result"]["resolution"]["deflect_attacks"]["status"],
                "damage_reduced",
            )
            encounter_repo.close()
            event_repo.close()

    def test_execute_resolves_uncanny_dodge_and_halves_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            attacker = build_attacker()
            target = build_uncanny_dodge_target()
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_uncanny_dodge_option_test",
                    name="Uncanny Dodge Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=attacker.entity_id,
                    turn_order=[attacker.entity_id, target.entity_id],
                    entities={attacker.entity_id: attacker, target.entity_id: target},
                    map=EncounterMap(
                        map_id="map_uncanny_dodge_option_test",
                        name="Uncanny Dodge Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_uncanny_001",
                            "reaction_type": "uncanny_dodge",
                            "template_type": "defensive_reaction_reduce_damage",
                            "trigger_type": "attack_declared",
                            "status": "pending",
                            "actor_entity_id": target.entity_id,
                            "target_entity_id": target.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {
                                "source_actor_id": attacker.entity_id,
                                "weapon_id": "rapier",
                            },
                        }
                    ],
                    pending_reaction_window={
                        "window_id": "rw_attack_declared_uncanny_001",
                        "status": "waiting_reaction",
                        "trigger_event_id": "evt_attack_declared_uncanny_001",
                        "trigger_type": "attack_declared",
                        "blocking": True,
                        "host_action_type": "attack",
                        "host_action_id": "attack_uncanny_001",
                        "host_action_snapshot": {
                            "attack_id": "attack_uncanny_001",
                            "actor_id": attacker.entity_id,
                            "target_id": target.entity_id,
                            "weapon_id": "rapier",
                            "final_total": 16,
                            "dice_rolls": {"base_rolls": [11], "modifier": 5},
                            "damage_rolls": [{"source": "weapon:rapier:part_0", "rolls": [6]}],
                            "vantage": "normal",
                            "consume_action": True,
                            "consume_reaction": False,
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
                                        "option_id": "opt_uncanny_001",
                                        "reaction_type": "uncanny_dodge",
                                        "template_type": "defensive_reaction_reduce_damage",
                                        "request_id": "react_uncanny_001",
                                        "label": "Uncanny Dodge",
                                        "status": "pending",
                                    }
                                ],
                            }
                        ],
                        "resolved_group_ids": [],
                    },
                )
            )

            result = self._build_service(encounter_repo, event_repo).execute(
                encounter_id="enc_uncanny_dodge_option_test",
                window_id="rw_attack_declared_uncanny_001",
                group_id=f"rg_{target.entity_id}",
                option_id="opt_uncanny_001",
                final_total=0,
                dice_rolls={},
            )

            updated = encounter_repo.get("enc_uncanny_dodge_option_test")
            assert updated is not None
            updated_target = updated.entities[target.entity_id]
            self.assertEqual(result["reaction_type"], "uncanny_dodge")
            self.assertEqual(result["resolution_mode"], "rewrite_host_action")
            self.assertEqual(result["reaction_result"]["status"], "uncanny_dodge_armed")
            self.assertEqual(result["reaction_result"]["pending_damage_multiplier"], 0.5)
            self.assertEqual(result["host_action_result"]["resolution"]["damage_resolution"]["total_damage"], 4)
            self.assertTrue(updated_target.action_economy["reaction_used"])
            self.assertEqual(updated_target.hp["current"], 11)
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


    def test_execute_resolves_interception_and_reduces_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            attacker = build_attacker()
            target = build_shield_target()
            target.spells = []
            target.resources = {}
            interceptor = build_interceptor()
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_interception_option_test",
                    name="Interception Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=attacker.entity_id,
                    turn_order=[attacker.entity_id, target.entity_id, interceptor.entity_id],
                    entities={attacker.entity_id: attacker, target.entity_id: target, interceptor.entity_id: interceptor},
                    map=EncounterMap(
                        map_id="map_interception_option_test",
                        name="Interception Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_interception_001",
                            "reaction_type": "interception",
                            "template_type": "defensive_reaction_reduce_damage",
                            "trigger_type": "attack_declared",
                            "status": "pending",
                            "actor_entity_id": interceptor.entity_id,
                            "target_entity_id": target.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {},
                        }
                    ],
                    pending_reaction_window={
                        "window_id": "rw_attack_declared_interception_001",
                        "status": "waiting_reaction",
                        "trigger_event_id": "evt_attack_declared_interception_001",
                        "trigger_type": "attack_declared",
                        "blocking": True,
                        "host_action_type": "attack",
                        "host_action_id": "attack_interception_001",
                        "host_action_snapshot": {
                            "attack_id": "attack_interception_001",
                            "actor_id": attacker.entity_id,
                            "target_id": target.entity_id,
                            "weapon_id": "rapier",
                            "final_total": 18,
                            "dice_rolls": {"base_rolls": [13], "modifier": 5},
                            "damage_rolls": [{"source": "weapon:rapier:part_0", "rolls": [6]}],
                            "vantage": "normal",
                            "consume_action": True,
                            "consume_reaction": False,
                        },
                        "choice_groups": [
                            {
                                "group_id": f"rg_{interceptor.entity_id}",
                                "actor_entity_id": interceptor.entity_id,
                                "ask_player": True,
                                "status": "pending",
                                "resource_pool": "reaction",
                                "group_priority": 100,
                                "trigger_sequence": 1,
                                "relationship_rank": 1,
                                "tie_break_key": interceptor.entity_id,
                                "options": [
                                    {
                                        "option_id": "opt_interception_001",
                                        "reaction_type": "interception",
                                        "template_type": "defensive_reaction_reduce_damage",
                                        "request_id": "react_interception_001",
                                        "label": "Interception",
                                        "status": "pending",
                                    }
                                ],
                            }
                        ],
                        "resolved_group_ids": [],
                    },
                )
            )

            result = self._build_service(encounter_repo, event_repo).execute(
                encounter_id="enc_interception_option_test",
                window_id="rw_attack_declared_interception_001",
                group_id=f"rg_{interceptor.entity_id}",
                option_id="opt_interception_001",
                final_total=0,
                dice_rolls={},
                option_payload={"reduction_roll": 5},
            )

            updated = encounter_repo.get("enc_interception_option_test")
            assert updated is not None
            self.assertEqual(result["reaction_type"], "interception")
            self.assertEqual(result["resolution_mode"], "rewrite_host_action")
            self.assertEqual(result["reaction_result"]["damage_reduction_total"], 8)
            self.assertEqual(result["host_action_result"]["resolution"]["damage_resolution"]["total_damage"], 1)
            self.assertTrue(updated.entities[interceptor.entity_id].action_economy["reaction_used"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_resolves_protection_and_replays_attack_with_disadvantage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            attacker = build_attacker()
            target = build_shield_target()
            target.spells = []
            target.resources = {}
            protector = build_protection_fighter()
            encounter_repo.save(
                Encounter(
                    encounter_id="enc_protection_option_test",
                    name="Protection Reaction Option Encounter",
                    status="active",
                    round=1,
                    current_entity_id=attacker.entity_id,
                    turn_order=[attacker.entity_id, target.entity_id, protector.entity_id],
                    entities={attacker.entity_id: attacker, target.entity_id: target, protector.entity_id: protector},
                    map=EncounterMap(
                        map_id="map_protection_option_test",
                        name="Protection Reaction Option Map",
                        description="A small combat room.",
                        width=8,
                        height=8,
                    ),
                    reaction_requests=[
                        {
                            "request_id": "react_protection_001",
                            "reaction_type": "protection",
                            "template_type": "targeted_defense_rewrite",
                            "trigger_type": "attack_declared",
                            "status": "pending",
                            "actor_entity_id": protector.entity_id,
                            "target_entity_id": target.entity_id,
                            "ask_player": True,
                            "auto_resolve": False,
                            "payload": {},
                        }
                    ],
                    pending_reaction_window={
                        "window_id": "rw_attack_declared_protection_001",
                        "status": "waiting_reaction",
                        "trigger_event_id": "evt_attack_declared_protection_001",
                        "trigger_type": "attack_declared",
                        "blocking": True,
                        "host_action_type": "attack",
                        "host_action_id": "attack_protection_001",
                        "host_action_snapshot": {
                            "attack_id": "attack_protection_001",
                            "actor_id": attacker.entity_id,
                            "target_id": target.entity_id,
                            "weapon_id": "rapier",
                            "final_total": 18,
                            "dice_rolls": {"base_rolls": [13], "modifier": 5},
                            "damage_rolls": [{"source": "weapon:rapier:part_0", "rolls": [6]}],
                            "vantage": "normal",
                            "consume_action": True,
                            "consume_reaction": False,
                        },
                        "choice_groups": [
                            {
                                "group_id": f"rg_{protector.entity_id}",
                                "actor_entity_id": protector.entity_id,
                                "ask_player": True,
                                "status": "pending",
                                "resource_pool": "reaction",
                                "group_priority": 100,
                                "trigger_sequence": 1,
                                "relationship_rank": 1,
                                "tie_break_key": protector.entity_id,
                                "options": [
                                    {
                                        "option_id": "opt_protection_001",
                                        "reaction_type": "protection",
                                        "template_type": "targeted_defense_rewrite",
                                        "request_id": "react_protection_001",
                                        "label": "Protection",
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
            with patch("tools.services.combat.attack.execute_attack.random.randint", side_effect=[2, 12, 6]):
                result = service.execute(
                    encounter_id="enc_protection_option_test",
                    window_id="rw_attack_declared_protection_001",
                    group_id=f"rg_{protector.entity_id}",
                    option_id="opt_protection_001",
                    final_total=0,
                    dice_rolls={},
                )

            updated = encounter_repo.get("enc_protection_option_test")
            assert updated is not None
            self.assertEqual(result["reaction_type"], "protection")
            self.assertEqual(result["resolution_mode"], "rewrite_host_action")
            self.assertFalse(result["host_action_result"]["resolution"]["hit"])
            protection_effects = [
                effect
                for effect in updated.entities[target.entity_id].turn_effects
                if effect.get("effect_type") == "protection"
            ]
            self.assertEqual(len(protection_effects), 1)
            self.assertTrue(updated.entities[protector.entity_id].action_economy["reaction_used"])
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
