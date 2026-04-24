# 运行时契约

## 目标

把 AGARS 风格的叙事后端能力以确定性的本地脚本形式暴露给 DM agent 调用。

## 核心命令

- `scripts/ingest_setting.py`
- `scripts/build_profiles.py`
- `scripts/start_session.py`
- `scripts/sync_battle.py`
- `scripts/dm_reply.py`
- `scripts/query_facts.py`

## 状态目录结构

- `runtime/campaigns/<campaign_id>.json`：已导入的设定文本、ontology、graph 摘要
- `runtime/profiles/<campaign_id>.json`：从图摘要生成的角色档案缓存
- `runtime/sessions/<session_id>.json`：当前场景、战斗摘要、近期记忆

## 非目标

- 不处理前端
- 不直接处理战斗规则裁定
- 最小版本不强制依赖 FalkorDB / Zep
