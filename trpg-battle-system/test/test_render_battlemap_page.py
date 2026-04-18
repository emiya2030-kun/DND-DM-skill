"""完整 battlemap 预览页测试。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.services.map.render_battlemap_page import RenderBattlemapPage


def build_preview_encounter() -> Encounter:
    wizard = EncounterEntity(
        entity_id="ent_ally_wizard_001",
        entity_def_id="pc_magus_lv6",
        source_ref={"class_name": "wizard"},
        name="米伦",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 5, "y": 4},
        hp={"current": 22, "max": 27, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 25},
        initiative=16,
    )
    ranger = EncounterEntity(
        entity_id="ent_ally_ranger_001",
        entity_def_id="pc_scout_lv6",
        source_ref={"class_name": "ranger"},
        name="萨布尔",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 8, "y": 7},
        hp={"current": 29, "max": 34, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=13,
    )
    brute = EncounterEntity(
        entity_id="ent_enemy_brute_001",
        name="钢铁蛮兵",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 16, "y": 14},
        hp={"current": 40, "max": 40, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=11,
    )

    return Encounter(
        encounter_id="enc_preview_demo",
        name="月祷礼拜堂攻防战",
        status="active",
        round=4,
        current_entity_id=wizard.entity_id,
        turn_order=[wizard.entity_id, ranger.entity_id, brute.entity_id],
        entities={
            wizard.entity_id: wizard,
            ranger.entity_id: ranger,
            brute.entity_id: brute,
        },
        map=EncounterMap(
            map_id="map_preview_demo",
            name="月祷礼拜堂",
            description="残破礼拜堂被高台、废墙和星火结界切成多个战术区域。",
            width=20,
            height=20,
            terrain=[
                {"terrain_id": "wall_north", "type": "wall", "x": 7, "y": 18, "blocks_movement": True, "blocks_los": True},
                {"terrain_id": "wall_north_02", "type": "wall", "x": 8, "y": 18, "blocks_movement": True, "blocks_los": True},
                {"terrain_id": "mire_centre", "type": "difficult_terrain", "x": 10, "y": 10, "costs_extra_movement": True},
                {"terrain_id": "mire_centre_02", "type": "difficult_terrain", "x": 11, "y": 10, "costs_extra_movement": True},
                {"terrain_id": "apse_high", "type": "high_ground", "x": 4, "y": 15},
                {"terrain_id": "apse_high_02", "type": "high_ground", "x": 5, "y": 15},
            ],
            zones=[
                {"zone_id": "ward_001", "type": "spell_area", "cells": [[13, 12], [14, 12], [13, 13], [14, 13]], "note": "星火结界仍在礼拜堂中殿燃烧。"},
                {"zone_id": "ward_002", "type": "hazard_area", "cells": [[4, 9], [5, 9], [4, 10]], "note": "冰雾缓滞带会拖慢穿越者的步伐。"},
            ],
        ),
    )


class RenderBattlemapPageTests(unittest.TestCase):
    def test_render_returns_full_html_document(self) -> None:
        encounter = build_preview_encounter()
        encounter.encounter_notes = [
            {
                "type": "spell_area_overlay",
                "payload": {
                    "overlay_id": "overlay_fireball_001",
                    "kind": "spell_area_circle",
                    "source_spell_id": "fireball",
                    "source_spell_name": "火球术",
                    "target_point": {"x": 5, "y": 5, "anchor": "cell_center"},
                    "radius_feet": 20,
                    "radius_tiles": 4,
                    "persistence": "instant",
                },
            }
        ]

        html = RenderBattlemapPage().execute(encounter)

        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("battlemap-preview", html)
        self.assertIn("battlemap-app", html)
        self.assertIn("app-shell", html)
        self.assertIn("encounter-hero", html)
        self.assertIn("topbar-chip", html)
        self.assertIn("月祷礼拜堂攻防战", html)
        self.assertIn("月祷礼拜堂", html)
        self.assertIn("战斗地图预览", html)
        self.assertNotIn("LLM Map Notes", html)
        self.assertNotIn("terrain_summary", html)
        self.assertIn("initiative-table", html)
        self.assertIn("character-card", html)
        self.assertIn("20 × 20", html)
        self.assertIn("每格 5 尺", html)
        self.assertIn("grid-template-columns: repeat(20, minmax(0, 1fr));", html)
        self.assertIn("📜", html)
        self.assertIn("🏹", html)
        self.assertIn("window.__BATTLEMAP_STATE__", html)
        self.assertIn("window.applyEncounterState", html)
        self.assertIn("window.applyToolResult", html)
        self.assertIn("window.applyToolError", html)
        self.assertIn("window.getLastToolResult", html)
        self.assertIn("window.getLastToolError", html)
        self.assertIn("window.__BATTLEMAP_RUNTIME__", html)
        self.assertIn("battlemap-runtime", html)
        self.assertIn("window.addEventListener('message'", html)
        self.assertIn("apply_encounter_state", html)
        self.assertIn("apply_tool_result", html)
        self.assertIn("apply_tool_error", html)
        self.assertIn("battlemap:runtime-ready", html)
        self.assertIn("battlemap:runtime-message-applied", html)
        self.assertIn("tool result must be an object", html)
        self.assertIn("tool result does not contain encounter_state", html)
        self.assertIn("tool error must be an object", html)
        self.assertIn("battlemap:tool-result-applied", html)
        self.assertIn("battlemap:tool-error-applied", html)
        self.assertIn("window.__LAST_TOOL_ERROR__", html)
        self.assertIn('data-role="battlemap-view-root"', html)
        self.assertIn('data-role="encounter-title"', html)
        self.assertIn("spell_area_overlays", html)
        self.assertIn("overlay_fireball_001", html)


if __name__ == "__main__":
    unittest.main()
