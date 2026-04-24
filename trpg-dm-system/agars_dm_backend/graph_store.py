from __future__ import annotations

from typing import Any


class NullGraphStore:
    def ingest_campaign_graph(self, *, campaign_id: str, ontology: dict, snippets: list[dict[str, str]]) -> dict[str, Any]:
        return {
            "graph_id": campaign_id,
            "node_count": 0,
            "edge_count": 0,
            "entities": [],
            "facts": [],
        }
