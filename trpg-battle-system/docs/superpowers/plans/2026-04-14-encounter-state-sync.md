# Encounter State Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让会修改 encounter 的内部 service tool 能在合适层级返回最新 `encounter_state`，供前端统一执行 `applyEncounterState(nextState)`。

**Architecture:** 保持 `GetEncounterState` 作为唯一状态投影入口。底层直接变更服务支持可选返回 `encounter_state`，组合型 execute 服务只在最外层流程结束后统一生成一次 `encounter_state`，避免中间步骤重复投影半成品状态。

**Tech Stack:** Python 3、现有 service/repository 模式、`unittest`

---

### Task 1: 统一底层变更服务的可选 `encounter_state`

**Files:**
- Modify: `tools/services/combat/shared/update_conditions.py`
- Modify: `tools/services/combat/shared/update_encounter_notes.py`
- Modify: `tools/services/spells/encounter_cast_spell.py`
- Modify: `tools/services/encounter/manage_encounter_entities.py`
- Test: `test/test_update_conditions.py`
- Test: `test/test_update_encounter_notes.py`
- Test: `test/test_encounter_cast_spell.py`
- Test: `test/test_encounter_service.py`

- [ ] 为直接修改 encounter 的服务增加 `include_encounter_state` 或 `*_with_state` 能力。
- [ ] 保证默认行为不变。
- [ ] 为每个代表性服务补一条“返回最新 state”测试。

### Task 2: 让组合型动作只在最外层返回一次 `encounter_state`

**Files:**
- Modify: `tools/services/combat/attack/execute_attack.py`
- Modify: `tools/services/combat/save_spell/execute_save_spell.py`
- Modify: `tools/services/combat/rules/concentration/execute_concentration_check.py`
- Test: `test/test_execute_attack.py`
- Test: `test/test_execute_save_spell.py`
- Test: `test/test_concentration_check.py`

- [ ] 为组合 execute 服务增加 `include_encounter_state`。
- [ ] 只在最外层流程完成后统一调用一次 `GetEncounterState`。
- [ ] 不修改中间 request/resolve 服务的职责。

### Task 3: 全量验证

**Files:**
- Test: `test/`

- [ ] 跑相关局部测试。
- [ ] 跑全量测试，确认前端同步字段和既有战斗链路都保持稳定。
