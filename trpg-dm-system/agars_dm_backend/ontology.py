from __future__ import annotations

import json
import os
from typing import Any
from urllib import error, request


DEFAULT_ONTOLOGY = {
    "analysis_summary": "识别出角色、地点、阵营、剧情道具、线索与目标。",
    "entity_types": [
        {"name": "character", "description": "角色实体，包含 PC、NPC、怪物、囚徒和同伴。"},
        {"name": "faction", "description": "阵营、组织、家族或稳定群体。"},
        {"name": "location", "description": "城市、据点、房间、洞穴、区域等地点。"},
        {"name": "item", "description": "剧情关键道具、钥匙、信物、宝物或证据。"},
        {"name": "clue", "description": "可以推动决策的线索、秘密、规则性发现。"},
        {"name": "objective", "description": "当前驱动剧情的目标。"},
    ],
    "edge_types": [
        {"name": "located_in", "description": "某对象当前位于某地点。"},
        {"name": "belongs_to", "description": "某对象归属于角色、阵营或地点。"},
        {"name": "captured_by", "description": "某角色被角色或阵营俘获。"},
        {"name": "imprisoned_in", "description": "某角色被关押在某地点。"},
        {"name": "guards", "description": "角色或阵营负责看守地点、人物或物品。"},
        {"name": "allied_with", "description": "双方存在稳定盟友关系。"},
        {"name": "hostile_to", "description": "双方存在稳定敌对关系。"},
        {"name": "travels_with", "description": "双方正在共同旅行或同行。"},
        {"name": "knows_about", "description": "某角色知道某条线索、地点、物品或事实。"},
        {"name": "seeks", "description": "某角色或阵营试图获取、找到或达成某事。"},
    ],
}


class OpenAiCompatibleOntologyGenerator:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.api_key = api_key or os.environ.get("LLM_API_KEY")
        self.model = model or os.environ.get("LLM_MODEL_NAME")

    def generate(self, *, title: str, combined_text: str, snippets: list[dict[str, str]]) -> dict[str, Any]:
        if not self.api_key or not self.model:
            return DEFAULT_ONTOLOGY.copy()

        prompt = self._build_prompt(title=title, combined_text=combined_text, snippets=snippets)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 TRPG 世界建模助手。请根据给定设定文本输出 JSON，"
                        "只返回包含 analysis_summary、entity_types、edge_types 的对象。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            return DEFAULT_ONTOLOGY.copy()

        try:
            content = body["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            return DEFAULT_ONTOLOGY.copy()

        return self._normalize(parsed)

    def _build_prompt(self, *, title: str, combined_text: str, snippets: list[dict[str, str]]) -> str:
        snippet_preview = "\n\n".join(item["text"][:600] for item in snippets[:8])
        combined_preview = combined_text[:12000]
        return (
            f"战役标题：{title}\n\n"
            "请基于以下设定文本，为 TRPG 叙事系统生成 ontology。\n"
            "节点类型只允许从以下语义中挑选和细化：角色、阵营、地点、剧情道具、线索、目标。\n"
            "边类型优先考虑：located_in、belongs_to、captured_by、imprisoned_in、guards、"
            "allied_with、hostile_to、travels_with、knows_about、seeks。\n\n"
            "输出要求：\n"
            "1. 返回 JSON 对象。\n"
            "2. analysis_summary 用中文。\n"
            "3. entity_types 和 edge_types 只保留最值得放入图谱的类型。\n"
            "4. 不要输出战斗数值、回合状态、HP 或 DC 规则文本。\n\n"
            f"文本预览：\n{combined_preview}\n\n"
            f"片段预览：\n{snippet_preview}"
        )

    def _normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "analysis_summary": payload.get("analysis_summary") or DEFAULT_ONTOLOGY["analysis_summary"],
            "entity_types": payload.get("entity_types") or DEFAULT_ONTOLOGY["entity_types"],
            "edge_types": payload.get("edge_types") or DEFAULT_ONTOLOGY["edge_types"],
        }
        return normalized
