from __future__ import annotations

from typing import Any


class GraphAwareProfileGenerator:
    def generate_profiles(self, *, campaign_id: str, entities: list[dict], graph_facts: list[dict | str]) -> list[dict[str, Any]]:
        del campaign_id

        relationships_by_source: dict[str, list[dict[str, Any]]] = {}
        for fact in graph_facts:
            if not isinstance(fact, dict) or "relationship_type" not in fact:
                continue
            relationships_by_source.setdefault(fact.get("source_id", ""), []).append(fact)

        profiles: list[dict[str, Any]] = []
        for entity in entities:
            if entity.get("entity_type") != "character":
                continue

            entity_id = entity.get("entity_id", "")
            relation_rows = relationships_by_source.get(entity_id, [])
            faction = ""
            current_location = entity.get("current_location", "")
            goals: list[str] = []
            relationships: list[dict[str, str]] = []

            for row in relation_rows:
                relation = row.get("relationship_type", "")
                target_name = self._target_name(row)
                if relation == "belongs_to":
                    faction = target_name
                elif relation in {"located_in", "imprisoned_in"}:
                    current_location = target_name
                elif relation == "seeks":
                    goals.append(target_name)
                else:
                    relationships.append({"name": target_name, "relation": relation})

            profiles.append(
                {
                    "entity_id": entity_id,
                    "entity_type": "character",
                    "name": entity.get("name", ""),
                    "summary": entity.get("summary", ""),
                    "personality": self._personality(entity=entity, relations=relation_rows),
                    "goals": goals,
                    "current_location": current_location,
                    "faction": faction or entity.get("faction", ""),
                    "status": entity.get("status", ""),
                    "relationships": relationships,
                }
            )
        return profiles

    def _target_name(self, row: dict[str, Any]) -> str:
        properties = row.get("properties", {}) or {}
        if properties.get("target_name"):
            return str(properties["target_name"])
        target_id = row.get("target_id", "")
        if ":" in target_id:
            return target_id.split(":", 1)[1].replace("_", " ")
        return target_id

    def _personality(self, *, entity: dict[str, Any], relations: list[dict[str, Any]]) -> str:
        summary = entity.get("summary", "")
        relation_types = {item.get("relationship_type", "") for item in relations}
        if "guards" in relation_types:
            return "警惕、掌控欲强"
        if "hostile_to" in relation_types:
            return "敌意明显、攻击性强"
        if entity.get("status") == "captured":
            return "紧张、求生欲强"
        return summary[:24]


class NullProfileGenerator(GraphAwareProfileGenerator):
    pass
