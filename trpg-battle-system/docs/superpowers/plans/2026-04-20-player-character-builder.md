# Player Character Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增统一 PC 构筑器，并把 `EncounterService` 的 PC 模板初始化链路接到该构筑器。

**Architecture:** 独立 `PlayerCharacterBuilder` 负责把模板中的 `character_build` 转成标准 `EncounterEntity`。`EncounterService` 只负责选择是否走 builder，规则推导复用现有熟练与法术位 helper。

**Tech Stack:** Python dataclasses, unittest, pytest

---

### Task 1: Builder 红绿测试

**Files:**
- Create: `test/test_player_character_builder.py`
- Create: `tools/services/characters/player_character_builder.py`
- Create: `tools/services/characters/__init__.py`

- [ ] 写失败测试：builder 能推导职业等级、能力调整值、熟练加值、豁免熟练、施法职业与法术位
- [ ] 跑失败测试
- [ ] 写最小实现
- [ ] 跑通过测试

### Task 2: EncounterService 接入

**Files:**
- Modify: `tools/services/encounter/manage_encounter_entities.py`
- Modify: `test/test_encounter_service.py`

- [ ] 写失败测试：PC 模板带 `character_build` 时，初始化链路走 builder
- [ ] 跑失败测试
- [ ] 写最小实现
- [ ] 跑通过测试

### Task 3: 聚焦回归

**Files:**
- Test: `test/test_player_character_builder.py`
- Test: `test/test_encounter_service.py`
- Test: `test/test_models.py`
- Test: `test/test_class_feature_runtime_helpers.py`
- Test: `test/test_resolve_spellcasting_access.py`
- Test: `test/test_spell_request.py`
- Test: `test/test_encounter_cast_spell.py`
- Test: `test/test_execute_spell.py`

- [ ] 运行聚焦回归
- [ ] 确认无回归后汇总
