"""豁免请求测试：覆盖 DC 计算、上下文组装和非法法术。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services import SavingThrowRequest


def build_caster() -> EncounterEntity:
    """构造带豁免型法术的施法者。"""
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
        source_ref={"spellcasting_ability": "cha"},
        ability_mods={"cha": 3},
        proficiency_bonus=2,
        spells=[
            {
                "spell_id": "blindness_deafness",
                "name": "Blindness/Deafness",
                "level": 2,
                "save_ability": "con",
                "requires_attack_roll": False,
            }
        ],
    )


def build_target() -> EncounterEntity:
    """构造需要过豁免的目标。"""
    return EncounterEntity(
        entity_id="ent_enemy_iron_duster_001",
        name="Iron Duster",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 5, "y": 4},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
    )


def build_encounter() -> Encounter:
    """构造豁免请求测试用 encounter。"""
    caster = build_caster()
    target = build_target()
    return Encounter(
        encounter_id="enc_save_request_test",
        name="Saving Throw Request Test Encounter",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, target.entity_id],
        entities={caster.entity_id: caster, target.entity_id: target},
        map=EncounterMap(
            map_id="map_save_request_test",
            name="Saving Throw Request Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class SavingThrowRequestTests(unittest.TestCase):
    def test_execute_builds_saving_throw_request(self) -> None:
        """测试会为目标生成带 save_dc 和施法者信息的豁免请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_save_request_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="blindness_deafness",
            )

            self.assertEqual(request.roll_type, "saving_throw")
            self.assertEqual(request.actor_entity_id, "ent_enemy_iron_duster_001")
            self.assertEqual(request.target_entity_id, "ent_enemy_iron_duster_001")
            self.assertEqual(request.context["caster_entity_id"], "ent_ally_eric_001")
            self.assertEqual(request.context["save_ability"], "con")
            self.assertEqual(request.context["save_dc"], 13)
            self.assertEqual(request.context["distance_to_target_feet"], 15)
            repo.close()

    def test_execute_rejects_spell_without_save_ability(self) -> None:
        """测试法术如果没有 save_ability，则不能走豁免请求链路。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].spells = [
                {
                    "spell_id": "fire_bolt",
                    "name": "Fire Bolt",
                    "level": 0,
                    "requires_attack_roll": True,
                }
            ]
            repo.save(encounter)

            with self.assertRaises(ValueError):
                SavingThrowRequest(repo).execute(
                    encounter_id="enc_save_request_test",
                    target_id="ent_enemy_iron_duster_001",
                    spell_id="fire_bolt",
                )
            repo.close()

    def test_execute_stores_vantage_in_request_context(self) -> None:
        """测试豁免请求会把优势/劣势信息写入 context。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_save_request_test",
                target_id="ent_enemy_iron_duster_001",
                spell_id="blindness_deafness",
                vantage="advantage",
            )

            self.assertEqual(request.context["vantage"], "advantage")
            repo.close()
