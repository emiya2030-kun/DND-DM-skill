# 标准化输出系统

## 概述

标准化输出系统生成符合TRPG DM系统规范的战斗输出格式。

## 文件说明

| 文件 | 功能 |
|------|------|
| `standardized_output.py` | 标准化格式生成 |
| `event_logger.py` | 事件日志记录 |
| `battle_persistence.py` | 持久化管理 |

---

## 快速开始

```python
import sys
sys.path.insert(0, '/path/to/scripts')

from standardized_output import BattleOutputFormatter, DiceRoller, AttackBuilder

# ========== 方式1: 直接格式化 ==========
formatter = BattleOutputFormatter()

# 攻击输出
output = formatter.format_attack(
    round_num=1,
    attack_num=1,
    attacker="凯兰",
    target="骷髅1",
    attack_roll="1d20+5=13",
    hit=True,
    damage_str="1d8+2=10挥砍 + 1d8=7雷鸣",
    is_crit=False
)
# 输出: **第1.1击 凯兰→骷髅1: 攻击骰1d20+5=13 ✅ → 伤害骰1d8+2=10挥砍 + 1d8=7雷鸣**

# 状态变化输出
status = formatter.format_status_change(
    name="骷髅1",
    hp_before=13,
    hp_after=0,
    max_hp=13
)
# 输出: **骷髅1: HP 13→0/13 💀**

# ========== 方式2: 骰子投掷器 ==========
roller = DiceRoller()

# 投攻击骰
attack = roller.roll_attack("1d20+5")
print(attack["formatted"])  # 1d20+5=13
print(attack["is_natural_20"])  # False

# 投伤害骰（暴击时骰子翻倍）
damage = roller.roll_damage("1d8+2", is_crit=False)
print(damage["formatted"])  # 1d8+2=10

# ========== 方式3: 攻击构建器（链式调用）==========
result = (AttackBuilder(round_num=1, attack_num=1)
    .set_attacker("凯兰")
    .set_target("骷髅1")
    .roll_attack("1d20", modifier=5)  # 自动投骰
    .add_damage("1d8", "挥砍", modifier=2)  # 自动投骰
    .add_damage("1d8", "雷鸣")  # 轰雷剑
    .add_damage("1d4", "光耀", notes="对不死额外")  # 日耀之剑
    .build())

print(result)
# **第1.1击 凯兰→骷髅1: 攻击骰1d20+5=13 ✅ → 伤害骰1d8+2=10挥砍 + 1d8=7雷鸣 + 1d4=2光耀 | 对不死额外**

# 获取总伤害
total = result.get_damage_total()  # 19
```

---

## API 参考

### BattleOutputFormatter

#### format_attack()
```python
formatter.format_attack(
    round_num: int,        # 回合数
    attack_num: int,       # 攻击序号
    attacker: str,         # 攻击者
    target: str,           # 目标
    attack_roll: str,      # 攻击骰结果 "1d20+5=13"
    hit: bool,             # 是否命中
    damage_str: str,       # 伤害字符串
    is_crit: bool = False  # 是否暴击
) -> str
```

**输出格式：**
```
**第R.A击 攻击者→目标: 攻击骰X=Y ✅ → 伤害骰...**
```

**命中符号：**
- `✅` = 命中
- `❌` = 未命中  
- `⚡✅` = 暴击命中

#### format_status_change()
```python
formatter.format_status_change(
    name: str,                    # 单位名称
    hp_before: int = None,        # 变化前HP
    hp_after: int = None,         # 变化后HP
    max_hp: int = None,           # 最大HP
    status_added: list = None,    # 新增状态
    status_removed: list = None   # 移除状态
) -> str
```

**输出格式：**
```
**名称: HP X→Y/Z 💀/⚠️, +状态A, -状态B**
```

**特殊符号：**
- `💀` = HP归零（死亡）
- `⚠️` = HP低于25%（重伤）

#### format_movement()
```python
formatter.format_movement(
    name: str,              # 单位名称
    from_pos: (int, int),   # 起始坐标
    to_pos: (int, int),     # 目标坐标
    distance: int = None    # 距离（尺）
) -> str
```

**输出格式：**
```
**名称 移动: (x1,y1)→(x2,y2) [距离尺]**
```

#### format_spell_cast()
```python
formatter.format_spell_cast(
    caster: str,            # 施法者
    spell_name: str,        # 法术名称
    target: str = None,     # 目标
    spell_slot: int = None, # 法术位环数
    effect: str = None      # 效果描述
) -> str
```

**输出格式：**
```
**施法者 施法: 法术名 → 目标 | 消耗X环法术位**
> 效果描述
```

---

### DiceRoller

#### roll()
```python
roller.roll("2d6+3")  # 通用骰子投掷
# 返回: {"dice": "2d6+3", "rolls": [4, 5], "modifier": 3, "total": 12, "formatted": "2d6+3=4+5+3=12"}
```

#### roll_attack()
```python
roller.roll_attack("1d20+5")
# 返回: {..., "is_natural_20": False, "is_natural_1": False}
```

#### roll_damage()
```python
roller.roll_damage("1d8+2", is_crit=True)
# 暴击时骰子翻倍: 实际投 2d8+2
```

---

### AttackBuilder（链式调用）

```python
(AttackBuilder(round_num=1, attack_num=1)
    .set_attacker("凯兰")           # 设置攻击者
    .set_target("骷髅1")            # 设置目标
    .roll_attack("1d20", modifier=5)  # 投攻击骰
    .add_damage("1d8", "挥砍", modifier=2)  # 添加伤害（自动投骰）
    .add_damage("1d8", "雷鸣")      # 添加伤害
    .add_damage_direct("1d4", 2, "光耀")  # 直接添加伤害（不投骰）
    .build())                       # 生成输出字符串
```

---

## 与 BattlePersistenceManager 集成

```python
from battle_persistence import BattlePersistenceManager
from standardized_output import BattleOutputFormatter, DiceRoller

# 初始化
persistence = BattlePersistenceManager("battle_001")
formatter = BattleOutputFormatter()
roller = DiceRoller()

# 战斗流程
def execute_attack(persistence, formatter, round_num, turn, attacker, target):
    # 1. 投攻击骰
    attack = roller.roll_attack("1d20+5")
    hit = attack["total"] >= 13  # vs AC
    
    if hit:
        # 2. 投伤害骰
        damage = roller.roll_damage("1d8+2")
        
        # 3. 生成标准化输出
        output = formatter.format_attack(
            round_num=round_num,
            attack_num=1,
            attacker=attacker,
            target=target,
            attack_roll=attack["formatted"],
            hit=True,
            damage_str=f"{damage['formatted']}挥砍",
            is_crit=attack["is_natural_20"]
        )
        
        # 4. 记录事件
        persistence.log_attack(
            round_num=round_num,
            turn=turn,
            actor=attacker,
            target=target,
            action="攻击",
            damage=f"{damage['formatted']}挥砍",
            damage_total=damage["total"],
            target_hp_before=13,
            target_hp_after=13 - damage["total"]
        )
        
        return output
    else:
        # 未命中输出
        return formatter.format_attack(
            round_num=round_num,
            attack_num=1,
            attacker=attacker,
            target=target,
            attack_roll=attack["formatted"],
            hit=False,
            damage_str=""
        )
```

---

## 完整战斗示例

```python
from battle_persistence import BattlePersistenceManager
from standardized_output import BattleOutputFormatter, DiceRoller

persistence = BattlePersistenceManager("kaelan_vs_skeleton")
formatter = BattleOutputFormatter()
roller = DiceRoller()

# 回合开始
print(formatter.format_round_header(1))

# 凯兰移动
print(formatter.format_movement("凯兰", (2,5), (6,5), distance=25))
persistence.log_move(1, "凯兰", "凯兰", (2,5), (6,5))

# 凯兰攻击
attack = roller.roll_attack("1d20+5")
damage = roller.roll_damage("1d8+2")

output = formatter.format_attack(
    round_num=1, attack_num=1,
    attacker="凯兰", target="骷髅1",
    attack_roll=attack["formatted"],
    hit=attack["total"] >= 13,
    damage_str=f"{damage['formatted']}挥砍",
    is_crit=attack["is_natural_20"]
)
print(output)

# 状态更新
print(formatter.format_status_change(
    "骷髅1",
    hp_before=13,
    hp_after=max(0, 13 - damage["total"]),
    max_hp=13
))

# 回合结束
print(formatter.format_round_end())

# 保存快照
persistence.save_round_snapshot(1)
```

---

## 输出格式速查

| 类型 | 格式 |
|------|------|
| **攻击命中** | `**第R.A击 A→B: 攻击骰X=Y ✅ → 伤害骰...**` |
| **攻击未命中** | `**第R.A击 A→B: 攻击骰X=Y ❌**` |
| **暴击** | `**第R.A击 A→B: 攻击骰X=Y ⚡✅ → 伤害骰...**` |
| **状态变化** | `**名称: HP X→Y/Z 💀, +状态**` |
| **移动** | `**名称 移动: (x1,y1)→(x2,y2) [距离尺]**` |
| **施法** | `**名称 施法: 法术名 → 目标**` |
| **回合标题** | `【第N回合】\n================================` |
