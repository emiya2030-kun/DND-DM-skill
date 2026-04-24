from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib import error, request


class OpenAiCompatibleLocationMapInferer:
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

    def extract_locations(self, *, chunk_text: str) -> list[str]:
        if not self.api_key or not self.model or not chunk_text.strip():
            return []
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是 TRPG 地点抽取助手。只返回 JSON。"},
                {
                    "role": "user",
                    "content": (
                        "请从以下文本中提取真实出现的具名地点，返回 JSON："
                        "{\"locations\": [\"地点1\", \"地点2\"]}\n\n"
                        f"{chunk_text[:6000]}"
                    ),
                },
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        parsed = self._post_json(payload)
        locations = parsed.get("locations", []) if isinstance(parsed, dict) else []
        return [str(item).strip() for item in locations if str(item).strip()]

    def infer_from_location_list(
        self,
        *,
        current_scene: str,
        location_names: list[str],
        location_facts: list[str],
    ) -> dict[str, Any]:
        if not self.api_key or not self.model or not location_names:
            return {}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是叙事世界的地图设计师。根据已知地点和世界设定，生成清晰合理的空间拓扑关系。只返回 JSON。"},
                {
                    "role": "user",
                    "content": (
                        "根据以下信息，为叙事世界生成地点邻接关系地图。\n\n"
                        f"【世界设定】\n{current_scene or '一个虚构的叙事世界'}\n\n"
                        "【已知地点列表】\n"
                        + "\n".join(f"- {loc}" for loc in location_names)
                        + "\n\n【地点相关背景信息】\n"
                        + ("\n".join(location_facts) if location_facts else "（无额外地点信息）")
                        + "\n\n返回格式：{\"locations\": {\"地点名称\": {\"description\": \"...\", \"adjacent\": [\"地点A\"]}}}"
                    ),
                },
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        parsed = self._post_json(payload)
        return parsed.get("locations", parsed) if isinstance(parsed, dict) else {}

    def infer_from_scene(self, *, current_scene: str, source_text: str) -> dict[str, Any]:
        if not self.api_key or not self.model or not (current_scene or source_text):
            return {}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是叙事世界的地图设计师。根据故事设定，设计清晰合理的空间拓扑。只返回 JSON。"},
                {
                    "role": "user",
                    "content": (
                        "根据以下信息，提取并设计该叙事世界的地点列表及其空间邻接关系。\n\n"
                        f"【世界设定 / 初始场景描述】\n{current_scene or '（无）'}\n\n"
                        f"【原始文件内容】\n{source_text[:8000] or '（无）'}\n\n"
                        "返回格式：{\"locations\": {\"地点名\": {\"description\": \"...\", \"adjacent\": [\"地点A\"]}}}"
                    ),
                },
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        parsed = self._post_json(payload)
        return parsed.get("locations", parsed) if isinstance(parsed, dict) else {}

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
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
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except (error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError):
            return {}


class LocationGraphBuilder:
    def __init__(self, *, map_inferer: Any | None = None, chunk_size: int = 5000):
        self.map_inferer = map_inferer or OpenAiCompatibleLocationMapInferer()
        self.chunk_size = chunk_size

    def build(
        self,
        *,
        graph_summary: dict[str, Any],
        snippets: list[dict[str, str]],
        current_scene: str = "",
        source_text: str = "",
    ) -> dict[str, dict[str, Any]]:
        locations = self._seed_locations(graph_summary=graph_summary, snippets=snippets, current_scene=current_scene)

        if source_text:
            for name in self.extract_locations_from_text(source_text):
                self._ensure_location(locations, name)

        self._apply_rule_connections(locations, snippets)
        location_facts = self._location_facts(graph_summary)

        inferred: dict[str, dict[str, Any]] = {}
        if len(locations) > 1:
            inferred = self._infer_from_location_list(
                location_names=[item["name"] for item in locations.values()],
                current_scene=current_scene,
                location_facts=location_facts,
            )
            if inferred:
                self._merge_inferred_map(locations, inferred)

        if not locations or not any(item.get("adjacent") for item in locations.values()):
            fallback = self._infer_from_scene(current_scene=current_scene, source_text=source_text or self._join_snippets(snippets))
            if fallback:
                self._merge_inferred_map(locations, fallback)

        if len(locations) > 1 and not any(item.get("adjacent") for item in locations.values()):
            location_ids = list(locations.keys())
            for source_id in location_ids:
                for target_id in location_ids:
                    if source_id != target_id:
                        self._connect(locations, source_id, target_id)

        return locations

    def extract_locations_from_text(self, text: str) -> list[str]:
        if not text.strip():
            return []
        chunks = [text[i:i + self.chunk_size] for i in range(0, len(text), self.chunk_size)] or [text]
        all_locations: set[str] = set()
        for chunk in chunks:
            extracted = []
            if hasattr(self.map_inferer, "extract_locations"):
                extracted = self.map_inferer.extract_locations(chunk_text=chunk) or []
            if not extracted:
                extracted = self._regex_extract_locations(chunk)
            all_locations.update(self._normalize_location_name(item) for item in extracted if item)
        return sorted(item for item in all_locations if item)

    def _seed_locations(
        self,
        *,
        graph_summary: dict[str, Any],
        snippets: list[dict[str, str]],
        current_scene: str,
    ) -> dict[str, dict[str, Any]]:
        locations: dict[str, dict[str, Any]] = {}
        for entity in graph_summary.get("entities", []):
            if entity.get("entity_type") != "location":
                continue
            self._ensure_location(locations, entity.get("name", ""), description=entity.get("summary", ""))

        for snippet in snippets:
            text = (snippet.get("text") or "").strip()
            if not text:
                continue
            for heading in self._extract_headings(text):
                self._ensure_location(locations, heading, description=f"来源于 {snippet.get('source', '')}")

        if current_scene:
            self._ensure_location(locations, current_scene, description="当前场景")
        return locations

    def _apply_rule_connections(self, locations: dict[str, dict[str, Any]], snippets: list[dict[str, str]]) -> None:
        for snippet in snippets:
            text = (snippet.get("text") or "").strip()
            if not text:
                continue
            for left, right in self._extract_connections(text):
                left_id = self._ensure_location(locations, left)
                right_id = self._ensure_location(locations, right)
                self._connect(locations, left_id, right_id)

    def _infer_from_location_list(
        self,
        *,
        location_names: list[str],
        current_scene: str,
        location_facts: list[str],
    ) -> dict[str, Any]:
        if not location_names or not hasattr(self.map_inferer, "infer_from_location_list"):
            return {}

        filtered_names = [name for name in location_names if len(name) >= 2]
        if not filtered_names:
            filtered_names = location_names

        best_map: dict[str, Any] = {}
        for attempt in range(2):
            use_names = filtered_names if attempt == 0 else filtered_names[: max(3, min(60, len(filtered_names)))]
            inferred = self.map_inferer.infer_from_location_list(
                current_scene=current_scene,
                location_names=use_names,
                location_facts=location_facts,
            ) or {}
            normalized = self._normalize_inferred_map(inferred)
            if normalized and not self._looks_truncated(input_names=use_names, normalized_map=normalized):
                return normalized
            if len(normalized) > len(best_map):
                best_map = normalized
        return best_map

    def _infer_from_scene(self, *, current_scene: str, source_text: str) -> dict[str, Any]:
        if not hasattr(self.map_inferer, "infer_from_scene"):
            return {}
        inferred = self.map_inferer.infer_from_scene(current_scene=current_scene, source_text=source_text) or {}
        return self._normalize_inferred_map(inferred)

    def _looks_truncated(
        self,
        *,
        input_names: list[str],
        normalized_map: dict[str, dict[str, Any]],
    ) -> bool:
        input_count = len(input_names)
        if input_count <= 3:
            return False
        expected_ids = {self._location_id(name) for name in input_names}
        covered_count = len(expected_ids.intersection(normalized_map.keys()))
        minimum_coverage = max(3, (input_count * 3 + 3) // 4)
        return covered_count < minimum_coverage

    def _normalize_inferred_map(self, inferred: dict[str, Any]) -> dict[str, dict[str, Any]]:
        raw_locations = inferred.get("locations", inferred) if isinstance(inferred, dict) else {}
        normalized: dict[str, dict[str, Any]] = {}
        for raw_key, data in raw_locations.items():
            if not isinstance(data, dict):
                continue
            name = self._normalize_location_name(str(data.get("name") or raw_key))
            location_id = self._ensure_location(normalized, str(data.get("name") or raw_key))
            if data.get("description") and not normalized[location_id]["description"]:
                normalized[location_id]["description"] = str(data.get("description"))
            for adjacent_raw in data.get("adjacent", []):
                adjacent_id = self._ensure_location(normalized, str(adjacent_raw))
                if adjacent_id != location_id and adjacent_id not in normalized[location_id]["adjacent"]:
                    normalized[location_id]["adjacent"].append(adjacent_id)

        all_ids = set(normalized.keys())
        for loc_id, data in list(normalized.items()):
            cleaned = [adj for adj in data["adjacent"] if adj in all_ids and adj != loc_id]
            data["adjacent"] = list(dict.fromkeys(cleaned))
        for loc_id, data in list(normalized.items()):
            for adjacent_id in data["adjacent"]:
                if loc_id not in normalized[adjacent_id]["adjacent"]:
                    normalized[adjacent_id]["adjacent"].append(loc_id)
        return normalized

    def _merge_inferred_map(self, locations: dict[str, dict[str, Any]], inferred: dict[str, dict[str, Any]]) -> None:
        for location_id, data in inferred.items():
            existing = locations.setdefault(
                location_id,
                {
                    "name": data.get("name", location_id),
                    "description": data.get("description", ""),
                    "adjacent": [],
                    "aliases": [],
                },
            )
            self._register_location_variant(existing, data.get("name", location_id))
            for alias in data.get("aliases", []):
                self._register_location_variant(existing, alias)
            if data.get("description") and not existing.get("description"):
                existing["description"] = data["description"]
            for adjacent_id in data.get("adjacent", []):
                locations.setdefault(
                    adjacent_id,
                    {
                        "name": adjacent_id.split(":", 1)[1].replace("_", " ").title(),
                        "description": "",
                        "adjacent": [],
                        "aliases": [],
                    },
                )
                self._connect(locations, location_id, adjacent_id)

    def _location_facts(self, graph_summary: dict[str, Any]) -> list[str]:
        facts: list[str] = []
        for entity in graph_summary.get("entities", []):
            if entity.get("entity_type") == "location" and entity.get("summary"):
                facts.append(f"- {entity.get('name', '')}: {entity.get('summary', '')[:120]}")
        return facts

    def _join_snippets(self, snippets: list[dict[str, str]]) -> str:
        return "\n\n".join(item.get("text", "") for item in snippets[:10])

    def _regex_extract_locations(self, text: str) -> list[str]:
        matches = re.findall(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3})\b", text)
        stop = {"The", "A", "An", "And", "But", "Or"}
        return [item for item in matches if item not in stop]

    def _extract_headings(self, text: str) -> list[str]:
        matches = re.findall(r"(?m)^#{1,6}\s+(.+)$", text)
        return [item.strip() for item in matches if item.strip()]

    def _extract_connections(self, text: str) -> list[tuple[str, str]]:
        connections: list[tuple[str, str]] = []
        separators = [
            " connects to ",
            " leads to ",
            " is adjacent to ",
            " 通往 ",
            " 连接到 ",
        ]
        for raw_line in text.splitlines():
            line = raw_line.strip().strip(".。")
            if not line or line.startswith("#"):
                continue
            lowered = line.lower()
            for separator in separators:
                needle = separator.strip().lower() if separator.isascii() else separator.strip()
                if needle not in lowered:
                    continue
                split_token = separator.strip()
                parts = re.split(re.escape(split_token), line, maxsplit=1, flags=re.IGNORECASE)
                if len(parts) != 2:
                    continue
                left = parts[0].strip(" .。")
                right = parts[1].strip(" .。")
                if left and right:
                    connections.append((left, right))
                break
        return connections

    def _ensure_location(self, locations: dict[str, dict[str, Any]], name: str, description: str = "") -> str:
        normalized_name = self._normalize_location_name(name)
        location_id = self._location_id(normalized_name)
        existing = locations.setdefault(
            location_id,
            {
                "name": self._canonical_display_name(name),
                "description": description,
                "adjacent": [],
                "aliases": [],
            },
        )
        self._register_location_variant(existing, name)
        if description and not existing.get("description"):
            existing["description"] = description
        return location_id

    def _connect(self, locations: dict[str, dict[str, Any]], left_id: str, right_id: str) -> None:
        if left_id == right_id:
            return
        if right_id not in locations[left_id]["adjacent"]:
            locations[left_id]["adjacent"].append(right_id)
        if left_id not in locations[right_id]["adjacent"]:
            locations[right_id]["adjacent"].append(left_id)

    def _location_id(self, name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", self._normalize_location_name(name).lower()).strip("_")
        return f"location:{slug or 'unknown'}"

    def _normalize_location_name(self, name: str) -> str:
        value = re.sub(r"\s+", " ", name.strip())
        value = value.strip(" .。,:;!?'\"`()[]{}")
        value = re.sub(r"^(?:the)\s+", "", value, flags=re.IGNORECASE)
        value = re.sub(r"[-_]+", " ", value)
        value = re.sub(r"\s+", " ", value).strip()
        return value

    def _register_location_variant(self, location: dict[str, Any], raw_name: str) -> None:
        alias = re.sub(r"\s+", " ", str(raw_name or "").strip())
        alias = alias.strip(" .。,:;!?'\"`()[]{}")
        if alias and alias not in location["aliases"]:
            location["aliases"].append(alias)
            location["aliases"] = sorted(
                location["aliases"],
                key=self._alias_score,
                reverse=True,
            )

        candidate = self._canonical_display_name(raw_name)
        current = location.get("name", "")
        if not current or self._canonical_name_score(candidate) > self._canonical_name_score(current):
            location["name"] = candidate

    def _canonical_display_name(self, raw_name: str) -> str:
        value = self._normalize_location_name(raw_name)
        if re.fullmatch(r"[a-z0-9 ]+", value):
            return " ".join(part.capitalize() for part in value.split())
        return value

    def _canonical_name_score(self, name: str) -> tuple[int, int, int]:
        normalized = self._normalize_location_name(name)
        words = normalized.split()
        title_case_words = sum(1 for word in str(name).split() if word[:1].isupper())
        punctuation_penalty = -sum(1 for ch in str(name) if ch in "-_")
        return (
            title_case_words,
            punctuation_penalty,
            len(words),
        )

    def _alias_score(self, name: str) -> tuple[int, int, int]:
        return self._canonical_name_score(name)
