# Spell Instances Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为战斗运行时新增 `spell_instances`，把法术持续效果从零散的 `conditions` / `turn_effects` 上收口成可追踪的整体实例，并为 LLM 提供可读摘要投影。

**Architecture:** 在 `Encounter` 顶层新增 `spell_instances`，只记录持续法术实例而不是所有施法。`Hold Person` 与 `Hex` 在施法成功时创建实例，并把 `conditions` / `turn_effects` 的关联信息写进实例。`GetEncounterState` 不直接暴露内部结构，而是投影实体级中文摘要与全局专注摘要。

**Tech Stack:** Python 3.9, TinyDB repository, unittest

---

### Task 1: 扩 `Encounter` 模型支持 `spell_instances`

**Files:**
- Modify: `tools/models/encounter.py`
- Modify: `test/test_models.py`

- [ ] **Step 1: 写失败测试，锁定 `Encounter` round-trip 保留 `spell_instances`**

```python
def test_encounter_roundtrip_preserves_spell_instances():
    encounter = build_encounter_with_spell_instance()
    roundtrip = Encounter.from_dict(encounter.to_dict())
    assert roundtrip.spell_instances[0]["spell_id"] == "hold_person"
```

- [ ] **Step 2: 实现字段**

新增：

```python
spell_instances: list[dict[str, Any]] = field(default_factory=list)
```

并加入 `to_dict()` / `from_dict()`。

- [ ] **Step 3: 跑定向测试**

Run: `python3 -m unittest test.test_models -v`
Expected: PASS

### Task 2: 新增实例构造 helper

**Files:**
- Create: `tools/services/spells/build_spell_instance.py`
- Create: `test/test_build_spell_instance.py`

- [ ] **Step 1: 写失败测试，锁定 `Hold Person` 实例结构**

测试至少断言：

- `spell_id`
- `caster_entity_id`
- `cast_level`
- `targets[0].applied_conditions`
- `targets[0].turn_effect_ids`
- `concentration.required`

- [ ] **Step 2: 写失败测试，锁定 `Hex` 实例结构**

测试至少断言：

- `special_runtime.retargetable = true`
- `special_runtime.current_target_id`

- [ ] **Step 3: 实现 helper**

签名建议：

```python
def build_spell_instance(
    *,
    spell_definition: dict[str, Any],
    caster: EncounterEntity,
    cast_level: int,
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
```

- [ ] **Step 4: 跑定向测试**

Run: `python3 -m unittest test.test_build_spell_instance -v`
Expected: PASS

### Task 3: `Hold Person` / `Hex` 施法时写入 `spell_instances`

**Files:**
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Modify: `tools/services/combat/save_spell/saving_throw_result.py`
- Modify: `test/test_execute_save_spell.py`
- Modify: `test/test_encounter_cast_spell.py`

- [ ] **Step 1: 写失败测试，锁定 `Hold Person` 失败时会生成实例**

- [ ] **Step 2: 写失败测试，锁定 `Hex` 施放时会生成实例**

- [ ] **Step 3: 在 `SavingThrowResult` 写入 `Hold Person` 实例**

需要把：

- 目标 `condition`
- 目标 `turn_effect_ids`

写进实例 targets。

- [ ] **Step 4: 在 `EncounterCastSpell` 的 no-roll 路径写入 `Hex` 实例**

- [ ] **Step 5: 跑定向测试**

Run: `python3 -m unittest test.test_execute_save_spell test.test_encounter_cast_spell -v`
Expected: PASS

### Task 4: `GetEncounterState` 增加 LLM 摘要投影

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `test/test_get_encounter_state.py`
- Modify: `docs/llm-runtime-tool-guide.md`

- [ ] **Step 1: 写失败测试，锁定实体摘要会包含“来自敌人A的定身术”**

- [ ] **Step 2: 写失败测试，锁定全局专注摘要**

- [ ] **Step 3: 只投影摘要，不暴露原始 `spell_instances`**

新增视图建议：

- `current_turn_entity.ongoing_effects`
- `turn_order[].ongoing_effects`
- `active_spell_summaries`

- [ ] **Step 4: 更新运行手册**

明确：

- 后端有 `spell_instances`
- LLM 只看摘要投影

- [ ] **Step 5: 跑定向测试**

Run: `python3 -m unittest test.test_get_encounter_state -v`
Expected: PASS

### Task 5: 全量回归

**Files:**
- No code changes expected

- [ ] **Step 1: 跑全量测试**

Run: `python3 -m unittest discover -s test -p 'test_*.py'`
Expected: PASS

- [ ] **Step 2: 检查差异**

Run: `git diff -- tools/models/encounter.py tools/services/spells tools/services/combat/save_spell tools/services/encounter/get_encounter_state.py test docs/llm-runtime-tool-guide.md`
Expected: only `spell_instances` model, helper, save spell wiring, state projection, tests, and docs changes
