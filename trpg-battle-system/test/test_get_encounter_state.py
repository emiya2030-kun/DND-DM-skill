"""视图层测试：覆盖 get_encounter_state 的投影结果。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap, Event
from tools.repositories import EncounterRepository, EventRepository
from tools.services import GetEncounterState


def build_player() -> EncounterEntity:
    """构造带武器、法术和资源的当前行动者。"""
    return EncounterEntity(
        entity_id="ent_ally_eric_001",
        entity_def_id="pc_eric_lv5",
        source_ref={
            "character_id": "pc_eric_001",
            "level": 5,
            "description": "A precise ranged spellcaster.",
            "spellcasting_ability": "cha",
            "class_name": "paladin",
        },
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 20, "temp": 3},
        ac=15,
        speed={"walk": 30, "remaining": 20},
        initiative=15,
        ability_mods={"str": 0, "dex": 2, "con": 1, "int": 1, "wis": 0, "cha": 3},
        proficiency_bonus=3,
        conditions=[],
        resources={
            "spell_slots": {
                "1": {"max": 2, "remaining": 1},
                "2": {"max": 2, "remaining": 2},
            },
            "feature_uses": {
                "eldritch_invocation": {"max": 3, "remaining": 2},
            },
        },
        class_features={
            "fighter": {
                "fighter_level": 9,
                "second_wind": {"max_uses": 3, "remaining_uses": 2},
                "action_surge": {"max_uses": 1, "remaining_uses": 1, "used_this_turn": False},
                "indomitable": {"max_uses": 1, "remaining_uses": 1},
                "extra_attack_count": 2,
                "tactical_master_enabled": True,
            }
        },
        weapons=[
            {
                "weapon_id": "rapier",
                "name": "Rapier",
                "attack_bonus": 5,
                "damage": [{"formula": "1d8+3", "type": "piercing"}],
                "properties": ["finesse"],
                "range": {"normal": 5, "long": 5},
                "slot": "right_hand",
            }
        ],
        spells=[
            {
                "spell_id": "eldritch_blast",
                "name": "Eldritch Blast",
                "level": 0,
                "description": "A beam of crackling energy.",
                "damage": [{"formula": "1d10", "type": "force"}],
                "requires_attack_roll": True,
                "range_feet": 120,
                "at_higher_levels": "Creates additional beams.",
            }
        ],
    )


def build_enemy() -> EncounterEntity:
    """构造一个在近战和远程范围内都能被检测到的敌人。"""
    enemy = EncounterEntity(
        entity_id="ent_enemy_goblin_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 3, "y": 2},
        hp={"current": 7, "max": 7, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        conditions=["prone"],
    )
    enemy.conditions = ["paralyzed"]
    enemy.turn_effects = [
        {
            "effect_id": "effect_hold_person_001",
            "name": "Hold Person Ongoing Save",
            "source_entity_id": "ent_ally_eric_001",
            "source_name": "Eric",
            "source_ref": "hold_person",
            "trigger": "end_of_turn",
            "save": {"ability": "wis", "dc": 14, "on_success_remove_effect": True},
            "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
            "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": ["paralyzed"]},
            "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
            "remove_after_trigger": False,
        }
    ]
    return enemy


def build_far_enemy() -> EncounterEntity:
    """构造一个只在远程范围内的敌人。"""
    return EncounterEntity(
        entity_id="ent_enemy_archer_001",
        name="Archer",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 8, "y": 2},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_encounter() -> Encounter:
    """构造视图层测试用 encounter。"""
    player = build_player()
    enemy = build_enemy()
    far_enemy = build_far_enemy()
    return Encounter(
        encounter_id="enc_view_test",
        name="View Test Encounter",
        status="active",
        round=2,
        current_entity_id=player.entity_id,
        turn_order=[player.entity_id, enemy.entity_id, far_enemy.entity_id],
        entities={
            player.entity_id: player,
            enemy.entity_id: enemy,
            far_enemy.entity_id: far_enemy,
        },
        map=EncounterMap(
            map_id="map_view_test",
            name="View Test Map",
            description="A compact stone room.",
            width=10,
            height=10,
            terrain=[
                {
                    "terrain_id": "ter_wall_001",
                    "type": "wall",
                    "x": 1,
                    "y": 1,
                    "blocks_movement": True,
                    "blocks_los": True,
                },
                {
                    "terrain_id": "ter_difficult_001",
                    "type": "difficult_terrain",
                    "x": 2,
                    "y": 1,
                    "costs_extra_movement": True,
                },
                {
                    "terrain_id": "ter_high_ground_001",
                    "type": "high_ground",
                    "x": 2,
                    "y": 2,
                },
            ],
            zones=[
                {
                    "zone_id": "zone_spell_001",
                    "type": "spell_area",
                    "cells": [[3, 2], [3, 3]],
                    "note": "Lingering radiant burst.",
                }
            ],
        ),
        encounter_notes=[{"note_id": "note_001", "note": "The room is dimly lit."}],
        spell_instances=[
            {
                "instance_id": "spell_hold_person_001",
                "spell_id": "hold_person",
                "spell_name": "Hold Person",
                "caster_entity_id": player.entity_id,
                "caster_name": player.name,
                "cast_level": 2,
                "concentration": {"required": True, "active": True},
                "targets": [
                    {
                        "entity_id": enemy.entity_id,
                        "applied_conditions": ["paralyzed"],
                        "turn_effect_ids": ["effect_hold_person_001"],
                    }
                ],
                "lifecycle": {"status": "active", "started_round": 2},
                "special_runtime": {},
            }
        ],
    )


class GetEncounterStateTests(unittest.TestCase):
    def test_execute_projects_armor_breakdown_and_speed_penalty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.ability_scores["str"] = 12
            player.equipped_armor = {"armor_id": "chain_mail"}
            player.equipped_shield = {"armor_id": "shield"}
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            current = state["current_turn_entity"]

            self.assertEqual(current["ac"], 18)
            self.assertEqual(current["ac_breakdown"]["base_armor_ac"], 16)
            self.assertEqual(current["ac_breakdown"]["shield_bonus"], 2)
            self.assertEqual(current["speed_penalty_feet"], 10)
            self.assertEqual(current["effective_speed"], 20)
            repo.close()
            event_repo.close()

    def test_execute_projects_fighter_runtime_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")

            fighter = state["current_turn_entity"]["resources"]["class_features"]["fighter"]
            self.assertEqual(fighter["second_wind"]["remaining_uses"], 2)
            self.assertEqual(fighter["action_surge"]["remaining_uses"], 1)
            self.assertEqual(fighter["indomitable"]["remaining_uses"], 1)
            self.assertEqual(fighter["extra_attack_count"], 2)
            repo.close()
            event_repo.close()

    def test_execute_does_not_project_fighter_weapon_proficiencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")

            fighter = state["current_turn_entity"]["resources"]["class_features"]["fighter"]
            self.assertNotIn("weapon_proficiencies", fighter)
            self.assertNotIn("armor_training", state["current_turn_entity"])
            repo.close()
            event_repo.close()

    def test_execute_projects_martial_class_resource_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features.update(
                {
                    "monk": {
                        "level": 5,
                        "focus_points": {"max": 5, "remaining": 4},
                        "martial_arts_die": "1d8",
                        "unarmored_movement_bonus_feet": 10,
                    },
                    "rogue": {
                        "level": 5,
                        "sneak_attack": {"damage_dice": "3d6", "used_this_turn": False},
                    },
                    "paladin": {"level": 5, "divine_smite": {"enabled": True}},
                    "barbarian": {"level": 4, "rage": {"remaining": 2, "max": 3}},
                    "ranger": {"level": 4},
                }
            )
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            resources = state["current_turn_entity"]["resources"]["class_features"]

            monk = resources["monk"]
            self.assertEqual(monk["focus_points"]["remaining"], 4)
            self.assertEqual(monk["martial_arts_die"], "1d8")
            self.assertIn("stunning_strike", monk["available_features"])

            rogue = resources["rogue"]
            self.assertEqual(rogue["level"], 5)
            self.assertEqual(rogue["sneak_attack"]["damage_dice"], "3d6")
            self.assertIn("sneak_attack", rogue["available_features"])

            paladin = resources["paladin"]
            self.assertEqual(paladin["level"], 5)
            self.assertIn("divine_smite", paladin["available_features"])

            barbarian = resources["barbarian"]
            self.assertEqual(barbarian["rage"]["remaining"], 2)
            self.assertIn("rage", barbarian["available_features"])

            ranger = resources["ranger"]
            self.assertEqual(ranger["level"], 4)
            self.assertIn("weapon_mastery", ranger["available_features"])

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_lay_on_hands_and_aura_summary_from_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 6,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertEqual(paladin["level"], 6)
            self.assertEqual(paladin["lay_on_hands"]["pool_max"], 30)
            self.assertEqual(paladin["lay_on_hands"]["pool_remaining"], 30)
            self.assertTrue(paladin["aura_of_protection"]["enabled"])
            self.assertEqual(paladin["aura_of_protection"]["radius_feet"], 10)
            self.assertIn("aura_of_protection", paladin["available_features"])

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_radiant_strikes_summary_from_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 11,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertTrue(paladin["radiant_strikes"]["enabled"])
            self.assertIn("radiant_strikes", paladin["available_features"])

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_restoring_touch_feature_at_level_fourteen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 14,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertIn("restoring_touch", paladin["available_features"])

            repo.close()
            event_repo.close()

    def test_execute_projects_barbarian_high_level_feature_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["barbarian"] = {
                "level": 18,
                "rage": {"remaining": 1},
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            barbarian = state["current_turn_entity"]["resources"]["class_features"]["barbarian"]

            self.assertEqual(barbarian["level"], 18)
            self.assertEqual(barbarian["rage"]["max"], 6)
            self.assertEqual(barbarian["rage_damage_bonus"], 4)
            self.assertTrue(barbarian["brutal_strike"]["enabled"])
            self.assertTrue(barbarian["relentless_rage"]["enabled"])
            self.assertIn("brutal_strike", barbarian["available_features"])
            self.assertIn("relentless_rage", barbarian["available_features"])
            self.assertIn("persistent_rage", barbarian["available_features"])
            self.assertIn("indomitable_might", barbarian["available_features"])
            repo.close()
            event_repo.close()

    def test_execute_projects_rogue_sneak_attack_growth_from_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["rogue"] = {
                "level": 7,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            rogue = state["current_turn_entity"]["resources"]["class_features"]["rogue"]

            self.assertEqual(rogue["level"], 7)
            self.assertEqual(rogue["sneak_attack"]["damage_dice"], "4d6")
            repo.close()
            event_repo.close()

    def test_execute_projects_rogue_cunning_action_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["rogue"] = {
                "level": 3,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            rogue = state["current_turn_entity"]["resources"]["class_features"]["rogue"]

            self.assertIn("cunning_action", rogue["available_features"])
            self.assertEqual(
                rogue["cunning_action"],
                {"bonus_dash": True, "bonus_disengage": True, "bonus_hide": True},
            )
            repo.close()
            event_repo.close()

    def test_execute_projects_monk_bonus_action_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["monk"] = {
                "level": 5,
                "focus_points": {"max": 5, "remaining": 4},
                "martial_arts_die": "1d8",
                "unarmored_movement_bonus_feet": 10,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            monk = state["current_turn_entity"]["resources"]["class_features"]["monk"]

            self.assertIn("patient_defense", monk["available_features"])
            self.assertIn("step_of_the_wind", monk["available_features"])
            repo.close()
            event_repo.close()

    def test_execute_projects_monk_progression_from_level_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["monk"] = {
                "level": 11,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            monk = state["current_turn_entity"]["resources"]["class_features"]["monk"]

            self.assertEqual(monk["martial_arts_die"], "1d10")
            self.assertEqual(monk["focus_points"]["max"], 11)
            self.assertEqual(monk["focus_points"]["remaining"], 11)
            self.assertEqual(monk["unarmored_movement_bonus_feet"], 20)
            repo.close()
            event_repo.close()

    def test_execute_projects_fighter_tactical_mind_and_style(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["fighter"]["tactical_mind"] = {"enabled": True}
            player.class_features["fighter"]["fighting_style"] = {"style_id": "archery"}
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            fighter = state["current_turn_entity"]["resources"]["class_features"]["fighter"]

            self.assertTrue(fighter["tactical_mind"]["enabled"])
            self.assertEqual(fighter["fighting_style"]["style_id"], "archery")
            repo.close()
            event_repo.close()

    def test_execute_projects_blind_fighting_blindsight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["fighter"]["fighting_style"] = {"style_id": "blind_fighting"}
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            fighter = state["current_turn_entity"]["resources"]["class_features"]["fighter"]

            self.assertEqual(fighter["blindsight_feet"], 10)
            repo.close()
            event_repo.close()

    def test_execute_projects_recent_activity_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())
            event_repo.append(
                Event(
                    event_id="evt_move_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="movement_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    payload={
                        "from_position": {"x": 2, "y": 2},
                        "to_position": {"x": 4, "y": 2},
                        "feet_cost": 10,
                        "used_dash": False,
                    },
                )
            )
            event_repo.append(
                Event(
                    event_id="evt_attack_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="attack_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "attack_name": "刺剑",
                        "attack_kind": "weapon_attack",
                        "final_total": 18,
                        "target_ac": 13,
                        "hit": True,
                        "is_critical_hit": False,
                    },
                )
            )
            event_repo.append(
                Event(
                    event_id="evt_damage_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="damage_applied",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "target_id": "ent_enemy_goblin_001",
                        "hp_change": 7,
                        "reason": "刺剑",
                        "source_entity_id": "ent_ally_eric_001",
                    },
                )
            )

            state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")

            self.assertIn("recent_activity", state)
            self.assertGreaterEqual(len(state["recent_activity"]), 3)
            self.assertEqual(state["recent_activity"][0]["event_type"], "damage_applied")
            self.assertEqual(state["recent_activity"][1]["event_type"], "attack_resolved")
            self.assertEqual(state["recent_activity"][2]["event_type"], "movement_resolved")
            self.assertIn("Eric", state["recent_activity"][0]["summary"])
            self.assertIn("Goblin", state["recent_activity"][0]["summary"])
            self.assertIn("刺剑", state["recent_activity"][1]["summary"])
            self.assertIn("(2,2)", state["recent_activity"][2]["summary"])
            repo.close()
            event_repo.close()

    def test_execute_limits_recent_activity_to_latest_six_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())
            for index in range(8):
                event_repo.append(
                    Event(
                        event_id=f"evt_turn_end_{index}",
                        encounter_id="enc_view_test",
                        round=2,
                        event_type="turn_ended",
                        actor_entity_id="ent_ally_eric_001",
                        payload={},
                    )
                )

            state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")

            self.assertEqual(len(state["recent_activity"]), 6)
            self.assertEqual(state["recent_activity"][0]["event_id"], "evt_turn_end_7")
            self.assertEqual(state["recent_activity"][-1]["event_id"], "evt_turn_end_2")
            repo.close()
            event_repo.close()

    def test_execute_projects_zone_effect_activity_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())
            event_repo.append(
                Event(
                    event_id="evt_zone_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="zone_effect_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "zone_id": "zone_fire_001",
                        "zone_name": "火焰灼域",
                        "trigger": "end_of_turn_inside",
                        "source_entity_id": "zone_source_fire",
                        "source_name": "火焰灼域",
                        "target_entity_id": "ent_enemy_goblin_001",
                        "damage_resolution": {
                            "total_damage": 6,
                            "applied_parts": [{"type": "fire", "final_damage": 6}],
                        },
                        "condition_updates": [],
                    },
                )
            )

            state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")

            self.assertEqual(state["recent_activity"][0]["event_type"], "zone_effect_resolved")
            self.assertIn("火焰灼域", state["recent_activity"][0]["summary"])
            self.assertIn("Goblin", state["recent_activity"][0]["summary"])
            self.assertIn("6 点", state["recent_activity"][0]["summary"])
            repo.close()
            event_repo.close()

    def test_execute_projects_recent_turn_effect_resolved_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())
            event_repo.append(
                Event(
                    event_id="evt_turn_effect_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="turn_effect_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "effect_id": "effect_hold_person_001",
                        "name": "定身术持续效果",
                        "trigger": "end_of_turn",
                        "target_entity_id": "ent_enemy_goblin_001",
                        "source_entity_id": "ent_ally_eric_001",
                        "save": {
                            "ability": "wis",
                            "dc": 14,
                            "base_roll": 5,
                            "bonus": 1,
                            "total": 6,
                            "success": False,
                        },
                        "trigger_damage_resolution": None,
                        "success_damage_resolution": None,
                        "failure_damage_resolution": None,
                        "condition_updates": [],
                        "effect_removed": False,
                    },
                )
            )

            state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")

            self.assertIn("recent_turn_effects", state)
            self.assertEqual(len(state["recent_turn_effects"]), 1)
            self.assertEqual(state["recent_turn_effects"][0]["effect_id"], "effect_hold_person_001")
            self.assertEqual(state["recent_turn_effects"][0]["source_name"], "Eric")
            self.assertEqual(state["recent_turn_effects"][0]["target_name"], "Goblin")
            self.assertEqual(state["recent_turn_effects"][0]["trigger"], "end_of_turn")
            self.assertIn("定身术持续效果", state["recent_turn_effects"][0]["summary"])
            repo.close()
            event_repo.close()

    def test_execute_hides_turn_effect_summary_when_newer_non_turn_effect_event_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())
            event_repo.append(
                Event(
                    event_id="evt_turn_effect_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="turn_effect_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "effect_id": "effect_hold_person_001",
                        "name": "定身术持续效果",
                        "trigger": "end_of_turn",
                    },
                )
            )
            event_repo.append(
                Event(
                    event_id="evt_damage_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="damage_applied",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={"reason": "Rapier damage"},
                )
            )

            state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")

            self.assertEqual(state["recent_turn_effects"], [])
            repo.close()
            event_repo.close()

    def test_execute_exposes_retargetable_mark_spells_as_structured_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.spell_instances.append(
                {
                    "instance_id": "spell_hex_001",
                    "spell_id": "hex",
                    "spell_name": "Hex",
                    "caster_entity_id": "ent_ally_eric_001",
                    "caster_name": "Eric",
                    "cast_level": 1,
                    "concentration": {"required": True, "active": True},
                    "targets": [
                        {
                            "entity_id": "ent_enemy_goblin_001",
                            "applied_conditions": [],
                            "turn_effect_ids": [],
                        }
                    ],
                    "lifecycle": {"status": "active", "started_round": 2},
                    "special_runtime": {
                        "retargetable": True,
                        "retarget_available": True,
                        "current_target_id": None,
                        "retarget_activation": "bonus_action",
                    },
                }
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertIn("retargetable_spell_actions", state)
            self.assertEqual(len(state["retargetable_spell_actions"]), 1)
            self.assertEqual(
                state["retargetable_spell_actions"][0],
                {
                    "spell_instance_id": "spell_hex_001",
                    "spell_id": "hex",
                    "spell_name": "Hex",
                    "caster_entity_id": "ent_ally_eric_001",
                    "caster_name": "Eric",
                    "previous_target_id": "ent_enemy_goblin_001",
                    "previous_target_name": "Goblin",
                    "activation": "bonus_action",
                },
            )
            repo.close()

    def test_execute_hides_non_available_or_non_current_entity_retarget_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.spell_instances.extend(
                [
                    {
                        "instance_id": "spell_hex_001",
                        "spell_id": "hex",
                        "spell_name": "Hex",
                        "caster_entity_id": "ent_ally_eric_001",
                        "caster_name": "Eric",
                        "cast_level": 1,
                        "concentration": {"required": True, "active": True},
                        "targets": [{"entity_id": "ent_enemy_goblin_001", "applied_conditions": [], "turn_effect_ids": []}],
                        "lifecycle": {"status": "active", "started_round": 2},
                        "special_runtime": {
                            "retargetable": True,
                            "retarget_available": False,
                            "current_target_id": "ent_enemy_goblin_001",
                            "retarget_activation": "bonus_action",
                        },
                    },
                    {
                        "instance_id": "spell_hm_001",
                        "spell_id": "hunters_mark",
                        "spell_name": "Hunter's Mark",
                        "caster_entity_id": "ent_enemy_goblin_001",
                        "caster_name": "Goblin",
                        "cast_level": 1,
                        "concentration": {"required": True, "active": True},
                        "targets": [{"entity_id": "ent_ally_eric_001", "applied_conditions": [], "turn_effect_ids": []}],
                        "lifecycle": {"status": "active", "started_round": 2},
                        "special_runtime": {
                            "retargetable": True,
                            "retarget_available": True,
                            "current_target_id": None,
                            "retarget_activation": "bonus_action",
                        },
                    },
                ]
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertEqual(state["retargetable_spell_actions"], [])
            repo.close()

    def test_execute_projects_recent_forced_movement_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())
            event_repo.append(
                Event(
                    event_id="evt_forced_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="forced_movement_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "reason": "weapon_mastery_push",
                        "source_entity_id": "ent_ally_eric_001",
                        "from_position": {"x": 3, "y": 2},
                        "to_position": {"x": 5, "y": 2},
                        "attempted_path": [{"x": 4, "y": 2}, {"x": 5, "y": 2}],
                        "resolved_path": [{"x": 4, "y": 2}, {"x": 5, "y": 2}],
                        "moved_feet": 10,
                        "blocked": False,
                        "block_reason": None,
                    },
                )
            )

            state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")
            forced = state["recent_forced_movement"]

            self.assertEqual(forced["moved_feet"], 10)
            self.assertEqual(forced["target_name"], "Goblin")
            self.assertEqual(forced["final_position"], {"x": 5, "y": 2})
            self.assertEqual(forced["summary"], "Goblin被 Push 推离 10 尺，移动到 (5,2)。")
            repo.close()
            event_repo.close()

    def test_execute_uses_latest_forced_movement_event_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())
            event_repo.append(
                Event(
                    event_id="evt_forced_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="forced_movement_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "reason": "weapon_mastery_push",
                        "source_entity_id": "ent_ally_eric_001",
                        "from_position": {"x": 3, "y": 2},
                        "to_position": {"x": 4, "y": 2},
                        "attempted_path": [{"x": 4, "y": 2}],
                        "resolved_path": [{"x": 4, "y": 2}],
                        "moved_feet": 5,
                        "blocked": True,
                        "block_reason": "wall",
                    },
                )
            )
            event_repo.append(
                Event(
                    event_id="evt_forced_002",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="forced_movement_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "reason": "weapon_mastery_push",
                        "source_entity_id": "ent_ally_eric_001",
                        "from_position": {"x": 3, "y": 2},
                        "to_position": {"x": 6, "y": 2},
                        "attempted_path": [{"x": 4, "y": 2}, {"x": 5, "y": 2}, {"x": 6, "y": 2}],
                        "resolved_path": [{"x": 4, "y": 2}, {"x": 5, "y": 2}, {"x": 6, "y": 2}],
                        "moved_feet": 15,
                        "blocked": False,
                        "block_reason": None,
                    },
                )
            )

            state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")
            forced = state["recent_forced_movement"]

            self.assertEqual(forced["final_position"], {"x": 6, "y": 2})
            self.assertEqual(forced["moved_feet"], 15)
            self.assertEqual(forced["summary"], "Goblin被 Push 推离 15 尺，移动到 (6,2)。")
            repo.close()
            event_repo.close()

    def test_execute_clears_forced_movement_after_new_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())
            event_repo.append(
                Event(
                    event_id="evt_forced_003",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="forced_movement_resolved",
                    actor_entity_id="ent_ally_eric_001",
                    target_entity_id="ent_enemy_goblin_001",
                    payload={
                        "reason": "weapon_mastery_push",
                        "source_entity_id": "ent_ally_eric_001",
                        "from_position": {"x": 3, "y": 2},
                        "to_position": {"x": 5, "y": 2},
                        "attempted_path": [{"x": 4, "y": 2}, {"x": 5, "y": 2}],
                        "resolved_path": [{"x": 4, "y": 2}, {"x": 5, "y": 2}],
                        "moved_feet": 10,
                        "blocked": False,
                        "block_reason": None,
                    },
                )
            )
            event_repo.append(
                Event(
                    event_id="evt_turn_advance_001",
                    encounter_id="enc_view_test",
                    round=2,
                    event_type="turn_advanced",
                    actor_entity_id="ent_ally_eric_001",
                )
            )

            state = GetEncounterState(repo, event_repository=event_repo).execute("enc_view_test")

            self.assertIsNone(state["recent_forced_movement"])
            repo.close()
            event_repo.close()

    def test_execute_returns_current_turn_projection(self) -> None:
        """测试 execute 会生成 current_turn_entity 的核心展示字段。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")
            current = state["current_turn_entity"]

            self.assertEqual(state["encounter_name"], "View Test Encounter")
            self.assertEqual(state["round"], 2)
            self.assertEqual(current["id"], "ent_ally_eric_001")
            self.assertEqual(current["hp"], "18 / 20 HP")
            self.assertEqual(current["movement_remaining"], "20 feet")
            self.assertEqual(current["spell_save_dc"], 14)
            repo.close()

    def test_execute_exposes_current_turn_death_saves(self) -> None:
        """当前回合实体的 death_saves 应投影为简短摘要。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].combat_flags = {
                "death_saves": {"successes": 2, "failures": 1}
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            current = state["current_turn_entity"]

            self.assertEqual(current["death_saves"], "2 成功 / 1 失败")
            repo.close()

    def test_execute_groups_actions_and_resources(self) -> None:
        """测试武器、法术和法术位会被整理到 available_actions 中。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")
            actions = state["current_turn_entity"]["available_actions"]

            self.assertEqual(actions["weapons"][0]["name"], "Rapier")
            self.assertIn("cantrips", actions["spells"])
            self.assertEqual(actions["spell_slots_available"]["1"], 1)
            repo.close()

    def test_execute_projects_pending_reaction_requests_and_pending_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.reaction_requests = [
                {
                    "request_id": "react_001",
                    "reaction_type": "opportunity_attack",
                    "trigger_type": "leave_melee_reach",
                    "status": "pending",
                    "actor_entity_id": "ent_ally_eric_001",
                    "actor_name": "Eric",
                    "target_entity_id": "ent_enemy_goblin_001",
                    "target_name": "Goblin",
                    "ask_player": True,
                    "auto_resolve": False,
                    "source_event_type": "movement_trigger_check",
                    "source_event_id": None,
                    "payload": {
                        "weapon_id": "rapier",
                        "weapon_name": "Rapier",
                        "trigger_position": {"x": 2, "y": 2},
                        "reason": "目标离开了你的近战触及",
                    },
                }
            ]
            encounter.pending_movement = {
                "movement_id": "move_001",
                "entity_id": "ent_enemy_goblin_001",
                "start_position": {"x": 3, "y": 2},
                "target_position": {"x": 6, "y": 2},
                "current_position": {"x": 3, "y": 2},
                "remaining_path": [{"x": 4, "y": 2}, {"x": 5, "y": 2}, {"x": 6, "y": 2}],
                "count_movement": True,
                "use_dash": False,
                "status": "waiting_reaction",
                "waiting_request_id": "react_001",
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertEqual(state["reaction_requests"][0]["request_id"], "react_001")
            self.assertTrue(state["reaction_requests"][0]["ask_player"])
            self.assertEqual(state["pending_movement"]["status"], "waiting_reaction")
            self.assertEqual(state["pending_movement"]["waiting_request_id"], "react_001")
            repo.close()

    def test_execute_includes_pending_reaction_window_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.reaction_requests = [
                {
                    "request_id": "react_001",
                    "reaction_type": "shield",
                    "template_type": "targeted_defense_rewrite",
                    "trigger_type": "attack_declared",
                    "status": "pending",
                    "actor_entity_id": "ent_ally_eric_001",
                    "target_entity_id": "ent_enemy_goblin_001",
                    "ask_player": True,
                    "auto_resolve": False,
                    "payload": {},
                }
            ]
            encounter.pending_reaction_window = {
                "window_id": "rw_001",
                "status": "waiting_reaction",
                "trigger_event_id": "evt_attack_declared_001",
                "trigger_type": "attack_declared",
                "blocking": True,
                "host_action_type": "attack",
                "host_action_id": "atk_001",
                "host_action_snapshot": {"phase": "before_hit_locked"},
                "choice_groups": [
                    {
                        "group_id": "rg_001",
                        "actor_entity_id": "ent_ally_eric_001",
                        "status": "pending",
                        "options": [
                            {
                                "option_id": "opt_001",
                                "reaction_type": "shield",
                                "template_type": "targeted_defense_rewrite",
                                "request_id": "react_001",
                                "label": "Shield",
                                "status": "pending",
                            }
                        ],
                    }
                ],
                "resolved_group_ids": [],
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            window = state["pending_reaction_window"]

            self.assertEqual(window["window_id"], "rw_001")
            self.assertEqual(window["status"], "waiting_reaction")
            self.assertEqual(window["choice_groups"][0]["options"][0]["reaction_type"], "shield")
            repo.close()

    def test_execute_builds_weapon_ranges(self) -> None:
        """测试近战和远程可选目标会按距离投影出来。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")
            weapon_ranges = state["current_turn_entity"]["weapon_ranges"]

            self.assertEqual(weapon_ranges["max_melee_range"], "5 ft")
            self.assertEqual(weapon_ranges["max_ranged_range"], "120 ft")
            self.assertEqual(weapon_ranges["targets_within_melee_range"][0]["name"], "Goblin")
            self.assertEqual(len(weapon_ranges["targets_within_ranged_range"]), 2)
            repo.close()

    def test_execute_builds_turn_order_and_battlemap_details(self) -> None:
        """测试 turn_order 和 battlemap_details 会按视图结构输出。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertEqual(state["turn_order"][1]["distance_from_current_turn_entity"], "5 ft")
            self.assertEqual(state["battlemap_details"]["dimensions"], "10 x 10 tiles")
            self.assertEqual(state["battlemap_details"]["grid_size"], "Each tile represents 5 feet")
            repo.close()

    def test_execute_handles_empty_actions_and_conditions(self) -> None:
        """测试缺少武器法术时仍返回空结构，且条件文本可读。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].weapons = []
            encounter.entities["ent_ally_eric_001"].spells = []
            encounter.entities["ent_ally_eric_001"].conditions = ["blinded"]
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            current = state["current_turn_entity"]

            self.assertEqual(current["available_actions"]["weapons"], [])
            self.assertEqual(current["available_actions"]["spells"]["cantrips"], [])
            self.assertEqual(current["conditions"], "blinded")
            repo.close()

    def test_execute_includes_battlemap_view_and_map_notes(self) -> None:
        """测试状态投影会附带玩家地图视图和 LLM map_notes。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertIn("battlemap_view", state)
            self.assertIn("map_notes", state)
            self.assertIn("html", state["battlemap_view"])
            self.assertIn("terrain_summary", state["map_notes"])
            self.assertEqual(state["map_notes"]["terrain_summary"][0]["type"], "wall")
            repo.close()

    def test_execute_projects_spell_area_overlay_into_battlemap_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.encounter_notes.append(
                {
                    "type": "spell_area_overlay",
                    "payload": {
                        "overlay_id": "overlay_fireball_001",
                        "kind": "spell_area_circle",
                        "source_spell_id": "fireball",
                        "source_spell_name": "火球术",
                        "target_point": {"x": 3, "y": 3, "anchor": "cell_center"},
                        "radius_feet": 20,
                        "radius_tiles": 4,
                        "persistence": "instant",
                    },
                }
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertEqual(len(state["spell_area_overlays"]), 1)
            self.assertIn("battlemap-spell-overlay", state["battlemap_view"]["html"])
            self.assertIn("火球术", state["battlemap_view"]["html"])
            repo.close()

    def test_execute_exposes_action_economy_actions(self) -> None:
        """current_turn_entity.actions 应包含 action_economy 的对称字段和明确状态."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            default_actions = state["current_turn_entity"]["actions"]

            self.assertEqual(
                default_actions,
                {
                    "action_used": False,
                    "bonus_action_used": False,
                    "reaction_used": False,
                    "free_interaction_used": False,
                },
            )

            encounter.entities["ent_ally_eric_001"].action_economy = {
                "action_used": True,
                "bonus_action_used": False,
                "reaction_used": True,
                "free_interaction_used": False,
            }
            repo.save(encounter)

            refreshed_state = GetEncounterState(repo).execute("enc_view_test")
            refreshed_actions = refreshed_state["current_turn_entity"]["actions"]

            self.assertTrue(refreshed_actions["action_used"])
            self.assertEqual(refreshed_actions["bonus_action_used"], False)
            self.assertTrue(refreshed_actions["reaction_used"])
            self.assertEqual(refreshed_actions["free_interaction_used"], False)
            repo.close()

    def test_execute_projects_spell_effect_summaries_without_exposing_raw_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertNotIn("spell_instances", state)
            self.assertIn("Hold Person", state["active_spell_summaries"][0])
            goblin = state["turn_order"][1]
            self.assertIn("ongoing_effects", goblin)
            self.assertIn("来自Eric的Hold Person", goblin["ongoing_effects"])
            self.assertEqual(
                goblin["conditions"],
                ["paralyzed", "来自Eric的Hold Person"],
            )
            repo.close()

    def test_execute_projects_turn_action_effects_into_ongoing_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            goblin = encounter.entities["ent_enemy_goblin_001"]
            player.turn_effects = [
                {"effect_id": "effect_disengage_001", "effect_type": "disengage", "name": "Disengage"},
            ]
            goblin.turn_effects.append(
                {"effect_id": "effect_dodge_001", "effect_type": "dodge", "name": "Dodge"}
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertIn("Disengage", state["current_turn_entity"]["ongoing_effects"])
            self.assertIn("Dodge", state["turn_order"][1]["ongoing_effects"])
            repo.close()

    def test_execute_projects_help_effect_labels_into_ongoing_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            goblin = encounter.entities["ent_enemy_goblin_001"]
            archer = encounter.entities["ent_enemy_archer_001"]
            goblin.turn_effects.append(
                {
                    "effect_id": "help_attack_1",
                    "effect_type": "help_attack",
                    "source_entity_id": player.entity_id,
                    "source_name": player.name,
                }
            )
            archer.side = "ally"
            archer.turn_effects.append(
                {
                    "effect_id": "help_check_1",
                    "effect_type": "help_ability_check",
                    "source_entity_id": player.entity_id,
                    "source_name": player.name,
                    "help_check": {"check_type": "skill", "check_key": "investigation"},
                }
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertIn("受到Eric的 Help（攻击）", state["turn_order"][1]["ongoing_effects"])
            self.assertIn("受到Eric的 Help（investigation）", state["turn_order"][2]["ongoing_effects"])
            repo.close()

    def test_execute_projects_grapple_status_for_target_and_grappler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            goblin = encounter.entities["ent_enemy_goblin_001"]
            player.combat_flags["active_grapple"] = {
                "target_entity_id": goblin.entity_id,
                "escape_dc": 13,
                "source_condition": f"grappled:{player.entity_id}",
            }
            goblin.conditions.append(f"grappled:{player.entity_id}")
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")

            self.assertIn("正在擒抱 Goblin", state["current_turn_entity"]["ongoing_effects"])
            conditions = state["turn_order"][1]["conditions"]
            if isinstance(conditions, str):
                self.assertIn(f"grappled:{player.entity_id}", conditions)
            else:
                self.assertIn(f"grappled:{player.entity_id}", conditions)
            repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
