# 职业熟练模板层设计

## 目标

在现有内部通用熟练解析层之上，再加一层“职业熟练模板知识库”，把职业自动给予的三类战斗熟练统一放进静态模板：

- `weapon_proficiencies`
- `armor_training`
- `save_proficiencies`

这轮的最终效果是：

1. 后端知道“各职业默认给什么熟练”
2. `resolve_entity_proficiencies(entity)` 统一从职业模板解析运行时熟练
3. 武器链继续读 `weapon_proficiencies`
4. 护甲链继续读 `armor_training`
5. 豁免链开始读 `save_proficiencies`
6. 前端 / LLM 仍然只看到结算后的结果，不看到职业模板本身

## 当前问题

现在系统已经有：

- 共享运行时熟练解析层 `resolve_entity_proficiencies`
- 武器链与护甲链已经开始依赖它

但它目前只有一条硬逻辑：

- `fighter` 默认给：
  - `simple`
  - `martial`
  - `light`
  - `medium`
  - `heavy`
  - `shield`

同时，`save_proficiencies` 仍然分散在多个地方直接读实体字段，例如：

- `ResolveSavingThrow`
- `resolve_concentration_check`
- `turn_effects`
- `cast_interrupt_contest`

这会导致：

1. 运行时默认熟练仍有一部分写死
2. 职业模板不能统一扩到别的职业
3. 豁免熟练没有接入这套统一来源

## 设计结论

新增一份静态职业熟练模板知识库与 repository：

- `data/knowledge/class_proficiency_definitions.json`
- `tools/repositories/class_proficiency_definition_repository.py`

并扩展现有：

- `tools/services/class_features/shared/proficiency_resolver.py`

让它不再手写 fighter 默认值，而是：

1. 识别实体有哪些职业 bucket
2. 去职业熟练模板仓库里取默认熟练
3. 再合并 entity 上的显式覆写
4. 输出统一结构：

```python
{
    "weapon_proficiencies": [...],
    "armor_training": [...],
    "save_proficiencies": [...],
}
```

## 知识库范围

这轮知识库直接放“全职业静态模板”，但只放熟练，不放职业能力。

职业范围先按 5e 2024 常见全职业模板准备：

- `barbarian`
- `bard`
- `cleric`
- `druid`
- `fighter`
- `monk`
- `paladin`
- `ranger`
- `rogue`
- `sorcerer`
- `warlock`
- `wizard`

每个职业模板只保留：

- `class_id`
- `name`
- `weapon_proficiencies`
- `armor_training`
- `save_proficiencies`

示例：

```json
{
  "class_id": "fighter",
  "name": "Fighter",
  "weapon_proficiencies": ["simple", "martial"],
  "armor_training": ["light", "medium", "heavy", "shield"],
  "save_proficiencies": ["str", "con"]
}
```

## 运行时解析规则

`resolve_entity_proficiencies(entity)` 继续是唯一入口。

### 输入来源

优先从 `entity.class_features` 中识别职业 bucket，例如：

```json
{
  "fighter": {...},
  "wizard": {...}
}
```

只要 bucket 存在，就视为该实体拥有这个职业模板。

### 合并顺序

对每个识别到的职业：

1. 读职业模板默认熟练
2. 合并 entity 该职业 bucket 里的显式覆写

例如：

- `class_features["fighter"]["weapon_proficiencies"]`
- `class_features["fighter"]["armor_training"]`
- `class_features["fighter"]["save_proficiencies"]`

### 归一化规则

所有字符串统一：

- `strip()`
- `lower()`

### 排序规则

输出需要保持稳定顺序，避免测试和投影反复抖动。

- `weapon_proficiencies`
  - 固定优先：`simple`, `martial`
  - 其余按字母序
- `armor_training`
  - 固定优先：`light`, `medium`, `heavy`, `shield`
  - 其余按字母序
- `save_proficiencies`
  - 固定优先：`str`, `dex`, `con`, `int`, `wis`, `cha`
  - 其余按字母序

## 各消费方接法

### 1. WeaponProfileResolver

保持现在做法：

- 继续读 `resolve_entity_proficiencies(actor)["weapon_proficiencies"]`
- 继续保留 `runtime_weapon.is_proficient` 显式优先
- 继续保留 legacy fallback

### 2. ArmorProfileResolver

保持现在做法：

- 继续读 `resolve_entity_proficiencies(actor)["armor_training"]`

### 3. ResolveSavingThrow

新增统一读取：

- 不再只看 `target.save_proficiencies`
- 改成合并使用：
  - `resolve_entity_proficiencies(target)["save_proficiencies"]`
  - 再兼容 entity 上显式已有的 `target.save_proficiencies`

原因是这轮不能粗暴切断旧存档和旧测试。

所以最终判定规则是：

```python
resolved_saves = set(resolve_entity_proficiencies(target)["save_proficiencies"])
entity_saves = set(normalized target.save_proficiencies)
all_save_proficiencies = resolved_saves | entity_saves
```

### 4. 其他直接读 `entity.save_proficiencies` 的地方

这轮一并收口到一个共享 helper，例如：

- `resolve_entity_save_proficiencies(entity)`

让：

- `resolve_concentration_check`
- `turn_effects`
- `cast_interrupt_contest`

这些逻辑统一调用，不再各自直接读裸字段。

## 对外边界

前端 / LLM 不看职业模板，也不看原始熟练列表。

它们只看到：

- 武器是否熟练
- AC 是否正确
- 某次豁免是否加了熟练后的最终结果

所以这轮不新增任何新的前端职业熟练展示字段。

## 兼容策略

这轮必须兼容旧数据和旧测试。

因此：

1. 旧实体上已经写死的 `save_proficiencies` 仍然有效
2. 新职业模板只是补充默认来源
3. 如果 entity 显式配置了同类熟练，按并集处理

这样可以逐步把“写死在实体里的默认职业熟练”迁走，而不是一次性打断所有旧数据。

## 测试范围

至少覆盖：

1. 职业熟练模板仓库可读取全职业模板
2. `resolve_entity_proficiencies` 能返回：
   - `weapon_proficiencies`
   - `armor_training`
   - `save_proficiencies`
3. fighter / wizard / rogue 这类典型职业的默认豁免熟练正确
4. mixed-case 显式覆写会被归一化
5. `ResolveSavingThrow` 会因为职业模板自动获得豁免熟练
6. 旧的 `entity.save_proficiencies` 仍然兼容
7. 前端状态仍不泄漏职业熟练明细

## 不做的内容

这轮不做：

- 职业能力模板统一仓库
- 技能熟练
- 专长
- 多职业复杂优先级规则的高阶裁定

这里只做“静态职业熟练模板 + 三类战斗熟练”。

## 例子

一个只有：

```json
{
  "class_features": {
    "fighter": {
      "level": 5
    }
  }
}
```

的实体，内部解析结果会是：

```json
{
  "weapon_proficiencies": ["simple", "martial"],
  "armor_training": ["light", "medium", "heavy", "shield"],
  "save_proficiencies": ["str", "con"]
}
```

一个只有：

```json
{
  "class_features": {
    "wizard": {
      "level": 5
    }
  }
}
```

的实体，内部解析结果会是：

```json
{
  "weapon_proficiencies": ["simple"],
  "armor_training": [],
  "save_proficiencies": ["int", "wis"]
}
```

而前端看到的依旧只是：

```json
{
  "ac": 14,
  "available_actions": {
    "weapons": [
      {
        "weapon_id": "dagger",
        "is_proficient": true
      }
    ]
  }
}
```
