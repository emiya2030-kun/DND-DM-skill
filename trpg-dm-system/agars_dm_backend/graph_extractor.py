from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any


class TwoStageHeuristicCampaignGraphExtractor:
    def extract(
        self,
        *,
        campaign_id: str,
        ontology: dict[str, Any],
        snippets: list[dict[str, str]],
    ) -> dict[str, list[dict[str, Any]]]:
        del campaign_id, ontology

        entities = self._collect_entities(snippets)
        relationships = self._collect_relationships(snippets, entities)
        return {
            "entities": list(entities.values()),
            "relationships": list(relationships.values()),
        }

    def _collect_entities(self, snippets: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
        entities: dict[str, dict[str, Any]] = {}
        for index, snippet in enumerate(snippets, start=1):
            text = (snippet.get("text") or "").strip()
            if not text:
                continue
            evidence = self._evidence(snippet=snippet, snippet_index=index, text=text)

            for faction_name in self._extract_factions(text):
                self._merge_entity(
                    entities,
                    {
                        "entity_id": self._entity_id("faction", faction_name),
                        "entity_type": "faction",
                        "name": faction_name,
                        "summary": evidence["excerpt"],
                        "canonical_names": [faction_name],
                        "provenance": [evidence],
                    },
                )

            proper_names = self._extract_proper_names(text)
            location_names = self._extract_location_names(text, proper_names)
            character_names = [item for item in proper_names if item not in location_names]

            for location_name in location_names:
                self._merge_entity(
                    entities,
                    {
                        "entity_id": self._entity_id("location", location_name),
                        "entity_type": "location",
                        "name": location_name,
                        "summary": evidence["excerpt"],
                        "canonical_names": [location_name],
                        "provenance": [evidence],
                    },
                )

            for character_name in character_names:
                self._merge_entity(
                    entities,
                    {
                        "entity_id": self._entity_id("character", character_name),
                        "entity_type": "character",
                        "name": character_name,
                        "summary": evidence["excerpt"],
                        "canonical_names": [character_name],
                        "provenance": [evidence],
                    },
                )

            for item_name in self._extract_items(text):
                self._merge_entity(
                    entities,
                    {
                        "entity_id": self._entity_id("item", item_name),
                        "entity_type": "item",
                        "name": item_name,
                        "summary": evidence["excerpt"],
                        "canonical_names": [item_name],
                        "provenance": [evidence],
                    },
                )
        return entities

    def _collect_relationships(
        self,
        snippets: list[dict[str, str]],
        entities: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        relationships: dict[str, dict[str, Any]] = {}
        name_index = self._name_index(entities)

        for index, snippet in enumerate(snippets, start=1):
            text = (snippet.get("text") or "").strip()
            if not text:
                continue
            lowered = text.lower()
            evidence = self._evidence(snippet=snippet, snippet_index=index, text=text)
            mentioned = self._mentioned_entities(text, entities, name_index)
            characters = [item for item in mentioned if item["entity_type"] == "character"]
            factions = [item for item in mentioned if item["entity_type"] == "faction"]
            locations = [item for item in mentioned if item["entity_type"] == "location"]
            items = [item for item in mentioned if item["entity_type"] == "item"]

            if characters and factions and self._contains_any(lowered, ["commands", "serves", "member of", "belongs to"]):
                self._merge_relationship(
                    relationships,
                    self._relationship_payload(
                        source_id=characters[0]["entity_id"],
                        target_id=factions[0]["entity_id"],
                        relationship_type="belongs_to",
                        target_name=factions[0]["name"],
                        evidence=evidence,
                    ),
                )

            if characters and locations and self._contains_any(
                lowered,
                [" at ", " in ", " inside ", " within ", "beneath", " under ", "waits in", "位于", "在", "囚于"],
            ):
                self._merge_relationship(
                    relationships,
                    self._relationship_payload(
                        source_id=characters[0]["entity_id"],
                        target_id=locations[0]["entity_id"],
                        relationship_type="located_in",
                        target_name=locations[0]["name"],
                        evidence=evidence,
                    ),
                )

            if characters and locations and self._contains_any(lowered, ["guards", "watches", "看守", "守着"]):
                self._merge_relationship(
                    relationships,
                    self._relationship_payload(
                        source_id=characters[0]["entity_id"],
                        target_id=locations[0]["entity_id"],
                        relationship_type="guards",
                        target_name=locations[0]["name"],
                        evidence=evidence,
                    ),
                )

            if len(characters) >= 2 and self._contains_any(lowered, ["travels with", "joins", "同行", "结伴"]):
                self._merge_relationship(
                    relationships,
                    self._relationship_payload(
                        source_id=characters[0]["entity_id"],
                        target_id=characters[1]["entity_id"],
                        relationship_type="travels_with",
                        target_name=characters[1]["name"],
                        evidence=evidence,
                    ),
                )

            if characters and items and self._contains_any(lowered, ["seeks", "wants", "寻找", "想要", "追寻"]):
                self._merge_relationship(
                    relationships,
                    self._relationship_payload(
                        source_id=characters[0]["entity_id"],
                        target_id=items[0]["entity_id"],
                        relationship_type="seeks",
                        target_name=items[0]["name"],
                        evidence=evidence,
                    ),
                )

        return relationships

    def _relationship_payload(
        self,
        *,
        source_id: str,
        target_id: str,
        relationship_type: str,
        target_name: str,
        evidence: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
            "properties": {
                "confidence": "heuristic",
                "status": "active",
                "target_name": target_name,
            },
            "provenance": [evidence],
        }

    def _extract_factions(self, text: str) -> list[str]:
        matches = re.findall(
            r"\b((?:House|Cult|Order|Clan|Guild)\s+(?:of\s+the\s+)?[A-Z][A-Za-z'/-]+(?:\s+[A-Z][A-Za-z'/-]+){0,3})\b",
            text,
        )
        return self._dedupe(matches)

    def _extract_proper_names(self, text: str) -> list[str]:
        candidates = re.findall(r"\b([A-Z][A-Za-z'/-]+(?:\s+[A-Z][A-Za-z'/-]+){0,3})\b", text)
        filtered: list[str] = []
        stopwords = {"The", "A", "An", "And", "But", "Or"}
        for candidate in candidates:
            if candidate in stopwords:
                continue
            if candidate.startswith(("House ", "Cult ", "Order ", "Clan ", "Guild ")):
                continue
            filtered.append(candidate.strip())
        return self._dedupe(filtered)

    def _extract_location_names(self, text: str, proper_names: list[str]) -> list[str]:
        locations: list[str] = []
        for name in proper_names:
            if re.search(rf"\b(?:at|in|inside|within|beneath|under)\s+{re.escape(name)}\b", text, flags=re.IGNORECASE):
                locations.append(name)

        common_location_matches = re.findall(
            r"\b(?:the\s+)?((?:old\s+|secret\s+)?(?:slave pen|keep|tunnel|cavern|outpost|fortress|gate|temple|mill|camp|velkynvelve))\b",
            text,
            flags=re.IGNORECASE,
        )
        for item in common_location_matches:
            locations.append(" ".join(part.capitalize() for part in item.split()))
        return self._dedupe(locations)

    def _extract_items(self, text: str) -> list[str]:
        matches = re.findall(
            r"\b((?:slave|iron|magic|stolen)\s+(?:key|map|idol|amulet|sword|book|manacles|chain|ring))\b",
            text,
            flags=re.IGNORECASE,
        )
        return self._dedupe([" ".join(part.capitalize() for part in item.split()) for item in matches])

    def _mentioned_entities(
        self,
        text: str,
        entities: dict[str, dict[str, Any]],
        name_index: dict[str, str],
    ) -> list[dict[str, Any]]:
        lowered = text.lower()
        matched_ids: list[str] = []
        for alias, entity_id in name_index.items():
            if not alias:
                continue
            if alias.isascii():
                if alias.lower() in lowered:
                    matched_ids.append(entity_id)
            elif alias in text:
                matched_ids.append(entity_id)

        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for entity_id in matched_ids:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            result.append(entities[entity_id])
        return result

    def _name_index(self, entities: dict[str, dict[str, Any]]) -> dict[str, str]:
        index: dict[str, str] = {}
        for entity in entities.values():
            for alias in entity.get("canonical_names", []):
                index[alias] = entity["entity_id"]
            if entity.get("name"):
                index[entity["name"]] = entity["entity_id"]
        return index

    def _entity_id(self, entity_type: str, name: str) -> str:
        slug = self._slugify(name)
        if not slug:
            slug = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
        return f"{entity_type}:{slug}"

    def _slugify(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
        ascii_value = ascii_value.lower()
        return re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")

    def _evidence(self, *, snippet: dict[str, str], snippet_index: int, text: str) -> dict[str, str]:
        return {
            "source_file": snippet.get("source", ""),
            "snippet_id": f"snippet_{snippet_index:03d}",
            "excerpt": text[:240],
        }

    def _merge_entity(self, entities: dict[str, dict[str, Any]], entity: dict[str, Any]) -> None:
        existing = entities.get(entity["entity_id"])
        if not existing:
            entities[entity["entity_id"]] = entity
            return
        existing["canonical_names"] = self._dedupe(existing.get("canonical_names", []) + entity.get("canonical_names", []))
        existing["provenance"] = existing.get("provenance", []) + entity.get("provenance", [])

    def _merge_relationship(self, relationships: dict[str, dict[str, Any]], relationship: dict[str, Any]) -> None:
        key = f"{relationship['source_id']}|{relationship['relationship_type']}|{relationship['target_id']}"
        existing = relationships.get(key)
        if not existing:
            relationships[key] = relationship
            return
        existing["provenance"] = existing.get("provenance", []) + relationship.get("provenance", [])

    def _contains_any(self, text: str, needles: list[str]) -> bool:
        return any(needle in text for needle in needles)

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                result.append(value)
        return result


HeuristicCampaignGraphExtractor = TwoStageHeuristicCampaignGraphExtractor
