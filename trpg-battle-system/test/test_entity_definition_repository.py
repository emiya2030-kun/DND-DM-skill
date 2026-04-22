from __future__ import annotations

"""实体模板仓储测试。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import EntityDefinitionRepository


class EntityDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_entity_definition_by_id(self) -> None:
        repository = EntityDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/entity_definitions.json"))

        entity = repository.get("pc_miren")

        self.assertIsNotNone(entity)
        self.assertEqual(entity["name"], "米伦")
        self.assertEqual(entity["character_build"]["classes"][0]["class_id"], "wizard")
        self.assertEqual(entity["skill_training"]["arcana"], "proficient")
        self.assertEqual(entity["spells"][0]["spell_id"], "fireball")

    def test_get_returns_none_for_unknown_template(self) -> None:
        repository = EntityDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/entity_definitions.json"))

        self.assertIsNone(repository.get("missing_entity"))

    def test_templates_expose_core_encounter_entity_fields(self) -> None:
        repository = EntityDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/entity_definitions.json"))

        for template_id in ("pc_miren", "pc_sabur", "monster_sabur", "npc_companion_guard"):
            entity = repository.get(template_id)
            self.assertIsNotNone(entity)
            self.assertIn("entity_def_id", entity)
            self.assertIn("name", entity)
            self.assertIn("side", entity)
            self.assertIn("category", entity)
            self.assertIn("controller", entity)
            self.assertIn("hp", entity)
            self.assertIn("ac", entity)
            self.assertIn("speed", entity)
            self.assertIn("ability_scores", entity)
            self.assertTrue("ability_mods" in entity or "character_build" in entity)
            self.assertIn("weapons", entity)
            self.assertIn("spells", entity)

    def test_pc_templates_expose_character_build_metadata(self) -> None:
        repository = EntityDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/entity_definitions.json"))

        miren = repository.get("pc_miren")
        self.assertIsNotNone(miren)
        self.assertEqual(miren["character_build"]["initial_class_name"], "wizard")
        self.assertEqual(miren["source_ref"]["entity_type"], "humanoid")
        self.assertNotIn("spellcasting_ability", miren["source_ref"])
        self.assertNotIn("ability_mods", miren)
        self.assertNotIn("proficiency_bonus", miren)
        self.assertNotIn("save_proficiencies", miren)
        self.assertNotIn("skill_modifiers", miren)
        self.assertEqual(miren["skill_training"]["arcana"], "proficient")

        sabur = repository.get("pc_sabur")
        self.assertIsNotNone(sabur)
        self.assertEqual(sabur["character_build"]["initial_class_name"], "ranger")
        self.assertEqual(sabur["source_ref"]["entity_type"], "humanoid")
        self.assertNotIn("ability_mods", sabur)
        self.assertNotIn("proficiency_bonus", sabur)
        self.assertNotIn("save_proficiencies", sabur)
        self.assertNotIn("skill_modifiers", sabur)
        self.assertEqual(sabur["skill_training"]["perception"], "proficient")

    def test_monster_template_keeps_runtime_metadata_shape(self) -> None:
        repository = EntityDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/entity_definitions.json"))

        marauder = repository.get("monster_sabur")
        self.assertIsNotNone(marauder)
        self.assertEqual(marauder["source_ref"]["entity_type"], "humanoid")

    def test_wight_template_exposes_llm_readable_combat_metadata(self) -> None:
        repository = EntityDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/entity_definitions.json"))

        wight = repository.get("monster_wight")

        self.assertIsNotNone(wight)
        assert wight is not None
        self.assertEqual(wight["name"], "尸妖")
        self.assertEqual(wight["source_ref"]["entity_type"], "undead")
        self.assertEqual(wight["source_ref"]["alignment"], "neutral_evil")
        self.assertEqual(wight["source_ref"]["equipment"], ["镶钉皮甲"])
        self.assertEqual(wight["source_ref"]["traits_metadata"][0]["name_zh"], "日照敏感")
        self.assertIn("阳光下", wight["source_ref"]["traits_metadata"][0]["summary"])
        actions = wight["source_ref"]["actions_metadata"]
        action_ids = {action["action_id"] for action in actions}
        self.assertEqual(action_ids, {"multiattack", "necrotic_sword", "necrotic_bow", "life_drain"})
        multiattack = next(action for action in actions if action["action_id"] == "multiattack")
        self.assertEqual(
            [sequence["sequence_id"] for sequence in multiattack["multiattack_sequences"]],
            ["double_sword", "double_bow", "life_drain_plus_sword"],
        )
        self.assertEqual(
            multiattack["multiattack_sequences"][2]["steps"],
            [
                {"type": "special_action", "action_id": "life_drain"},
                {"type": "weapon", "weapon_id": "necrotic_sword"},
            ],
        )
        self.assertEqual(wight["source_ref"]["bonus_actions_metadata"], [])
        self.assertEqual(wight["source_ref"]["reactions_metadata"], [])

    def test_vampire_template_exposes_structured_action_schema(self) -> None:
        repository = EntityDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/entity_definitions.json"))

        vampire = repository.get("monster_vampire")

        self.assertIsNotNone(vampire)
        assert vampire is not None
        self.assertEqual(vampire["name"], "吸血鬼")
        self.assertEqual(vampire["source_ref"]["entity_type"], "undead")
        self.assertEqual(
            vampire["source_ref"]["combat_profile"]["resources"]["legendary_actions"]["max"],
            3,
        )
        multiattack = next(
            action for action in vampire["source_ref"]["actions_metadata"] if action["action_id"] == "multiattack"
        )
        self.assertEqual(multiattack["availability"]["forms_any_of"], ["vampire"])
        self.assertEqual(multiattack["execution_steps"][0]["weapon_id"], "grave_strike")
        self.assertEqual(multiattack["execution_steps"][0]["repeat"], 2)
        bite = next(action for action in vampire["source_ref"]["actions_metadata"] if action["action_id"] == "bite")
        self.assertTrue(bite["targeting"]["allow_any_of_filters"])
        self.assertIn("grappled_by_self", bite["targeting"]["target_filters"])
        charm = vampire["source_ref"]["bonus_actions_metadata"][0]
        self.assertEqual(charm["bonus_action_id"], "charm")
        self.assertEqual(charm["resource_cost"]["recharge"], "5_6")
        legendary = vampire["source_ref"]["legendary_actions_metadata"][0]
        self.assertEqual(legendary["legendary_action_id"], "beguile")
        self.assertEqual(legendary["resource_cost"]["legendary_actions"], 1)


if __name__ == "__main__":
    unittest.main()
