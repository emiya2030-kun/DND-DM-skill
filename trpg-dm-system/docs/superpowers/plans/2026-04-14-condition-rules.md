# Condition Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

I'm using the writing-plans skill to create the implementation plan.

**Goal:** Establish a condition rule center that parses condition strings, exposes runtime helpers, defines canonical rule sets, and makes everything available from `tools.services.combat.rules`.

**Architecture:** Break the solution into parser/runtime/rules modules so each file owns one responsibility: parsing raw strings, evaluating entity conditions, and collecting rule sets. Expose a single entry point from the package for higher-level consumers while keeping tests focused on the new surface.

**Tech Stack:** Python 3.11-style `unittest`, tokenizer-free parsing logic, simple dataclasses or named tuples for structured conditions, module-level lists for rule categories.

---

### Task 1: Capture expectation through tests

**Files:**
- Create: `test/test_condition_rules.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from tools.services.combat.rules.conditions import (
    ConditionRuntime,
    parse_condition,
)


class ConditionRulesTest(unittest.TestCase):
    def test_parse_plain_condition(self):
        condition = parse_condition("blinded")
        self.assertEqual(condition.name, "blinded")
        self.assertIsNone(condition.source)

    def test_parse_from_source(self):
        condition = parse_condition("frightened:ent_enemy_dragon_001")
        self.assertEqual(condition.source, "ent_enemy_dragon_001")

    def test_parse_exhaustion(self):
        condition = parse_condition("exhaustion:2")
        self.assertEqual(condition.name, "exhaustion")
        self.assertEqual(condition.level, 2)

    def test_runtime_helpers(self):
        conditions = ["paralyzed", "exhaustion:3", "frightened:owner"]
        runtime = ConditionRuntime(conditions)
        self.assertTrue(runtime.has("paralyzed"))
        self.assertTrue(runtime.has_from_source("frightened", "owner"))
        self.assertEqual(runtime.exhaustion_level(), 3)
        self.assertEqual(runtime.get_d20_penalty(), 0)
        self.assertEqual(runtime.get_speed_penalty_feet(), 15 * runtime.exhaustion_level())
```

- [ ] **Step 2: Run test to confirm failure**

```
python3 -m unittest test.test_condition_rules -v
```

Expected: FAIL because `parse_condition` and `ConditionRuntime` do not yet exist.

### Task 2: Implement parser and runtime

**Files:**
- Create: `tools/services/combat/rules/conditions/condition_parser.py`
- Create: `tools/services/combat/rules/conditions/condition_runtime.py`

- [ ] **Step 1: Implement `parse_condition`**

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ParsedCondition:
    name: str
    source: str | None = None
    level: int | None = None


def parse_condition(raw: str) -> ParsedCondition:
    if not raw or ":" in raw and raw.endswith(":"):
        raise ValueError(f"invalid condition: {raw!r}")
    parts = raw.split(":", 1)
    name = parts[0]
    source_or_level = parts[1] if len(parts) == 2 else None

    if name == "exhaustion":
        if source_or_level is None or not source_or_level.isdecimal():
            raise ValueError(f"invalid exhaustion level: {raw!r}")
        return ParsedCondition(name=name, level=int(source_or_level))
    return ParsedCondition(name=name, source=source_or_level)
```

- [ ] **Step 2: Implement `ConditionRuntime` helpers**

```python
from typing import Iterable

class ConditionRuntime:
    def __init__(self, conditions: Iterable[str]):
        self._parsed = [parse_condition(cond) for cond in conditions]

    def has(self, name: str) -> bool:
        return any(cond.name == name for cond in self._parsed)

    def has_from_source(self, name: str, source: str) -> bool:
        return any(cond.name == name and cond.source == source for cond in self._parsed)

    def exhaustion_level(self) -> int:
        return next((cond.level for cond in self._parsed if cond.name == "exhaustion"), 0)

    def get_d20_penalty(self) -> int:
        level = self.exhaustion_level()
        if level >= 1:
            return level
        return 0

    def get_speed_penalty_feet(self) -> int:
        return 15 * self.exhaustion_level()
```

- [ ] **Step 3: Run targeted test for parser/runtime**

```
python3 -m unittest test.test_condition_rules.ConditionRulesTest.test_runtime_helpers -v
```

Expected: FAIL until implementations exist.

### Task 3: Define canonical condition rule sets

**Files:**
- Create: `tools/services/combat/rules/conditions/condition_rules.py`
- Modify: `tools/services/combat/rules/__init__.py`

Rule definitions for the requested categories should be plain lists of strings, for example:

```python
BLOCKED_ATTACK_CONDITIONS = ["incapacitated", "paralyzed"]
ATTACK_DISADVANTAGE_CONDITIONS = ["blinded", "poisoned"]
ATTACK_ADVANTAGE_CONDITIONS = ["flanking"]
TARGET_ATTACK_ADVANTAGE_CONDITIONS = ["prone"]
AUTO_FAIL_STRENGTH_DEX_SAVES = ["unconscious"]
DEX_SAVE_DISADVANTAGE_CONDITIONS = ["paralyzed"]
ZERO_SPEED_CONDITIONS = ["stunned"]
INCAPACITATING_CONDITIONS = ["dead"]
AUTO_CRIT_MELEE_TARGET_CONDITIONS = ["unconscious"]
```

- [ ] **Step 1: Implement rule module**

```
python3 -m unittest test.test_condition_rules -v
```

This is a placeholder for verifying rules connect; expect failure if definitions do not yet exist in exports.

- [ ] **Step 2: Export from `tools.services.combat.rules`**

Modify `tools/services/combat/rules/__init__.py` to re-export parser, runtime, and rule constants so tests can import them from `tools.services.combat.rules.conditions`.

### Task 4: Final verification and cleanup

**Files:** (no new files)

- [ ] **Step 1: Run full test suite**

```
python3 -m unittest test.test_condition_rules -v
```

Expected: PASS once parser, runtime, and rules are wired.

- [ ] **Step 2: Self-review**

Manually inspect the new modules for consistency, confirm no placeholders remain, and note any assumptions or follow-ups before reporting status.
