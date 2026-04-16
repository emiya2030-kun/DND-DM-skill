# Runtime Protocol

## 战斗开始

1. LLM 决定战场和参战者
2. 调 `initialize_encounter`
3. 页面刷新
4. 调 `RollInitiativeAndStartEncounter`
5. 向玩家播报 `initiative_results`
6. 宣布 `turn_order` 与当前行动者

## 战斗循环

1. 读 `GetEncounterState`
2. 判断当前行动者
3. 玩家回合时等待玩家明确行动
4. 怪物/NPC 回合时按对应 flow 自主决策
5. 每次状态变更后改用最新 `encounter_state`

## 硬性禁令

- 不手工改 HP、位置、condition、resources、turn order
- 不跳过 `waiting_reaction`
- 不在移动未完成前提前结算后续动作
- 不用旧状态继续推理
