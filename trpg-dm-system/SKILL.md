# TRPG 跑团系统完整指南

> **适用对象**:任何D&D模组的DM
> **最后更新**:2026-04-06

# ⚠️ 输出格式规则(强制)

**战斗输出不要套代码块!** `standardized_output.py` 和 `combat_manager.py` 的输出包含 `**粗体**` 和 `> 引用` 等 markdown 语法,必须直接输出原始文本让其自然渲染,**绝不能**用 ``` 包裹.这是用户明确要求的.

**错误示范:**
```
**第1击 攻击骰1d20+4=16 ✅**
```

**正确示范:**
**第1击 攻击骰1d20+4=16 ✅**
(直接输出,不套代码块)


# ⚠️ 开始之前,必须确认下列表格的事情有没有做完!(强制)

| 检查项 | 有没有? |
|--------|---------|
| 是否安装了trpg-module-prep 备团skill | ❌/✅ |
| 是否是第一次跑团? 检查trpg-module-prep/dnd_campaigns/<module name>/session_notes/下是否为空 | ❌/✅ |


# 如果是第一次开团:请询问玩家创建你的角色

## 请先完成以下两件事

### 1. 创建你的PC档案

在trpg-module-prep\dnd_campaigns\shared\pcs文件夹下创建 `pc_你的角色名.md`,包含:

```markdown
# PC档案:[角色名]

## 基本信息
- 名字:
- 种族:
- 职业/子职:
- 等级:

## 战斗数据
- AC:
- HP:
- 速度:
- 熟练加值:

## 属性值
| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
|------|------|------|------|------|------|
| xx(+x) | xx(+x) | xx(+x) | xx(+x) | xx(+x) | xx(+x) |

## 熟练豁免
[列出你的熟练豁免属性]

## 技能
[列出你的熟练技能和加值]

## 动作
- 武器名:+x命中, 1dX+X 伤害类型

## 特性
[列出你的职业特性、种族特性]

## 装备
[列出你的装备和AC计算方式]

## 背景故事
[简要描述你的角色]
```

### 2. 设计一个同行NPC伙伴

在 `trpg-module-prep\dnd_campaigns\<module name>\module\companions` 文件夹下创建 `npc_名字.md`,包含:

```markdown
# NPC:[名字]

## 基本信息
- 种族/身份:
- 阵营:
- 性格关键词:

## 属性值(简表)
| 力量 | 敏捷 | 体质 | 智力 | 感知 | 魅力 |
|------|------|------|------|------|------|
| +x | +x | +x | +x | +x | +x |

## 背景
[TA是谁?为什么和你同行?]

## 战斗行为
[遇到战斗时TA怎么行动?]

## 目前举动
- [日期] 出发冒险
```

### NPC互动铁律

2. **NPC之间必须有互动对话**
   - 每次剧情推进至少包含1-2句NPC之间的对话
   - NPC会主动与其他NPC聊天、争论、开玩笑、表达情绪

3. **NPC有独立行动**
   - NPC会主动做决定、表达意见、推动剧情
   - 不是被动等待PC指令的花瓶

---

# 第二部分:如何进行剧情

## 2.1 开场前必读文件

**⚠️ 每次会话开始前,必须读取以下文件:(强制)**

1. `session_notes/session_progress.md` — 确认玩家当前在哪里
2. `state/world_state.md` — 世界已经发生了什么
3. `module/prep/chapter_0x_prep.md` — 复习当前章节备团资料
4. `module/prep/event_triggers.md` — 检查哪些图片待发送
5. `module/npcs/` 目录下所有NPC档案 — 确认NPC当前状态

## 2.2 剧情推进流程

```
1. 确认当前位置(读session_progress.md)
2. 描述环境(参考备团资料的场景描述)
3. 检查event_triggers.md → 匹配关键词 → 发送图片
4. 等待玩家行动
5. 解析行动结果
6. 更新状态(session_progress.md + NPC档案)
7. 检查是否触发预设遭遇
8. 如果触发:发地图 → 开始战斗/解谜/RP
9. 如果没触发:继续探索
```

## 2.3 对话技巧

- **NPC要有性格**_不是每个人都友善
- **NPC之间会互动**_至少1-2句对话/场景
- **允许玩家说服/恐吓**_骰社交检定
- **保持世界观语言**_禁止出现游戏术语
- **不要过度纵容玩家**_请以骰子的结果为基本的裁定方向

## 2.4 即兴发挥规则

**允许的即兴:**
- NPC的临场反应和对话
- 环境的细节描述
- 玩家行动的合理后果

**禁止的即兴:**
- 编造不在预设遭遇中的怪物
- 编造不存在的宝藏
- 跳过关键的检定环节
- 让NPC做出不符合性格的决定

## 2.5 会话记录

每次会话结束后更新:
- `session_progress.md` — 位置和状态
- 各NPC的 `目前举动` 部分
- 如果有战斗,记录战斗日志

---

# 第三部分:战斗系统

## ⛔ 战斗执行协议(每次战斗必须遵守)

### 第一步:读档
收到玩家行动后,**先执行以下查询,再做任何事**:
1. `read trpg-module-prep\dnd_campaigns\shared\pcs/<module>/<player>/` — 确认玩家属性、法术位、特性、装备


### 第二步:动作经济检查(每回合必须核对)
| 资源 | 每回合可用 | 常见消耗 |
|------|-----------|---------|
| **动作 (Action)** | 1个 | 攻击、施法、展开UBW、射杀百头、Caliburn圣光斩 |
| **附赠动作 (Bonus Action)** | 1个 | 投影武器、干将莫邪Nick攻击、战争魔法附赠攻击 |
| **反应 (Reaction)** | 1个/轮 | Rho Aias展开、护盾术、银光锐语 |
| **移动 (Movement)** | 30尺 | 步行移动 |

**硬性规则:**
- 展开UBW = 1个动作 → **该回合不能再用动作攻击**
- 投影武器 = 1个附赠动作 → 可与攻击同回合(如果还有动作)
- **组合限制示例:**
  - ✅ 第1回合:动作=UBW + 附赠动作=投影 + 反应=待命
  - ✅ 第2回合:动作=攻击 + 附赠动作=Nick/战争魔法 + 反应=Rho Aias
  - ❌ 第1回合:动作=UBW + 动作=九连攻击(超了!)

### 第三步:技能/武器效果确认
- **不要凭记忆执行,必须查文件**
`read trpg-module-prep\dnd_campaigns\shared\pcs/<module>/<player>/` — 确认玩家的能力 法术效果

### 第四步:掷骰与应用
1. 掷骰
2. 确认命中/未命中
3. 计算伤害
4. 用 combat_manager.py 更新状态
5. 渲染地图

### 第五步:RP描写
- 如果有rp文本 ->从本文件选取对应技能的描写
- 根据掷骰结果调整剧情(暴击要夸张,未命中要有合理解释)
- 描写敌人反应和环境互动

# 骰子展示格式

> 第一行:**骰子表达式+结果(加粗)**.第二行:> RP描写(引用块区分).

## 格式

命中:
**第N击 攻击骰1d20+[修正]=[结果]✅ → 伤害骰1d[N]+[修正]=[结果][类型] | [精通] ✅**
> [RP描写]

未命中:
**第N击 攻击骰1d20+[修正]=[结果]❌**
> [RP描写]

暴击:
**第N击 攻击骰1d20+[修正]=[结果]⚡ → 伤害骰1d[N]+1d[N]+[修正]=[结果][类型] | [精通] ✅**
> [RP描写]

优势骰:攻击骰1d20+[修正](优势)=[结果]

汇总:
**命中: X/N | 总伤害: NN**

## 案例

**第1矢 攻击骰1d20+7=16 ✅ → 伤害骰1d8+4=12 穿刺 | 缓速 ✅**
> 第一箭射出_黑色流星贯穿龙翼!箭矢深深嵌入翼骨,魔力沿箭杆扩散!

**第2矢 攻击骰1d20+7=8 ❌**
> 弓弦在指间滑了一下_箭矢偏离了轨迹!

**命中: 1/2 | 总伤害: 12**


---

## 使用规则
- 每次攻击/施法/技能至少选一段描写
- 根据情境混用长短版本,避免重复
- 结合战场地图变化和敌人状态变化
- 敌人要有**反应和情绪**(恐惧、愤怒、绝望随战况变化)
- 环境要**互动**(剑影刮过岩壁、火花四溅、地面震动)


## 3.1 战斗管理器

所有战斗状态通过 `combat_manager.py` 追踪.

### 核心命令

```bash
# 初始化战斗
python3 combat_manager.py init <战斗ID> [宽] [高]

# 添加单位(完整参数,通过Python调用)
python3 -c "
import combat_manager
cm = combat_manager.CombatManager('/tmp/battle.json')
cm.init_combat('战斗名', 12, 12)
cm.add_unit('名称', x, y, hp, max_hp, ac, '符号', is_player,
    dex_mod=3,
    equipment=[{'name':'皮甲','type':'armor','ac_base':11,'dex_cap':10}],
    save_proficiencies=['dex','con'],
    ability_mods={'str':0,'dex':3,'con':2,'int':1,'wis':0,'cha':0},
    damage_resistances=['cold'],
    size='large',
    movement_speed=30)
"

# 移动
python3 combat_manager.py move <名称> <x> <y>

# 造成伤害(自动应用抗性)
python3 combat_manager.py take_damage <名称> <伤害> <伤害类型>

# 治疗
python3 combat_manager.py heal <名称> <治疗量>

# 设置先攻
python3 combat_manager.py initiative <名称> <值>

# 下一回合
python3 combat_manager.py next_turn

# 渲染地图
python3 combat_manager.py render

# 查看状态
python3 combat_manager.py status
```

### 行动经济命令

```bash
# 使用主要动作
python3 combat_manager.py use_action <名称>

# 使用附赠动作
python3 combat_manager.py use_bonus_action <名称>

# 使用反应
python3 combat_manager.py use_reaction <名称>

# 使用移动
python3 combat_manager.py use_movement <名称> <格数>

# 查看行动经济状态
python3 combat_manager.py check_economy <名称>

# 重置行动经济
python3 combat_manager.py reset_economy [名称]
```

### 豁免检定命令

```bash
# 豁免检定
python3 combat_manager.py save <名称> <属性> <DC> [优势] [劣势]

# 死亡豁免
python3 combat_manager.py death_save <名称> [手动骰值]

# 查看死亡豁免状态
python3 combat_manager.py death_saves <名称>

# 设置临时HP
python3 combat_manager.py temp_hp <名称> <数量>
```

### 体型命令

```bash
# 设置体型
python3 combat_manager.py set_size <名称> <体型>
# 体型: tiny/small/medium/large/huge/gargantuan

# 查看占据格子
python3 combat_manager.py occupied <名称>
```

## 3.2 战斗执行协议(强制)

**每次战斗必须按以下5步执行:**

### 第一步:读档
收到玩家行动 → 必须立即读取 (强制):
- PC档案(确认技能/属性/装备)
- 战斗管理器状态(确认位置/HP/行动经济)
- NPC档案(确认NPC战斗行为)

### 第二步:动作经济检查
确认玩家的行动是否符合规则:
- **主要动作**:1个(攻击/施法/疾走/撤退/协助/躲藏/准备)
- **附赠动作**:1个(双武器/特定能力)
- **反应**:1个/轮(机会攻击/防护/法术反应)
- **移动**:不超过速度
- **免费物品交互**:1个

### 第三步:技能效果确认
查表确认法术/技能的D&D效果,不要凭记忆.

### 第四步:掷骰与应用
- 使用骰子模板格式显示结果
- 更新战斗管理器状态(HP/位置/条件)
- 应用抗性/免疫/易伤

### 第五步:RP描写
在引用块中描写战斗场面,包含:
- 电影化动作描述
- 敌人反应
- 环境互动
- 适当对白

## 3.3 骰子展示格式

**必须使用统一格式**,详见 `_shared/system/dice_template.md`.

## 3.4 装备AC计算

AC以 `combat_manager.py` 的equipment字段为准,档案中的AC仅供参考.

```
最终AC = 盔甲基础AC + DEX修正(受上限) + 盾牌(+2) + 风格(+1) + 其他
```

## 3.5 大型生物距离规则

距离计算改为**最近边缘距离**(非中心点):
- 中型(1×1) vs 大型(2×2):边缘到边缘
- 近战触及5尺 = 边缘距离≤7尺即可攻击

## 3.6 伤害抗性系统

```bash
# 自动应用免疫→抗性→易伤→临时HP
python3 combat_manager.py take_damage <名称> <伤害> <伤害类型>
```

处理顺序:
1. 免疫:伤害=0
2. 抗性:伤害÷2(向下取整)
3. 易伤:伤害×2
4. 临时HP:先吸收
5. 实际HP:剩余伤害

---

# 附录A:文件路径速查

```
trpg-module-prep/dnd_campaigns/<module name 根据模组分开管理>
├── module/  
│   ├── prep/
│   │   ├── chapter_01_prep.md    ← 之前章节
│   │   ├── chapter_02_prep.md    ← 目前的章节
│   │   └── event_triggers.md     ← 事件图片触发注册表
│   ├── maps/
│   │   └── *.jpg                 ← 地图
│   ├── monsters/
│   │   └── part1_monsters.md     ← 怪物数据(集中管理)
│   └── npcs/
│   │   └── npc_xxx.md            ← NPC档案(纯剧情,不含战斗数据)
│   └── companions/
│   │   └── xxx.md                ← 同伴NPC
└   └── <module name>.pdf         ← 模组设定集
│   
├── session_notes/
│   ├── session_progress.md       ← 当前位置
│   └── s01.md                    ← 会话记录
├── state/
│   ├── world_state.md            ← 世界发生了什么
│   ├── quest_state.md            ← 任务追踪
│   ├── npc_relationships.md      ← NPC关系
│   └── loot_registry.md          ← 战利品追踪
└── shared/
      └── pcs
           └──<player name>       ← 根据玩家名保存pc角色卡
                    ├── xxx.md    ← pc角色卡


```
trpg-dm-system
├── scripts/
│   ├── combat_manager.py         ← 战斗管理器核心(状态/伤害/AC/行动经济)
│   ├── battle_persistence.py     ← 持久化管理器(高层API,整合战斗+日志)
│   ├── standardized_output.py    ← 标准化输出(骰子/攻击格式化)
│   ├── event_logger.py           ← 事件日志(记录/回放/总结)
│   ├── battle_map.py             ← 独立地图渲染(轻量版)
│   └── combat_rules.md           ← 体型/距离规则文档
└── SKILL.md                      ← SKILL文件
```

---

## 3.1.5 持久化管理器 battle_persistence.py(推荐高层API)

**用途**: 整合 combat_manager + event_logger,一个对象搞定所有战斗操作

```python
from battle_persistence import BattlePersistenceManager

# 初始化
p = BattlePersistenceManager("战斗ID")          # 数据存 /tmp/trpg_battles/战斗ID/
p.init_battle(width=10, height=10)

# 添加单位(同 combat_manager)
p.combat.add_unit("凯兰", 3, 3, 24, 24, 19, "凯", True,
    dex_mod=1,
    equipment=[{"name":"链甲","type":"armor","ac_base":16,"dex_cap":0}],
    ability_mods={"str":2,"dex":1,"con":2,"int":1,"wis":0,"cha":-1})
p.combat.set_initiative("凯兰", 15)

# 记录事件
p.log_attack(round_num=1, turn="凯兰", actor="凯兰", target="幽魂",
             action="魔法飞弹", damage="10力场", damage_total=10,
             target_hp_before=67, target_hp_after=57)
p.log_move(1, "凯兰", "凯兰", (3,3), (4,4))
p.log_spell(1, "凯兰", "凯兰", "护盾术", spell_slot=1)
p.log_status_change(1, "凯兰", "获得专注状态")
p.log_use_item(1, "凯兰", "凯兰", "治疗药水")

# 回合快照 & 查询
p.save_round_snapshot(1)
p.get_round_summary(1)                          # 格式化回合摘要

# 战斗结束
p.finalize_battle(result="凯兰胜利",
    summary_text="凯兰在第3回合击杀幽魂",
    key_moments=["第1回合:幽魂生命吸取", "第3回合:凯兰致命一击"])
```

文件结构:
```
/tmp/trpg_battles/战斗ID/
├── current_state.json    ← 当前战斗状态
├── events.jsonl          ← 事件日志
├── battle_summary.json   ← 战斗总结
└── rounds/
    ├── round_1.json
    └── round_2.json
```

---

## 3.1.6 标准化输出 standardized_output.py

**用途**: 生成统一格式的攻击/伤害/RP输出(markdown直接渲染,不要套代码块!)

```python
from standardized_output import DiceRoller, AttackBuilder, BattleOutputFormatter

# DiceRoller 骰子投掷
r = DiceRoller.roll("1d20+5")         # → {"total": 14, "formatted": "1d20+5=9+5=14"}
r = DiceRoller.roll_with_crit("1d8+2", is_crit=True)  # 暴击翻倍

# AttackBuilder 攻击序列构建
builder = AttackBuilder(round_num=1)

builder.create_attack(1, "凯兰", "幽魂", target_ac=13, attack_modifier=4)
builder.add_damage("1d8+2", "挥砍")
builder.set_rp("日耀之剑划出金色弧光!")
builder.finish_attack()

builder.create_attack(2, "凯兰", "幽魂", target_ac=999)
builder.add_damage("1d4+1", "力场")
builder.add_damage("1d4+1", "力场")
builder.add_damage("1d4+1", "力场")
builder.set_rp("三支飞弹自动追踪!")
builder.finish_attack()

# 输出(直接发送,不要套代码块!)
print(builder.format_all())
```

BattleOutputFormatter 快捷格式:
```python
BattleOutputFormatter.format_hp_change("凯兰", 24, 2, 24)
BattleOutputFormatter.format_round_header(1)
BattleOutputFormatter.format_round_summary(2, 1, 12)
BattleOutputFormatter.format_movement("凯兰", (3,3), (5,5), 20)
```




