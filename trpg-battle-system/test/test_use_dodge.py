from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.combat.actions.state_effects import has_dodge_effect
from tools.services.combat.actions.use_dodge import UseDodge


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_actor_001",
        name="Sabur",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
    )


def build_encounter(*, action_used: bool = False, current_entity_id: str = "ent_actor_001") -> Encounter:
    actor = build_actor()
    actor.action_economy["action_used"] = action_used
    other = EncounterEntity(
        entity_id="ent_other_001",
        name="Other",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 3, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
    )
    return Encounter(
        encounter_id="enc_dodge_test",
        name="Dodge Test",
        status="active",
        round=1,
        current_entity_id=current_entity_id,
        turn_order=[actor.entity_id, other.entity_id],
        entities={actor.entity_id: actor, other.entity_id: other},
        map=EncounterMap(map_id="map_dodge_test", name="Map", description="Test", width=8, height=8),
    )


class UseDodgeTests(unittest.TestCase):
    def test_execute_consumes_action_and_applies_dodge_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            result = UseDodge(repo).execute(encounter_id="enc_dodge_test", actor_id="ent_actor_001")

            updated = repo.get("enc_dodge_test")
            self.assertIsNotNone(updated)
            self.assertTrue(updated.entities["ent_actor_001"].action_economy["action_used"])
            self.assertTrue(has_dodge_effect(updated.entities["ent_actor_001"]))
            self.assertEqual(result["encounter_id"], "enc_dodge_test")
            repo.close()

    def test_execute_rejects_when_action_already_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(action_used=True))

            with self.assertRaisesRegex(ValueError, "action_already_used"):
                UseDodge(repo).execute(encounter_id="enc_dodge_test", actor_id="ent_actor_001")
            repo.close()

    def test_execute_rejects_when_not_actor_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(current_entity_id="ent_other_001"))

            with self.assertRaisesRegex(ValueError, "not_actor_turn"):
                UseDodge(repo).execute(encounter_id="enc_dodge_test", actor_id="ent_actor_001")
            repo.close()
