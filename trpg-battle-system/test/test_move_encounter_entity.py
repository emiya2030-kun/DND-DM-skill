from __future__ import annotations

"""移动服务测试：覆盖写回位置、移动力和失败不落盘。"""

import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent
from tools.services.encounter.move_encounter_entity import MoveEncounterEntity


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
    speed_remaining: int = 30,
    conditions: list[str] | None = None,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side=side,
        category=category,
        controller=controller,
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": speed_walk, "remaining": speed_remaining},
        initiative=initiative,
        size=size,
        conditions=conditions or [],
    )


def build_service_encounter(
    *,
    terrain: list[dict] | None = None,
    width: int = 12,
    height: int = 12,
) -> Encounter:
    entity = build_entity("ent_ally_eric_001", name="Eric", x=2, y=2, initiative=15)
    return Encounter(
        encounter_id="enc_move_service_test",
        name="Move Service Encounter",
        status="active",
        round=1,
        current_entity_id=entity.entity_id,
        turn_order=[entity.entity_id],
        entities={entity.entity_id: entity},
        map=EncounterMap(
            map_id="map_move_service_test",
            name="Move Service Test Map",
            description="A map used by move encounter entity tests.",
            width=width,
            height=height,
            terrain=[] if terrain is None else terrain,
        ),
    )


class MoveEncounterEntityTests(unittest.TestCase):
    def test_services_package_exports_move_encounter_entity(self) -> None:
        from tools.services import MoveEncounterEntity as ExportedMoveEncounterEntity

        self.assertIs(ExportedMoveEncounterEntity, MoveEncounterEntity)

    def test_move_entity_updates_anchor_and_remaining_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = repo.save(build_service_encounter())

            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 5, "y": 2},
            )

            entity = updated.entities["ent_ally_eric_001"]
            self.assertEqual(entity.position, {"x": 5, "y": 2})
            self.assertEqual(entity.speed["remaining"], 15)
            repo.close()

    def test_move_entity_rejects_non_current_turn_actor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = build_service_encounter()
            ally = build_entity(
                "ent_ally_lia_001",
                name="Lia",
                x=3,
                y=2,
                controller="companion_npc",
                initiative=12,
            )
            encounter.entities[ally.entity_id] = ally
            encounter.turn_order.append(ally.entity_id)
            repo.save(encounter)

            with self.assertRaisesRegex(ValueError, "actor_not_current_turn_entity"):
                service.execute(
                    encounter_id="enc_move_service_test",
                    entity_id=ally.entity_id,
                    target_position={"x": 4, "y": 2},
                )
            repo.close()

    def test_execute_with_state_returns_latest_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = repo.save(build_service_encounter())

            result = service.execute_with_state(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
            )

            self.assertEqual(result["position"], {"x": 4, "y": 2})
            self.assertEqual(result["encounter_state"]["encounter_id"], encounter.encounter_id)
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["position"], "(4, 2)")
            self.assertIn("battlemap_view", result["encounter_state"])
            repo.close()

    def test_move_entity_with_dash_uses_extra_allowance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = repo.save(build_service_encounter())

            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 10, "y": 2},
                use_dash=True,
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 10, "y": 2})
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 0)
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 40)
            repo.close()

    def test_move_entity_short_dash_keeps_remaining_legal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = repo.save(build_service_encounter())

            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 3, "y": 2},
                use_dash=True,
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 25)
            reloaded = repo.get(encounter.encounter_id)
            self.assertEqual(reloaded.entities["ent_ally_eric_001"].speed["remaining"], 25)
            repo.close()

    def test_move_entity_without_counting_movement_keeps_remaining_speed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = repo.save(build_service_encounter())

            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
                count_movement=False,
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 30)
            repo.close()

    def test_illegal_move_does_not_mutate_repository_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            service = MoveEncounterEntity(repo)
            encounter = repo.save(
                build_service_encounter(
                    terrain=[{"x": 4, "y": 2, "type": "wall"}],
                )
            )

            with self.assertRaisesRegex(ValueError, "blocked_by_wall"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 4, "y": 2},
                )

            reloaded = repo.get(encounter.encounter_id)
            self.assertEqual(reloaded.entities["ent_ally_eric_001"].position, {"x": 2, "y": 2})
            self.assertEqual(reloaded.entities["ent_ally_eric_001"].speed["remaining"], 30)
            repo.close()

    def test_move_entity_can_append_movement_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            service = MoveEncounterEntity(encounter_repo, AppendEvent(event_repo))
            encounter = encounter_repo.save(build_service_encounter())

            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            events = event_repo.list_by_encounter(encounter.encounter_id)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "movement_resolved")
            self.assertEqual(events[0].actor_entity_id, "ent_ally_eric_001")
            self.assertEqual(events[0].payload["from_position"], {"x": 2, "y": 2})
            self.assertEqual(events[0].payload["to_position"], {"x": 4, "y": 2})
            self.assertEqual(events[0].payload["feet_cost"], 10)
            encounter_repo.close()
            event_repo.close()

    def test_move_entity_triggers_enter_zone_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_service_encounter()
            encounter.map.zones = [
                {
                    "zone_id": "zone_fire_001",
                    "type": "hazard_area",
                    "name": "火焰灼域",
                    "cells": [[4, 2]],
                    "note": "踏入时会灼伤。",
                    "runtime": {
                        "source_entity_id": "zone_source_fire",
                        "source_name": "火焰灼域",
                        "triggers": [
                            {
                                "timing": "enter",
                                "effect": {
                                    "damage_parts": [{"source": "zone:fire:enter", "formula": "1d4", "type": "fire"}],
                                    "apply_conditions": [],
                                    "remove_conditions": [],
                                },
                            }
                        ],
                    },
                }
            ]
            encounter_repo.save(encounter)

            service = MoveEncounterEntity(encounter_repo, AppendEvent(event_repo))
            with patch(
                "tools.services.encounter.zones.zone_effects.turn_effect_runtime.random.randint",
                return_value=1,
            ):
                updated = service.execute(
                    encounter_id="enc_move_service_test",
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 4, "y": 2},
                )

            self.assertEqual(updated.entities["ent_ally_eric_001"].hp["current"], 19)
            events = event_repo.list_by_encounter("enc_move_service_test")
            self.assertEqual(len(events), 2)
            self.assertEqual(events[1].event_type, "zone_effect_resolved")
            self.assertEqual(events[1].payload["zone_id"], "zone_fire_001")
            self.assertEqual(events[1].payload["trigger"], "enter")
            encounter_repo.close()
            event_repo.close()

    def test_move_entity_zone_can_treat_cells_as_difficult_terrain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            encounter.map.zones = [
                {
                    "zone_id": "zone_frost_001",
                    "type": "hazard_area",
                    "name": "霜雾缓滞",
                    "cells": [[4, 2]],
                    "note": "区域内移动会变慢。",
                    "runtime": {
                        "movement_modifier": {
                            "treat_as_difficult_terrain": True,
                        }
                    },
                }
            ]
            repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id="enc_move_service_test",
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 15)
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 15)
            repo.close()

    def test_move_entity_applies_exhaustion_speed_penalty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.speed["remaining"] = 10
            entity.speed["walk"] = 30
            entity.conditions = ["exhaustion:1"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            with self.assertRaisesRegex(ValueError, "insufficient_movement"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 5, "y": 2},
                )

            repo.close()

    def test_move_entity_applies_exhaustion_speed_penalty_with_dash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter(width=14)
            entity = encounter.entities["ent_ally_eric_001"]
            entity.conditions = ["exhaustion:1"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            with self.assertRaisesRegex(ValueError, "insufficient_movement"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 13, "y": 2},
                    use_dash=True,
                )

            repo.close()

    def test_move_entity_ignores_malformed_condition_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.conditions = ["frightened:"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            repo.close()

    def test_move_entity_ignores_malformed_condition_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.conditions = [None, 123, "frightened:"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            repo.close()

    def test_move_entity_handles_none_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.conditions = None
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            repo.close()

    def test_move_entity_handles_none_combat_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.combat_flags = None
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 10)
            repo.close()

    def test_move_entity_ignores_non_iterable_condition_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.conditions = 123
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            repo.close()

    def test_move_entity_treats_string_conditions_as_single_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.conditions = "prone"
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 3, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 20)
            repo.close()

    def test_move_entity_tracks_exhaustion_limit_across_multiple_moves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.conditions = ["exhaustion:2"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 6, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 0)
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 20)

            with self.assertRaisesRegex(ValueError, "insufficient_movement"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 7, "y": 2},
                )

            repo.close()

    def test_move_entity_applies_exhaustion_after_prior_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.speed["remaining"] = 20
            entity.conditions = ["exhaustion:1"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            with self.assertRaisesRegex(ValueError, "insufficient_movement"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 6, "y": 2},
                )

            repo.close()

    def test_move_entity_applies_exhaustion_dash_limit_after_prior_full_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.speed["remaining"] = 0
            entity.conditions = ["exhaustion:1"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            with self.assertRaisesRegex(ValueError, "insufficient_movement"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 7, "y": 2},
                    use_dash=True,
                )

            repo.close()

    def test_move_entity_can_continue_exhausted_movement_after_small_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.conditions = ["exhaustion:1"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            first = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 3, "y": 2},
            )

            self.assertEqual(first.entities["ent_ally_eric_001"].speed["remaining"], 20)

            second = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 7, "y": 2},
            )

            self.assertEqual(second.entities["ent_ally_eric_001"].speed["remaining"], 0)

            with self.assertRaisesRegex(ValueError, "insufficient_movement"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 8, "y": 2},
                )

            repo.close()

    def test_move_entity_ignores_stale_movement_spent_after_speed_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.combat_flags = {"movement_spent_feet": 25}
            entity.speed["remaining"] = entity.speed["walk"]
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 3, "y": 2},
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 25)
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 5)
            repo.close()

    def test_move_entity_can_use_free_movement_to_cover_insufficient_regular_movement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.speed["remaining"] = 5
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
                free_movement_feet=5,
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 0)
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 30)
            repo.close()

    def test_move_entity_free_movement_only_consumes_cost_above_free_allowance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.speed["remaining"] = 10
            entity.combat_flags = {"movement_spent_feet": 20}
            encounter = repo.save(encounter)

            service = MoveEncounterEntity(repo)
            updated = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
                free_movement_feet=10,
            )

            self.assertEqual(updated.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})
            self.assertEqual(updated.entities["ent_ally_eric_001"].combat_flags["movement_spent_feet"], 20)
            self.assertEqual(updated.entities["ent_ally_eric_001"].speed["remaining"], 10)
            repo.close()

    def test_move_entity_free_movement_only_applies_to_current_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_service_encounter()
            entity = encounter.entities["ent_ally_eric_001"]
            entity.speed["remaining"] = 5
            encounter = repo.save(encounter)
            service = MoveEncounterEntity(repo)

            first = service.execute(
                encounter_id=encounter.encounter_id,
                entity_id="ent_ally_eric_001",
                target_position={"x": 4, "y": 2},
                free_movement_feet=5,
            )
            self.assertEqual(first.entities["ent_ally_eric_001"].position, {"x": 4, "y": 2})

            with self.assertRaisesRegex(ValueError, "insufficient_movement"):
                service.execute(
                    encounter_id=encounter.encounter_id,
                    entity_id="ent_ally_eric_001",
                    target_position={"x": 5, "y": 2},
                )
            repo.close()


if __name__ == "__main__":
    unittest.main()
