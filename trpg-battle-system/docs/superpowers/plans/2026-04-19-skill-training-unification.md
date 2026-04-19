# Skill Training Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把技能熟练/专精统一到 `EncounterEntity.skill_training`，并让角色卡、检定和预览数据全部改读新字段。

**Architecture:** 在模型层加入正式字段和旧数据迁移；服务层只消费新字段；测试和预览数据全部切换，防止继续写回旧结构。

**Tech Stack:** Python dataclasses、unittest、本地 localhost battlemap 预览

---

### Task 1: 锁定失败测试

**Files:**
- Test: `test/test_models.py`
- Test: `test/test_get_encounter_state.py`
- Test: `test/test_resolve_ability_check.py`

- [ ] Step 1: 运行最小测试集合并记录红灯
- [ ] Step 2: 以失败测试为边界实施模型和服务改动

### Task 2: 统一模型字段

**Files:**
- Modify: `tools/models/encounter_entity.py`
- Modify: `app/models/encounter_entity.py`

- [ ] Step 1: 添加 `skill_training` 字段和合法性校验
- [ ] Step 2: 在 `from_dict` / `__post_init__` 中迁移 `source_ref.skill_training`
- [ ] Step 3: 在 `to_dict` 中只输出新字段

### Task 3: 切换服务读取

**Files:**
- Modify: `tools/services/encounter/get_encounter_state.py`
- Modify: `tools/services/checks/resolve_ability_check.py`
- Modify: `tools/services/class_features/shared/proficiency_resolver.py`

- [ ] Step 1: 角色卡熟练标记只读 `skill_training`
- [ ] Step 2: 技能检定熟练/专精只读 `skill_training`
- [ ] Step 3: 保留职业 runtime 其他职责，不再承担技能专精事实源

### Task 4: 切换预览与测试数据

**Files:**
- Modify: `scripts/run_battlemap_localhost.py`
- Modify: `test/test_resolve_ability_check.py`
- Modify: 其他命中旧字段的测试数据文件

- [ ] Step 1: 预览米伦数据迁到正式字段
- [ ] Step 2: 删除测试中 `source_ref.skill_proficiencies` 依赖

### Task 5: 回归验证

**Files:**
- Test: `test/test_models.py`
- Test: `test/test_get_encounter_state.py`
- Test: `test/test_resolve_ability_check.py`
- Test: `test/test_run_battlemap_localhost.py`

- [ ] Step 1: 运行相关 unittest 套件
- [ ] Step 2: 如有必要重启 `8766` 预览服务验证角色卡数据
