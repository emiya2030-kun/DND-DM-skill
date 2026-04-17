# Rogue Playbook

这个 playbook 只负责盗贼在战斗中的 tool 调用示例.

规则边界:

1. 先遵守主 `SKILL.md` 的通用协议
2. 这个文档只补充“盗贼自然语言如何转成 `class_feature_options`”
3. 若后端已自动处理的特性,不要重复声明

## 1. 稳定瞄准 + 攻击

适用条件:

- 本回合尚未移动
- 附赠动作未使用

玩家例子:

- “我稳住身形朝他射一箭。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_rogue",
    "target_id": "enemy_1",
    "weapon_id": "shortbow",
    "class_feature_options": {
      "steady_aim": true
    }
  }
}
```

后端效果:

- 消耗附赠动作
- 本回合速度归 0
- 这次攻击获得优势

## 2. 普通偷袭

玩家例子:

- “我用刺剑偷袭他。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_rogue",
    "target_id": "enemy_1",
    "weapon_id": "rapier",
    "class_feature_options": {
      "sneak_attack": true
    }
  }
}
```

说明:

- 只有在本次攻击满足偷袭条件时才应声明 `sneak_attack: true`
- 偷袭伤害骰由后端按盗贼等级自动推导
- 每回合一次
- 借机攻击也可以这样触发

## 3. 偷袭 + 诡诈打击 Trip

玩家例子:

- “我刺他腿,把他绊倒。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_rogue",
    "target_id": "enemy_1",
    "weapon_id": "rapier",
    "class_feature_options": {
      "sneak_attack": true,
      "cunning_strike": {
        "effects": ["trip"]
      }
    }
  }
}
```

后端效果:

- 自动从偷袭骰中扣除 `1d6`
- 目标进行敏捷豁免
- 失败则附加 `prone`

## 4. 11级盗贼双诡诈打击

玩家例子:

- “我绊倒他,然后立刻抽身后撤。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_rogue",
    "target_id": "enemy_1",
    "weapon_id": "rapier",
    "class_feature_options": {
      "sneak_attack": true,
      "cunning_strike": {
        "effects": ["trip", "withdraw"]
      }
    }
  }
}
```

说明:

- 只有 11 级及以上盗贼允许一次两个效果
- 11 级以下这样调用会被后端拒绝

## 5. Withdraw 的后续处理

`withdraw` 不会自动替角色移动.

若攻击命中且该效果成功进入结算结果,LLM 应继续调用移动工具完成“立即移动半速且不触发借机攻击”,而不是假设后端已经自动移动.

## 6. 直觉闪避

触发条件:

- 盗贼被一次攻击检定命中
- 反应未使用

运行方式:

1. 后端会自动打开反应窗口
2. 玩家确认后,按通用反应协议调用反应解析 tool
3. 后端会把这次攻击伤害减半

说明:

- 不改变是否命中
- 只改写伤害结果

## 7. 飘忽不定

18 级盗贼若未失能,以其为目标的攻击检定不能具有优势.

LLM 不需要额外声明任何参数.

只要正常发起攻击请求,后端会自动把针对该盗贼的优势压成普通掷骰.

## 8. 灵巧动作

盗贼可以把以下行为作为附赠动作使用:

- `Dash`
- `Disengage`
- `Hide`

说明:

- `GetEncounterState` 已会投影这些能力
- LLM 应根据玩家语义决定这是在消耗附赠动作,而不是普通动作
- 仍然使用现有移动 / 检定链路,不需要额外职业专用 tool

## 9. 高阶诡诈打击

当前后端已支持:

- `poison`
- `trip`
- `withdraw`
- `daze`
- `knock_out`
- `obscure`

说明:

- `poison` 需要角色具备制毒工具
- 5级起可用 `poison / trip / withdraw`
- 14级起可用 `daze / knock_out / obscure`
- 11级起一次命中可声明两个效果
