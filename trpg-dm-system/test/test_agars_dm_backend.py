from __future__ import annotations

import json
import subprocess
import sys


class FakeOntologyGenerator:
    def generate(self, *, title: str, combined_text: str, snippets: list[dict[str, str]]) -> dict:
        assert title
        assert combined_text
        assert snippets
        return {
            "analysis_summary": "识别出角色、地点、阵营、线索与目标。",
            "entity_types": [
                {"name": "character", "description": "角色实体"},
                {"name": "location", "description": "地点实体"},
                {"name": "faction", "description": "阵营实体"},
            ],
            "edge_types": [
                {"name": "located_in", "description": "位于"},
                {"name": "hostile_to", "description": "敌对"},
            ],
        }


class FakeGraphStore:
    def __init__(self):
        self.runtime_updates: list[dict] = []

    def ingest_campaign_graph(self, *, campaign_id: str, ontology: dict, snippets: list[dict[str, str]]) -> dict:
        assert campaign_id
        assert ontology["entity_types"]
        assert snippets
        return {
            "graph_id": campaign_id,
            "node_count": 5,
            "edge_count": 4,
            "entities": [
                {
                    "entity_id": "char_ilvara",
                    "entity_type": "character",
                    "name": "Ilvara",
                    "summary": "卓尔前哨站指挥官。",
                    "current_location": "Velkynvelve",
                    "faction": "House Mizzrym",
                    "status": "active",
                },
                {
                    "entity_id": "loc_pen",
                    "entity_type": "location",
                    "name": "Slave Pen",
                    "summary": "囚徒被关押的牢笼。",
                },
            ],
            "facts": [
                "Ilvara guards the prisoners in Velkynvelve.",
                "The slave pen is suspended above the cavern.",
            ],
        }

    def query_facts(self, *, campaign_id: str, query: str, limit: int = 10) -> list[dict]:
        assert campaign_id
        assert query is not None
        return [
            {
                "entity_id": "char_ilvara",
                "entity_type": "character",
                "name": "Ilvara",
                "summary": "卓尔前哨站指挥官。",
            },
            {
                "source_id": "char_ilvara",
                "relationship_type": "guards",
                "target_id": "loc_pen",
                "properties": {"status": "active"},
            },
        ][:limit]

    def apply_runtime_updates(self, *, campaign_id: str, updates: dict) -> dict:
        assert campaign_id
        self.runtime_updates.append({"campaign_id": campaign_id, **updates})
        return {
            "graph_id": campaign_id,
            "entity_writes": len(updates.get("entities", [])),
            "relationship_writes": len(updates.get("relationships", [])),
        }


class FakeProfileGenerator:
    def generate_profiles(self, *, campaign_id: str, entities: list[dict], graph_facts: list[str]) -> list[dict]:
        assert campaign_id
        assert entities
        assert graph_facts
        return [
            {
                "entity_id": "char_ilvara",
                "entity_type": "character",
                "name": "Ilvara",
                "summary": "卓尔前哨站指挥官，擅长威压囚徒。",
                "personality": "残忍、控制欲强",
                "goals": ["维持前哨站秩序", "把囚徒送往魔索布莱城"],
                "current_location": "Velkynvelve",
                "faction": "House Mizzrym",
                "status": "active",
            }
        ]


class FakeFalkorGraphBackend:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.relationships: dict[str, dict] = {}

    def upsert_node(self, *, graph_id: str, entity_id: str, entity_type: str, properties: dict) -> None:
        self.nodes[entity_id] = {
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
        properties: dict,
    ) -> None:
        key = f"{source_id}|{relationship_type}|{target_id}"
        self.relationships[key] = {
            "graph_id": graph_id,
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
            "properties": dict(properties),
        }

    def query_entities(self, *, graph_id: str, query: str | None = None, entity_type: str | None = None, limit: int = 20) -> list[dict]:
        results = []
        lowered = query.lower() if query else None
        for record in self.nodes.values():
            if record["graph_id"] != graph_id:
                continue
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
    ) -> list[dict]:
        results = []
        for record in self.relationships.values():
            if record["graph_id"] != graph_id:
                continue
            if record["source_id"] != entity_id and record["target_id"] != entity_id:
                continue
            if relationship_types and record["relationship_type"] not in relationship_types:
                continue
            results.append(dict(record))
        return results


class FakeCampaignGraphExtractor:
    def extract(self, *, campaign_id: str, ontology: dict, snippets: list[dict[str, str]]) -> dict:
        assert campaign_id
        assert ontology["entity_types"]
        assert snippets
        return {
            "entities": [
                {
                    "entity_id": "character:ilvara",
                    "entity_type": "character",
                    "name": "Ilvara",
                    "summary": "卓尔前哨站指挥官。",
                    "kind": "npc",
                    "status": "active",
                    "canonical_names": ["Ilvara", "伊尔瓦拉"],
                    "provenance": [
                        {
                            "source_file": snippets[0]["source"],
                            "snippet_id": "snippet_001",
                            "excerpt": snippets[0]["text"][:80],
                        }
                    ],
                },
                {
                    "entity_id": "location:velkynvelve",
                    "entity_type": "location",
                    "name": "Velkynvelve",
                    "summary": "卓尔前哨站。",
                    "kind": "outpost",
                    "canonical_names": ["Velkynvelve", "瓦肯维吾"],
                    "provenance": [
                        {
                            "source_file": snippets[0]["source"],
                            "snippet_id": "snippet_002",
                            "excerpt": snippets[0]["text"][:80],
                        }
                    ],
                },
            ],
            "relationships": [
                {
                    "source_id": "character:ilvara",
                    "target_id": "location:velkynvelve",
                    "relationship_type": "located_in",
                    "properties": {
                        "confidence": "confirmed",
                        "status": "active",
                    },
                    "provenance": [
                        {
                            "source_file": snippets[0]["source"],
                            "snippet_id": "snippet_003",
                            "excerpt": snippets[0]["text"][:80],
                        }
                    ],
                }
            ],
        }


class FakeWorldStateEngine:
    def create_initial_state(self, *, campaign_id: str, session_id: str, current_scene: str, player_name: str) -> dict:
        return {
            "engine_name": "fake",
            "campaign_id": campaign_id,
            "session_id": session_id,
            "current_scene": current_scene,
            "player_name": player_name,
            "time_index": 0,
            "scene_flags": [],
            "entity_locations": {},
            "companions": [],
            "inventory": {},
        }

    def apply_events(self, *, world_state: dict, encounter_state: dict, new_events: list[dict[str, str]]) -> dict:
        next_state = dict(world_state)
        next_state["time_index"] = world_state.get("time_index", 0) + len(new_events)
        next_state["entity_locations"] = {
            "ent_pc_001": encounter_state.get("entities", {}).get("ent_pc_001", {}).get("location", "")
        }
        next_state["companions"] = ["Governor Nighthill"]
        return next_state

    def build_context(self, *, world_state: dict) -> str:
        return f"scene={world_state.get('current_scene')} time={world_state.get('time_index')}"


class FakeLocationGraphInferer:
    def __init__(self):
        self.location_list_attempts = 0

    def extract_locations(self, *, chunk_text: str) -> list[str]:
        found = []
        for name in ["Slave Pen", "Guard Post", "Lift", "Upper Ledge"]:
            if name in chunk_text and name not in found:
                found.append(name)
        return found

    def infer_from_location_list(
        self,
        *,
        current_scene: str,
        location_names: list[str],
        location_facts: list[str],
    ) -> dict[str, dict]:
        self.location_list_attempts += 1
        if len(location_names) > 3 and self.location_list_attempts == 1:
            return {
                "locations": {
                    "Slave Pen": {
                        "description": "疑似截断结果。",
                        "adjacent": ["Guard Post"],
                    }
                }
            }
        return {
            "locations": {
                "Slave Pen": {
                    "description": "囚徒区域。",
                    "adjacent": ["Guard Post"],
                },
                "Guard Post": {
                    "description": "守卫哨所。",
                    "adjacent": ["Slave Pen", "Lift"],
                },
                "Lift": {
                    "description": "升降机。",
                    "adjacent": ["Guard Post", "Upper Ledge"],
                },
                "Upper Ledge": {
                    "description": "高处平台。",
                    "adjacent": ["Lift"],
                },
            }
        }

    def infer_from_scene(self, *, current_scene: str, source_text: str) -> dict[str, dict]:
        return {
            "locations": {
                "Camp Entrance": {
                    "description": "入口。",
                    "adjacent": ["Main Tunnel"],
                },
                "Main Tunnel": {
                    "description": "主通道。",
                    "adjacent": ["Camp Entrance"],
                },
            }
        }


def test_split_snippets_prefers_heading_aware_sections():
    from agars_dm_backend.file_parser import split_snippets

    text = (
        "# Chapter 1\n"
        "Opening scene line 1.\n\n"
        "Opening scene line 2.\n\n"
        "## Prisoners\n"
        "Ilvara watches the slave pen.\n\n"
        "Ront growls at the drow guards.\n"
    )

    snippets = split_snippets(text)

    assert len(snippets) == 2
    assert snippets[0].startswith("# Chapter 1")
    assert "Opening scene line 2." in snippets[0]
    assert snippets[1].startswith("## Prisoners")
    assert "Ront growls" in snippets[1]


def test_world_state_engine_manages_state_in_engine_layer():
    from agars_dm_backend.world_state_engine import NarrativeWorldStateEngine

    engine = NarrativeWorldStateEngine()
    world_state = engine.create_initial_state(
        campaign_id="camp_world",
        session_id="sess_world",
        current_scene="Slave Pen",
        player_name="米伦",
        location_graph={
            "location:slave_pen": {
                "name": "Slave Pen",
                "adjacent": ["location:guard_post"],
            },
            "location:guard_post": {
                "name": "Guard Post",
                "adjacent": ["location:slave_pen", "location:watch_post"],
            },
            "location:watch_post": {
                "name": "Watch Post",
                "adjacent": ["location:guard_post"],
            },
        },
    )
    next_state = engine.apply_events(
        world_state=world_state,
        encounter_state={"entities": {"ent_pc_miren": {"location": "Slave Pen"}}},
        new_events=[
            {
                "event_type": "movement_resolved",
                "actor_entity_id": "ent_pc_miren",
                "payload": {"destination": "Watch Post"},
            },
            {
                "event_type": "scene_flag_set",
                "payload": {"flag": "alarm_raised"},
            },
        ],
    )
    context = engine.build_context(world_state=next_state)

    assert world_state["scene"]["name"] == "Slave Pen"
    assert next_state["clock"]["time_index"] == 2
    assert next_state["scene"]["flags"] == ["alarm_raised"]
    assert next_state["entities"]["ent_pc_miren"]["location"] == "Guard Post"
    assert next_state["movement"]["last_check"]["valid_move"] is False
    assert next_state["movement"]["last_check"]["applied_destination"] == "location:guard_post"
    assert next_state["movement"]["last_check"]["required_path"] == [
        "location:slave_pen",
        "location:guard_post",
        "location:watch_post",
    ]
    assert "Slave Pen" in context
    assert "alarm_raised" in context
    assert "移动校验：不合法" in context
    assert "Guard Post" in context


def test_start_session_auto_builds_location_graph_from_campaign(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Velkynvelve\n"
        "The Slave Pen connects to Guard Post.\n\n"
        "## Guard Post\n"
        "Guard Post connects to Lift.\n\n"
        "## Lift\n"
        "Lift connects to Upper Ledge.\n",
        encoding="utf-8",
    )

    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
    )
    service.ingest_setting(
        campaign_id="camp_map",
        title="Out of the Abyss",
        file_paths=[setting_file],
    )

    session = service.start_session(
        campaign_id="camp_map",
        session_id="sess_map_001",
        player_name="米伦",
        current_scene="Slave Pen",
    )

    locations = session["world_state"]["map"]["locations"]
    assert "location:slave_pen" in locations
    assert "location:guard_post" in locations
    assert "location:lift" in locations
    assert "location:guard_post" in locations["location:slave_pen"]["adjacent"]
    assert "location:slave_pen" in locations["location:guard_post"]["adjacent"]


def test_location_graph_builder_can_use_llm_inference_when_rules_are_sparse():
    from agars_dm_backend.location_graph_builder import LocationGraphBuilder

    builder = LocationGraphBuilder(map_inferer=FakeLocationGraphInferer())
    location_graph = builder.build(
        graph_summary={
            "entities": [
                {"entity_type": "location", "name": "Slave Pen", "summary": "囚徒区域。"},
                {"entity_type": "location", "name": "Guard Post", "summary": "守卫哨所。"},
                {"entity_type": "location", "name": "Lift", "summary": "升降机。"},
            ]
        },
        snippets=[
            {
                "source": "chapter_01.md",
                "text": "The prisoners hang in the slave pen while guards patrol nearby.",
            }
        ],
        current_scene="Slave Pen",
    )

    assert location_graph["location:slave_pen"]["adjacent"] == ["location:guard_post"]
    assert "location:lift" in location_graph["location:guard_post"]["adjacent"]


def test_location_graph_builder_extracts_locations_from_large_text():
    from agars_dm_backend.location_graph_builder import LocationGraphBuilder

    builder = LocationGraphBuilder(map_inferer=FakeLocationGraphInferer())
    names = builder.extract_locations_from_text(
        (
            "Slave Pen is watched by drow guards. " * 200
            + "Guard Post stands above the cavern. " * 200
            + "Lift reaches the Upper Ledge. " * 200
        )
    )

    assert names == ["Guard Post", "Lift", "Slave Pen", "Upper Ledge"]


def test_location_graph_builder_retries_after_truncated_map_output():
    from agars_dm_backend.location_graph_builder import LocationGraphBuilder

    inferer = FakeLocationGraphInferer()
    builder = LocationGraphBuilder(map_inferer=inferer)
    location_graph = builder.build(
        graph_summary={"entities": []},
        snippets=[
            {"source": "chapter_01.md", "text": "Slave Pen Guard Post Lift Upper Ledge"}
        ],
        current_scene="Slave Pen",
        source_text="Slave Pen Guard Post Lift Upper Ledge",
    )

    assert inferer.location_list_attempts == 2
    assert "location:upper_ledge" in location_graph
    assert "location:lift" in location_graph["location:guard_post"]["adjacent"]


def test_location_graph_builder_falls_back_to_scene_map_when_no_locations():
    from agars_dm_backend.location_graph_builder import LocationGraphBuilder

    builder = LocationGraphBuilder(map_inferer=FakeLocationGraphInferer())
    location_graph = builder.build(
        graph_summary={"entities": []},
        snippets=[],
        current_scene="Camp Entrance",
        source_text="A narrow tunnel leads into the camp.",
    )

    assert "location:camp_entrance" in location_graph
    assert "location:main_tunnel" in location_graph


def test_location_graph_builder_merges_stronger_normalized_location_names():
    from agars_dm_backend.location_graph_builder import LocationGraphBuilder

    class DuplicateNameInferer:
        def extract_locations(self, *, chunk_text: str) -> list[str]:
            return ["The Slave Pen", "slave-pen", "Guard Post", "guard post"]

        def infer_from_location_list(
            self,
            *,
            current_scene: str,
            location_names: list[str],
            location_facts: list[str],
        ) -> dict[str, dict]:
            return {
                "locations": {
                    "The Slave Pen": {
                        "description": "囚徒区域。",
                        "adjacent": ["Guard Post"],
                    },
                    "slave-pen": {
                        "description": "重复写法。",
                        "adjacent": ["guard post"],
                    },
                    "Guard Post": {
                        "description": "守卫哨所。",
                        "adjacent": ["The Slave Pen"],
                    },
                    "guard post": {
                        "description": "重复写法。",
                        "adjacent": ["slave-pen"],
                    },
                }
            }

        def infer_from_scene(self, *, current_scene: str, source_text: str) -> dict[str, dict]:
            return {}

    builder = LocationGraphBuilder(map_inferer=DuplicateNameInferer())
    location_graph = builder.build(
        graph_summary={"entities": []},
        snippets=[{"source": "chapter_01.md", "text": "The Slave Pen connects to guard post."}],
        current_scene="slave pen",
        source_text="The Slave Pen connects to guard post.",
    )

    assert sorted(location_graph.keys()) == ["location:guard_post", "location:slave_pen"]
    assert location_graph["location:slave_pen"]["name"] == "Slave Pen"
    assert location_graph["location:slave_pen"]["aliases"][0] == "The Slave Pen"
    assert "slave pen" in location_graph["location:slave_pen"]["aliases"]
    assert "slave-pen" in location_graph["location:slave_pen"]["aliases"]
    assert location_graph["location:slave_pen"]["adjacent"] == ["location:guard_post"]
    assert location_graph["location:guard_post"]["aliases"][0] == "Guard Post"
    assert "guard post" in location_graph["location:guard_post"]["aliases"]
    assert location_graph["location:guard_post"]["adjacent"] == ["location:slave_pen"]


def test_world_state_engine_propagates_scene_flags_to_neighboring_locations():
    from agars_dm_backend.world_state_engine import NarrativeWorldStateEngine

    engine = NarrativeWorldStateEngine()
    world_state = engine.create_initial_state(
        campaign_id="camp_world",
        session_id="sess_world",
        current_scene="Slave Pen",
        player_name="米伦",
        location_graph={
            "location:slave_pen": {
                "name": "Slave Pen",
                "adjacent": ["location:guard_post"],
            },
            "location:guard_post": {
                "name": "Guard Post",
                "adjacent": ["location:slave_pen", "location:watch_post"],
            },
            "location:watch_post": {
                "name": "Watch Post",
                "adjacent": ["location:guard_post"],
            },
        },
    )

    next_state = engine.apply_events(
        world_state=world_state,
        encounter_state={"entities": {"ent_pc_miren": {"location": "Slave Pen"}}},
        new_events=[
            {
                "event_type": "scene_flag_set",
                "payload": {"flag": "alarm_raised"},
            },
        ],
    )
    context = engine.build_context(world_state=next_state)

    assert next_state["scene"]["flags"] == ["alarm_raised"]
    assert next_state["map"]["locations"]["location:slave_pen"]["flags"] == ["alarm_raised"]
    assert next_state["map"]["locations"]["location:guard_post"]["nearby_flags"] == ["alarm_raised"]
    assert next_state["map"]["locations"]["location:watch_post"].get("nearby_flags", []) == []
    assert "场景标记：alarm_raised" in context
    assert "邻区态势：alarm_raised" in context


def test_service_applies_player_message_movement_with_alias_resolution(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Velkynvelve\n"
        "The Slave Pen connects to Guard Post.\n\n"
        "## Guard Post\n"
        "Guard Post connects to Lift.\n",
        encoding="utf-8",
    )

    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
    )
    service.ingest_setting(
        campaign_id="camp_move_alias",
        title="Out of the Abyss",
        file_paths=[setting_file],
    )
    service.start_session(
        campaign_id="camp_move_alias",
        session_id="sess_move_alias",
        player_name="米伦",
        current_scene="The Slave Pen",
    )

    result = service.apply_player_action(
        session_id="sess_move_alias",
        player_message="我想去 guard post 看看。",
    )

    assert result["detected_destination"] == "location:guard_post"
    assert result["world_state"]["scene"]["name"] == "Guard Post"
    assert result["world_state"]["movement"]["last_check"]["valid_move"] is True
    assert result["world_state"]["movement"]["last_check"]["applied_destination"] == "location:guard_post"

    reply_bundle = service.build_dm_reply(
        session_id="sess_move_alias",
        player_message="我想去 guard post 看看。",
    )
    assert "当前场景: Guard Post" in reply_bundle["user_prompt"]
    assert "场景：Guard Post" in reply_bundle["world_state_context"]


def test_service_player_message_uses_bfs_first_step_for_distant_destination(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Velkynvelve\n"
        "Slave Pen connects to Guard Post.\n\n"
        "## Guard Post\n"
        "Guard Post connects to Lift.\n\n"
        "## Lift\n"
        "Lift connects to Upper Ledge.\n",
        encoding="utf-8",
    )

    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
    )
    service.ingest_setting(
        campaign_id="camp_move_path",
        title="Out of the Abyss",
        file_paths=[setting_file],
    )
    service.start_session(
        campaign_id="camp_move_path",
        session_id="sess_move_path",
        player_name="米伦",
        current_scene="Slave Pen",
    )

    result = service.apply_player_action(
        session_id="sess_move_path",
        player_message="我想直接前往 upper ledge。",
    )

    assert result["detected_destination"] == "location:upper_ledge"
    assert result["world_state"]["scene"]["name"] == "Guard Post"
    assert result["world_state"]["movement"]["last_check"]["valid_move"] is False
    assert result["world_state"]["movement"]["last_check"]["applied_destination"] == "location:guard_post"
    assert result["world_state"]["movement"]["last_check"]["required_path"] == [
        "location:slave_pen",
        "location:guard_post",
        "location:lift",
        "location:upper_ledge",
    ]


def test_sync_battle_updates_session_current_scene_from_movement(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Velkynvelve\n"
        "Slave Pen connects to Guard Post.\n\n"
        "## Guard Post\n"
        "Guard Post connects to Lift.\n",
        encoding="utf-8",
    )

    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
    )
    service.ingest_setting(
        campaign_id="camp_sync_scene",
        title="Out of the Abyss",
        file_paths=[setting_file],
    )
    service.start_session(
        campaign_id="camp_sync_scene",
        session_id="sess_sync_scene",
        player_name="米伦",
        current_scene="Slave Pen",
    )

    result = service.sync_battle(
        session_id="sess_sync_scene",
        encounter_id="enc_001",
        encounter_state={
            "entities": {
                "player": {"name": "米伦", "location": "Slave Pen"},
            }
        },
        new_events=[
            {
                "event_type": "movement_resolved",
                "actor_entity_id": "player",
                "payload": {"destination": "Guard Post"},
            }
        ],
    )

    assert result["world_state"]["entities"]["player"]["location"] == "Guard Post"

    reply_bundle = service.build_dm_reply(
        session_id="sess_sync_scene",
        player_message="我观察守卫哨所。",
    )
    assert "当前场景: Guard Post" in reply_bundle["user_prompt"]
    assert "场景：Guard Post" in reply_bundle["world_state_context"]


def test_service_applies_dm_outcome_scene_transition(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Velkynvelve\n"
        "Slave Pen connects to Guard Post.\n\n"
        "## Guard Post\n"
        "Guard Post connects to Lift.\n",
        encoding="utf-8",
    )

    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
    )
    service.ingest_setting(
        campaign_id="camp_dm_outcome",
        title="Out of the Abyss",
        file_paths=[setting_file],
    )
    service.start_session(
        campaign_id="camp_dm_outcome",
        session_id="sess_dm_outcome",
        player_name="米伦",
        current_scene="Slave Pen",
    )

    result = service.apply_dm_outcome(
        session_id="sess_dm_outcome",
        dm_output={
            "narration": "你们冲出囚笼，扑向守卫哨所。",
            "scene_transition": True,
            "new_location": "guard post",
            "world_effects": ["你们已经脱离囚笼。"],
            "memory_updates": ["场景推进到守卫哨所。"],
        },
    )

    assert result["world_state"]["scene"]["name"] == "Guard Post"
    assert result["applied_location"] == "location:guard_post"

    reply_bundle = service.build_dm_reply(
        session_id="sess_dm_outcome",
        player_message="我看看周围。",
    )
    assert "当前场景: Guard Post" in reply_bundle["user_prompt"]
    assert "场景：Guard Post" in reply_bundle["world_state_context"]


def test_service_applies_dm_outcome_new_entities_and_exit_characters(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Velkynvelve\n"
        "Ilvara commands the outpost.\n"
        "Slave Pen connects to Guard Post.\n\n"
        "## Guard Post\n"
        "Guard Post connects to Lift.\n",
        encoding="utf-8",
    )

    graph_store = FakeGraphStore()
    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=graph_store,
        profile_generator=FakeProfileGenerator(),
    )
    service.ingest_setting(
        campaign_id="camp_dm_entities",
        title="Out of the Abyss",
        file_paths=[setting_file],
    )
    service.build_profiles(campaign_id="camp_dm_entities")
    service.start_session(
        campaign_id="camp_dm_entities",
        session_id="sess_dm_entities",
        player_name="米伦",
        current_scene="Guard Post",
    )

    result = service.apply_dm_outcome(
        session_id="sess_dm_entities",
        dm_output={
            "narration": "一名新的囚徒跌入视野，旧的卓尔指挥官撤离了现场。",
            "new_entities": [
                {
                    "entity_type": "character",
                    "name": "Sarith",
                    "brief_description": "一名神色不安的卓尔囚徒。",
                    "current_location": "Guard Post",
                },
                {
                    "entity_type": "location",
                    "name": "Watch Post",
                    "brief_description": "高处警戒台。",
                    "adjacent": ["Guard Post"],
                },
                {
                    "entity_type": "item",
                    "name": "Spider Key",
                    "brief_description": "能打开锁链的钥匙。",
                    "owner": "player",
                },
            ],
            "exit_characters": [
                {
                    "entity_id": "char_ilvara",
                    "reason": "撤回更深处的通道。",
                }
            ],
            "world_effects": ["新的哨点被发现。"],
        },
    )

    active_names = {item["name"] for item in result["active_profiles"]}
    assert "Sarith" in active_names
    assert "Ilvara" not in active_names
    assert result["world_state"]["entities"]["character:sarith"]["location"] == "Guard Post"
    assert "location:watch_post" in result["world_state"]["map"]["locations"]
    assert "location:guard_post" in result["world_state"]["map"]["locations"]["location:watch_post"]["adjacent"]
    assert result["world_state"]["inventory"]["Spider Key"] == "player"
    assert result["graph_update"]["entity_writes"] >= 3


def test_build_dm_reply_exposes_agars_style_structured_story_controls(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Velkynvelve\n"
        "Slave Pen connects to Guard Post.\n\n"
        "## Guard Post\n"
        "Guard Post connects to Lift.\n",
        encoding="utf-8",
    )

    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
    )
    service.ingest_setting(
        campaign_id="camp_reply_schema",
        title="Out of the Abyss",
        file_paths=[setting_file],
    )
    service.start_session(
        campaign_id="camp_reply_schema",
        session_id="sess_reply_schema",
        player_name="米伦",
        current_scene="Guard Post",
    )

    reply_bundle = service.build_dm_reply(
        session_id="sess_reply_schema",
        player_message="我观察附近还有什么路可走。",
    )

    assert "scene_transition" in reply_bundle["output_schema"]
    assert "new_location" in reply_bundle["output_schema"]
    assert "new_entities" in reply_bundle["output_schema"]
    assert "exit_characters" in reply_bundle["output_schema"]
    assert "相邻地点" in reply_bundle["user_prompt"]
    assert "Lift" in reply_bundle["user_prompt"]


def test_two_stage_graph_extractor_links_entities_across_snippets():
    from agars_dm_backend.graph_extractor import TwoStageHeuristicCampaignGraphExtractor

    extractor = TwoStageHeuristicCampaignGraphExtractor()
    result = extractor.extract(
        campaign_id="camp_extract",
        ontology={
            "entity_types": [{"name": "character"}, {"name": "faction"}, {"name": "location"}],
            "edge_types": [{"name": "belongs_to"}, {"name": "located_in"}],
        },
        snippets=[
            {"source": "chapter_01.md", "text": "Ilvara commands House Mizzrym."},
            {"source": "chapter_01.md", "text": "Ilvara waits in Velkynvelve and guards the slave pen."},
        ],
    )

    entity_ids = {item["entity_id"] for item in result["entities"]}
    relationship_types = {item["relationship_type"] for item in result["relationships"]}

    assert "character:ilvara" in entity_ids
    assert "faction:house_mizzrym" in entity_ids
    assert "location:velkynvelve" in entity_ids
    assert "belongs_to" in relationship_types
    assert "located_in" in relationship_types


def test_graph_aware_profile_generator_uses_graph_facts():
    from agars_dm_backend.profile_generator import GraphAwareProfileGenerator

    generator = GraphAwareProfileGenerator()
    profiles = generator.generate_profiles(
        campaign_id="camp_profiles",
        entities=[
            {
                "entity_id": "character:ilvara",
                "entity_type": "character",
                "name": "Ilvara",
                "summary": "卓尔前哨站指挥官。",
                "status": "active",
            }
        ],
        graph_facts=[
            {
                "source_id": "character:ilvara",
                "relationship_type": "belongs_to",
                "target_id": "faction:house_mizzrym",
                "properties": {"target_name": "House Mizzrym"},
            },
            {
                "source_id": "character:ilvara",
                "relationship_type": "seeks",
                "target_id": "objective:deliver_prisoners",
                "properties": {"target_name": "把囚徒送往魔索布莱城"},
            },
        ],
    )

    assert profiles[0]["name"] == "Ilvara"
    assert "House Mizzrym" in json.dumps(profiles[0], ensure_ascii=False)
    assert "把囚徒送往魔索布莱城" in json.dumps(profiles[0], ensure_ascii=False)


def test_campaign_session_and_battle_sync_flow(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Greenest\n"
        "Greenest is a fortified town threatened by raiders.\n\n"
        "## Keep\n"
        "The keep shelters civilians during an attack.\n\n"
        "## Governor Nighthill\n"
        "Nighthill is wounded but still directing the defense.\n",
        encoding="utf-8",
    )

    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
        profile_generator=FakeProfileGenerator(),
        world_state_engine=FakeWorldStateEngine(),
    )
    campaign = service.ingest_setting(
        campaign_id="camp_greenest",
        title="Hoard of the Dragon Queen",
        file_paths=[setting_file],
    )

    assert campaign["campaign_id"] == "camp_greenest"
    assert campaign["document_count"] == 1
    assert campaign["text_length"] > 40
    assert campaign["graph_id"] == "camp_greenest"
    assert "entity_types" in campaign["ontology"]
    assert campaign["graph_summary"]["node_count"] == 5

    profiles = service.build_profiles(campaign_id="camp_greenest")
    assert profiles["profile_count"] == 1

    session = service.start_session(
        campaign_id="camp_greenest",
        session_id="sess_greenest_001",
        player_name="Eli",
        current_scene="Night raid at Greenest keep",
    )

    assert session["session_id"] == "sess_greenest_001"
    assert session["current_scene"] == "Night raid at Greenest keep"
    assert session["graph_id"] == "camp_greenest"
    assert session["world_state"]["engine_name"] == "fake"
    assert session["world_state"]["time_index"] == 0

    sync_result = service.sync_battle(
        session_id="sess_greenest_001",
        encounter_id="enc_greenest_gate",
        encounter_state={
            "round": 2,
            "current_entity_id": "ent_guard_001",
            "entities": {
                "ent_pc_001": {"name": "Eli", "hp": {"current": 11, "max": 18}, "location": "Greenest Keep"},
                "ent_enemy_001": {"name": "Blue Dragon Wyrmling", "hp": {"current": 24, "max": 52}},
            },
        },
        new_events=[
            {
                "event_type": "attack_resolved",
                "actor_entity_id": "ent_enemy_001",
                "target_entity_id": "ent_pc_001",
                "payload": {"damage_total": 7, "damage_type": "lightning", "reason": "Lightning Breath"},
            },
            {
                "event_type": "movement_resolved",
                "actor_entity_id": "ent_pc_001",
                "payload": {"destination": "Greenest Keep", "action": "retreat"},
            },
            {
                "event_type": "companion_joined",
                "actor_entity_id": "ent_guard_001",
                "target_entity_id": "ent_pc_001",
                "payload": {"companion_name": "Governor Nighthill"},
            }
        ],
    )

    assert sync_result["encounter_id"] == "enc_greenest_gate"
    assert sync_result["new_event_count"] == 3
    assert "Lightning Breath" in sync_result["battle_digest"]
    assert sync_result["world_state"]["time_index"] == 3
    assert sync_result["world_state"]["entity_locations"]["ent_pc_001"] == "Greenest Keep"
    assert "Governor Nighthill" in sync_result["world_state"]["companions"]

    reply_bundle = service.build_dm_reply(
        session_id="sess_greenest_001",
        player_message="我拖着伤员往要塞里撤，然后大喊让守军关门。",
    )

    assert reply_bundle["session_id"] == "sess_greenest_001"
    assert "Governor Nighthill" in reply_bundle["setting_context"]
    assert "Lightning Breath" in reply_bundle["battle_context"]
    assert "Ilvara" in reply_bundle["graph_context"]
    assert "Night raid at Greenest keep" in reply_bundle["world_state_context"]
    assert "time=3" in reply_bundle["world_state_context"]
    assert "守军关门" in reply_bundle["user_prompt"]
    assert "world_effects" in reply_bundle["output_schema"]
    assert "Ilvara" in reply_bundle["profile_context"]


def test_query_facts_returns_relevant_snippets(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.txt"
    setting_file.write_text(
        "Leosin Erlanthar is a monk investigating the Cult of the Dragon.\n"
        "The old tunnel beneath the mill leads toward the keep.\n",
        encoding="utf-8",
    )

    service = NarrativeDmService(
        base_dir=tmp_path / "runtime",
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
    )
    service.ingest_setting(
        campaign_id="camp_greenest",
        title="Greenest",
        file_paths=[setting_file],
    )

    result = service.query_facts(campaign_id="camp_greenest", query="Leosin tunnel")

    assert result["campaign_id"] == "camp_greenest"
    assert len(result["matches"]) >= 1
    assert len(result["graph_matches"]) >= 1
    assert len(result["snippet_matches"]) >= 1
    joined = json.dumps(result["matches"], ensure_ascii=False)
    assert "Leosin" in joined or "tunnel" in joined
    assert "Ilvara" in joined or "guards" in joined


def test_campaign_file_persists_ontology_and_graph_id(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "# Velkynvelve\n"
        "Ilvara commands the drow outpost.\n"
        "Prisoners are held in a slave pen suspended above the cavern.\n",
        encoding="utf-8",
    )

    runtime_dir = tmp_path / "runtime"
    service = NarrativeDmService(
        base_dir=runtime_dir,
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
    )
    service.ingest_setting(
        campaign_id="camp_velkynvelve",
        title="Out of the Abyss Chapter 1",
        file_paths=[setting_file],
    )

    campaign_path = runtime_dir / "campaigns" / "camp_velkynvelve.json"
    payload = json.loads(campaign_path.read_text(encoding="utf-8"))

    assert payload["graph_id"] == "camp_velkynvelve"
    assert payload["ontology"]["analysis_summary"] == "识别出角色、地点、阵营、线索与目标。"
    assert payload["ontology"]["entity_types"][0]["name"] == "character"
    assert payload["graph_summary"]["edge_count"] == 4


def test_build_profiles_persists_generated_profiles(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "Ilvara commands the drow outpost at Velkynvelve.\n"
        "Prisoners are held in the slave pen.\n",
        encoding="utf-8",
    )

    runtime_dir = tmp_path / "runtime"
    service = NarrativeDmService(
        base_dir=runtime_dir,
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
        profile_generator=FakeProfileGenerator(),
    )
    service.ingest_setting(
        campaign_id="camp_profiles",
        title="Outpost",
        file_paths=[setting_file],
    )

    result = service.build_profiles(campaign_id="camp_profiles")

    assert result["campaign_id"] == "camp_profiles"
    assert result["profile_count"] == 1

    profile_path = runtime_dir / "profiles" / "camp_profiles.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    assert payload["profiles"][0]["name"] == "Ilvara"
    assert payload["profiles"][0]["personality"] == "残忍、控制欲强"


def test_falkordb_graph_store_upserts_entities_relationships_and_metadata(tmp_path):
    from agars_dm_backend.falkor_graph_store import FalkorDBGraphStore

    backend = FakeFalkorGraphBackend()
    store = FalkorDBGraphStore(base_dir=tmp_path / "runtime", backend=backend)

    entity_result = store.upsert_entities(
        campaign_id="camp_graph",
        entities=[
            {
                "entity_id": "ent_pc_miren_library_001",
                "entity_type": "character",
                "name": "米伦",
                "summary": "年轻法师。",
                "kind": "pc",
                "current_location": "Velkynvelve",
                "status": "captured",
                "canonical_names": ["米伦", "Miren"],
                "provenance": [
                    {
                        "source_file": "chapter_01.md",
                        "section_key": "chapter_01.slave_pen",
                        "snippet_id": "snippet_001",
                        "excerpt": "米伦被囚于前哨站。",
                    }
                ],
            },
            {
                "entity_id": "location:velkynvelve",
                "entity_type": "location",
                "name": "Velkynvelve",
                "summary": "卓尔前哨站。",
                "kind": "outpost",
                "canonical_names": ["Velkynvelve", "瓦肯维吾"],
            },
        ],
    )

    assert entity_result["graph_id"] == "camp_graph"
    assert entity_result["written_count"] == 2
    assert backend.nodes["ent_pc_miren_library_001"]["properties"]["name"] == "米伦"

    relationship_result = store.upsert_relationships(
        campaign_id="camp_graph",
        relationships=[
            {
                "source_id": "ent_pc_miren_library_001",
                "target_id": "location:velkynvelve",
                "relationship_type": "imprisoned_in",
                "properties": {
                    "status": "active",
                    "confidence": "confirmed",
                },
                "provenance": [
                    {
                        "source_file": "chapter_01.md",
                        "section_key": "chapter_01.slave_pen",
                        "snippet_id": "snippet_009",
                        "excerpt": "囚徒被关押在瓦肯维吾。",
                    }
                ],
            }
        ],
    )

    assert relationship_result["written_count"] == 1
    edge_key = "ent_pc_miren_library_001|imprisoned_in|location:velkynvelve"
    assert backend.relationships[edge_key]["properties"]["status"] == "active"

    alias_index = json.loads((tmp_path / "runtime" / "metadata" / "camp_graph_alias_index.json").read_text(encoding="utf-8"))
    assert alias_index["米伦"] == "ent_pc_miren_library_001"
    assert alias_index["Velkynvelve"] == "location:velkynvelve"

    provenance = json.loads((tmp_path / "runtime" / "metadata" / "camp_graph_provenance.json").read_text(encoding="utf-8"))
    assert provenance["nodes"]["ent_pc_miren_library_001"]["evidence"][0]["snippet_id"] == "snippet_001"
    assert provenance["relationships"][edge_key]["evidence"][0]["section_key"] == "chapter_01.slave_pen"


def test_falkordb_graph_store_ingest_campaign_graph_extracts_and_writes_graph(tmp_path):
    from agars_dm_backend.falkor_graph_store import FalkorDBGraphStore

    backend = FakeFalkorGraphBackend()
    store = FalkorDBGraphStore(
        base_dir=tmp_path / "runtime",
        backend=backend,
        extractor=FakeCampaignGraphExtractor(),
    )

    result = store.ingest_campaign_graph(
        campaign_id="camp_ingest",
        ontology={
            "entity_types": [{"name": "character"}, {"name": "location"}],
            "edge_types": [{"name": "located_in"}],
        },
        snippets=[
            {
                "source": "chapter_01.md",
                "text": "Ilvara commands the drow outpost of Velkynvelve.",
            }
        ],
    )

    assert backend.nodes["character:ilvara"]["properties"]["name"] == "Ilvara"
    edge_key = "character:ilvara|located_in|location:velkynvelve"
    assert backend.relationships[edge_key]["properties"]["confidence"] == "confirmed"
    assert result["graph_id"] == "camp_ingest"
    assert result["node_count"] == 2
    assert result["edge_count"] == 1
    assert any(item["entity_id"] == "character:ilvara" for item in result["entities"])
    assert any(item.get("relationship_type") == "located_in" for item in result["facts"])

    alias_index = json.loads((tmp_path / "runtime" / "metadata" / "camp_ingest_alias_index.json").read_text(encoding="utf-8"))
    assert alias_index["伊尔瓦拉"] == "character:ilvara"

    provenance = json.loads((tmp_path / "runtime" / "metadata" / "camp_ingest_provenance.json").read_text(encoding="utf-8"))
    assert provenance["nodes"]["character:ilvara"]["evidence"][0]["snippet_id"] == "snippet_001"
    assert provenance["relationships"][edge_key]["evidence"][0]["snippet_id"] == "snippet_003"


def test_falkordb_graph_store_query_helpers_use_backend_results(tmp_path):
    from agars_dm_backend.falkor_graph_store import FalkorDBGraphStore

    backend = FakeFalkorGraphBackend()
    store = FalkorDBGraphStore(base_dir=tmp_path / "runtime", backend=backend)
    store.upsert_entities(
        campaign_id="camp_query",
        entities=[
            {
                "entity_id": "ent_pc_miren_library_001",
                "entity_type": "character",
                "name": "米伦",
                "summary": "年轻法师。",
                "kind": "pc",
                "canonical_names": ["米伦"],
            },
            {
                "entity_id": "location:slave_pen",
                "entity_type": "location",
                "name": "奴隶围栏",
                "summary": "囚徒牢笼。",
                "kind": "prison",
                "canonical_names": ["奴隶围栏"],
            },
        ],
    )
    store.upsert_relationships(
        campaign_id="camp_query",
        relationships=[
            {
                "source_id": "ent_pc_miren_library_001",
                "target_id": "location:slave_pen",
                "relationship_type": "imprisoned_in",
                "properties": {"status": "active", "confidence": "confirmed"},
            }
        ],
    )

    entities = store.find_entities(campaign_id="camp_query", query="米伦", entity_type="character")
    relationships = store.get_entity_relationships(campaign_id="camp_query", entity_id="ent_pc_miren_library_001")
    facts = store.query_facts(campaign_id="camp_query", query="奴隶围栏")

    assert entities[0]["entity_id"] == "ent_pc_miren_library_001"
    assert relationships[0]["relationship_type"] == "imprisoned_in"
    assert "奴隶围栏" in json.dumps(facts, ensure_ascii=False)


def test_cli_scripts_round_trip(tmp_path):
    repo_root = tmp_path
    setting_file = repo_root / "setting.md"
    setting_file.write_text("The keep has a secret tunnel under the old mill.", encoding="utf-8")

    ingest = subprocess.run(
        [
            sys.executable,
            "/Users/runshi.zhang/DND-DM-skill/trpg-dm-system/scripts/ingest_setting.py",
            "--base-dir",
            str(repo_root / "runtime"),
            "--campaign-id",
            "camp_cli",
            "--title",
            "CLI Campaign",
            "--file",
            str(setting_file),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert ingest.returncode == 0, ingest.stderr
    ingest_payload = json.loads(ingest.stdout)
    assert ingest_payload["campaign_id"] == "camp_cli"

    start = subprocess.run(
        [
            sys.executable,
            "/Users/runshi.zhang/DND-DM-skill/trpg-dm-system/scripts/start_session.py",
            "--base-dir",
            str(repo_root / "runtime"),
            "--campaign-id",
            "camp_cli",
            "--session-id",
            "sess_cli",
            "--player-name",
            "Eli",
            "--current-scene",
            "Inside the keep",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert start.returncode == 0, start.stderr
    start_payload = json.loads(start.stdout)
    assert start_payload["session_id"] == "sess_cli"


def test_build_profiles_cli_round_trip(tmp_path):
    from agars_dm_backend.service import NarrativeDmService

    setting_file = tmp_path / "setting.md"
    setting_file.write_text(
        "Ilvara commands the outpost.\nThe prisoners are kept in the slave pen.\n",
        encoding="utf-8",
    )
    runtime_dir = tmp_path / "runtime"
    service = NarrativeDmService(
        base_dir=runtime_dir,
        ontology_generator=FakeOntologyGenerator(),
        graph_store=FakeGraphStore(),
        profile_generator=FakeProfileGenerator(),
    )
    service.ingest_setting(
        campaign_id="camp_cli_profiles",
        title="CLI Profiles",
        file_paths=[setting_file],
    )

    build = subprocess.run(
        [
            sys.executable,
            "/Users/runshi.zhang/DND-DM-skill/trpg-dm-system/scripts/build_profiles.py",
            "--base-dir",
            str(runtime_dir),
            "--campaign-id",
            "camp_cli_profiles",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert build.returncode == 0, build.stderr
    build_payload = json.loads(build.stdout)
    assert build_payload["campaign_id"] == "camp_cli_profiles"
    assert build_payload["profile_count"] >= 0
