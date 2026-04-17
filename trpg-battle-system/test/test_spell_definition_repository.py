"""法术模板仓储测试：覆盖全局知识库读取。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.repositories import SpellDefinitionRepository


class SpellDefinitionRepositoryTests(unittest.TestCase):
    def test_get_returns_spell_definition_by_id(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        spell = repo.get("fireball")

        self.assertIsNotNone(spell)
        self.assertEqual(spell["id"], "fireball")
        self.assertEqual(spell["on_cast"]["on_failed_save"]["damage_parts"][0]["formula"], "8d6")

    def test_get_returns_none_for_unknown_spell(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        self.assertIsNone(repo.get("missing_spell"))

    def test_templates_expose_shared_core_sections(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        for spell_id in ("fireball", "hold_person", "shield", "counterspell", "hex", "hunters_mark", "eldritch_blast"):
            spell = repo.get(spell_id)
            self.assertIsNotNone(spell)
            self.assertIn("base", spell)
            self.assertIn("targeting", spell)
            self.assertIn("resolution", spell)
            self.assertIn("on_cast", spell)
            self.assertIn("effect_templates", spell)
            self.assertIn("scaling", spell)
            self.assertIn("localization", spell)
            self.assertIn("usage_contexts", spell)
            self.assertIn("runtime_support", spell)

    def test_fireball_and_hold_person_templates_expose_task2_fields(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        fireball = repo.get("fireball")
        hold_person = repo.get("hold_person")

        self.assertIsNotNone(fireball)
        self.assertEqual(fireball["resolution"]["activation"], "action")
        self.assertIn("base_slot_level", fireball["scaling"]["slot_level_bonus"])
        self.assertEqual(
            fireball["scaling"]["slot_level_bonus"]["additional_damage_parts"][0]["formula_per_extra_level"],
            "1d6",
        )

        self.assertIsNotNone(hold_person)
        self.assertEqual(hold_person["resolution"]["activation"], "action")
        self.assertIn("humanoid", hold_person["targeting"]["allowed_target_types"])
        self.assertEqual(hold_person["scaling"]["slot_level_bonus"]["additional_targets_per_extra_level"], 1)

    def test_counterspell_template_uses_2024_con_save_interrupt_rule(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        spell = repo.get("counterspell")

        self.assertIsNotNone(spell)
        self.assertEqual(spell["resolution"]["activation"], "reaction")
        self.assertEqual(spell["resolution"]["mode"], "interrupt_save")
        self.assertEqual(spell["resolution"]["save_ability"], "con")
        self.assertTrue(spell["resolution"]["on_failed_save_cancel_cast"])
        self.assertTrue(spell["resolution"]["on_failed_save_preserve_interrupted_spell_slot"])

    def test_shield_template_matches_runtime_reaction_behavior(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        spell = repo.get("shield")

        self.assertIsNotNone(spell)
        self.assertEqual(spell["resolution"]["activation"], "reaction")
        self.assertEqual(spell["resolution"]["mode"], "no_roll")
        self.assertEqual(spell["targeting"]["type"], "self")
        self.assertEqual(spell["special_rules"]["ac_bonus"], 5)
        self.assertEqual(spell["special_rules"]["duration_until"], "start_of_next_self_turn")

    def test_get_returns_eldritch_blast_cantrip_template(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        spell = repo.get("eldritch_blast")

        self.assertIsNotNone(spell)
        self.assertEqual(spell["id"], "eldritch_blast")
        self.assertEqual(spell["base"]["level"], 0)
        self.assertEqual(spell["resolution"]["activation"], "action")
        self.assertEqual(spell["targeting"]["allowed_target_types"], ["creature"])
        self.assertGreaterEqual(len(spell["scaling"]["cantrip_by_level"]), 1)

    def test_hex_template_describes_retarget_rule_even_if_not_implemented(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        spell = repo.get("hex")

        self.assertIsNotNone(spell)
        self.assertTrue(spell["special_rules"]["retarget_on_target_drop_to_zero"]["enabled"])
        self.assertEqual(
            spell["special_rules"]["retarget_on_target_drop_to_zero"]["activation"],
            "bonus_action",
        )

    def test_hunters_mark_template_describes_retarget_rule(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        spell = repo.get("hunters_mark")

        self.assertIsNotNone(spell)
        self.assertEqual(spell["name"], "Hunter's Mark")
        self.assertTrue(spell["special_rules"]["retarget_on_target_drop_to_zero"]["enabled"])
        self.assertEqual(
            spell["special_rules"]["retarget_on_target_drop_to_zero"]["activation"],
            "bonus_action",
        )

    def test_hex_and_hunters_mark_expose_slot_duration_bonus_rules(self) -> None:
        repo = SpellDefinitionRepository(Path(PROJECT_ROOT / "data/knowledge/spell_definitions.json"))

        hex_spell = repo.get("hex")
        hunters_mark = repo.get("hunters_mark")

        self.assertIsNotNone(hex_spell)
        self.assertIsNotNone(hunters_mark)
        self.assertEqual(hex_spell["scaling"]["slot_duration_bonus"][0]["slot_level"], 2)
        self.assertEqual(
            hex_spell["scaling"]["slot_duration_bonus"][-1]["duration"],
            "concentration_up_to_24_hours",
        )
        self.assertEqual(hunters_mark["scaling"]["slot_duration_bonus"][0]["slot_level"], 2)
        self.assertEqual(
            hunters_mark["scaling"]["slot_duration_bonus"][-1]["duration"],
            "concentration_up_to_24_hours",
        )
