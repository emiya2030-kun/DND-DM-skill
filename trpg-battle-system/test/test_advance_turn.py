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
from tools.services.encounter.turns import AdvanceTurn


def build_entity(
    entity_id: str,
    *,
    name: str,
    initiative: int,
    speed_walk: int = 30,
    speed_remaining: int = 30,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": speed_walk, "remaining": speed_remaining},
        initiative=initiative,
    )


def build_encounter() -> Encounter:
    entity_a = build_entity("ent_ally_eric_001", name="Eric", initiative=15)
    entity_b = build_entity("ent_ally_lia_001", name="Lia", initiative=12)
    entity_b.action_economy = {
        "action_used": True,
        "bonus_action_used": True,
        "reaction_used": True,
        "free_interaction_used": True,
    }
    entity_b.speed["remaining"] = 0
    entity_b.combat_flags["movement_spent_feet"] = 30
    return Encounter(
        encounter_id="enc_advance_turn_test",
        name="Advance Turn Test",
        status="active",
        round=1,
        current_entity_id=entity_a.entity_id,
        turn_order=[entity_a.entity_id, entity_b.entity_id],
        entities={entity_a.entity_id: entity_a, entity_b.entity_id: entity_b},
        map=EncounterMap(
            map_id="map_advance_turn_test",
            name="Advance Turn Test Map",
            description="A map used by advance turn tests.",
            width=10,
            height=10,
        ),
    )


class AdvanceTurnTests(unittest.TestCase):
    def test_execute_returns_updated_encounter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            updated = AdvanceTurn(repo).execute("enc_advance_turn_test")

            self.assertEqual(updated.current_entity_id, "ent_ally_lia_001")
            self.assertEqual(updated.entities["ent_ally_lia_001"].speed["remaining"], 0)
            self.assertTrue(updated.entities["ent_ally_lia_001"].action_economy["action_used"])
            repo.close()

    def test_execute_with_state_returns_latest_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            result = AdvanceTurn(repo).execute_with_state("enc_advance_turn_test")

            self.assertEqual(result["encounter_id"], "enc_advance_turn_test")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["id"], "ent_ally_lia_001")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["movement_remaining"], "0 feet")
            self.assertTrue(result["encounter_state"]["current_turn_entity"]["actions"]["action_used"])
            repo.close()


if __name__ == "__main__":
    unittest.main()
