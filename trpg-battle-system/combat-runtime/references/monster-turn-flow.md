# Monster Turn Flow

1. 回合开始先读 `GetEncounterState`
2. 识别当前可合法影响的目标
3. 优先选择能立即击倒、高威胁、或能多目标命中的动作
4. 如需移动，先 `BeginMoveEncounterEntity`
5. 如遇 `waiting_reaction`，先停下处理
6. 移动完成后重新检查目标合法性
7. 攻击或施法
8. 结束回合时走 `EndTurn -> AdvanceTurn -> StartTurn`
