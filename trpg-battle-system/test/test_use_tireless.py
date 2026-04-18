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
from tools.services import AppendEvent, UseTireless


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ranger_001",
        name="Ranger",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_mods={"wis": 3},
        proficiency_bonus=4,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={"ranger": {"level": 10}},
    )


def build_encounter() -> Encounter:
    actor = build_actor()
    return Encounter(
        encounter_id="enc_use_tireless_test",
        name="Use Tireless Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id],
        entities={actor.entity_id: actor},
        map=EncounterMap(
            map_id="map_use_tireless_test",
            name="Use Tireless Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class UseTirelessTests(unittest.TestCase):
    def test_execute_grants_temp_hp_and_consumes_use(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            repo.save(build_encounter())

            result = UseTireless(repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_use_tireless_test",
                actor_id="ent_ranger_001",
                temp_hp_roll={"rolls": [5]},
            )

            updated = repo.get("enc_use_tireless_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_ranger_001"].hp["temp"], 8)
            self.assertEqual(
                updated.entities["ent_ranger_001"].class_features["ranger"]["tireless"]["temp_hp_uses_remaining"],
                2,
            )
            self.assertEqual(result["class_feature_result"]["tireless"]["temp_hp_gained"], 8)
            repo.close()
            event_repo.close()

    def test_execute_keeps_higher_existing_temp_hp_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_ranger_001"].hp["temp"] = 10
            repo.save(encounter)

            result = UseTireless(repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_use_tireless_test",
                actor_id="ent_ranger_001",
                temp_hp_roll={"rolls": [5]},
            )

            updated = repo.get("enc_use_tireless_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_ranger_001"].hp["temp"], 10)
            self.assertEqual(result["class_feature_result"]["tireless"]["temp_hp_after"], 10)
            repo.close()
            event_repo.close()
