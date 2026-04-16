import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.services import ResolveDamageParts


class ResolveDamagePartsTests(unittest.TestCase):
    def test_execute_resolves_single_damage_part_without_adjustment(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8+4", "damage_type": "piercing", "source": "weapon_base"}
            ],
            is_critical_hit=False,
            rolled_values=[[5]],
        )

        self.assertEqual(len(result["parts"]), 1)
        self.assertFalse(result["is_critical_hit"])
        self.assertEqual(result["parts"][0]["resolved_formula"], "1d8+4")
        self.assertEqual(result["parts"][0]["rolled_total"], 9)
        self.assertEqual(result["parts"][0]["adjusted_total"], 9)
        self.assertEqual(result["parts"][0]["adjustment_rule"], "normal")
        self.assertEqual(result["total_damage"], 9)

    def test_execute_resolves_multiple_damage_parts_independently(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8+4", "damage_type": "piercing", "source": "weapon_base"},
                {"formula": "1d8", "damage_type": "fire", "source": "weapon_bonus"},
            ],
            is_critical_hit=False,
            rolled_values=[[3], [7]],
        )

        self.assertEqual(len(result["parts"]), 2)
        self.assertEqual(result["parts"][0]["adjusted_total"], 7)
        self.assertEqual(result["parts"][1]["adjusted_total"], 7)
        self.assertEqual(result["total_damage"], 14)

    def test_execute_rejects_invalid_damage_formula(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_damage_formula"):
            ResolveDamageParts().execute(
                damage_parts=[
                    {
                        "formula": "0d6",
                        "damage_type": "force",
                        "source": "spell_base",
                    }
                ],
                is_critical_hit=False,
                rolled_values=[[]],
            )

    def test_execute_rejects_invalid_die_roll(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_die_roll"):
            ResolveDamageParts().execute(
                damage_parts=[
                    {"formula": "1d8", "damage_type": "force", "source": "spell_base"}
                ],
                is_critical_hit=False,
                rolled_values=[[99]],
            )

    def test_execute_rejects_zero_die_roll(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_die_roll"):
            ResolveDamageParts().execute(
                damage_parts=[
                    {"formula": "1d8", "damage_type": "force", "source": "spell_base"}
                ],
                is_critical_hit=False,
                rolled_values=[[0]],
            )

    def test_execute_rejects_bool_die_roll(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_die_roll"):
            ResolveDamageParts().execute(
                damage_parts=[
                    {"formula": "1d8", "damage_type": "force", "source": "spell_base"}
                ],
                is_critical_hit=False,
                rolled_values=[[True]],
            )

    def test_execute_doubles_only_dice_on_critical_hit(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8+4", "damage_type": "piercing", "source": "weapon_base"}
            ],
            is_critical_hit=True,
            rolled_values=[[5, 7]],
        )

        self.assertEqual(result["parts"][0]["resolved_formula"], "2d8+4")
        self.assertEqual(result["parts"][0]["rolled_total"], 16)
        self.assertEqual(result["total_damage"], 16)

    def test_execute_doubles_each_dice_based_part_on_critical_hit(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8+4", "damage_type": "piercing", "source": "weapon_base"},
                {"formula": "1d8", "damage_type": "fire", "source": "weapon_bonus"},
            ],
            is_critical_hit=True,
            rolled_values=[[2, 6], [3, 4]],
        )

        self.assertEqual(result["parts"][0]["resolved_formula"], "2d8+4")
        self.assertEqual(result["parts"][1]["resolved_formula"], "2d8")
        self.assertEqual(result["total_damage"], 19)

    def test_execute_applies_resistance_per_part(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8", "damage_type": "piercing", "source": "weapon_base"},
                {"formula": "1d8", "damage_type": "fire", "source": "weapon_bonus"},
            ],
            is_critical_hit=False,
            rolled_values=[[4], [6]],
            resistances=["PierCing"],
        )

        self.assertEqual(result["parts"][0]["adjusted_total"], 2)
        self.assertEqual(result["parts"][1]["adjusted_total"], 6)
        self.assertEqual(result["total_damage"], 8)

    def test_execute_applies_immunity_and_vulnerability_per_part(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8", "damage_type": "piercing", "source": "weapon_base"},
                {"formula": "1d8", "damage_type": "fire", "source": "weapon_bonus"},
            ],
            is_critical_hit=False,
            rolled_values=[[3], [5]],
            immunities=["fire"],
            vulnerabilities=["piercing"],
        )

        self.assertEqual(result["parts"][0]["adjusted_total"], 6)
        self.assertEqual(result["parts"][1]["adjusted_total"], 0)
        self.assertEqual(result["total_damage"], 6)

    def test_execute_clamps_negative_adjusted_total_to_zero(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d4-10", "damage_type": "force", "source": "spell_base"}
            ],
            is_critical_hit=False,
            rolled_values=[[1]],
        )

        self.assertEqual(result["parts"][0]["rolled_total"], -9)
        self.assertEqual(result["parts"][0]["adjusted_total"], 0)
        self.assertEqual(result["total_damage"], 0)

    def test_execute_clamps_negative_without_damage_type(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[{"formula": "1d4-10", "source": "spell_base"}],
            is_critical_hit=False,
            rolled_values=[[1]],
        )

        self.assertEqual(result["parts"][0]["adjusted_total"], 0)
        self.assertEqual(result["total_damage"], 0)

    def test_execute_resistance_and_vulnerability_cancel(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d6", "damage_type": "cold", "source": "weapon_base"}
            ],
            is_critical_hit=False,
            rolled_values=[[4]],
            resistances=["cold"],
            vulnerabilities=["cold"],
        )

        self.assertEqual(result["parts"][0]["adjusted_total"], 4)
        self.assertEqual(result["parts"][0]["adjustment_rule"], "normal")
        self.assertEqual(result["total_damage"], 4)

    def test_execute_requires_boolean_is_critical_hit(self) -> None:
        with self.assertRaisesRegex(ValueError, "is_critical_hit must be a boolean"):
            ResolveDamageParts().execute(
                damage_parts=[
                    {"formula": "1d6", "damage_type": "cold", "source": "weapon_base"}
                ],
                is_critical_hit=None,
                rolled_values=[[4]],
            )

    def test_execute_requires_list_for_traits(self) -> None:
        with self.assertRaisesRegex(ValueError, "resistances must be a list"):
            ResolveDamageParts().execute(
                damage_parts=[
                    {"formula": "1d6", "damage_type": "cold", "source": "weapon_base"}
                ],
                is_critical_hit=False,
                rolled_values=[[4]],
                resistances="cold",
            )
