# Nick Light Bonus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `light_bonus` 攻击链上补上最小版 `nick`，使满足条件的双持额外攻击不再消耗附赠动作。

**Architecture:** 继续复用当前的 `attack_mode="light_bonus"` 入口，不新增额外 tool 形状。第一次轻型武器攻击在 `combat_flags.light_bonus_trigger` 中写入是否允许 `nick` 的触发信息；第二次额外攻击在请求层读取该触发器，决定是否需要校验附赠动作，并在执行层决定是否实际消耗附赠动作。

**Tech Stack:** Python 3、unittest、现有 encounter/combat service 层

---

### Task 1: 为 Nick 写失败测试

**Files:**
- Modify: `test/test_execute_attack.py`

- [ ] **Step 1: 写两个失败测试**

```python
def test_execute_nick_light_bonus_does_not_consume_bonus_action():
    ...

def test_execute_nick_light_bonus_still_works_when_bonus_action_already_used():
    ...
```

- [ ] **Step 2: 运行定向测试并确认失败**

Run: `python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_nick_light_bonus_does_not_consume_bonus_action test.test_execute_attack.ExecuteAttackTests.test_execute_nick_light_bonus_still_works_when_bonus_action_already_used -v`
Expected: FAIL，说明当前 `light_bonus` 仍会要求并消耗附赠动作

### Task 2: 最小实现 Nick 触发器

**Files:**
- Modify: `tools/services/combat/attack/attack_roll_request.py`
- Modify: `tools/services/combat/attack/execute_attack.py`

- [ ] **Step 1: 在请求层读取触发器**

```python
trigger = self._get_light_bonus_trigger_or_raise(actor, weapon)
light_bonus_uses_bonus_action = not bool(trigger.get("grants_nick"))
```

- [ ] **Step 2: 在执行层按上下文决定是否消耗附赠动作**

```python
effective_consume_bonus_action = bool(request.context.get("light_bonus_uses_bonus_action", True))
```

- [ ] **Step 3: 第一次攻击写入 Nick 触发信息**

```python
actor.combat_flags["light_bonus_trigger"] = {
    "weapon_id": weapon_id,
    "slot": attack_context.get("weapon_slot"),
    "grants_nick": attack_context.get("weapon_mastery") == "nick",
}
```

### Task 3: 回归验证

**Files:**
- Modify: `test/test_attack_roll_request.py`（如需要补请求层测试）
- Verify: `test/test_execute_attack.py`
- Verify: `test/test_attack_roll_request.py`
- Verify: `test/test_turn_engine.py`

- [ ] **Step 1: 跑 Nick 定向测试**

Run: `python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_nick_light_bonus_does_not_consume_bonus_action test.test_execute_attack.ExecuteAttackTests.test_execute_nick_light_bonus_still_works_when_bonus_action_already_used -v`
Expected: PASS

- [ ] **Step 2: 跑攻击链回归**

Run: `python3 -m unittest test.test_execute_attack test.test_attack_roll_request test.test_turn_engine -v`
Expected: PASS

- [ ] **Step 3: 跑全量测试**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS
