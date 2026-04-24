from __future__ import annotations

from collections import deque
from copy import deepcopy
import re
from typing import Any


class NarrativeWorldStateEngine:
    def create_initial_state(
        self,
        *,
        campaign_id: str,
        session_id: str,
        current_scene: str,
        player_name: str,
        location_graph: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_locations = self._prepare_location_graph(location_graph or {})
        return {
            "campaign_id": campaign_id,
            "session_id": session_id,
            "clock": {
                "time_index": 0,
            },
            "scene": {
                "name": current_scene,
                "flags": [],
            },
            "player": {
                "name": player_name,
                "entity_id": "player",
            },
            "entities": {},
            "party": {
                "companions": [],
            },
            "inventory": {},
            "map": {
                "locations": normalized_locations,
            },
            "movement": {
                "last_check": {
                    "valid_move": True,
                    "required_path": [],
                    "warning": "",
                }
            },
        }

    def apply_events(
        self,
        *,
        world_state: dict[str, Any],
        encounter_state: dict[str, Any],
        new_events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        next_state = deepcopy(world_state)
        next_state.setdefault("clock", {}).setdefault("time_index", 0)
        next_state.setdefault("scene", {}).setdefault("flags", [])
        next_state.setdefault("entities", {})
        next_state.setdefault("party", {}).setdefault("companions", [])
        next_state.setdefault("inventory", {})
        next_state.setdefault("map", {}).setdefault("locations", {})
        next_state["map"]["locations"] = self._prepare_location_graph(next_state["map"]["locations"])
        next_state.setdefault("movement", {}).setdefault(
            "last_check",
            {"valid_move": True, "required_path": [], "warning": "", "applied_destination": ""},
        )

        for entity_id, entity in (encounter_state.get("entities") or {}).items():
            entity_state = next_state["entities"].setdefault(entity_id, {"name": entity.get("name", entity_id)})
            entity_state["name"] = entity.get("name", entity_state.get("name", entity_id))
            if entity.get("location"):
                entity_state["location"] = entity["location"]

        for event in new_events:
            next_state["clock"]["time_index"] += 1
            payload = event.get("payload", {}) or {}
            event_type = event.get("event_type", "")
            actor_id = event.get("actor_entity_id") or ""
            target_id = event.get("target_entity_id") or ""

            if event_type == "movement_resolved" and actor_id and payload.get("destination"):
                entity_state = next_state["entities"].setdefault(actor_id, {"name": actor_id})
                destination_name = payload["destination"]
                from_location = self._location_id_from_name(entity_state.get("location", ""), next_state["map"]["locations"])
                to_location = self._location_id_from_name(destination_name, next_state["map"]["locations"])
                movement_check = self._check_movement(
                    locations=next_state["map"]["locations"],
                    from_location=from_location,
                    to_location=to_location,
                )
                next_state["movement"]["last_check"] = movement_check
                applied_destination = movement_check.get("applied_destination", "")
                if movement_check["valid_move"]:
                    entity_state["location"] = destination_name
                elif applied_destination:
                    entity_state["location"] = self._location_name(applied_destination, next_state["map"]["locations"])
                if self._is_player_entity(actor_id=actor_id, world_state=next_state) and entity_state.get("location"):
                    next_state["scene"]["name"] = entity_state["location"]

            if event_type == "scene_flag_set" and payload.get("flag"):
                flag = payload["flag"]
                if flag not in next_state["scene"]["flags"]:
                    next_state["scene"]["flags"].append(flag)
                flag_location = self._resolve_flag_location(
                    actor_id=actor_id,
                    payload=payload,
                    scene_name=next_state["scene"].get("name", ""),
                    entities=next_state["entities"],
                    locations=next_state["map"]["locations"],
                )
                if flag_location:
                    self._apply_scene_flag(
                        locations=next_state["map"]["locations"],
                        location_id=flag_location,
                        flag=flag,
                    )

            if event_type == "companion_joined":
                companion_name = payload.get("companion_name") or actor_id
                if companion_name and companion_name not in next_state["party"]["companions"]:
                    next_state["party"]["companions"].append(companion_name)
                if actor_id:
                    entity_state = next_state["entities"].setdefault(actor_id, {"name": companion_name})
                    entity_state["name"] = companion_name

            if event_type == "item_transferred":
                item_name = payload.get("item_name")
                owner_id = target_id or actor_id
                if item_name and owner_id:
                    next_state["inventory"][item_name] = owner_id

        return next_state

    def build_context(self, *, world_state: dict[str, Any]) -> str:
        clock = world_state.get("clock", {})
        scene = world_state.get("scene", {})
        lines = [
            f"- 场景：{scene.get('name', '')}",
            f"- 时间推进计数：{clock.get('time_index', 0)}",
        ]

        flags = scene.get("flags", [])
        if flags:
            lines.append(f"- 场景标记：{'、'.join(flags)}")

        current_location_id = self._location_id_from_name(scene.get("name", ""), world_state.get("map", {}).get("locations", {}))
        if current_location_id:
            current_location = world_state.get("map", {}).get("locations", {}).get(current_location_id, {})
            local_flags = current_location.get("flags", [])
            nearby_flags = current_location.get("nearby_flags", [])
            if not nearby_flags:
                nearby_flags = self._neighboring_flags(
                    location_id=current_location_id,
                    locations=world_state.get("map", {}).get("locations", {}),
                )
            if local_flags:
                lines.append(f"- 当前区域态势：{'、'.join(local_flags)}")
            if nearby_flags:
                lines.append(f"- 邻区态势：{'、'.join(nearby_flags)}")

        movement_check = world_state.get("movement", {}).get("last_check", {})
        if movement_check:
            lines.append(f"- 移动校验：{'合法' if movement_check.get('valid_move') else '不合法'}")
            required_path = movement_check.get("required_path", [])
            if required_path:
                path_names = [self._location_name(loc_id, world_state.get("map", {}).get("locations", {})) for loc_id in required_path]
                lines.append(f"- 建议路径：{' -> '.join(path_names)}")
            if movement_check.get("warning"):
                lines.append(f"- 移动告警：{movement_check['warning']}")

        entities = world_state.get("entities", {})
        for entity_id, entity in list(entities.items())[:6]:
            if entity.get("location"):
                lines.append(f"- 位置：{entity_id} -> {entity['location']}")

        companions = world_state.get("party", {}).get("companions", [])
        if companions:
            lines.append(f"- 同伴：{'、'.join(companions)}")

        inventory = world_state.get("inventory", {})
        for item_name, owner_id in list(inventory.items())[:4]:
            lines.append(f"- 道具：{item_name} -> {owner_id}")

        return "\n".join(lines)

    def apply_player_action(
        self,
        *,
        world_state: dict[str, Any],
        player_message: str,
        actor_entity_id: str = "player",
    ) -> dict[str, Any]:
        next_state = deepcopy(world_state)
        next_state.setdefault("scene", {}).setdefault("name", "")
        next_state.setdefault("map", {}).setdefault("locations", {})
        next_state["map"]["locations"] = self._prepare_location_graph(next_state["map"]["locations"])
        next_state.setdefault("movement", {})["last_check"] = {
            "valid_move": True,
            "required_path": [],
            "warning": "",
            "applied_destination": "",
        }

        locations = next_state["map"]["locations"]
        current_location = self._location_id_from_name(next_state["scene"].get("name", ""), locations)
        detected_destination = self._detect_destination_from_text(
            text=player_message,
            locations=locations,
            current_location=current_location,
        )
        if not detected_destination:
            return {
                "world_state": next_state,
                "detected_destination": "",
            }

        movement_check = self._check_movement(
            locations=locations,
            from_location=current_location,
            to_location=detected_destination,
        )
        next_state["movement"]["last_check"] = movement_check
        applied_destination = movement_check.get("applied_destination") or ""
        if movement_check.get("valid_move"):
            applied_destination = detected_destination
        if applied_destination:
            next_state["scene"]["name"] = self._location_name(applied_destination, locations)
            next_state.setdefault("entities", {}).setdefault(actor_entity_id, {"name": actor_entity_id})["location"] = next_state["scene"]["name"]

        return {
            "world_state": next_state,
            "detected_destination": detected_destination,
        }

    def apply_scene_transition(
        self,
        *,
        world_state: dict[str, Any],
        new_location: str,
        actor_entity_id: str = "player",
    ) -> dict[str, Any]:
        next_state = deepcopy(world_state)
        next_state.setdefault("scene", {}).setdefault("name", "")
        next_state.setdefault("map", {}).setdefault("locations", {})
        next_state["map"]["locations"] = self._prepare_location_graph(next_state["map"]["locations"])
        next_state.setdefault("movement", {})["last_check"] = {
            "valid_move": True,
            "required_path": [],
            "warning": "",
            "applied_destination": "",
        }

        location_id = self._location_id_from_name(new_location, next_state["map"]["locations"])
        if not location_id:
            return {"world_state": next_state, "applied_location": ""}

        location_name = self._location_name(location_id, next_state["map"]["locations"])
        next_state["scene"]["name"] = location_name
        next_state.setdefault("entities", {}).setdefault(actor_entity_id, {"name": actor_entity_id})["location"] = location_name
        next_state["movement"]["last_check"] = {
            "valid_move": True,
            "required_path": [location_id],
            "warning": "",
            "applied_destination": location_id,
        }
        return {"world_state": next_state, "applied_location": location_id}

    def _check_movement(
        self,
        *,
        locations: dict[str, dict[str, Any]],
        from_location: str,
        to_location: str,
    ) -> dict[str, Any]:
        if not from_location or not to_location or from_location == to_location:
            return {"valid_move": True, "required_path": [], "warning": "", "applied_destination": ""}

        adjacent = locations.get(from_location, {}).get("adjacent", [])
        if to_location in adjacent:
            return {
                "valid_move": True,
                "required_path": [from_location, to_location],
                "warning": "",
                "applied_destination": to_location,
            }

        required_path = self._find_path(locations=locations, start=from_location, goal=to_location)
        if required_path:
            return {
                "valid_move": False,
                "required_path": required_path,
                "warning": "目标地点不与当前位置直接邻接，需要经过中间路径。",
                "applied_destination": required_path[1] if len(required_path) > 1 else "",
            }

        return {
            "valid_move": False,
            "required_path": [],
            "warning": "目标地点与当前位置不连通。",
            "applied_destination": "",
        }

    def _find_path(
        self,
        *,
        locations: dict[str, dict[str, Any]],
        start: str,
        goal: str,
    ) -> list[str]:
        if start not in locations or goal not in locations:
            return []

        queue: deque[tuple[str, list[str]]] = deque([(start, [start])])
        visited = {start}
        while queue:
            current, path = queue.popleft()
            if current == goal:
                return path
            for nxt in locations.get(current, {}).get("adjacent", []):
                if nxt in visited:
                    continue
                visited.add(nxt)
                queue.append((nxt, path + [nxt]))
        return []

    def _location_id_from_name(self, name: str, locations: dict[str, dict[str, Any]]) -> str:
        if not name:
            return ""
        lowered = self._normalize_text(name)
        for location_id, meta in locations.items():
            if self._normalize_text(meta.get("name", "")) == lowered:
                return location_id
            for alias in meta.get("aliases", []):
                if self._normalize_text(alias) == lowered:
                    return location_id
        return ""

    def _detect_destination_from_text(
        self,
        *,
        text: str,
        locations: dict[str, dict[str, Any]],
        current_location: str,
    ) -> str:
        if not text.strip() or not locations:
            return ""
        explicit = re.search(r"\[移动到[：:]\s*([^\]]+)\]", text, flags=re.IGNORECASE)
        if explicit:
            return self._location_id_from_name(explicit.group(1).strip(), locations)

        move_verbs = [
            "前往",
            "去",
            "去到",
            "走向",
            "走去",
            "走到",
            "来到",
            "赶往",
            "奔向",
            "返回",
            "回到",
            "移动到",
            "move to",
            "go to",
            "head to",
            "travel to",
        ]
        lowered_text = self._normalize_text(text)
        if not any(verb in lowered_text for verb in move_verbs):
            return ""

        candidates: list[tuple[int, str]] = []
        for location_id, meta in locations.items():
            if location_id == current_location:
                continue
            names = [meta.get("name", "")] + list(meta.get("aliases", []))
            for name in names:
                normalized_name = self._normalize_text(name)
                if normalized_name and normalized_name in lowered_text:
                    candidates.append((len(normalized_name), location_id))
        if not candidates:
            return ""
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _normalize_text(self, value: str) -> str:
        normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
        normalized = re.sub(r"[-_]+", " ", normalized)
        normalized = normalized.strip(" .。,:;!?'\"`()[]{}")
        normalized = re.sub(r"^(?:the)\s+", "", normalized)
        return normalized

    def _location_name(self, location_id: str, locations: dict[str, dict[str, Any]]) -> str:
        return locations.get(location_id, {}).get("name", location_id)

    def _prepare_location_graph(self, locations: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for location_id, data in (locations or {}).items():
            location = deepcopy(data)
            location.setdefault("name", location_id)
            location.setdefault("adjacent", [])
            location.setdefault("flags", [])
            location.setdefault("nearby_flags", [])
            location.setdefault("aliases", [])
            normalized[location_id] = location
        return normalized

    def _resolve_flag_location(
        self,
        *,
        actor_id: str,
        payload: dict[str, Any],
        scene_name: str,
        entities: dict[str, dict[str, Any]],
        locations: dict[str, dict[str, Any]],
    ) -> str:
        explicit_location = payload.get("location") or ""
        if explicit_location:
            return self._location_id_from_name(explicit_location, locations)
        if actor_id and entities.get(actor_id, {}).get("location"):
            return self._location_id_from_name(entities[actor_id]["location"], locations)
        return self._location_id_from_name(scene_name, locations)

    def _apply_scene_flag(
        self,
        *,
        locations: dict[str, dict[str, Any]],
        location_id: str,
        flag: str,
    ) -> None:
        source = locations.get(location_id)
        if not source:
            return
        if flag not in source["flags"]:
            source["flags"].append(flag)
        for neighbor_id in source.get("adjacent", []):
            neighbor = locations.get(neighbor_id)
            if not neighbor:
                continue
            if flag not in neighbor["nearby_flags"]:
                neighbor["nearby_flags"].append(flag)

    def _neighboring_flags(
        self,
        *,
        location_id: str,
        locations: dict[str, dict[str, Any]],
    ) -> list[str]:
        found: list[str] = []
        for neighbor_id in locations.get(location_id, {}).get("adjacent", []):
            neighbor = locations.get(neighbor_id, {})
            for flag in neighbor.get("nearby_flags", []):
                if flag not in found:
                    found.append(flag)
            for flag in neighbor.get("flags", []):
                if flag not in found:
                    found.append(flag)
        return found

    def _is_player_entity(self, *, actor_id: str, world_state: dict[str, Any]) -> bool:
        player = world_state.get("player", {})
        player_entity_id = player.get("entity_id") or "player"
        return actor_id == player_entity_id or actor_id == "player"
