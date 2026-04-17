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
from tools.services.combat.actions.help_effects import (
    find_help_attack_effect,
    remove_turn_effect_by_id,
)
from tools.services.combat.actions.use_help_attack import UseHelpAttack


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


def build_enemy(*, side: str = "enemy", position: tuple[int, int] = (3, 2)) -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_001",
        name="Raider",
        side=side,
        category="monster",
        controller="gm",
        position={"x": position[0], "y": position[1]},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        turn_effects=[],
    )


def build_encounter(
    *,
    action_used: bool = False,
    current_entity_id: str = "ent_actor_001",
    target_side: str = "enemy",
    target_position: tuple[int, int] = (3, 2),
) -> Encounter:
    actor = build_actor()
    actor.action_economy["action_used"] = action_used
    target = build_enemy(side=target_side, position=target_position)
    return Encounter(
        encounter_id="enc_help_attack_test",
        name="Help Attack Test",
        status="active",
        round=1,
        current_entity_id=current_entity_id,
        turn_order=[actor.entity_id, target.entity_id],
        entities={actor.entity_id: actor, target.entity_id: target},
        map=EncounterMap(map_id="map_help_attack_test", name="Map", description="Test", width=8, height=8),
    )


class HelpEffectHelpersTests(unittest.TestCase):
    def test_find_help_attack_effect_for_actor_and_target(self) -> None:
        actor = build_actor()
        target = build_enemy()
        target.turn_effects = [
            {
                "effect_id": "help_attack_1",
                "effect_type": "help_attack",
                "source_entity_id": "ent_helper_001",
                "source_side": "ally",
                "remaining_uses": 1,
            }
        ]

        effect = find_help_attack_effect(target=target, attacker=actor)

        self.assertIsNotNone(effect)
        self.assertEqual(effect["effect_id"], "help_attack_1")

    def test_remove_turn_effect_by_id_only_removes_matching_effect(self) -> None:
        actor = build_actor()
        actor.turn_effects = [
            {"effect_id": "keep", "effect_type": "dodge"},
            {"effect_id": "drop", "effect_type": "help_attack"},
        ]

        remove_turn_effect_by_id(actor, "drop")

        self.assertEqual(actor.turn_effects, [{"effect_id": "keep", "effect_type": "dodge"}])


class UseHelpAttackTests(unittest.TestCase):
    def test_execute_consumes_action_and_adds_help_attack_effect_to_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            result = UseHelpAttack(repo).execute(
                encounter_id="enc_help_attack_test",
                actor_id="ent_actor_001",
                target_id="ent_enemy_001",
            )

            updated = repo.get("enc_help_attack_test")
            self.assertIsNotNone(updated)
            actor = updated.entities["ent_actor_001"]
            target = updated.entities["ent_enemy_001"]
            self.assertTrue(actor.action_economy["action_used"])
            self.assertTrue(any(effect.get("effect_type") == "help_attack" for effect in target.turn_effects))
            self.assertEqual(result["actor_id"], "ent_actor_001")
            repo.close()

    def test_execute_rejects_when_target_not_within_five_feet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(target_position=(5, 5)))

            with self.assertRaisesRegex(ValueError, "target_not_within_help_attack_range"):
                UseHelpAttack(repo).execute(
                    encounter_id="enc_help_attack_test",
                    actor_id="ent_actor_001",
                    target_id="ent_enemy_001",
                )
            repo.close()

    def test_execute_rejects_when_target_is_not_enemy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter(target_side="ally"))

            with self.assertRaisesRegex(ValueError, "help_attack_target_must_be_enemy"):
                UseHelpAttack(repo).execute(
                    encounter_id="enc_help_attack_test",
                    actor_id="ent_actor_001",
                    target_id="ent_enemy_001",
                )
            repo.close()


if __name__ == "__main__":
    unittest.main()
