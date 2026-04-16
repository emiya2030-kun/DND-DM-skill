"""先攻开战入口测试：覆盖排序、隐藏 tie-break 字段与首回合开始。"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.encounter.roll_initiative_and_start_encounter import RollInitiativeAndStartEncounter


def build_entity(
    entity_id: str,
    *,
    name: str,
    x: int,
    y: int,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=name,
        side="ally" if entity_id == "ent_a" else "enemy",
        category="pc" if entity_id == "ent_a" else "monster",
        controller="player" if entity_id == "ent_a" else "gm",
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=0,
        size="medium",
    )


class RollInitiativeAndStartEncounterTests(unittest.TestCase):
    def test_rolls_initiative_sorts_turn_order_and_starts_first_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            entity_a = build_entity("ent_a", name="米伦", x=2, y=2)
            entity_a.ability_mods = {"dex": 3}
            entity_a.action_economy = {"action_used": True}
            entity_a.speed["remaining"] = 0

            entity_b = build_entity("ent_b", name="萨布尔", x=4, y=2)
            entity_b.ability_mods = {"dex": 1}

            encounter = Encounter(
                encounter_id="enc_initiative_test",
                name="Initiative Test",
                status="active",
                round=1,
                current_entity_id=None,
                turn_order=[],
                entities={"ent_a": entity_a, "ent_b": entity_b},
                map=EncounterMap(
                    map_id="map_init",
                    name="Map",
                    description="Map",
                    width=10,
                    height=10,
                ),
            )
            repo.save(encounter)

            with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", side_effect=[12, 12]):
                with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", side_effect=[0.25, 0.10]):
                    result = RollInitiativeAndStartEncounter(repo).execute_with_state("enc_initiative_test")

            self.assertEqual(result["turn_order"], ["ent_a", "ent_b"])
            self.assertEqual(result["current_entity_id"], "ent_a")
            self.assertFalse(result["encounter_state"]["current_turn_entity"]["actions"]["action_used"])
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["movement_remaining"], "30 feet")
            repo.close()

    def test_initiative_results_hide_internal_decimal_from_public_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            entity = build_entity("ent_a", name="米伦", x=2, y=2)
            entity.ability_mods = {"dex": 2}
            encounter = Encounter(
                encounter_id="enc_initiative_hidden_decimal",
                name="Hidden Decimal Test",
                status="active",
                round=1,
                current_entity_id=None,
                turn_order=[],
                entities={"ent_a": entity},
                map=EncounterMap(
                    map_id="map_init",
                    name="Map",
                    description="Map",
                    width=10,
                    height=10,
                ),
            )
            repo.save(encounter)

            with patch("tools.services.encounter.roll_initiative_and_start_encounter.randint", return_value=11):
                with patch("tools.services.encounter.roll_initiative_and_start_encounter.random", return_value=0.42):
                    result = RollInitiativeAndStartEncounter(repo).execute_with_state("enc_initiative_hidden_decimal")

            self.assertEqual(result["initiative_results"][0]["initiative_roll"], 11)
            self.assertEqual(result["initiative_results"][0]["initiative_modifier"], 2)
            self.assertEqual(result["initiative_results"][0]["initiative_total"], 13)
            self.assertNotIn("initiative_tiebreak_decimal", result["initiative_results"][0])
            repo.close()


if __name__ == "__main__":
    unittest.main()
