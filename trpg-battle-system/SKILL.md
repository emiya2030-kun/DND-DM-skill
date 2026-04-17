# Combat Runtime Skill

这个 skill 只负责战斗期运行协议.

核心原则:

1. 先读 `GetEncounterState`
2. 若战斗尚未开始,先 `initialize_encounter`,再 `RollInitiativeAndStartEncounter`
3. 每次 mutation 后都改用最新 `encounter_state`
4. 任何 `waiting_reaction` 都必须先处理
5. 回合结束固定走 `EndTurn -> AdvanceTurn -> StartTurn`

职业特性读取规则:

1. 主 `SKILL.md` 只定义通用战斗运行协议,不重复职业细节
2. 若当前行动者具有职业战斗特性,先按对应 playbook 理解自然语言,再决定是否补 `class_feature_options`
3. 职业 playbook 只负责“如何调用已有 tool”,不改写主协议
4. 当前已提供:
   - `docs/skill-playbooks/fighter.md`
   - `docs/skill-playbooks/monk.md`
   - `docs/skill-playbooks/rogue.md`
   - `docs/skill-playbooks/barbarian.md`

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

- `use_rage`
  - 用途: 野蛮人进入狂暴、仅延长狂暴、或进入狂暴时附带 `Instinctive Pounce`
  - 必填参数:
    - `encounter_id`
    - `entity_id`
  - 常用可选参数:
    - `extend_only`: 仅延长已激活狂暴时设为 `true`
    - `pounce_path`: 进入狂暴时附带的半速免费移动路径
  - 默认行为:
    - 消耗附赠动作
    - 正常进入狂暴时扣除一次 `Rage`
    - `extend_only=true` 时不扣次数,只刷新持续状态
    - 若传了 `pounce_path`,后端会把它当作 `Instinctive Pounce`
  - 调用约束:
    - 当前只允许在野蛮人自己的回合调用
    - 若角色穿重甲,后端会拒绝
    - 这不是自动攻击,调完后若还要攻击或移动,仍要继续走对应链路

- `execute_ability_check`
  - 用途: 当玩家或 NPC 的意图本质上是“做一次属性检定或技能检定”时使用
  - 必填参数:
    - `encounter_id`
    - `actor_id`
    - `check_type`: `ability` / `skill`
    - `check`
    - `dc`
  - 常用可选参数:
    - `vantage`: `normal` / `advantage` / `disadvantage`
    - `additional_bonus`
    - `reason`
  - 默认行为:
    - 后端自动掷 d20
    - 后端自动计算属性修正、技能修正、熟练与力竭惩罚
    - 后端自动比较 `final_total` 与 `dc`
    - 返回检定结果与最新 `encounter_state`
  - 调用约束:
    - 先由 LLM 自己把玩家自然语言理解成标准检定,再调用 tool
    - 必须显式传 `dc`
    - 不要自己掷 d20,不要自己算修正值,不要自己比较是否成功
    - 后续叙述一律基于返回里的 `success` / `failed` / `final_total`
    - 当前版不用于对抗检定、秘密检定、擒抱专用规则
  - 常见映射:
    - 偷偷绕过去 -> `{"command":"execute_ability_check","args":{"encounter_id":"enc_preview_demo","actor_id":"pc_sabur","check_type":"skill","check":"stealth","dc":15}}`
    - 看附近有没有埋伏 -> `{"command":"execute_ability_check","args":{"encounter_id":"enc_preview_demo","actor_id":"pc_sabur","check_type":"skill","check":"perception","dc":13}}`
    - 推门或搬石头 -> `{"command":"execute_ability_check","args":{"encounter_id":"enc_preview_demo","actor_id":"pc_sabur","check_type":"ability","check":"str","dc":12}}`

- `use_disengage`
  - 用途: 当前行动者执行 `Disengage` 动作
  - 必填参数:
    - `encounter_id`
    - `actor_id`
  - 默认行为:
    - 消耗该行动者本回合的 `action`
    - 给该行动者附加本回合持续的 `Disengage` 效果
    - 该效果生效期间,其移动不会触发借机攻击
    - 返回动作结果与最新 `encounter_state`
  - 调用约束:
    - 如果玩家先声明“我要撤离再移动”,先调这个 command,再开始移动
    - `Disengage` 只保护当前回合剩余时间内的移动,回合开始后会自动清除

- `use_dodge`
  - 用途: 当前行动者执行 `Dodge` 动作
  - 必填参数:
    - `encounter_id`
    - `actor_id`
  - 默认行为:
    - 消耗该行动者本回合的 `action`
    - 给该行动者附加持续到其下个回合开始前的 `Dodge` 效果
    - 该效果生效期间:
      - 其他生物对其进行的攻击检定通常具有劣势
      - 其敏捷豁免通常具有优势
    - 返回动作结果与最新 `encounter_state`
  - 调用约束:
    - 若使用者陷入 `incapacitated` 或速度降为 0,这些增益会失效
    - 若攻击者对其不可见,`Dodge` 不为该次攻击附加劣势
    - 后续攻击或豁免描述,必须基于返回后的最新 `encounter_state`

- `use_help_attack`
  - 用途: 当前行动者对 5 尺内敌人执行 `Help(attack)`
  - 必填参数:
    - `encounter_id`
    - `actor_id`
    - `target_id`
  - 默认行为:
    - 消耗该行动者本回合的 `action`
    - 给目标敌人附加短时 `Help(攻击)` 效果
    - 之后任意盟友对该目标的下一次攻击会自动获得优势并消耗该效果
    - 若到施助者下个回合开始前仍未用掉,效果自动失效
  - 调用约束:
    - 目标必须是敌人且在 5 尺内
    - 不要手动给后续攻击口头补优势,一律交给后端读取和消费

- `use_help_ability_check`
  - 用途: 当前行动者对盟友执行 `Help(ability)`
  - 必填参数:
    - `encounter_id`
    - `actor_id`
    - `ally_id`
    - `check_type`
    - `check_key`
  - 默认行为:
    - 消耗该行动者本回合的 `action`
    - 给受助盟友附加一次性的对应检定协助效果
    - 该盟友下一次匹配的检定会自动获得优势并消耗该效果
    - 若到施助者下个回合开始前仍未用掉,效果自动失效
  - 调用约束:
    - 先由 LLM 判断场景上是否真的帮得上忙,再调用
    - 当前版 `check_type` 主要按 `skill` / `tool` 使用
    - 后续检定不要手动补优势,一律交给后端读取和消费

- `use_grapple`
  - 用途: 当前行动者对 5 尺内敌人发起擒抱
  - 必填参数:
    - `encounter_id`
    - `actor_id`
    - `target_id`
  - 默认行为:
    - 消耗该行动者本回合的 `action`
    - 后端自动计算擒抱 DC
    - 目标自动在力量豁免和敏捷豁免中取更优者结算
    - 若失败,目标获得 `grappled:来源`,施术者获得 `active_grapple`
    - 返回动作结果与最新 `encounter_state`
  - 调用约束:
    - 目标必须是敌人且在 5 尺内
    - 当前版一个擒抱者同一时间只能维持一个主动擒抱目标
    - 后续若擒抱者正常移动,拖行会由普通移动链自动处理

- `escape_grapple`
  - 用途: 受擒目标用动作尝试挣脱
  - 必填参数:
    - `encounter_id`
    - `actor_id`
  - 默认行为:
    - 消耗该行动者本回合的 `action`
    - 后端自动找到擒抱来源
    - 后端自动在 `athletics` 与 `acrobatics` 中取更优者结算
    - 若成功,移除 `grappled:来源` 并清除对方的 `active_grapple`
    - 返回动作结果与最新 `encounter_state`
  - 调用约束:
    - 只有当前确实处于 `grappled:来源` 时才能调用

阅读顺序:

- `trpg-battle-system/combat-runtime/references/runtime-protocol.md`
- `trpg-battle-system/combat-runtime/references/tool-catalog.md`
- `trpg-battle-system/combat-runtime/references/monster-turn-flow.md`
- `trpg-battle-system/combat-runtime/references/companion-npc-turn-flow.md`
- `trpg-battle-system/combat-runtime/references/intent-examples.md`
- `trpg-battle-system/docs/skill-playbooks/fighter.md`（当当前行动者是战士或正在使用战士职业特性时）
- `trpg-battle-system/docs/skill-playbooks/monk.md`（当当前行动者是武僧或正在使用武僧职业特性时）
- `trpg-battle-system/docs/skill-playbooks/rogue.md`（当当前行动者是盗贼或正在使用盗贼职业特性时）
- `trpg-battle-system/docs/skill-playbooks/barbarian.md`（当当前行动者是野蛮人或正在使用野蛮人职业特性时）

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
