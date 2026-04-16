"""Reaction definition repository unit tests."""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import ReactionDefinitionRepository


class ReactionDefinitionRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = ReactionDefinitionRepository()

    def test_get_returns_registered_definition(self) -> None:
        definition = self.repository.get("shield")

        self.assertEqual(definition["reaction_type"], "shield")
        self.assertEqual(definition["template_type"], "targeted_defense_rewrite")

    def test_get_unknown_reaction_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.repository.get("unknown_reaction_type")

    def test_list_by_trigger_type_filters_definitions(self) -> None:
        attack_defs = self.repository.list_by_trigger_type("attack_declared")

        self.assertTrue(len(attack_defs) >= 1)
        self.assertTrue(
            all(definition.get("trigger_type") == "attack_declared" for definition in attack_defs)
        )
