---
name: agars-dm-runtime
description: 当 agent 需要一个仅后端的叙事 DM 运行时，用于导入设定文件、同步战斗结果，并为飞书等聊天渠道生成可直接用于 RP 的 DM 回复上下文时使用。
---

# AGARS 叙事 DM 运行时

这个 skill 把一个 AGARS 风格的叙事后端暴露为本地脚本。

它**不负责战斗规则裁定**。战斗系统产出的结果是唯一事实源。

## 使用顺序

1. 如果战役设定还没有导入，先读 `references/runtime-contract.md`，再运行 `scripts/ingest_setting.py`。
2. 设定导入后，运行 `scripts/build_profiles.py` 生成角色档案缓存。
3. 每次开始新场景或新聊天线程时，运行 `scripts/start_session.py`。
4. 每当战斗状态发生变化时，先读 `references/battle-event-schema.md`，再运行 `scripts/sync_battle.py`。
5. 在准备以 DM 身份回复玩家前，运行 `scripts/dm_reply.py`。
6. 如果回复过程中还需要额外查设定，再运行 `scripts/query_facts.py`。

## 规则

- 把战斗结果当作事实，不要重新解释命中、伤害、状态或资源消耗。
- 设定文本只用来补充连续性、NPC 行为、环境后果和世界反馈。
- 最终 DM 回复应遵守 `references/prompt-policy.md`。
- 不处理前端。这个 skill 只负责后端叙事运行。

## 常用命令

```bash
python3 scripts/ingest_setting.py --base-dir runtime --campaign-id camp_001 --title "Greenest" --file module.md
python3 scripts/build_profiles.py --base-dir runtime --campaign-id camp_001
python3 scripts/start_session.py --base-dir runtime --campaign-id camp_001 --session-id sess_001 --player-name Eli --current-scene "Inside the keep"
python3 scripts/sync_battle.py --base-dir runtime --session-id sess_001 --encounter-id enc_001 --encounter-state-json '{}' --new-events-json '[]'
python3 scripts/dm_reply.py --base-dir runtime --session-id sess_001 --player-message "我让守军关门"
python3 scripts/query_facts.py --base-dir runtime --campaign-id camp_001 --query "Nighthill keep"
```
