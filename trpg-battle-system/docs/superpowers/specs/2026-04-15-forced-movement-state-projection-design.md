# 强制位移状态投影与前端展示设计

## 目标

把已经落地的强制位移运行结果继续投影到两层消费面：

1. **LLM 可读状态**
   - 能直接看到最近一次强制位移的中文摘要
   - 例如：`钢铁蛮兵被 Push 推离 10 尺，移动到 (8,14)。`

2. **玩家前端**
   - 不显示这句中文摘要
   - 只在地图上高亮最近一次强制位移的轨迹

这次的目标不是做完整战报系统，而是把 `push` 的结果从“后端内部结算”变成“状态里可读、地图上可见”。

---

## 本次范围

本次只做：

- `GetEncounterState` 投影最近一次强制位移
- `RenderBattlemapView` 读取该投影并画地图轨迹高亮
- localhost 页面在收到新的 `encounter_state` 后能立即看到高亮

本次明确**不做**：

- 多条历史战报列表
- 前端单独的“战斗日志面板”
- 自动消退动画
- 多次强制位移同时叠加显示
- 把 LLM 摘要直接显示给玩家

---

## 关键规则结论

### 1. LLM 和玩家看到的不是同一份文案

用户已明确：

- 类似“钢铁蛮兵被 Push 推离 10 尺，移动到 (8,14)”这种句子
- **只给 LLM 看**
- 不直接显示在玩家 UI 上

因此需要把“结构化摘要”和“地图渲染层”分开。

### 2. 第一版只投影最近一次强制位移

为了保持状态简单，第一版只取最近一次 `forced_movement_resolved` 事件。

如果一次攻击或一次状态刷新之前发生过多次强制位移：

- encounter state 里只投影最新的一条
- 地图也只高亮最新的一条

### 3. 前端高亮来自状态投影，不直接扫事件日志

不建议让前端自己遍历事件日志找 `forced_movement_resolved`。

原因：

- 前端会耦合底层事件结构
- 中文摘要逻辑会分散到前端
- 未来如果事件 payload 变化，前端也会一起破

因此应由 `GetEncounterState` 先把结果整理成一个稳定字段，再交给地图渲染。

---

## 推荐方案

采用**状态投影字段 + 地图高亮层**：

1. `GetEncounterState`
   - 新增 `recent_forced_movement`
   - 只给 LLM 和宿主层读取

2. `RenderBattlemapView`
   - 读取 `recent_forced_movement`
   - 在地图中对起点、路径、终点做高亮

这是最小且稳定的方案。

---

## 状态投影设计

### 新字段

在 `GetEncounterState.execute()` 返回对象顶层新增：

```json
{
  "recent_forced_movement": {
    "reason": "weapon_mastery_push",
    "source_entity_id": "ent_ally_001",
    "source_name": "Eric",
    "target_entity_id": "ent_enemy_001",
    "target_name": "钢铁蛮兵",
    "start_position": {"x": 6, "y": 14},
    "final_position": {"x": 8, "y": 14},
    "attempted_path": [
      {"x": 7, "y": 14},
      {"x": 8, "y": 14}
    ],
    "resolved_path": [
      {"x": 7, "y": 14},
      {"x": 8, "y": 14}
    ],
    "moved_feet": 10,
    "blocked": false,
    "block_reason": null,
    "summary": "钢铁蛮兵被 Push 推离 10 尺，移动到 (8,14)。"
  }
}
```

如果没有最近强制位移，则：

```json
{
  "recent_forced_movement": null
}
```

### 字段来源

该字段来源于最近一条 `forced_movement_resolved` 事件。

从事件 payload 中读取：

- `reason`
- `source_entity_id`
- `target_entity_id`
- `from_position`
- `to_position`
- `attempted_path`
- `resolved_path`
- `moved_feet`
- `blocked`
- `block_reason`

然后在投影层补齐：

- `source_name`
- `target_name`
- `summary`

### 摘要生成规则

第一版只处理 `weapon_mastery_push` 的中文摘要。

格式固定：

- 成功完整位移：
  - `钢铁蛮兵被 Push 推离 10 尺，移动到 (8,14)。`
- 中途被阻挡：
  - `钢铁蛮兵被 Push 推离 5 尺，移动到 (7,14)，随后被墙壁阻挡。`
- 原地未推动：
  - `钢铁蛮兵尝试被 Push 推离，但被墙壁阻挡，位置未改变。`

如果 `reason` 不是当前已知类型：

- 退化成通用摘要
- 例如：
  - `钢铁蛮兵发生了强制位移，最终到达 (8,14)。`

这样以后法术击退接进来时，不会因为缺少文案模板而直接坏掉。

---

## 前端展示设计

### 展示原则

玩家只看地图，不看 LLM 摘要。

因此前端只消费这些信息：

- `start_position`
- `resolved_path`
- `final_position`
- `blocked`

### 地图高亮层

`RenderBattlemapView` 在生成格子 HTML 时：

- 起点格增加 `tile--forced-origin`
- 经过路径增加 `tile--forced-path`
- 终点格增加 `tile--forced-destination`

如果起点和终点相同：

- 只渲染起点/终点的单格高亮

如果 `resolved_path` 为空：

- 仍可在起点格显示“受阻”态
- 但不画路径

### 图例说明

为了避免玩家看不懂亮线，图例中增加一条非常短的说明：

- `亮色轨迹：最近一次强制位移`

这里只解释“这是什么”，不解释详细战报。

### 样式方向

第一版建议：

- 起点：偏金色描边
- 路径：偏青蓝发光
- 终点：偏亮白或亮青强调
- 被阻挡时：终点或起点额外带一层暖色告警边框

这样能和现有地形色、区域色区分开。

---

## 边界情况

### 1. 最近强制位移对应的实体已不存在

如果 `source_entity_id` 或 `target_entity_id` 已找不到：

- 不报错
- `source_name` / `target_name` 退化成事件里已有名称或“未知单位”
- 地图高亮仍按坐标显示

### 2. 强制位移发生后地图立即又被别的操作刷新

只要新的 encounter state 里仍然没有更新的强制位移事件：

- 高亮就继续存在

如果后续状态已经有更晚的新强制位移：

- 新的一条覆盖旧的一条

也就是说，第一版行为明确为：

- **最近一次强制位移高亮会持续保留**
- **直到下一次强制位移发生后才被覆盖**
- 普通的其他状态刷新不会主动清掉它

### 3. 没有强制位移

- `recent_forced_movement = null`
- 地图不添加任何强制位移高亮 class

---

## 文件边界

### `tools/services/encounter/get_encounter_state.py`

负责：

- 找出最近一次 `forced_movement_resolved` 事件
- 整理成稳定结构
- 生成 LLM 摘要

不负责：

- 拼 HTML
- 决定具体颜色和 CSS 类名

### `tools/services/map/render_battlemap_view.py`

负责：

- 读取 `recent_forced_movement`
- 决定哪些格子加高亮 class
- 更新图例里的短说明

不负责：

- 生成中文摘要
- 自己遍历事件仓储

---

## 测试范围

至少补这些测试：

1. `GetEncounterState` 会投影最近一次强制位移
2. `summary` 对 `weapon_mastery_push` 生成正确中文句子
3. 无强制位移时返回 `null`
4. `RenderBattlemapView` 对起点/路径/终点输出对应 class
5. 被阻挡且未移动时，只显示单点受阻高亮，不画路径

---

## 最终结论

本次应增加一个新的 encounter state 投影字段：

- `recent_forced_movement`

它负责把最近一次强制位移整理成：

- LLM 可直接读的结构化摘要
- 地图渲染可直接消费的路径数据

然后由地图层只渲染轨迹高亮，不显示文字战报。

这样既满足：

- LLM 理解战斗结果
- 玩家持续看大地图

又不会把详细规则说明塞进玩家 UI。
