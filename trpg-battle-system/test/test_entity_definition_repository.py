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
        self.assertEqual(entity["ability_mods"]["dex"], 3)
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
            self.assertIn("ability_mods", entity)
            self.assertIn("weapons", entity)
            self.assertIn("spells", entity)

    def test_spellcasting_and_humanoid_runtime_metadata_exist_for_demo_entities(self) -> None:
        repository = EntityDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/entity_definitions.json"))

        miren = repository.get("pc_miren")
        self.assertIsNotNone(miren)
        self.assertEqual(miren["source_ref"]["spellcasting_ability"], "int")
        self.assertEqual(miren["source_ref"]["entity_type"], "humanoid")
        self.assertEqual(miren["resources"]["spell_slots"]["2"]["remaining"], 3)

        marauder = repository.get("monster_sabur")
        self.assertIsNotNone(marauder)
        self.assertEqual(marauder["source_ref"]["entity_type"], "humanoid")


if __name__ == "__main__":
    unittest.main()
