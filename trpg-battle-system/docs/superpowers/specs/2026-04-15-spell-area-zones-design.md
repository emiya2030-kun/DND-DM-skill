# Spell Area Zones Design

## 背景

当前战斗系统已经具备以下基础能力:

- `SpellRequest` / `ExecuteSpell` / `EncounterCastSpell` 组成的施法链
- `spell_instances` 作为持续法术运行态
- `EncounterMap.zones` 作为地图附着区域事实层
- 区域触发运行时:
  - `enter`
  - `start_of_turn_inside`
  - `end_of_turn_inside`
- battlemap 前端能把 `zones` 投影成地图亮区,并在右侧图例与战况记录里展示

但现在仍缺一段关键闭环:

1. 法术施放后,不能自动在地图上生成区域实例
2. `火球术` 这类范围法术虽然有范围和伤害定义,但没有统一的“落点 -> 覆盖格 -> 视觉投影”链路
3. 持续区域法术未来如果要接专注结束、回合触发、前端显示,缺少统一运行模型

因此本次设计的目标,是把“法术范围”正式接入地图区域系统.

## 目标

本次只解决遭遇战内的法术区域问题,不扩展战斗外施法.

需要满足:

1. 范围法术支持指定落点 `target_point`
2. 圆形范围法术能从落点计算覆盖格
3. 前端显示圆形覆盖层,而不是只显示方格拼块
4. 后端仍以“命中格列表”做规则结算
5. 持续区域法术与瞬时范围法术共用同一套区域模型
6. 持续区域法术可挂到 `spell_instance` 上,为后续“专注结束自动移除区域”留出口

## 非目标

这次不做:

- 战斗外施法运行态
- 复杂几何落点,例如任意浮点坐标
- 线形 / 锥形 / 立方体 / 圆柱形的完整全覆盖
- 玩家可视化拖拽选区
- 区域对物件、门、可燃地物等环境对象的完整模拟

第一版只聚焦:

- 以格子中心为落点的圆形区域
- 瞬时区域
- 持续区域

## 核心结论

### 1. 后端按“格子命中列表”结算,前端按“圆形覆盖层”渲染

规则层和视觉层分离:

- 后端:
  - 输入 `target_point`
  - 根据范围模板计算命中格列表
  - 根据命中格列表找出受影响实体
  - 执行豁免 / 伤害 / 状态 / 区域运行态更新
- 前端:
  - 使用同一个落点和半径
  - 画一个圆形 overlay
  - 再叠加已命中的格子高亮

这样可以同时保证:

- 判定稳定
- 玩家视觉自然
- 日志和地图说明统一

### 2. 第一版圆形范围以“目标格中心”为圆心

例如玩家声明:

- “火球术砸 `(3,4)`”

系统解释为:

- 落点 = `(3,4)` 这格的中心点

第一版不支持格角、半格、自由点,避免前后端接口一开始就过复杂.

### 3. 圆形命中规则使用“格中心入圈”

圆形区域覆盖格的计算方式:

1. 把半径换算为格数
2. 遍历战场格子
3. 计算“格中心”到“法术落点中心”的欧式距离
4. `distance <= radius` 则该格命中

这套规则简单、稳定、可解释,适合作为 V1.

### 4. 大体型实体按占位格判定是否命中

实体是否被法术区域命中,不只看锚点:

- 取该实体当前全部占位格
- 只要任意一个占位格落入命中格列表,即视为命中

这样和当前占位系统保持一致,不会出现大型生物站在火球里却因为锚点在外面而完全不受影响.

### 5. 区域法术统一生成“法术区域实例”

无论是瞬时还是持续:

- 都先生成一份区域实例描述
- 再决定它是:
  - 只用于本次即时结算后立即消失
  - 还是保存进 `encounter.map.zones` 持续存在

这样未来扩展别的区域法术时,不会分裂成两套实现.

## 数据设计

### 1. `target_point`

第一版结构:

```json
{
  "x": 3,
  "y": 4,
  "anchor": "cell_center"
}
```

说明:

- `x` / `y` 是目标格坐标
- `anchor` 第一版固定为 `cell_center`

后续如果要扩展格角落点,可以继续加:

- `corner_ne`
- `corner_nw`
- `corner_se`
- `corner_sw`

但本次不实现.

### 2. 法术定义里的区域模板

法术知识库新增一类可选字段:

```json
{
  "area_template": {
    "shape": "sphere",
    "radius_feet": 20,
    "render_mode": "circle_overlay",
    "persistence": "instant"
  }
}
```

或对于持续区域:

```json
{
  "area_template": {
    "shape": "sphere",
    "radius_feet": 20,
    "render_mode": "circle_overlay",
    "persistence": "sustained",
    "zone_definition_id": "fire_burn_area"
  }
}
```

字段语义:

- `shape`: 当前只支持 `sphere`
- `radius_feet`: 半径,单位尺
- `render_mode`: 前端投影方式,当前固定 `circle_overlay`
- `persistence`:
  - `instant`: 即时区域,结算后不常驻地图
  - `sustained`: 持续区域,保存到 `encounter.map.zones`
- `zone_definition_id`: 如果持续区域要复用静态区域模板,这里给出模板 id

### 3. 地图区域实例扩展

`EncounterMap.zones` 里的单个区域实例,新增统一运行元数据:

```json
{
  "zone_id": "zone_spell_fireball_001",
  "name": "火球术",
  "type": "spell_area",
  "cells": [[1, 1], [1, 2]],
  "note": "火球术爆炸覆盖区域。",
  "runtime": {
    "source_type": "spell",
    "source_spell_id": "fireball",
    "source_spell_instance_id": null,
    "source_entity_id": "ent_caster_001",
    "source_name": "米伦",
    "target_point": {
      "x": 3,
      "y": 4,
      "anchor": "cell_center"
    },
    "shape": "sphere",
    "radius_feet": 20,
    "radius_tiles": 4,
    "persistence": "instant"
  }
}
```

持续区域把 `source_spell_instance_id` 挂上对应 spell instance id.

### 4. `spell_instance` 与区域的绑定

持续区域法术生成 spell instance 时,在实例里记录绑定区域:

```json
{
  "instance_id": "spell_xxx",
  "spell_id": "moonbeam",
  "special_runtime": {
    "linked_zone_ids": ["zone_spell_moonbeam_001"]
  }
}
```

这给后续两件事留出口:

1. 专注结束时自动移除区域
2. 某些法术后续允许移动区域时,能反查对应 zone

## 规则流设计

### 1. 瞬时范围法术

以 `火球术` 为例:

1. LLM 提供:
   - `spell_id = fireball`
   - `target_point = {x, y, anchor: cell_center}`
2. `SpellRequest` 校验:
   - 法术存在
   - 施法环位合法
   - 该法术需要 `target_point`
3. `ExecuteSpell` 根据 `area_template` 计算命中格列表
4. 根据命中格列表收集命中实体
5. 对每个命中实体结算豁免与伤害
6. 生成一条瞬时区域投影数据,用于:
   - 事件日志
   - 前端圆形显示
   - `recent_activity` 摘要
7. 该区域不长期写入 `encounter.map.zones`

### 2. 持续区域法术

以未来的持续燃烧地面 / 毒云 / 月光柱类法术为例:

1. 施法时同样提供 `target_point`
2. 根据 `area_template` 计算覆盖格
3. 生成 `zone` 实例并写入 `encounter.map.zones`
4. 如果法术需要专注:
   - 同时生成 `spell_instance`
   - 在 instance 上记录 `linked_zone_ids`
5. 后续移动 / 回合开始 / 回合结束时,区域继续按现有 zone runtime 触发

### 3. 命中实体收集规则

从区域命中格到实体命中的转换:

1. 遍历 encounter 中全部实体
2. 取该实体当前占位格
3. 若其任一占位格属于区域命中格,则该实体命中
4. 同一实体只结算一次

## 前端投影设计

### 1. 地图状态新增“法术区域覆盖层”

前端 battlemap state 新增一类 overlay:

```json
{
  "overlay_id": "overlay_spell_fireball_001",
  "kind": "spell_area_circle",
  "source_spell_id": "fireball",
  "source_spell_name": "火球术",
  "target_point": {
    "x": 3,
    "y": 4,
    "anchor": "cell_center"
  },
  "radius_tiles": 4,
  "persistence": "instant"
}
```

### 2. 瞬时区域的前端行为

前端收到瞬时区域 overlay 后:

- 在地图上绘制圆形高亮
- 保持一个较短展示时间
- 然后自然淡出

如果当前阶段不做动画,也至少要在本次 `applyEncounterState` 里可见一次.

### 3. 持续区域的前端行为

持续区域:

- 继续用现有 `zones` 格子亮区渲染
- 同时可选加一个淡圆形外圈,增强视觉直觉

第一版优先级:

1. 瞬时区域圆形 overlay
2. 持续区域继续沿用格子亮区

## 服务边界

### 新增职责

建议增加一个独立的区域法术辅助模块,职责仅限:

- 读取法术 `area_template`
- 计算圆形命中格
- 构造区域实例 / overlay 描述
- 收集命中实体

不要把这些逻辑全部塞进 `ExecuteSpell`.

### 保持现有职责

- `SpellRequest`: 负责施法合法性校验
- `EncounterCastSpell`: 负责声明施法、消耗资源、生成 spell instance
- `ExecuteSpell`: 负责编排整条施法链
- `zone_effects`: 继续负责区域运行时触发

## 错误处理

以下情况需要结构化失败返回:

- 法术需要 `target_point` 但未提供
- `target_point` 超出施法距离
- `target_point` 不合法
- 法术未定义 `area_template` 却走了区域链

错误信息要让 LLM 可以直接转述给玩家,例如:

- “火球术需要指定一个落点坐标。”
- “该落点超出 150 尺施法距离。”

## 测试策略

至少覆盖:

1. 圆形命中格计算
2. 火球术以格中心落点命中正确实体
3. 大体型实体只要任一占位格入圈就算命中
4. 即时区域不会常驻 `encounter.map.zones`
5. 持续区域会写入 `encounter.map.zones`
6. 持续区域会和 `spell_instance.linked_zone_ids` 绑定
7. `get_encounter_state` 能把瞬时区域 overlay 投影给前端
8. 前端 battlemap 能渲染圆形 overlay

## 实施顺序

建议按四步实现:

1. 先做圆形范围几何计算与命中实体收集
2. 再把 `火球术` 接到瞬时区域 overlay
3. 再把持续区域法术接到 `map.zones + spell_instance`
4. 最后把前端圆形 overlay 渲染补齐

## 成功标准

完成后,系统应达到以下状态:

1. 玩家说“火球术砸 `(3,4)`”
2. LLM 可以直接把 `(3,4)` 作为 `target_point`
3. 后端正确算出圆形覆盖格和命中目标
4. 豁免 / 伤害按命中目标结算
5. 前端看到一个以 `(3,4)` 为中心的圆形法术范围显示
6. 对持续区域法术,地图会留下后续可自动触发的区域实例
