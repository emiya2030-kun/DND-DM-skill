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
from tools.services import AppendEvent, AttackRollRequest, AttackRollResult, ExecuteAttack, UpdateHp


def build_attacker() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_orc_001",
        name="Orc",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        ability_mods={"str": 3, "dex": 1},
        proficiency_bonus=2,
        weapons=[
            {
                "weapon_id": "spear",
                "name": "Spear",
                "attack_bonus": 5,
                "damage": [{"formula": "1d6+3", "type": "piercing"}],
                "properties": ["thrown"],
                "range": {"normal": 5, "long": 20},
            }
        ],
    )


def build_target(*, with_shield: bool) -> EncounterEntity:
    spells = [{"spell_id": "shield", "name": "Shield", "level": 1}] if with_shield else []
    resources = {"spell_slots": {"1": {"max": 1, "remaining": 1}}} if with_shield else {}
    action_economy = {"reaction_used": False} if with_shield else {"reaction_used": False}
    return EncounterEntity(
        entity_id="ent_ally_wizard_001",
        name="Wizard",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 3, "y": 2},
        hp={"current": 16, "max": 16, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        spells=spells,
        resources=resources,
        action_economy=action_economy,
    )


def build_encounter(*, with_shield: bool) -> Encounter:
    attacker = build_attacker()
    target = build_target(with_shield=with_shield)
    return Encounter(
        encounter_id="enc_attack_reaction_test",
        name="Attack Reaction Test",
        status="active",
        round=1,
        current_entity_id=attacker.entity_id,
        turn_order=[attacker.entity_id, target.entity_id],
        entities={attacker.entity_id: attacker, target.entity_id: target},
        map=EncounterMap(
            map_id="map_attack_reaction_test",
            name="Attack Reaction Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class AttackReactionWindowTests(unittest.TestCase):
    def test_execute_attack_returns_normal_result_when_no_shield_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(with_shield=False))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_attack_reaction_test",
                actor_id="ent_enemy_orc_001",
                target_id="ent_ally_wizard_001",
                weapon_id="spear",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
            )

            self.assertIn("request", result)
            self.assertIn("resolution", result)
            self.assertNotIn("status", result)
            encounter_repo.close()
            event_repo.close()

    def test_execute_attack_returns_waiting_reaction_when_target_can_cast_shield(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(with_shield=True))

            append_event = AppendEvent(event_repo)
            service = ExecuteAttack(
                AttackRollRequest(encounter_repo),
                AttackRollResult(
                    encounter_repo,
                    append_event,
                    UpdateHp(encounter_repo, append_event),
                ),
            )

            result = service.execute(
                encounter_id="enc_attack_reaction_test",
                actor_id="ent_enemy_orc_001",
                target_id="ent_ally_wizard_001",
                weapon_id="spear",
                final_total=17,
                dice_rolls={"base_rolls": [12], "modifier": 5},
            )

            self.assertEqual(result["status"], "waiting_reaction")
            self.assertEqual(result["pending_reaction_window"]["trigger_type"], "attack_declared")
            options = result["pending_reaction_window"]["choice_groups"][0]["options"]
            self.assertEqual(options[0]["reaction_type"], "shield")
            self.assertIn("encounter_state", result)
            encounter_repo.close()
            event_repo.close()
