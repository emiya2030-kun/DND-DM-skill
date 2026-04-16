# Forced Movement And Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加强制位移内部服务，并将武器精通 `push` 接到现有 `ExecuteAttack` 结算链。

**Architecture:** 保持普通移动链不变，新增独立的 `resolve_forced_movement` 规则服务，专门处理逐步推进、逐步合法性校验和“遇阻停下”。`push` 只负责在命中后计算推离路径，并调用该服务返回结构化结算结果。

**Tech Stack:** Python 3、unittest、现有 encounter repository / attack service / movement rules 模块

---

### Task 1: 底层强制位移服务

**Files:**
- Create: `tools/services/encounter/resolve_forced_movement.py`
- Modify: `tools/services/encounter/__init__.py`
- Modify: `tools/services/__init__.py`
- Test: `test/test_resolve_forced_movement.py`

- [ ] **Step 1: 写失败测试**

```python
def test_forced_movement_stops_at_last_legal_step(self) -> None:
    result = service.execute(
        encounter_id="enc_forced_move",
        entity_id="ent_enemy_001",
        path=[{"x": 4, "y": 2}, {"x": 5, "y": 2}],
        reason="weapon_mastery_push",
        source_entity_id="ent_ally_001",
    )
    self.assertEqual(result["final_position"], {"x": 4, "y": 2})
    self.assertEqual(result["moved_feet"], 5)
    self.assertTrue(result["blocked"])
```

- [ ] **Step 2: 跑单测确认失败**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_resolve_forced_movement`

Expected: FAIL，提示 `ResolveForcedMovement` 或对应模块不存在

- [ ] **Step 3: 写最小实现**

```python
class ResolveForcedMovement:
    def execute(...):
        encounter = self.repository.get(encounter_id)
        entity = encounter.entities[entity_id]
        start = {"x": entity.position["x"], "y": entity.position["y"]}
        resolved_path = []
        blocked = False
        block_reason = None
        for anchor in path:
            legal, reason = ...
            if not legal:
                blocked = True
                block_reason = reason
                break
            entity.position = {"x": anchor["x"], "y": anchor["y"]}
            resolved_path.append({"x": anchor["x"], "y": anchor["y"]})
        self.repository.save(encounter)
        return {...}
```

- [ ] **Step 4: 跑单测确认通过**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_resolve_forced_movement`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  test/test_resolve_forced_movement.py \
  tools/services/encounter/resolve_forced_movement.py \
  tools/services/encounter/__init__.py \
  tools/services/__init__.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: add forced movement resolver"
```

### Task 2: 校验强制位移边界行为

**Files:**
- Modify: `test/test_resolve_forced_movement.py`
- Modify: `tools/services/encounter/resolve_forced_movement.py`

- [ ] **Step 1: 写失败测试**

```python
def test_forced_movement_does_not_spend_speed_or_create_reactions(self) -> None:
    result = service.execute(...)
    updated = encounter_repo.get("enc_forced_move")
    target = updated.entities["ent_enemy_001"]
    self.assertEqual(target.speed["remaining"], 30)
    self.assertEqual(target.combat_flags.get("movement_spent_feet"), None)
    self.assertEqual(updated.reaction_requests, [])
    self.assertIsNone(updated.pending_movement)
```

- [ ] **Step 2: 跑该测试确认失败**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_resolve_forced_movement.ResolveForcedMovementTests.test_forced_movement_does_not_spend_speed_or_create_reactions`

Expected: FAIL

- [ ] **Step 3: 补最小实现**

```python
# 不修改 speed.remaining
# 不写 movement_spent_feet
# 不追加 reaction_requests
# 不写 pending_movement
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_resolve_forced_movement`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  test/test_resolve_forced_movement.py \
  tools/services/encounter/resolve_forced_movement.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "test: cover forced movement rules"
```

### Task 3: 将 Push 接入武器精通结算

**Files:**
- Modify: `tools/services/combat/attack/weapon_mastery_effects.py`
- Modify: `test/test_execute_attack.py`

- [ ] **Step 1: 写失败测试**

```python
def test_execute_applies_push_forced_movement_when_attack_hits(self) -> None:
    result = service.execute(...)
    push = result["resolution"]["weapon_mastery_updates"]["push"]
    self.assertEqual(push["status"], "resolved")
    self.assertEqual(push["moved_feet"], 10)
    updated = encounter_repo.get("enc_execute_attack_test")
    self.assertEqual(updated.entities["ent_enemy_goblin_001"].position, {"x": 5, "y": 2})
```

- [ ] **Step 2: 跑该测试确认失败**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_applies_push_forced_movement_when_attack_hits`

Expected: FAIL，返回中没有 `push` 或目标位置未变化

- [ ] **Step 3: 写最小实现**

```python
elif mastery == "push" and damage_dealt > 0:
    forced = resolve_forced_movement.execute(...)
    results["push"] = {
        "status": "resolved",
        "target_entity_id": target.entity_id,
        "start_position": forced["start_position"],
        "final_position": forced["final_position"],
        "moved_feet": forced["moved_feet"],
        "blocked": forced["blocked"],
        "block_reason": forced["block_reason"],
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_applies_push_forced_movement_when_attack_hits`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  test/test_execute_attack.py \
  tools/services/combat/attack/weapon_mastery_effects.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "feat: resolve push mastery with forced movement"
```

### Task 4: 补 Push 边界与回归

**Files:**
- Modify: `test/test_execute_attack.py`
- Modify: `tools/services/combat/attack/weapon_mastery_effects.py`

- [ ] **Step 1: 写失败测试**

```python
def test_execute_push_stops_when_second_step_blocked(self) -> None:
    ...
    self.assertEqual(push["moved_feet"], 5)
    self.assertTrue(push["blocked"])

def test_execute_push_has_no_effect_on_huge_target(self) -> None:
    ...
    self.assertEqual(push["status"], "no_effect")
    self.assertEqual(push["reason"], "target_too_large")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_execute_attack.ExecuteAttackTests.test_execute_push_stops_when_second_step_blocked test.test_execute_attack.ExecuteAttackTests.test_execute_push_has_no_effect_on_huge_target`

Expected: FAIL

- [ ] **Step 3: 补最小实现**

```python
if target.size not in {"tiny", "small", "medium", "large"}:
    return {"applied_effects": [], "push": {"status": "no_effect", "reason": "target_too_large"}}
```

- [ ] **Step 4: 跑攻击相关回归**

Run: `cd /Users/runshi.zhang/trpg-module-skills/trpg-dm-system && python3 -m unittest test.test_resolve_forced_movement test.test_execute_attack test.test_attack_roll_request`

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system add \
  test/test_resolve_forced_movement.py \
  test/test_execute_attack.py \
  tools/services/combat/attack/weapon_mastery_effects.py \
  tools/services/encounter/resolve_forced_movement.py
git -C /Users/runshi.zhang/trpg-module-skills/trpg-dm-system commit -m "test: cover push mastery forced movement edges"
```
