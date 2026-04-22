# Player Character Builder Design

## Goal

提供一个统一的玩家角色构筑入口，把角色定义转换为标准 `EncounterEntity`，避免手工拼接职业、熟练、法术和资源字段。

## Scope

第一阶段只覆盖玩家角色模板：

- 输入来源：`entity_definitions.json` 中的 PC 模板
- 新字段：`character_build`
- 输出：标准 `EncounterEntity`
- 接入点：`EncounterService._build_entity_from_template`

不在本阶段处理：

- 怪物模板统一 builder
- 召唤物模板统一 builder
- 完整前端角色编辑器
- 旧 encounter 存量数据批量迁移

## Approach

新增 `PlayerCharacterBuilder`：

1. 读取 `character_build.classes`
2. 生成 `class_features.<class>.level`
3. 计算 `ability_mods`
4. 计算 `proficiency_bonus`
5. 设置 `initial_class_name`
6. 补 `source_ref.class_name` 与 `source_ref.level`
7. 为法术补 `casting_class`
8. 交给 `EncounterEntity.from_dict`
9. 再调用现有运行时 helper：
   - `resolve_entity_save_proficiencies`
   - `ensure_spell_slots_runtime`

这样可以复用现有的职业熟练模板、法术位推导和施法 schema 标准化逻辑。

## Data Shape

建议的最小 `character_build`：

```json
{
  "classes": [
    {"class_id": "wizard", "level": 5}
  ],
  "initial_class_name": "wizard"
}
```

后续可扩展：

- `primary_class_name`
- `skill_training`
- `expertise`
- `equipment_packages`
- `prepared_spells`
- `subclass`

## Compatibility

- PC 模板有 `character_build`：走 builder
- PC 模板没有 `character_build`：保持旧模板直转
- 非 PC 模板：保持旧路径

## Verification

至少覆盖：

- builder 能推导等级、熟练加值、豁免熟练、法术位、施法职业
- `EncounterService` 在 PC 模板链路上确实调用 builder
- 施法合法性相关旧测试不回归
