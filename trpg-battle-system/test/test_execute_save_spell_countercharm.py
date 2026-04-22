"""ExecuteSaveSpell 与 Countercharm 接入测试。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import (
    AppendEvent,
    EncounterCastSpell,
    ExecuteSaveSpell,
    ResolveSavingThrow,
    SavingThrowRequest,
    SavingThrowResult,
    UpdateConditions,
    UpdateEncounterNotes,
    UpdateHp,
)


def build_enemy_caster() -> EncounterEntity:
    spell_definition = {
        "id": "fear_burst",
        "name": "Fear Burst",
        "level": 2,
        "save_ability": "wis",
        "failed_save_outcome": {
            "damage_parts": [],
            "conditions": ["frightened"],
            "note": None,
        },
        "successful_save_outcome": {
            "damage_parts": [],
            "conditions": [],
            "note": None,
        },
    }
    return EncounterEntity(
        entity_id="ent_enemy_001",
        name="Enemy Caster",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 2, "y": 2},
        hp={"current": 25, "max": 25, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=18,
        source_ref={"spellcasting_ability": "cha", "spell_definitions": {"fear_burst": spell_definition}},
        ability_mods={"cha": 3},
        proficiency_bonus=2,
        resources={"spell_slots": {"2": {"max": 2, "remaining": 2}}},
        spells=[{"spell_id": "fear_burst", "name": "Fear Burst", "level": 2, "spell_definition": spell_definition}],
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
    )


def build_bard() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_bard_001",
        name="Bard",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 5, "y": 2},
        hp={"current": 22, "max": 22, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        ability_mods={"cha": 4},
        proficiency_bonus=3,
        action_economy={"reaction_used": False},
        class_features={"bard": {"level": 7}},
    )


def build_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_001",
        name="Target",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 7, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        ability_mods={"wis": 1},
        proficiency_bonus=3,
        save_proficiencies=["wis"],
        action_economy={"reaction_used": True},
    )


def build_encounter() -> Encounter:
    caster = build_enemy_caster()
    bard = build_bard()
    target = build_target()
    return Encounter(
        encounter_id="enc_execute_save_spell_countercharm_test",
        name="Execute Save Spell Countercharm Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, bard.entity_id, target.entity_id],
        entities={caster.entity_id: caster, bard.entity_id: bard, target.entity_id: target},
        map=EncounterMap(
            map_id="map_execute_save_spell_countercharm_test",
            name="Execute Save Spell Countercharm Test Map",
            description="A small combat room.",
            width=10,
            height=10,
        ),
    )


class ExecuteSaveSpellCountercharmTests(unittest.TestCase):
    def test_execute_failed_frightened_save_opens_countercharm_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = ExecuteSaveSpell(
                EncounterCastSpell(encounter_repo, AppendEvent(event_repo)),
                SavingThrowRequest(encounter_repo),
                ResolveSavingThrow(encounter_repo),
                SavingThrowResult(
                    encounter_repo,
                    AppendEvent(event_repo),
                    UpdateHp(encounter_repo, AppendEvent(event_repo)),
                    UpdateConditions(encounter_repo, AppendEvent(event_repo)),
                    UpdateEncounterNotes(encounter_repo, AppendEvent(event_repo)),
                ),
            )
            result = service.execute(
                encounter_id="enc_execute_save_spell_countercharm_test",
                target_id="ent_target_001",
                spell_id="fear_burst",
                base_roll=5,
                include_encounter_state=True,
            )

            self.assertEqual(result["status"], "waiting_reaction")
            self.assertEqual(result["pending_reaction_window"]["trigger_type"], "failed_save")
            self.assertEqual(
                result["pending_reaction_window"]["choice_groups"][0]["options"][0]["reaction_type"],
                "countercharm",
            )
            self.assertIn("cast", result)
            self.assertIn("encounter_state", result)

            encounter_repo.close()
            event_repo.close()
