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


def build_attacker(*, damage_type: str = "piercing") -> EncounterEntity:
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
                "damage": [{"formula": "1d6+3", "type": damage_type}],
                "properties": ["thrown"],
                "range": {"normal": 5, "long": 20},
            }
        ],
    )


def build_target(
    *,
    with_shield: bool,
    with_deflect_attacks: bool = False,
    monk_level: int = 5,
    with_deflect_energy: bool = False,
    with_uncanny_dodge: bool = False,
    rogue_level: int = 5,
) -> EncounterEntity:
    spells = [{"spell_id": "shield", "name": "Shield", "level": 1}] if with_shield else []
    resources = {"spell_slots": {"1": {"max": 1, "remaining": 1}}} if with_shield else {}
    action_economy = {"reaction_used": False} if with_shield else {"reaction_used": False}
    target = EncounterEntity(
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
    if with_deflect_attacks:
        target.class_features = {
            "monk": {
                "level": monk_level,
                "deflect_attacks": {"enabled": True},
                "deflect_energy": {"enabled": with_deflect_energy},
                "focus_points": {"max": 5, "remaining": 3},
            }
        }
    if with_uncanny_dodge:
        class_features = target.class_features if isinstance(target.class_features, dict) else {}
        class_features["rogue"] = {"level": rogue_level}
        target.class_features = class_features
    return target


def build_encounter(
    *,
    with_shield: bool,
    with_deflect_attacks: bool = False,
    damage_type: str = "piercing",
    monk_level: int = 5,
    with_deflect_energy: bool = False,
    with_uncanny_dodge: bool = False,
    rogue_level: int = 5,
) -> Encounter:
    attacker = build_attacker(damage_type=damage_type)
    target = build_target(
        with_shield=with_shield,
        with_deflect_attacks=with_deflect_attacks,
        monk_level=monk_level,
        with_deflect_energy=with_deflect_energy,
        with_uncanny_dodge=with_uncanny_dodge,
        rogue_level=rogue_level,
    )
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
    def test_execute_attack_does_not_open_shield_window_on_miss(self) -> None:
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
                final_total=9,
                dice_rolls={"base_rolls": [4], "modifier": 5},
            )

            self.assertIn("request", result)
            self.assertIn("resolution", result)
            self.assertNotIn("status", result)
            encounter_repo.close()
            event_repo.close()

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

    def test_execute_attack_returns_waiting_reaction_when_target_can_deflect_attacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(with_shield=False, with_deflect_attacks=True))

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
            options = result["pending_reaction_window"]["choice_groups"][0]["options"]
            self.assertEqual(options[0]["reaction_type"], "deflect_attacks")
            encounter_repo.close()
            event_repo.close()

    def test_execute_attack_returns_waiting_reaction_when_target_can_uncanny_dodge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter(with_shield=False, with_uncanny_dodge=True))

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
            options = result["pending_reaction_window"]["choice_groups"][0]["options"]
            self.assertEqual(options[0]["reaction_type"], "uncanny_dodge")
            encounter_repo.close()
            event_repo.close()

    def test_execute_attack_does_not_open_deflect_window_for_non_bps_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(
                build_encounter(with_shield=False, with_deflect_attacks=True, damage_type="fire")
            )

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

    def test_execute_attack_opens_deflect_window_for_level_13_monk_on_non_bps_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(
                build_encounter(
                    with_shield=False,
                    with_deflect_attacks=True,
                    damage_type="fire",
                    monk_level=13,
                )
            )

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
            options = result["pending_reaction_window"]["choice_groups"][0]["options"]
            self.assertEqual(options[0]["reaction_type"], "deflect_attacks")
            encounter_repo.close()
            event_repo.close()
