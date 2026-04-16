# Close Range Ranged Disadvantage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为武器攻击请求补上远程贴脸劣势，并预留未来专长/特性忽略该劣势的通用覆盖口。

**Architecture:** 只在 `AttackRollRequest` 的优势/劣势合并层实现这条规则，不改 tool 形状。通过扫描攻击者 5 尺内的敌对实体，生成 `close_range_hostile` 劣势来源；若攻击者 `combat_flags.attack_rule_overrides.ignore_close_range_disadvantage` 生效，则跳过该来源。

**Tech Stack:** Python 3、unittest、现有 encounter/combat service 层

---

### Task 1: 写失败测试

**Files:**
- Modify: `test/test_attack_roll_request.py`

- [ ] **Step 1: 写三条失败测试**

```python
def test_execute_applies_disadvantage_for_ranged_attack_when_hostile_is_within_5_feet():
    ...

def test_execute_ignores_close_range_disadvantage_when_adjacent_hostile_cannot_see_or_act():
    ...

def test_execute_ignores_close_range_disadvantage_when_actor_has_override():
    ...
```

- [ ] **Step 2: 运行定向测试确认失败**

Run: `python3 -m unittest test.test_attack_roll_request.AttackRollRequestTests.test_execute_applies_disadvantage_for_ranged_attack_when_hostile_is_within_5_feet test.test_attack_roll_request.AttackRollRequestTests.test_execute_ignores_close_range_disadvantage_when_adjacent_hostile_cannot_see_or_act test.test_attack_roll_request.AttackRollRequestTests.test_execute_ignores_close_range_disadvantage_when_actor_has_override -v`
Expected: FAIL，说明当前攻击请求还未处理远程贴脸劣势

### Task 2: 最小实现

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`

- [ ] **Step 1: 增加邻近敌对实体扫描**

```python
if attack_kind == "ranged_weapon" and not self._actor_ignores_close_range_disadvantage(actor):
    for entity in encounter.entities.values():
        ...
```

- [ ] **Step 2: 只在满足规则时添加劣势来源**

```python
disadvantage_sources.append(f"close_range_hostile:{entity.entity_id}")
```

- [ ] **Step 3: 增加覆盖口 helper**

```python
overrides = actor.combat_flags.get("attack_rule_overrides", {})
```

### Task 3: 回归验证

**Files:**
- Verify: `test/test_attack_roll_request.py`
- Verify: `test/test_execute_attack.py`

- [ ] **Step 1: 跑定向测试**

Run: `python3 -m unittest test.test_attack_roll_request.AttackRollRequestTests.test_execute_applies_disadvantage_for_ranged_attack_when_hostile_is_within_5_feet test.test_attack_roll_request.AttackRollRequestTests.test_execute_ignores_close_range_disadvantage_when_adjacent_hostile_cannot_see_or_act test.test_attack_roll_request.AttackRollRequestTests.test_execute_ignores_close_range_disadvantage_when_actor_has_override -v`
Expected: PASS

- [ ] **Step 2: 跑攻击链回归**

Run: `python3 -m unittest test.test_attack_roll_request test.test_execute_attack -v`
Expected: PASS

- [ ] **Step 3: 跑全量测试**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS
