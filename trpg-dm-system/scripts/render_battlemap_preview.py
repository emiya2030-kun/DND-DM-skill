#!/usr/bin/env python3
"""生成一个可直接在浏览器中打开的 battlemap 预览页。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import ZoneDefinitionRepository
from tools.services.map.render_battlemap_page import RenderBattlemapPage


def _build_zone_instance(
    template_id: str,
    *,
    zone_id: str,
    cells: list[list[int]],
    source_name: str,
    source_entity_id: str | None = None,
) -> dict[str, object]:
    template = ZoneDefinitionRepository().get(template_id)
    if template is None:
        raise ValueError(f"unknown zone template: {template_id}")

    zone = deepcopy(template)
    zone["zone_id"] = zone_id
    zone["cells"] = cells
    runtime = zone.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
        zone["runtime"] = runtime
    runtime["source_name"] = source_name
    if isinstance(source_entity_id, str) and source_entity_id.strip():
        runtime["source_entity_id"] = source_entity_id
    return zone


def build_preview_encounter() -> Encounter:
    wizard = EncounterEntity(
        entity_id="ent_ally_wizard_001",
        entity_def_id="pc_magus_lv6",
        source_ref={"class_name": "wizard"},
        name="米伦",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 5, "y": 5},
        hp={"current": 22, "max": 27, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
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
        position={"x": 10, "y": 8},
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
        position={"x": 17, "y": 14},
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
        encounter_notes=[
            {
                "title": "区域测试顺序",
                "content": "先用米伦测试火焰灼域，再推进到萨布尔测试毒雾区，最后移动钢铁蛮兵进入冰霜缓滞区。",
            }
        ],
        map=EncounterMap(
            map_id="map_preview_demo",
            name="月祷礼拜堂",
            description="残破礼拜堂被火焰灼域、毒雾区与冰霜缓滞区切成多个战术区域，适合逐个验证区域触发。",
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
                _build_zone_instance(
                    "fire_burn_area",
                    zone_id="zone_preview_fire_001",
                    cells=[[6, 5], [7, 5], [6, 6], [7, 6]],
                    source_name="礼拜堂残焰",
                ),
                _build_zone_instance(
                    "poison_mist_area",
                    zone_id="zone_preview_poison_001",
                    cells=[[10, 8], [11, 8], [10, 9], [11, 9]],
                    source_name="祭坛毒雾",
                ),
                _build_zone_instance(
                    "frost_slow_area",
                    zone_id="zone_preview_frost_001",
                    cells=[[15, 14], [16, 14], [15, 15], [16, 15]],
                    source_name="北侧冰霜带",
                ),
            ],
        ),
    )


def main() -> None:
    output_path = PROJECT_ROOT / "data" / "examples" / "battlemap_preview.html"
    html = RenderBattlemapPage().execute(build_preview_encounter())
    output_path.write_text(html, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
