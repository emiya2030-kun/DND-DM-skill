# 战斗事件结构

`sync_battle.py` 期望接收的输入结构：

```json
{
  "encounter_id": "enc_001",
  "encounter_state": {
    "round": 2,
    "current_entity_id": "ent_enemy_001",
    "entities": {
      "ent_pc_001": {"name": "Eli"},
      "ent_enemy_001": {"name": "Blue Dragon Wyrmling"}
    }
  },
  "new_events": [
    {
      "event_type": "attack_resolved",
      "actor_entity_id": "ent_enemy_001",
      "target_entity_id": "ent_pc_001",
      "payload": {
        "reason": "Lightning Breath",
        "damage_total": 7,
        "damage_type": "lightning"
      }
    }
  ]
}
```

叙事后端只读取战斗输出，不参与规则裁定。
