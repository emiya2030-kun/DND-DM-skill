from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agars_dm_backend.graph_extractor import HeuristicCampaignGraphExtractor


class FalkorDBGraphStore:
    def __init__(self, *, base_dir: str | Path, backend: Any | None = None, extractor: Any | None = None):
        self.base_dir = Path(base_dir)
        self.metadata_dir = self.base_dir / "metadata"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.backend = backend or FalkorDBPythonBackend.from_env()
        self.extractor = extractor or HeuristicCampaignGraphExtractor()

    def ensure_graph(self, campaign_id: str) -> str:
        return campaign_id

    def reset_campaign_graph(self, campaign_id: str) -> dict[str, Any]:
        alias_path = self._alias_index_path(campaign_id)
        provenance_path = self._provenance_path(campaign_id)
        if alias_path.exists():
            alias_path.unlink()
        if provenance_path.exists():
            provenance_path.unlink()
        if hasattr(self.backend, "reset_graph"):
            self.backend.reset_graph(graph_id=campaign_id)
        return {"graph_id": campaign_id, "reset": True}

    def upsert_entities(self, *, campaign_id: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
        graph_id = self.ensure_graph(campaign_id)
        alias_index = self._load_alias_index(campaign_id)
        provenance = self._load_provenance(campaign_id)

        written_count = 0
        for entity in entities:
            entity_id = entity["entity_id"]
            entity_type = entity["entity_type"]
            properties = self._entity_properties(entity)
            self.backend.upsert_node(
                graph_id=graph_id,
                entity_id=entity_id,
                entity_type=entity_type,
                properties=properties,
            )
            written_count += 1

            canonical_names = entity.get("canonical_names", [])
            for name in canonical_names:
                if isinstance(name, str) and name.strip():
                    alias_index[name.strip()] = entity_id
            if isinstance(entity.get("name"), str) and entity["name"].strip():
                alias_index[entity["name"].strip()] = entity_id

            evidence = entity.get("provenance") or []
            if evidence:
                provenance["nodes"][entity_id] = {"evidence": evidence}

        self._save_alias_index(campaign_id, alias_index)
        self._save_provenance(campaign_id, provenance)
        return {
            "graph_id": graph_id,
            "written_count": written_count,
        }

    def upsert_relationships(self, *, campaign_id: str, relationships: list[dict[str, Any]]) -> dict[str, Any]:
        graph_id = self.ensure_graph(campaign_id)
        provenance = self._load_provenance(campaign_id)

        written_count = 0
        for relationship in relationships:
            source_id = relationship["source_id"]
            target_id = relationship["target_id"]
            relationship_type = relationship["relationship_type"]
            properties = dict(relationship.get("properties") or {})
            self.backend.upsert_relationship(
                graph_id=graph_id,
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship_type,
                properties=properties,
            )
            written_count += 1

            evidence = relationship.get("provenance") or []
            if evidence:
                key = self._relationship_key(source_id, relationship_type, target_id)
                provenance["relationships"][key] = {"evidence": evidence}

        self._save_provenance(campaign_id, provenance)
        return {
            "graph_id": graph_id,
            "written_count": written_count,
        }

    def apply_runtime_updates(self, *, campaign_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        entity_result = {"written_count": 0}
        relationship_result = {"written_count": 0}
        entities = updates.get("entities", [])
        relationships = updates.get("relationships", [])
        if entities:
            entity_result = self.upsert_entities(campaign_id=campaign_id, entities=entities)
        if relationships:
            relationship_result = self.upsert_relationships(campaign_id=campaign_id, relationships=relationships)
        return {
            "graph_id": campaign_id,
            "entity_writes": entity_result["written_count"],
            "relationship_writes": relationship_result["written_count"],
        }

    def ingest_campaign_graph(self, *, campaign_id: str, ontology: dict, snippets: list[dict[str, str]]) -> dict[str, Any]:
        graph_id = self.ensure_graph(campaign_id)
        self.reset_campaign_graph(campaign_id)
        extracted = self.extractor.extract(
            campaign_id=campaign_id,
            ontology=ontology,
            snippets=snippets,
        )
        entities = extracted.get("entities", [])
        entity_ids = {item["entity_id"] for item in entities if item.get("entity_id")}
        relationships = [
            item
            for item in extracted.get("relationships", [])
            if item.get("source_id") in entity_ids and item.get("target_id") in entity_ids
        ]

        if entities:
            self.upsert_entities(campaign_id=campaign_id, entities=entities)
        if relationships:
            self.upsert_relationships(campaign_id=campaign_id, relationships=relationships)

        summary = self.get_graph_summary(campaign_id=campaign_id)
        summary["graph_id"] = graph_id
        summary["ontology"] = ontology
        summary["snippet_count"] = len(snippets)
        return summary

    def get_entity(self, *, campaign_id: str, entity_id: str) -> dict[str, Any] | None:
        matches = self.find_entities(campaign_id=campaign_id, query=None, entity_type=None, limit=1000)
        return next((item for item in matches if item.get("entity_id") == entity_id), None)

    def find_entities(
        self,
        *,
        campaign_id: str,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self.backend.query_entities(
            graph_id=campaign_id,
            query=query,
            entity_type=entity_type,
            limit=limit,
        )

    def get_entity_relationships(
        self,
        *,
        campaign_id: str,
        entity_id: str,
        relationship_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return self.backend.query_relationships(
            graph_id=campaign_id,
            entity_id=entity_id,
            relationship_types=relationship_types,
        )

    def query_facts(self, *, campaign_id: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        entities = self.find_entities(campaign_id=campaign_id, query=query, entity_type=None, limit=limit)
        facts: list[dict[str, Any]] = []
        for entity in entities:
            facts.append(
                {
                    "entity_id": entity.get("entity_id"),
                    "entity_type": entity.get("entity_type"),
                    "name": entity.get("name"),
                    "summary": entity.get("summary", ""),
                }
            )
            relationships = self.get_entity_relationships(
                campaign_id=campaign_id,
                entity_id=entity.get("entity_id", ""),
                relationship_types=None,
            )
            for relationship in relationships[:3]:
                facts.append(
                    {
                        "source_id": relationship["source_id"],
                        "relationship_type": relationship["relationship_type"],
                        "target_id": relationship["target_id"],
                        "properties": relationship.get("properties", {}),
                    }
                )
            if len(facts) >= limit:
                break
        return facts[:limit]

    def get_graph_summary(self, *, campaign_id: str) -> dict[str, Any]:
        entities = self.find_entities(campaign_id=campaign_id, limit=50)
        edge_count = 0
        seen_edges: set[str] = set()
        for entity in entities:
            relationships = self.get_entity_relationships(campaign_id=campaign_id, entity_id=entity["entity_id"])
            for relationship in relationships:
                key = self._relationship_key(
                    relationship["source_id"],
                    relationship["relationship_type"],
                    relationship["target_id"],
                )
                seen_edges.add(key)
        edge_count = len(seen_edges)
        return {
            "graph_id": campaign_id,
            "node_count": len(entities),
            "edge_count": edge_count,
            "entities": entities[:12],
            "facts": self.query_facts(campaign_id=campaign_id, query="", limit=12),
        }

    def _entity_properties(self, entity: dict[str, Any]) -> dict[str, Any]:
        excluded = {"entity_id", "entity_type", "canonical_names", "provenance"}
        return {key: value for key, value in entity.items() if key not in excluded}

    def _relationship_key(self, source_id: str, relationship_type: str, target_id: str) -> str:
        return f"{source_id}|{relationship_type}|{target_id}"

    def _alias_index_path(self, campaign_id: str) -> Path:
        return self.metadata_dir / f"{campaign_id}_alias_index.json"

    def _provenance_path(self, campaign_id: str) -> Path:
        return self.metadata_dir / f"{campaign_id}_provenance.json"

    def _load_alias_index(self, campaign_id: str) -> dict[str, str]:
        path = self._alias_index_path(campaign_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_alias_index(self, campaign_id: str, payload: dict[str, str]) -> None:
        self._alias_index_path(campaign_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_provenance(self, campaign_id: str) -> dict[str, Any]:
        path = self._provenance_path(campaign_id)
        if not path.exists():
            return {"nodes": {}, "relationships": {}}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_provenance(self, campaign_id: str, payload: dict[str, Any]) -> None:
        self._provenance_path(campaign_id).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class _InMemoryGraphBackend:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, dict[str, Any]]] = {}
        self.relationships: dict[str, dict[str, dict[str, Any]]] = {}

    def reset_graph(self, *, graph_id: str) -> None:
        self.nodes[graph_id] = {}
        self.relationships[graph_id] = {}

    def upsert_node(self, *, graph_id: str, entity_id: str, entity_type: str, properties: dict[str, Any]) -> None:
        graph_nodes = self.nodes.setdefault(graph_id, {})
        graph_nodes[entity_id] = {
            "graph_id": graph_id,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "properties": dict(properties),
        }

    def upsert_relationship(
        self,
        *,
        graph_id: str,
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: dict[str, Any],
    ) -> None:
        graph_relationships = self.relationships.setdefault(graph_id, {})
        key = f"{source_id}|{relationship_type}|{target_id}"
        graph_relationships[key] = {
            "graph_id": graph_id,
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
            "properties": dict(properties),
        }

    def query_entities(self, *, graph_id: str, query: str | None = None, entity_type: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        graph_nodes = self.nodes.get(graph_id, {})
        results: list[dict[str, Any]] = []
        lowered = query.lower() if query else None
        for record in graph_nodes.values():
            if entity_type and record["entity_type"] != entity_type:
                continue
            props = record["properties"]
            if lowered:
                haystack = f"{props.get('name', '')} {props.get('summary', '')}".lower()
                if lowered not in haystack:
                    continue
            results.append(
                {
                    "entity_id": record["entity_id"],
                    "entity_type": record["entity_type"],
                    **props,
                }
            )
        return results[:limit]

    def query_relationships(
        self,
        *,
        graph_id: str,
        entity_id: str,
        relationship_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        graph_relationships = self.relationships.get(graph_id, {})
        results: list[dict[str, Any]] = []
        for record in graph_relationships.values():
            if record["source_id"] != entity_id and record["target_id"] != entity_id:
                continue
            if relationship_types and record["relationship_type"] not in relationship_types:
                continue
            results.append(dict(record))
        return results


class FalkorDBPythonBackend:
    def __init__(self, *, host: str, port: int, password: str | None = None):
        try:
            from falkordb import FalkorDB
        except ImportError as exc:
            raise RuntimeError("falkordb package is required to use FalkorDBPythonBackend") from exc

        self._client = FalkorDB(
            host=host,
            port=port,
            password=password or None,
        )

    @classmethod
    def from_env(cls) -> "FalkorDBPythonBackend | _InMemoryGraphBackend":
        host = os.environ.get("FALKORDB_HOST", "localhost")
        port = int(os.environ.get("FALKORDB_PORT", "6379"))
        password = os.environ.get("FALKORDB_PASSWORD", "")
        try:
            return cls(host=host, port=port, password=password)
        except RuntimeError:
            return _InMemoryGraphBackend()

    def reset_graph(self, *, graph_id: str) -> None:
        graph = self._client.select_graph(graph_id)
        graph.query("MATCH (n) DETACH DELETE n")

    def upsert_node(self, *, graph_id: str, entity_id: str, entity_type: str, properties: dict) -> None:
        graph = self._client.select_graph(graph_id)
        payload = dict(properties)
        payload["entity_id"] = entity_id
        payload["entity_type"] = entity_type
        labels = self._labels_for_entity_type(entity_type)
        label_clause = ":".join(labels)
        graph.query(
            f"""
            MERGE (n:{label_clause} {{entity_id: $entity_id}})
            SET n += $props
            SET n.entity_type = $entity_type,
                n.name = coalesce($props.name, n.name),
                n.summary = coalesce($props.summary, n.summary)
            """,
            {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "props": payload,
            },
        )

    def upsert_relationship(
        self,
        *,
        graph_id: str,
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: dict,
    ) -> None:
        graph = self._client.select_graph(graph_id)
        rel_type = self._normalize_relationship_type(relationship_type)
        payload = dict(properties)
        payload["relationship_type"] = relationship_type
        graph.query(
            f"""
            MATCH (s {{entity_id: $source_id}})
            MATCH (t {{entity_id: $target_id}})
            MERGE (s)-[r:{rel_type}]->(t)
            SET r += $props
            """,
            {
                "source_id": source_id,
                "target_id": target_id,
                "props": payload,
            },
        )

    def query_entities(self, *, graph_id: str, query: str | None = None, entity_type: str | None = None, limit: int = 20) -> list[dict]:
        graph = self._client.select_graph(graph_id)
        if query:
            result = graph.query(
                """
                MATCH (n:Entity)
                WHERE ($entity_type IS NULL OR n.entity_type = $entity_type)
                  AND (
                    toLower(coalesce(n.name, "")) CONTAINS toLower($query)
                    OR toLower(coalesce(n.summary, "")) CONTAINS toLower($query)
                  )
                RETURN n
                LIMIT $limit
                """,
                {
                    "entity_type": entity_type,
                    "query": query,
                    "limit": limit,
                },
            )
        else:
            result = graph.query(
                """
                MATCH (n:Entity)
                WHERE ($entity_type IS NULL OR n.entity_type = $entity_type)
                RETURN n
                LIMIT $limit
                """,
                {
                    "entity_type": entity_type,
                    "limit": limit,
                },
            )
        return [self._node_record_to_dict(record[0]) for record in result.result_set]

    def query_relationships(self, *, graph_id: str, entity_id: str, relationship_types: list[str] | None = None) -> list[dict]:
        graph = self._client.select_graph(graph_id)
        result = graph.query(
            """
            MATCH (s)-[r]->(t)
            WHERE s.entity_id = $entity_id OR t.entity_id = $entity_id
            RETURN s.entity_id, type(r), t.entity_id, r
            """,
            {"entity_id": entity_id},
        )
        normalized_types = {self._normalize_relationship_type(item) for item in relationship_types or []}
        rows: list[dict[str, Any]] = []
        for source_id, rel_type, target_id, rel in result.result_set:
            if normalized_types and rel_type not in normalized_types:
                continue
            properties = dict(getattr(rel, "properties", {}) or {})
            rows.append(
                {
                    "graph_id": graph_id,
                    "source_id": source_id,
                    "target_id": target_id,
                    "relationship_type": properties.get("relationship_type", rel_type.lower()),
                    "properties": properties,
                }
            )
        return rows

    def _labels_for_entity_type(self, entity_type: str) -> list[str]:
        normalized = "".join(ch if ch.isalnum() else "_" for ch in entity_type).strip("_") or "EntityNode"
        return ["Entity", normalized]

    def _normalize_relationship_type(self, relationship_type: str) -> str:
        return "".join(ch if ch.isalnum() else "_" for ch in relationship_type.upper()).strip("_") or "RELATED_TO"

    def _node_record_to_dict(self, node: Any) -> dict[str, Any]:
        properties = dict(getattr(node, "properties", {}) or {})
        properties.setdefault("entity_id", properties.get("entity_id", ""))
        properties.setdefault("entity_type", properties.get("entity_type", ""))
        return properties
