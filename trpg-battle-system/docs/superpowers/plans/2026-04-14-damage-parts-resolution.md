# Damage Parts Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个独立的 `ResolveDamageParts` 基础设施，支持多段立即生效伤害、暴击倍骰、逐段抗性/免疫/易伤修正，并返回结构化 breakdown。

**Architecture:** 这次只做纯规则层，不改 `execute_attack` 或 `UpdateHp` 主流程。新增 `tools/services/combat/damage/resolve_damage_parts.py` 作为无仓储依赖的结算器，输入 `damage_parts` 与目标伤害 trait，输出 `parts` breakdown 和 `total_damage`。测试集中放在 `test/test_resolve_damage_parts.py`，把规则边界先锁死。

**Tech Stack:** Python 3.9, unittest

---

### File Structure

- Create: `tools/services/combat/damage/resolve_damage_parts.py`
  - 负责解析最小伤害公式、应用暴击倍骰、逐段处理抗性/免疫/易伤、汇总结果
- Create: `tools/services/combat/damage/__init__.py`
  - 暴露 `ResolveDamageParts`
- Modify: `tools/services/__init__.py`
  - 聚合导出 `ResolveDamageParts`
- Create: `test/test_resolve_damage_parts.py`
  - 为新结算器建立独立契约测试

### Task 1: 建立单段与多段伤害的红灯测试

**Files:**
- Create: `test/test_resolve_damage_parts.py`
- Test: `test/test_resolve_damage_parts.py`

- [ ] **Step 1: Write the failing tests**

```python
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.services.combat.damage.resolve_damage_parts import ResolveDamageParts


class ResolveDamagePartsTests(unittest.TestCase):
    def test_execute_resolves_single_damage_part_without_adjustment(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8+4", "damage_type": "piercing", "source": "weapon_base"}
            ],
            is_critical_hit=False,
            rolled_values=[[5]],
        )

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test.test_resolve_damage_parts`
Expected: FAIL with import error because `ResolveDamageParts` does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
class ResolveDamageParts:
    def execute(...):
        return {
            "is_critical_hit": is_critical_hit,
            "parts": [],
            "total_damage": 0,
        }
```

Create the class and method with the final signature, but return the minimal shape first so the failure moves from import to behavior.

- [ ] **Step 4: Run tests to verify they still fail for behavior**

Run: `python3 -m unittest test.test_resolve_damage_parts`
Expected: FAIL on assertion mismatch (`parts` empty / `total_damage` wrong)

- [ ] **Step 5: Commit**

```bash
git add test/test_resolve_damage_parts.py tools/services/combat/damage/resolve_damage_parts.py tools/services/combat/damage/__init__.py tools/services/__init__.py
git commit -m "test: scaffold damage parts resolution"
```

### Task 2: 实现最小公式解析与普通伤害结算

**Files:**
- Modify: `tools/services/combat/damage/resolve_damage_parts.py`
- Test: `test/test_resolve_damage_parts.py`

- [ ] **Step 1: Write the failing test for formula parsing validation**

```python
    def test_execute_rejects_invalid_damage_formula(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_damage_formula"):
            ResolveDamageParts().execute(
                damage_parts=[
                    {"formula": "bad_formula", "damage_type": "force", "source": "spell_base"}
                ],
                is_critical_hit=False,
                rolled_values=[[]],
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest test.test_resolve_damage_parts.ResolveDamagePartsTests.test_execute_rejects_invalid_damage_formula`
Expected: FAIL because invalid formulas are not validated yet

- [ ] **Step 3: Write minimal implementation**

```python
import re


class ResolveDamageParts:
    _FORMULA_RE = re.compile(r"^(?:(\d+)d(\d+))?([+-]\d+)?$")

    def execute(self, *, damage_parts, is_critical_hit, rolled_values, resistances=None, immunities=None, vulnerabilities=None):
        resolved_parts = []
        total_damage = 0
        for index, part in enumerate(damage_parts):
            formula = str(part["formula"])
            dice_count, die_size, flat_bonus = self._parse_formula(formula)
            rolls = rolled_values[index]
            if dice_count != len(rolls):
                raise ValueError("rolled_values_count_mismatch")
            rolled_total = sum(rolls) + flat_bonus
            adjusted_total, adjustment_rule = self._apply_adjustment(
                rolled_total,
                str(part.get("damage_type") or "").lower() or None,
                resistances or [],
                immunities or [],
                vulnerabilities or [],
            )
            resolved_parts.append(
                {
                    "source": part["source"],
                    "formula": formula,
                    "resolved_formula": formula,
                    "damage_type": part.get("damage_type"),
                    "rolled_total": rolled_total,
                    "adjusted_total": adjusted_total,
                    "adjustment_rule": adjustment_rule,
                }
            )
            total_damage += adjusted_total
        return {"is_critical_hit": is_critical_hit, "parts": resolved_parts, "total_damage": total_damage}
```

Also implement `_parse_formula(...)` and `_apply_adjustment(...)` helpers in the same file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test.test_resolve_damage_parts`
Expected: PASS for single-part, multi-part, and invalid-formula tests

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/damage/resolve_damage_parts.py test/test_resolve_damage_parts.py
git commit -m "feat: resolve basic damage parts"
```

### Task 3: 补暴击倍骰规则

**Files:**
- Modify: `test/test_resolve_damage_parts.py`
- Modify: `tools/services/combat/damage/resolve_damage_parts.py`

- [ ] **Step 1: Write the failing critical-hit tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test.test_resolve_damage_parts.ResolveDamagePartsTests.test_execute_doubles_only_dice_on_critical_hit test.test_resolve_damage_parts.ResolveDamagePartsTests.test_execute_doubles_each_dice_based_part_on_critical_hit`
Expected: FAIL because critical hits still use the original dice count

- [ ] **Step 3: Write minimal implementation**

```python
    effective_dice_count = dice_count * 2 if is_critical_hit and dice_count > 0 else dice_count
    rolls = rolled_values[index]
    if effective_dice_count != len(rolls):
        raise ValueError("rolled_values_count_mismatch")
    resolved_formula = self._build_formula(effective_dice_count, die_size, flat_bonus)
```

Add `_build_formula(...)` helper so `resolved_formula` becomes `"2d8+4"` on critical hits.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test.test_resolve_damage_parts`
Expected: PASS with critical-hit behavior covered

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/damage/resolve_damage_parts.py test/test_resolve_damage_parts.py
git commit -m "feat: support critical damage parts"
```

### Task 4: 补逐段抗性 / 免疫 / 易伤规则

**Files:**
- Modify: `test/test_resolve_damage_parts.py`
- Modify: `tools/services/combat/damage/resolve_damage_parts.py`

- [ ] **Step 1: Write the failing adjustment tests**

```python
    def test_execute_applies_resistance_per_part(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8", "damage_type": "fire", "source": "spell_base"}
            ],
            is_critical_hit=False,
            rolled_values=[[7]],
            resistances=["fire"],
        )

        self.assertEqual(result["parts"][0]["adjusted_total"], 3)
        self.assertEqual(result["parts"][0]["adjustment_rule"], "resistance")
        self.assertEqual(result["total_damage"], 3)

    def test_execute_applies_immunity_and_vulnerability_per_part(self) -> None:
        result = ResolveDamageParts().execute(
            damage_parts=[
                {"formula": "1d8", "damage_type": "poison", "source": "spell_base"},
                {"formula": "1d6", "damage_type": "cold", "source": "spell_bonus"},
            ],
            is_critical_hit=False,
            rolled_values=[[6], [4]],
            immunities=["poison"],
            vulnerabilities=["cold"],
        )

        self.assertEqual(result["parts"][0]["adjusted_total"], 0)
        self.assertEqual(result["parts"][0]["adjustment_rule"], "immunity")
        self.assertEqual(result["parts"][1]["adjusted_total"], 8)
        self.assertEqual(result["parts"][1]["adjustment_rule"], "vulnerability")
        self.assertEqual(result["total_damage"], 8)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test.test_resolve_damage_parts.ResolveDamagePartsTests.test_execute_applies_resistance_per_part test.test_resolve_damage_parts.ResolveDamagePartsTests.test_execute_applies_immunity_and_vulnerability_per_part`
Expected: FAIL because current implementation still returns unadjusted totals

- [ ] **Step 3: Write minimal implementation**

```python
    def _apply_adjustment(self, rolled_total, damage_type, resistances, immunities, vulnerabilities):
        normalized_immunities = {item.lower() for item in immunities}
        normalized_resistances = {item.lower() for item in resistances}
        normalized_vulnerabilities = {item.lower() for item in vulnerabilities}
        if damage_type is None:
            return rolled_total, "normal"
        if damage_type in normalized_immunities:
            return 0, "immunity"
        if damage_type in normalized_resistances and damage_type in normalized_vulnerabilities:
            return rolled_total, "resistance_and_vulnerability_cancel"
        if damage_type in normalized_resistances:
            return rolled_total // 2, "resistance"
        if damage_type in normalized_vulnerabilities:
            return rolled_total * 2, "vulnerability"
        return rolled_total, "normal"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest test.test_resolve_damage_parts`
Expected: PASS for resistance, immunity, vulnerability, and mixed-part cases

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/damage/resolve_damage_parts.py test/test_resolve_damage_parts.py
git commit -m "feat: apply damage traits per damage part"
```

### Task 5: 聚合导出与回归验证

**Files:**
- Create: `tools/services/combat/damage/__init__.py`
- Modify: `tools/services/__init__.py`
- Test: `test/test_resolve_damage_parts.py`

- [ ] **Step 1: Write the failing import test**

In `test/test_resolve_damage_parts.py`, import through the public aggregator:

```python
from tools.services import ResolveDamageParts
```

Remove the direct module import so the test fails if the aggregator export is missing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest test.test_resolve_damage_parts`
Expected: FAIL with import error for `ResolveDamageParts`

- [ ] **Step 3: Write minimal implementation**

Create `tools/services/combat/damage/__init__.py`:

```python
from tools.services.combat.damage.resolve_damage_parts import ResolveDamageParts

__all__ = ["ResolveDamageParts"]
```

Update `tools/services/__init__.py`:

```python
from tools.services.combat.damage.resolve_damage_parts import ResolveDamageParts
```

and add `"ResolveDamageParts"` to `__all__`.

- [ ] **Step 4: Run verification**

Run: `python3 -m unittest test.test_resolve_damage_parts`
Expected: PASS

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS with all existing suites still green

- [ ] **Step 5: Commit**

```bash
git add tools/services/combat/damage/__init__.py tools/services/combat/damage/resolve_damage_parts.py tools/services/__init__.py test/test_resolve_damage_parts.py
git commit -m "feat: add damage parts resolution service"
```
