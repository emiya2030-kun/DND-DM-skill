# TRPG 战斗持久化系统 (Phase 1)

## 概述

战斗持久化系统提供事件日志记录、回合快照和状态查询功能。

## 文件说明

| 文件 | 功能 | 大小 |
|------|------|------|
| `event_logger.py` | 事件日志核心 | 6.4KB |
| `battle_persistence.py` | 持久化管理器 | 9.2KB |

## 快速开始

```python
import sys
sys.path.insert(0, '/path/to/scripts')

from battle_persistence import BattlePersistenceManager

# 1. 初始化战斗
persistence = BattlePersistenceManager("wraith_fight_001")
persistence.init_battle(width=10, height=10)

# 2. 添加单位 (使用内置 combat_manager)
persistence.combat.add_unit("奎利昂", x=3, y=3, hp=44, max_hp=44, ac=16)
persistence.combat.add_unit("幽魂", x=8, y=8, hp=67, max_hp=67, ac=13)

# 3. 记录事件
persistence.log_attack(
    round_num=1,
    turn="幽魂",
    actor="幽魂",
    target="奎利昂",
    action="生命吸取",
    damage="4d8+3=32黯蚀",
    damage_total=32,
    target_hp_before=44,
    target_hp_after=12
)

# 4. 记录施法
persistence.log_spell(
    round_num=1,
    turn="奎利昂",
    actor="奎利昂",
    spell_name="无限剑制",
    notes="开启剑刃风暴，范围60尺"
)

# 5. 记录移动
persistence.log_move(
    round_num=1,
    turn="奎利昂",
    actor="奎利昂",
    from_pos=(3, 3),
    to_pos=(5, 5)
)

# 6. 回合结束保存快照
persistence.save_round_snapshot(round_num=1)

# 7. 查询回合摘要
print(persistence.get_round_summary(1))
```

## API 参考

### BattlePersistenceManager

#### 初始化

```python
BattlePersistenceManager(battle_id: str, base_dir: str = "/tmp/trpg_battles")
```

| 参数 | 说明 |
|------|------|
| `battle_id` | 战斗唯一标识符 |
| `base_dir` | 数据存储根目录 |

#### 方法

| 方法 | 说明 |
|------|------|
| `init_battle(width, height)` | 初始化新战斗 |
| `log_attack(...)` | 记录攻击事件 |
| `log_move(...)` | 记录移动事件 |
| `log_spell(...)` | 记录施法事件 |
| `log_status_change(...)` | 记录状态变化 |
| `log_use_item(...)` | 记录使用物品 |
| `save_round_snapshot(round_num)` | 保存回合快照 |
| `get_current_state()` | 获取当前状态 |
| `get_round_events(round_num)` | 获取回合事件列表 |
| `get_round_summary(round_num)` | 获取格式化回合摘要 |
| `finalize_battle(...)` | 战斗结束处理 |

### 事件格式

```python
{
    "event": "attack",           # 事件类型
    "round": 1,                  # 回合数
    "turn": "奎利昂",            # 当前行动角色
    "actor": "奎利昂",           # 事件执行者
    "target": "幽魂",            # 目标
    "action": "投影武器攻击",    # 动作描述
    "damage": "1d6+4=7穿刺",    # 伤害详情
    "damage_total": 13,          # 总伤害
    "target_hp_change": "67→54", # HP变化
    "spell_slot_used": 1         # 消耗法术位 (可选)
}
```

## 数据存储结构

```
/tmp/trpg_battles/
└── {battle_id}/
    ├── current_state.json      # 当前战斗状态
    ├── events.jsonl            # 事件日志 (战斗中)
    ├── rounds/
    │   ├── round_1.json        # 回合1快照
    │   └── round_2.json        # 回合2快照
    └── battle_summary.json     # 战斗总结 (战斗结束后)
```

## 战斗结束处理

```python
# 战斗结束时调用
result = persistence.finalize_battle(
    result="奎利昂胜利",
    summary_text="奎利昂在生命垂危时开启无限剑制，最终击败幽魂",
    key_moments=[
        "第1回合：幽魂生命吸取，奎利昂HP上限降至12",
        "第1回合：奎利昂开启无限剑制"
    ]
)
```

调用后会：
1. 生成 `battle_summary.json`
2. 删除 `events.jsonl`
3. 保留 `rounds/` 快照

## 查询示例

```python
# 获取上回合摘要
print(persistence.get_last_round_summary())

# 获取指定回合事件
events = persistence.get_round_events(1)
for e in events:
    print(f"{e['actor']}: {e['action']}")

# 获取当前状态
state = persistence.get_current_state()
print(f"当前回合: {state['round']}")
print(f"参战单位: {list(state['units'].keys())}")
```

## 与 combat_manager.py 的关系

`BattlePersistenceManager` 封装了 `CombatManager`，可以直接访问：

```python
# 直接使用 combat_manager 的方法
persistence.combat.damage_unit("幽魂", 13, "force")
persistence.combat.move_unit("奎利昂", 5, 5)
persistence.combat.use_action("奎利昂")
```

## 注意事项

1. **事件日志只在战斗中保留** - 战斗结束后自动删除
2. **回合快照永久保留** - 用于历史回溯
3. **数据存储在 `/tmp/trpg_battles/`** - 系统重启可能丢失
4. **如需持久化请修改 `base_dir`** - 如 `/home/ubuntu/trpg_data/`
