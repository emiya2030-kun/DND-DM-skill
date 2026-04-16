# Intent Examples

## 玩家说：“我移动到 7,10 再砍兽人”

1. 调 `BeginMoveEncounterEntity`
2. 若返回 `waiting_reaction`，先处理 reaction
3. 移动完成后读最新状态
4. 检查兽人是否仍在合法攻击范围
5. 调 `ExecuteAttack`

## 玩家说：“我结束回合”

1. 调 `EndTurn`
2. 调 `AdvanceTurn`
3. 调 `StartTurn`

## 怪物回合：近战怪想接近玩家

1. 读 `GetEncounterState`
2. 选择最近且可合法接近的玩家目标
3. 调 `BeginMoveEncounterEntity`
4. 移动完成后调 `ExecuteAttack`
