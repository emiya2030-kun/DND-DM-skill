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
from tools.services.combat.grapple.shared import (
    extract_grapple_source_id,
    resolve_grapple_save_dc,
)
from tools.services.combat.grapple.use_grapple import UseGrapple


def build_grappler(
    *,
    str_mod: int = 3,
    dex_mod: int = 1,
    proficiency_bonus: int = 2,
    class_features: dict | None = None,
) -> EncounterEntity:
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
        initiative=14,
        ability_mods={"str": str_mod, "dex": dex_mod},
        proficiency_bonus=proficiency_bonus,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        combat_flags={},
        class_features=class_features or {},
    )


def build_target(
    *,
    conditions: list[str] | None = None,
    position: tuple[int, int] = (3, 2),
    side: str = "enemy",
    size: str = "medium",
    str_mod: int = 0,
    dex_mod: int = 0,
    save_proficiencies: list[str] | None = None,
    proficiency_bonus: int = 2,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_001",
        name="Raider",
        side=side,
        category="monster",
        controller="gm",
        position={"x": position[0], "y": position[1]},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        size=size,
        ability_mods={"str": str_mod, "dex": dex_mod},
        proficiency_bonus=proficiency_bonus,
        save_proficiencies=save_proficiencies or [],
        conditions=conditions or [],
    )


def build_grapple_encounter(
    *,
    target_position: tuple[int, int] = (3, 2),
    target_side: str = "enemy",
    target_size: str = "medium",
    target_str_mod: int = 0,
    target_dex_mod: int = 0,
    target_save_proficiencies: list[str] | None = None,
) -> Encounter:
    actor = build_grappler()
    target = build_target(
        position=target_position,
        side=target_side,
        size=target_size,
        str_mod=target_str_mod,
        dex_mod=target_dex_mod,
        save_proficiencies=target_save_proficiencies,
    )
    return Encounter(
        encounter_id="enc_grapple_test",
        name="Grapple Test",
        status="active",
        round=1,
        current_entity_id=actor.entity_id,
        turn_order=[actor.entity_id, target.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(map_id="map_grapple_test", name="Map", description="Test", width=8, height=8),
    )


class GrappleSharedTests(unittest.TestCase):
    def test_resolve_grapple_save_dc_defaults_to_strength(self) -> None:
        actor = build_grappler(str_mod=3, dex_mod=1, proficiency_bonus=2)

        result = resolve_grapple_save_dc(actor)

        self.assertEqual(result["dc"], 13)
        self.assertEqual(result["ability_used"], "str")

    def test_resolve_grapple_save_dc_uses_dex_for_monk_martial_arts(self) -> None:
        actor = build_grappler(
            str_mod=1,
            dex_mod=4,
            proficiency_bonus=2,
            class_features={"monk": {"level": 1, "martial_arts": {"grapple_dc_ability": "dex"}}},
        )

        result = resolve_grapple_save_dc(actor)

        self.assertEqual(result["dc"], 14)
        self.assertEqual(result["ability_used"], "dex")

    def test_extract_grapple_source_from_target_condition(self) -> None:
        target = build_target(conditions=["grappled:ent_actor_001"])

        self.assertEqual(extract_grapple_source_id(target), "ent_actor_001")


class UseGrappleTests(unittest.TestCase):
    def test_execute_consumes_action_and_applies_grappled_condition_and_active_grapple(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_grapple_encounter())

            result = UseGrapple(repo).execute(
                encounter_id="enc_grapple_test",
                actor_id="ent_actor_001",
                target_id="ent_target_001",
            )

            updated = repo.get("enc_grapple_test")
            self.assertIsNotNone(updated)
            actor = updated.entities["ent_actor_001"]
            target = updated.entities["ent_target_001"]
            self.assertTrue(actor.action_economy["action_used"])
            self.assertIn("grappled:ent_actor_001", target.conditions)
            self.assertEqual(actor.combat_flags["active_grapple"]["target_entity_id"], "ent_target_001")
            self.assertEqual(result["result"]["status"], "grappled")
            repo.close()

    def test_execute_rejects_when_target_out_of_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_grapple_encounter(target_position=(5, 5)))

            with self.assertRaisesRegex(ValueError, "grapple_target_out_of_range"):
                UseGrapple(repo).execute(
                    encounter_id="enc_grapple_test",
                    actor_id="ent_actor_001",
                    target_id="ent_target_001",
                )
            repo.close()

    def test_execute_rejects_when_actor_already_has_active_grapple(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_grapple_encounter()
            encounter.entities["ent_actor_001"].combat_flags["active_grapple"] = {"target_entity_id": "ent_other_001"}
            repo.save(encounter)

            with self.assertRaisesRegex(ValueError, "grapple_already_active"):
                UseGrapple(repo).execute(
                    encounter_id="enc_grapple_test",
                    actor_id="ent_actor_001",
                    target_id="ent_target_001",
                )
            repo.close()


if __name__ == "__main__":
    unittest.main()
