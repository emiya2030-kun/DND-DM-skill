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
from tools.services import EndTurn, StartTurn, UseNaturesVeil


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
        proficiency_bonus=5,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        class_features={"ranger": {"level": 14}},
    )


def build_other() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_other_001",
        name="Other",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 4, "y": 2},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_encounter() -> Encounter:
    actor = build_actor()
    other = build_other()
    return Encounter(
        encounter_id="enc_use_natures_veil_test",
        name="Use Nature's Veil Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, other.entity_id],
        entities={actor.entity_id: actor, other.entity_id: other},
        map=EncounterMap(
            map_id="map_use_natures_veil_test",
            name="Use Nature's Veil Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class UseNaturesVeilTests(unittest.TestCase):
    def test_execute_applies_invisible_until_next_turn_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            UseNaturesVeil(repo).execute(
                encounter_id="enc_use_natures_veil_test",
                actor_id="ent_ranger_001",
            )

            after_use = repo.get("enc_use_natures_veil_test")
            self.assertIsNotNone(after_use)
            self.assertIn("invisible", after_use.entities["ent_ranger_001"].conditions)
            self.assertEqual(
                after_use.entities["ent_ranger_001"].class_features["ranger"]["natures_veil"]["uses_remaining"],
                2,
            )

            EndTurn(repo).execute("enc_use_natures_veil_test")
            StartTurn(repo).execute("enc_use_natures_veil_test")
            EndTurn(repo).execute("enc_use_natures_veil_test")
            StartTurn(repo).execute("enc_use_natures_veil_test")
            EndTurn(repo).execute("enc_use_natures_veil_test")

            updated = repo.get("enc_use_natures_veil_test")
            self.assertIsNotNone(updated)
            self.assertNotIn("invisible", updated.entities["ent_ranger_001"].conditions)
            repo.close()
