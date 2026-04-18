# Find Steed And Summon Template Design

## Goal

在现有 `trpg-battle-system` 中，先建立一套可复用的**召唤法术模板**，并以：

- `Faithful Steed`｜信实坐骑
- `Find Steed`｜寻获坐骑

作为第一张完整实例卡落地。

本轮目标不是一次做完整骑乘战斗系统，而是先把“施法后真实生成召唤实体，并进入当前遭遇战地图与实体系统”的主链稳定跑通。

## Scope

本轮完成：

1. 通用召唤法术模板
2. `Find Steed` 的专用召唤 builder
3. 召唤物写入 encounter：
   - `entities`
   - `turn_order`
   - 地图占位 / 位置
4. 再次施放时替换旧坐骑
5. 召唤物 0 HP 消失
6. 施法者死亡时坐骑消失
7. `Faithful Steed` 免费一次资源框架
8. `GetEncounterState` 可见召唤摘要
9. 对应测试

本轮不做：

- 完整骑乘战斗规则
- “施法者失能后坐骑独立行动”的高级行为
- `Life Bond`｜生命连接
- 坐骑专属附赠动作的完整执行服务
- 其他召唤法术实例
- 长休恢复入口

## Why Template First

本轮采用“先模板、后实例”的原因：

1. 现有系统已经有：
   - `spell_instances`
   - `EncounterEntity`
   - `summon` category
   - 0 HP 时移除 summon 的行为
2. `Find Steed` 不是单纯一条 spell log，而是会真实创造一个可参与战斗的实体
3. 如果只特判 `Find Steed`，后续其他召唤法术大概率会重复造轮子
4. 先抽模板后，未来 `Summon Beast`、`Summon Celestial`、死灵仆从之类都能共用壳子

## Core Rule Choice

这轮的核心设计是：

- **召唤物必须是 encounter 里的真实 entity**
- **不能只挂在 spell_instance 里当一个抽象效果**

原因：

1. 召唤物需要位置
2. 召唤物需要参与回合顺序
3. 召唤物需要被攻击、受伤、死亡
4. 地图渲染与 `GetEncounterState` 都应把它当正常战斗单位处理

也就是说，施法成功后，系统必须同时写入：

1. `encounter.spell_instances`
2. `encounter.entities[summon_id]`
3. `encounter.turn_order`

## Architecture

拆成三层：

### 1. Summon Spell Template

新增一层通用召唤模板服务，负责：

1. 校验召唤落点
2. 创建 summon runtime entity
3. 创建 spell instance
4. 把 summon 注入 encounter
5. 建立 summon 与 spell / caster 的绑定

这个模板不是直接暴露给 LLM 的顶层 action，而是作为 `ExecuteSpell` 或后续职业特性能力的内部能力。

### 2. Find Steed Builder

`Find Steed` 在模板上提供一个专用 builder，负责按：

- 施法环阶
- 坐骑生物类型：`celestial / fey / fiend`
- LLM 决定的外观字符串

生成“异界坐骑”实体数据。

这里的“马 / 骆驼 / 恐狼 / 赤鹿”等只作为**外观 flavor** 记录，不影响规则数值。

### 3. Paladin Feature Hook

在 paladin runtime 中补 `faithful_steed` 资源位：

```python
entity.class_features["paladin"]["faithful_steed"] = {
  "enabled": True,
  "free_cast_available": True,
}
```

施放 `Find Steed` 时：

1. 若该免费次数可用，则不消耗法术位，改为消耗 `free_cast_available`
2. 否则正常消耗 2 环或升环法术位

## Summon Runtime Entity

通用 summon entity 统一使用：

- `category = "summon"`
- `controller = "player"` 或沿用施法者控制方
- `side = caster.side`

并在 `source_ref` / `combat_flags` / `class_features` 中记录最小运行时元数据：

```python
source_ref = {
  "summoner_entity_id": "ent_paladin_001",
  "source_spell_id": "find_steed",
  "source_spell_instance_id": "spell_find_steed_001",
  "summon_template": "otherworldly_steed",
  "steed_type": "celestial",
  "appearance": "warhorse",
}
```

```python
combat_flags = {
  "dismiss_on_zero_hp": True,
  "dismiss_on_summoner_death": True,
  "shares_initiative_with_summoner": True,
  "controlled_mount": True,
}
```

## Encounter Integration

### Entities

施法成功后，把新 summon 写入：

```python
encounter.entities[summon.entity_id] = summon
```

### Turn Order

由于规则写明“共用你的先攻”，第一版采用：

- summon 的 `initiative = caster.initiative`
- summon 紧跟在施法者之后插入 `turn_order`

例如：

```python
["ent_paladin_001", "ent_steed_001", "ent_enemy_a"]
```

这样做的原因：

1. `turn_order` 仍保持显式实体序列
2. summon 是真实 entity，后端现有回合系统更容易接
3. 不需要现在就重写“共享先攻但不独立条目”的复杂机制

### Map Placement

召唤点由 LLM / 调用方明确传入一个未占据格。

后端负责校验：

1. 在施法 30 尺内
2. 格子未占据
3. 不与墙体 / 非法地形重叠
4. 大型体型占 2x2 时整体都合法

召唤成功后，该实体就作为地图上的正常实体参与：

- battlemap 渲染
- 距离判定
- 移动 / 攻击 / 受击

## Spell Instance Shape

`Find Steed` 仍然要记录 spell instance，因为后续需要通过它管理：

1. 旧坐骑替换
2. 召唤来源追踪
3. 后续更多召唤法术复用

建议 `special_runtime` 最小结构：

```python
"special_runtime": {
  "summon_mode": "persistent_entity",
  "summon_entity_ids": ["ent_steed_001"],
  "replace_previous_from_same_caster": True,
}
```

## Find Steed Builder

### Fixed Rules

召唤物模板名固定为：

- `Otherworldly Steed`

第一版规则字段：

- `size = "large"`
- `ac = 10 + cast_level`
- `hp.max = 5 + cast_level * 10`
- `hp.current = hp.max`
- `hp.temp = 0`
- `speed.walk = 60`
- `speed.remaining = 60`
- 若 `cast_level >= 4`：
  - 增加 `speed.fly = 60`

能力值固定：

- STR 18 / DEX 12 / CON 14 / INT 6 / WIS 12 / CHA 8

熟练加值：

- 使用施法者熟练加值

被动察觉、语言等先作为说明性字段写入 `notes` 或 `source_ref`

### Attack Shape

武器列表中挂一个通用近战攻击：

```python
{
  "id": "otherworldly_slam",
  "name": "Otherworldly Slam",
  "attack_type": "melee_weapon",
  "range": {"reach": 5},
  "ability": "spell_attack",
  "damage": {
    "formula": "1d8+cast_level",
    "damage_type": "<by steed type>"
  }
}
```

其中伤害类型由坐骑类型决定：

- `celestial -> radiant`
- `fey -> psychic`
- `fiend -> necrotic`

### Bonus Actions

第一版只把三种专属附赠动作写进 summon entity 的 `notes` / `class_features`
作为“已声明但未接执行服务”的能力摘要：

- `Fell Glare`
- `Fey Step`
- `Healing Touch`

本轮不做对应 action service。

## Replacement Rule

若同一施法者已经有一个活跃的 `find_steed` summon：

1. 再次施放时，先移除旧坐骑实体
2. 清理旧 `spell_instance` 的 summon_entity_ids
3. 再创建新坐骑

是否“重新召回同一只”与“新的一只”这种叙事层区别，本轮不做后端区分，交给 LLM 叙述。

## Dismiss Rule

### On Zero HP

召唤物 0 HP 时：

1. 触发 summon removal
2. 从 `encounter.entities` 删除
3. 从 `turn_order` 删除
4. 对应 spell instance 保留，但其 `special_runtime.summon_entity_ids` 清空或标记已失效

### On Summoner Death

施法者死亡时：

1. 查找其活跃 `find_steed` summon
2. 直接移除召唤物实体
3. 更新对应 spell instance

## LLM Responsibility Boundary

用户已经明确：

- 可选召唤外观由 LLM 理解决定

因此本轮边界是：

### 后端负责

1. 数值生成
2. 合法位置校验
3. encounter 写入
4. 替换 / 消失生命周期

### LLM 负责

1. 决定这只坐骑外观看起来像什么
2. 决定召唤时描述文本
3. 决定 `celestial / fey / fiend` 选择

## GetEncounterState Projection

需要补两块摘要：

### Paladin Summary

```python
"faithful_steed": {
  "enabled": True,
  "free_cast_available": True
}
```

### Summon Summary

在实体列表 / turn order / current_turn_entity 可直接看到 summon，因为它就是正常 entity。

另外在 `spell_instances` 的摘要里可附带：

- summon source spell
- summon entity ids

## Files To Touch

预计新增：

- `tools/services/spells/summons/create_summoned_entity.py`
- `tools/services/spells/summons/find_steed_builder.py`

预计修改：

- `tools/services/spells/execute_spell.py`
- `tools/services/spells/encounter_cast_spell.py`
- `tools/services/spells/build_spell_instance.py`
- `tools/services/class_features/shared/runtime.py`
- `tools/services/encounter/get_encounter_state.py`
- `tools/services/combat/shared/update_hp.py`

预计测试：

- `test/test_find_steed.py`
- `test/test_get_encounter_state.py`
- `test/test_update_hp.py`

## Testing

至少覆盖：

1. 施放 `Find Steed` 后会创建 summon entity
2. summon entity 会写入 `encounter.entities`
3. summon entity 会插入 `turn_order`
4. summon entity 位置合法且为大型占格
5. 同一施法者再次施法会替换旧坐骑
6. 免费施放可用时不消耗法术位
7. 免费施放用完后正常消耗法术位
8. 坐骑 0 HP 时会消失
9. 施法者死亡时坐骑消失
10. `GetEncounterState` 能看到 `faithful_steed` 摘要

## Open Follow-Ups

本轮完成后，后续最自然的延伸顺序是：

1. 为 summon 模板接第二个法术实例
2. 接坐骑专属附赠动作执行服务
3. 接骑乘战斗的受控坐骑规则
4. 接 `Life Bond`

但这些都不属于本轮范围。
