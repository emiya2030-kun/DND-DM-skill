# Combat Runtime Skill

这个 skill 只负责战斗期运行协议。

核心原则：

1. 先读 `GetEncounterState`
2. 若战斗尚未开始，先 `initialize_encounter`，再 `RollInitiativeAndStartEncounter`
3. 每次 mutation 后都改用最新 `encounter_state`
4. 任何 `waiting_reaction` 都必须先处理
5. 回合结束固定走 `EndTurn -> AdvanceTurn -> StartTurn`

阅读顺序：

- `references/runtime-protocol.md`
- `references/tool-catalog.md`
- `references/monster-turn-flow.md`
- `references/companion-npc-turn-flow.md`
- `references/intent-examples.md`
