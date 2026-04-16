"""区域模板仓储测试：覆盖全局知识库读取。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import ZoneDefinitionRepository


class ZoneDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_zone_definition_by_id(self) -> None:
        repo = ZoneDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/zone_definitions.json"))

        zone = repo.get("fire_burn_area")

        self.assertIsNotNone(zone)
        self.assertEqual(zone["id"], "fire_burn_area")
        self.assertEqual(zone["runtime"]["triggers"][0]["timing"], "enter")

    def test_get_returns_none_for_unknown_zone(self) -> None:
        repo = ZoneDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/zone_definitions.json"))

        self.assertIsNone(repo.get("missing_zone"))

    def test_templates_expose_shared_core_sections(self) -> None:
        repo = ZoneDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/zone_definitions.json"))

        for zone_id in ("fire_burn_area", "poison_mist_area", "frost_slow_area"):
            zone = repo.get(zone_id)
            self.assertIsNotNone(zone)
            self.assertIn("id", zone)
            self.assertIn("name", zone)
            self.assertIn("type", zone)
            self.assertIn("note", zone)
            self.assertIn("runtime", zone)
            self.assertIn("localization", zone)

    def test_fire_zone_uses_damage_and_save_template(self) -> None:
        repo = ZoneDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/zone_definitions.json"))

        zone = repo.get("fire_burn_area")

        self.assertIsNotNone(zone)
        self.assertTrue(zone["runtime"]["movement_modifier"]["treat_as_difficult_terrain"])
        self.assertEqual(zone["runtime"]["triggers"][1]["save"]["ability"], "dex")
        self.assertEqual(zone["runtime"]["triggers"][1]["on_save_failure"]["damage_parts"][0]["formula"], "2d6")

    def test_poison_and_frost_templates_cover_condition_and_terrain_cases(self) -> None:
        repo = ZoneDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/zone_definitions.json"))

        poison_zone = repo.get("poison_mist_area")
        frost_zone = repo.get("frost_slow_area")

        self.assertIsNotNone(poison_zone)
        self.assertIsNotNone(frost_zone)
        self.assertEqual(
            poison_zone["runtime"]["triggers"][0]["on_save_failure"]["apply_conditions"],
            ["poisoned"],
        )
        self.assertTrue(frost_zone["runtime"]["movement_modifier"]["treat_as_difficult_terrain"])
        self.assertEqual(
            frost_zone["runtime"]["triggers"][0]["on_save_failure"]["apply_conditions"],
            ["prone"],
        )


if __name__ == "__main__":
    unittest.main()
