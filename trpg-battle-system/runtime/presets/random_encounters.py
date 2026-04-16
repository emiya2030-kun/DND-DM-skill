from __future__ import annotations

from copy import deepcopy
from random import choice
from typing import Any

_RANDOM_ENCOUNTER_CATALOG: dict[str, list[dict[str, Any]]] = {
    "forest_road": [
        {
            "encounter_name": "林间伏击",
            "map_setup": {
                "map_id": "map_forest_road_01",
                "name": "林地小径",
                "description": "树林中的狭窄道路。",
                "width": 20,
                "height": 20,
                "grid_size_feet": 5,
                "terrain": [],
                "zones": [],
                "auras": [],
                "remains": [],
                "battlemap_details": [{"title": "树林", "summary": "树木遮挡视线"}],
            },
            "entity_setups": [
                {
                    "entity_instance_id": "ent_ally_wizard_001",
                    "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
                    "runtime_overrides": {"name": "米伦", "position": {"x": 4, "y": 4}},
                },
                {
                    "entity_instance_id": "ent_enemy_brute_001",
                    "template_ref": {"source_type": "monster", "template_id": "monster_sabur"},
                    "runtime_overrides": {"name": "荒林掠夺者", "position": {"x": 11, "y": 9}},
                },
            ],
        }
    ],
    "swamp_road": [
        {
            "encounter_name": "沼泽堵截",
            "map_setup": {
                "map_id": "map_swamp_road_01",
                "name": "雾沼路段",
                "description": "泥泞地带视野受限。",
                "width": 20,
                "height": 20,
                "grid_size_feet": 5,
                "terrain": [],
                "zones": [],
                "auras": [],
                "remains": [],
                "battlemap_details": [{"title": "雾沼", "summary": "湿地使移动变慢"}],
            },
            "entity_setups": [
                {
                    "entity_instance_id": "ent_ally_wizard_001",
                    "template_ref": {"source_type": "pc", "template_id": "pc_miren"},
                    "runtime_overrides": {"name": "米伦", "position": {"x": 3, "y": 5}},
                },
                {
                    "entity_instance_id": "ent_enemy_brute_001",
                    "template_ref": {"source_type": "monster", "template_id": "monster_sabur"},
                    "runtime_overrides": {"name": "沼泽掠夺者", "position": {"x": 12, "y": 10}},
                },
            ],
        }
    ],
}


def choose_random_encounter_setup(theme: str | None = None) -> dict[str, Any]:
    if theme is not None:
        candidates = _RANDOM_ENCOUNTER_CATALOG.get(theme)
        if not candidates:
            raise ValueError(f"unknown encounter theme '{theme}'")
        return deepcopy(choice(candidates))

    available_themes = list(_RANDOM_ENCOUNTER_CATALOG.keys())
    if not available_themes:
        raise ValueError("random encounter catalog is empty")
    chosen_theme = choice(available_themes)
    return deepcopy(choice(_RANDOM_ENCOUNTER_CATALOG[chosen_theme]))
