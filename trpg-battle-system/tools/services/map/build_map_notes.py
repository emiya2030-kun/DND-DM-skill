from __future__ import annotations

from typing import Any

from tools.models.encounter import Encounter


class BuildMapNotes:
    """把 EncounterMap 投影成适合 LLM 读取的结构化地图摘要。"""

    def execute(self, encounter: Encounter) -> dict[str, Any]:
        return {
            "terrain_summary": self._build_terrain_summary(encounter),
            "zone_summary": self._build_zone_summary(encounter),
            "landmarks": self._build_landmarks(encounter),
            "tactical_warnings": self._build_tactical_warnings(encounter),
        }

    def _build_terrain_summary(self, encounter: Encounter) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for terrain in encounter.map.terrain:
            terrain_type = terrain.get("type")
            if terrain_type == "high_ground":
                continue

            items.append(
                {
                    "type": terrain_type,
                    "region": terrain.get("terrain_id", terrain_type),
                    "cells": [[terrain.get("x"), terrain.get("y")]],
                    "rules": self._terrain_rules(terrain),
                    "note": self._terrain_note(terrain),
                }
            )
        return items

    def _build_zone_summary(self, encounter: Encounter) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for zone in encounter.map.zones:
            items.append(
                {
                    "type": zone.get("type"),
                    "region": zone.get("zone_id", zone.get("type")),
                    "cells": zone.get("cells", []),
                    "rules": zone.get("rules", []),
                    "note": zone.get("note"),
                }
            )
        return items

    def _build_landmarks(self, encounter: Encounter) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for terrain in encounter.map.terrain:
            if terrain.get("type") != "high_ground":
                continue
            items.append(
                {
                    "type": "high_ground",
                    "region": terrain.get("terrain_id", "high_ground"),
                    "cells": [[terrain.get("x"), terrain.get("y")]],
                    "note": "高台格可作为视野和站位优势点。",
                }
            )
        return items

    def _build_tactical_warnings(self, encounter: Encounter) -> list[str]:
        warnings: list[str] = []
        if any(terrain.get("type") == "wall" for terrain in encounter.map.terrain):
            warnings.append("部分路径被墙体阻挡，移动前应先确认可通行路线。")
        if any(terrain.get("type") == "difficult_terrain" for terrain in encounter.map.terrain):
            warnings.append("战场包含困难地形，穿越这些格子会额外消耗移动力。")
        return warnings

    def _terrain_rules(self, terrain: dict[str, Any]) -> list[str]:
        rules: list[str] = []
        if terrain.get("blocks_movement"):
            rules.append("blocks_movement")
        if terrain.get("blocks_los"):
            rules.append("blocks_los")
        if terrain.get("costs_extra_movement"):
            rules.append("costs_extra_movement")
        if terrain.get("type") == "high_ground":
            rules.append("elevated_position")
        return rules

    def _terrain_note(self, terrain: dict[str, Any]) -> str:
        terrain_type = terrain.get("type")
        if terrain_type == "wall":
            return "该格为墙体，阻挡移动与视线。"
        if terrain_type == "difficult_terrain":
            return "该格为困难地形，进入时需要额外移动力。"
        return f"该格属于 {terrain_type} 地形。"
