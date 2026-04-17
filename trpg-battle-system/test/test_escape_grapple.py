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
from tools.services.combat.grapple.escape_grapple import EscapeGrapple


def build_grappler(*, escape_dc: int = 12) -> EncounterEntity:
    grappler = EncounterEntity(
        entity_id="ent_actor_001",
        name="Raider",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        combat_flags={},
    )
    grappler.combat_flags["active_grapple"] = {
        "target_entity_id": "ent_target_001",
        "escape_dc": escape_dc,
        "dc_ability_used": "str",
        "movement_speed_halved": True,
        "source_condition": "grappled:ent_actor_001",
    }
    return grappler


def build_target(*, skill_modifiers: dict[str, int] | None = None) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_001",
        name="Sabur",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 3, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 0},
        initiative=12,
        conditions=["grappled:ent_actor_001"],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        skill_modifiers=skill_modifiers or {},
        ability_mods={"str": 0, "dex": 0},
    )


def build_escape_encounter(
    *,
    grapple_escape_dc: int = 12,
    actor_skill_modifiers: dict[str, int] | None = None,
) -> Encounter:
    grappler = build_grappler(escape_dc=grapple_escape_dc)
    actor = build_target(skill_modifiers=actor_skill_modifiers)
    return Encounter(
        encounter_id="enc_escape_test",
        name="Escape Grapple Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, grappler.entity_id],
        entities={actor.entity_id: actor, grappler.entity_id: grappler},
        map=EncounterMap(map_id="map_escape_test", name="Map", description="Test", width=8, height=8),
    )


class EscapeGrappleTests(unittest.TestCase):
    def test_execute_removes_grapple_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(
                build_escape_encounter(
                    grapple_escape_dc=12,
                    actor_skill_modifiers={"athletics": 12, "acrobatics": 2},
                )
            )

            result = EscapeGrapple(repo).execute(
                encounter_id="enc_escape_test",
                actor_id="ent_target_001",
            )

            updated = repo.get("enc_escape_test")
            self.assertIsNotNone(updated)
            actor = updated.entities["ent_target_001"]
            grappler = updated.entities["ent_actor_001"]
            self.assertNotIn("grappled:ent_actor_001", actor.conditions)
            self.assertNotIn("active_grapple", grappler.combat_flags)
            self.assertEqual(result["result"]["status"], "escaped")
            repo.close()

    def test_execute_keeps_grapple_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_escape_encounter(grapple_escape_dc=20, actor_skill_modifiers={"athletics": 1, "acrobatics": 1}))

            result = EscapeGrapple(repo).execute(
                encounter_id="enc_escape_test",
                actor_id="ent_target_001",
            )

            updated = repo.get("enc_escape_test")
            self.assertIsNotNone(updated)
            self.assertIn("grappled:ent_actor_001", updated.entities["ent_target_001"].conditions)
            self.assertEqual(result["result"]["status"], "still_grappled")
            repo.close()


if __name__ == "__main__":
    unittest.main()
