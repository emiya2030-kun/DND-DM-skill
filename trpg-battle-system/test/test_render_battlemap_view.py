"""网页 battlemap 视图测试：覆盖 HTML 网格与地图摘要。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.services.map.build_map_notes import BuildMapNotes
from tools.services.map.render_battlemap_view import RenderBattlemapView


def build_demo_encounter() -> Encounter:
    paladin = EncounterEntity(
        entity_id="ent_ally_paladin_001",
        entity_def_id="pc_tank_lv5",
        source_ref={"class_name": "paladin"},
        name="Aster",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 30, "max": 35, "temp": 0},
        ac=18,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
    )
    goblin = EncounterEntity(
        entity_id="ent_enemy_goblin_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 5, "y": 4},
        hp={"current": 7, "max": 7, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )

    return Encounter(
        encounter_id="enc_battlemap_demo",
        name="Battlemap Demo",
        status="active",
        round=3,
        current_entity_id=paladin.entity_id,
        turn_order=[paladin.entity_id, goblin.entity_id],
        entities={paladin.entity_id: paladin, goblin.entity_id: goblin},
        map=EncounterMap(
            map_id="map_demo",
            name="Sanctum",
            description="A ritual hall with layered terrain.",
            width=6,
            height=4,
            terrain=[
                {
                    "terrain_id": "ter_wall_001",
                    "type": "wall",
                    "x": 1,
                    "y": 4,
                    "blocks_movement": True,
                    "blocks_los": True,
                },
                {
                    "terrain_id": "ter_difficult_001",
                    "type": "difficult_terrain",
                    "x": 3,
                    "y": 1,
                    "costs_extra_movement": True,
                },
                {
                    "terrain_id": "ter_high_ground_001",
                    "type": "high_ground",
                    "x": 2,
                    "y": 3,
                },
            ],
            zones=[
                {
                    "zone_id": "zone_spell_001",
                    "type": "spell_area",
                    "cells": [[3, 3], [4, 3]],
                    "note": "Lingering radiant field.",
                },
                {
                    "zone_id": "zone_spell_002",
                    "type": "hazard_area",
                    "cells": [[5, 2], [6, 2]],
                    "note": "Necrotic mist slows movement.",
                }
            ],
        ),
    )


class RenderBattlemapViewTests(unittest.TestCase):
    def test_render_shows_skeleton_remains_on_empty_tile(self) -> None:
        encounter = build_demo_encounter()
        encounter.map.remains = [
            {
                "remains_id": "remains_goblin_001",
                "icon": "💀",
                "label": "哥布林尸骸",
                "position": {"x": 6, "y": 4},
            }
        ]

        payload = RenderBattlemapView().execute(encounter)

        self.assertIn("tile__remains", payload["html"])
        self.assertIn("💀", payload["html"])
        self.assertIn("哥布林尸骸", payload["html"])

    def test_render_marks_zero_hp_player_with_red_outline(self) -> None:
        encounter = build_demo_encounter()
        player = encounter.entities["ent_ally_paladin_001"]
        player.hp["current"] = 0
        player.conditions = ["unconscious"]

        payload = RenderBattlemapView().execute(encounter)

        self.assertIn('class="tile tile--downed', payload["html"])
        self.assertNotIn("token--downed\">", payload["html"])
        self.assertNotIn("token--dead\">", payload["html"])
        self.assertIn("character-card--downed", payload["html"])

    def test_render_marks_dead_player_with_dead_token_and_label(self) -> None:
        encounter = build_demo_encounter()
        player = encounter.entities["ent_ally_paladin_001"]
        player.hp["current"] = 0
        player.combat_flags = {"is_dead": True}

        payload = RenderBattlemapView().execute(encounter)

        self.assertIn('class="tile tile--dead', payload["html"])
        self.assertNotIn("token--dead\">", payload["html"])
        self.assertNotIn("token--downed\">", payload["html"])
        self.assertIn("死亡", payload["html"])

    def test_render_highlights_recent_forced_movement_cells(self) -> None:
        encounter = build_demo_encounter()

        payload = RenderBattlemapView().execute(
            encounter,
            recent_forced_movement={
                "start_position": {"x": 5, "y": 4},
                "resolved_path": [{"x": 6, "y": 4}],
                "final_position": {"x": 6, "y": 4},
                "blocked": False,
            },
        )

        self.assertIn("tile--forced-origin", payload["html"])
        self.assertIn("tile--forced-path", payload["html"])
        self.assertIn("tile--forced-destination", payload["html"])
        self.assertIn("亮色轨迹：最近一次强制位移", payload["html"])
        self.assertIn("--forced-highlight:", payload["html"])
        self.assertIn(
            ".tile--forced-origin,.tile--forced-path{box-shadow:inset 0 0 0 2px var(--forced-highlight),0 0 18px var(--forced-highlight-soft);}",
            payload["html"],
        )
        self.assertIn(
            ".tile--forced-destination,.tile--forced-blocked{box-shadow:inset 0 0 0 2px var(--forced-highlight),0 0 18px var(--forced-highlight-soft),0 0 0 1px var(--forced-highlight-strong);}",
            payload["html"],
        )

    def test_render_shows_recent_activity_panel(self) -> None:
        encounter = build_demo_encounter()

        payload = RenderBattlemapView().execute(
            encounter,
            recent_forced_movement={
                "summary": "Goblin被 Push 推离 5 尺，移动到 (6,4)。",
            },
            recent_turn_effects=[
                {
                    "summary": "回合结束，Aster的定身术持续效果对Goblin结算。WIS 豁免失败。",
                }
            ],
        )

        self.assertIn("战况记录", payload["html"])
        self.assertIn("自动效果", payload["html"])
        self.assertIn("强制位移", payload["html"])
        self.assertIn("Aster的定身术持续效果", payload["html"])
        self.assertIn("Goblin被 Push 推离 5 尺", payload["html"])
        self.assertIn(".activity-feed{display:grid;gap:10px;max-height:", payload["html"])
        self.assertIn("overflow-y:auto;", payload["html"])

    def test_render_shows_recent_activity_empty_state(self) -> None:
        encounter = build_demo_encounter()

        payload = RenderBattlemapView().execute(
            encounter,
            recent_forced_movement=None,
            recent_turn_effects=[],
        )

        self.assertIn("战况记录", payload["html"])
        self.assertIn("本回合暂未记录新的自动结算。", payload["html"])

    def test_render_shows_spell_area_circle_overlay(self) -> None:
        encounter = build_demo_encounter()

        payload = RenderBattlemapView().execute(
            encounter,
            spell_area_overlays=[
                {
                    "overlay_id": "overlay_fireball_001",
                    "kind": "spell_area_circle",
                    "target_point": {"x": 3, "y": 4, "anchor": "cell_center"},
                    "radius_tiles": 4,
                    "source_spell_name": "火球术",
                    "persistence": "instant",
                }
            ],
        )

        self.assertIn("battlemap-spell-overlays", payload["html"])
        self.assertIn("battlemap-spell-overlay", payload["html"])
        self.assertIn("data-spell-name=\"火球术\"", payload["html"])
        self.assertIn("--overlay-x:3", payload["html"])

    def test_render_returns_html_with_grid_layers_and_sidebar(self) -> None:
        encounter = build_demo_encounter()

        payload = RenderBattlemapView().execute(encounter)
        self.assertIn("battlemap-header__layout", payload["html"])
        self.assertIn("header-initiative", payload["html"])
        self.assertIn(".header-initiative__body{max-height:", payload["html"])
        self.assertIn("overflow-y:auto;", payload["html"])

        self.assertEqual(payload["title"], "Battlemap Demo")
        self.assertIn("battlemap-shell", payload["html"])
        self.assertIn("war-room", payload["html"])
        self.assertIn("battlefield-panel", payload["html"])
        self.assertIn("battlemap-grid-frame", payload["html"])
        self.assertIn("grid-sheen", payload["html"])
        self.assertIn("tile-tooltip", payload["html"])
        self.assertIn("tile-tooltip__content", payload["html"])
        self.assertIn(".tile-tooltip{position:absolute;left:50%;top:4px;", payload["html"])
        self.assertIn("sidebar-card", payload["html"])
        self.assertIn("turn-list", payload["html"])
        self.assertIn("entity-pills", payload["html"])
        self.assertIn("battlemap-frame", payload["html"])
        self.assertIn("tactical-surface", payload["html"])
        self.assertIn("hud-panel", payload["html"])
        self.assertIn("token token--ally", payload["html"])
        self.assertIn("grid-template-columns: repeat(6, minmax(0, 1fr));", payload["html"])
        self.assertIn("background:rgba(165,191,228,.28)", payload["html"])
        self.assertIn("border:1px solid rgba(214,228,255,.06)", payload["html"])
        self.assertIn("border-bottom:1px solid rgba(164,187,220,.16)", payload["html"])
        self.assertIn("zone-swatch", payload["html"])
        self.assertIn("terrain-swatch", payload["html"])
        self.assertIn("terrain-swatch--wall", payload["html"])
        self.assertIn("terrain-swatch--difficult", payload["html"])
        self.assertIn("terrain-swatch--high-ground", payload["html"])
        self.assertIn("legend-list__zone", payload["html"])
        self.assertIn("墙壁：不可穿越并阻挡视线。", payload["html"])
        self.assertIn("困难地形：进入时需要额外移动。", payload["html"])
        self.assertIn("高台：提供抬升站位与视野优势。", payload["html"])
        self.assertIn("Lingering radiant field.", payload["html"])
        self.assertIn("区域效果：Lingering radiant field.", payload["html"])
        self.assertIn("Necrotic mist slows movement.", payload["html"])
        self.assertIn("区域效果：Necrotic mist slows movement.", payload["html"])
        self.assertIn("--zone-fill:rgba(235,200,255,.3)", payload["html"])
        self.assertIn("--zone-fill:rgba(155,225,255,.28)", payload["html"])
        self.assertIn("--zone-glow:rgba(205,124,255,.32)", payload["html"])
        self.assertIn("--zone-glow:rgba(91,202,255,.28)", payload["html"])
        self.assertIn("地图图例", payload["html"])
        self.assertIn("先攻表", payload["html"])
        self.assertIn("角色卡", payload["html"])
        self.assertIn("tile tile--wall", payload["html"])
        self.assertIn("tile tile--difficult", payload["html"])
        self.assertIn("tile tile--high-ground", payload["html"])
        self.assertIn("tile tile--zone", payload["html"])
        self.assertIn("tile__terrain-art", payload["html"])
        self.assertIn("tile__terrain-art--wall", payload["html"])
        self.assertIn("tile__terrain-art--difficult", payload["html"])
        self.assertIn("tile__terrain-art--high-ground", payload["html"])
        self.assertIn("tile__terrain-art--zone", payload["html"])
        self.assertIn("tile__occupant", payload["html"])
        self.assertIn('(2, 2)', payload["html"])
        self.assertIn("🛡", payload["html"])
        self.assertIn("current-turn", payload["html"])
        self.assertIn("initiative-table", payload["html"])
        self.assertIn("character-card", payload["html"])
        self.assertIn("Aster", payload["html"])
        self.assertIn("Goblin", payload["html"])
        self.assertLess(payload["html"].find("遭遇战术面板"), payload["html"].find("先攻表"))
        self.assertLess(payload["html"].find("先攻表"), payload["html"].find("回合焦点"))

    def test_build_map_notes_summarizes_structured_terrain(self) -> None:
        encounter = build_demo_encounter()

        payload = BuildMapNotes().execute(encounter)

        self.assertEqual(payload["terrain_summary"][0]["type"], "wall")
        self.assertEqual(payload["zone_summary"][0]["type"], "spell_area")
        self.assertEqual(payload["landmarks"][0]["type"], "high_ground")


if __name__ == "__main__":
    unittest.main()
