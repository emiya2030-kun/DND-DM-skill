"""豁免总值结算测试：覆盖熟练豁免、非熟练豁免和主动失败。"""

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.models.roll_request import RollRequest
from tools.repositories import EncounterRepository
from tools.services import ResolveSavingThrow, SavingThrowRequest


def build_caster() -> EncounterEntity:
    """构造豁免结算测试用施法者。"""
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
                "spell_id": "hold_person",
                "name": "Hold Person",
                "level": 2,
                "save_ability": "wis",
                "requires_attack_roll": False,
            },
            {
                "spell_id": "burning_hands",
                "name": "Burning Hands",
                "level": 1,
                "save_ability": "dex",
                "requires_attack_roll": False,
            },
        ],
    )


def build_target() -> EncounterEntity:
    """构造需要过豁免的目标。"""
    return EncounterEntity(
        entity_id="ent_enemy_guard_001",
        name="Guard",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 4, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        ability_mods={"dex": 2, "wis": 1},
        proficiency_bonus=2,
        save_proficiencies=["wis"],
    )


def build_encounter() -> Encounter:
    """构造豁免总值结算测试用 encounter。"""
    caster = build_caster()
    target = build_target()
    return Encounter(
        encounter_id="enc_resolve_save_test",
        name="Resolve Save Test Encounter",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, target.entity_id],
        entities={caster.entity_id: caster, target.entity_id: target},
        map=EncounterMap(
            map_id="map_resolve_save_test",
            name="Resolve Save Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class ResolveSavingThrowTests(unittest.TestCase):
    def test_execute_calculates_proficient_save_total(self) -> None:
        """测试熟练豁免会把属性修正和熟练加值一起计入 final_total。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id="ent_enemy_guard_001",
                spell_id="hold_person",
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_roll=11,
            )

            self.assertEqual(result.final_total, 14)
            self.assertEqual(result.metadata["save_bonus"], 3)
            self.assertTrue(result.metadata["save_bonus_breakdown"]["is_proficient"])
            repo.close()

    def test_execute_calculates_non_proficient_save_total(self) -> None:
        """测试非熟练豁免只会计入对应属性调整值。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id="ent_enemy_guard_001",
                spell_id="burning_hands",
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_roll=11,
            )

            self.assertEqual(result.final_total, 13)
            self.assertEqual(result.metadata["save_bonus"], 2)
            self.assertFalse(result.metadata["save_bonus_breakdown"]["is_proficient"])
            repo.close()

    def test_execute_supports_voluntary_fail(self) -> None:
        """测试主动放弃豁免时，会直接标记为失败用的最低总值。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id="ent_enemy_guard_001",
                spell_id="hold_person",
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_roll=11,
                voluntary_fail=True,
            )

            self.assertEqual(result.final_total, 0)
            self.assertTrue(result.metadata["voluntary_fail"])
            repo.close()

    def test_execute_supports_advantage(self) -> None:
        """测试优势豁免会取两次 d20 中更高的结果。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            repo.save(build_encounter())

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id="ent_enemy_guard_001",
                spell_id="hold_person",
                vantage="advantage",
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_rolls=[5, 16],
            )

            self.assertEqual(result.final_total, 19)
            self.assertEqual(result.metadata["chosen_roll"], 16)
            self.assertEqual(result.metadata["vantage"], "advantage")
            repo.close()

    def test_execute_auto_fails_when_paralyzed(self) -> None:
        """STR/DEX 豁免在虚脱/眩晕等情况下直接判定为失败。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target_id = "ent_enemy_guard_001"
            encounter.entities[target_id].conditions = ["paralyzed"]
            repo.save(encounter)

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id=target_id,
                spell_id="burning_hands",
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_roll=20,
            )

            self.assertEqual(result.final_total, 0)
            self.assertTrue(result.metadata["auto_fail"])
            self.assertEqual(result.metadata["condition_disadvantages"], [])
            self.assertEqual(result.metadata["vantage"], "normal")
            repo.close()

    def test_execute_applies_disadvantage_on_restrained_dex(self) -> None:
        """DEX 豁免在被束缚时会获得劣势。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target_id = "ent_enemy_guard_001"
            encounter.entities[target_id].conditions = ["restrained"]
            repo.save(encounter)

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id=target_id,
                spell_id="burning_hands",
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_rolls=[17, 6],
            )

            self.assertEqual(result.metadata["vantage"], "disadvantage")
            self.assertEqual(result.metadata["condition_disadvantages"], ["restrained"])
            self.assertEqual(result.metadata["chosen_roll"], 6)
            self.assertEqual(result.final_total, 8)
            repo.close()

    def test_execute_danger_sense_adds_advantage_to_dex_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_guard_001"].class_features = {"barbarian": {"level": 2}}
            repo.save(encounter)

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id="ent_enemy_guard_001",
                spell_id="burning_hands",
            )

            self.assertEqual(request.context["vantage"], "advantage")
            self.assertIn("barbarian_danger_sense", request.context["vantage_sources"]["advantage"])
            repo.close()

    def test_execute_rage_grants_advantage_on_strength_save(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_guard_001"]
            target.ability_mods["str"] = 3
            target.class_features = {"barbarian": {"level": 1, "rage": {"active": True}}}
            repo.save(encounter)

            request = RollRequest(
                request_id="req_strength_save_001",
                encounter_id="enc_resolve_save_test",
                actor_entity_id=target.entity_id,
                target_entity_id=target.entity_id,
                roll_type="saving_throw",
                formula="1d20+save_modifier",
                reason="Strength save test",
                context={"save_ability": "str", "save_dc": 15, "vantage": "normal"},
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_rolls=[4, 16],
            )

            self.assertEqual(result.metadata["vantage"], "advantage")
            self.assertEqual(result.metadata["chosen_roll"], 16)
            self.assertEqual(result.final_total, 21)
            repo.close()

    def test_execute_indomitable_might_raises_strength_save_floor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_guard_001"]
            target.ability_scores = {"str": 20, "dex": 14, "wis": 12}
            target.ability_mods["str"] = 5
            target.class_features = {"barbarian": {"level": 18, "indomitable_might": {"enabled": True}}}
            repo.save(encounter)

            request = RollRequest(
                request_id="req_strength_save_002",
                encounter_id="enc_resolve_save_test",
                actor_entity_id=target.entity_id,
                target_entity_id=target.entity_id,
                roll_type="saving_throw",
                formula="1d20+save_modifier",
                reason="Strength save floor test",
                context={"save_ability": "str", "save_dc": 18, "vantage": "normal"},
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_roll=2,
            )

            self.assertEqual(result.final_total, 20)
            repo.close()

    def test_execute_does_not_auto_fail_wis_save(self) -> None:
        """非 STR/DEX 豁免即使目标眩晕也能正常掷骰。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target_id = "ent_enemy_guard_001"
            encounter.entities[target_id].conditions = ["stunned"]
            repo.save(encounter)

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id=target_id,
                spell_id="hold_person",
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_roll=12,
            )

            self.assertFalse(result.metadata["auto_fail"])
            self.assertGreater(result.final_total, 0)
            repo.close()

    def test_execute_applies_exhaustion_penalty(self) -> None:
        """疲劳等级会扣除对应的 d20 惩罚。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target_id = "ent_enemy_guard_001"
            encounter.entities[target_id].conditions = ["exhaustion:2"]
            repo.save(encounter)

            request = SavingThrowRequest(repo).execute(
                encounter_id="enc_resolve_save_test",
                target_id=target_id,
                spell_id="burning_hands",
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_roll=15,
            )

            self.assertEqual(result.metadata["d20_penalty"], 4)
            self.assertEqual(result.final_total, 13)
            self.assertEqual(result.metadata["condition_disadvantages"], [])
            repo.close()

    def test_execute_uses_class_template_save_proficiencies(self) -> None:
        """测试职业模板提供的默认豁免熟练会参与结算。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_guard_001"]
            target.class_features = {"fighter": {"level": 1}}
            target.save_proficiencies = []
            target.ability_mods["str"] = 0
            repo.save(encounter)

            request = RollRequest(
                request_id="req_save_class_template",
                encounter_id="enc_resolve_save_test",
                actor_entity_id=target.entity_id,
                target_entity_id=target.entity_id,
                roll_type="saving_throw",
                formula="1d20",
                context={"save_ability": "str", "vantage": "normal"},
            )
            result = ResolveSavingThrow(repo).execute(
                encounter_id="enc_resolve_save_test",
                roll_request=request,
                base_roll=11,
            )

            self.assertEqual(result.final_total, 13)
            self.assertTrue(result.metadata["save_bonus_breakdown"]["is_proficient"])
            self.assertEqual(result.metadata["save_bonus_breakdown"]["proficiency_bonus_applied"], 2)
            repo.close()
