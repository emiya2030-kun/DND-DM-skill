# Combat Runtime Skill

这个 skill 只负责战斗期运行协议.

核心原则:

1. 先读 `GetEncounterState`
2. 若战斗尚未开始,先 `initialize_encounter`,再 `RollInitiativeAndStartEncounter`
3. 每次 mutation 后都改用最新 `encounter_state`
4. 任何 `waiting_reaction` 都必须先处理
5. 回合结束固定走 `EndTurn -> AdvanceTurn -> StartTurn`

阅读顺序:

- `trpg-battle-system/combat-runtime/references/runtime-protocol.md`
- `trpg-battle-system/combat-runtime/references/tool-catalog.md`
- `trpg-battle-system/combat-runtime/references/monster-turn-flow.md`
- `trpg-battle-system/combat-runtime/references/companion-npc-turn-flow.md`
- `trpg-battle-system/combat-runtime/references/intent-examples.md`

本地页面调试:

- 当需要验证地图初始化、先攻生成、当前行动者高亮、移动刷新、攻击结算时，优先启动本地 battlemap 服务。
- 推荐流程:
  - 先启动 runtime 服务（默认 `http://127.0.0.1:8771`）。
  - 再启动 localhost battlemap，并指向 runtime：
  - `python3 scripts/run_battlemap_localhost.py --runtime-base-url http://127.0.0.1:8771 --theme forest_road`
- 开发模式默认命令:
  - `python3 scripts/run_battlemap_dev.py`
- 若只需要普通 localhost 页面而不需要热重载，可用:
  - `python3 scripts/run_battlemap_localhost.py --runtime-base-url http://127.0.0.1:8771`
- 默认启动后，应优先确认:
  - 页面能打开
  - encounter 已经过 `initialize_encounter`
  - 先攻已经过 `RollInitiativeAndStartEncounter`
  - 地图、token、先攻表、当前行动者高亮都已出现
- 若端口被占用，应先清理旧的 Python battlemap 进程，再重新启动。
