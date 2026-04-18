"""HP 更新测试：覆盖伤害、治疗、临时 HP 和事件写入。"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, RequestConcentrationCheck, UpdateHp


def build_target() -> EncounterEntity:
    """构造 HP 更新测试用目标。"""
    return EncounterEntity(
        entity_id="ent_enemy_goblin_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 3, "y": 2},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_player_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_eric_001",
        name="Eric",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        combat_flags={"is_active": True, "is_defeated": False},
    )


def build_barbarian_player_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_barbarian_001",
        name="Barbarian",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 8, "max": 30, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        ability_scores={"str": 18, "dex": 12, "con": 16, "int": 8, "wis": 10, "cha": 10},
        ability_mods={"str": 4, "dex": 1, "con": 3, "int": -1, "wis": 0, "cha": 0},
        proficiency_bonus=4,
        save_proficiencies=["con"],
        combat_flags={"is_active": True, "is_defeated": False},
        class_features={
            "barbarian": {
                "level": 11,
                "rage": {"active": True, "remaining": 2, "max": 4},
                "relentless_rage": {"enabled": True, "current_dc": 10},
            }
        },
    )


def build_npc_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_npc_guard_001",
        name="Town Guard",
        side="ally",
        category="npc",
        controller="gm",
        position={"x": 5, "y": 2},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        combat_flags={"is_active": True, "is_defeated": False},
    )


def build_summon_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_summon_wolf_001",
        name="Spirit Wolf",
        side="ally",
        category="summon",
        controller="player",
        position={"x": 4, "y": 2},
        hp={"current": 8, "max": 8, "temp": 0},
        ac=13,
        speed={"walk": 40, "remaining": 40},
        initiative=12,
        combat_flags={"is_active": True, "is_defeated": False},
    )


def build_mark_caster() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_ally_warlock_001",
        name="Warlock",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 2},
        hp={"current": 16, "max": 16, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        combat_flags={"is_active": True, "is_defeated": False, "is_concentrating": True},
    )


def build_paladin_source() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_paladin_001",
        name="Paladin",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 2},
        hp={"current": 24, "max": 24, "temp": 0},
        ac=18,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        combat_flags={"is_active": True, "is_defeated": False},
    )


def build_enemy_attacker() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_orc_001",
        name="Orc",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 4, "y": 2},
        hp={"current": 15, "max": 15, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
    )


def build_encounter() -> Encounter:
    """构造 HP 更新测试用 encounter。"""
    target = build_target()
    return Encounter(
        encounter_id="enc_hp_test",
        name="HP Test Encounter",
        status="active",
        round=1,
        current_entity_id=target.entity_id,
        turn_order=[target.entity_id],
        entities={target.entity_id: target},
        map=EncounterMap(
            map_id="map_hp_test",
            name="HP Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


def build_concentration_spell_instance(caster_entity_id: str, target_id: str) -> dict[str, object]:
    return {
        "instance_id": "spell_inst_001",
        "caster_entity_id": caster_entity_id,
        "concentration": {"required": True, "active": True},
        "lifecycle": {"status": "active"},
        "targets": [
            {
                "entity_id": target_id,
                "applied_conditions": ["marked"],
                "turn_effect_ids": ["effect_marked_001"],
            }
        ],
    }


def build_mark_spell_instance(*, spell_id: str, caster_entity_id: str, target_id: str, effect_id: str) -> dict[str, object]:
    spell_name = "Hex" if spell_id == "hex" else "Hunter's Mark"
    return {
        "instance_id": f"spell_{spell_id}_001",
        "spell_id": spell_id,
        "spell_name": spell_name,
        "caster_entity_id": caster_entity_id,
        "caster_name": "Warlock",
        "cast_level": 1,
        "concentration": {"required": True, "active": True},
        "lifecycle": {"status": "active"},
        "targets": [
            {
                "entity_id": target_id,
                "applied_conditions": [],
                "turn_effect_ids": [effect_id],
            }
        ],
        "special_runtime": {
            "retargetable": True,
            "retarget_available": False,
            "current_target_id": target_id,
            "retarget_trigger": "target_drop_to_zero",
            "retarget_activation": "bonus_action",
        },
    }


class UpdateHpTests(unittest.TestCase):
    def test_execute_damage_removes_abjure_foes_effect_and_condition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            paladin = build_paladin_source()
            attacker = build_enemy_attacker()
            target = build_target()
            target.conditions = [f"frightened:{paladin.entity_id}"]
            target.turn_effects = [
                {
                    "effect_id": f"abjure_foes:{paladin.entity_id}:{target.entity_id}",
                    "effect_type": "abjure_foes_restriction",
                    "source_entity_id": paladin.entity_id,
                    "source_ref": "paladin:abjure_foes",
                    "ends_on_damage": True,
                    "duration_rounds": 10,
                }
            ]
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=attacker.entity_id,
                turn_order=[attacker.entity_id, target.entity_id, paladin.entity_id],
                entities={
                    attacker.entity_id: attacker,
                    target.entity_id: target,
                    paladin.entity_id: paladin,
                },
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            result = UpdateHp(encounter_repo, AppendEvent(event_repo)).execute(
                encounter_id="enc_hp_test",
                target_id=target.entity_id,
                hp_change=4,
                reason="test_hit",
                damage_type="slashing",
                source_entity_id=attacker.entity_id,
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_target = updated.entities[target.entity_id]
            self.assertNotIn(f"frightened:{paladin.entity_id}", updated_target.conditions)
            self.assertEqual(updated_target.turn_effects, [])
            self.assertEqual(result["class_feature_resolution"]["abjure_foes"]["removed_effects"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_relentless_rage_success_sets_hp_to_double_barbarian_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            target = build_barbarian_player_target()
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=target.entity_id,
                turn_order=[target.entity_id],
                entities={target.entity_id: target},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            with patch("random.randint", return_value=10):
                result = service.execute(
                    encounter_id="enc_hp_test",
                    target_id=target.entity_id,
                    hp_change=10,
                    reason="Relentless Rage test",
                    damage_type="slashing",
                )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_target = updated.entities[target.entity_id]
            relentless = result["class_feature_resolution"]["relentless_rage"]
            self.assertEqual(updated_target.hp["current"], 22)
            self.assertTrue(relentless["triggered"])
            self.assertTrue(relentless["success"])
            self.assertEqual(relentless["save_dc"], 10)
            self.assertEqual(relentless["save_total"], 17)
            self.assertEqual(updated_target.class_features["barbarian"]["relentless_rage"]["current_dc"], 15)
            encounter_repo.close()
            event_repo.close()

    def test_execute_marks_hex_instance_retargetable_when_target_drops_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            caster = build_mark_caster()
            target = build_target()
            target.turn_effects = [
                {
                    "effect_id": "effect_hex_001",
                    "source_ref": "hex",
                    "source_entity_id": caster.entity_id,
                    "attack_bonus_damage_parts": [
                        {
                            "source": "spell:hex:bonus_damage",
                            "formula": "1d6",
                            "damage_type": "necrotic",
                        }
                    ],
                }
            ]
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=target.entity_id,
                turn_order=[caster.entity_id, target.entity_id],
                entities={caster.entity_id: caster, target.entity_id: target},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
                spell_instances=[
                    build_mark_spell_instance(
                        spell_id="hex",
                        caster_entity_id=caster.entity_id,
                        target_id=target.entity_id,
                        effect_id="effect_hex_001",
                    )
                ],
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=target.entity_id,
                hp_change=99,
                reason="Hexed target dropped",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            instance = updated.spell_instances[0]
            self.assertTrue(instance["special_runtime"]["retarget_available"])
            self.assertIsNone(instance["special_runtime"]["current_target_id"])
            self.assertEqual(instance["targets"][0]["entity_id"], target.entity_id)
            self.assertEqual(instance["targets"][0]["turn_effect_ids"], [])
            self.assertEqual(result["retarget_updates"][0]["spell_id"], "hex")
            encounter_repo.close()
            event_repo.close()

    def test_execute_marks_hunters_mark_instance_retargetable_when_target_drops_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            caster = build_mark_caster()
            target = build_npc_target()
            target.turn_effects = [
                {
                    "effect_id": "effect_hunters_mark_001",
                    "source_ref": "hunters_mark",
                    "source_entity_id": caster.entity_id,
                    "attack_bonus_damage_parts": [
                        {
                            "source": "spell:hunters_mark:bonus_damage",
                            "formula": "1d6",
                            "damage_type": "force",
                        }
                    ],
                }
            ]
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=target.entity_id,
                turn_order=[caster.entity_id, target.entity_id],
                entities={caster.entity_id: caster, target.entity_id: target},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
                spell_instances=[
                    build_mark_spell_instance(
                        spell_id="hunters_mark",
                        caster_entity_id=caster.entity_id,
                        target_id=target.entity_id,
                        effect_id="effect_hunters_mark_001",
                    )
                ],
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=target.entity_id,
                hp_change=99,
                reason="Marked npc dropped",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_target = updated.entities[target.entity_id]
            instance = updated.spell_instances[0]
            self.assertTrue(instance["special_runtime"]["retarget_available"])
            self.assertIsNone(instance["special_runtime"]["current_target_id"])
            self.assertEqual(updated_target.turn_effects, [])
            self.assertEqual(result["retarget_updates"][0]["spell_id"], "hunters_mark")
            encounter_repo.close()
            event_repo.close()

    def test_execute_ends_concentration_when_pc_drops_to_zero_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            player.combat_flags["is_concentrating"] = True
            player.conditions = ["marked"]
            player.turn_effects = [
                {
                    "effect_id": "effect_marked_001",
                    "effect_type": "spell_mark",
                }
            ]
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
                spell_instances=[build_concentration_spell_instance(player.entity_id, player.entity_id)],
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=99,
                reason="Player dropped",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            self.assertFalse(updated_player.combat_flags.get("is_concentrating", True))
            self.assertNotIn("marked", updated_player.conditions)
            self.assertEqual(updated_player.turn_effects, [])
            self.assertFalse(updated.spell_instances[0]["concentration"]["active"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_ends_concentration_when_zero_hp_pc_dies_from_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            player.hp["current"] = 0
            player.conditions = ["unconscious", "marked"]
            player.turn_effects = [
                {
                    "effect_id": "effect_marked_001",
                    "effect_type": "spell_mark",
                }
            ]
            player.combat_flags["is_concentrating"] = True
            player.combat_flags["death_saves"] = {"successes": 0, "failures": 1}
            player.combat_flags["is_dead"] = False
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
                spell_instances=[build_concentration_spell_instance(player.entity_id, player.entity_id)],
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=10,
                reason="Massive damage at zero hp",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            self.assertTrue(updated_player.combat_flags["is_dead"])
            self.assertFalse(updated_player.combat_flags.get("is_concentrating", True))
            self.assertNotIn("marked", updated_player.conditions)
            self.assertEqual(updated_player.turn_effects, [])
            self.assertFalse(updated.spell_instances[0]["concentration"]["active"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_knockout_protection_on_melee_zero_hp_intent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=99,
                reason="Flat of blade strike",
                attack_kind="melee_weapon",
                zero_hp_intent="knockout",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            protection_effects = [
                effect
                for effect in updated_player.turn_effects
                if effect.get("effect_type") == "knockout_protection"
            ]
            self.assertEqual(updated_player.hp["current"], 0)
            self.assertIn("unconscious", updated_player.conditions)
            self.assertEqual(updated_player.combat_flags["death_saves"], {"successes": 0, "failures": 0})
            self.assertFalse(updated_player.combat_flags["is_dead"])
            self.assertEqual(len(protection_effects), 1)
            self.assertEqual(protection_effects[0]["duration_seconds"], 3600)
            self.assertEqual(result["zero_hp_outcome"]["outcome"], "entity_dying")
            encounter_repo.close()
            event_repo.close()

    def test_execute_consumes_knockout_protection_before_zero_hp_followup_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            player.hp["current"] = 0
            player.conditions = ["unconscious"]
            player.combat_flags["death_saves"] = {"successes": 0, "failures": 0}
            player.combat_flags["is_dead"] = False
            player.turn_effects = [
                {
                    "effect_id": "effect_knockout_001",
                    "effect_type": "knockout_protection",
                    "duration_seconds": 3600,
                }
            ]
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=1,
                reason="Follow-up hit on unconscious target",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            protection_effects = [
                effect
                for effect in updated_player.turn_effects
                if effect.get("effect_type") == "knockout_protection"
            ]
            self.assertEqual(protection_effects, [])
            self.assertEqual(updated_player.combat_flags["death_saves"]["failures"], 1)
            self.assertFalse(updated_player.combat_flags["is_dead"])
            self.assertEqual(result["zero_hp_followup"]["outcome"], "death_save_failure")
            encounter_repo.close()
            event_repo.close()

    def test_execute_keeps_pc_on_map_and_marks_it_dying_at_zero_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=99,
                reason="Player dropped",
                include_encounter_state=True,
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            self.assertIn(player.entity_id, updated.entities)
            self.assertEqual(updated_player.hp["current"], 0)
            self.assertIn("unconscious", updated_player.conditions)
            self.assertEqual(
                updated_player.combat_flags.get("death_saves"),
                {"successes": 0, "failures": 0},
            )
            self.assertFalse(updated_player.combat_flags.get("is_dead", True))
            self.assertFalse(updated_player.combat_flags.get("is_defeated", False))
            self.assertEqual(result["zero_hp_outcome"]["outcome"], "entity_dying")
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_damage(self) -> None:
        """测试正数 hp_change 会作为伤害扣减当前 HP。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=4,
                reason="Rapier damage",
                damage_type="piercing",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 6)
            self.assertEqual(result["event_type"], "damage_applied")
            encounter_repo.close()
            event_repo.close()

    def test_execute_can_include_latest_encounter_state(self) -> None:
        """测试可以在 HP 更新结果里附带最新前端状态。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=4,
                reason="Rapier damage",
                damage_type="piercing",
                include_encounter_state=True,
            )

            self.assertIn("encounter_state", result)
            self.assertEqual(result["encounter_state"]["encounter_id"], "enc_hp_test")
            self.assertEqual(result["encounter_state"]["current_turn_entity"]["hp"], "6 / 10 HP")
            encounter_repo.close()
            event_repo.close()

    def test_execute_removes_monster_at_zero_hp_and_leaves_skeleton_remains(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=99,
                reason="Massive damage",
                include_encounter_state=True,
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertNotIn("ent_enemy_goblin_001", updated.entities)
            self.assertNotIn("ent_enemy_goblin_001", updated.turn_order)
            self.assertEqual(getattr(updated.map, "remains", [])[0]["icon"], "💀")
            self.assertEqual(getattr(updated.map, "remains", [])[0]["position"], {"x": 3, "y": 2})
            self.assertEqual(result["zero_hp_outcome"]["outcome"], "monster_removed_with_remains")
            encounter_repo.close()
            event_repo.close()

    def test_execute_removes_summon_at_zero_hp_without_remains(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            summon = build_summon_target()
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=summon.entity_id,
                turn_order=[summon.entity_id],
                entities={summon.entity_id: summon},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=summon.entity_id,
                hp_change=99,
                reason="Summon destroyed",
                include_encounter_state=True,
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertNotIn(summon.entity_id, updated.entities)
            self.assertEqual(getattr(updated.map, "remains", []), [])
            self.assertEqual(result["zero_hp_outcome"]["outcome"], "summon_removed")
            encounter_repo.close()
            event_repo.close()

    def test_execute_keeps_npc_on_map_and_marks_it_dying_at_zero_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            npc = build_npc_target()
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=npc.entity_id,
                turn_order=[npc.entity_id],
                entities={npc.entity_id: npc},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=npc.entity_id,
                hp_change=99,
                reason="NPC dropped",
                include_encounter_state=True,
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_npc = updated.entities[npc.entity_id]
            self.assertIn(npc.entity_id, updated.entities)
            self.assertEqual(updated_npc.hp["current"], 0)
            self.assertIn("unconscious", updated_npc.conditions)
            self.assertEqual(
                updated_npc.combat_flags.get("death_saves"),
                {"successes": 0, "failures": 0},
            )
            self.assertFalse(updated_npc.combat_flags.get("is_dead", True))
            self.assertFalse(updated_npc.combat_flags.get("is_defeated", False))
            self.assertEqual(result["zero_hp_outcome"]["outcome"], "entity_dying")
            encounter_repo.close()
            event_repo.close()

    def test_execute_adds_one_death_save_failure_when_pc_at_zero_hp_takes_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            player.hp["current"] = 0
            player.conditions = ["unconscious"]
            player.combat_flags["death_saves"] = {"successes": 0, "failures": 0}
            player.combat_flags["is_dead"] = False
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=1,
                reason="Failed coup de grace",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            self.assertEqual(updated_player.combat_flags["death_saves"]["failures"], 1)
            self.assertFalse(updated_player.combat_flags["is_dead"])
            self.assertEqual(result["zero_hp_followup"]["outcome"], "death_save_failure")
            encounter_repo.close()
            event_repo.close()

    def test_execute_adds_two_death_save_failures_when_zero_hp_target_takes_critical_hit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            player.hp["current"] = 0
            player.conditions = ["unconscious"]
            player.combat_flags["death_saves"] = {"successes": 1, "failures": 0}
            player.combat_flags["is_dead"] = False
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=1,
                reason="Critical hit on dying target",
                from_critical_hit=True,
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            self.assertEqual(updated_player.combat_flags["death_saves"]["failures"], 2)
            self.assertFalse(updated_player.combat_flags["is_dead"])
            self.assertEqual(result["zero_hp_followup"]["outcome"], "death_save_failure")
            encounter_repo.close()
            event_repo.close()

    def test_execute_kills_zero_hp_pc_on_massive_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            player.hp["current"] = 0
            player.conditions = ["unconscious"]
            player.combat_flags["death_saves"] = {"successes": 0, "failures": 1}
            player.combat_flags["is_dead"] = False
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=10,
                reason="Massive damage at zero hp",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            self.assertTrue(updated_player.combat_flags["is_dead"])
            self.assertEqual(result["zero_hp_followup"]["outcome"], "entity_dead")
            encounter_repo.close()
            event_repo.close()

    def test_execute_kills_zero_hp_pc_when_failures_reach_three(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            player = build_player_target()
            player.hp["current"] = 0
            player.conditions = ["unconscious"]
            player.combat_flags["death_saves"] = {"successes": 0, "failures": 2}
            player.combat_flags["is_dead"] = False
            encounter = Encounter(
                encounter_id="enc_hp_test",
                name="HP Test Encounter",
                status="active",
                round=1,
                current_entity_id=player.entity_id,
                turn_order=[player.entity_id],
                entities={player.entity_id: player},
                map=EncounterMap(
                    map_id="map_hp_test",
                    name="HP Test Map",
                    description="A small combat room.",
                    width=8,
                    height=8,
                ),
            )
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=player.entity_id,
                hp_change=1,
                reason="Third failed death save from damage",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            updated_player = updated.entities[player.entity_id]
            self.assertEqual(updated_player.combat_flags["death_saves"]["failures"], 3)
            self.assertTrue(updated_player.combat_flags["is_dead"])
            self.assertEqual(result["zero_hp_followup"]["outcome"], "entity_dead")
            encounter_repo.close()
            event_repo.close()

    def test_execute_uses_temp_hp_before_current_hp(self) -> None:
        """测试伤害会先消耗临时 HP，再扣当前 HP。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_goblin_001"].hp["temp"] = 3
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=5,
                reason="Fire damage",
                damage_type="fire",
                from_critical_hit=True,
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 8)
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["temp"], 0)
            self.assertEqual(result["temp_hp_absorbed"], 3)
            self.assertTrue(result["from_critical_hit"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_healing_and_caps_at_max_hp(self) -> None:
        """测试负数 hp_change 会作为治疗，并且不会超过 max HP。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_goblin_001"].hp["current"] = 6
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=-10,
                reason="Healing word",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 10)
            self.assertEqual(result["event_type"], "healing_applied")
            encounter_repo.close()
            event_repo.close()

    def test_execute_blocks_healing_for_dead_target(self) -> None:
        """测试已死亡目标不能接受普通治疗。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_goblin_001"]
            target.hp["current"] = 0
            target.combat_flags["is_dead"] = True
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=-6,
                reason="Healing Word",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 0)
            self.assertEqual(result["event_type"], "hp_unchanged")
            self.assertTrue(result["healing_blocked"])
            self.assertEqual(result["healing_blocked_reason"], "target_is_dead")
            encounter_repo.close()
            event_repo.close()

    def test_execute_allows_healing_for_zero_hp_but_not_dead_target(self) -> None:
        """测试 0 HP 但未死亡的目标仍可接受治疗。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_goblin_001"]
            target.hp["current"] = 0
            target.combat_flags["is_dead"] = False
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=-4,
                reason="Healing Word",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 4)
            self.assertEqual(result["event_type"], "healing_applied")
            self.assertNotIn("healing_blocked_reason", result)
            encounter_repo.close()
            event_repo.close()

    def test_execute_writes_event_payload(self) -> None:
        """测试事件日志里会保留 HP 变化前后和原因。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=2,
                reason="Magic missile",
                damage_type="force",
            )

            events = event_repo.list_by_encounter("enc_hp_test")
            self.assertEqual(events[0].payload["reason"], "Magic missile")
            self.assertEqual(events[0].payload["hp_before"], 10)
            self.assertEqual(events[0].payload["hp_after"], 8)
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_resistance(self) -> None:
        """测试目标拥有对应抗性时，伤害会减半并向下取整。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_goblin_001"].resistances = ["fire"]
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=5,
                reason="Fire damage",
                damage_type="fire",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 8)
            self.assertEqual(result["adjusted_hp_change"], 2)
            self.assertEqual(result["damage_adjustment"]["rule"], "resistance")
            encounter_repo.close()
            event_repo.close()

    def test_execute_does_not_treat_petrified_as_extra_resistance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_goblin_001"]
            target.conditions = ["petrified"]
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id=target.entity_id,
                hp_change=10,
                reason="Fire damage",
                damage_type="fire",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertNotIn("ent_enemy_goblin_001", updated.entities)
            self.assertEqual(result["adjusted_hp_change"], 10)
            self.assertEqual(result["damage_adjustment"]["rule"], "normal")
            self.assertEqual(result["zero_hp_outcome"]["outcome"], "monster_removed_with_remains")
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_immunity(self) -> None:
        """测试目标拥有对应免疫时，该类型伤害会被完全忽略。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_goblin_001"].immunities = ["poison"]
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=5,
                reason="Poison damage",
                damage_type="poison",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 10)
            self.assertEqual(result["adjusted_hp_change"], 0)
            self.assertEqual(result["damage_adjustment"]["rule"], "immunity")
            encounter_repo.close()
            event_repo.close()

    def test_execute_applies_vulnerability(self) -> None:
        """测试目标拥有对应易伤时，该类型伤害会翻倍。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_goblin_001"].vulnerabilities = ["radiant"]
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=3,
                reason="Radiant damage",
                damage_type="radiant",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 4)
            self.assertEqual(result["adjusted_hp_change"], 6)
            self.assertEqual(result["damage_adjustment"]["rule"], "vulnerability")
            encounter_repo.close()
            event_repo.close()

    def test_execute_resistance_and_vulnerability_cancel_out(self) -> None:
        """测试同一伤害类型同时存在抗性和易伤时，按原伤害处理。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            target = encounter.entities["ent_enemy_goblin_001"]
            target.resistances = ["cold"]
            target.vulnerabilities = ["cold"]
            encounter_repo.save(encounter)

            service = UpdateHp(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=4,
                reason="Cold damage",
                damage_type="cold",
            )

            updated = encounter_repo.get("enc_hp_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_enemy_goblin_001"].hp["current"], 6)
            self.assertEqual(result["adjusted_hp_change"], 4)
            self.assertEqual(result["damage_adjustment"]["rule"], "resistance_and_vulnerability_cancel")
            encounter_repo.close()
            event_repo.close()

    def test_execute_auto_creates_concentration_check_request(self) -> None:
        """测试目标正在专注且受到实际伤害时，会自动生成专注检定请求。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_goblin_001"].combat_flags = {
                "is_active": True,
                "is_defeated": False,
                "is_concentrating": True,
            }
            encounter.entities["ent_enemy_goblin_001"].ability_mods = {"con": 2}
            encounter.entities["ent_enemy_goblin_001"].save_proficiencies = ["con"]
            encounter.entities["ent_enemy_goblin_001"].proficiency_bonus = 2
            encounter_repo.save(encounter)

            service = UpdateHp(
                encounter_repo,
                AppendEvent(event_repo),
                RequestConcentrationCheck(encounter_repo),
            )
            result = service.execute(
                encounter_id="enc_hp_test",
                target_id="ent_enemy_goblin_001",
                hp_change=8,
                reason="Force damage",
                damage_type="force",
                source_entity_id="ent_enemy_goblin_001",
                concentration_vantage="advantage",
            )

            self.assertEqual(result["concentration_check_request"]["roll_type"], "concentration_check")
            self.assertEqual(result["concentration_check_request"]["context"]["save_dc"], 10)
            self.assertEqual(result["concentration_check_request"]["context"]["vantage"], "advantage")
            event_repo.close()
            encounter_repo.close()

if __name__ == "__main__":
    unittest.main()
