import re
from typing import Tuple


class ResolveDamageParts:
    _FORMULA_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$")
    _FLAT_RE = re.compile(r"^[+]?(\d+)$")

    def execute(
        self,
        *,
        damage_parts,
        is_critical_hit,
        rolled_values,
        resistances=None,
        immunities=None,
        vulnerabilities=None,
    ):
        resolved_parts = []
        total_damage = 0

        if len(rolled_values) != len(damage_parts):
            raise ValueError("rolled_values_count_mismatch")

        if not isinstance(is_critical_hit, bool):
            raise ValueError("is_critical_hit must be a boolean")

        resistances = self._normalize_trait_list("resistances", resistances)
        immunities = self._normalize_trait_list("immunities", immunities)
        vulnerabilities = self._normalize_trait_list("vulnerabilities", vulnerabilities)

        for index, part in enumerate(damage_parts):
            formula = str(part["formula"])
            dice_count, die_size, flat_bonus = self._parse_formula(formula)
            effective_dice_count = (
                dice_count * 2 if is_critical_hit and dice_count > 0 else dice_count
            )

            part_rolls = rolled_values[index]

            if effective_dice_count != len(part_rolls):
                raise ValueError("rolled_values_count_mismatch")

            for roll_value in part_rolls:
                if not isinstance(roll_value, int) or isinstance(roll_value, bool):
                    raise ValueError("invalid_die_roll")
                if roll_value < 1 or roll_value > die_size:
                    raise ValueError("invalid_die_roll")

            rolled_total = sum(part_rolls) + flat_bonus
            adjusted_total, adjustment_rule = self._apply_adjustment(
                rolled_total,
                part.get("damage_type"),
                resistances=resistances,
                immunities=immunities,
                vulnerabilities=vulnerabilities,
            )

            resolved_parts.append(
                {
                    "source": part.get("source"),
                    "formula": formula,
                    "resolved_formula": self._format_resolved_formula(
                        effective_dice_count, die_size, flat_bonus
                    ),
                    "damage_type": part.get("damage_type"),
                    "rolled_total": rolled_total,
                    "adjusted_total": adjusted_total,
                    "adjustment_rule": adjustment_rule,
                }
            )

            total_damage += adjusted_total

        return {
            "is_critical_hit": is_critical_hit,
            "parts": resolved_parts,
            "total_damage": total_damage,
        }

    def _parse_formula(self, formula: str) -> Tuple[int, int, int]:
        match = self._FORMULA_RE.match(formula)
        if match:
            dice_count = int(match.group(1))
            die_size = int(match.group(2))
            flat_bonus = int(match.group(3) or 0)

            if dice_count <= 0 or die_size <= 0:
                raise ValueError("invalid_damage_formula")

            return dice_count, die_size, flat_bonus

        flat_match = self._FLAT_RE.match(formula)
        if flat_match:
            flat_bonus = int(flat_match.group(1))
            if flat_bonus < 0:
                raise ValueError("invalid_damage_formula")
            return 0, 1, flat_bonus

        raise ValueError("invalid_damage_formula")

    def _normalize_trait_list(self, name: str, value):
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError(f"{name} must be a list")
        return value

    def _format_resolved_formula(
        self, dice_count: int, die_size: int, flat_bonus: int
    ) -> str:
        if dice_count == 0:
            return str(flat_bonus)
        if flat_bonus > 0:
            bonus = f"+{flat_bonus}"
        elif flat_bonus < 0:
            bonus = str(flat_bonus)
        else:
            bonus = ""

        return f"{dice_count}d{die_size}{bonus}"

    def _apply_adjustment(
        self,
        rolled_total: int,
        damage_type,
        *,
        resistances=None,
        immunities=None,
        vulnerabilities=None,
    ) -> Tuple[int, str]:
        normalized_type = (
            str(damage_type).strip().lower() if damage_type else None
        )

        if not normalized_type:
            return max(0, rolled_total), "normal"
        resistances = [str(r).strip().lower() for r in (resistances or [])]
        immunities = [str(i).strip().lower() for i in (immunities or [])]
        vulnerabilities = [str(v).strip().lower() for v in (vulnerabilities or [])]

        if normalized_type in immunities:
            return 0, "immunity"

        has_resistance = normalized_type in resistances
        has_vulnerability = normalized_type in vulnerabilities

        if has_resistance and has_vulnerability:
            return max(0, rolled_total), "normal"
        if has_resistance:
            return max(0, rolled_total // 2), "resistance"
        if has_vulnerability:
            return max(0, rolled_total * 2), "vulnerability"

        return max(0, rolled_total), "normal"
