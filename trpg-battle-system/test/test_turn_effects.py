from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.services.encounter.turns.turn_effects import resolve_turn_effects


def build_entity(
    entity_id: str,
    *,
    name: str,
    initiative: int,
    hp_current: int = 10,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": hp_current, "max": 10, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=initiative,
        ability_scores={"wis": 14},
        ability_mods={"wis": 2},
        proficiency_bonus=3,
        save_proficiencies=["wis"],
    )


def build_encounter_with_turn_effect_target() -> Encounter:
    caster = build_entity("ent_caster", name="吸血鬼法师", initiative=15)
    target = build_entity("ent_target", name="米伦", initiative=12)
    return Encounter(
        encounter_id="enc_turn_effects_test",
        name="Turn Effects Test",
        status="active",
        round=1,
        current_entity_id=target.entity_id,
        turn_order=[caster.entity_id, target.entity_id],
        entities={caster.entity_id: caster, target.entity_id: target},
        map=EncounterMap(
            map_id="map_turn_effects_test",
            name="Turn Effects Test Map",
            description="A map used by turn effect tests.",
            width=10,
            height=10,
        ),
    )


def build_concentration_spell_instance(caster_entity_id: str, target_id: str) -> dict[str, object]:
    return {
        "instance_id": "spell_inst_001",
        "spell_id": "hex",
        "spell_name": "Hex",
        "caster_entity_id": caster_entity_id,
        "caster_name": "吸血鬼法师",
        "cast_level": 1,
        "concentration": {"required": True, "active": True},
        "lifecycle": {"status": "active"},
        "targets": [
            {
                "entity_id": target_id,
                "applied_conditions": ["marked"],
                "turn_effect_ids": ["effect_marked_001"],
            }
        ],
    }


class TurnEffectsTests(unittest.TestCase):
    def test_resolve_turn_effects_removes_condition_and_effect_on_successful_end_of_turn_save(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.conditions = ["paralyzed"]
        target.turn_effects = [
            {
                "effect_id": "effect_hold_person_001",
                "name": "定身术持续效果",
                "source_entity_id": "ent_caster",
                "trigger": "end_of_turn",
                "save": {"ability": "wis", "dc": 15, "on_success_remove_effect": True},
                "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": ["paralyzed"]},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": False,
            }
        ]

        result = resolve_turn_effects(
            encounter=encounter,
            entity_id="ent_target",
            trigger="end_of_turn",
            save_roll_overrides={"effect_hold_person_001": 12},
        )

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["save"]["success"])
        self.assertNotIn("paralyzed", target.conditions)
        self.assertEqual(target.turn_effects, [])

    def test_resolve_turn_effects_applies_damage_and_removes_one_shot_effect(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.turn_effects = [
            {
                "effect_id": "effect_acid_001",
                "name": "强酸残留",
                "source_entity_id": "ent_caster",
                "trigger": "end_of_turn",
                "save": None,
                "on_trigger": {
                    "damage_parts": [{"source": "effect:acid", "formula": "2d4", "damage_type": "acid"}],
                    "apply_conditions": [],
                    "remove_conditions": [],
                },
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": True,
            }
        ]

        result = resolve_turn_effects(
            encounter=encounter,
            entity_id="ent_target",
            trigger="end_of_turn",
            damage_roll_overrides={"effect:acid": {"rolls": [4, 3]}},
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["trigger_damage_resolution"]["total_damage"], 7)
        self.assertEqual(target.hp["current"], 3)
        self.assertEqual(target.turn_effects, [])

    def test_resolve_turn_effects_keeps_effect_when_end_of_turn_save_fails(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.conditions = ["paralyzed"]
        target.turn_effects = [
            {
                "effect_id": "effect_hold_person_001",
                "name": "定身术持续效果",
                "source_entity_id": "ent_caster",
                "trigger": "end_of_turn",
                "save": {"ability": "wis", "dc": 15, "on_success_remove_effect": True},
                "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": ["paralyzed"]},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": False,
            }
        ]

        result = resolve_turn_effects(
            encounter=encounter,
            entity_id="ent_target",
            trigger="end_of_turn",
            save_roll_overrides={"effect_hold_person_001": 5},
        )

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["save"]["success"])
        self.assertIn("paralyzed", target.conditions)
        self.assertEqual(len(target.turn_effects), 1)

    def test_resolve_turn_effects_rolls_runtime_d20_when_save_override_missing(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.conditions = ["paralyzed"]
        target.turn_effects = [
            {
                "effect_id": "effect_hold_person_001",
                "name": "定身术持续效果",
                "source_entity_id": "ent_caster",
                "trigger": "end_of_turn",
                "save": {"ability": "wis", "dc": 15, "on_success_remove_effect": True},
                "on_trigger": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": ["paralyzed"]},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": False,
            }
        ]

        with patch("tools.services.encounter.turns.turn_effects.random.randint", return_value=4):
            result = resolve_turn_effects(
                encounter=encounter,
                entity_id="ent_target",
                trigger="end_of_turn",
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["save"]["base_roll"], 4)
        self.assertFalse(result[0]["save"]["success"])
        self.assertIn("paralyzed", target.conditions)
        self.assertEqual(len(target.turn_effects), 1)

    def test_resolve_turn_effects_rolls_runtime_damage_when_damage_override_missing(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.turn_effects = [
            {
                "effect_id": "effect_acid_001",
                "name": "强酸残留",
                "source_entity_id": "ent_caster",
                "trigger": "end_of_turn",
                "save": None,
                "on_trigger": {
                    "damage_parts": [{"source": "effect:acid", "formula": "2d4", "damage_type": "acid"}],
                    "apply_conditions": [],
                    "remove_conditions": [],
                },
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": True,
            }
        ]

        with patch(
            "tools.services.encounter.turns.turn_effects.random.randint",
            side_effect=[4, 3],
        ):
            result = resolve_turn_effects(
                encounter=encounter,
                entity_id="ent_target",
                trigger="end_of_turn",
            )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["trigger_damage_resolution"]["total_damage"], 7)
        self.assertEqual(target.hp["current"], 3)

    def test_resolve_turn_effects_drops_pc_to_zero_and_breaks_concentration(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.hp["current"] = 3
        target.category = "pc"
        target.combat_flags["is_concentrating"] = True
        target.conditions = ["marked"]
        target.turn_effects = [
            {
                "effect_id": "effect_fire_001",
                "name": "燃烧",
                "source_entity_id": "ent_caster",
                "trigger": "end_of_turn",
                "save": None,
                "on_trigger": {
                    "damage_parts": [{"source": "effect:fire", "formula": "1d4", "damage_type": "fire"}],
                    "apply_conditions": [],
                    "remove_conditions": [],
                },
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": True,
            },
            {
                "effect_id": "effect_marked_001",
                "effect_type": "spell_mark",
            },
        ]
        encounter.spell_instances = [build_concentration_spell_instance("ent_target", "ent_target")]

        result = resolve_turn_effects(
            encounter=encounter,
            entity_id="ent_target",
            trigger="end_of_turn",
            damage_roll_overrides={"effect:fire": {"rolls": [4]}},
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(target.hp["current"], 0)
        self.assertIn("unconscious", target.conditions)
        self.assertEqual(target.combat_flags["death_saves"], {"successes": 0, "failures": 0})
        self.assertFalse(target.combat_flags["is_dead"])
        self.assertFalse(target.combat_flags.get("is_concentrating", True))
        self.assertEqual(target.turn_effects, [])
        self.assertFalse(encounter.spell_instances[0]["concentration"]["active"])

    def test_resolve_turn_effects_adds_death_save_failure_when_zero_hp_target_takes_damage(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.category = "pc"
        target.hp["current"] = 0
        target.conditions = ["unconscious"]
        target.combat_flags["death_saves"] = {"successes": 1, "failures": 1}
        target.combat_flags["is_dead"] = False
        target.turn_effects = [
            {
                "effect_id": "effect_fire_001",
                "name": "燃烧",
                "source_entity_id": "ent_caster",
                "trigger": "start_of_turn",
                "save": None,
                "on_trigger": {
                    "damage_parts": [{"source": "effect:fire", "formula": "1d4", "damage_type": "fire"}],
                    "apply_conditions": [],
                    "remove_conditions": [],
                },
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": True,
            }
        ]

        result = resolve_turn_effects(
            encounter=encounter,
            entity_id="ent_target",
            trigger="start_of_turn",
            damage_roll_overrides={"effect:fire": {"rolls": [2]}},
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(target.combat_flags["death_saves"]["successes"], 1)
        self.assertEqual(target.combat_flags["death_saves"]["failures"], 2)
        self.assertFalse(target.combat_flags["is_dead"])

    def test_resolve_turn_effects_removes_monster_and_leaves_remains_at_zero_hp(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.category = "monster"
        target.side = "enemy"
        target.position = {"x": 4, "y": 3}
        target.turn_effects = [
            {
                "effect_id": "effect_fire_001",
                "name": "燃烧",
                "source_entity_id": "ent_caster",
                "trigger": "end_of_turn",
                "save": None,
                "on_trigger": {
                    "damage_parts": [{"source": "effect:fire", "formula": "3d4", "damage_type": "fire"}],
                    "apply_conditions": [],
                    "remove_conditions": [],
                },
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": True,
            }
        ]

        result = resolve_turn_effects(
            encounter=encounter,
            entity_id="ent_target",
            trigger="end_of_turn",
            damage_roll_overrides={"effect:fire": {"rolls": [4, 4, 4]}},
        )

        self.assertEqual(len(result), 1)
        self.assertNotIn("ent_target", encounter.entities)
        self.assertNotIn("ent_target", encounter.turn_order)
        self.assertEqual(encounter.map.remains[0]["icon"], "💀")
        self.assertEqual(encounter.map.remains[0]["position"], {"x": 4, "y": 3})

    def test_resolve_turn_effects_removes_summon_without_remains_at_zero_hp(self) -> None:
        encounter = build_encounter_with_turn_effect_target()
        target = encounter.entities["ent_target"]
        target.category = "summon"
        target.position = {"x": 6, "y": 2}
        target.turn_effects = [
            {
                "effect_id": "effect_fire_001",
                "name": "燃烧",
                "source_entity_id": "ent_caster",
                "trigger": "start_of_turn",
                "save": None,
                "on_trigger": {
                    "damage_parts": [{"source": "effect:fire", "formula": "3d4", "damage_type": "fire"}],
                    "apply_conditions": [],
                    "remove_conditions": [],
                },
                "on_save_success": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "on_save_failure": {"damage_parts": [], "apply_conditions": [], "remove_conditions": []},
                "remove_after_trigger": True,
            }
        ]

        result = resolve_turn_effects(
            encounter=encounter,
            entity_id="ent_target",
            trigger="start_of_turn",
            damage_roll_overrides={"effect:fire": {"rolls": [4, 4, 4]}},
        )

        self.assertEqual(len(result), 1)
        self.assertNotIn("ent_target", encounter.entities)
        self.assertEqual(encounter.map.remains, [])
