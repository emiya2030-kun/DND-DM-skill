# Sorcerer Core Design

日期：2026-04-18

## 目标

为 `Sorcerer / 术士` 增加第一批可稳定落地的核心职业特性，优先覆盖 1-7 级中对战斗与资源管理直接有影响、且不依赖超魔细节的部分。

本轮实现完成后，术士应当具备：

- 作为完整施法职业正常接入已准备法术与法术位体系
- 拥有独立的 `Sorcery Points / 术法点` 资源
- 可将法术位转为术法点
- 可将术法点转为 1-5 环法术位
- 可激活 `Innate Sorcery / 先天术法`
- 在 `先天术法` 激活期间，对术士法术获得 `DC +1` 与攻击检定优势
- 可使用 `Sorcerous Restoration / 术法复苏`
- 7 级后可通过 `Sorcery Incarnate / 术法化身` 花费 2 点术法点续开 `先天术法`

## 本轮范围

### 包含

- `Spellcasting / 施法`
- `Innate Sorcery / 先天术法`
- `Font of Magic / 魔力泉涌`
  - 法术位转术法点
  - 术法点造法术位
- `Sorcerous Restoration / 术法复苏`
- `Sorcery Incarnate / 术法化身`
  - 仅实现“可花 2 点术法点激活先天术法”

### 明确不包含

- `Metamagic / 超魔法`
- 任何超魔选项
- 7 级“每道法术最多应用两次超魔”规则
- 子职
- 19/20 级传奇恩惠与奥术化神

## 设计原则

- 复用现有职业资源框架，不为术士单独造第二套施法系统
- 玩家可见文本优先中文
- 新对外调用接口必须写入 LLM 文档
- 对战斗内即时能力使用显式服务入口
- 对被动增益采用运行态读取，不要求 LLM 额外传隐藏参数

## 施法接入

术士属于完整施法者，继续复用现有完整施法职业法术位进度与兼职施法者总环位表。

### 行为

- `class_features.sorcerer.level` 决定术士职业等级
- 术士准备法术数量按职业表
- 术士施法属性为 `Charisma / 魅力`
- 术士法器为 `Arcane Focus / 奥术法器`
- 戏法数与已准备法术数写入职业运行时辅助解析逻辑

### 非目标

- 本轮不处理“升级时替换法术/戏法”的 UI 或引导
- 只要求运行时能正确识别术士法术与资源

## 运行态

在实体运行态中新增术士节点：

```json
{
  "class_runtime": {
    "sorcerer": {
      "sorcery_points": {
        "current": 0,
        "max": 0
      },
      "innate_sorcery": {
        "uses_current": 0,
        "uses_max": 0,
        "active": false,
        "expires_at_turn": null
      },
      "sorcerous_restoration": {
        "used_since_long_rest": false
      },
      "created_spell_slots": {
        "1": 0,
        "2": 0,
        "3": 0,
        "4": 0,
        "5": 0
      }
    }
  }
}
```

### 字段说明

- `sorcery_points.current/max`
  - 当前术法点与上限
  - 上限等于术士等级
- `innate_sorcery.uses_current/max`
  - 先天术法剩余次数与上限
  - 1 级起固定为 2 次
- `innate_sorcery.active`
  - 当前是否激活
- `innate_sorcery.expires_at_turn`
  - 用于 1 分钟持续时间的统一回合结束清理
- `sorcerous_restoration.used_since_long_rest`
  - 标记本长休周期是否已使用过术法复苏
- `created_spell_slots`
  - 记录通过术法点临时创造的法术位，供长休时清空

## 能力设计

## 1. Innate Sorcery / 先天术法

### 服务入口

- `use_innate_sorcery(encounter_id, actor_id)`

### 规则

- 消耗一个附赠动作
- 若剩余使用次数大于 0，则扣除一次使用次数并激活 1 分钟
- 若剩余次数为 0，但术士等级至少 7 且术法点至少 2，则允许改为消耗 2 点术法点激活
- 若已在激活状态，则拒绝重复激活

### 激活效果

- 术士法术的法术豁免 DC +1
- 术士法术攻击检定具有优势

### 落地方式

- 在施法请求构建阶段判断施法来源是否为术士法术
- 若是术士法术且 `innate_sorcery.active = true`
  - 保存豁免 DC 计算时增加 1
  - 保存法术攻击检定时添加优势

### 持续时间

- 按现有回合效果系统记录 1 分钟
- 到期后自动将 `active` 置回 `false`

## 2. Font of Magic / 魔力泉涌

分为两个显式入口。

### A. 法术位转术法点

- `convert_spell_slot_to_sorcery_points(encounter_id, actor_id, slot_level)`

行为：

- 不消耗动作
- 校验术士等级至少 2
- 校验该环法术位尚有剩余
- 扣除一个指定环位
- 增加等同环位数值的术法点
- 不得超过术法点上限

若转化后会溢出：

- 默认拒绝，不做“超出上限只拿部分”的隐式处理

### B. 术法点造法术位

- `create_spell_slot_from_sorcery_points(encounter_id, actor_id, slot_level)`

行为：

- 消耗一个附赠动作
- 校验术士等级至少 2
- 仅允许创建 1-5 环
- 按规则表校验最小术士等级
- 扣除对应术法点
- 为指定环位增加一个可用法术位
- 同时在 `created_spell_slots[slot_level]` 计数 +1

### 创建规则表

- 1 环：2 点，2 级
- 2 环：3 点，3 级
- 3 环：5 点，5 级
- 4 环：6 点，7 级
- 5 环：7 点，9 级

## 3. Sorcerous Restoration / 术法复苏

### 服务入口

- `use_sorcerous_restoration(encounter_id, actor_id)`

### 规则

- 仅短休后可调用，或直接复用当前“短休结算时触发职业恢复”的服务入口
- 术士等级至少 5
- 若本长休周期已用过，则拒绝
- 恢复不大于术士等级一半（向下取整）的已消耗术法点
- 不能超过上限
- 使用后将 `used_since_long_rest = true`

### 建议实现

优先做成显式服务，和当前战士 `Second Wind / 回气`、魔契师 `Magical Cunning / 秘法回流` 一样可被 LLM 主动调用，不强行绑死在短休流程里。

如果后续短休系统成熟，再补自动化入口。

## 4. Sorcery Incarnate / 术法化身

本轮只实现其对 `先天术法` 的扩展部分。

### 行为

- 当术士等级至少 7 时：
  - `use_innate_sorcery` 在原始次数耗尽后，可允许消耗 2 点术法点激活

### 不实现部分

- 每法术两次超魔

## 资源初始化与重置

### 初始化

在职业运行态确保逻辑中加入术士：

- 术法点上限 = 术士等级
- 当前术法点若不存在，则初始化为上限
- `先天术法` 使用次数初始化为 2
- `术法复苏` 标记默认 `false`

### 长休

长休完成时：

- 术法点回满
- `先天术法` 使用次数回满
- `先天术法` 激活状态结束
- `used_since_long_rest = false`
- 清空 `created_spell_slots`
- 同步扣除对应由术法点造出的临时法术位

### 短休

- 不自动恢复术法点
- 仅当显式调用 `use_sorcerous_restoration` 时恢复

## 对现有系统的影响

## 施法请求

在法术请求构建与执行链路中补充：

- 判断法术是否以术士职业施放
- 若是，并且 `先天术法` 激活：
  - 法术攻击检定加优势
  - 法术豁免 DC +1

## 法术位存储

创造出来的法术位与普通法术位共用同一套可用法术位存储。

额外要求：

- 必须单独记录“创造出来的数量”
- 长休清空时，只清空这部分临时额度，不误伤正常法术位进度

## LLM 接口文档

本轮新增接口都必须写入 LLM 文档，至少包括：

- `use_innate_sorcery(encounter_id, actor_id)`
- `convert_spell_slot_to_sorcery_points(encounter_id, actor_id, slot_level)`
- `create_spell_slot_from_sorcery_points(encounter_id, actor_id, slot_level)`
- `use_sorcerous_restoration(encounter_id, actor_id)`

并补充说明：

- `actor_id` 始终传实体 ID
- 若 `先天术法` 已激活，后端会自动把术士法术的攻击检定改为优势，并自动为术士法术豁免 DC +1
- `术法化身` 生效后，`use_innate_sorcery` 会在次数耗尽时自动尝试改扣 2 点术法点

## 测试

至少补以下测试：

- 术士运行态初始化
- 先天术法成功激活
- 先天术法次数耗尽时报错
- 7 级术士可用 2 点术法点续开先天术法
- 激活时术士法术攻击检定具有优势
- 激活时术士法术豁免 DC +1
- 法术位转术法点成功
- 法术位转术法点溢出时报错
- 术法点造法术位成功
- 术法点不足时报错
- 术法点造高于允许环位时报错
- 术法复苏成功恢复
- 术法复苏在同一长休周期重复使用时报错
- 长休会清空通过术法点造出的临时法术位

## 风险与约束

- 当前没有完整长休系统时，长休清空临时法术位可能只能先挂在现有恢复入口上
- “术士法术”的识别必须基于施法职业上下文，而不是仅看法术列表归属；否则兼职角色会套错加成
- 如果现有法术位结构不支持区分临时造出的额度，则必须最小改造该结构

## 实施顺序

1. 补术士运行态初始化
2. 接入术士施法辅助元数据
3. 实现 `先天术法`
4. 实现术法点与两种转化
5. 实现 `术法复苏`
6. 接入长休清理逻辑
7. 补 LLM 文档与开发日志
8. 补测试并跑全量
