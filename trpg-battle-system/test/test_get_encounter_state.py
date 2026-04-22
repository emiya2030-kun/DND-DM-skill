"""视图层测试：覆盖 get_encounter_state 的投影结果。"""

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap, Event
from tools.repositories import EncounterRepository, EventRepository
from tools.services import GetEncounterState


def build_player() -> EncounterEntity:
    """构造带武器、法术和资源的当前行动者。"""
    entity = EncounterEntity(
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
    entity.equipped_armor = {"armor_id": "leather_armor"}
    entity.equipped_shield = {"armor_id": "shield"}
    entity.inventory = [
        {"name": "链条", "quantity": 1},
        {"name": "火绒盒", "quantity": 1},
        {"name": "口粮", "quantity": 5},
    ]
    entity.currency = {"gp": 127}
    return entity


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


def build_test_weapon(
    *,
    weapon_id: str,
    name: str,
    damage_formula: str,
    damage_type: str,
    normal_range: int,
    long_range: int,
    kind: str,
    attack_bonus: int = 4,
    category: Optional[str] = None,
) -> dict[str, object]:
    weapon = {
        "weapon_id": weapon_id,
        "name": name,
        "attack_bonus": attack_bonus,
        "damage": [{"formula": damage_formula, "type": damage_type}],
        "range": {"normal": normal_range, "long": long_range},
        "kind": kind,
    }
    if category is not None:
        weapon["category"] = category
    return weapon


def set_current_turn(encounter: Encounter, entity_id: str) -> None:
    encounter.current_entity_id = entity_id
    encounter.turn_order = [entity_id, *[existing for existing in encounter.turn_order if existing != entity_id]]


def execute_get_encounter_state(encounter: Encounter) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        try:
            repo.save(encounter)
            return GetEncounterState(repo).execute(encounter.encounter_id)
        finally:
            repo.close()


def build_enemy_tactical_brief_actor_encounter(
    *,
    current_actor: str,
    enemy_weapon: dict[str, object],
    enemy_position: Optional[dict[str, int]] = None,
    enemy_source_ref: Optional[dict[str, object]] = None,
) -> Encounter:
    player = EncounterEntity(
        entity_id="ent_ally_player_001",
        name="Player",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 6, "y": 5},
        hp={"current": 18, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
    )
    melee_enemy = EncounterEntity(
        entity_id="ent_enemy_brute_001",
        name="Brute",
        side="enemy",
        category="monster",
        controller="gm",
        position=enemy_position or {"x": 5, "y": 5},
        hp={"current": 30, "max": 30, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        weapons=[enemy_weapon],
        source_ref=enemy_source_ref or {},
    )
    return Encounter(
        encounter_id="enc_enemy_brief_actor",
        name="Enemy Brief Actor",
        status="active",
        round=1,
        current_entity_id=current_actor,
        turn_order=[current_actor, *[
            entity_id
            for entity_id in [player.entity_id, melee_enemy.entity_id]
            if entity_id != current_actor
        ]],
        entities={
            player.entity_id: player,
            melee_enemy.entity_id: melee_enemy,
        },
        map=EncounterMap(
            map_id="map_enemy_brief_actor",
            name="Actor Map",
            description="actor test",
            width=12,
            height=12,
        ),
    )


def build_enemy_turn_encounter_with_weapon(
    weapon: dict[str, object],
    *,
    position: Optional[dict[str, int]] = None,
    source_ref: Optional[dict[str, object]] = None,
) -> Encounter:
    return build_enemy_tactical_brief_actor_encounter(
        current_actor="ent_enemy_brute_001",
        enemy_weapon=weapon,
        enemy_position=position,
        enemy_source_ref=source_ref,
    )


def build_enemy_hybrid_brief_encounter(
    *,
    enemy_position: dict[str, int],
    player_position: dict[str, int],
    player_ac: int,
    melee_attack_bonus: int = 4,
    ranged_attack_bonus: int = 4,
    save_action_range_feet: int = 30,
) -> Encounter:
    enemy = EncounterEntity(
        entity_id="ent_enemy_hybrid_001",
        name="Wight",
        side="enemy",
        category="monster",
        controller="gm",
        position=enemy_position,
        hp={"current": 45, "max": 45, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        weapons=[
            build_test_weapon(
                weapon_id="necrotic_sword",
                name="Necrotic Sword",
                damage_formula="1d8+2",
                damage_type="slashing",
                normal_range=5,
                long_range=5,
                kind="melee",
                attack_bonus=melee_attack_bonus,
            ),
            build_test_weapon(
                weapon_id="necrotic_bow",
                name="Necrotic Bow",
                damage_formula="1d8+2",
                damage_type="piercing",
                normal_range=150,
                long_range=600,
                kind="ranged",
                attack_bonus=ranged_attack_bonus,
            ),
        ],
        source_ref={
            "actions_metadata": [
                {
                    "action_id": "multiattack",
                    "name_zh": "多重攻击",
                    "name_en": "Multiattack",
                    "summary": "用死灵剑或死灵弓攻击两次；其中一次可替换为吸取生命。",
                    "multiattack_sequences": [
                        {
                            "sequence_id": "double_sword",
                            "mode": "melee",
                            "steps": [
                                {"type": "weapon", "weapon_id": "necrotic_sword"},
                                {"type": "weapon", "weapon_id": "necrotic_sword"},
                            ],
                        },
                        {
                            "sequence_id": "double_bow",
                            "mode": "ranged",
                            "steps": [
                                {"type": "weapon", "weapon_id": "necrotic_bow"},
                                {"type": "weapon", "weapon_id": "necrotic_bow"},
                            ],
                        },
                        {
                            "sequence_id": "life_drain_plus_sword",
                            "mode": "melee",
                            "tags": ["prefer_high_ac"],
                            "steps": [
                                {"type": "special_action", "action_id": "life_drain"},
                                {"type": "weapon", "weapon_id": "necrotic_sword"},
                            ],
                        },
                    ],
                },
                {
                    "action_id": "life_drain",
                    "name_zh": "吸取生命",
                    "name_en": "Life Drain",
                    "summary": "体质豁免型特殊动作。",
                    "range_feet": save_action_range_feet,
                    "save_ability": "con",
                }
            ]
        },
    )
    player = EncounterEntity(
        entity_id="ent_ally_player_001",
        name="Player",
        side="ally",
        category="pc",
        controller="player",
        position=player_position,
        hp={"current": 20, "max": 20, "temp": 0},
        ac=player_ac,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )
    return Encounter(
        encounter_id="enc_enemy_hybrid_brief",
        name="Enemy Hybrid Brief",
        status="active",
        round=1,
        current_entity_id=enemy.entity_id,
        turn_order=[enemy.entity_id, player.entity_id],
        entities={
            enemy.entity_id: enemy,
            player.entity_id: player,
        },
        map=EncounterMap(
            map_id="map_enemy_hybrid_brief",
            name="Hybrid Brief Map",
            description="hybrid brief test",
            width=20,
            height=20,
        ),
    )


def build_enemy_tactical_brief_ranking_encounter() -> Encounter:
    enemy = EncounterEntity(
        entity_id="ent_enemy_brute_001",
        name="Brute",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 5, "y": 5},
        hp={"current": 40, "max": 40, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        weapons=[
            build_test_weapon(
                weapon_id="mace",
                name="Mace",
                damage_formula="1d6+3",
                damage_type="bludgeoning",
                normal_range=5,
                long_range=5,
                kind="melee",
                attack_bonus=5,
            )
        ],
    )
    low_ac = EncounterEntity(
        entity_id="ent_ally_low_ac_001",
        name="Low AC",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 6, "y": 5},
        hp={"current": 16, "max": 20, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
    )
    concentrating = EncounterEntity(
        entity_id="ent_ally_concentration_001",
        name="Concentration",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 5, "y": 6},
        hp={"current": 22, "max": 22, "temp": 0},
        ac=18,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        turn_effects=[
            {
                "effect_id": "fx_conc",
                "effect_type": "concentration",
                "name": "Hex",
            }
        ],
    )
    summon = EncounterEntity(
        entity_id="ent_ally_summon_001",
        name="Summon",
        side="ally",
        category="summon",
        controller="player",
        position={"x": 4, "y": 5},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=13,
    )
    far_target = EncounterEntity(
        entity_id="ent_ally_far_001",
        name="Far",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 10, "y": 5},
        hp={"current": 8, "max": 8, "temp": 0},
        ac=10,
        speed={"walk": 30, "remaining": 30},
        initiative=11,
    )
    return Encounter(
        encounter_id="enc_enemy_brief_rank",
        name="Enemy Brief Rank",
        status="active",
        round=1,
        current_entity_id=enemy.entity_id,
        turn_order=[
            enemy.entity_id,
            low_ac.entity_id,
            concentrating.entity_id,
            summon.entity_id,
            far_target.entity_id,
        ],
        entities={
            enemy.entity_id: enemy,
            low_ac.entity_id: low_ac,
            concentrating.entity_id: concentrating,
            summon.entity_id: summon,
            far_target.entity_id: far_target,
        },
        map=EncounterMap(
            map_id="map_enemy_brief_rank",
            name="Rank Map",
            description="rank test",
            width=12,
            height=12,
        ),
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
            self.assertTrue(monk["uncanny_metabolism"]["available"])
            self.assertTrue(monk["slow_fall"]["enabled"])
            self.assertTrue(monk["flurry_of_blows"]["enabled"])
            self.assertEqual(monk["flurry_of_blows"]["base_attack_count"], 2)
            self.assertNotIn("available_features", monk)
            self.assertIn("震慑拳", monk["available_features_zh"])
            self.assertIn("坚强防御", monk["available_features_zh"])

            rogue = resources["rogue"]
            self.assertEqual(rogue["level"], 5)
            self.assertEqual(rogue["sneak_attack"]["damage_dice"], "3d6")
            self.assertNotIn("available_features", rogue)
            self.assertIn("巧诈动作", rogue["available_features_zh"])

            paladin = resources["paladin"]
            self.assertEqual(paladin["level"], 5)
            self.assertNotIn("available_features", paladin)
            self.assertIn("施法", paladin["available_features_zh"])

            barbarian = resources["barbarian"]
            self.assertEqual(barbarian["rage"]["remaining"], 2)
            self.assertNotIn("available_features", barbarian)
            self.assertIn("狂暴", barbarian["available_features_zh"])

            ranger = resources["ranger"]
            self.assertEqual(ranger["level"], 4)
            self.assertNotIn("available_features", ranger)
            self.assertIn("战斗风格", ranger["available_features_zh"])

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
            self.assertIn("守护灵光", paladin["available_features_zh"])

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
            self.assertIn("辉耀打击", paladin["available_features_zh"])

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

            self.assertIn("疗愈之触", paladin["available_features_zh"])

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_channel_divinity_defaults_at_level_three(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 3,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertTrue(paladin["channel_divinity"]["enabled"])
            self.assertEqual(paladin["channel_divinity"]["max_uses"], 2)
            self.assertEqual(paladin["channel_divinity"]["remaining_uses"], 2)
            self.assertIn("引导神力", paladin["available_features_zh"])

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_channel_divinity_defaults_at_level_eleven(self) -> None:
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

            self.assertEqual(paladin["channel_divinity"]["max_uses"], 3)
            self.assertEqual(paladin["channel_divinity"]["remaining_uses"], 3)

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_channel_divinity_preserves_explicit_remaining_uses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 9,
                "channel_divinity": {"remaining_uses": 1},
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertEqual(paladin["channel_divinity"]["max_uses"], 2)
            self.assertEqual(paladin["channel_divinity"]["remaining_uses"], 1)

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_aura_of_courage_summary_from_level_ten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 10,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertTrue(paladin["aura_of_courage"]["enabled"])
            self.assertEqual(paladin["aura_of_courage"]["radius_feet"], 10)
            self.assertIn("勇气灵光", paladin["available_features_zh"])

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_aura_expansion_at_level_eighteen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 18,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertEqual(paladin["aura_of_protection"]["radius_feet"], 30)
            self.assertEqual(paladin["aura_of_courage"]["radius_feet"], 30)

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_faithful_steed_summary_at_level_five(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 5,
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertTrue(paladin["faithful_steed"]["enabled"])
            self.assertTrue(paladin["faithful_steed"]["free_cast_available"])
            self.assertIn("忠诚坐骑", paladin["available_features_zh"])

            repo.close()
            event_repo.close()

    def test_execute_projects_paladin_faithful_steed_preserves_explicit_free_cast_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["paladin"] = {
                "level": 5,
                "faithful_steed": {"free_cast_available": False},
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertFalse(paladin["faithful_steed"]["free_cast_available"])

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
            self.assertIn("凶蛮打击", barbarian["available_features_zh"])
            self.assertIn("坚韧狂暴", barbarian["available_features_zh"])
            self.assertIn("持久狂暴", barbarian["available_features_zh"])
            self.assertIn("不屈勇武", barbarian["available_features_zh"])
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

            self.assertIn("巧诈动作", rogue["available_features_zh"])
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

            self.assertIn("坚强防御", monk["available_features_zh"])
            self.assertIn("疾步如风", monk["available_features_zh"])
            repo.close()
            event_repo.close()

    def test_execute_projects_monk_available_features_respect_level_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["monk"] = {
                "level": 2,
                "focus_points": {"max": 2, "remaining": 2},
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            monk = state["current_turn_entity"]["resources"]["class_features"]["monk"]

            self.assertNotIn("available_features", monk)
            self.assertIn("武艺", monk["available_features_zh"])
            self.assertIn("疾风连击", monk["available_features_zh"])
            self.assertNotIn("震慑拳", monk["available_features_zh"])
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
            self.assertTrue(monk["heightened_focus"]["enabled"])
            self.assertTrue(monk["self_restoration"]["enabled"])
            self.assertFalse(monk["perfect_focus"]["enabled"])
            self.assertFalse(monk["superior_defense"]["enabled"])
            repo.close()
            event_repo.close()

    def test_execute_projects_high_level_monk_runtime_state_details(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features["monk"] = {
                "level": 18,
                "focus_points": {"max": 18, "remaining": 2},
                "superior_defense": {"active": True, "remaining_rounds": 7, "added_resistances": ["fire", "cold"]},
            }
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            monk = state["current_turn_entity"]["resources"]["class_features"]["monk"]

            self.assertTrue(monk["deflect_energy"]["enabled"])
            self.assertTrue(monk["disciplined_survivor"]["enabled"])
            self.assertTrue(monk["perfect_focus"]["enabled"])
            self.assertEqual(monk["perfect_focus"]["restore_to"], 4)
            self.assertTrue(monk["superior_defense"]["enabled"])
            self.assertTrue(monk["superior_defense"]["active"])
            self.assertEqual(monk["superior_defense"]["remaining_rounds"], 7)
            self.assertEqual(monk["superior_defense"]["added_resistances"], ["fire", "cold"])
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
            self.assertEqual(forced["summary"], "Goblin被推离 10 尺，移动到 (5,2)。")
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
            self.assertEqual(forced["summary"], "Goblin被推离 15 尺，移动到 (6,2)。")
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
            self.assertEqual(current["movement_remaining"], "20 尺")
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

            self.assertEqual(actions["weapons"][0]["name"], "刺剑")
            self.assertEqual(actions["weapons"][0]["damage"], "1d8+3 穿刺")
            self.assertEqual(actions["weapons"][0]["bonus"], "+5 命中")
            self.assertEqual(actions["spells"]["cantrips"][0]["name"], "魔能爆")
            self.assertIn("cantrips", actions["spells"])
            self.assertEqual(actions["spell_slots_available"]["1"], 1)
            repo.close()

    def test_execute_projects_warlock_pact_magic_into_actions_and_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.resources = {}
            player.class_features = {
                "warlock": {"level": 5},
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            current = state["current_turn_entity"]

            self.assertEqual(current["available_actions"]["spell_slots_available"]["3"], 2)
            self.assertEqual(
                current["resources"]["pact_magic_slots"],
                {"slot_level": 3, "max": 2, "remaining": 2},
            )
            self.assertIn("契约魔法", current["resources"]["summary"])
            repo.close()

    def test_execute_projects_warlock_runtime_summary_from_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features = {
                "warlock": {
                    "level": 17,
                    "eldritch_invocations": {
                        "selected": [
                            {"invocation_id": "pact_of_the_blade"},
                            {"invocation_id": "eldritch_smite"},
                        ]
                    },
                },
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            warlock = state["current_turn_entity"]["resources"]["class_features"]["warlock"]

            self.assertEqual(warlock["level"], 17)
            self.assertEqual(warlock["invocations_known"], 9)
            self.assertEqual(warlock["cantrips_known"], 4)
            self.assertEqual(warlock["prepared_spells_count"], 14)
            self.assertTrue(warlock["magical_cunning"]["enabled"])
            self.assertTrue(warlock["contact_patron"]["enabled"])
            self.assertTrue(warlock["eldritch_smite"]["enabled"])
            self.assertIn("联系宗主", warlock["available_features_zh"])
            self.assertIn("邪术惩击", warlock["available_features_zh"])
            self.assertIn("秘法玄奥", warlock["available_features_zh"])
            repo.close()

    def test_execute_projects_armor_of_shadows_in_warlock_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features = {
                "warlock": {
                    "level": 2,
                    "eldritch_invocations": {
                        "selected": [{"invocation_id": "armor_of_shadows"}],
                    },
                },
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            warlock = state["current_turn_entity"]["resources"]["class_features"]["warlock"]

            self.assertTrue(warlock["armor_of_shadows"]["enabled"])
            self.assertIn("暗影护甲", warlock["available_features_zh"])
            repo.close()

    def test_execute_projects_sorcerer_runtime_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features = {
                "sorcerer": {
                    "level": 7,
                    "sorcery_points": {"current": 5, "max": 7},
                    "innate_sorcery": {"enabled": True, "uses_max": 2, "uses_current": 1, "active": False},
                    "created_spell_slots": {"1": 1, "2": 0, "3": 0, "4": 0, "5": 0},
                }
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            sorcerer = state["current_turn_entity"]["resources"]["class_features"]["sorcerer"]

            self.assertEqual(sorcerer["level"], 7)
            self.assertEqual(sorcerer["sorcery_points"], {"current": 5, "max": 7})
            self.assertEqual(sorcerer["created_spell_slots"]["1"], 1)
            self.assertIn("魔法源泉", sorcerer["available_features_zh"])
            self.assertIn("术法复原", sorcerer["available_features_zh"])
            self.assertIn("术法化身", sorcerer["available_features_zh"])
            repo.close()

    def test_execute_projects_bard_runtime_summary_from_source_ref_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.source_ref["class_name"] = "bard"
            player.source_ref["level"] = 10
            player.ability_mods["cha"] = 4
            player.class_features = {}
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            bard = state["current_turn_entity"]["resources"]["class_features"]["bard"]

            self.assertEqual(bard["level"], 10)
            self.assertEqual(bard["cantrips_known"], 4)
            self.assertEqual(bard["prepared_spells_count"], 15)
            self.assertEqual(bard["bardic_inspiration"]["die"], "d10")
            self.assertEqual(bard["bardic_inspiration"]["uses_max"], 4)
            self.assertTrue(bard["magical_secrets"]["enabled"])
            self.assertIn("吟游诗人激励", bard["available_features_zh"])
            self.assertIn("万事通", bard["available_features_zh"])
            self.assertIn("反迷惑", bard["available_features_zh"])
            self.assertIn("魔法奥秘", bard["available_features_zh"])
            repo.close()

    def test_execute_projects_wizard_runtime_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.source_ref["class_name"] = "wizard"
            player.source_ref["level"] = 6
            player.class_features = {}
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            wizard = state["current_turn_entity"]["resources"]["class_features"]["wizard"]

            self.assertEqual(wizard["level"], 6)
            self.assertEqual(wizard["cantrips_known"], 4)
            self.assertEqual(wizard["prepared_spells_count"], 10)
            self.assertEqual(wizard["spell_preparation_mode"], "long_rest_any")
            self.assertIn("施法", wizard["available_features_zh"])
            repo.close()

    def test_execute_projects_cleric_runtime_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.source_ref["class_name"] = "cleric"
            player.source_ref["level"] = 10
            player.ability_mods["wis"] = 4
            player.class_features = {}
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            cleric = state["current_turn_entity"]["resources"]["class_features"]["cleric"]

            self.assertEqual(cleric["level"], 10)
            self.assertEqual(cleric["cantrips_known"], 5)
            self.assertEqual(cleric["prepared_spells_count"], 15)
            self.assertEqual(cleric["spell_preparation_mode"], "long_rest_any")
            self.assertEqual(cleric["channel_divinity"]["max_uses"], 3)
            self.assertEqual(cleric["divine_spark"]["healing_dice"], "2d8")
            self.assertTrue(cleric["divine_intervention"]["enabled"])
            self.assertIn("施法", cleric["available_features_zh"])
            self.assertIn("引导神力", cleric["available_features_zh"])
            self.assertIn("神迹祈请", cleric["available_features_zh"])
            repo.close()

    def test_execute_projects_druid_runtime_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.source_ref["class_name"] = "druid"
            player.source_ref["level"] = 18
            player.class_features = {}
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            druid = state["current_turn_entity"]["resources"]["class_features"]["druid"]

            self.assertEqual(druid["level"], 18)
            self.assertEqual(druid["cantrips_known"], 4)
            self.assertEqual(druid["prepared_spells_count"], 20)
            self.assertEqual(druid["spell_preparation_mode"], "long_rest_any")
            self.assertEqual(druid["always_prepared_spells"], ["speak_with_animals"])
            self.assertEqual(druid["wild_shape"]["max_uses"], 4)
            self.assertTrue(druid["beast_spells"]["enabled"])
            self.assertFalse(druid["archdruid"]["enabled"])
            self.assertIn("施法", druid["available_features_zh"])
            self.assertIn("野性变形", druid["available_features_zh"])
            self.assertIn("兽形施法", druid["available_features_zh"])
            repo.close()

    def test_execute_projects_druid_archdruid_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.source_ref["class_name"] = "druid"
            player.source_ref["level"] = 20
            player.class_features = {}
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            druid = state["current_turn_entity"]["resources"]["class_features"]["druid"]

            self.assertTrue(druid["archdruid"]["enabled"])
            self.assertTrue(druid["archdruid"]["evergreen_wild_shape"])
            self.assertIn("大德鲁伊", druid["available_features_zh"])
            repo.close()

    def test_execute_projects_paladin_spellcasting_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.source_ref["class_name"] = "paladin"
            player.source_ref["level"] = 5
            player.class_features = {}
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            paladin = state["current_turn_entity"]["resources"]["class_features"]["paladin"]

            self.assertEqual(paladin["level"], 5)
            self.assertEqual(paladin["prepared_spells_count"], 6)
            self.assertEqual(paladin["spell_preparation_mode"], "long_rest_one")
            self.assertEqual(paladin["always_prepared_spells"], ["divine_smite", "find_steed"])
            self.assertIn("施法", paladin["available_features_zh"])
            repo.close()

    def test_execute_projects_ranger_spellcasting_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.source_ref["class_name"] = "ranger"
            player.source_ref["level"] = 9
            player.class_features = {}
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            ranger = state["current_turn_entity"]["resources"]["class_features"]["ranger"]

            self.assertEqual(ranger["level"], 9)
            self.assertEqual(ranger["prepared_spells_count"], 9)
            self.assertEqual(ranger["spell_preparation_mode"], "long_rest_one")
            self.assertEqual(ranger["always_prepared_spells"], ["hunters_mark"])
            self.assertIn("施法", ranger["available_features_zh"])
            repo.close()

    def test_execute_projects_fiendish_vigor_in_warlock_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features = {
                "warlock": {
                    "level": 2,
                    "eldritch_invocations": {
                        "selected": [{"invocation_id": "fiendish_vigor"}],
                    },
                },
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            warlock = state["current_turn_entity"]["resources"]["class_features"]["warlock"]

            self.assertTrue(warlock["fiendish_vigor"]["enabled"])
            self.assertIn("邪魔活力", warlock["available_features_zh"])
            repo.close()

    def test_execute_projects_eldritch_mind_in_warlock_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features = {
                "warlock": {
                    "level": 2,
                    "eldritch_invocations": {
                        "selected": [{"invocation_id": "eldritch_mind"}],
                    },
                },
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            warlock = state["current_turn_entity"]["resources"]["class_features"]["warlock"]

            self.assertTrue(warlock["eldritch_mind"]["enabled"])
            self.assertIn("邪术心智", warlock["available_features_zh"])
            repo.close()

    def test_execute_projects_devils_sight_in_warlock_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.class_features = {
                "warlock": {
                    "level": 2,
                    "eldritch_invocations": {
                        "selected": [{"invocation_id": "devils_sight"}],
                    },
                },
            }
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            warlock = state["current_turn_entity"]["resources"]["class_features"]["warlock"]

            self.assertTrue(warlock["devils_sight"]["enabled"])
            self.assertEqual(warlock["devils_sight"]["range_feet"], 120)
            self.assertIn("魔鬼视觉", warlock["available_features_zh"])
            repo.close()

    def test_execute_projects_ranger_runtime_summary_from_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.ability_mods["wis"] = 3
            player.class_features["ranger"] = {"level": 18}
            repo.save(encounter)

            state = GetEncounterState(repo, event_repo).execute("enc_view_test")
            ranger = state["current_turn_entity"]["resources"]["class_features"]["ranger"]

            self.assertEqual(ranger["level"], 18)
            self.assertEqual(ranger["weapon_mastery_count"], 2)
            self.assertEqual(ranger["favored_enemy"]["free_cast_uses_max"], 2)
            self.assertTrue(ranger["roving"]["enabled"])
            self.assertEqual(ranger["roving"]["speed_bonus_feet"], 10)
            self.assertTrue(ranger["tireless"]["enabled"])
            self.assertEqual(ranger["tireless"]["temp_hp_uses_max"], 3)
            self.assertTrue(ranger["natures_veil"]["enabled"])
            self.assertEqual(ranger["natures_veil"]["uses_max"], 3)
            self.assertTrue(ranger["precise_hunter"]["enabled"])
            self.assertEqual(ranger["feral_senses"]["blindsight_feet"], 30)
            self.assertIn("自然帷幕", ranger["available_features_zh"])
            self.assertIn("野性感官", ranger["available_features_zh"])
            repo.close()
            event_repo.close()

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

            self.assertEqual(weapon_ranges["max_melee_range"], "5 尺")
            self.assertEqual(weapon_ranges["max_ranged_range"], "120 尺")
            self.assertEqual(weapon_ranges["targets_within_melee_range"][0]["name"], "Goblin")
            self.assertEqual(weapon_ranges["targets_within_melee_range"][0]["distance"], "5 尺")
            self.assertEqual(len(weapon_ranges["targets_within_ranged_range"]), 2)
            repo.close()

    def test_execute_builds_turn_order_and_battlemap_details(self) -> None:
        """测试 turn_order 和 battlemap_details 会按视图结构输出。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertEqual(state["turn_order"][1]["distance_from_current_turn_entity"], "5 尺")
            self.assertEqual(state["battlemap_details"]["dimensions"], "10 x 10 格")
            self.assertEqual(state["battlemap_details"]["grid_size"], "每格代表 5 尺")
            repo.close()

    def test_execute_projects_new_llm_facing_top_level_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertEqual(state["encounter"]["encounter_id"], "enc_view_test")
            self.assertEqual(state["encounter"]["current_entity_id"], "ent_ally_eric_001")
            self.assertEqual(state["player_sheet"]["summary"]["name"], "Eric")
            self.assertEqual(state["current_turn_context"]["actor"]["id"], "ent_ally_eric_001")
            self.assertEqual(
                state["interaction"]["command_hints"]["execute_attack"]["required_args"],
                ["encounter_id", "actor_id", "target_id", "weapon_id"],
            )
            self.assertEqual(state["battlemap"]["entities"][1]["entity_id"], "ent_enemy_goblin_001")
            self.assertEqual(state["battlemap"]["details"]["dimensions"], "10 x 10 格")
            repo.close()

    def test_execute_projects_compact_current_turn_context_actor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            actor = state["current_turn_context"]["actor"]
            self.assertEqual(
                set(actor.keys()),
                {
                    "id",
                    "name",
                    "level",
                    "hp",
                    "position",
                    "movement_remaining",
                    "ac",
                    "speed",
                    "spell_save_dc",
                    "spellcasting",
                    "conditions",
                    "ongoing_effects",
                    "resources",
                },
            )
            self.assertEqual(
                actor["spellcasting"],
                {"summary": "本回合还可以通过自身施法消耗一次法术位。"},
            )
            self.assertEqual(
                actor["resources"],
                {"summary": "法术位：1环 1/4, 2环 2/2 | eldritch_invocation: 2/3"},
            )
            self.assertNotIn("class", actor)
            self.assertNotIn("description", actor)
            self.assertNotIn("effective_speed", actor)
            self.assertNotIn("speed_penalty_feet", actor)
            self.assertNotIn("armor", actor)
            self.assertNotIn("shield", actor)
            self.assertNotIn("ac_breakdown", actor)
            self.assertNotIn("stealth_disadvantage_sources", actor)
            self.assertNotIn("untrained_armor_penalties", actor)
            self.assertNotIn("available_actions", actor)
            self.assertNotIn("death_saves", actor)
            repo.close()

    def test_execute_projects_compact_current_turn_context_group_and_targeting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            current_turn_context = state["current_turn_context"]
            group = current_turn_context["current_turn_group"]
            targeting = current_turn_context["targeting"]

            self.assertEqual(
                set(group.keys()),
                {"owner_entity_id", "owner_name", "controlled_members"},
            )
            self.assertEqual(
                set(group["controlled_members"][0].keys()),
                {"entity_id", "name", "relation"},
            )
            self.assertEqual(
                set(targeting.keys()),
                {"melee_range", "ranged_range", "melee_targets", "ranged_targets"},
            )
            self.assertEqual(targeting["melee_range"], "5 尺")
            self.assertEqual(targeting["ranged_range"], "120 尺")
            self.assertEqual(targeting["melee_targets"][0]["name"], "Goblin")
            self.assertEqual(targeting["melee_targets"][0]["distance"], "5 尺")
            self.assertEqual(len(targeting["ranged_targets"]), 2)
            self.assertNotIn("max_melee_range", targeting)
            self.assertNotIn("max_ranged_range", targeting)
            self.assertNotIn("targets_within_melee_range", targeting)
            self.assertNotIn("targets_within_ranged_range", targeting)
            repo.close()

    def test_execute_projects_monster_action_execution_hints_for_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            enemy = encounter.entities["ent_enemy_goblin_001"]
            enemy.source_ref = {
                "traits_metadata": [
                    {
                        "trait_id": "sunlight_sensitivity",
                        "name_zh": "日照敏感",
                        "name_en": "Sunlight Sensitivity",
                        "summary": "处于阳光下时攻击检定具有劣势。",
                    }
                ],
                "actions_metadata": [
                    {
                        "action_id": "necrotic_sword",
                        "name_zh": "死灵剑",
                        "name_en": "Necrotic Sword",
                        "summary": "近战武器攻击。",
                    },
                    {
                        "action_id": "life_drain",
                        "name_zh": "吸取生命",
                        "name_en": "Life Drain",
                        "summary": "体质豁免型特殊动作。",
                    },
                ],
                "bonus_actions_metadata": [],
                "reactions_metadata": [],
                "special_senses": {"darkvision": 60},
                "languages": ["common"],
            }
            enemy.weapons = [
                {
                    "weapon_id": "necrotic_sword",
                    "name": "Necrotic Sword",
                    "attack_bonus": 4,
                    "damage": [{"formula": "1d8+2", "type": "slashing"}],
                    "range": {"normal": 5, "long": 5},
                    "kind": "melee",
                }
            ]
            encounter.current_entity_id = enemy.entity_id
            encounter.turn_order = [enemy.entity_id, "ent_ally_eric_001", "ent_enemy_archer_001"]
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            actor_options = state["current_turn_context"]["actor_options"]
            self.assertEqual(actor_options["traits"][0]["name_zh"], "日照敏感")
            self.assertNotIn("name_en", actor_options["traits"][0])
            self.assertEqual(actor_options["actions"][0]["action_id"], "necrotic_sword")
            self.assertNotIn("name_en", actor_options["actions"][0])
            self.assertEqual(actor_options["actions"][0]["execution"]["command"], "execute_attack")
            self.assertEqual(
                actor_options["actions"][0]["execution"]["preset_args"]["weapon_id"],
                "necrotic_sword",
            )
            self.assertIsNone(actor_options["actions"][1]["execution"]["command"])
            self.assertEqual(actor_options["actions"][1]["execution"]["mode"], "special_action")
            repo.close()

    def test_execute_projects_structured_monster_action_schema_for_llm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            enemy = encounter.entities["ent_enemy_goblin_001"]
            enemy.source_ref = {
                "combat_profile": {
                    "forms": ["vampire", "bat", "mist"],
                    "current_form": "vampire",
                    "passive_rules": ["sunlight_hypersensitivity"],
                    "resources": {
                        "legendary_resistance": {"max": 3, "remaining": 3, "recharge": "long_rest"},
                        "legendary_actions": {"max": 3, "remaining": 3, "recharge": "turn_start"},
                    },
                },
                "actions_metadata": [
                    {
                        "action_id": "multiattack",
                        "name_zh": "多重攻击",
                        "name_en": "Multiattack",
                        "summary": "发动两次葬送打击并使用啃咬。",
                        "action_type": "action",
                        "category": "composite",
                        "availability": {"forms_any_of": ["vampire"]},
                        "targeting": {"mode": "single_primary_target"},
                        "execution_steps": [
                            {"type": "weapon", "weapon_id": "grave_strike", "repeat": 2},
                            {"type": "special_action", "action_id": "bite"},
                        ],
                        "ai_hints": {"role": "melee_finisher", "prefer_when_adjacent": True},
                    },
                ],
                "bonus_actions_metadata": [
                    {
                        "bonus_action_id": "shape_shift",
                        "name_zh": "变形",
                        "name_en": "Shape-Shift",
                        "summary": "变成蝙蝠、迷雾或恢复原形。",
                        "action_type": "bonus_action",
                        "availability": {"not_in_sunlight": True},
                    }
                ],
                "legendary_actions_metadata": [
                    {
                        "legendary_action_id": "deathless_strike",
                        "name_zh": "不死者打击",
                        "name_en": "Deathless Strike",
                        "summary": "移动并发动一次葬送打击。",
                        "action_type": "legendary_action",
                        "resource_cost": {"legendary_actions": 1},
                        "execution_steps": [
                            {"type": "move", "distance_mode": "half_speed"},
                            {"type": "weapon", "weapon_id": "grave_strike"},
                        ],
                    }
                ],
                "reactions_metadata": [],
                "special_senses": {"darkvision": 120},
                "languages": ["common"],
            }
            enemy.weapons = [
                {
                    "weapon_id": "grave_strike",
                    "name": "Grave Strike",
                    "attack_bonus": 9,
                    "damage": [{"formula": "1d8+4", "type": "bludgeoning"}],
                    "range": {"normal": 5, "long": 5},
                    "kind": "melee",
                }
            ]
            encounter.current_entity_id = enemy.entity_id
            encounter.turn_order = [enemy.entity_id, "ent_ally_eric_001", "ent_enemy_archer_001"]
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            actor_options = state["current_turn_context"]["actor_options"]
            battlemap_enemy = next(
                item for item in state["battlemap"]["entities"] if item["entity_id"] == enemy.entity_id
            )

            self.assertEqual(actor_options["actions"][0]["action_type"], "action")
            self.assertEqual(actor_options["actions"][0]["category"], "composite")
            self.assertEqual(actor_options["actions"][0]["availability"]["forms_any_of"], ["vampire"])
            self.assertEqual(actor_options["actions"][0]["targeting"]["mode"], "single_primary_target")
            self.assertEqual(actor_options["actions"][0]["execution_steps"][0]["weapon_id"], "grave_strike")
            self.assertEqual(actor_options["actions"][0]["ai_hints"]["role"], "melee_finisher")
            self.assertEqual(actor_options["bonus_actions"][0]["bonus_action_id"], "shape_shift")
            self.assertEqual(actor_options["legendary_actions"][0]["legendary_action_id"], "deathless_strike")
            self.assertEqual(
                actor_options["legendary_actions"][0]["resource_cost"]["legendary_actions"],
                1,
            )
            self.assertEqual(
                battlemap_enemy["combat_profile"]["legendary_actions"][0]["legendary_action_id"],
                "deathless_strike",
            )
            self.assertEqual(
                battlemap_enemy["combat_profile"]["state"]["resources"]["legendary_actions"]["remaining"],
                3,
            )
            repo.close()

    def test_execute_projects_compact_current_turn_context_spell_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            spell = state["current_turn_context"]["actor_options"]["spells"]["cantrips"][0]
            self.assertEqual(
                set(spell.keys()),
                {"id", "name", "level", "range", "summary", "damage_summary", "requires_attack_roll"},
            )
            self.assertEqual(spell["id"], "eldritch_blast")
            self.assertEqual(spell["name"], "魔能爆")
            self.assertEqual(spell["level"], 0)
            self.assertEqual(spell["range"], "120 尺")
            self.assertEqual(spell["summary"], "A beam of crackling energy.")
            self.assertEqual(spell["damage_summary"], "1d10 力场")
            self.assertTrue(spell["requires_attack_roll"])
            repo.close()

    def test_execute_projects_compact_current_turn_context_weapon_attacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            weapon = state["current_turn_context"]["actor_options"]["weapon_attacks"][0]
            self.assertEqual(
                set(weapon.keys()),
                {"slot", "weapon_id", "name", "damage", "attack_bonus", "note"},
            )
            self.assertEqual(weapon["weapon_id"], "rapier")
            self.assertEqual(weapon["name"], "刺剑")
            self.assertEqual(weapon["damage"], "1d8+3 穿刺")
            self.assertEqual(weapon["attack_bonus"], "+5 命中")
            self.assertNotIn("bonus", weapon)
            self.assertNotIn("properties", weapon)
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
            self.assertEqual(current["conditions"], "目盲")
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

    def test_execute_exposes_spell_slot_cast_limit_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            spellcasting = state["current_turn_entity"]["spellcasting"]

            self.assertFalse(spellcasting["spell_slot_cast_used_this_turn"])
            self.assertTrue(spellcasting["spell_slot_cast_available_this_turn"])
            self.assertTrue(spellcasting["reaction_spell_exception"])
            self.assertTrue(spellcasting["item_cast_exception"])
            self.assertTrue(spellcasting["non_slot_cast_exception"])
            self.assertEqual(spellcasting["summary"], "本回合还可以通过自身施法消耗一次法术位。")

            encounter.entities["ent_ally_eric_001"].action_economy = {
                "spell_slot_cast_used_this_turn": True,
            }
            repo.save(encounter)

            refreshed_state = GetEncounterState(repo).execute("enc_view_test")
            refreshed_spellcasting = refreshed_state["current_turn_entity"]["spellcasting"]

            self.assertTrue(refreshed_spellcasting["spell_slot_cast_used_this_turn"])
            self.assertFalse(refreshed_spellcasting["spell_slot_cast_available_this_turn"])
            self.assertEqual(
                refreshed_spellcasting["summary"],
                "本回合已通过自身施法消耗过一次法术位；动作/附赠动作的再次耗位施法受限，反应法术、物品施法与其他不消耗法术位的施法例外。",
            )
            repo.close()

    def test_execute_projects_spell_effect_summaries_without_exposing_raw_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            state = GetEncounterState(repo).execute("enc_view_test")

            self.assertNotIn("spell_instances", state)
            self.assertIn("定身类人", state["active_spell_summaries"][0])
            goblin = state["turn_order"][1]
            self.assertIn("ongoing_effects", goblin)
            self.assertIn("来自Eric的定身类人", goblin["ongoing_effects"])
            self.assertEqual(
                goblin["conditions"],
                ["麻痹", "来自Eric的定身类人"],
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

            self.assertIn("脱离", state["current_turn_entity"]["ongoing_effects"])
            self.assertIn("闪避", state["turn_order"][1]["ongoing_effects"])
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

            self.assertIn("受到Eric的协助（攻击）", state["turn_order"][1]["ongoing_effects"])
            self.assertIn("受到Eric的协助（调查）", state["turn_order"][2]["ongoing_effects"])
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
                self.assertIn("被Eric擒抱", conditions)
            else:
                self.assertIn("被Eric擒抱", conditions)
            repo.close()
            event_repo.close()

    def test_execute_projects_fixed_player_sheet_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")

            player_sheet = state["player_sheet_source"]
            summary = player_sheet["summary"]
            self.assertEqual(summary["name"], "Eric")
            self.assertEqual(summary["hp_current"], 18)
            self.assertEqual(summary["hp_max"], 20)
            self.assertEqual(summary["ac"], 15)
            self.assertEqual(summary["speed"], 30)
            self.assertEqual(summary["spell_save_dc"], 14)
            self.assertEqual(summary["spell_attack_bonus"], 6)
            self.assertEqual(player_sheet["abilities"][0]["label"], "力量")
            self.assertEqual(player_sheet["abilities"][0]["save_bonus"], 0)
            self.assertEqual(player_sheet["abilities"][4]["label"], "感知")
            self.assertEqual(player_sheet["abilities"][4]["save_bonus"], 3)
            self.assertEqual(player_sheet["abilities"][5]["label"], "魅力")
            self.assertEqual(player_sheet["abilities"][5]["save_bonus"], 6)
            self.assertEqual(player_sheet["tabs"]["skills"][0]["label"], "运动")
            self.assertEqual(player_sheet["tabs"]["skills"][0]["modifier"], 0)
            self.assertEqual(player_sheet["tabs"]["skills"][0]["ability_label"], "力量")
            self.assertEqual(player_sheet["tabs"]["skills"][0]["training_indicator"], "X")
            self.assertEqual(player_sheet["tabs"]["skills"][9]["label"], "驯兽")
            self.assertEqual(player_sheet["tabs"]["equipment"]["weapons"][0]["name"], "刺剑")
            self.assertEqual(player_sheet["tabs"]["equipment"]["weapons"][0]["attack_display"], "D20+5")
            self.assertEqual(player_sheet["tabs"]["equipment"]["weapons"][0]["damage_display"], "1d8+3")
            self.assertEqual(player_sheet["tabs"]["equipment"]["armor"]["items"][0]["name"], "皮甲")
            self.assertEqual(player_sheet["tabs"]["equipment"]["armor"]["items"][0]["dex"], "+2")
            self.assertEqual(player_sheet["tabs"]["equipment"]["armor"]["items"][1]["name"], "盾牌")
            self.assertEqual(player_sheet["tabs"]["equipment"]["backpacks"][0]["items"][0]["name"], "链条")
            self.assertEqual(player_sheet["tabs"]["equipment"]["backpacks"][0]["gold"], 127)
            repo.close()

    def test_execute_projects_bard_player_sheet_skill_modifiers_dynamically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            player = encounter.entities["ent_ally_eric_001"]
            player.source_ref["class_name"] = "bard"
            player.source_ref["level"] = 2
            player.ability_mods = {"str": 1, "dex": 2, "con": 1, "int": 1, "wis": 0, "cha": 4}
            player.proficiency_bonus = 2
            player.skill_modifiers = {}
            player.skill_training = {
                "perception": "proficient",
                "persuasion": "expertise",
            }
            player.class_features = {}
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_test")
            skills = state["player_sheet_source"]["tabs"]["skills"]
            athletics = next(item for item in skills if item["key"] == "athletics")
            perception = next(item for item in skills if item["key"] == "perception")
            persuasion = next(item for item in skills if item["key"] == "persuasion")

            self.assertEqual(athletics["modifier"], 2)
            self.assertEqual(athletics["training_indicator"], "X")
            self.assertEqual(perception["modifier"], 2)
            self.assertEqual(perception["training_indicator"], "O")
            self.assertEqual(persuasion["modifier"], 8)
            self.assertEqual(persuasion["training_indicator"], "🅞")
            repo.close()

    def test_execute_projects_monk_weapon_damage_from_source_ref_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            monk = EncounterEntity(
                entity_id="ent_ally_mylin_001",
                name="米伦",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 2, "y": 2},
                hp={"current": 22, "max": 27, "temp": 0},
                ac=16,
                speed={"walk": 40, "remaining": 40},
                initiative=15,
                source_ref={
                    "class_name": "monk",
                    "level": 5,
                },
                ability_scores={"str": 8, "dex": 17, "con": 14, "int": 8, "wis": 16, "cha": 10},
                ability_mods={"str": -1, "dex": 3, "con": 2, "int": -1, "wis": 3, "cha": 0},
                proficiency_bonus=3,
                skill_training={
                    "sleight_of_hand": "expertise",
                    "stealth": "proficient",
                    "investigation": "expertise",
                    "arcana": "proficient",
                    "perception": "expertise",
                    "insight": "expertise",
                    "persuasion": "expertise",
                },
                skill_modifiers={
                    "athletics": -1,
                    "acrobatics": 3,
                    "sleight_of_hand": 5,
                    "stealth": 5,
                    "investigation": 1,
                    "arcana": 1,
                    "history": -1,
                    "nature": -1,
                    "religion": -1,
                    "perception": 5,
                    "insight": 5,
                    "animal_handling": 3,
                    "medicine": 3,
                    "survival": 3,
                    "persuasion": 2,
                    "deception": 0,
                    "intimidation": 0,
                    "performance": 0,
                },
                weapons=[
                    {
                        "weapon_id": "dagger",
                        "name": "匕首",
                        "category": "simple",
                        "kind": "melee",
                        "damage": [{"formula": "1d4", "type": "piercing"}],
                        "properties": ["finesse", "light", "thrown"],
                        "range": {"normal": 5, "long": 5},
                        "thrown_range": {"normal": 20, "long": 60},
                        "mastery": "迅击",
                    }
                ],
            )
            encounter = Encounter(
                encounter_id="enc_view_monk_test",
                name="View Monk Encounter",
                status="active",
                round=1,
                current_entity_id=monk.entity_id,
                turn_order=[monk.entity_id],
                entities={monk.entity_id: monk},
                map=EncounterMap(
                    map_id="map_view_monk_test",
                    name="Monk Test Map",
                    description="A practice hall.",
                    width=10,
                    height=10,
                ),
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_monk_test")

            self.assertEqual(state["player_sheet_source"]["summary"]["speed"], 40)
            weapon = state["player_sheet_source"]["tabs"]["equipment"]["weapons"][0]
            self.assertEqual(weapon["name"], "匕首")
            self.assertEqual(weapon["proficient"], "O")
            self.assertEqual(weapon["attack_display"], "D20+6")
            self.assertEqual(weapon["damage_display"], "1d8+3")
            repo.close()

    def test_execute_projects_monk_player_sheet_class_features_quantified_focus_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            monk = EncounterEntity(
                entity_id="ent_ally_monk_010",
                name="米伦",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 2, "y": 2},
                hp={"current": 68, "max": 68, "temp": 0},
                ac=17,
                speed={"walk": 50, "remaining": 50},
                initiative=15,
                source_ref={"class_name": "monk", "level": 10},
                ability_scores={"str": 8, "dex": 18, "con": 14, "int": 8, "wis": 16, "cha": 10},
                ability_mods={"str": -1, "dex": 4, "con": 2, "int": -1, "wis": 3, "cha": 0},
                proficiency_bonus=4,
                class_features={"monk": {"level": 10}},
            )
            encounter = Encounter(
                encounter_id="enc_view_monk_features",
                name="Monk Feature Encounter",
                status="active",
                round=1,
                current_entity_id=monk.entity_id,
                turn_order=[monk.entity_id],
                entities={monk.entity_id: monk},
                map=EncounterMap(
                    map_id="map_view_monk_features",
                    name="Monk Test Map",
                    description="A practice hall.",
                    width=8,
                    height=8,
                ),
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_monk_features")

            extras = state["player_sheet_source"]["tabs"]["extras"]
            focus = next(item for item in extras["class_features"] if item["key"] == "monk.monks_focus")
            heightened = next(item for item in extras["class_features"] if item["key"] == "monk.heightened_focus")
            acrobatic = next(item for item in extras["class_features"] if item["key"] == "monk.acrobatic_movement")
            self.assertEqual(
                focus["description"],
                "获得功力资源，并可用其发动三项核心武功：疾风连击可用附赠动作进行两次徒手打击；坚强防御可用附赠动作撤离，消耗功力时还可同时回避；疾步如风可用附赠动作疾走，消耗功力时还可同时撤离并强化跳跃。",
            )
            self.assertEqual(
                heightened["description"],
                "强化三项核心武功：疾风连击消耗 1 点功力时可进行 3 次徒手打击而非 2 次；坚强防御消耗功力使用时获得 2 个武艺骰的临时生命值；疾步如风消耗功力使用时可带上 1 名邻近自愿生物一起移动且不触发借机攻击。",
            )
            self.assertEqual(
                acrobatic["description"],
                "未穿护甲且未持盾时，在自己的回合内可沿垂直表面与液体表面移动而不坠落。",
            )
            self.assertNotIn("monk.disciplined_survivor", {item["key"] for item in extras["class_features"]})
            self.assertTrue(all(item["level"] <= 10 for item in extras["class_features"]))
            repo.close()

    def test_execute_projects_monk_player_sheet_class_features_high_level_hide_locked_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            monk = EncounterEntity(
                entity_id="ent_ally_monk_018",
                name="米伦",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 2, "y": 2},
                hp={"current": 130, "max": 130, "temp": 0},
                ac=19,
                speed={"walk": 60, "remaining": 60},
                initiative=15,
                source_ref={"class_name": "monk", "level": 18},
                ability_scores={"str": 8, "dex": 20, "con": 14, "int": 8, "wis": 18, "cha": 10},
                ability_mods={"str": -1, "dex": 5, "con": 2, "int": -1, "wis": 4, "cha": 0},
                proficiency_bonus=6,
                class_features={"monk": {"level": 18}},
            )
            encounter = Encounter(
                encounter_id="enc_view_monk_features_high_level",
                name="Monk Feature Encounter",
                status="active",
                round=1,
                current_entity_id=monk.entity_id,
                turn_order=[monk.entity_id],
                entities={monk.entity_id: monk},
                map=EncounterMap(
                    map_id="map_view_monk_features_high_level",
                    name="Monk Test Map",
                    description="A practice hall.",
                    width=8,
                    height=8,
                ),
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_monk_features_high_level")

            extras = state["player_sheet_source"]["tabs"]["extras"]
            feature_keys = {item["key"] for item in extras["class_features"]}
            self.assertIn("monk.superior_defense", feature_keys)
            self.assertIn("monk.perfect_focus", feature_keys)
            self.assertIn("monk.disciplined_survivor", feature_keys)
            self.assertNotIn("monk.epic_boon", feature_keys)
            self.assertNotIn("monk.body_and_mind", feature_keys)
            self.assertTrue(all(item["level"] <= 18 for item in extras["class_features"]))
            repo.close()

    def test_execute_projects_fighter_player_sheet_class_features(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            fighter = EncounterEntity(
                entity_id="ent_ally_fighter_001",
                name="萨布尔",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 2, "y": 2},
                hp={"current": 68, "max": 68, "temp": 0},
                ac=18,
                speed={"walk": 30, "remaining": 30},
                initiative=12,
                source_ref={"class_name": "fighter", "level": 13},
                ability_scores={"str": 18, "dex": 14, "con": 16, "int": 10, "wis": 12, "cha": 8},
                ability_mods={"str": 4, "dex": 2, "con": 3, "int": 0, "wis": 1, "cha": -1},
                proficiency_bonus=5,
                class_features={"fighter": {"level": 13}},
            )
            encounter = Encounter(
                encounter_id="enc_view_fighter_features",
                name="Fighter Feature Encounter",
                status="active",
                round=1,
                current_entity_id=fighter.entity_id,
                turn_order=[fighter.entity_id],
                entities={fighter.entity_id: fighter},
                map=EncounterMap(
                    map_id="map_view_fighter_features",
                    name="Fighter Test Map",
                    description="A drill yard.",
                    width=8,
                    height=8,
                ),
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_fighter_features")

            extras = state["player_sheet_source"]["tabs"]["extras"]
            self.assertEqual(extras["title"], "职业特性")
            self.assertEqual(extras["class_name"], "fighter")
            self.assertTrue(len(extras["class_features"]) > 0)
            self.assertEqual(extras["class_features"][0]["label"], "战斗风格")
            self.assertEqual(
                extras["class_features"][0]["description"],
                "获得 1 项战斗风格专长；每次获得战士等级时可更换。",
            )
            self.assertTrue(extras["class_features"][0]["unlocked"])
            studied_attacks = next(item for item in extras["class_features"] if item["key"] == "fighter.studied_attacks")
            self.assertEqual(studied_attacks["level"], 13)
            self.assertEqual(
                studied_attacks["description"],
                "攻击失手后，在你下个回合结束前对该目标的下一次攻击具有优势。",
            )
            self.assertTrue(studied_attacks["unlocked"])
            self.assertNotIn("fighter.epic_boon", {item["key"] for item in extras["class_features"]})
            self.assertTrue(all(item["level"] <= 13 for item in extras["class_features"]))
            repo.close()

    def test_execute_projects_barbarian_player_sheet_class_features_hide_locked_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            barbarian = EncounterEntity(
                entity_id="ent_ally_barbarian_001",
                name="托姆",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 2, "y": 2},
                hp={"current": 95, "max": 95, "temp": 0},
                ac=17,
                speed={"walk": 40, "remaining": 40},
                initiative=10,
                source_ref={"class_name": "barbarian", "level": 9},
                ability_scores={"str": 18, "dex": 14, "con": 18, "int": 8, "wis": 12, "cha": 10},
                ability_mods={"str": 4, "dex": 2, "con": 4, "int": -1, "wis": 1, "cha": 0},
                proficiency_bonus=4,
                class_features={"barbarian": {"level": 9}},
            )
            encounter = Encounter(
                encounter_id="enc_view_barbarian_features",
                name="Barbarian Feature Encounter",
                status="active",
                round=1,
                current_entity_id=barbarian.entity_id,
                turn_order=[barbarian.entity_id],
                entities={barbarian.entity_id: barbarian},
                map=EncounterMap(
                    map_id="map_view_barbarian_features",
                    name="Barbarian Test Map",
                    description="A shattered gate.",
                    width=8,
                    height=8,
                ),
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_barbarian_features")

            extras = state["player_sheet_source"]["tabs"]["extras"]
            rage = next(item for item in extras["class_features"] if item["key"] == "barbarian.rage")
            self.assertEqual(
                rage["description"],
                "附赠动作进入狂暴。获得钝击/穿刺/挥砍抗性；基于力量的攻击伤害获得额外加值；力量检定与力量豁免具有优势；不能专注或施法。",
            )
            self.assertNotIn("barbarian.relentless_rage", {item["key"] for item in extras["class_features"]})
            self.assertTrue(all(item["level"] <= 9 for item in extras["class_features"]))
            repo.close()

    def test_execute_projects_barbarian_player_sheet_class_features_include_high_level_unlocked_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            barbarian = EncounterEntity(
                entity_id="ent_ally_barbarian_018",
                name="托姆",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 2, "y": 2},
                hp={"current": 176, "max": 176, "temp": 0},
                ac=16,
                speed={"walk": 40, "remaining": 40},
                initiative=10,
                source_ref={"class_name": "barbarian", "level": 18},
                ability_scores={"str": 20, "dex": 14, "con": 18, "int": 8, "wis": 12, "cha": 10},
                ability_mods={"str": 5, "dex": 2, "con": 4, "int": -1, "wis": 1, "cha": 0},
                proficiency_bonus=6,
                class_features={"barbarian": {"level": 18}},
            )
            encounter = Encounter(
                encounter_id="enc_view_barbarian_features_high_level",
                name="Barbarian Feature Encounter",
                status="active",
                round=1,
                current_entity_id=barbarian.entity_id,
                turn_order=[barbarian.entity_id],
                entities={barbarian.entity_id: barbarian},
                map=EncounterMap(
                    map_id="map_view_barbarian_features_high_level",
                    name="Barbarian Test Map",
                    description="A shattered gate.",
                    width=8,
                    height=8,
                ),
            )
            repo.save(encounter)

            state = GetEncounterState(repo).execute("enc_view_barbarian_features_high_level")

            extras = state["player_sheet_source"]["tabs"]["extras"]
            feature_keys = {item["key"] for item in extras["class_features"]}
            self.assertIn("barbarian.persistent_rage", feature_keys)
            self.assertIn("barbarian.improved_brutal_strike_17", feature_keys)
            self.assertIn("barbarian.indomitable_might", feature_keys)
            self.assertNotIn("barbarian.epic_boon", feature_keys)
            self.assertNotIn("barbarian.primal_champion", feature_keys)
            self.assertTrue(all(item["level"] <= 18 for item in extras["class_features"]))
            repo.close()


    def test_execute_projects_enemy_tactical_brief_for_current_melee_gm_actor(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="shortsword",
                name="Shortsword",
                damage_formula="1d6+2",
                damage_type="piercing",
                normal_range=5,
                long_range=5,
                kind="melee",
                category="martial",
            )
        )

        state = execute_get_encounter_state(encounter)

        brief = state["current_turn_context"]["enemy_tactical_brief"]
        self.assertIn("candidate_targets", brief)
        self.assertEqual(len(brief["candidate_targets"]), 1)
        self.assertEqual(brief["candidate_targets"][0]["entity_id"], "ent_ally_player_001")
        self.assertTrue(brief["candidate_targets"][0]["in_attack_range"])
        self.assertEqual(brief["candidate_targets"][0]["priority_reason"], "目标甲低，更容易打穿")
        self.assertEqual(brief["recommended_tactic"]["action"], "attack")
        self.assertEqual(brief["recommended_tactic"]["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(brief["recommended_tactic"]["engage_mode"], "already_in_range")
        self.assertEqual(brief["recommended_tactic"]["reason"], "已经贴住目标，直接近战施压")
        self.assertEqual(
            brief["recommended_tactic"]["execution_plan"],
            [
                {
                    "command": "execute_attack",
                    "args": {
                        "encounter_id": "enc_enemy_brief_actor",
                        "actor_id": "ent_enemy_brute_001",
                        "target_id": "ent_ally_player_001",
                        "weapon_id": "shortsword",
                    },
                }
            ],
        )

    def test_execute_omits_enemy_tactical_brief_on_player_turn(self) -> None:
        state = execute_get_encounter_state(
            build_enemy_tactical_brief_actor_encounter(
                current_actor="ent_ally_player_001",
                enemy_weapon=build_test_weapon(
                    weapon_id="shortsword",
                    name="Shortsword",
                    damage_formula="1d6+2",
                    damage_type="piercing",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                ),
            )
        )

        self.assertNotIn("enemy_tactical_brief", state["current_turn_context"])

    def test_execute_omits_enemy_tactical_brief_for_gm_controlled_non_enemy_actor(self) -> None:
        encounter = build_enemy_tactical_brief_actor_encounter(
            current_actor="ent_ally_player_001",
            enemy_weapon=build_test_weapon(
                weapon_id="shortsword",
                name="Shortsword",
                damage_formula="1d6+2",
                damage_type="piercing",
                normal_range=5,
                long_range=5,
                kind="melee",
            ),
        )
        ally_actor = encounter.entities["ent_ally_player_001"]
        ally_actor.controller = "gm"
        ally_actor.weapons = [
            build_test_weapon(
                weapon_id="dagger",
                name="Dagger",
                damage_formula="1d4+2",
                damage_type="piercing",
                normal_range=5,
                long_range=20,
                kind="melee",
            )
        ]

        state = execute_get_encounter_state(encounter)

        self.assertNotIn("enemy_tactical_brief", state["current_turn_context"])

    def test_execute_enemy_tactical_brief_returns_top_two_ranked_targets(self) -> None:
        encounter = build_enemy_tactical_brief_ranking_encounter()

        state = execute_get_encounter_state(encounter)

        brief = state["current_turn_context"]["enemy_tactical_brief"]
        candidates = brief["candidate_targets"]
        candidate_ids = [item["entity_id"] for item in candidates]
        candidate_scores = [item["score"] for item in candidates]

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidate_ids, ["ent_ally_concentration_001", "ent_ally_low_ac_001"])
        self.assertLess(candidate_scores[0], candidate_scores[1])
        self.assertLessEqual(candidate_scores[1] - candidate_scores[0], 8.0)
        self.assertTrue(all(item["in_attack_range"] for item in candidates))
        self.assertEqual(candidates[0]["priority_reason"], "目标正在维持专注，优先打断")
        self.assertEqual(candidates[1]["priority_reason"], "目标甲低，更容易打穿")
        self.assertNotIn("ent_ally_summon_001", candidate_ids)
        self.assertNotIn("ent_ally_far_001", candidate_ids)
        score_by_id = {item["entity_id"]: item["score"] for item in candidates}
        self.assertGreater(score_by_id["ent_ally_concentration_001"], 2.0)

    def test_execute_enemy_tactical_brief_prefers_concentration_on_close_scores(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 40, "max": 40, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        low_ac_non_concentration = EncounterEntity(
            entity_id="ent_ally_low_ac_001",
            name="Low AC",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=10,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        concentrating_higher_ac = EncounterEntity(
            entity_id="ent_ally_concentration_001",
            name="Concentration",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 6},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            turn_effects=[{"effect_id": "fx_conc", "effect_type": "concentration", "name": "Hex"}],
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_close_score_concentration",
            name="Enemy Brief Close Score Concentration",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, low_ac_non_concentration.entity_id, concentrating_higher_ac.entity_id],
            entities={
                enemy.entity_id: enemy,
                low_ac_non_concentration.entity_id: low_ac_non_concentration,
                concentrating_higher_ac.entity_id: concentrating_higher_ac,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_close_score_concentration",
                name="Close Score Map",
                description="close score concentration preference",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        candidates = state["current_turn_context"]["enemy_tactical_brief"]["candidate_targets"]

        self.assertEqual(candidates[0]["entity_id"], concentrating_higher_ac.entity_id)
        self.assertEqual(candidates[1]["entity_id"], low_ac_non_concentration.entity_id)
        self.assertEqual(candidates[0]["priority_reason"], "目标正在维持专注，优先打断")

    def test_execute_enemy_tactical_brief_projects_attack_has_advantage_and_applies_small_bonus(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 40, "max": 40, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        normal_target = EncounterEntity(
            entity_id="ent_ally_normal_001",
            name="Normal",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        advantaged_target = EncounterEntity(
            entity_id="ent_ally_adv_001",
            name="Advantaged",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 6},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            conditions=["restrained"],
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_adv_projection",
            name="Enemy Brief Advantage Projection",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, normal_target.entity_id, advantaged_target.entity_id],
            entities={
                enemy.entity_id: enemy,
                normal_target.entity_id: normal_target,
                advantaged_target.entity_id: advantaged_target,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_adv_projection",
                name="Adv Projection Map",
                description="advantage projection test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        candidates = state["current_turn_context"]["enemy_tactical_brief"]["candidate_targets"]
        by_id = {item["entity_id"]: item for item in candidates}

        self.assertTrue(by_id[advantaged_target.entity_id]["attack_has_advantage"])
        self.assertFalse(by_id[normal_target.entity_id]["attack_has_advantage"])
        self.assertEqual(by_id[advantaged_target.entity_id]["score"], by_id[normal_target.entity_id]["score"] + 1.0)
        self.assertEqual(by_id[advantaged_target.entity_id]["priority_reason"], "对其出手占优，适合先压")

    def test_execute_enemy_tactical_brief_advantage_bonus_does_not_override_primary_signals(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 40, "max": 40, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        advantage_only = EncounterEntity(
            entity_id="ent_ally_adv_only_001",
            name="AdvantageOnly",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
            conditions=["paralyzed"],
        )
        concentration_target = EncounterEntity(
            entity_id="ent_ally_concentration_001",
            name="Concentration",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 6},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            turn_effects=[{"effect_id": "fx_conc", "effect_type": "concentration", "name": "Hex"}],
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_adv_not_override",
            name="Enemy Brief Advantage Not Override",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, advantage_only.entity_id, concentration_target.entity_id],
            entities={
                enemy.entity_id: enemy,
                advantage_only.entity_id: advantage_only,
                concentration_target.entity_id: concentration_target,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_adv_not_override",
                name="Adv Not Override Map",
                description="advantage should not override concentration",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        candidates = state["current_turn_context"]["enemy_tactical_brief"]["candidate_targets"]
        by_id = {item["entity_id"]: item for item in candidates}

        self.assertEqual(candidates[0]["entity_id"], concentration_target.entity_id)
        self.assertGreater(by_id[concentration_target.entity_id]["score"], by_id[advantage_only.entity_id]["score"])
        self.assertFalse(by_id[concentration_target.entity_id]["attack_has_advantage"])
        self.assertTrue(by_id[advantage_only.entity_id]["attack_has_advantage"])

    def test_execute_enemy_tactical_brief_returns_empty_candidates_when_no_target_in_range(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="club",
                name="Club",
                damage_formula="1d4+2",
                damage_type="bludgeoning",
                normal_range=5,
                long_range=5,
                kind="melee",
            ),
            position={"x": 9, "y": 9},
        )

        state = execute_get_encounter_state(encounter)

        brief = state["current_turn_context"]["enemy_tactical_brief"]
        self.assertEqual(brief["candidate_targets"], [])

    def test_execute_enemy_tactical_brief_excludes_downed_player_from_candidates_and_reachable(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 1, "y": 1},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        downed_player = EncounterEntity(
            entity_id="ent_ally_downed_001",
            name="Downed Player",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 2, "y": 1},
            hp={"current": 0, "max": 20, "temp": 0},
            ac=10,
            speed={"walk": 30, "remaining": 0},
            initiative=10,
            conditions=["unconscious"],
            combat_flags={"death_saves": {"successes": 0, "failures": 1}},
        )
        standing_player = EncounterEntity(
            entity_id="ent_ally_standing_001",
            name="Standing Player",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 1},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_excludes_downed_player",
            name="Enemy Brief Excludes Downed Player",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, downed_player.entity_id, standing_player.entity_id],
            entities={
                enemy.entity_id: enemy,
                downed_player.entity_id: downed_player,
                standing_player.entity_id: standing_player,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_excludes_downed_player",
                name="Exclude Downed Player",
                description="downed player should not be targeted",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        brief = state["current_turn_context"]["enemy_tactical_brief"]

        self.assertEqual([item["entity_id"] for item in brief["candidate_targets"]], [])
        self.assertEqual([item["entity_id"] for item in brief["reachable_targets"]], [standing_player.entity_id])
        self.assertEqual(brief["recommended_tactic"]["action"], "move_and_attack")
        self.assertEqual(brief["recommended_tactic"]["target_entity_id"], standing_player.entity_id)
        self.assertEqual(brief["recommended_tactic"]["engage_mode"], "move_and_attack")
        self.assertEqual(brief["recommended_tactic"]["reason"], "可以直接贴上目标，本回合就近战施压")
        self.assertEqual(
            brief["recommended_tactic"]["execution_plan"],
            [
                {
                    "command": "begin_move_encounter_entity",
                    "args": {
                        "encounter_id": "enc_enemy_brief_excludes_downed_player",
                        "entity_id": "ent_enemy_brute_001",
                        "target_position": {"x": 4, "y": 1},
                    },
                },
                {
                    "command": "execute_attack",
                    "args": {
                        "encounter_id": "enc_enemy_brief_excludes_downed_player",
                        "actor_id": "ent_enemy_brute_001",
                        "target_id": standing_player.entity_id,
                        "weapon_id": "mace",
                    },
                },
            ],
        )

    def test_execute_enemy_tactical_brief_low_ac_is_relative_to_current_candidate_pool(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 40, "max": 40, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        in_range_target = EncounterEntity(
            entity_id="ent_ally_in_range_001",
            name="In Range",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        far_lower_ac_target = EncounterEntity(
            entity_id="ent_ally_far_low_ac_001",
            name="Far Low AC",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 10, "y": 5},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=10,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_relative_low_ac",
            name="Enemy Brief Relative Low AC",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, in_range_target.entity_id, far_lower_ac_target.entity_id],
            entities={
                enemy.entity_id: enemy,
                in_range_target.entity_id: in_range_target,
                far_lower_ac_target.entity_id: far_lower_ac_target,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_relative_low_ac",
                name="Relative Low AC",
                description="low ac should be relative to current candidate pool",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        brief = state["current_turn_context"]["enemy_tactical_brief"]

        self.assertEqual([item["entity_id"] for item in brief["candidate_targets"]], [in_range_target.entity_id])
        self.assertEqual(brief["candidate_targets"][0]["priority_reason"], "目标甲低，更容易打穿")

    def test_execute_omits_enemy_tactical_brief_for_ranged_only_gm_actor(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="longbow",
                name="Longbow",
                damage_formula="1d8+2",
                damage_type="piercing",
                normal_range=150,
                long_range=600,
                kind="ranged",
            )
        )

        state = execute_get_encounter_state(encounter)

        self.assertNotIn("enemy_tactical_brief", state["current_turn_context"])

    def test_execute_projects_enemy_ranged_tactical_brief_for_ranged_only_gm_actor(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="longbow",
                name="Longbow",
                damage_formula="1d8+2",
                damage_type="piercing",
                normal_range=150,
                long_range=600,
                kind="ranged",
            )
        )

        state = execute_get_encounter_state(encounter)

        brief = state["current_turn_context"]["enemy_ranged_tactical_brief"]
        self.assertEqual(brief["candidate_targets"][0]["entity_id"], "ent_ally_player_001")
        self.assertEqual(brief["candidate_targets"][0]["priority_reason"], "目标甲低，更容易打穿")
        self.assertFalse(brief["pressure_state"]["threatened_in_melee"])
        self.assertFalse(brief["pressure_state"]["bloodied"])
        self.assertEqual(brief["pressure_state"]["stay_and_shoot_penalty"], "无")
        self.assertEqual(brief["fallback_options"], [])
        self.assertEqual(brief["recommended_tactic"]["action"], "attack")
        self.assertEqual(brief["recommended_tactic"]["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(brief["recommended_tactic"]["reason"], "未被贴身，优先点杀高价值目标")
        self.assertEqual(
            brief["recommended_tactic"]["execution_plan"],
            [
                {
                    "command": "execute_attack",
                    "args": {
                        "encounter_id": "enc_enemy_brief_actor",
                        "actor_id": "ent_enemy_brute_001",
                        "target_id": "ent_ally_player_001",
                        "weapon_id": "longbow",
                    },
                }
            ],
        )

    def test_execute_enemy_ranged_tactical_brief_attacks_under_melee_pressure_when_not_bloodied(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_archer_001",
            name="Archer",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 18, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="longbow",
                    name="Longbow",
                    damage_formula="1d8+2",
                    damage_type="piercing",
                    normal_range=150,
                    long_range=600,
                    kind="ranged",
                )
            ],
        )
        melee_threat = EncounterEntity(
            entity_id="ent_ally_fighter_001",
            name="Fighter",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            weapons=[
                build_test_weapon(
                    weapon_id="longsword",
                    name="Longsword",
                    damage_formula="1d8+3",
                    damage_type="slashing",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
            action_economy={"reaction_used": False},
        )
        player_target = EncounterEntity(
            entity_id="ent_ally_wizard_001",
            name="Wizard",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 9, "y": 5},
            hp={"current": 18, "max": 18, "temp": 0},
            ac=13,
            speed={"walk": 30, "remaining": 30},
            initiative=9,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_ranged_brief_pressure_attack",
            name="Enemy Ranged Brief Pressure Attack",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, melee_threat.entity_id, player_target.entity_id],
            entities={
                enemy.entity_id: enemy,
                melee_threat.entity_id: melee_threat,
                player_target.entity_id: player_target,
            },
            map=EncounterMap(
                map_id="map_enemy_ranged_brief_pressure_attack",
                name="Pressure Attack Map",
                description="ranged pressure attack test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        brief = state["current_turn_context"]["enemy_ranged_tactical_brief"]

        self.assertTrue(brief["pressure_state"]["threatened_in_melee"])
        self.assertFalse(brief["pressure_state"]["bloodied"])
        self.assertEqual(brief["recommended_tactic"]["action"], "attack")
        self.assertEqual(brief["recommended_tactic"]["reason"], "虽被贴身但仍可承压，先顶着压力射击")

    def test_execute_projects_enemy_hybrid_tactical_brief_prefers_save_action_when_melee_hit_rate_is_low(self) -> None:
        encounter = build_enemy_hybrid_brief_encounter(
            enemy_position={"x": 5, "y": 5},
            player_position={"x": 6, "y": 5},
            player_ac=19,
            melee_attack_bonus=3,
            ranged_attack_bonus=4,
            save_action_range_feet=5,
        )

        state = execute_get_encounter_state(encounter)

        brief = state["current_turn_context"]["enemy_hybrid_tactical_brief"]
        self.assertEqual(brief["available_modes"], ["melee_attack", "ranged_attack", "save_action"])
        self.assertEqual(brief["recommended_mode"], "multiattack")
        self.assertEqual(brief["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(brief["selected_action_id"], "life_drain")
        self.assertEqual(brief["selected_weapon_id"], "necrotic_sword")
        self.assertEqual(brief["reason"], "目标甲高，先用吸取生命压制再补一击")
        self.assertEqual(
            brief["recommended_tactic"]["execution_plan"],
            [
                {
                    "command": None,
                    "mode": "special_action",
                    "action_id": "life_drain",
                    "target_id": "ent_ally_player_001",
                    "note": "不是标准武器攻击；通常需要专用动作或豁免接口。",
                },
                {
                    "command": "execute_attack",
                    "args": {
                        "encounter_id": "enc_enemy_hybrid_brief",
                        "actor_id": "ent_enemy_hybrid_001",
                        "target_id": "ent_ally_player_001",
                        "weapon_id": "necrotic_sword",
                    },
                },
            ],
        )

    def test_execute_projects_enemy_hybrid_tactical_brief_defaults_to_melee_attack(self) -> None:
        encounter = build_enemy_hybrid_brief_encounter(
            enemy_position={"x": 5, "y": 5},
            player_position={"x": 6, "y": 5},
            player_ac=14,
            melee_attack_bonus=5,
            ranged_attack_bonus=4,
            save_action_range_feet=5,
        )

        state = execute_get_encounter_state(encounter)

        brief = state["current_turn_context"]["enemy_hybrid_tactical_brief"]
        self.assertEqual(brief["recommended_mode"], "multiattack")
        self.assertEqual(brief["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(brief["selected_weapon_id"], "necrotic_sword")
        self.assertIsNone(brief["selected_action_id"])
        self.assertEqual(brief["reason"], "已贴近目标，优先用多重攻击施压")
        self.assertEqual(len(brief["recommended_tactic"]["execution_plan"]), 2)
        self.assertEqual(
            [step["command"] for step in brief["recommended_tactic"]["execution_plan"]],
            ["execute_attack", "execute_attack"],
        )

    def test_execute_projects_enemy_hybrid_tactical_brief_falls_back_to_ranged_attack_when_not_in_melee(self) -> None:
        encounter = build_enemy_hybrid_brief_encounter(
            enemy_position={"x": 5, "y": 5},
            player_position={"x": 15, "y": 5},
            player_ac=14,
            melee_attack_bonus=5,
            ranged_attack_bonus=4,
            save_action_range_feet=5,
        )

        state = execute_get_encounter_state(encounter)

        brief = state["current_turn_context"]["enemy_hybrid_tactical_brief"]
        self.assertEqual(brief["recommended_mode"], "multiattack")
        self.assertEqual(brief["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(brief["selected_weapon_id"], "necrotic_bow")
        self.assertIsNone(brief["selected_action_id"])
        self.assertEqual(brief["reason"], "暂时接不上近战，优先用死灵弓多重压制")
        self.assertEqual(len(brief["recommended_tactic"]["execution_plan"]), 2)
        self.assertEqual(
            [step["command"] for step in brief["recommended_tactic"]["execution_plan"]],
            ["execute_attack", "execute_attack"],
        )

    def test_execute_projects_top_level_enemy_turn_recommendation_for_melee_actor(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="shortsword",
                name="Shortsword",
                damage_formula="1d6+2",
                damage_type="piercing",
                normal_range=5,
                long_range=5,
                kind="melee",
            )
        )

        state = execute_get_encounter_state(encounter)
        recommendation = state["current_turn_context"]["recommended_tactic"]
        contingencies = state["current_turn_context"]["contingencies"]

        self.assertEqual(recommendation["source"], "enemy_tactical_brief")
        self.assertEqual(recommendation["action"], "attack")
        self.assertEqual(recommendation["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(recommendation["execution_plan"][0]["command"], "execute_attack")
        self.assertEqual(contingencies["alternative_targets"], [])
        self.assertEqual(contingencies["reachable_options"], [])

    def test_execute_projects_top_level_enemy_turn_recommendation_for_ranged_actor(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="longbow",
                name="Longbow",
                damage_formula="1d8+2",
                damage_type="piercing",
                normal_range=150,
                long_range=600,
                kind="ranged",
            )
        )

        state = execute_get_encounter_state(encounter)
        recommendation = state["current_turn_context"]["recommended_tactic"]
        contingencies = state["current_turn_context"]["contingencies"]

        self.assertEqual(recommendation["source"], "enemy_ranged_tactical_brief")
        self.assertEqual(recommendation["action"], "attack")
        self.assertEqual(recommendation["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(recommendation["execution_plan"][0]["command"], "execute_attack")
        self.assertEqual(contingencies["alternative_targets"], [])
        self.assertEqual(contingencies["fallback_options"], [])

    def test_execute_projects_top_level_enemy_turn_recommendation_for_melee_multiattack_actor(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="claw",
                name="Claw",
                damage_formula="1d6+2",
                damage_type="slashing",
                normal_range=5,
                long_range=5,
                kind="melee",
            ),
            source_ref={
                "actions_metadata": [
                    {
                        "action_id": "multiattack",
                        "name_zh": "多重攻击",
                        "name_en": "Multiattack",
                        "summary": "进行两次爪击。",
                        "multiattack_sequences": [
                            {
                                "sequence_id": "double_claw",
                                "mode": "melee",
                                "steps": [
                                    {"type": "weapon", "weapon_id": "claw"},
                                    {"type": "weapon", "weapon_id": "claw"},
                                ],
                            }
                        ],
                    }
                ]
            },
        )

        state = execute_get_encounter_state(encounter)
        recommendation = state["current_turn_context"]["recommended_tactic"]

        self.assertEqual(recommendation["source"], "enemy_tactical_brief")
        self.assertEqual(recommendation["action"], "multiattack")
        self.assertEqual(recommendation["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(recommendation["reason"], "已经贴住目标，优先用多重攻击施压")
        self.assertEqual(
            [step["command"] for step in recommendation["execution_plan"]],
            ["execute_attack", "execute_attack"],
        )

    def test_execute_projects_top_level_enemy_turn_recommendation_for_ranged_multiattack_actor(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="longbow",
                name="Longbow",
                damage_formula="1d8+2",
                damage_type="piercing",
                normal_range=150,
                long_range=600,
                kind="ranged",
            ),
            source_ref={
                "actions_metadata": [
                    {
                        "action_id": "multiattack",
                        "name_zh": "多重攻击",
                        "name_en": "Multiattack",
                        "summary": "进行两次长弓射击。",
                        "multiattack_sequences": [
                            {
                                "sequence_id": "double_shot",
                                "mode": "ranged",
                                "steps": [
                                    {"type": "weapon", "weapon_id": "longbow"},
                                    {"type": "weapon", "weapon_id": "longbow"},
                                ],
                            }
                        ],
                    }
                ]
            },
        )

        state = execute_get_encounter_state(encounter)
        recommendation = state["current_turn_context"]["recommended_tactic"]

        self.assertEqual(recommendation["source"], "enemy_ranged_tactical_brief")
        self.assertEqual(recommendation["action"], "multiattack")
        self.assertEqual(recommendation["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(recommendation["reason"], "未被贴身，优先用多重射击压制")
        self.assertEqual(
            [step["command"] for step in recommendation["execution_plan"]],
            ["execute_attack", "execute_attack"],
        )

    def test_execute_projects_top_level_enemy_turn_recommendation_for_hybrid_actor(self) -> None:
        encounter = build_enemy_hybrid_brief_encounter(
            enemy_position={"x": 5, "y": 5},
            player_position={"x": 6, "y": 5},
            player_ac=19,
            melee_attack_bonus=3,
            ranged_attack_bonus=4,
            save_action_range_feet=5,
        )

        state = execute_get_encounter_state(encounter)
        recommendation = state["current_turn_context"]["recommended_tactic"]
        contingencies = state["current_turn_context"]["contingencies"]

        self.assertEqual(recommendation["source"], "enemy_hybrid_tactical_brief")
        self.assertEqual(recommendation["action"], "multiattack")
        self.assertEqual(recommendation["target_entity_id"], "ent_ally_player_001")
        self.assertEqual(recommendation["selected_action_id"], "life_drain")
        self.assertEqual(recommendation["selected_weapon_id"], "necrotic_sword")
        self.assertEqual(recommendation["reason"], "目标甲高，先用吸取生命压制再补一击")
        self.assertEqual(contingencies["alternate_modes"], ["melee_attack", "ranged_attack", "save_action"])

    def test_execute_enemy_ranged_tactical_brief_prioritizes_concentration_over_low_ac(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_archer_001",
            name="Archer",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 22, "max": 22, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="longbow",
                    name="Longbow",
                    damage_formula="1d8+2",
                    damage_type="piercing",
                    normal_range=150,
                    long_range=600,
                    kind="ranged",
                )
            ],
        )
        low_ac_target = EncounterEntity(
            entity_id="ent_ally_low_ac_001",
            name="Low AC",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 9, "y": 5},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=11,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        concentration_target = EncounterEntity(
            entity_id="ent_ally_concentration_001",
            name="Concentration",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 8, "y": 5},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            turn_effects=[{"effect_id": "fx_conc", "effect_type": "concentration", "name": "Hex"}],
        )
        encounter = Encounter(
            encounter_id="enc_enemy_ranged_brief_priority",
            name="Enemy Ranged Brief Priority",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, low_ac_target.entity_id, concentration_target.entity_id],
            entities={
                enemy.entity_id: enemy,
                low_ac_target.entity_id: low_ac_target,
                concentration_target.entity_id: concentration_target,
            },
            map=EncounterMap(
                map_id="map_enemy_ranged_brief_priority",
                name="Ranged Priority Map",
                description="ranged priority test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        candidates = state["current_turn_context"]["enemy_ranged_tactical_brief"]["candidate_targets"]

        self.assertEqual([item["entity_id"] for item in candidates], [concentration_target.entity_id, low_ac_target.entity_id])
        self.assertEqual(candidates[0]["priority_reason"], "目标正在维持专注，优先打断")
        self.assertEqual(candidates[1]["priority_reason"], "目标甲低，更容易打穿")

    def test_execute_enemy_ranged_tactical_brief_projects_bloodied_melee_pressure_and_fallback(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_archer_001",
            name="Archer",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 10, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="longbow",
                    name="Longbow",
                    damage_formula="1d8+2",
                    damage_type="piercing",
                    normal_range=150,
                    long_range=600,
                    kind="ranged",
                )
            ],
        )
        melee_threat = EncounterEntity(
            entity_id="ent_ally_fighter_001",
            name="Fighter",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            weapons=[
                build_test_weapon(
                    weapon_id="longsword",
                    name="Longsword",
                    damage_formula="1d8+3",
                    damage_type="slashing",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
            action_economy={"reaction_used": False},
        )
        ally_enemy = EncounterEntity(
            entity_id="ent_enemy_guard_001",
            name="Guard",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 3, "y": 5},
            hp={"current": 18, "max": 18, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        player_target = EncounterEntity(
            entity_id="ent_ally_wizard_001",
            name="Wizard",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 9, "y": 5},
            hp={"current": 18, "max": 18, "temp": 0},
            ac=13,
            speed={"walk": 30, "remaining": 30},
            initiative=9,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_ranged_brief_fallback",
            name="Enemy Ranged Brief Fallback",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, melee_threat.entity_id, player_target.entity_id, ally_enemy.entity_id],
            entities={
                enemy.entity_id: enemy,
                melee_threat.entity_id: melee_threat,
                player_target.entity_id: player_target,
                ally_enemy.entity_id: ally_enemy,
            },
            map=EncounterMap(
                map_id="map_enemy_ranged_brief_fallback",
                name="Ranged Fallback Map",
                description="ranged fallback test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        brief = state["current_turn_context"]["enemy_ranged_tactical_brief"]

        self.assertTrue(brief["pressure_state"]["threatened_in_melee"])
        self.assertEqual(brief["pressure_state"]["threat_source_ids"], [melee_threat.entity_id])
        self.assertTrue(brief["pressure_state"]["bloodied"])
        self.assertEqual(brief["pressure_state"]["stay_and_shoot_penalty"], "中")
        self.assertTrue(len(brief["fallback_options"]) > 0)
        self.assertTrue(brief["fallback_options"][0]["requires_disengage"])
        self.assertTrue(brief["fallback_options"][0]["breaks_all_melee_threat"])
        self.assertEqual(brief["recommended_tactic"]["action"], "disengage_and_fallback")
        self.assertEqual(brief["recommended_tactic"]["reason"], "已被贴身且状态不稳，先撤开再打")
        self.assertEqual(
            brief["recommended_tactic"]["execution_plan"][0],
            {
                "command": "use_disengage",
                "args": {
                    "encounter_id": "enc_enemy_ranged_brief_fallback",
                    "actor_id": "ent_enemy_archer_001",
                },
            },
        )
        self.assertEqual(
            brief["recommended_tactic"]["execution_plan"][1]["command"],
            "begin_move_encounter_entity",
        )

    def test_execute_omits_enemy_tactical_brief_for_short_range_non_melee_weapon(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="hand_xbow",
                name="Hand Crossbow",
                damage_formula="1d6+2",
                damage_type="piercing",
                normal_range=5,
                long_range=30,
                kind="ranged",
            )
        )

        state = execute_get_encounter_state(encounter)

        self.assertNotIn("enemy_tactical_brief", state["current_turn_context"])

    def test_execute_projects_enemy_tactical_brief_for_melee_kind_with_extended_reach(self) -> None:
        encounter = build_enemy_turn_encounter_with_weapon(
            build_test_weapon(
                weapon_id="whip",
                name="Whip",
                damage_formula="1d4+2",
                damage_type="slashing",
                normal_range=15,
                long_range=15,
                kind="melee",
            )
        )

        state = execute_get_encounter_state(encounter)

        brief = state["current_turn_context"]["enemy_tactical_brief"]
        self.assertEqual(len(brief["candidate_targets"]), 1)
        self.assertEqual(brief["candidate_targets"][0]["entity_id"], "ent_ally_player_001")


    def test_execute_enemy_tactical_brief_projects_reachable_target_via_normal_move(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 1, "y": 1},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        target = EncounterEntity(
            entity_id="ent_ally_target_001",
            name="Target",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 1},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_reachable_move",
            name="Enemy Brief Reachable Move",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, target.entity_id],
            entities={enemy.entity_id: enemy, target.entity_id: target},
            map=EncounterMap(
                map_id="map_enemy_brief_reachable_move",
                name="Reachable Move",
                description="reachable move test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]
        recommended = state["current_turn_context"]["enemy_tactical_brief"]["recommended_tactic"]

        self.assertEqual(len(reachable), 1)
        self.assertEqual(reachable[0]["entity_id"], target.entity_id)
        self.assertEqual(reachable[0]["engage_mode"], "move_and_attack")
        self.assertTrue(reachable[0]["can_attack_this_turn"])
        self.assertFalse(reachable[0]["requires_action_dash"])
        self.assertFalse(reachable[0]["requires_action_disengage"])
        self.assertFalse(reachable[0]["opportunity_attack_risk"])
        self.assertEqual(recommended["action"], "move_and_attack")
        self.assertEqual(recommended["target_entity_id"], target.entity_id)
        self.assertEqual(recommended["engage_mode"], "move_and_attack")
        self.assertEqual(recommended["reason"], "可以直接贴上目标，本回合就近战施压")

    def test_execute_enemy_tactical_brief_projects_dash_only_target(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 1, "y": 1},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        far_target = EncounterEntity(
            entity_id="ent_ally_far_target_001",
            name="Far Target",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 9, "y": 1},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_dash",
            name="Enemy Brief Dash",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, far_target.entity_id],
            entities={enemy.entity_id: enemy, far_target.entity_id: far_target},
            map=EncounterMap(
                map_id="map_enemy_brief_dash",
                name="Dash Map",
                description="dash reach test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]
        recommended = state["current_turn_context"]["enemy_tactical_brief"]["recommended_tactic"]

        self.assertEqual(len(reachable), 1)
        self.assertEqual(reachable[0]["entity_id"], far_target.entity_id)
        self.assertEqual(reachable[0]["engage_mode"], "dash_to_engage")
        self.assertFalse(reachable[0]["can_attack_this_turn"])
        self.assertTrue(reachable[0]["requires_action_dash"])
        self.assertFalse(reachable[0]["requires_action_disengage"])
        self.assertFalse(reachable[0]["opportunity_attack_risk"])
        self.assertEqual(recommended["action"], "dash_to_engage")
        self.assertEqual(recommended["target_entity_id"], far_target.entity_id)
        self.assertEqual(recommended["engage_mode"], "dash_to_engage")
        self.assertEqual(recommended["reason"], "本回合够不到，先冲上去抢近战位置")

    def test_execute_enemy_tactical_brief_marks_opportunity_attack_risk_when_leaving_reach(self) -> None:
        mover = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        blocker = EncounterEntity(
            entity_id="ent_ally_blocker_001",
            name="Blocker",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            weapons=[
                build_test_weapon(
                    weapon_id="longsword",
                    name="Longsword",
                    damage_formula="1d8+3",
                    damage_type="slashing",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
            action_economy={"reaction_used": False},
        )
        caster = EncounterEntity(
            entity_id="ent_ally_caster_001",
            name="Caster",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 9},
            hp={"current": 14, "max": 14, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
            turn_effects=[{"effect_id": "fx_conc", "effect_type": "concentration", "name": "Hold Person"}],
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_opportunity_attack_risk",
            name="Enemy Brief Opportunity Attack Risk",
            status="active",
            round=1,
            current_entity_id=mover.entity_id,
            turn_order=[mover.entity_id, blocker.entity_id, caster.entity_id],
            entities={
                mover.entity_id: mover,
                blocker.entity_id: blocker,
                caster.entity_id: caster,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_opportunity_attack_risk",
                name="Opportunity Attack Risk Map",
                description="opportunity attack risk test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]
        caster_entry = next(
            (item for item in reachable if item["entity_id"] == caster.entity_id),
            None,
        )

        self.assertIsNotNone(caster_entry)
        self.assertTrue(caster_entry["opportunity_attack_risk"])
        self.assertEqual(caster_entry["risk_sources"], [blocker.entity_id])

    def test_execute_enemy_tactical_brief_projects_disengage_to_engage_option(self) -> None:
        mover = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        blocker = EncounterEntity(
            entity_id="ent_ally_blocker_001",
            name="Blocker",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            weapons=[
                build_test_weapon(
                    weapon_id="longsword",
                    name="Longsword",
                    damage_formula="1d8+3",
                    damage_type="slashing",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
            action_economy={"reaction_used": False},
        )
        caster = EncounterEntity(
            entity_id="ent_ally_caster_001",
            name="Caster",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 9},
            hp={"current": 14, "max": 14, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
            turn_effects=[{"effect_id": "fx_conc", "effect_type": "concentration", "name": "Hold Person"}],
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_disengage_to_engage",
            name="Enemy Brief Disengage To Engage",
            status="active",
            round=1,
            current_entity_id=mover.entity_id,
            turn_order=[mover.entity_id, blocker.entity_id, caster.entity_id],
            entities={
                mover.entity_id: mover,
                blocker.entity_id: blocker,
                caster.entity_id: caster,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_disengage_to_engage",
                name="Disengage To Engage Map",
                description="disengage to engage test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]
        recommended = state["current_turn_context"]["enemy_tactical_brief"]["recommended_tactic"]
        caster_entry = next(
            (
                item
                for item in reachable
                if item["entity_id"] == caster.entity_id
                and item["engage_mode"] == "disengage_to_engage"
            ),
            None,
        )

        self.assertIsNotNone(caster_entry)
        self.assertEqual(caster_entry["engage_mode"], "disengage_to_engage")
        self.assertTrue(caster_entry["requires_action_disengage"])
        self.assertFalse(caster_entry["requires_action_dash"])
        self.assertFalse(caster_entry["can_attack_this_turn"])
        self.assertFalse(caster_entry["opportunity_attack_risk"])
        self.assertEqual(caster_entry["risk_sources"], [])
        self.assertEqual(recommended["action"], "attack")
        self.assertEqual(recommended["target_entity_id"], blocker.entity_id)
        self.assertEqual(recommended["engage_mode"], "already_in_range")
        self.assertEqual(recommended["reason"], "已经贴住目标，直接近战施压")

    def test_execute_enemy_tactical_brief_reachable_targets_returns_top_two(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 40, "max": 40, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        target_a = EncounterEntity(
            entity_id="ent_ally_target_a_001",
            name="Target A",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 7, "y": 5},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
        )
        target_b = EncounterEntity(
            entity_id="ent_ally_target_b_001",
            name="Target B",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 8, "y": 5},
            hp={"current": 18, "max": 20, "temp": 0},
            ac=13,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        target_c = EncounterEntity(
            entity_id="ent_ally_target_c_001",
            name="Target C",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 9, "y": 5},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=9,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_reachable_top_two",
            name="Enemy Brief Reachable Top Two",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, target_a.entity_id, target_b.entity_id, target_c.entity_id],
            entities={
                enemy.entity_id: enemy,
                target_a.entity_id: target_a,
                target_b.entity_id: target_b,
                target_c.entity_id: target_c,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_reachable_top_two",
                name="Reachable Top Two",
                description="reachable top two test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]

        self.assertEqual(len(reachable), 2)
        self.assertEqual(
            [item["entity_id"] for item in reachable],
            [target_a.entity_id, target_b.entity_id],
        )

    def test_execute_enemy_tactical_brief_recommended_tactic_advances_when_target_cannot_be_reached_this_turn(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 1, "y": 1},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        target = EncounterEntity(
            entity_id="ent_ally_far_target_001",
            name="Far Target",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 12, "y": 12},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_hold_position",
            name="Enemy Brief Hold Position",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, target.entity_id],
            entities={enemy.entity_id: enemy, target.entity_id: target},
            map=EncounterMap(
                map_id="map_enemy_brief_hold_position",
                name="Hold Position",
                description="hold position test",
                width=20,
                height=20,
            ),
        )

        state = execute_get_encounter_state(encounter)
        brief = state["current_turn_context"]["enemy_tactical_brief"]

        self.assertEqual(brief["candidate_targets"], [])
        self.assertEqual(len(brief["reachable_targets"]), 1)
        self.assertEqual(brief["reachable_targets"][0]["entity_id"], target.entity_id)
        self.assertEqual(brief["reachable_targets"][0]["engage_mode"], "dash_to_engage")
        self.assertFalse(brief["reachable_targets"][0]["can_attack_this_turn"])
        self.assertEqual(brief["recommended_tactic"]["action"], "dash_to_engage")
        self.assertEqual(brief["recommended_tactic"]["target_entity_id"], target.entity_id)
        self.assertEqual(brief["recommended_tactic"]["engage_mode"], "dash_to_engage")
        self.assertEqual(brief["recommended_tactic"]["reason"], "本回合够不到，先冲上去抢近战位置")
        self.assertEqual(brief["recommended_tactic"]["execution_plan"][0]["command"], "begin_move_encounter_entity")
        self.assertTrue(brief["recommended_tactic"]["execution_plan"][0]["args"]["use_dash"])

    def test_execute_enemy_tactical_brief_holds_when_cannot_move(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 1, "y": 1},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 0, "remaining": 0},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        target = EncounterEntity(
            entity_id="ent_ally_far_target_001",
            name="Far Target",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 12, "y": 12},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_hold_position_no_move",
            name="Enemy Brief Hold Position No Move",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, target.entity_id],
            entities={enemy.entity_id: enemy, target.entity_id: target},
            map=EncounterMap(
                map_id="map_enemy_brief_hold_position_no_move",
                name="Hold Position No Move",
                description="hold position when cannot move",
                width=20,
                height=20,
            ),
        )

        state = execute_get_encounter_state(encounter)
        brief = state["current_turn_context"]["enemy_tactical_brief"]

        self.assertEqual(brief["reachable_targets"], [])
        self.assertEqual(brief["recommended_tactic"]["action"], "hold_position")
        self.assertIsNone(brief["recommended_tactic"]["target_entity_id"])
        self.assertIsNone(brief["recommended_tactic"]["engage_mode"])
        self.assertEqual(brief["recommended_tactic"]["reason"], "暂时压不上去，先维持位置等待机会")

    def test_execute_enemy_tactical_brief_does_not_treat_non_melee_blocker_as_risk_source(self) -> None:
        mover = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        ranged_blocker = EncounterEntity(
            entity_id="ent_ally_blocker_001",
            name="Blocker",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            weapons=[
                build_test_weapon(
                    weapon_id="hand_crossbow",
                    name="Hand Crossbow",
                    damage_formula="1d6+3",
                    damage_type="piercing",
                    normal_range=10,
                    long_range=30,
                    kind="ranged",
                )
            ],
            action_economy={"reaction_used": False},
        )
        caster = EncounterEntity(
            entity_id="ent_ally_caster_001",
            name="Caster",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 9},
            hp={"current": 14, "max": 14, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_non_melee_risk_source",
            name="Enemy Brief Non Melee Risk Source",
            status="active",
            round=1,
            current_entity_id=mover.entity_id,
            turn_order=[mover.entity_id, ranged_blocker.entity_id, caster.entity_id],
            entities={
                mover.entity_id: mover,
                ranged_blocker.entity_id: ranged_blocker,
                caster.entity_id: caster,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_non_melee_risk_source",
                name="Non Melee Risk Source Map",
                description="non melee blocker risk test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]
        caster_entry = next((item for item in reachable if item["entity_id"] == caster.entity_id), None)

        self.assertIsNotNone(caster_entry)
        self.assertFalse(caster_entry["opportunity_attack_risk"])
        self.assertEqual(caster_entry["risk_sources"], [])

    def test_execute_enemy_tactical_brief_keeps_risky_move_and_attack_when_safe_path_only_reaches_by_dash(self) -> None:
        mover = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 0, "y": 0},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        blocker = EncounterEntity(
            entity_id="ent_ally_blocker_001",
            name="Blocker",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 0, "y": 3},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            weapons=[
                build_test_weapon(
                    weapon_id="longsword",
                    name="Longsword",
                    damage_formula="1d8+3",
                    damage_type="slashing",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
            action_economy={"reaction_used": False},
        )
        target = EncounterEntity(
            entity_id="ent_ally_target_001",
            name="Target",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 4, "y": 6},
            hp={"current": 14, "max": 14, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_risky_move_beats_safe_dash",
            name="Enemy Brief Risky Move Beats Safe Dash",
            status="active",
            round=1,
            current_entity_id=mover.entity_id,
            turn_order=[mover.entity_id, blocker.entity_id, target.entity_id],
            entities={
                mover.entity_id: mover,
                blocker.entity_id: blocker,
                target.entity_id: target,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_risky_move_beats_safe_dash",
                name="Risky Move Beats Safe Dash",
                description="risky move attack should not be swallowed by safe dash",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]

        target_move_entry = next(
            (
                item
                for item in reachable
                if item["entity_id"] == target.entity_id and item["engage_mode"] == "move_and_attack"
            ),
            None,
        )

        self.assertIsNotNone(target_move_entry)
        self.assertTrue(target_move_entry["can_attack_this_turn"])
        self.assertTrue(target_move_entry["opportunity_attack_risk"])
        self.assertEqual(target_move_entry["movement_cost_feet"], 25)
        self.assertEqual(target_move_entry["risk_sources"], [blocker.entity_id])
        self.assertFalse(
            any(item["entity_id"] == target.entity_id and item["engage_mode"] == "dash_to_engage" for item in reachable)
        )

    def test_execute_enemy_tactical_brief_does_not_add_disengage_option_when_safe_move_and_attack_exists(self) -> None:
        mover = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 0, "y": 0},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        blocker = EncounterEntity(
            entity_id="ent_ally_blocker_001",
            name="Blocker",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 0, "y": 1},
            hp={"current": 24, "max": 24, "temp": 0},
            ac=16,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            weapons=[
                build_test_weapon(
                    weapon_id="longsword",
                    name="Longsword",
                    damage_formula="1d8+3",
                    damage_type="slashing",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
            action_economy={"reaction_used": False},
        )
        target = EncounterEntity(
            entity_id="ent_ally_target_001",
            name="Target",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 1, "y": 2},
            hp={"current": 14, "max": 14, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_safe_move_no_disengage_duplicate",
            name="Enemy Brief Safe Move No Disengage Duplicate",
            status="active",
            round=1,
            current_entity_id=mover.entity_id,
            turn_order=[mover.entity_id, blocker.entity_id, target.entity_id],
            entities={
                mover.entity_id: mover,
                blocker.entity_id: blocker,
                target.entity_id: target,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_safe_move_no_disengage_duplicate",
                name="Safe Move No Disengage Duplicate",
                description="safe move should suppress disengage duplicate",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]

        target_entries = [item for item in reachable if item["entity_id"] == target.entity_id]

        self.assertEqual(len(target_entries), 1)
        self.assertEqual(target_entries[0]["engage_mode"], "move_and_attack")
        self.assertFalse(target_entries[0]["opportunity_attack_risk"])
        self.assertFalse(
            any(item["entity_id"] == target.entity_id and item["engage_mode"] == "disengage_to_engage" for item in reachable)
        )

    def test_execute_enemy_tactical_brief_reachable_targets_keep_score_as_primary_signal(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 1, "y": 1},
            hp={"current": 40, "max": 40, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=5,
                    long_range=5,
                    kind="melee",
                )
            ],
        )
        lower_value_easy_target = EncounterEntity(
            entity_id="ent_ally_near_guard_001",
            name="Near Guard",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 5, "y": 1},
            hp={"current": 30, "max": 30, "temp": 0},
            ac=13,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        higher_value_dash_target = EncounterEntity(
            entity_id="ent_ally_wounded_caster_001",
            name="Wounded Caster",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 9, "y": 1},
            hp={"current": 14, "max": 20, "temp": 0},
            ac=19,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
            turn_effects=[{"effect_id": "fx_conc", "effect_type": "concentration", "name": "Hex"}],
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_reachable_score_priority",
            name="Enemy Brief Reachable Score Priority",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, lower_value_easy_target.entity_id, higher_value_dash_target.entity_id],
            entities={
                enemy.entity_id: enemy,
                lower_value_easy_target.entity_id: lower_value_easy_target,
                higher_value_dash_target.entity_id: higher_value_dash_target,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_reachable_score_priority",
                name="Reachable Score Priority",
                description="reachable targets should stay score-first even when a higher-value target needs dash",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        reachable = state["current_turn_context"]["enemy_tactical_brief"]["reachable_targets"]
        reachable_by_id = {item["entity_id"]: item for item in reachable}

        self.assertEqual(
            [item["entity_id"] for item in reachable],
            [higher_value_dash_target.entity_id, lower_value_easy_target.entity_id],
        )
        self.assertGreater(
            reachable_by_id[higher_value_dash_target.entity_id]["score"],
            reachable_by_id[lower_value_easy_target.entity_id]["score"],
        )
        self.assertEqual(reachable[0]["engage_mode"], "dash_to_engage")
        self.assertEqual(reachable[1]["engage_mode"], "move_and_attack")

    def test_execute_enemy_tactical_brief_applies_stable_tie_break_for_equal_scores(self) -> None:
        enemy = EncounterEntity(
            entity_id="ent_enemy_brute_001",
            name="Brute",
            side="enemy",
            category="monster",
            controller="gm",
            position={"x": 5, "y": 5},
            hp={"current": 40, "max": 40, "temp": 0},
            ac=15,
            speed={"walk": 30, "remaining": 30},
            initiative=12,
            weapons=[
                build_test_weapon(
                    weapon_id="mace",
                    name="Mace",
                    damage_formula="1d6+3",
                    damage_type="bludgeoning",
                    normal_range=10,
                    long_range=10,
                    kind="melee",
                )
            ],
        )
        farther = EncounterEntity(
            entity_id="ent_ally_farther_002",
            name="Farther",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 7, "y": 5},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=10,
        )
        closer = EncounterEntity(
            entity_id="ent_ally_closer_001",
            name="Closer",
            side="ally",
            category="pc",
            controller="player",
            position={"x": 6, "y": 5},
            hp={"current": 20, "max": 20, "temp": 0},
            ac=14,
            speed={"walk": 30, "remaining": 30},
            initiative=11,
        )
        encounter = Encounter(
            encounter_id="enc_enemy_brief_tie_break",
            name="Enemy Brief Tie Break",
            status="active",
            round=1,
            current_entity_id=enemy.entity_id,
            turn_order=[enemy.entity_id, farther.entity_id, closer.entity_id],
            entities={
                enemy.entity_id: enemy,
                farther.entity_id: farther,
                closer.entity_id: closer,
            },
            map=EncounterMap(
                map_id="map_enemy_brief_tie_break",
                name="Tie Break Map",
                description="tie-break test",
                width=12,
                height=12,
            ),
        )

        state = execute_get_encounter_state(encounter)
        candidates = state["current_turn_context"]["enemy_tactical_brief"]["candidate_targets"]

        self.assertEqual(candidates[0]["score"], candidates[1]["score"])
        self.assertEqual([item["entity_id"] for item in candidates], [closer.entity_id, farther.entity_id])


if __name__ == "__main__":
    unittest.main()
