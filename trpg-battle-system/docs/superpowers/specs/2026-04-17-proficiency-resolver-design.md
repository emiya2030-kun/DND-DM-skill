# 通用熟练解析层设计

## 目标

把职业带来的战斗熟练从各个具体解析器里抽出来，统一放到一个内部通用解析层。

本轮只覆盖两类：

- `weapon_proficiencies`
- `armor_training`

这层只给后端运行时使用，不新增前端展示字段，也不要求 LLM 看到职业熟练明细。

## 当前问题

现在有两处职业规则是分散写死的：

- `WeaponProfileResolver` 内部知道 `fighter` 自动有 `simple / martial`
- `ArmorProfileResolver` 内部知道 `fighter` 自动有 `light / medium / heavy / shield`

这会带来三个问题：

1. 职业规则散在武器链和护甲链里
2. 后续加别的职业时，要改两个地方
3. `GetEncounterState` 如果也想展示“武器是否熟练”，就容易和后端真实判定分叉

## 设计结论

新增一个内部模块：

- `tools/services/class_features/shared/proficiency_resolver.py`

职责只有一个：

- 根据 `entity.class_features` 解析出战斗熟练结果

输出结构固定为：

```python
{
    "weapon_proficiencies": [...],
    "armor_training": [...],
}
```

## 第一版规则范围

第一版只实现战士默认熟练：

- 武器熟练：`simple`、`martial`
- 护甲受训：`light`、`medium`、`heavy`、`shield`

同时支持显式配置覆盖：

- `class_features["fighter"]["weapon_proficiencies"]`
- `class_features["fighter"]["armor_training"]`

合并规则：

- 先给战士默认值
- 再并入显式配置
- 去重
- 按固定顺序输出

固定顺序：

- `weapon_proficiencies`: `simple`, `martial`, 其余按字母序
- `armor_training`: `light`, `medium`, `heavy`, `shield`, 其余按字母序

## 调用方式

### WeaponProfileResolver

不再自己识别 `fighter`。

改成：

1. 调 `resolve_entity_proficiencies(actor)`
2. 拿到 `weapon_proficiencies`
3. 用武器 `category` 判断是否熟练

仍然保留现有优先级：

1. `runtime_weapon.is_proficient` 显式布尔值优先
2. 否则用通用熟练解析结果判断
3. 最后才走旧的 legacy 默认熟练兼容

### ArmorProfileResolver

不再自己识别 `fighter`。

改成：

1. 调 `resolve_entity_proficiencies(actor)`
2. 拿到 `armor_training`
3. 判断护甲/盾牌是否受训

这样 AC、未受训护甲惩罚、盾牌 AC 是否生效，都依赖同一份熟练结果。

## 对外边界

这层不新增前端必须看到的职业熟练明细。

保留现有用户真正需要的结果：

- `ac` 正常计算
- 武器列表里的 `is_proficient` 正确

因此：

- `GetEncounterState` 不新增 `armor_training`
- 不要求把 `weapon_proficiencies` 原样投影给前端
- 如果当前武器视图已经有 `is_proficient`，继续保留

## 示例

输入：

```json
{
  "fighter": {
    "level": 1
  }
}
```

内部解析结果：

```json
{
  "weapon_proficiencies": ["simple", "martial"],
  "armor_training": ["light", "medium", "heavy", "shield"]
}
```

武器链最终只消费：

```json
{
  "weapon_id": "longsword",
  "category": "martial",
  "is_proficient": true
}
```

护甲链最终只消费：

```json
{
  "equipped_armor": "chain_mail",
  "equipped_shield": "shield",
  "armor_trained": true,
  "shield_trained": true,
  "current_ac": 18
}
```

## 测试范围

至少覆盖：

1. `fighter` 默认解析出武器熟练与护甲受训
2. 显式配置会并入默认值
3. `WeaponProfileResolver` 改走通用解析层后行为不变
4. `ArmorProfileResolver` 改走通用解析层后行为不变
5. `GetEncounterState` 仍只暴露 `is_proficient` 与正确 AC，不额外暴露职业熟练列表

## 不做的内容

本轮不做：

- 其他职业
- `save_proficiencies`
- `skill_proficiencies`
- 更大的职业总运行时解析器

原因很简单：现在只需要把战斗里真正共用的两类熟练抽干净，不扩大范围。
