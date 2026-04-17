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
from tools.services.combat.actions.help_effects import find_help_ability_check_effect
from tools.services.combat.actions.use_help_ability_check import UseHelpAbilityCheck


def build_actor() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_actor_001",
        name="Miren",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 16, "max": 16, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
    )


def build_ally(*, side: str = "ally") -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_001",
        name="Eric",
        side=side,
        category="pc",
        controller="player",
        position={"x": 3, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        turn_effects=[],
    )


def build_encounter(
    *,
    action_used: bool = False,
    current_entity_id: str = "ent_actor_001",
    ally_side: str = "ally",
) -> Encounter:
    actor = build_actor()
    actor.action_economy["action_used"] = action_used
    ally = build_ally(side=ally_side)
    return Encounter(
        encounter_id="enc_help_check_test",
        name="Help Check Test",
        status="active",
        round=1,
        current_entity_id=current_entity_id,
        turn_order=[actor.entity_id, ally.entity_id],
        entities={actor.entity_id: actor, ally.entity_id: ally},
        map=EncounterMap(map_id="map_help_check_test", name="Map", description="Test", width=8, height=8),
    )


class HelpAbilityEffectHelpersTests(unittest.TestCase):
    def test_find_help_ability_effect_matches_check_type_and_key(self) -> None:
        actor = build_actor()
        actor.turn_effects = [
            {
                "effect_id": "help_check_1",
                "effect_type": "help_ability_check",
                "remaining_uses": 1,
                "help_check": {"check_type": "skill", "check_key": "investigation"},
            }
        ]

        effect = find_help_ability_check_effect(
            actor=actor,
            check_type="skill",
            check_key="investigation",
        )

        self.assertIsNotNone(effect)
        self.assertEqual(effect["effect_id"], "help_check_1")


class UseHelpAbilityCheckTests(unittest.TestCase):
    def test_execute_consumes_action_and_adds_help_check_effect_to_ally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            result = UseHelpAbilityCheck(repo).execute(
                encounter_id="enc_help_check_test",
                actor_id="ent_actor_001",
                ally_id="ent_ally_001",
                check_type="skill",
                check_key="investigation",
            )

            updated = repo.get("enc_help_check_test")
            self.assertIsNotNone(updated)
            ally = updated.entities["ent_ally_001"]
            self.assertTrue(any(effect.get("effect_type") == "help_ability_check" for effect in ally.turn_effects))
            self.assertEqual(result["ally_id"], "ent_ally_001")
            repo.close()

    def test_execute_rejects_when_ally_is_enemy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(ally_side="enemy"))

            with self.assertRaisesRegex(ValueError, "help_check_target_must_be_ally"):
                UseHelpAbilityCheck(repo).execute(
                    encounter_id="enc_help_check_test",
                    actor_id="ent_actor_001",
                    ally_id="ent_ally_001",
                    check_type="skill",
                    check_key="investigation",
                )
            repo.close()

    def test_execute_rejects_invalid_check_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            with self.assertRaisesRegex(ValueError, "invalid_help_check_type"):
                UseHelpAbilityCheck(repo).execute(
                    encounter_id="enc_help_check_test",
                    actor_id="ent_actor_001",
                    ally_id="ent_ally_001",
                    check_type="ability",
                    check_key="str",
                )
            repo.close()


if __name__ == "__main__":
    unittest.main()
