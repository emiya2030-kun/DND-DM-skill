# Combat Runtime Skill

这个 skill 只负责战斗期运行协议.

核心原则:

1. 先读 `GetEncounterState`
2. 若战斗尚未开始,先 `initialize_encounter`,再 `RollInitiativeAndStartEncounter`
3. 每次 mutation 后都改用最新 `encounter_state`
4. 任何 `waiting_reaction` 都必须先处理
5. 回合结束固定走 `EndTurn -> AdvanceTurn -> StartTurn`

常用 runtime command:

- `execute_attack`
  - 用途: 原地普通攻击、轻型额外攻击、投掷攻击、借机攻击
  - 必填参数:
    - `encounter_id`
    - `actor_id`
    - `target_id`
    - `weapon_id`
  - 常用可选参数:
    - `attack_mode`: `default` / `light_bonus` / `thrown`
    - `allow_out_of_turn_actor`: 借机攻击等回合外攻击时设为 `true`
    - `consume_action`: 普通攻击通常为 `true`
    - `consume_reaction`: 借机攻击通常为 `true`
    - `zero_hp_intent`: 例如 `knockout`
  - 默认行为:
    - 若不手传攻击骰与伤害骰,后端会自动掷攻击骰与伤害骰
    - 返回 `attack_result` 与最新 `encounter_state`
  - 普通攻击例子:
    - `{"command":"execute_attack","args":{"encounter_id":"enc_preview_demo","actor_id":"pc_sabur","target_id":"enemy_raider_1","weapon_id":"longbow"}}`
  - 轻型额外攻击例子:
    - `{"command":"execute_attack","args":{"encounter_id":"enc_preview_demo","actor_id":"pc_sabur","target_id":"enemy_raider_1","weapon_id":"dagger","attack_mode":"light_bonus"}}`
  - 投掷攻击例子:
    - `{"command":"execute_attack","args":{"encounter_id":"enc_preview_demo","actor_id":"pc_sabur","target_id":"enemy_raider_1","weapon_id":"dagger","attack_mode":"thrown"}}`
  - 借机攻击例子:
    - `{"command":"execute_attack","args":{"encounter_id":"enc_preview_demo","actor_id":"pc_sabur","target_id":"enemy_raider_1","weapon_id":"shortsword","allow_out_of_turn_actor":true,"consume_action":false,"consume_reaction":true}}`
  - 调用约束:
    - 普通攻击时,默认只能由当前行动者发起
    - 若返回 `invalid_attack`,这不是 transport error,而是规则非法,必须读取返回里的结构化结果并改口或改目标
    - 每次攻击结算后,后续判断一律基于返回的最新 `encounter_state`

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
