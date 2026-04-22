# Monk Playbook

这个 playbook 只负责武僧在战斗中的 tool 调用示例。

规则边界:

1. 先遵守主 `SKILL.md` 的通用协议
2. 这个文档只补充“武僧自然语言如何转成已有 tool 参数”
3. 若后端已自动处理的特性,不要重复声明

## 1. 武艺 Martial Arts 附赠徒手打击

适用条件:

- 当前是武僧自己的回合
- 附赠动作未使用
- 未着装护甲且未持用盾牌
- 当前徒手或只持用武僧武器
- 玩家明确是在攻击动作后追加一次徒手打击

玩家例子:

- “我打完以后再补一拳。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_monk",
    "target_id": "enemy_1",
    "weapon_id": "unarmed_strike",
    "attack_mode": "martial_arts_bonus"
  }
}
```

后端效果:

- 把这次攻击当作武艺附赠徒手打击
- 消耗附赠动作
- 自动按武僧武艺规则使用武艺骰 / 敏捷修正

## 2. 疾风连击 Flurry of Blows

适用条件:

- 当前是武僧自己的回合
- 附赠动作未使用
- 还有 `focus_points.remaining`
- 未着装护甲且未持用盾牌
- 当前徒手或只持用武僧武器

玩家例子:

- “我用疾风连击追打他。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_monk",
    "target_id": "enemy_1",
    "weapon_id": "unarmed_strike",
    "attack_mode": "flurry_of_blows"
  }
}
```

后端效果:

- 消耗附赠动作
- 消耗 1 点功力
- 这次攻击按武僧徒手打击结算

说明:

- 当前链路里,`flurry_of_blows` 不是“一键把所有连击都自动打完”
- 它只是把这一击声明为 `Flurry of Blows` 攻击
- 若玩家描述为连续多拳,LLM 仍要基于最新状态继续决定是否还能合法追加后续攻击
- 若武僧穿甲、持盾或当前持有非武僧武器,则不要声明 `martial_arts_bonus` / `flurry_of_blows`

## 3. 震慑拳 Stunning Strike

适用条件:

- 本次攻击命中后玩家想接震慑拳
- 还有 `focus_points.remaining`
- 本回合尚未到 `stunning_strike.max_per_turn`

玩家例子:

- “命中的话我接震慑拳。”

调用:

```json
{
  "command": "execute_attack",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_monk",
    "target_id": "enemy_1",
    "weapon_id": "quarterstaff",
    "class_feature_options": {
      "stunning_strike": {
        "enabled": true
      }
    }
  }
}
```

后端效果:

- 命中后自动扣 1 点功力
- 目标自动进行体质豁免
- 失败则附加 `stunned`
- 成功则后端写入“下一次对该目标攻击具有优势”的临时标记

说明:

- 不要自己掷目标豁免
- 不要自己手动写 `stunned`
- 若没有命中,这次震慑拳不会生效

## 4. 拨挡攻击 / 拨挡能量 Deflect Attacks / Deflect Energy

触发条件:

- 你被一次攻击检定命中
- 该次伤害类型符合当前武僧等级允许的拨挡范围

运行方式:

1. 后端会自动打开反应窗口
2. 玩家确认后,按通用反应协议调用反应解析 tool
3. 宿主攻击恢复结算时,后端会自动先应用减伤
4. 若减到 0,并且玩家选择转定向,后端会继续处理转定向伤害

说明:

- LLM 不要自己先扣伤害再“补回去”
- 这是改写宿主攻击结算的反应
- 若有可转定向目标,也应按反应窗口返回的信息继续处理

## 5. 反射闪避 Evasion

说明:

- 这是自动效果
- 当武僧受到“敏捷豁免成功半伤、失败全伤”的效果时:
  - 成功改为免伤
  - 失败改为半伤
- 失能状态下不会生效

LLM 不需要额外声明参数。

## 6. 无甲防御 Unarmored Defense

说明:

- 这是自动效果
- 当武僧未穿甲且未持盾时,AC 会自动按武僧无甲防御计算
- 前端和 `GetEncounterState` 只需要读取结果,不要手算

## 7. 无甲移动 Unarmored Movement

说明:

- 这是自动效果
- 在满足无甲条件时,回合开始后端会自动把武僧的有效速度提高
- LLM 只读取 `GetEncounterState` 里的当前速度,不要自己额外再加
- 若武僧穿甲或持盾,则不要再把无甲移动当成生效中

## 8. 暂不写进调用示例的能力

当前 `GetEncounterState` 可能会投影:

- `patient_defense`
- `step_of_the_wind`

但这份 playbook 暂时不把它们写成明确调用示例,因为当前重点是只记录已稳定接线、调用路径明确的部分。

## 9. 坚强防御 Patient Defense

玩家例子:

- “我拉开架势防守。”
- “我花 1 点功力进入防御姿态。”

调用:

```json
{
  "command": "use_patient_defense",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_monk",
    "spend_focus": true
  }
}
```

说明:

- `spend_focus: false` 时，只给 `Disengage`
- `spend_focus: true` 时，同时给 `Disengage + Dodge`

## 10. 疾步如风 Step of the Wind

玩家例子:

- “我疾步冲过去。”
- “我花 1 点功力踏风而行。”

调用:

```json
{
  "command": "use_step_of_the_wind",
  "args": {
    "encounter_id": "enc_preview_demo",
    "actor_id": "pc_monk",
    "spend_focus": true
  }
}
```

说明:

- `spend_focus: false` 时，获得一次 `Dash`
- `spend_focus: true` 时，同时获得 `Dash + Disengage`，并让本回合跳跃距离翻倍
