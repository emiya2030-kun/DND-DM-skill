from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.services.spells.area_geometry import collect_circle_cells, collect_entities_in_cells


def build_area_test_encounter() -> Encounter:
    caster = EncounterEntity(
        entity_id="ent_caster_001",
        name="Area Wizard",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
    )
    small_target = EncounterEntity(
        entity_id="ent_enemy_small_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 3, "y": 4},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )
    large_target = EncounterEntity(
        entity_id="ent_enemy_large_001",
        name="Ogre",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 6, "y": 4},
        hp={"current": 40, "max": 40, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=9,
        size="large",
    )
    far_target = EncounterEntity(
        entity_id="ent_enemy_far_001",
        name="Bandit",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 10, "y": 10},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=8,
    )
    return Encounter(
        encounter_id="enc_spell_area_geometry_test",
        name="Spell Area Geometry Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, small_target.entity_id, large_target.entity_id, far_target.entity_id],
        entities={
            caster.entity_id: caster,
            small_target.entity_id: small_target,
            large_target.entity_id: large_target,
            far_target.entity_id: far_target,
        },
        map=EncounterMap(
            map_id="map_spell_area_geometry_test",
            name="Spell Area Geometry Map",
            description="Area geometry test map.",
            width=12,
            height=12,
        ),
    )


class SpellAreaGeometryTests(unittest.TestCase):
    def test_circle_area_uses_cell_center_and_returns_covered_cells(self) -> None:
        cells = collect_circle_cells(
            map_width=12,
            map_height=12,
            target_point={"x": 3, "y": 4, "anchor": "cell_center"},
            radius_feet=20,
            grid_size_feet=5,
        )

        self.assertIn((3, 4), cells)
        self.assertIn((7, 4), cells)
        self.assertNotIn((8, 4), cells)

    def test_collects_all_entities_with_any_occupied_cell_inside_area(self) -> None:
        encounter = build_area_test_encounter()

        entity_ids = collect_entities_in_cells(
            encounter=encounter,
            covered_cells={(3, 4), (4, 4), (5, 4), (6, 4)},
        )

        self.assertEqual(
            entity_ids,
            ["ent_enemy_small_001", "ent_enemy_large_001"],
        )


if __name__ == "__main__":
    unittest.main()
