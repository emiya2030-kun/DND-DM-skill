from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agars_dm_backend.file_parser import extract_text, split_snippets
from agars_dm_backend.falkor_graph_store import FalkorDBGraphStore
from agars_dm_backend.location_graph_builder import LocationGraphBuilder
from agars_dm_backend.ontology import OpenAiCompatibleOntologyGenerator
from agars_dm_backend.profile_generator import GraphAwareProfileGenerator
from agars_dm_backend.world_state_engine import NarrativeWorldStateEngine


class NarrativeDmService:
    def __init__(
        self,
        *,
        base_dir: str | Path,
        ontology_generator: Any | None = None,
        graph_store: Any | None = None,
        profile_generator: Any | None = None,
        world_state_engine: Any | None = None,
        location_graph_builder: Any | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.campaigns_dir = self.base_dir / "campaigns"
        self.sessions_dir = self.base_dir / "sessions"
        self.profiles_dir = self.base_dir / "profiles"
        self.campaigns_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.ontology_generator = ontology_generator or OpenAiCompatibleOntologyGenerator()
        self.graph_store = graph_store or FalkorDBGraphStore(base_dir=self.base_dir)
        self.profile_generator = profile_generator or GraphAwareProfileGenerator()
        self.world_state_engine = world_state_engine or NarrativeWorldStateEngine()
        self.location_graph_builder = location_graph_builder or LocationGraphBuilder()

    def ingest_setting(
        self,
        *,
        campaign_id: str,
        title: str,
        file_paths: list[str | Path],
    ) -> dict[str, Any]:
        documents: list[dict[str, Any]] = []
        combined_text_parts: list[str] = []
        snippets: list[dict[str, str]] = []

        for file_path in file_paths:
            path = Path(file_path)
            text = extract_text(path)
            documents.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "text_length": len(text),
                }
            )
            combined_text_parts.append(f"=== {path.name} ===\n{text}")
            snippets.extend(
                {
                    "source": path.name,
                    "text": snippet,
                }
                for snippet in split_snippets(text)
            )

        combined_text = "\n\n".join(combined_text_parts)
        ontology = self.ontology_generator.generate(
            title=title,
            combined_text=combined_text,
            snippets=snippets,
        )
        graph_summary = self.graph_store.ingest_campaign_graph(
            campaign_id=campaign_id,
            ontology=ontology,
            snippets=snippets,
        )
        location_graph = self.location_graph_builder.build(
            graph_summary=graph_summary,
            snippets=snippets,
        )
        payload = {
            "campaign_id": campaign_id,
            "title": title,
            "graph_id": campaign_id,
            "documents": documents,
            "document_count": len(documents),
            "text_length": len(combined_text),
            "combined_text": combined_text,
            "snippets": snippets,
            "ontology": ontology,
            "graph_summary": graph_summary,
            "location_graph": location_graph,
        }
        self._save_json(self._campaign_path(campaign_id), payload)
        return {
            "campaign_id": campaign_id,
            "title": title,
            "graph_id": campaign_id,
            "document_count": len(documents),
            "text_length": len(combined_text),
            "ontology": ontology,
            "graph_summary": graph_summary,
        }

    def start_session(
        self,
        *,
        campaign_id: str,
        session_id: str,
        player_name: str,
        current_scene: str,
    ) -> dict[str, Any]:
        campaign = self._load_json(self._campaign_path(campaign_id))
        session = {
            "session_id": session_id,
            "campaign_id": campaign["campaign_id"],
            "graph_id": campaign["graph_id"],
            "player_name": player_name,
            "current_scene": current_scene,
            "encounter_id": "",
            "encounter_state": {},
            "battle_log": [],
            "recent_memory": [],
            "active_profiles": self._load_profiles(campaign_id),
            "world_state": self._create_initial_world_state(
                campaign=campaign,
                campaign_id=campaign_id,
                session_id=session_id,
                current_scene=current_scene,
                player_name=player_name,
            ),
        }
        self._save_json(self._session_path(session_id), session)
        return {
            "session_id": session_id,
            "campaign_id": campaign_id,
            "graph_id": campaign["graph_id"],
            "player_name": player_name,
            "current_scene": current_scene,
            "world_state": session["world_state"],
        }

    def sync_battle(
        self,
        *,
        session_id: str,
        encounter_id: str,
        encounter_state: dict[str, Any],
        new_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        session = self._load_json(self._session_path(session_id))
        digests = [self._event_digest(event, encounter_state) for event in new_events]
        for digest in digests:
            session["battle_log"].append(digest)
        session["encounter_id"] = encounter_id
        session["encounter_state"] = encounter_state
        session["recent_memory"] = (session.get("recent_memory", []) + digests)[-12:]
        session["world_state"] = self.world_state_engine.apply_events(
            world_state=session.get("world_state") or self._default_world_state(),
            encounter_state=encounter_state,
            new_events=new_events,
        )
        session["current_scene"] = session["world_state"].get("scene", {}).get("name", session.get("current_scene", ""))
        graph_update_result = self._apply_runtime_graph_updates(
            campaign_id=session["campaign_id"],
            encounter_state=encounter_state,
            new_events=new_events,
        )
        self._save_json(self._session_path(session_id), session)
        return {
            "session_id": session_id,
            "encounter_id": encounter_id,
            "new_event_count": len(new_events),
            "battle_digest": "\n".join(digests[-3:]),
            "world_state": session["world_state"],
            "graph_update": graph_update_result,
        }

    def build_dm_reply(
        self,
        *,
        session_id: str,
        player_message: str,
    ) -> dict[str, Any]:
        session = self._load_json(self._session_path(session_id))
        campaign = self._load_json(self._campaign_path(session["campaign_id"]))
        query = " ".join(
            item for item in [player_message, session.get("current_scene", ""), " ".join(session.get("recent_memory", [])[-3:])] if item
        )
        setting_matches = self._rank_snippets(campaign.get("snippets", []), query)[:4]
        graph_matches = self._graph_matches(campaign_id=session["campaign_id"], query=query, limit=6)
        setting_context = "\n".join(f"- [{item['source']}] {item['text']}" for item in setting_matches)
        graph_context = "\n".join(self._format_graph_match(item) for item in graph_matches)
        battle_context = "\n".join(f"- {item}" for item in session.get("recent_memory", [])[-4:])
        world_state_context = self.world_state_engine.build_context(world_state=session.get("world_state") or {})
        profiles = session.get("active_profiles") or self._load_profiles(session["campaign_id"])
        adjacent_locations = self._adjacent_location_names(session.get("world_state") or {})
        profile_context = "\n".join(
            f"- {profile['name']}：{profile.get('summary', '')} | 性格：{profile.get('personality', '')} | 目标：{'、'.join(profile.get('goals', []))}"
            for profile in profiles[:6]
        )
        user_prompt = (
            f"当前场景: {session['current_scene']}\n"
            f"相邻地点: {'、'.join(adjacent_locations) if adjacent_locations else '（未知）'}\n"
            f"玩家消息: {player_message}\n"
            "请作为叙事 DM，结合设定、战斗结果和当前局势，输出下一段回复，并在需要时给出结构化剧情推进结果。"
        )
        output_schema = {
            "narration": "string",
            "npc_reactions": ["string"],
            "world_effects": ["string"],
            "memory_updates": ["string"],
            "suggested_followups": ["string"],
            "scene_transition": "boolean",
            "new_location": "string",
            "new_entities": [
                {
                    "entity_type": "character|location|item|event",
                    "name": "string",
                    "brief_description": "string",
                }
            ],
            "exit_characters": [
                {
                    "entity_id": "string",
                    "reason": "string",
                }
            ],
        }
        fallback_reply = {
            "narration": f"{session['player_name']}的行动立刻改变了场上的节奏，局势开始向新的方向倾斜。",
            "npc_reactions": ["附近 NPC 开始根据最新战况调整态度与行动。"],
            "world_effects": ["当前战斗结果会继续影响场景中的门、火势、视线或士气。"],
            "memory_updates": ["将最近一次战斗结果纳入持续叙事记忆。"],
            "suggested_followups": ["继续描述守军、敌人或环境如何响应玩家刚才的行动。"],
            "scene_transition": False,
            "new_location": "",
            "new_entities": [],
            "exit_characters": [],
        }
        return {
            "session_id": session_id,
            "campaign_id": session["campaign_id"],
            "setting_context": setting_context,
            "graph_context": graph_context,
            "battle_context": battle_context,
            "world_state_context": world_state_context,
            "profile_context": profile_context,
            "user_prompt": user_prompt,
            "output_schema": output_schema,
            "fallback_reply": fallback_reply,
        }

    def apply_player_action(
        self,
        *,
        session_id: str,
        player_message: str,
    ) -> dict[str, Any]:
        session = self._load_json(self._session_path(session_id))
        world_state = session.get("world_state") or self._default_world_state()
        if hasattr(self.world_state_engine, "apply_player_action"):
            result = self.world_state_engine.apply_player_action(
                world_state=world_state,
                player_message=player_message,
                actor_entity_id="player",
            )
            session["world_state"] = result.get("world_state", world_state)
            session["current_scene"] = session["world_state"].get("scene", {}).get("name", session.get("current_scene", ""))
            self._save_json(self._session_path(session_id), session)
            return {
                "session_id": session_id,
                "player_message": player_message,
                "detected_destination": result.get("detected_destination", ""),
                "world_state": session["world_state"],
                "current_scene": session["current_scene"],
            }

        return {
            "session_id": session_id,
            "player_message": player_message,
            "detected_destination": "",
            "world_state": world_state,
            "current_scene": session.get("current_scene", ""),
        }

    def apply_dm_outcome(
        self,
        *,
        session_id: str,
        dm_output: dict[str, Any],
    ) -> dict[str, Any]:
        session = self._load_json(self._session_path(session_id))
        world_state = session.get("world_state") or self._default_world_state()

        applied_location = ""
        if (
            dm_output.get("scene_transition")
            and dm_output.get("new_location")
            and hasattr(self.world_state_engine, "apply_scene_transition")
        ):
            result = self.world_state_engine.apply_scene_transition(
                world_state=world_state,
                new_location=dm_output["new_location"],
                actor_entity_id="player",
            )
            world_state = result.get("world_state", world_state)
            applied_location = result.get("applied_location", "")

        graph_update_result = self._apply_dm_entity_updates(
            session=session,
            world_state=world_state,
            dm_output=dm_output,
        )
        world_state = session["world_state"]

        memory_entries = []
        for key in ["world_effects", "memory_updates"]:
            values = dm_output.get(key, []) or []
            if isinstance(values, list):
                memory_entries.extend(str(item) for item in values if str(item).strip())
        if dm_output.get("narration"):
            memory_entries.append(str(dm_output["narration"]))

        session["world_state"] = world_state
        session["current_scene"] = world_state.get("scene", {}).get("name", session.get("current_scene", ""))
        session["recent_memory"] = (session.get("recent_memory", []) + memory_entries)[-12:]
        self._save_json(self._session_path(session_id), session)
        return {
            "session_id": session_id,
            "world_state": world_state,
            "current_scene": session["current_scene"],
            "applied_location": applied_location,
            "recent_memory": session["recent_memory"],
            "active_profiles": session.get("active_profiles", []),
            "graph_update": graph_update_result,
        }

    def _apply_dm_entity_updates(
        self,
        *,
        session: dict[str, Any],
        world_state: dict[str, Any],
        dm_output: dict[str, Any],
    ) -> dict[str, Any]:
        active_profiles = list(session.get("active_profiles") or [])
        profiles_by_id = {item.get("entity_id", ""): dict(item) for item in active_profiles if item.get("entity_id")}
        world_state.setdefault("entities", {})
        world_state.setdefault("map", {}).setdefault("locations", {})
        world_state.setdefault("inventory", {})

        graph_entities: list[dict[str, Any]] = []
        graph_relationships: list[dict[str, Any]] = []

        for entity in dm_output.get("new_entities", []) or []:
            if not isinstance(entity, dict) or not entity.get("name"):
                continue
            entity_type = entity.get("entity_type", "character")
            name = str(entity["name"])

            if entity_type == "character":
                entity_id = entity.get("entity_id") or self._character_id_for_name(name)
                location_name = entity.get("current_location") or session.get("current_scene", "")
                profiles_by_id[entity_id] = {
                    "entity_id": entity_id,
                    "entity_type": "character",
                    "name": name,
                    "summary": entity.get("brief_description", ""),
                    "personality": entity.get("personality", ""),
                    "goals": entity.get("goals", []),
                    "current_location": location_name,
                    "status": "active",
                }
                world_state["entities"][entity_id] = {
                    "name": name,
                    "location": location_name,
                }
                graph_entities.append(
                    {
                        "entity_id": entity_id,
                        "entity_type": "character",
                        "name": name,
                        "summary": entity.get("brief_description", f"运行时引入角色：{name}"),
                        "status": "active",
                        "current_location": location_name,
                    }
                )
                if location_name:
                    graph_relationships.append(
                        {
                            "source_id": entity_id,
                            "target_id": self._location_id(location_name),
                            "relationship_type": "located_in",
                            "properties": {"target_name": location_name, "status": "active"},
                        }
                    )

            elif entity_type == "location":
                location_id = self._location_id(name)
                adjacent_ids = []
                for adjacent_name in entity.get("adjacent", []) or []:
                    adjacent_id = self._resolve_location_id(world_state=world_state, name=str(adjacent_name))
                    if adjacent_id and adjacent_id != location_id:
                        adjacent_ids.append(adjacent_id)
                world_state["map"]["locations"].setdefault(
                    location_id,
                    {
                        "name": name,
                        "description": entity.get("brief_description", ""),
                        "adjacent": [],
                        "aliases": [],
                        "flags": [],
                        "nearby_flags": [],
                    },
                )
                for adjacent_id in adjacent_ids:
                    if adjacent_id not in world_state["map"]["locations"][location_id]["adjacent"]:
                        world_state["map"]["locations"][location_id]["adjacent"].append(adjacent_id)
                    world_state["map"]["locations"].setdefault(
                        adjacent_id,
                        {
                            "name": adjacent_id.split(":", 1)[1].replace("_", " ").title(),
                            "description": "",
                            "adjacent": [],
                            "aliases": [],
                            "flags": [],
                            "nearby_flags": [],
                        },
                    )
                    if location_id not in world_state["map"]["locations"][adjacent_id]["adjacent"]:
                        world_state["map"]["locations"][adjacent_id]["adjacent"].append(location_id)
                graph_entities.append(
                    {
                        "entity_id": location_id,
                        "entity_type": "location",
                        "name": name,
                        "summary": entity.get("brief_description", f"运行时发现地点：{name}"),
                    }
                )

            elif entity_type == "item":
                item_name = name
                owner_id = str(entity.get("owner") or "player")
                world_state["inventory"][item_name] = owner_id
                item_id = self._item_id(item_name)
                graph_entities.append(
                    {
                        "entity_id": item_id,
                        "entity_type": "item",
                        "name": item_name,
                        "summary": entity.get("brief_description", f"运行时出现的剧情道具：{item_name}"),
                    }
                )
                graph_relationships.append(
                    {
                        "source_id": item_id,
                        "target_id": owner_id,
                        "relationship_type": "belongs_to",
                        "properties": {"status": "active", "target_name": owner_id},
                    }
                )

        for exit_char in dm_output.get("exit_characters", []) or []:
            if not isinstance(exit_char, dict):
                continue
            entity_id = exit_char.get("entity_id") or ""
            if entity_id and entity_id in profiles_by_id:
                profiles_by_id.pop(entity_id, None)
            if entity_id and entity_id in world_state.get("entities", {}):
                world_state["entities"][entity_id]["status"] = "inactive"

        session["active_profiles"] = list(profiles_by_id.values())
        session["world_state"] = world_state

        if hasattr(self.graph_store, "apply_runtime_updates") and (graph_entities or graph_relationships):
            return self.graph_store.apply_runtime_updates(
                campaign_id=session["campaign_id"],
                updates={
                    "entities": graph_entities,
                    "relationships": graph_relationships,
                },
            )
        return {"graph_id": session["campaign_id"], "entity_writes": 0, "relationship_writes": 0}

    def _resolve_location_id(self, *, world_state: dict[str, Any], name: str) -> str:
        locations = world_state.get("map", {}).get("locations", {})
        if hasattr(self.world_state_engine, "_location_id_from_name"):
            resolved = self.world_state_engine._location_id_from_name(name, locations)
            if resolved:
                return resolved
        return self._location_id(name)

    def _adjacent_location_names(self, world_state: dict[str, Any]) -> list[str]:
        locations = world_state.get("map", {}).get("locations", {})
        scene_name = world_state.get("scene", {}).get("name", "")
        current_location_id = self._resolve_location_id(world_state=world_state, name=scene_name)
        if not current_location_id:
            return []
        adjacent = locations.get(current_location_id, {}).get("adjacent", [])
        names = []
        for location_id in adjacent:
            name = locations.get(location_id, {}).get("name", "")
            if name:
                names.append(name)
        return names

    def build_profiles(self, *, campaign_id: str) -> dict[str, Any]:
        campaign = self._load_json(self._campaign_path(campaign_id))
        graph_summary = campaign.get("graph_summary", {})
        if hasattr(self.graph_store, "get_graph_summary"):
            graph_summary = self.graph_store.get_graph_summary(campaign_id=campaign_id)
            campaign["graph_summary"] = graph_summary
            self._save_json(self._campaign_path(campaign_id), campaign)
        profiles = self.profile_generator.generate_profiles(
            campaign_id=campaign_id,
            entities=graph_summary.get("entities", []),
            graph_facts=graph_summary.get("facts", []),
        )
        payload = {
            "campaign_id": campaign_id,
            "graph_id": campaign.get("graph_id", campaign_id),
            "profiles": profiles,
        }
        self._save_json(self._profile_path(campaign_id), payload)
        return {
            "campaign_id": campaign_id,
            "graph_id": campaign.get("graph_id", campaign_id),
            "profile_count": len(profiles),
        }

    def query_facts(self, *, campaign_id: str, query: str) -> dict[str, Any]:
        campaign = self._load_json(self._campaign_path(campaign_id))
        snippet_matches = self._rank_snippets(campaign.get("snippets", []), query)[:8]
        graph_matches = self._graph_matches(campaign_id=campaign_id, query=query, limit=8)
        matches = graph_matches + snippet_matches
        return {
            "campaign_id": campaign_id,
            "query": query,
            "graph_matches": graph_matches,
            "snippet_matches": snippet_matches,
            "matches": matches,
        }

    def _event_digest(self, event: dict[str, Any], encounter_state: dict[str, Any]) -> str:
        actor = self._entity_name(encounter_state, event.get("actor_entity_id"))
        target = self._entity_name(encounter_state, event.get("target_entity_id"))
        payload = event.get("payload", {})
        event_type = event.get("event_type", "event")
        reason = payload.get("reason") or payload.get("spell_name") or payload.get("action") or ""
        damage_total = payload.get("damage_total")
        damage_type = payload.get("damage_type")

        if damage_total is not None and damage_type:
            return f"{actor} 对 {target} 结算了 {event_type}：{reason}，造成 {damage_total} 点{damage_type}伤害。".strip()
        if reason:
            return f"{actor} 对 {target} 结算了 {event_type}：{reason}。".strip()
        return f"{actor} 对 {target} 结算了 {event_type}。".strip()

    def _entity_name(self, encounter_state: dict[str, Any], entity_id: str | None) -> str:
        if not entity_id:
            return "未知目标"
        entities = encounter_state.get("entities", {})
        entity = entities.get(entity_id, {})
        return entity.get("name", entity_id)

    def _rank_snippets(self, snippets: list[dict[str, str]], query: str) -> list[dict[str, str]]:
        terms = [term for term in re.split(r"\W+", query.lower()) if term]
        scored: list[tuple[int, dict[str, str]]] = []
        for snippet in snippets:
            haystack = snippet.get("text", "").lower()
            score = sum(haystack.count(term) for term in terms)
            if score > 0:
                scored.append((score, snippet))
        if not scored:
            return snippets[:5]
        scored.sort(key=lambda item: (-item[0], len(item[1].get("text", ""))))
        return [item[1] for item in scored]

    def _graph_matches(self, *, campaign_id: str, query: str, limit: int) -> list[dict[str, Any]]:
        if not hasattr(self.graph_store, "query_facts"):
            return []
        return list(self.graph_store.query_facts(campaign_id=campaign_id, query=query, limit=limit) or [])

    def _default_world_state(self) -> dict[str, Any]:
        return self.world_state_engine.create_initial_state(
            campaign_id="",
            session_id="",
            current_scene="",
            player_name="",
        )

    def _apply_runtime_graph_updates(
        self,
        *,
        campaign_id: str,
        encounter_state: dict[str, Any],
        new_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not hasattr(self.graph_store, "apply_runtime_updates"):
            return {"graph_id": campaign_id, "entity_writes": 0, "relationship_writes": 0}

        updates = self._derive_runtime_graph_updates(encounter_state=encounter_state, new_events=new_events)
        return self.graph_store.apply_runtime_updates(campaign_id=campaign_id, updates=updates)

    def _derive_runtime_graph_updates(
        self,
        *,
        encounter_state: dict[str, Any],
        new_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        entities_by_id: dict[str, dict[str, Any]] = {}
        relationships_by_key: dict[str, dict[str, Any]] = {}

        for event in new_events:
            payload = event.get("payload", {}) or {}
            actor_id = event.get("actor_entity_id")
            target_id = event.get("target_entity_id")
            event_type = event.get("event_type", "")

            for entity_id in [actor_id, target_id]:
                if entity_id:
                    self._add_runtime_character(
                        entities_by_id,
                        encounter_state=encounter_state,
                        entity_id=entity_id,
                    )

            if event_type == "movement_resolved" and actor_id and payload.get("destination"):
                location_id = self._location_id(payload["destination"])
                entities_by_id[location_id] = {
                    "entity_id": location_id,
                    "entity_type": "location",
                    "name": payload["destination"],
                    "summary": f"运行时地点：{payload['destination']}",
                }
                relationships_by_key[f"{actor_id}|located_in|{location_id}"] = {
                    "source_id": actor_id,
                    "target_id": location_id,
                    "relationship_type": "located_in",
                    "properties": {"target_name": payload["destination"], "status": "active"},
                }

            if event_type == "companion_joined" and target_id:
                companion_name = payload.get("companion_name") or self._entity_name(encounter_state, actor_id)
                companion_id = actor_id or self._character_id_for_name(companion_name)
                entities_by_id[companion_id] = {
                    "entity_id": companion_id,
                    "entity_type": "character",
                    "name": companion_name,
                    "summary": f"运行时加入的同伴：{companion_name}",
                    "status": "active",
                }
                relationships_by_key[f"{target_id}|travels_with|{companion_id}"] = {
                    "source_id": target_id,
                    "target_id": companion_id,
                    "relationship_type": "travels_with",
                    "properties": {"target_name": companion_name, "status": "active"},
                }

            if event_type == "attack_resolved" and actor_id and target_id:
                relationships_by_key[f"{actor_id}|hostile_to|{target_id}"] = {
                    "source_id": actor_id,
                    "target_id": target_id,
                    "relationship_type": "hostile_to",
                    "properties": {"status": "active", "reason": payload.get("reason", "")},
                }

            if event_type == "item_transferred":
                item_name = payload.get("item_name")
                owner_id = target_id or actor_id
                if item_name and owner_id:
                    item_id = self._item_id(item_name)
                    entities_by_id[item_id] = {
                        "entity_id": item_id,
                        "entity_type": "item",
                        "name": item_name,
                        "summary": f"运行时出现的剧情道具：{item_name}",
                    }
                    relationships_by_key[f"{item_id}|belongs_to|{owner_id}"] = {
                        "source_id": item_id,
                        "target_id": owner_id,
                        "relationship_type": "belongs_to",
                        "properties": {"status": "active", "target_name": self._entity_name(encounter_state, owner_id)},
                    }

        return {
            "entities": list(entities_by_id.values()),
            "relationships": list(relationships_by_key.values()),
        }

    def _add_runtime_character(
        self,
        entities_by_id: dict[str, dict[str, Any]],
        *,
        encounter_state: dict[str, Any],
        entity_id: str,
    ) -> None:
        entity = (encounter_state.get("entities") or {}).get(entity_id, {})
        name = entity.get("name", entity_id)
        summary = f"运行时战斗实体：{name}"
        if entity.get("location"):
            summary += f"，位于 {entity['location']}"
        entities_by_id[entity_id] = {
            "entity_id": entity_id,
            "entity_type": "character",
            "name": name,
            "summary": summary,
            "status": "active",
            "current_location": entity.get("location", ""),
        }

    def _location_id(self, name: str) -> str:
        return f"location:{self._slug(name)}"

    def _item_id(self, name: str) -> str:
        return f"item:{self._slug(name)}"

    def _character_id_for_name(self, name: str) -> str:
        return f"character:{self._slug(name)}"

    def _slug(self, value: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", value.lower())
        normalized = normalized.strip("_")
        return normalized or "unknown"

    def _format_graph_match(self, item: dict[str, Any]) -> str:
        if "relationship_type" in item:
            source_id = item.get("source_id", "")
            relationship_type = item.get("relationship_type", "")
            target_id = item.get("target_id", "")
            properties = item.get("properties", {})
            if properties:
                return f"- {source_id} --{relationship_type}--> {target_id} | {json.dumps(properties, ensure_ascii=False)}"
            return f"- {source_id} --{relationship_type}--> {target_id}"

        entity_id = item.get("entity_id", "")
        entity_type = item.get("entity_type", "")
        name = item.get("name", entity_id)
        summary = item.get("summary", "")
        return f"- [{entity_type}] {name} ({entity_id})：{summary}".rstrip("：")

    def _campaign_path(self, campaign_id: str) -> Path:
        return self.campaigns_dir / f"{campaign_id}.json"

    def _session_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"{session_id}.json"

    def _profile_path(self, campaign_id: str) -> Path:
        return self.profiles_dir / f"{campaign_id}.json"

    def _load_profiles(self, campaign_id: str) -> list[dict[str, Any]]:
        path = self._profile_path(campaign_id)
        if not path.exists():
            return []
        payload = self._load_json(path)
        return payload.get("profiles", [])

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _create_initial_world_state(
        self,
        *,
        campaign: dict[str, Any],
        campaign_id: str,
        session_id: str,
        current_scene: str,
        player_name: str,
    ) -> dict[str, Any]:
        location_graph = self._session_location_graph(campaign=campaign, current_scene=current_scene)
        try:
            return self.world_state_engine.create_initial_state(
                campaign_id=campaign_id,
                session_id=session_id,
                current_scene=current_scene,
                player_name=player_name,
                location_graph=location_graph,
            )
        except TypeError:
            return self.world_state_engine.create_initial_state(
                campaign_id=campaign_id,
                session_id=session_id,
                current_scene=current_scene,
                player_name=player_name,
            )

    def _session_location_graph(self, *, campaign: dict[str, Any], current_scene: str) -> dict[str, dict[str, Any]]:
        existing = campaign.get("location_graph")
        if isinstance(existing, dict) and existing:
            locations = dict(existing)
        else:
            locations = self.location_graph_builder.build(
                graph_summary=campaign.get("graph_summary", {}),
                snippets=campaign.get("snippets", []),
                current_scene=current_scene,
            )
            campaign["location_graph"] = locations
            self._save_json(self._campaign_path(campaign["campaign_id"]), campaign)

        if current_scene:
            current_id = self.location_graph_builder._location_id(current_scene)
            locations.setdefault(
                current_id,
                {
                    "name": current_scene,
                    "description": "当前场景",
                    "adjacent": [],
                },
            )
        return locations
