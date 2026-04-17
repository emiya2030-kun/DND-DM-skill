# Barbarian Playbook

这个 playbook 只负责野蛮人在战斗中的 tool 调用示例。

规则边界:

1. 先遵守主 `SKILL.md` 的通用协议
2. 这个文档只补充“野蛮人自然语言如何转成已有 tool / 参数”
3. 若后端已自动处理的特性,不要重复声明

## 1. 进入狂暴 Rage

适用条件:

- 当前是野蛮人自己的回合
- 附赠动作未使用
- 未穿重甲
- 还有 `rage.remaining`

玩家例子:

- “我进入狂暴。”
- “我怒吼着冲上去开狂暴。”

调用:

```json
{
  "command": "use_rage",
  "args": {
    "encounter_id": "enc_preview_demo",
    "entity_id": "pc_barbarian"
  }
}
```

后端效果:

- 消耗附赠动作
- 扣除一次 `Rage`
- 进入狂暴
- 若正在专注,会自动终止专注

说明:

- 这不是自动攻击
- 调完后若玩家还要攻击或移动,仍要继续调用对应 tool

## 2. 狂暴 + 莽驰 Instinctive Pounce

适用条件:

- 当前是野蛮人自己的回合
- 本次要进入狂暴
- 角色已有 `Instinctive Pounce / 莽驰`
- 玩家明确描述了“开狂暴时顺势扑进/冲进”

玩家例子:

- “我开狂暴,顺势往前扑过去。”

调用:

```json
{
  "command": "use_rage",
  "args": {
    "encounter_id": "enc_preview_demo",
    "entity_id": "pc_barbarian",
    "pounce_path": [[4, 2], [5, 2], [6, 2]]
  }
}
```

说明:

- `pounce_path` 只是进入狂暴附带的半速免费移动
- 这段移动不会自动替你接攻击
- 后续若还要攻击,仍要继续调用攻击链

## 3. 仅延长狂暴

适用条件:

- 当前是野蛮人自己的回合
- 狂暴已经激活
- 玩家明确表示“我用附赠动作维持/续上狂暴”

玩家例子:

- “我先维持狂暴。”

调用:

```json
{
  "command": "use_rage",
  "args": {
    "encounter_id": "enc_preview_demo",
    "entity_id": "pc_barbarian",
    "extend_only": true
  }
}
```

说明:

- 这会消耗附赠动作
- 不会再扣一次 `Rage` 使用次数
- 若本回合本来就打算攻击敌人,通常不需要这样做,因为攻击检定本身就能维持狂暴

## 4. 鲁莽攻击 Reckless Attack

适用条件:

- 本次是基于力量的攻击
- 当前是野蛮人自己的回合
- 玩家明确表示“不顾防御猛打 / 鲁莽进攻”

玩家例子:

- “我鲁莽攻击他。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_barbarian",
    "target_id": "enemy_1",
    "weapon_id": "greataxe",
    "class_feature_options": {
      "reckless_attack": true
    }
  }
}
```

后端效果:

- 这次基于力量的攻击获得优势
- 直到你的下个回合开始前,其他生物对你进行的攻击检定会获得相应的优势效果

说明:

- 每回合只能声明一次
- 若这击不是力量攻击,后端会拒绝
- LLM 不要手动给敌人“之后打你有优势”,后端会自动挂效果

## 5. 凶蛮打击 Brutal Strike

适用条件:

- 角色已有 `Brutal Strike / 凶蛮打击`
- 本次攻击是基于力量的攻击
- 本回合已经声明 `Reckless Attack`
- 玩家明确说想追加凶蛮打击效果

玩家例子:

- “我鲁莽一斧,把他狠狠干退。”
- “这一下改成断筋猛击。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_barbarian",
    "target_id": "enemy_1",
    "weapon_id": "greataxe",
    "class_feature_options": {
      "reckless_attack": true,
      "brutal_strike": {
        "effects": ["forceful_blow"]
      }
    }
  }
}
```

当前效果名:

- `forceful_blow`
- `hamstring_blow`
- 13级起额外开放:
  - `staggering_blow`
  - `sundering_blow`

说明:

- 9到16级一次只能传一个效果
- 17级起一次可以传两个不同效果
- 若本回合之前已经声明过 `Reckless Attack`,这次只传 `brutal_strike` 也可以
- `Brutal Strike` 会放弃这次攻击上的优势,这是后端自动处理的,LLM 不要自己改掷骰方式

## 6. Forceful Blow 的后续处理

`forceful_blow` 的推离是后端自动结算的。

若结果里出现:

```json
{
  "resolution": {
    "brutal_strike": {
      "forceful_blow": {
        "moved_feet": 15,
        "free_movement_after_forceful_blow": {
          "feet": 15,
          "ignore_opportunity_attacks": true
        }
      }
    }
  }
}
```

则说明:

- 目标已经被自动推走
- 野蛮人自己还可以立刻再移动半速
- 这段额外移动不会触发借机攻击

注意:

- 后端不会自动替野蛮人走完这段追击
- 若玩家要跟上去,LLM 仍需继续调用移动 tool

## 7. 自动效果

以下能力是自动生效,LLM 不需要主动传参数:

- `Rage Damage / 狂暴伤害`
- `Danger Sense / 危机感应`
- `Fast Movement / 快速移动`
- `Feral Instinct / 野性直觉`
- `Primal Knowledge / 原初学识`
- `Relentless Rage / 坚韧狂暴`
- `Persistent Rage / 持久狂暴`
- `Indomitable Might / 不屈勇武`
- `Unarmored Defense / 无甲防御`

其中补充说明:

- `Primal Knowledge` 只在属性检定链里由 LLM 显式声明“改用力量”时才会启用
- `Relentless Rage` 在掉到 0 HP 时由后端自动掷体质豁免
- `Persistent Rage` 的先攻恢复与回合末维持由后端自动处理
- 狂暴期间不能施法,施法请求会被后端直接拒绝
