# Fighter Playbook

这个 playbook 只负责战士在战斗中的 tool 调用示例。

规则边界:

1. 先遵守主 `SKILL.md` 的通用协议
2. 这个文档只补充“战士自然语言如何转成 tool 调用”
3. 若后端已自动处理的特性,不要重复声明

## 1. 回气 Second Wind

适用条件:

- 当前就是战士自己的回合
- 附赠动作未使用
- 还有 `second_wind.remaining_uses`

玩家例子:

- “我先回口气。”

调用:

```json
{
  "command": "use_second_wind",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_fighter"
  }
}
```

后端效果:

- 消耗一次附赠动作
- 自动恢复生命值
- 自动扣除一次 `Second Wind` 次数

## 2. 战术转进 Tactical Shift

说明:

- `Tactical Shift` 不单独调用
- 它跟在 `use_second_wind` 后端结果里一起返回

若 `use_second_wind` 返回:

```json
{
  "class_feature_result": {
    "free_movement_after_second_wind": {
      "feet": 15,
      "ignore_opportunity_attacks": true
    }
  }
}
```

则 LLM 应继续调用移动链,把这段移动当作:

- 免费移动
- 不触发借机攻击

不要假设 `use_second_wind` 已经自动把角色移动了。

## 3. 动作如潮 Action Surge

适用条件:

- 当前就是战士自己的回合
- 还有 `action_surge.remaining_uses`
- 本回合尚未使用过 `Action Surge`

玩家例子:

- “我动作如潮,再打一轮。”

调用:

```json
{
  "command": "use_action_surge",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_fighter"
  }
}
```

后端效果:

- 为本回合增加一次额外的非魔法动作额度
- 扣除一次 `Action Surge` 使用次数

说明:

- 这不是自动攻击
- 调完后仍要继续正常调用攻击 / 移动 / 其他非魔法动作 tool
- 这次额外动作不能用于施放法术

## 4. 额外攻击 Extra Attack

说明:

- `Extra Attack` 不需要单独 tool
- 只要角色正在执行 `Attack action`,攻击链会自动允许连续攻击次数
- 多职业来源不叠加,只取更高档位

玩家例子:

- “我砍他两次。”

调用方式:

1. 先正常调第一次 `execute_attack`
2. 若返回结果表明这次 `Attack action` 还有剩余攻击次数,继续调下一次 `execute_attack`
3. 直到本次 `Attack action` 的攻击次数用完,或玩家改做别的合法动作

不要自己手算战士能打几次,以返回的最新状态为准。

## 5. 战术主宰 Tactical Master

适用条件:

- 当前攻击本来就能使用该武器的精通词条
- 战士具备 `Tactical Master`
- 玩家明确想把本次精通改成 `push / sap / slow` 之一

玩家例子:

- “我这一下不用原本精通,改成推离。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_fighter",
    "target_id": "enemy_1",
    "weapon_id": "longsword",
    "mastery_override": "push"
  }
}
```

说明:

- 当前只允许改成 `push / sap / slow`
- 不要传别的精通名
- 若玩家没有明确改写意图,就不要手动传 `mastery_override`

## 6. 究明攻击 Studied Attacks

说明:

- 这是自动效果
- 若战士攻击某目标失手,后端会对该目标写入下一次攻击优势标记
- 下次再攻击同一目标时,攻击请求会自动吃到这个优势并在结算后消费

LLM 不需要额外声明参数。

## 7. 不屈 Indomitable

触发条件:

- 战士豁免失败
- 还有 `indomitable.remaining_uses`

运行方式:

1. 后端会自动打开反应窗口
2. 玩家确认后,按通用反应协议调用反应解析 tool
3. 后端会自动重掷该次豁免,并额外加上战士等级

说明:

- 这不是普通 `reaction` 消耗
- 也不是主动在自己回合空放
- 只会在失败豁免时出现

## 8. 战术思维 Tactical Mind

适用条件:

- 战士一次属性检定失败
- 还有 `second_wind.remaining_uses`

调用:

```json
{
  "command": "execute_ability_check",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_fighter",
    "check_type": "ability",
    "check": "str",
    "dc": 15,
    "class_feature_options": {
      "tactical_mind": true
    }
  }
}
```

说明:

- 后端会在失败后自动补掷 `1d10`
- 若补后仍失败，则不会消耗 `Second Wind`

## 9. 战斗风格 Fighting Style

当前已接入:

- `Defense`
- `Archery`
- `Dueling`

说明:

- 这些是被动效果
- LLM 不需要主动声明参数
- 只要角色 runtime 中存在对应 `fighting_style.style_id`，后端会自动结算
