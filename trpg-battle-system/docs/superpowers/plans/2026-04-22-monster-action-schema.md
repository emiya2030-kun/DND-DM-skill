# Monster Action Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一怪物动作模板 schema，让未来怪物模板都能复用 `availability`、`targeting`、`execution_steps`、`ai_hints`、`legendary_actions_metadata`。

**Architecture:** 先扩展知识库模板与动作元数据投影层，使结构化字段能稳定进入 `get_encounter_state`。再补一个完整的吸血鬼模板作为通用样板，并保持现有多重攻击编排兼容。

**Tech Stack:** Python, pytest, JSON knowledge templates

---

### Task 1: Schema Projection

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Test: `test/test_get_encounter_state.py`

- [ ] 补动作元数据投影测试
- [ ] 跑失败测试确认缺字段
- [ ] 实现 `legendary_actions_metadata` 与通用字段透传
- [ ] 跑测试确认通过

### Task 2: Template Samples

**Files:**
- Modify: `data/knowledge/entity_definitions.json`
- Modify: `tools/services/spells/summons/find_familiar_builder.py`
- Test: `test/test_entity_definition_repository.py`
- Test: `test/test_find_familiar_builder.py`

- [ ] 补尸妖/伪龙/吸血鬼结构化模板测试
- [ ] 跑失败测试确认模板缺口
- [ ] 实现统一 schema 样板
- [ ] 跑测试确认通过

### Task 3: Regression

**Files:**
- Test: `test/test_get_encounter_state.py`
- Test: `test/test_entity_definition_repository.py`
- Test: `test/test_find_familiar_builder.py`

- [ ] 跑组合回归
- [ ] 检查 `current_turn_context` 和 `combat_profile` 输出兼容
