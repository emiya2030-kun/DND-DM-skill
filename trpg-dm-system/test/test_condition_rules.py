import unittest

from tools.services.combat.rules.conditions import ConditionRuntime, parse_condition


class ConditionRulesTest(unittest.TestCase):
    def test_parse_plain_condition(self):
        condition = parse_condition("blinded")
        self.assertEqual(condition.name, "blinded")
        self.assertIsNone(condition.source)
        self.assertIsNone(condition.level)

    def test_parse_condition_with_source(self):
        condition = parse_condition("frightened:ent_enemy_dragon_001")
        self.assertEqual(condition.name, "frightened")
        self.assertEqual(condition.source, "ent_enemy_dragon_001")
        self.assertIsNone(condition.level)

    def test_parse_exhaustion(self):
        condition = parse_condition("exhaustion:3")
        self.assertEqual(condition.name, "exhaustion")
        self.assertEqual(condition.level, 3)
        self.assertIsNone(condition.source)

    def test_parse_invalid_strings_raise(self):
        with self.assertRaises(ValueError):
            parse_condition("")
        with self.assertRaises(ValueError):
            parse_condition("exhaustion:")
        with self.assertRaises(ValueError):
            parse_condition("exhaustion:bad")
        with self.assertRaises(ValueError):
            parse_condition("exhaustion:0")
        with self.assertRaises(ValueError):
            parse_condition("exhaustion:10")
        with self.assertRaises(ValueError):
            parse_condition("frightened:")
        with self.assertRaises(ValueError):
            parse_condition(":")

    def test_condition_runtime_helpers(self):
        runtime = ConditionRuntime(
            ["paralyzed", "frightened:owner", "exhaustion:2"]
        )
        self.assertTrue(runtime.has("paralyzed"))
        self.assertFalse(runtime.has("charmed"))
        self.assertTrue(runtime.has_from_source("frightened", "owner"))
        self.assertFalse(runtime.has_from_source("frightened", "other"))
        self.assertEqual(runtime.exhaustion_level(), 2)
        self.assertEqual(runtime.get_d20_penalty(), 4)
        self.assertEqual(runtime.get_speed_penalty_feet(), 10)

    def test_runtime_without_exhaustion(self):
        runtime = ConditionRuntime(["blinded"])
        self.assertEqual(runtime.exhaustion_level(), 0)
        self.assertEqual(runtime.get_d20_penalty(), 0)
        self.assertEqual(runtime.get_speed_penalty_feet(), 0)
