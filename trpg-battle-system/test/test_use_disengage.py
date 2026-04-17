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
from tools.services.combat.actions.state_effects import (
    add_or_replace_turn_effect,
    clear_turn_effect_type,
    has_disengage_effect,
)
from tools.services.combat.actions.use_disengage import UseDisengage


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
        encounter_id="enc_disengage_test",
        name="Disengage Test",
        status="active",
        round=1,
        current_entity_id=current_entity_id,
        turn_order=[actor.entity_id, other.entity_id],
        entities={actor.entity_id: actor, other.entity_id: other},
        map=EncounterMap(map_id="map_disengage_test", name="Map", description="Test", width=8, height=8),
    )


class DisengageStateEffectsTests(unittest.TestCase):
    def test_add_or_replace_turn_effect_replaces_same_type(self) -> None:
        actor = build_actor()
        actor.turn_effects = [{"effect_id": "old", "effect_type": "disengage", "name": "Disengage"}]

        add_or_replace_turn_effect(
            actor,
            {"effect_id": "new", "effect_type": "disengage", "name": "Disengage"},
        )

        self.assertEqual(len(actor.turn_effects), 1)
        self.assertEqual(actor.turn_effects[0]["effect_id"], "new")

    def test_clear_turn_effect_type_removes_matching_effects_only(self) -> None:
        actor = build_actor()
        actor.turn_effects = [
            {"effect_id": "a", "effect_type": "disengage"},
            {"effect_id": "b", "effect_type": "dodge"},
        ]

        clear_turn_effect_type(actor, "disengage")

        self.assertEqual(actor.turn_effects, [{"effect_id": "b", "effect_type": "dodge"}])

    def test_has_disengage_effect_detects_active_effect(self) -> None:
        actor = build_actor()
        actor.turn_effects = [{"effect_id": "a", "effect_type": "disengage"}]

        self.assertTrue(has_disengage_effect(actor))


class UseDisengageTests(unittest.TestCase):
    def test_execute_consumes_action_and_applies_disengage_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            result = UseDisengage(repo).execute(encounter_id="enc_disengage_test", actor_id="ent_actor_001")

            updated = repo.get("enc_disengage_test")
            self.assertIsNotNone(updated)
            self.assertTrue(updated.entities["ent_actor_001"].action_economy["action_used"])
            self.assertTrue(
                any(effect.get("effect_type") == "disengage" for effect in updated.entities["ent_actor_001"].turn_effects)
            )
            self.assertEqual(result["encounter_id"], "enc_disengage_test")
            repo.close()

    def test_execute_rejects_when_action_already_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(action_used=True))

            with self.assertRaisesRegex(ValueError, "action_already_used"):
                UseDisengage(repo).execute(encounter_id="enc_disengage_test", actor_id="ent_actor_001")
            repo.close()

    def test_execute_rejects_when_not_actor_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(current_entity_id="ent_other_001"))

            with self.assertRaisesRegex(ValueError, "not_actor_turn"):
                UseDisengage(repo).execute(encounter_id="enc_disengage_test", actor_id="ent_actor_001")
            repo.close()
