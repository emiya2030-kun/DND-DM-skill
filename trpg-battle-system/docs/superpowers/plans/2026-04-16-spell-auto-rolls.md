# Spell Auto Rolls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让战斗内 `cast_spell` 完全由后端自动掷豁免骰、攻击骰与伤害骰，外部不再传入 spell roll 参数。

**Architecture:** 保持现有 runtime `cast_spell -> ExecuteSpell -> 规则 service` 链路不变，只把“缺少 save_rolls / attack_rolls / damage_rolls 时返回错误”改成“内部自动生成掷骰输入”。自动掷骰逻辑集中放在 `ExecuteSpell`，这样 runtime 与未来其他调用入口都能复用。

**Tech Stack:** Python 3, unittest, 当前 runtime/encounter/service 结构

---

### Task 1: 先用 runtime 测试锁定行为

**Files:**
- Modify: `test/test_runtime_cast_spell.py`

- [ ] **Step 1: 写失败测试**

```python
result = execute_runtime_command(
    context,
    command="cast_spell",
    args={
        "encounter_id": "enc_runtime_spell_demo",
        "actor_id": "ent_ally_wizard_001",
        "spell_id": "hold_person",
        "cast_level": 2,
        "target_entity_ids": ["ent_enemy_brute_001"],
    },
    handlers=COMMAND_HANDLERS,
)
assert result["ok"] is True
```

- [ ] **Step 2: 跑单测确认当前失败**

Run: `python3 -m unittest test.test_runtime_cast_spell -v`
Expected: FAIL，原因是缺少 `save_rolls`

- [ ] **Step 3: 扩断言**

```python
self.assertIn("paralyzed", updated.entities["ent_enemy_brute_001"].conditions)
self.assertTrue(any(item["event_type"] == "saving_throw_resolved" for item in recent_activity))
```

- [ ] **Step 4: 再跑一次确认仍为红灯**

Run: `python3 -m unittest test.test_runtime_cast_spell -v`
Expected: FAIL，但断点仍在自动掷骰缺失

### Task 2: 在 ExecuteSpell 内生成自动掷骰输入

**Files:**
- Modify: `tools/services/spells/execute_spell.py`

- [ ] **Step 1: 写最小 helper 设计**

```python
def _build_auto_save_rolls(...)
def _build_auto_attack_roll_entries(...)
def _build_auto_damage_rolls_for_outcome(...)
```

- [ ] **Step 2: 在 save_damage / save_condition 分支缺省时自动补 save_rolls**

```python
if save_rolls is None:
    save_roll_index = self._build_auto_save_roll_index(...)
```

- [ ] **Step 3: 在 save_damage / attack_spell 分支缺省时自动补 damage_rolls**

```python
if damage_rolls is None:
    normalized_damage_rolls = self._build_auto_damage_rolls_for_outcome(...)
```

- [ ] **Step 4: 在 attack_spell 分支缺省时自动补 attack_rolls**

```python
if attack_rolls is None:
    attack_roll_entries = self._build_auto_attack_roll_entries(...)
```

- [ ] **Step 5: 自动骰点仍走现有 resolve/update 链，不改结算模型**

```python
roll_result = self.resolve_saving_throw.execute(...)
resolution = self.saving_throw_result.execute(...)
```

### Task 3: 回归验证 runtime 与本地页面

**Files:**
- Modify: `test/test_runtime_cast_spell.py`
- Verify only: `runtime/commands/cast_spell.py`

- [ ] **Step 1: 跑 runtime 相关测试**

Run: `python3 -m unittest test.test_runtime_cast_spell test.test_runtime_start_random_encounter test.test_runtime_http_server test.test_battlemap_runtime_integration -v`
Expected: 全部 PASS

- [ ] **Step 2: 真实 POST 一次 `cast_spell`**

```bash
python3 - <<'PY'
import json, urllib.request
payload = {
  "command": "cast_spell",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "ent_ally_wizard_001",
    "spell_id": "hold_person",
    "cast_level": 2,
    "target_entity_ids": ["ent_enemy_brute_001"]
  }
}
req = urllib.request.Request(
  "http://127.0.0.1:8771/runtime/command",
  data=json.dumps(payload).encode("utf-8"),
  method="POST",
  headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=5) as r:
    print(r.read().decode("utf-8"))
PY
```

- [ ] **Step 3: 验证前端状态投影**

Run: `python3 - <<'PY' ... urllib.request.urlopen('http://127.0.0.1:8765/api/encounter-state?encounter_id=enc_preview_demo') ... PY`
Expected: `recent_activity` 出现施法/豁免，目标条件更新
