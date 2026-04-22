from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.services.characters.player_character_builder import PlayerCharacterBuilder


class PlayerCharacterBuilderTests(unittest.TestCase):
    def test_build_from_character_build_derives_core_entity_fields(self) -> None:
        builder = PlayerCharacterBuilder()
        template = {
            "entity_def_id": "pc_arcanist_lv5",
            "name": "伊兰",
            "side": "ally",
            "category": "pc",
            "controller": "player",
            "position": {"x": 3, "y": 4},
            "hp": {"current": 27, "max": 27, "temp": 0},
            "ac": 14,
            "speed": {"walk": 30, "remaining": 30},
            "initiative": 0,
            "size": "medium",
            "source_ref": {"entity_type": "humanoid"},
            "ability_scores": {"str": 8, "dex": 14, "con": 14, "int": 18, "wis": 12, "cha": 10},
            "skill_training": {"arcana": "expertise", "investigation": "proficient"},
            "weapons": [{"weapon_id": "dagger", "name": "匕首"}],
            "spells": [
                {"spell_id": "fireball", "name": "Fireball", "level": 3},
                {"spell_id": "shield", "name": "Shield", "level": 1},
                {"spell_id": "light", "name": "Light", "level": 0},
            ],
            "character_build": {
                "classes": [{"class_id": "wizard", "level": 5}],
                "initial_class_name": "wizard",
            },
        }

        entity = builder.build(
            template=template,
            entity_id="ent_pc_arcanist_001",
        )

        self.assertEqual(entity.entity_id, "ent_pc_arcanist_001")
        self.assertEqual(entity.initial_class_name, "wizard")
        self.assertEqual(entity.source_ref["class_name"], "wizard")
        self.assertEqual(entity.source_ref["level"], 5)
        self.assertEqual(entity.source_ref["spellcasting_ability"], "int")
        self.assertEqual(entity.ability_mods["int"], 4)
        self.assertEqual(entity.proficiency_bonus, 3)
        self.assertEqual(entity.save_proficiencies, ["int", "wis"])
        self.assertEqual(entity.class_features["wizard"]["level"], 5)
        self.assertEqual(entity.class_features["wizard"]["spell_preparation_mode"], "long_rest_any")
        self.assertEqual(entity.class_features["wizard"]["prepared_spells"], ["fireball", "shield"])
        self.assertEqual(entity.resources["spell_slots"]["3"]["max"], 2)
        self.assertEqual(entity.spells[0]["casting_class"], "wizard")
        self.assertEqual(entity.skill_modifiers["arcana"], 10)
        self.assertEqual(entity.skill_modifiers["investigation"], 7)

    def test_build_allows_runtime_override_to_replace_primary_class(self) -> None:
        builder = PlayerCharacterBuilder()
        template = {
            "entity_def_id": "pc_preview_actor",
            "name": "米伦",
            "side": "ally",
            "category": "pc",
            "controller": "player",
            "position": {"x": 5, "y": 5},
            "hp": {"current": 22, "max": 27, "temp": 0},
            "ac": 16,
            "speed": {"walk": 40, "remaining": 40},
            "initiative": 0,
            "size": "medium",
            "source_ref": {"class_name": "monk", "level": 5, "entity_type": "humanoid"},
            "ability_scores": {"str": 8, "dex": 17, "con": 14, "int": 8, "wis": 16, "cha": 10},
            "class_features": {"monk": {"level": 5}},
            "spells": [],
            "character_build": {
                "classes": [{"class_id": "wizard", "level": 5}],
                "initial_class_name": "wizard",
            },
        }

        entity = builder.build(template=template, entity_id="ent_preview_001")

        self.assertEqual(entity.source_ref["class_name"], "monk")
        self.assertEqual(entity.class_features["monk"]["level"], 5)
        self.assertNotIn("wizard", entity.class_features)
        self.assertEqual(entity.initial_class_name, "wizard")
        self.assertNotIn("spellcasting_ability", entity.source_ref)

    def test_build_initializes_fighter_runtime_from_character_build(self) -> None:
        builder = PlayerCharacterBuilder()
        template = {
            "entity_def_id": "pc_fighter_lv13",
            "name": "萨布尔",
            "side": "ally",
            "category": "pc",
            "controller": "player",
            "position": {"x": 1, "y": 1},
            "hp": {"current": 104, "max": 104, "temp": 0},
            "ac": 18,
            "speed": {"walk": 30, "remaining": 30},
            "initiative": 0,
            "size": "medium",
            "ability_scores": {"str": 18, "dex": 14, "con": 16, "int": 10, "wis": 12, "cha": 8},
            "character_build": {
                "classes": [{"class_id": "fighter", "level": 13}],
                "initial_class_name": "fighter",
            },
        }

        entity = builder.build(template=template, entity_id="ent_fighter_001")

        fighter = entity.class_features["fighter"]
        self.assertEqual(entity.save_proficiencies, ["str", "con"])
        self.assertEqual(fighter["fighter_level"], 13)
        self.assertEqual(fighter["second_wind"]["max_uses"], 3)
        self.assertEqual(fighter["action_surge"]["max_uses"], 1)
        self.assertEqual(fighter["indomitable"]["max_uses"], 2)
        self.assertTrue(fighter["tactical_master_enabled"])
        self.assertTrue(fighter["studied_attacks_feature"]["enabled"])

    def test_build_initializes_barbarian_runtime_from_character_build(self) -> None:
        builder = PlayerCharacterBuilder()
        template = {
            "entity_def_id": "pc_barbarian_lv15",
            "name": "格罗姆",
            "side": "ally",
            "category": "pc",
            "controller": "player",
            "position": {"x": 1, "y": 1},
            "hp": {"current": 142, "max": 142, "temp": 0},
            "ac": 17,
            "speed": {"walk": 40, "remaining": 40},
            "initiative": 0,
            "size": "medium",
            "ability_scores": {"str": 20, "dex": 14, "con": 18, "int": 8, "wis": 12, "cha": 10},
            "character_build": {
                "classes": [{"class_id": "barbarian", "level": 15}],
                "initial_class_name": "barbarian",
            },
        }

        entity = builder.build(template=template, entity_id="ent_barbarian_001")

        barbarian = entity.class_features["barbarian"]
        self.assertEqual(entity.save_proficiencies, ["str", "con"])
        self.assertEqual(barbarian["rage"]["max"], 5)
        self.assertTrue(barbarian["rage"]["persistent_rage"])
        self.assertEqual(barbarian["weapon_mastery_count"], 4)
        self.assertTrue(barbarian["fast_movement"]["enabled"])
        self.assertTrue(barbarian["brutal_strike"]["enabled"])
        self.assertTrue(barbarian["relentless_rage"]["enabled"])


if __name__ == "__main__":
    unittest.main()
