# Companion NPC Turn Flow

1. 回合开始先读 `GetEncounterState`
2. 若玩家已明确下达战术指令，优先执行
3. 若玩家未明确指挥，自主采取合理行动
4. 优先保护玩家阵营、补位、支援、处理玩家当前威胁
5. 不擅自做高风险剧情决定
6. 仍然严格遵守同一套 runtime-protocol
