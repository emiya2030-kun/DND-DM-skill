from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, ResolveForcedMovement


def build_entity(
    entity_id: str,
    *,
    name: str,
    x: int,
    y: int,
    side: str,
    controller: str,
    initiative: int,
    size: str = "medium",
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side=side,
        category="pc" if side == "ally" else "monster",
        controller=controller,
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=initiative,
        size=size,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        combat_flags={"is_active": True, "is_defeated": False},
    )


def build_forced_movement_encounter(*, terrain: list[dict] | None = None) -> Encounter:
    actor = build_entity(
        "ent_ally_001",
        name="Eric",
        x=2,
        y=2,
        side="ally",
        controller="player",
        initiative=15,
    )
    target = build_entity(
        "ent_enemy_001",
        name="Orc",
        x=3,
        y=2,
        side="enemy",
        controller="gm",
        initiative=10,
    )
    return Encounter(
        encounter_id="enc_forced_move",
        name="Forced Move Encounter",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, target.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(
            map_id="map_forced_move",
            name="Forced Move Map",
            description="A small combat room.",
            width=12,
            height=12,
            terrain=[] if terrain is None else terrain,
        ),
    )


class ResolveForcedMovementTests(unittest.TestCase):
    def test_services_package_exports_resolve_forced_movement(self) -> None:
        from tools.services import ResolveForcedMovement as ExportedResolveForcedMovement

        self.assertIs(ExportedResolveForcedMovement, ResolveForcedMovement)

    def test_forced_movement_stops_at_last_legal_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(
                build_forced_movement_encounter(
                    terrain=[{"x": 5, "y": 2, "type": "wall"}],
                )
            )

            service = ResolveForcedMovement(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_forced_move",
                entity_id="ent_enemy_001",
                path=[{"x": 4, "y": 2}, {"x": 5, "y": 2}],
                reason="weapon_mastery_push",
                source_entity_id="ent_ally_001",
            )

            updated = encounter_repo.get("enc_forced_move")
            assert updated is not None
            self.assertEqual(result["start_position"], {"x": 3, "y": 2})
            self.assertEqual(result["final_position"], {"x": 4, "y": 2})
            self.assertEqual(result["resolved_path"], [{"x": 4, "y": 2}])
            self.assertEqual(result["moved_feet"], 5)
            self.assertTrue(result["blocked"])
            self.assertEqual(result["block_reason"], "wall")
            self.assertEqual(updated.entities["ent_enemy_001"].position, {"x": 4, "y": 2})
            events = event_repo.list_by_encounter("enc_forced_move")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0].event_type, "forced_movement_resolved")
            encounter_repo.close()
            event_repo.close()

    def test_forced_movement_does_not_spend_speed_or_create_reactions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter_repo.save(build_forced_movement_encounter())

            service = ResolveForcedMovement(encounter_repo)
            result = service.execute(
                encounter_id="enc_forced_move",
                entity_id="ent_enemy_001",
                path=[{"x": 4, "y": 2}, {"x": 5, "y": 2}],
                reason="weapon_mastery_push",
                source_entity_id="ent_ally_001",
            )

            updated = encounter_repo.get("enc_forced_move")
            assert updated is not None
            target = updated.entities["ent_enemy_001"]
            self.assertEqual(result["final_position"], {"x": 5, "y": 2})
            self.assertEqual(target.speed["remaining"], 30)
            self.assertNotIn("movement_spent_feet", target.combat_flags)
            self.assertEqual(updated.reaction_requests, [])
            self.assertIsNone(updated.pending_movement)
            encounter_repo.close()


if __name__ == "__main__":
    unittest.main()
