# Tool Catalog

## initialize_encounter

- 用途：把 LLM 决定好的地图和参战实体写入 encounter
- 何时调用：战斗开始但尚未开战时
- 下一步：刷新页面，然后调用 `RollInitiativeAndStartEncounter`

## RollInitiativeAndStartEncounter

- 用途：为当前 encounter 中全部参战实体掷先攻并正式开始第一回合
- 何时调用：`initialize_encounter` 完成后
- 下一步：向玩家播报 `initiative_results`

## GetEncounterState

- 用途：读取唯一事实源投影
- 何时调用：任何行动决策前，以及每次 mutation 后需要继续决策时

## BeginMoveEncounterEntity

- 用途：启动一次合法移动判定
- 何时调用：任何主动移动前
- 特殊返回：`waiting_reaction`

## ContinuePendingMovement

- 用途：reaction 处理完后继续未完成移动

## ResolveReactionRequest

- 用途：结算等待中的 reaction request

## ExecuteAttack

- 用途：执行一次攻击动作
- 前提：目标、范围、动作资源都仍合法

## ExecuteSpell

- 用途：执行一次法术动作
- 前提：法术、目标、法术位/资源都仍合法

## EndTurn / AdvanceTurn / StartTurn

- `EndTurn`：结束当前回合
- `AdvanceTurn`：推进先攻顺序
- `StartTurn`：开始下一位回合
