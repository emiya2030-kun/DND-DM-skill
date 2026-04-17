"""职业熟练模板仓储测试：覆盖静态知识库读取。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import ClassProficiencyDefinitionRepository


class ClassProficiencyDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_fighter_proficiency_definition(self) -> None:
        repo = ClassProficiencyDefinitionRepository(
            Path(PROJECT_ROOT / "data/knowledge/class_proficiency_definitions.json")
        )

        definition = repo.get("fighter")

        self.assertIsNotNone(definition)
        self.assertEqual(definition["weapon_proficiencies"], ["simple", "martial"])
        self.assertEqual(definition["armor_training"], ["light", "medium", "heavy", "shield"])
        self.assertEqual(definition["save_proficiencies"], ["str", "con"])

    def test_get_returns_rogue_property_based_weapon_entries(self) -> None:
        repo = ClassProficiencyDefinitionRepository(
            Path(PROJECT_ROOT / "data/knowledge/class_proficiency_definitions.json")
        )

        definition = repo.get("rogue")

        self.assertIsNotNone(definition)
        self.assertIn("simple", definition["weapon_proficiencies"])
        self.assertIn("martial_finesse_or_light", definition["weapon_proficiencies"])
        self.assertEqual(definition["armor_training"], ["light"])
        self.assertEqual(definition["save_proficiencies"], ["dex", "int"])


if __name__ == "__main__":
    unittest.main()
