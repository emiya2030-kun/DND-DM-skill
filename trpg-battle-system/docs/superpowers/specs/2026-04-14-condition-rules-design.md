# Condition 规则中心化设计

## 目标

把 DND 2024 战斗内常用 condition 收口到一个统一规则中心，让后端自动判断这些状态对攻击、豁免、移动、行动限制和专注的影响，而不是让 LLM 手工判断。

本次范围只覆盖战斗内闭环，不覆盖完整探索、社交或属性/技能检定系统。

---

## 当前问题

现在项目中虽然已经有 `conditions` 字段，也有 `UpdateConditions` 这个更新入口，但 condition 的真实规则效果仍然是零散的：

- 一部分攻击优劣势写在 `AttackRollRequest`
- 一部分状态只作为字符串存储，并不会自动影响其他系统
- `力竭` 尚未作为有等级状态建模
- `魅惑`、`恐慌`、`受擒` 这类依赖来源的状态还没有统一表示方式

这样继续扩，会导致：

1. 规则分散
2. 同一 condition 在不同入口里表现不一致
3. LLM 必须记很多规则细节
4. 后续接法术、怪物能力和更多状态时会越来越难维护

---

## 设计原则

1. condition 规则统一由后端判断
2. LLM 只需要读“目标当前有哪些状态”
3. `entity.conditions` 继续作为唯一 condition 存储入口
4. 不为 `力竭` 单独增加新字段
5. 所有 condition 解析、归一化和规则判断集中到 `combat/rules/conditions/`
6. 本次只接战斗内已有闭环入口，不扩到未成型系统

---

## 覆盖范围

本次覆盖以下 condition：

- `blinded`
- `charmed`
- `deafened`
- `exhaustion`
- `frightened`
- `grappled`
- `incapacitated`
- `invisible`
- `paralyzed`
- `petrified`
- `poisoned`
- `prone`
- `restrained`
- `stunned`
- `unconscious`

本次只接入这些战斗入口：

- `UpdateConditions`
- `AttackRollRequest`
- 豁免链相关入口
- `MoveEncounterEntity`
- 与专注 / 受伤 / 死亡直接相关的共享结算

---

## Condition 存储格式

所有 condition 继续存储在 `EncounterEntity.conditions` 中，元素仍然是字符串。

### 普通状态

```python
["blinded", "restrained", "poisoned"]
```

### 带来源状态

用 `condition_name:source_entity_id` 表示。

例如：

```python
["charmed:ent_enemy_succubus_001"]
["frightened:ent_enemy_dragon_001"]
["grappled:ent_enemy_ogre_001"]
```

### `力竭`

用 `exhaustion:<level>` 表示，`level` 为 1 到 6。

例如：

```python
["exhaustion:2"]
```

### 不叠加规则

除 `力竭` 外，其他 condition 不与自己叠加。

具体规则：

- `blinded` 不重复插入
- `restrained` 不重复插入
- `charmed:ent_a` 与 `charmed:ent_a` 不重复
- `charmed:ent_a` 与 `charmed:ent_b` 允许同时存在
- `frightened` 与 `grappled` 同理
- `exhaustion` 在任意时刻只能存在一条，等级靠字符串值表达

---

## 规则中心模块

新增一个 condition 规则专题模块，放在：

- `tools/services/combat/rules/conditions/`

建议分成几类职责：

### 1. 解析与标准化

负责把原始字符串解析成统一结构。

例如：

```python
{
  "raw": "frightened:ent_enemy_dragon_001",
  "name": "frightened",
  "source_entity_id": "ent_enemy_dragon_001",
  "level": None,
}
```

以及：

```python
{
  "raw": "exhaustion:2",
  "name": "exhaustion",
  "source_entity_id": None,
  "level": 2,
}
```

### 2. Condition 索引与查询

负责回答：

- 是否具有某 condition
- 是否具有某来源的 condition
- 当前 `exhaustion` 等级是多少
- 哪些状态会阻止攻击
- 哪些状态会让速度归零
- 哪些状态会导致特定豁免自动失败

### 3. 规则判断辅助

提供统一函数给攻击、豁免、移动等入口复用。

例如：

- 计算 condition 带来的攻击优劣势来源
- 计算 condition 带来的豁免自动失败或劣势
- 计算 condition 带来的移动限制
- 计算 `exhaustion` 的 D20 检定减值和速度减值

---

## UpdateConditions 设计

`UpdateConditions` 继续作为唯一写入口，但需要升级。

### 支持的写法

#### 普通状态

```python
condition="blinded"
operation="apply"
```

或：

```python
condition="restrained"
operation="remove"
```

#### 带来源状态

```python
condition="charmed:ent_enemy_succubus_001"
operation="apply"
```

```python
condition="frightened:ent_enemy_dragon_001"
operation="remove"
```

#### `力竭`

支持三类行为：

1. `apply` + `condition="exhaustion"`
   - 等价于等级 +1
2. `remove` + `condition="exhaustion"`
   - 等价于等级 -1，降到 0 时移除
3. `apply` + `condition="exhaustion:3"`
   - 直接设定为指定等级

### `力竭` 的特殊规则

- 等级合法范围为 1 到 6
- 若升级到 6，目标立即死亡
- 立即死亡通过既有共享 HP 更新路径落地，而不是单独起一套死亡系统

### 返回结果

保留原有结果，并继续返回：

- `condition`
- `operation`
- `changed`
- `conditions_after`

如果由于 `exhaustion:6` 导致死亡，应在返回中包含这一结算结果，便于上层读取。

---

## 战斗入口接入方案

## 1. 攻击请求 `AttackRollRequest`

需要通过规则中心统一处理：

- 是否不能攻击
- 是否对攻击检定有优势 / 劣势
- 目标是否让攻击者获得优势 / 劣势
- 近战命中后是否自动重击
- `exhaustion` 的 D20 检定减值

### 影响攻击的 condition

#### 攻击者不能攻击

以下 condition 会阻止攻击：

- `incapacitated`
- `paralyzed`
- `petrified`
- `stunned`
- `unconscious`

#### 攻击者攻击检定劣势

- `blinded`
- `poisoned`
- `prone`
- `restrained`
- `frightened`
  - 仅当恐惧源在视线范围内时生效
- `grappled`
  - 攻击目标不是擒抱者时生效

#### 攻击者攻击检定优势

- `invisible`
  - 如果目标可以看见攻击者，则不生效

#### 作为目标时影响来袭攻击

- `blinded`
  - 对其攻击有优势
- `invisible`
  - 来袭攻击有劣势；若攻击者能看见它则不生效
- `paralyzed`
  - 来袭攻击有优势
- `petrified`
  - 来袭攻击有优势
- `prone`
  - 5 尺内来袭攻击有优势，5 尺外来袭攻击有劣势
- `restrained`
  - 来袭攻击有优势
- `stunned`
  - 来袭攻击有优势
- `unconscious`
  - 来袭攻击有优势

#### 自动重击

以下 condition 在攻击者位于目标 5 尺内且命中时，使该次命中变成重击：

- `paralyzed`
- `unconscious`

### 本次不做的视觉例外

`invisible` 的完整规则依赖“谁能看见谁”的感知系统。当前项目尚无完整感知模型。

因此本次采用兼容策略：

- 默认按“看不见隐形者”处理
- 暂不实现“某生物可以看见隐形者”的例外开关

---

## 2. 豁免链

需要统一处理：

- 自动失败力量豁免
- 自动失败敏捷豁免
- 敏捷豁免劣势
- `exhaustion` 的 D20 检定减值

### 自动失败力量 / 敏捷豁免

以下 condition 会使目标自动失败力量豁免和敏捷豁免：

- `paralyzed`
- `petrified`
- `stunned`
- `unconscious`

### 敏捷豁免劣势

- `restrained`

### 本次不做

不扩到依赖视觉 / 听觉的属性检定，不扩到完整能力检定系统。

---

## 3. 移动 `MoveEncounterEntity`

需要统一处理：

- 速度归零
- 速度不可被增加
- 不可自愿靠近恐惧源
- 倒地时只能匍匐或起立
- `exhaustion` 速度减值

### 速度归零

以下 condition 会让速度变为 0，且无法被增加：

- `grappled`
- `paralyzed`
- `petrified`
- `restrained`
- `unconscious`

### `震慑`

`stunned` 本身文本没有直接写“速度变为 0”，但由于其带来 `incapacitated` 且战斗内无法有效行动，本次移动入口应视为不能进行自愿移动。

### 恐慌

- 不能自愿向靠近恐惧源的方向移动
- 需要比较当前位置与目标位置到恐惧源中心点的距离
- 只要一步移动使自己更接近任一可见恐惧源，就应拒绝该路径

### 倒地

- 倒地时只能匍匐移动，或先消耗一半速度起立
- 若速度为 0，则不能起立
- 本次最小实现中，`MoveEncounterEntity` 需要识别倒地状态并限制普通移动

### `exhaustion`

- 当前速度减少 `level * 5` 尺
- 这会影响本回合可用移动力上限

---

## 4. 行动限制

以下 condition 会带来“无法动作 / 附赠动作 / 反应”的战斗内限制：

- `incapacitated`
- `paralyzed`
- `petrified`
- `stunned`
- `unconscious`

本次先接到已存在的攻击和移动入口真正会用到的地方。

不在本次中额外扩完整动作系统。

---

## 5. 专注与附带规则

### `incapacitated`

- 会打断专注
- 该规则也应适用于：
  - `paralyzed`
  - `petrified`
  - `stunned`
  - `unconscious`
  - 因为这些状态包含或等效带来 `incapacitated`

### `petrified`

- 对所有伤害具有抗性
- 免疫 `poisoned`

本次影响：

- `UpdateHp` 在处理伤害时应识别石化的全伤害抗性
- `UpdateConditions` 在试图施加 `poisoned` 给石化目标时，应拒绝或标记未变更

### `unconscious`

- 隐含倒地
- 但当 `unconscious` 结束时，`prone` 不自动结束

本次最小处理：

- 规则判断中把 `unconscious` 视作同时满足“目标倒地”
- 不在状态列表里自动插入额外一条 `prone`
- 以后若要完整处理“结束昏迷后仍保持倒地”，再扩显式派生状态写回

---

## `魅惑`、`耳聋` 的边界

### `魅惑`

本次只实现战斗内可直接落地的部分：

- 不能攻击魅惑源
- 不能把魅惑源作为伤害性能力或魔法效应对象

不实现社交检定优势。

### `耳聋`

当前战斗闭环中没有完整“依赖听觉”的可判定入口。

因此本次只完成：

- condition 存储
- 可被读取
- 为后续属性/技能检定系统预留规则定义

但不强行接入现有攻击 / 移动 / 豁免流程。

---

## `目盲` 与依赖视觉的检定

当前也不扩完整“依赖视觉的属性检定自动失败”。

本次只接：

- 攻击劣势
- 被攻击时对方优势

---

## `中毒`

本次只接：

- 攻击检定劣势

不扩完整属性检定系统。

---

## `力竭`

### 存储

只保留一条：

- `exhaustion:1`
- `exhaustion:2`
- ...
- `exhaustion:6`

### 规则

#### D20 检定减值

当进行一次 D20 检定时，减去 `等级 * 2`。

本次接入：

- 攻击检定
- 豁免检定

#### 速度减值

速度减少 `等级 * 5` 尺。

本次接入：

- 移动系统

#### 死亡

达到 6 级立即死亡。

---

## 对 LLM 的暴露方式

LLM 不需要读取 condition 效果解释。

LLM 只需要从 `encounter_state` 或其他结果中看到：

- 实体有哪些 condition

例如：

- `blinded`
- `restrained`
- `charmed:ent_enemy_succubus_001`
- `exhaustion:2`

后端负责把这些 condition 自动转化为实际战斗影响。

如果以后需要更友好的展示，可以在视图层再把这些 condition 渲染为中文，但不改变底层规则来源。

---

## 文件边界建议

建议新增或修改这些文件：

### 新增

- `tools/services/combat/rules/conditions/__init__.py`
- `tools/services/combat/rules/conditions/condition_parser.py`
- `tools/services/combat/rules/conditions/condition_rules.py`
- `tools/services/combat/rules/conditions/condition_runtime.py`
- `test/test_condition_rules.py`
- `test/test_update_conditions.py`

### 修改

- `tools/services/combat/shared/update_conditions.py`
- `tools/services/combat/attack/attack_roll_request.py`
- `tools/services/combat/save_spell/resolve_saving_throw.py`
- `tools/services/encounter/move_encounter_entity.py`
- `tools/services/encounter/movement_rules.py`
- `tools/services/combat/shared/update_hp.py`
- `tools/services/encounter/get_encounter_state.py`

---

## 非目标

本次明确不做：

- 社交检定规则
- 完整属性检定 / 技能检定系统
- 感知系统 / 能否看见隐形者
- 掉落武器与装备系统
- condition 持续时间
- condition 来源持续跟踪的完整对象模型
- 回合结束自动解除
- 所有法术 / 特性对 condition 的完整生成逻辑

---

## 成功标准

完成后应满足：

1. `conditions` 仍然是唯一 condition 存储入口
2. `UpdateConditions` 能正确处理普通状态、来源状态与 `力竭`
3. 攻击请求会自动读取并应用 condition 影响
4. 豁免链会自动读取并应用 condition 影响
5. 移动会自动读取并应用 condition 影响
6. 石化会自动表现出全伤害抗性和中毒免疫
7. `力竭` 会自动影响攻击、豁免和移动，并在 6 级致死
8. LLM 不需要手工解释或计算这些规则
