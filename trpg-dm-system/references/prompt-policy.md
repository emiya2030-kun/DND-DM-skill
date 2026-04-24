# Prompt 策略

当 agent 使用 `dm_reply.py` 时，应遵守：

- 以战斗结算结果为权威事实
- 设定片段只用于补充连续性，不得覆盖战斗事实
- 输出应包含：
  - `narration`
  - `npc_reactions`
  - `world_effects`
  - `memory_updates`
  - `suggested_followups`

如果战斗结果与既有设定假设冲突，以当前场景中的战斗结果为准。
