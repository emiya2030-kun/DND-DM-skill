# Skill Training Unification Design

**Goal:** 将技能熟练/专精统一为 `EncounterEntity.skill_training` 单一正式字段，并移除角色卡与检定逻辑对旧来源字段和运行时反推的依赖。

**Scope:** 仅覆盖实体模型、旧数据迁移、角色卡投影、技能检定解析、localhost 预览种子与相关测试。不重构无关职业运行时结构。

## Data Model

- `EncounterEntity.skill_training` 为 `dict[str, str]`
- 允许值只有 `none`、`proficient`、`expertise`
- `skill_modifiers` 只表示最终技能修正值，不再承担熟练来源语义

## Migration

- 读取旧数据时，如果正式字段为空且 `source_ref.skill_training` 存在，则迁移到 `skill_training`
- 迁移后从 `source_ref` 中移除该旧键，避免双写继续扩散
- 序列化时只写 `skill_training`

## Runtime Behavior

- 角色卡熟练标记只读 `entity.skill_training`
- 技能检定的熟练/专精判断只读 `entity.skill_training`
- 职业 runtime 中保留其他能力状态；不再作为技能专精事实源

## Validation

- 模型 roundtrip 测试覆盖新字段和旧数据迁移
- 技能检定测试覆盖 `none / proficient / expertise`
- localhost 预览与角色卡测试改用新字段
