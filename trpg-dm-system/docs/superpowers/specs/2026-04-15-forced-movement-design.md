# 强制位移与 Push 精通设计

## 目标

为战斗系统增加一层**通用强制位移底层能力**，用于承接：

- `push`
- 爆炸击退
- 法术推离/拉拽
- 未来其他非自愿位移效果

这层能力必须和普通移动链分开，原因很直接：

- 强制位移**不消耗移动力**
- 强制位移**不触发借机攻击**
- 强制位移不是“自愿移动”
- 强制位移未来会被多种效果复用，不应绑定在 `MoveEncounterEntity` 或 `BeginMoveEncounterEntity` 上

---

## 本次范围

本次设计只覆盖两件事：

1. 一个内部可复用的强制位移服务
2. 武器精通 `push` 如何接入这层服务

本次明确**不做**：

- 坠落与坠落伤害
- 撞墙额外伤害
- 被推入危险区域后的二次自动结算
- 拖拽/抱持的移动成本差异
- “多个同优方向时的智能寻路”
- 任何新的对外 tool

---

## 关键规则结论

### 1. 强制位移不是普通移动

强制位移与普通移动共用地图合法性校验，但不共用完整流程语义。

强制位移：

- 不消耗 `speed.remaining`
- 不使用 `dash`
- 不写入 `movement_spent_feet`
- 不触发借机攻击
- 不经过 `pending_movement / reaction_requests`

### 2. 非法时停在最后一个合法格子

用户已确定：

- 如果强制位移途中遇到墙、阻挡、非法占位或越界
- 实体停在**最后一个合法格子**
- 整次位移不报错失败

这意味着强制位移的返回结果必须是“部分成功”模型，而不是“要么全成，要么全失败”。

### 3. 体型判定仍然严格

普通移动已有的严格判定仍然保留：

- 移动后整块占位区域每一格都必须合法
- 途中每一步展开后的整块也都必须合法

因此强制位移不能只看锚点格子，也必须按实体体型展开后检查整块占位。

### 4. 困难地形不影响强制位移距离

强制位移不属于“消耗移动力”的移动。

所以本次规则定为：

- 困难地形不会让强制位移少推
- 但困难地形格子如果本身是可站立合法格，仍可被推入

### 5. 生物占位仍然阻挡终点与路径

第一版保持和普通严格移动一致：

- 不能结束在非法占位上
- 途中某一步整块占位不合法，就停止

本次不额外开放“强制位移可穿过生物”的特殊例外。

如果未来某类法术需要穿过生物，再由强制位移层新增显式参数，而不是现在预埋模糊行为。

---

## 推荐方案

采用**独立强制位移服务**，而不是给 `MoveEncounterEntity` 增加 `movement_mode="forced"`。

原因：

- 语义更干净
- 避免把“自愿移动 / 借机攻击 / 行动经济”污染到强制位移
- 方便被 `push`、法术与后续特性重复复用
- 后续如果要支持“可穿过生物但不能停留”“拉向施法者”“沿模板路径位移”，扩展点也更清晰

---

## 服务设计

### 服务名

建议新增内部服务：

`tools/services/encounter/resolve_forced_movement.py`

这是内部规则服务，不新增对 LLM 暴露的新 tool。

### 输入

第一版建议输入结构如下：

```python
resolve_forced_movement.execute(
    encounter_id="enc_001",
    entity_id="ent_enemy_orc_001",
    path=[
        {"x": 7, "y": 5},
        {"x": 8, "y": 5},
    ],
    reason="weapon_mastery_push",
    source_entity_id="ent_ally_eric_001",
)
```

说明：

- `path`
  - 由调用方预先算好“尝试位移到哪些锚点”
  - 服务本身只负责逐步校验与推进
- `reason`
  - 用于事件记录与调试
- `source_entity_id`
  - 可选，但建议保留
  - 方便未来追踪“是谁把目标推开的”

第一版不让底层自己算方向，避免把“规则执行”和“效果选格”耦合在一起。

### 输出

返回结构建议为：

```python
{
  "encounter_id": "enc_001",
  "entity_id": "ent_enemy_orc_001",
  "start_position": {"x": 6, "y": 5},
  "final_position": {"x": 7, "y": 5},
  "attempted_path": [
    {"x": 7, "y": 5},
    {"x": 8, "y": 5}
  ],
  "resolved_path": [
    {"x": 7, "y": 5}
  ],
  "moved_feet": 5,
  "stopped_early": true,
  "blocked": true,
  "block_reason": "occupied_tile",
  "reason": "weapon_mastery_push",
  "source_entity_id": "ent_ally_eric_001"
}
```

其中：

- `attempted_path`
  - 调用方希望尝试的完整路径
- `resolved_path`
  - 实际成功推进的路径
- `moved_feet`
  - 实际位移尺数
- `blocked`
  - 是否因非法步骤中断
- `block_reason`
  - 第一版建议复用已有移动校验原因，统一成：
    - `out_of_bounds`
    - `wall`
    - `occupied_tile`
    - `invalid_terrain`
    - `blocked_unknown`

### 行为

服务按以下顺序执行：

1. 读取 encounter 与实体
2. 记录起点
3. 对 `path` 逐步尝试推进
4. 每一步都复用现有地图/占位合法性判定
5. 一旦某一步非法：
   - 停止继续尝试
   - 实体停在上一格合法位置
6. 保存 encounter
7. 追加事件
8. 返回结构化结果

---

## 与现有移动规则的关系

### 复用的部分

应尽量复用已有移动规则中的这些能力：

- 地图边界检查
- 墙壁/阻挡检查
- 整块占位展开
- 大体型/小体型锚点与中心点逻辑

### 不复用的部分

不应直接复用普通移动完整入口中的这些流程：

- 速度消耗
- `use_dash`
- 困难地形移动力换算
- 借机攻击触发
- `pending_movement`
- `reaction_requests`

结论：

- **复用校验逻辑**
- **不要复用普通移动编排逻辑**

---

## Push 的接入设计

### 规则目标

`push`：当武器命中一个体型不超过大型的生物时，可以将其**沿直线推离至多 10 尺**。

第一版按最小稳定实现：

- 只处理“最多 10 尺推离”
- 体型大于 Large 时直接无效
- 路线按“远离攻击者中心点”的方向逐格生成
- 若中途被阻挡，只移动已成功的那部分

### 为什么 Push 不自己改坐标

因为 `push` 不是一个单独的坐标改写特例，它本质上就是“命中后触发一次强制位移”。

如果直接在 `weapon_mastery_effects.py` 里手写坐标修改：

- 会重复地图合法性逻辑
- 会跳过大体型整块检查
- 未来其他强制位移又要再写一遍

所以 `push` 应只做两件事：

1. 计算想尝试的推离路径
2. 调用 `resolve_forced_movement`

### Push 的路径生成

第一版建议：

- 取攻击者中心点
- 取目标当前中心点
- 计算“从攻击者指向目标”的离开方向
- 按该方向生成最多 2 格候选锚点

例如：

- 攻击者在 `(5,5)`
- 目标在 `(6,5)`
- 则尝试路径为：
  - `(7,5)`
  - `(8,5)`

如果是斜向关系：

- 攻击者在 `(5,5)`
- 目标在 `(6,6)`
- 则尝试路径为：
  - `(7,7)`
  - `(8,8)`

第一版不做复杂“多方向择优”。

只要方向计算稳定、可预测即可。

### Push 在 ExecuteAttack 内的表现

当命中且武器精通是 `push` 时：

- 内部调用强制位移服务
- 不新增新 tool
- 把结果写入：

```python
resolution["weapon_mastery_updates"]["push"] = {
  "status": "resolved",
  "target_entity_id": "...",
  "moved_feet": 10,
  "start_position": {"x": 6, "y": 5},
  "final_position": {"x": 8, "y": 5},
  "blocked": false
}
```

若体型不合法：

```python
resolution["weapon_mastery_updates"]["push"] = {
  "status": "no_effect",
  "reason": "target_too_large"
}
```

若只能推开 5 尺：

```python
resolution["weapon_mastery_updates"]["push"] = {
  "status": "resolved",
  "moved_feet": 5,
  "blocked": true,
  "block_reason": "wall",
  ...
}
```

---

## 事件记录

建议新增一种内部事件：

- `forced_movement_resolved`

最小 payload：

```json
{
  "reason": "weapon_mastery_push",
  "source_entity_id": "ent_ally_eric_001",
  "target_entity_id": "ent_enemy_orc_001",
  "from_position": {"x": 6, "y": 5},
  "to_position": {"x": 7, "y": 5},
  "attempted_path": [
    {"x": 7, "y": 5},
    {"x": 8, "y": 5}
  ],
  "resolved_path": [
    {"x": 7, "y": 5}
  ],
  "moved_feet": 5,
  "blocked": true,
  "block_reason": "occupied_tile"
}
```

这样后续页面刷新、日志记录和调试都能直接复用。

---

## 测试范围

第一批测试至少覆盖：

1. **完整推开 10 尺**
- `push` 命中后目标成功移动 2 格

2. **中途撞墙只移动 5 尺**
- 第 2 格非法，停在第 1 格

3. **第一步就非法则原地不动**
- 返回 `blocked = true`
- `moved_feet = 0`

4. **大型以上目标不受 Push 影响**
- 返回 `no_effect`

5. **强制位移不消耗速度**
- `speed.remaining` 不变化
- `movement_spent_feet` 不变化

6. **强制位移不生成借机攻击请求**
- `reaction_requests` 不新增
- `pending_movement` 不写入

7. **大体型实体整块占位仍严格检查**
- 某一步锚点合法但展开后不合法时，必须停止

---

## 实现顺序

建议顺序：

1. 先抽出可复用的强制位移服务
2. 先写底层测试，确认“不消耗移动力、不触发借机、遇阻停下”
3. 再把 `push` 接到 `weapon_mastery_effects.py`
4. 最后补 `ExecuteAttack` 集成测试

这样可以避免一上来把 `push` 和底层规则绑死。

---

## 最终结论

本次应新增一个**内部强制位移服务**，专门处理：

- 逐步推进
- 每步合法性校验
- 遇阻停在最后合法位置
- 不消耗移动力
- 不触发借机攻击

然后让 `push` 作为其第一个调用方接入。

这能保证：

- 当前 `push` 实现最小且稳定
- 后续法术/爆炸/击退不会重复造轮子
- 普通移动链保持干净，不会被强制位移语义污染
