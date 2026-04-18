from __future__ import annotations

"""移动规则测试：覆盖体型占格、路径搜索和移动成本。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.services.encounter.movement_rules import (
    calculate_step_costs,
    get_center_position,
    get_occupied_cells,
    validate_movement_path,
)


def build_entity(
    entity_id: str,
    *,
    name: str,
    x: int,
    y: int,
    side: str = "ally",
    category: str = "pc",
    controller: str = "player",
    initiative: int = 10,
    size: str = "medium",
    speed_walk: int = 30,
    speed_fly: int | None = None,
    speed_remaining: int = 30,
    conditions: list[str] | None = None,
) -> EncounterEntity:
    speed = {"walk": speed_walk, "remaining": speed_remaining}
    if speed_fly is not None:
        speed["fly"] = speed_fly
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side=side,
        category=category,
        controller=controller,
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed=speed,
        initiative=initiative,
        size=size,
        conditions=conditions or [],
    )


def build_encounter(
    *entities: EncounterEntity,
    width: int = 12,
    height: int = 12,
    terrain: list[dict] | None = None,
) -> Encounter:
    first_entity = entities[0]
    return Encounter(
        encounter_id="enc_movement_rules",
        name="Movement Rules Encounter",
        status="active",
        round=1,
        current_entity_id=first_entity.entity_id,
        turn_order=[entity.entity_id for entity in entities],
        entities={entity.entity_id: entity for entity in entities},
        map=EncounterMap(
            map_id="map_movement_rules",
            name="Movement Test Map",
            description="A map used by movement rule tests.",
            width=width,
            height=height,
            terrain=[] if terrain is None else terrain,
        ),
    )


class MovementRulesTests(unittest.TestCase):
    def test_get_occupied_cells_for_large_creature(self) -> None:
        entity = build_entity("ent_large", name="Ogre", x=10, y=10, size="large")

        self.assertEqual(
            get_occupied_cells(entity, {"x": 10, "y": 10}),
            {(10, 10), (11, 10), (10, 11), (11, 11)},
        )

    def test_get_center_position_for_large_creature(self) -> None:
        entity = build_entity("ent_large", name="Ogre", x=10, y=10, size="large")

        self.assertEqual(get_center_position(entity), {"x": 10.5, "y": 10.5})

    def test_diagonal_cost_uses_5_10_and_resets_after_orthogonal(self) -> None:
        self.assertEqual(
            calculate_step_costs((0, 0), [(1, 1), (2, 2), (2, 3), (3, 4)]),
            [5, 10, 5, 5],
        )

    def test_validate_path_allows_ally_pass_through(self) -> None:
        mover = build_entity("ent_pc", name="Eric", x=2, y=2)
        ally = build_entity("ent_ally", name="Lia", x=3, y=2)
        encounter = build_encounter(mover, ally)

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 4, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual([step.anchor for step in result.path], [{"x": 3, "y": 2}, {"x": 4, "y": 2}])
        self.assertEqual(result.feet_cost, 10)

    def test_validate_path_routes_around_enemy(self) -> None:
        mover = build_entity("ent_pc", name="Eric", x=2, y=2)
        enemy = build_entity(
            "ent_enemy",
            name="Goblin",
            x=3,
            y=2,
            side="enemy",
            category="monster",
            controller="gm",
        )
        encounter = build_encounter(mover, enemy)

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 4, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.path[-1].anchor, {"x": 4, "y": 2})
        self.assertNotIn({"x": 3, "y": 2}, [step.anchor for step in result.path])
        self.assertEqual(result.feet_cost, 15)

    def test_difficult_terrain_doubles_cost_when_entered(self) -> None:
        mover = build_entity("ent_pc", name="Eric", x=2, y=2)
        encounter = build_encounter(
            mover,
            terrain=[{"x": 3, "y": 2, "type": "difficult_terrain"}],
        )

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 3, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.feet_cost, 10)

    def test_flying_ignores_difficult_terrain_cost(self) -> None:
        mover = build_entity("ent_pc", name="Eric", x=2, y=2, speed_walk=30, speed_fly=40)
        encounter = build_encounter(
            mover,
            terrain=[{"x": 3, "y": 2, "type": "difficult_terrain"}],
        )

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 3, "y": 2},
            count_movement=True,
            use_dash=False,
            movement_mode="fly",
        )

        self.assertEqual(result.feet_cost, 5)

    def test_large_creature_checks_full_footprint_for_target(self) -> None:
        mover = build_entity(
            "ent_large",
            name="Ogre",
            x=2,
            y=2,
            side="enemy",
            category="monster",
            controller="gm",
            initiative=8,
            size="large",
        )
        encounter = build_encounter(
            mover,
            terrain=[{"x": 4, "y": 3, "type": "wall"}],
        )

        with self.assertRaisesRegex(ValueError, "blocked_by_wall"):
            validate_movement_path(
                encounter=encounter,
                entity_id=mover.entity_id,
                target_position={"x": 3, "y": 2},
                count_movement=True,
                use_dash=False,
            )

    def test_validate_path_rejects_zero_speed_condition(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
            conditions=["restrained"],
        )
        encounter = build_encounter(mover)

        with self.assertRaisesRegex(ValueError, "movement_blocked_by_condition"):
            validate_movement_path(
                encounter=encounter,
                entity_id=mover.entity_id,
                target_position={"x": 3, "y": 2},
                count_movement=True,
                use_dash=False,
            )

    def test_validate_path_treats_prone_movement_as_crawl(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
            conditions=["prone"],
        )
        encounter = build_encounter(mover)

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 3, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.feet_cost, 10)

    def test_validate_path_prone_doubles_difficult_terrain_cost(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
            conditions=["prone"],
        )
        encounter = build_encounter(
            mover,
            terrain=[{"x": 3, "y": 2, "type": "difficult_terrain"}],
        )

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 3, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.feet_cost, 20)

    def test_validate_path_prone_keeps_diagonal_5_10_pattern_before_doubling(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
            conditions=["prone"],
        )
        encounter = build_encounter(mover)

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 4, "y": 4},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.feet_cost, 30)

    def test_validate_path_prone_diagonal_into_difficult_terrain_uses_both_modifiers(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
            conditions=["prone"],
        )
        encounter = build_encounter(
            mover,
            terrain=[{"x": 3, "y": 3, "type": "difficult_terrain"}],
        )

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 3, "y": 3},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.feet_cost, 20)

    def test_validate_path_ignores_malformed_condition_values(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
        )
        mover.conditions = [None, 123, "frightened:"]
        encounter = build_encounter(mover)

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 3, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.feet_cost, 5)

    def test_validate_path_treats_string_conditions_as_single_condition(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
        )
        mover.conditions = "prone"
        encounter = build_encounter(mover)

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 3, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.feet_cost, 10)

    def test_validate_path_blocks_frightened_source_proximity(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
            conditions=["frightened:ent_enemy_goblin_001"],
        )
        enemy = build_entity(
            "ent_enemy_goblin_001",
            name="Goblin",
            x=5,
            y=2,
            side="enemy",
            category="monster",
            controller="gm",
            initiative=8,
        )
        encounter = build_encounter(mover, enemy)

        with self.assertRaisesRegex(ValueError, "blocked_by_frightened_source"):
            validate_movement_path(
                encounter=encounter,
                entity_id=mover.entity_id,
                target_position={"x": 3, "y": 2},
                count_movement=True,
                use_dash=False,
            )

    def test_validate_path_allows_moving_away_from_frightened_source(self) -> None:
        mover = build_entity(
            "ent_pc",
            name="Eric",
            x=2,
            y=2,
            conditions=["frightened:ent_enemy_goblin_001"],
        )
        enemy = build_entity(
            "ent_enemy_goblin_001",
            name="Goblin",
            x=5,
            y=2,
            side="enemy",
            category="monster",
            controller="gm",
            initiative=8,
        )
        encounter = build_encounter(mover, enemy)

        result = validate_movement_path(
            encounter=encounter,
            entity_id=mover.entity_id,
            target_position={"x": 1, "y": 2},
            count_movement=True,
            use_dash=False,
        )

        self.assertEqual(result.path[-1].anchor, {"x": 1, "y": 2})


if __name__ == "__main__":
    unittest.main()
