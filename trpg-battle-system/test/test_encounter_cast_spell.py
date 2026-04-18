"""施法声明测试：覆盖法术位消耗、戏法处理和非法施法。"""

import sys
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import ArmorDefinitionRepository, EncounterRepository, EventRepository, SpellDefinitionRepository
from tools.services import AppendEvent, EncounterCastSpell


def build_caster() -> EncounterEntity:
    """构造带法术列表和法术位的施法者。"""
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
        ability_mods={"cha": 3},
        proficiency_bonus=2,
        resources={
            "spell_slots": {
                "1": {"max": 2, "remaining": 2},
                "2": {"max": 1, "remaining": 1},
                "3": {"max": 1, "remaining": 1},
            }
        },
        spells=[
            {
                "spell_id": "blindness_deafness",
                "name": "Blindness/Deafness",
                "level": 2,
                "save_ability": "con",
                "requires_attack_roll": False,
            },
            {
                "spell_id": "fire_bolt",
                "name": "Fire Bolt",
                "level": 0,
                "requires_attack_roll": True,
            },
            {
                "spell_id": "find_steed",
                "name": "Find Steed",
                "level": 2,
                "base": {
                    "level": 2,
                    "casting_time": "1 action",
                    "concentration": False
                },
            },
            {
                "spell_id": "find_familiar",
                "name": "Find Familiar",
                "level": 1,
                "base": {
                    "level": 1,
                    "casting_time": "1 action",
                    "concentration": False
                },
            },
        ],
    )


def build_target() -> EncounterEntity:
    """构造施法目标。"""
    return EncounterEntity(
        entity_id="ent_enemy_iron_duster_001",
        name="Iron Duster",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 4, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=16,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
    )


def build_encounter() -> Encounter:
    """构造施法声明测试用 encounter。"""
    caster = build_caster()
    target = build_target()
    return Encounter(
        encounter_id="enc_cast_spell_test",
        name="Cast Spell Test Encounter",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, target.entity_id],
        entities={caster.entity_id: caster, target.entity_id: target},
        map=EncounterMap(
            map_id="map_cast_spell_test",
            name="Cast Spell Test Map",
            description="A small combat room.",
            width=8,
            height=8,
        ),
    )


class EncounterCastSpellTests(unittest.TestCase):
    def test_execute_find_steed_creates_spell_instance_and_summon_entity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.class_features["paladin"] = {"level": 5, "faithful_steed": {"free_cast_available": False}}
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="find_steed",
                cast_level=2,
                target_point={"x": 5, "y": 5, "anchor": "cell_center"},
                reason="Summon steed",
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            summon_ids = result["spell_instance"]["special_runtime"]["summon_entity_ids"]
            self.assertEqual(len(summon_ids), 1)
            summon_id = summon_ids[0]
            self.assertIn(summon_id, updated.entities)
            self.assertNotIn(summon_id, updated.turn_order)
            self.assertEqual(updated.entities[summon_id].position, {"x": 5, "y": 5})
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["2"]["remaining"], 0)
            encounter_repo.close()
            event_repo.close()

    def test_execute_find_steed_consumes_free_cast_before_spell_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.class_features["paladin"] = {"level": 5}
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="find_steed",
                cast_level=2,
                target_point={"x": 5, "y": 5, "anchor": "cell_center"},
                reason="Summon steed",
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            self.assertIsNone(result["slot_consumed"])
            self.assertFalse(updated.entities["ent_ally_eric_001"].class_features["paladin"]["faithful_steed"]["free_cast_available"])
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["2"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_find_steed_defaults_to_adjacent_open_space_when_target_point_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.class_features["paladin"] = {"level": 5, "faithful_steed": {"free_cast_available": False}}
            encounter.entities["ent_enemy_iron_duster_001"].position = {"x": 3, "y": 2}
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="find_steed",
                cast_level=2,
                reason="Summon steed",
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            summon_id = result["spell_instance"]["special_runtime"]["summon_entity_ids"][0]
            self.assertEqual(updated.entities[summon_id].position, {"x": 0, "y": 2})
            encounter_repo.close()
            event_repo.close()

    def test_execute_find_steed_rejects_target_point_beyond_thirty_feet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.class_features["paladin"] = {"level": 5, "faithful_steed": {"free_cast_available": False}}
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))

            with self.assertRaisesRegex(ValueError, "find_steed_target_point_out_of_range"):
                service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="find_steed",
                    cast_level=2,
                    target_point={"x": 9, "y": 2, "anchor": "cell_center"},
                    reason="Summon steed",
                )

            encounter_repo.close()
            event_repo.close()

    def test_execute_find_familiar_creates_spell_instance_and_summon_entity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            with patch("tools.services.spells.encounter_cast_spell.randint", return_value=12):
                result = service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="find_familiar",
                    cast_level=1,
                    target_point={"x": 3, "y": 2, "anchor": "cell_center"},
                    spell_options={"familiar_form": "pseudodragon"},
                    reason="Summon familiar",
                )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            summon_ids = result["spell_instance"]["special_runtime"]["summon_entity_ids"]
            self.assertEqual(len(summon_ids), 1)
            summon_id = summon_ids[0]
            self.assertIn(summon_id, updated.entities)
            self.assertEqual(updated.entities[summon_id].position, {"x": 3, "y": 2})
            self.assertEqual(updated.entities[summon_id].source_ref["familiar_form_id"], "pseudodragon")
            self.assertEqual(updated.entities[summon_id].initiative, 14)
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["1"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_find_familiar_defaults_to_adjacent_open_space_when_target_point_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter.entities["ent_enemy_iron_duster_001"].position = {"x": 3, "y": 2}
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            with patch("tools.services.spells.encounter_cast_spell.randint", return_value=10):
                result = service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="find_familiar",
                    cast_level=1,
                    spell_options={"familiar_form": "sprite"},
                    reason="Summon familiar",
                )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            summon_id = result["spell_instance"]["special_runtime"]["summon_entity_ids"][0]
            self.assertEqual(updated.entities[summon_id].position, {"x": 1, "y": 2})
            encounter_repo.close()
            event_repo.close()

    def test_execute_find_familiar_replaces_previous_familiar_from_same_caster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            with patch("tools.services.spells.encounter_cast_spell.randint", side_effect=[12, 11]):
                service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="find_familiar",
                    cast_level=1,
                    target_point={"x": 3, "y": 2, "anchor": "cell_center"},
                    spell_options={"familiar_form": "pseudodragon"},
                    reason="First familiar",
                )
                first_updated = encounter_repo.get("enc_cast_spell_test")
                self.assertIsNotNone(first_updated)
                first_summon_id = first_updated.spell_instances[0]["special_runtime"]["summon_entity_ids"][0]
                first_updated.entities["ent_ally_eric_001"].action_economy["action_used"] = False
                encounter_repo.save(first_updated)

                service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="find_familiar",
                    cast_level=1,
                    target_point={"x": 4, "y": 3, "anchor": "cell_center"},
                    spell_options={"familiar_form": "sprite"},
                    reason="Second familiar",
                )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            active_summon_ids = [entity_id for entity_id, entity in updated.entities.items() if entity.category == "summon"]
            self.assertEqual(len(active_summon_ids), 1)
            self.assertNotIn(first_summon_id, active_summon_ids)
            self.assertEqual(updated.spell_instances[0]["special_runtime"]["summon_entity_ids"], [])
            self.assertEqual(updated.spell_instances[1]["special_runtime"]["summon_entity_ids"], active_summon_ids)
            encounter_repo.close()
            event_repo.close()

    def test_execute_find_familiar_rejects_target_point_beyond_ten_feet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))

            with self.assertRaisesRegex(ValueError, "find_familiar_target_point_out_of_range"):
                service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="find_familiar",
                    cast_level=1,
                    target_point={"x": 5, "y": 2, "anchor": "cell_center"},
                    spell_options={"familiar_form": "sprite"},
                    reason="Summon familiar",
                )

            encounter_repo.close()
            event_repo.close()

    def test_execute_find_familiar_supports_normal_owl_form(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            with patch("tools.services.spells.encounter_cast_spell.randint", return_value=9):
                result = service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="find_familiar",
                    cast_level=1,
                    target_point={"x": 3, "y": 2, "anchor": "cell_center"},
                    spell_options={"familiar_form": "owl", "creature_type": "celestial"},
                    reason="Summon owl",
                )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            summon_id = result["spell_instance"]["special_runtime"]["summon_entity_ids"][0]
            summon = updated.entities[summon_id]
            self.assertEqual(summon.name, "Owl")
            self.assertEqual(summon.source_ref["familiar_form_id"], "owl")
            self.assertEqual(summon.source_ref["creature_type"], "celestial")
            self.assertEqual(summon.initiative, 10)
            encounter_repo.close()
            event_repo.close()

    def test_execute_find_familiar_requires_familiar_form(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))

            with self.assertRaisesRegex(ValueError, "find_familiar_requires_familiar_form"):
                service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="find_familiar",
                    cast_level=1,
                    reason="Summon familiar",
                )

            encounter_repo.close()
            event_repo.close()

    def test_execute_consumes_derived_multiclass_spell_slot_when_resources_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.resources = {}
            caster.class_features = {
                "ranger": {"level": 4},
                "sorcerer": {"level": 3},
            }
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="blindness_deafness",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=3,
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            self.assertEqual(result["slot_consumed"]["slot_level"], 3)
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["3"]["max"], 2)
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["3"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_consumes_derived_warlock_pact_magic_slot_when_resources_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.resources = {}
            caster.class_features = {
                "warlock": {"level": 5},
            }
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="blindness_deafness",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=3,
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            self.assertEqual(result["slot_consumed"]["slot_level"], 3)
            self.assertEqual(result["slot_consumed"]["resource_pool"], "pact_magic_slots")
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["pact_magic_slots"]["slot_level"], 3)
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["pact_magic_slots"]["max"], 2)
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["pact_magic_slots"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_rejects_spellcasting_in_untrained_armor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            armor_path = Path(tmp_dir) / "armor_definitions.json"
            armor_path.write_text(
                json.dumps(
                    {
                        "armor_definitions": {
                            "chain_mail": {
                                "armor_id": "chain_mail",
                                "name": "链甲",
                                "category": "heavy",
                                "ac": {"base": 16},
                                "strength_requirement": 13,
                                "stealth_disadvantage": True,
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            encounter = build_encounter()
            encounter.entities["ent_ally_eric_001"].equipped_armor = {"armor_id": "chain_mail"}
            encounter_repo.save(encounter)

            service = EncounterCastSpell(
                encounter_repo,
                AppendEvent(event_repo),
                armor_definition_repository=ArmorDefinitionRepository(armor_path),
            )

            with self.assertRaisesRegex(ValueError, "armor_training_required_for_spellcasting"):
                service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="blindness_deafness",
                    target_ids=["ent_enemy_iron_duster_001"],
                    cast_level=3,
                )

            encounter_repo.close()
            event_repo.close()

    def test_execute_sustained_area_spell_creates_zone_and_links_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                """
                {
                  "spell_definitions": {
                    "moonbeam": {
                      "id": "moonbeam",
                      "name": "Moonbeam",
                      "level": 2,
                      "base": {
                        "level": 2,
                        "casting_time": "1 action",
                        "concentration": true
                      },
                      "targeting": {
                        "type": "area_sphere",
                        "range_feet": 120,
                        "radius_feet": 5,
                        "allowed_target_types": ["creature"]
                      },
                      "area_template": {
                        "shape": "sphere",
                        "radius_feet": 5,
                        "render_mode": "circle_overlay",
                        "persistence": "sustained",
                        "zone_definition_id": "fire_burn_area"
                      },
                      "resolution": {
                        "mode": "save_damage",
                        "activation": "action"
                      }
                    }
                  }
                }
                """,
                encoding="utf-8",
            )
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.resources["spell_slots"]["2"] = {"max": 1, "remaining": 1}
            caster.spells.append({"spell_id": "moonbeam", "name": "Moonbeam", "level": 2})
            encounter_repo.save(encounter)

            service = EncounterCastSpell(
                encounter_repo,
                AppendEvent(event_repo),
                SpellDefinitionRepository(spell_repo_path),
            )
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="moonbeam",
                cast_level=2,
                target_point={"x": 6, "y": 6, "anchor": "cell_center"},
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            self.assertEqual(len(updated.map.zones), 1)
            self.assertEqual(updated.map.zones[0]["runtime"]["source_spell_id"], "moonbeam")
            self.assertEqual(updated.map.zones[0]["runtime"]["target_point"], {"x": 6, "y": 6, "anchor": "cell_center"})
            self.assertEqual(updated.spell_instances[0]["special_runtime"]["linked_zone_ids"], [updated.map.zones[0]["zone_id"]])
            self.assertEqual(result["spell_instance"]["special_runtime"]["linked_zone_ids"], [updated.map.zones[0]["zone_id"]])
            encounter_repo.close()
            event_repo.close()

    def test_execute_attaches_turn_effect_for_no_roll_hex_spell(self) -> None:
        """测试 Hex 这种无掷骰法术会直接把持续效果挂到目标身上。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="hex",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=1,
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            target = updated.entities["ent_enemy_iron_duster_001"]

            self.assertEqual(len(target.turn_effects), 1)
            self.assertEqual(target.turn_effects[0]["source_ref"], "hex")
            self.assertEqual(target.turn_effects[0]["source_entity_id"], "ent_ally_eric_001")
            self.assertEqual(result["turn_effect_updates"][0]["trigger"], "end_of_turn")
            self.assertEqual(len(updated.spell_instances), 1)
            self.assertEqual(updated.spell_instances[0]["spell_id"], "hex")
            self.assertEqual(updated.spell_instances[0]["targets"][0]["entity_id"], "ent_enemy_iron_duster_001")
            self.assertTrue(updated.spell_instances[0]["special_runtime"]["retargetable"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_attaches_turn_effect_for_no_roll_hunters_mark_spell(self) -> None:
        """测试 Hunter's Mark 也会直接把持续效果挂到目标身上。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="hunters_mark",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=1,
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            target = updated.entities["ent_enemy_iron_duster_001"]

            self.assertEqual(len(target.turn_effects), 1)
            self.assertEqual(target.turn_effects[0]["source_ref"], "hunters_mark")
            self.assertEqual(target.turn_effects[0]["source_entity_id"], "ent_ally_eric_001")
            self.assertEqual(result["turn_effect_updates"][0]["trigger"], "end_of_turn")
            self.assertEqual(len(updated.spell_instances), 1)
            self.assertEqual(updated.spell_instances[0]["spell_id"], "hunters_mark")
            self.assertEqual(updated.spell_instances[0]["targets"][0]["entity_id"], "ent_enemy_iron_duster_001")
            self.assertTrue(updated.spell_instances[0]["special_runtime"]["retargetable"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_consumes_ranger_favored_enemy_free_cast_before_spell_slot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.class_features["ranger"] = {"level": 1}
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="hunters_mark",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=1,
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            self.assertIsNone(result["slot_consumed"])
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["1"]["remaining"], 2)
            self.assertEqual(
                updated.entities["ent_ally_eric_001"].class_features["ranger"]["favored_enemy"]["free_cast_uses_remaining"],
                1,
            )
            encounter_repo.close()
            event_repo.close()

    def test_execute_uses_foe_slayer_damage_die_for_hunters_mark_at_level_twenty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_ally_eric_001"]
            caster.class_features["ranger"] = {"level": 20}
            encounter_repo.save(encounter)

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="hunters_mark",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=1,
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            self.assertIsNotNone(updated)
            target = updated.entities["ent_enemy_iron_duster_001"]
            self.assertEqual(target.turn_effects[0]["attack_bonus_damage_parts"][0]["formula"], "1d10")
            encounter_repo.close()
            event_repo.close()

    def test_execute_reads_spell_definition_from_global_repository(self) -> None:
        """测试施法声明可以直接从全局法术知识库读取模板。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="fireball",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=3,
            )

            self.assertEqual(result["spell_id"], "fireball")
            self.assertEqual(result["spell_name"], "Fireball")
            self.assertEqual(result["spell_level"], 3)
            encounter_repo.close()
            event_repo.close()

    def test_execute_consumes_spell_slot_and_appends_event(self) -> None:
        """测试非戏法施法会扣法术位并写入 spell_declared 事件。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="blindness_deafness",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=3,
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["3"]["remaining"], 0)
            self.assertEqual(result["slot_consumed"]["slot_level"], 3)
            self.assertEqual(event_repo.list_by_encounter("enc_cast_spell_test")[0].event_type, "spell_declared")
            encounter_repo.close()
            event_repo.close()

    def test_execute_does_not_consume_slot_for_cantrip(self) -> None:
        """测试戏法施放不会扣除法术位。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="fire_bolt",
                target_ids=["ent_enemy_iron_duster_001"],
            )

            updated = encounter_repo.get("enc_cast_spell_test")
            assert updated is not None
            self.assertEqual(updated.entities["ent_ally_eric_001"].resources["spell_slots"]["1"]["remaining"], 2)
            self.assertIsNone(result["slot_consumed"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_rejects_missing_slot_level(self) -> None:
        """测试如果指定的施法等级没有对应法术位，会直接报错。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            with self.assertRaises(ValueError):
                service.execute(
                    encounter_id="enc_cast_spell_test",
                    spell_id="blindness_deafness",
                    target_ids=["ent_enemy_iron_duster_001"],
                    cast_level=4,
                )
            encounter_repo.close()
            event_repo.close()

    def test_execute_can_include_latest_encounter_state(self) -> None:
        """测试施法声明结果里可以附带最新前端状态。"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
            event_repo = EventRepository(Path(tmp_dir) / "events.json")
            encounter_repo.save(build_encounter())

            service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
            result = service.execute(
                encounter_id="enc_cast_spell_test",
                spell_id="blindness_deafness",
                target_ids=["ent_enemy_iron_duster_001"],
                cast_level=3,
                include_encounter_state=True,
            )

            self.assertIn("encounter_state", result)
            current = result["encounter_state"]["current_turn_entity"]
            self.assertEqual(current["id"], "ent_ally_eric_001")
            self.assertEqual(current["resources"]["summary"], "法术位：1环 2/2, 2环 1/1, 3环 0/1")
            encounter_repo.close()
            event_repo.close()
