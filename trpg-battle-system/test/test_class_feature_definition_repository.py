"""职业特性模板仓储测试：覆盖静态知识库读取。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import ClassFeatureDefinitionRepository


class ClassFeatureDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_fighter_second_wind_definition(self) -> None:
        repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))

        feature = repo.get("fighter.second_wind")

        self.assertIsNotNone(feature)
        self.assertEqual(feature["template_type"], "activated_heal")
        self.assertEqual(feature["activation"], "bonus_action")

    def test_extra_attack_definition_marks_non_stacking_rule(self) -> None:
        repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))

        feature = repo.get("fighter.extra_attack")

        self.assertIsNotNone(feature)
        self.assertEqual(feature["special_rules"]["stacking"], "take_highest_only")

    def test_tactical_shift_binds_to_second_wind(self) -> None:
        repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))

        feature = repo.get("fighter.tactical_shift")

        self.assertIsNotNone(feature)
        self.assertEqual(feature["resource_model"]["linked_to_feature"], "fighter.second_wind")
        self.assertEqual(feature["trigger"]["feature_id"], "fighter.second_wind")

    def test_get_returns_rogue_sneak_attack_definition(self) -> None:
        repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))

        feature = repo.get("rogue.sneak_attack")

        self.assertIsNotNone(feature)
        self.assertEqual(feature["template_type"], "damage_rider_once_per_turn")
        self.assertEqual(feature["activation"], "passive")

    def test_get_returns_monk_stunning_strike_definition(self) -> None:
        repo = ClassFeatureDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/class_feature_definitions.json"))

        feature = repo.get("monk.stunning_strike")

        self.assertIsNotNone(feature)
        self.assertEqual(feature["template_type"], "save_on_hit_control")
        self.assertEqual(feature["resource_model"]["cost"], {"focus_points": 1})
