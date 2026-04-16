"""标记法术转移测试：覆盖 Hex / Hunter's Mark 的正式转移。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, RetargetMarkedSpell


def build_caster() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_eric_001",
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        resources={"spell_slots": {"1": {"max": 2, "remaining": 2}}},
        action_economy={"bonus_action_used": False},
        combat_flags={"is_active": True, "is_defeated": False, "is_concentrating": True},
    )


def build_old_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_goblin_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 4, "y": 2},
        hp={"current": 0, "max": 10, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        combat_flags={"is_active": False, "is_defeated": True},
    )


def build_new_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_orc_001",
        name="Orc",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 6, "y": 2},
        hp={"current": 15, "max": 15, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=9,
    )


def build_encounter(spell_id: str, effect_id: str) -> Encounter:
    caster = build_caster()
    old_target = build_old_target()
    new_target = build_new_target()
    return Encounter(
        encounter_id="enc_retarget_test",
        name="Retarget Test Encounter",
        status="active",
        round=2,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, old_target.entity_id, new_target.entity_id],
        entities={
            caster.entity_id: caster,
            old_target.entity_id: old_target,
            new_target.entity_id: new_target,
        },
        map=EncounterMap(
            map_id="map_retarget_test",
            name="Retarget Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
        spell_instances=[
            {
                "instance_id": f"spell_{spell_id}_001",
                "spell_id": spell_id,
                "spell_name": "Hex" if spell_id == "hex" else "Hunter's Mark",
                "caster_entity_id": caster.entity_id,
                "caster_name": caster.name,
                "cast_level": 1,
                "concentration": {"required": True, "active": True},
                "targets": [
                    {
                        "entity_id": old_target.entity_id,
                        "applied_conditions": [],
                        "turn_effect_ids": [effect_id],
                    }
                ],
                "lifecycle": {"status": "active", "started_round": 1},
                "special_runtime": {
                    "retargetable": True,
                    "retarget_available": True,
                    "current_target_id": None,
                },
            }
        ],
    )


class RetargetMarkedSpellTests(unittest.TestCase):
    def test_execute_retargets_hex_without_consuming_spell_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter("hex", "effect_hex_001"))

            service = RetargetMarkedSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_retarget_test",
                spell_instance_id="spell_hex_001",
                new_target_id="ent_enemy_orc_001",
            )

            updated = encounter_repo.get("enc_retarget_test")
            assert updated is not None
            caster = updated.entities["ent_ally_eric_001"]
            new_target = updated.entities["ent_enemy_orc_001"]
            instance = updated.spell_instances[0]

            self.assertEqual(caster.resources["spell_slots"]["1"]["remaining"], 2)
            self.assertTrue(caster.action_economy["bonus_action_used"])
            self.assertIsNone(result["slot_consumed"])
            self.assertEqual(instance["targets"][0]["entity_id"], "ent_enemy_orc_001")
            self.assertEqual(instance["special_runtime"]["current_target_id"], "ent_enemy_orc_001")
            self.assertFalse(instance["special_runtime"]["retarget_available"])
            self.assertEqual(len(new_target.turn_effects), 1)
            self.assertEqual(new_target.turn_effects[0]["source_ref"], "hex")
            encounter_repo.close()
            event_repo.close()

    def test_execute_retargets_hunters_mark_without_consuming_spell_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter("hunters_mark", "effect_hunters_mark_001"))

            service = RetargetMarkedSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_retarget_test",
                spell_instance_id="spell_hunters_mark_001",
                new_target_id="ent_enemy_orc_001",
            )

            updated = encounter_repo.get("enc_retarget_test")
            assert updated is not None
            new_target = updated.entities["ent_enemy_orc_001"]
            instance = updated.spell_instances[0]

            self.assertIsNone(result["slot_consumed"])
            self.assertEqual(instance["targets"][0]["entity_id"], "ent_enemy_orc_001")
            self.assertEqual(instance["special_runtime"]["current_target_id"], "ent_enemy_orc_001")
            self.assertFalse(instance["special_runtime"]["retarget_available"])
            self.assertEqual(len(new_target.turn_effects), 1)
            self.assertEqual(new_target.turn_effects[0]["source_ref"], "hunters_mark")
            encounter_repo.close()
            event_repo.close()

    def test_execute_rejects_when_bonus_action_already_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter("hex", "effect_hex_001")
            encounter.entities["ent_ally_eric_001"].action_economy["bonus_action_used"] = True
            encounter_repo.save(encounter)

            service = RetargetMarkedSpell(encounter_repo, AppendEvent(event_repo))
            with self.assertRaises(ValueError):
                service.execute(
                    encounter_id="enc_retarget_test",
                    spell_instance_id="spell_hex_001",
                    new_target_id="ent_enemy_orc_001",
                )
            encounter_repo.close()
            event_repo.close()


if __name__ == "__main__":
    unittest.main()
