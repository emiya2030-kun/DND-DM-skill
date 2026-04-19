"""ExecuteSpell 骨架测试。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository, SpellDefinitionRepository
from tools.services import AppendEvent, ExecuteSpell, SpellRequest


def build_caster() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_caster_001",
        name="Task3 Wizard",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=12,
        source_ref={"caster_level": 7, "entity_type": "humanoid"},
        resources={"spell_slots": {"3": {"max": 1, "remaining": 1}}},
        spells=[
            {
                "spell_id": "fireball",
                "name": "Fireball",
                "level": 3,
            }
        ],
    )


def build_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_001",
        name="Bandit",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 2, "y": 1},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=8,
        source_ref={"entity_type": "humanoid"},
    )


def build_encounter() -> Encounter:
    caster = build_caster()
    target = build_target()
    return Encounter(
        encounter_id="enc_execute_spell_test",
        name="Execute Spell Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, target.entity_id],
        entities={caster.entity_id: caster, target.entity_id: target},
        map=EncounterMap(
            map_id="map_execute_spell_test",
            name="Execute Spell Map",
            description="Minimal map for execute spell tests.",
            width=4,
            height=4,
        ),
    )


def build_fireball_save_damage_encounter() -> Encounter:
    caster = EncounterEntity(
        entity_id="ent_fireball_caster_001",
        name="Fireball Wizard",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 5, "y": 5},
        hp={"current": 30, "max": 30, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        source_ref={"caster_level": 7, "spellcasting_ability": "int", "entity_type": "humanoid"},
        ability_mods={"int": 4},
        proficiency_bonus=3,
        resources={"spell_slots": {"3": {"max": 1, "remaining": 1}, "4": {"max": 1, "remaining": 1}}},
        spells=[
            {
                "spell_id": "fireball",
                "name": "Fireball",
                "level": 3,
            }
        ],
    )
    failed_target = EncounterEntity(
        entity_id="ent_fireball_target_failed_001",
        name="Failed Save Target",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 8, "y": 5},
        hp={"current": 40, "max": 40, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        source_ref={"entity_type": "humanoid"},
        ability_mods={"dex": 2},
        proficiency_bonus=2,
        save_proficiencies=[],
    )
    success_target = EncounterEntity(
        entity_id="ent_fireball_target_success_001",
        name="Successful Save Target",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 5, "y": 9},
        hp={"current": 40, "max": 40, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=9,
        source_ref={"entity_type": "humanoid"},
        ability_mods={"dex": 2},
        proficiency_bonus=2,
        save_proficiencies=[],
    )
    return Encounter(
        encounter_id="enc_execute_fireball_save_damage_test",
        name="Execute Fireball Save Damage Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, failed_target.entity_id, success_target.entity_id],
        entities={
            caster.entity_id: caster,
            failed_target.entity_id: failed_target,
            success_target.entity_id: success_target,
        },
        map=EncounterMap(
            map_id="map_execute_fireball_save_damage_test",
            name="Fireball Save Damage Map",
            description="Map for fireball save-damage execute test.",
            width=20,
            height=20,
        ),
    )


def build_hold_person_save_condition_encounter() -> Encounter:
    caster = EncounterEntity(
        entity_id="ent_hold_person_caster_001",
        name="Hold Person Wizard",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 5, "y": 5},
        hp={"current": 30, "max": 30, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        source_ref={"caster_level": 7, "spellcasting_ability": "int", "entity_type": "humanoid"},
        ability_mods={"int": 4},
        proficiency_bonus=3,
        resources={"spell_slots": {"3": {"max": 1, "remaining": 1}}},
        spells=[
            {
                "spell_id": "hold_person",
                "name": "Hold Person",
                "level": 2,
            }
        ],
    )
    first_target = EncounterEntity(
        entity_id="ent_hold_person_target_001",
        name="Bandit Captain",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 8, "y": 5},
        hp={"current": 40, "max": 40, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        source_ref={"entity_type": "humanoid"},
        ability_mods={"wis": 0},
        proficiency_bonus=2,
        save_proficiencies=[],
    )
    second_target = EncounterEntity(
        entity_id="ent_hold_person_target_002",
        name="Cult Fanatic",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 6, "y": 7},
        hp={"current": 35, "max": 35, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=9,
        source_ref={"entity_type": "humanoid"},
        ability_mods={"wis": 1},
        proficiency_bonus=2,
        save_proficiencies=[],
    )
    return Encounter(
        encounter_id="enc_execute_hold_person_save_condition_test",
        name="Execute Hold Person Save Condition Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, first_target.entity_id, second_target.entity_id],
        entities={
            caster.entity_id: caster,
            first_target.entity_id: first_target,
            second_target.entity_id: second_target,
        },
        map=EncounterMap(
            map_id="map_execute_hold_person_save_condition_test",
            name="Hold Person Save Condition Map",
            description="Map for hold person save-condition execute test.",
            width=20,
            height=20,
        ),
    )


def build_eldritch_blast_attack_encounter(*, actor_level: int = 5) -> Encounter:
    caster = EncounterEntity(
        entity_id="ent_eldritch_caster_001",
        name="Eldritch Warlock",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 5, "y": 5},
        hp={"current": 24, "max": 24, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=16,
        source_ref={"caster_level": actor_level, "spellcasting_ability": "cha", "entity_type": "humanoid"},
        ability_mods={"cha": 4},
        proficiency_bonus=3,
        spells=[
            {
                "spell_id": "eldritch_blast",
                "name": "Eldritch Blast",
                "level": 0,
            }
        ],
    )
    first_target = EncounterEntity(
        entity_id="ent_eldritch_target_001",
        name="Bandit Acolyte",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 8, "y": 5},
        hp={"current": 12, "max": 12, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        source_ref={"entity_type": "humanoid"},
    )
    second_target = EncounterEntity(
        entity_id="ent_eldritch_target_002",
        name="Bandit Guard",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 7, "y": 7},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=9,
        source_ref={"entity_type": "humanoid"},
    )
    return Encounter(
        encounter_id="enc_execute_eldritch_blast_attack_test",
        name="Execute Eldritch Blast Attack Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, first_target.entity_id, second_target.entity_id],
        entities={
            caster.entity_id: caster,
            first_target.entity_id: first_target,
            second_target.entity_id: second_target,
        },
        map=EncounterMap(
            map_id="map_execute_eldritch_blast_attack_test",
            name="Eldritch Blast Attack Map",
            description="Map for eldritch blast execute test.",
            width=20,
            height=20,
        ),
    )


def write_fireball_save_damage_spell_definition(
    spell_repo_path: Path, *, allowed_target_types: list[str] | None = None
) -> None:
    spell_repo_path.write_text(
        json.dumps(
            {
                "spell_definitions": {
                    "fireball": {
                        "id": "fireball",
                        "name": "Fireball",
                        "level": 3,
                        "base": {
                            "level": 3,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "resolution": {"mode": "save_damage", "activation": "action"},
                        "targeting": {
                            "type": "area_sphere",
                            "range_feet": 150,
                            "radius_feet": 20,
                            "allowed_target_types": allowed_target_types or ["creature"],
                        },
                        "area_template": {
                            "shape": "sphere",
                            "radius_feet": 20,
                            "render_mode": "circle_overlay",
                            "persistence": "instant",
                        },
                        "save_ability": "dex",
                        "on_cast": {
                            "on_failed_save": {
                                "damage_parts": [
                                    {
                                        "source": "spell:fireball:failed:part_0",
                                        "formula": "8d6",
                                        "damage_type": "fire",
                                    }
                                ]
                            },
                            "on_successful_save": {
                                "damage_parts_mode": "same_as_failed",
                                "damage_multiplier": 0.5,
                            },
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def write_hold_person_save_condition_spell_definition(spell_repo_path: Path) -> None:
    spell_repo_path.write_text(
        json.dumps(
            {
                "spell_definitions": {
                    "hold_person": {
                        "id": "hold_person",
                        "name": "Hold Person",
                        "level": 2,
                        "base": {
                            "level": 2,
                            "casting_time": "1 action",
                            "concentration": True,
                        },
                        "resolution": {"mode": "save", "activation": "action"},
                        "targeting": {
                            "type": "single_target",
                            "allowed_target_types": ["humanoid"],
                        },
                        "save_ability": "wis",
                        "on_cast": {
                            "on_failed_save": {
                                "damage_parts": [],
                                "apply_conditions": ["paralyzed"],
                                "apply_turn_effects": [
                                    {
                                        "effect_template_id": "hold_person_repeat_save",
                                    }
                                ],
                                "note": None,
                            },
                            "on_successful_save": {
                                "damage_parts": [],
                                "apply_conditions": [],
                                "apply_turn_effects": [],
                                "note": None,
                            },
                        },
                        "effect_templates": {
                            "hold_person_repeat_save": {
                                "name": "Hold Person Ongoing Save",
                                "trigger": "end_of_turn",
                                "save": {
                                    "ability": "wis",
                                    "dc_mode": "caster_spell_dc",
                                    "on_success_remove_effect": True,
                                },
                                "on_trigger": {
                                    "damage_parts": [],
                                    "apply_conditions": [],
                                    "remove_conditions": [],
                                },
                                "on_save_success": {
                                    "damage_parts": [],
                                    "apply_conditions": [],
                                    "remove_conditions": ["paralyzed"],
                                },
                                "on_save_failure": {
                                    "damage_parts": [],
                                    "apply_conditions": [],
                                    "remove_conditions": [],
                                },
                                "remove_after_trigger": False,
                            }
                        },
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_level_bonus": {
                                "base_slot_level": 2,
                                "additional_targets_per_extra_level": 1,
                            },
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def write_eldritch_blast_attack_spell_definition(spell_repo_path: Path) -> None:
    spell_repo_path.write_text(
        json.dumps(
            {
                "spell_definitions": {
                    "eldritch_blast": {
                        "id": "eldritch_blast",
                        "name": "Eldritch Blast",
                        "level": 0,
                        "base": {
                            "level": 0,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "requires_attack_roll": True,
                        "resolution": {"mode": "attack_roll", "activation": "action"},
                        "targeting": {
                            "type": "single_target",
                            "range_feet": 120,
                            "allowed_target_types": ["creature"],
                        },
                        "on_cast": {
                            "on_hit": {
                                "damage_parts": [
                                    {
                                        "source": "spell:eldritch_blast:on_hit:part_0",
                                        "formula": "1d10",
                                        "damage_type": "force",
                                    }
                                ]
                            },
                            "on_miss": {
                                "damage_parts": []
                            },
                        },
                        "scaling": {
                            "cantrip_by_level": [
                                {"caster_level": 1, "beam_count": 1},
                                {"caster_level": 5, "beam_count": 2},
                                {"caster_level": 11, "beam_count": 3},
                                {"caster_level": 17, "beam_count": 4},
                            ]
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def write_ray_of_dread_attack_spell_definition(spell_repo_path: Path) -> None:
    spell_repo_path.write_text(
        json.dumps(
            {
                "spell_definitions": {
                    "ray_of_dread": {
                        "id": "ray_of_dread",
                        "name": "Ray of Dread",
                        "level": 1,
                        "base": {
                            "level": 1,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "requires_attack_roll": True,
                        "resolution": {"mode": "attack_roll", "activation": "action"},
                        "targeting": {
                            "type": "single_target",
                            "range_feet": 15,
                            "requires_line_of_sight": True,
                            "allowed_target_types": ["creature"],
                        },
                        "on_cast": {
                            "on_hit": {
                                "damage_parts": [
                                    {
                                        "source": "spell:ray_of_dread:on_hit:part_0",
                                        "formula": "2d8",
                                        "damage_type": "necrotic",
                                    }
                                ]
                            },
                            "on_miss": {"damage_parts": []},
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def write_chromatic_orb_attack_spell_definition(spell_repo_path: Path) -> None:
    spell_repo_path.write_text(
        json.dumps(
            {
                "spell_definitions": {
                    "chromatic_orb": {
                        "id": "chromatic_orb",
                        "name": "Chromatic Orb",
                        "level": 1,
                        "base": {
                            "level": 1,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "requires_attack_roll": True,
                        "resolution": {"mode": "attack_roll", "activation": "action"},
                        "targeting": {
                            "type": "single_target",
                            "range_feet": 90,
                            "allowed_target_types": ["creature"],
                        },
                        "on_cast": {
                            "on_hit": {
                                "damage_parts": [
                                    {
                                        "source": "spell:chromatic_orb:on_hit:part_0",
                                        "formula": "3d8",
                                        "damage_type": "fire",
                                    }
                                ]
                            },
                            "on_miss": {"damage_parts": []},
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )


class ExecuteSpellTests(unittest.TestCase):
    def test_execute_rejects_second_slot_spending_spell_in_same_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "fireball": {
                                "id": "fireball",
                                "name": "Fireball",
                                "level": 3,
                                "base": {"level": 3, "casting_time": "1 action", "concentration": False},
                                "resolution": {"mode": "save", "save_ability": "dex", "activation": "action"},
                                "targeting": {
                                    "type": "area_sphere",
                                    "range_feet": 150,
                                    "shape": "sphere",
                                    "radius_feet": 20,
                                    "allowed_target_types": ["creature"],
                                },
                                "failed_save_outcome": {
                                    "damage_parts": [
                                        {"source": "spell:fireball:failed:part_0", "formula": "8d6", "damage_type": "fire"}
                                    ],
                                    "conditions": [],
                                    "note": None,
                                },
                                "successful_save_outcome": {
                                    "damage_parts_mode": "same_as_failed",
                                    "damage_multiplier": 0.5,
                                    "conditions": [],
                                    "note": None,
                                },
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            encounter = build_encounter()
            encounter.entities["ent_caster_001"].action_economy["spell_slot_cast_used_this_turn"] = True
            encounter_repo.save(encounter)

            with self.assertRaisesRegex(ValueError, "spell_slot_cast_already_used_this_turn"):
                ExecuteSpell(
                    encounter_repository=encounter_repo,
                    append_event=AppendEvent(event_repo),
                    spell_request=SpellRequest(encounter_repo, SpellDefinitionRepository(spell_repo_path)),
                ).execute(
                    encounter_id="enc_execute_spell_test",
                    actor_id="ent_caster_001",
                    spell_id="fireball",
                    cast_level=3,
                    target_point={"x": 2, "y": 1, "anchor": "cell_center"},
                    declared_action_cost="action",
                    save_rolls={"ent_target_001": {"base_roll": 8}},
                    damage_rolls=[{"source": "spell:fireball:failed:part_0", "rolls": [6, 5, 4, 3, 2, 1, 6, 5]}],
                )

            encounter_repo.close()
            event_repo.close()

    def test_execute_healing_word_auto_rolls_upcast_and_caps_at_max_hp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            target = encounter.entities["ent_target_001"]
            caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
            caster.resources["spell_slots"]["1"] = {"max": 2, "remaining": 2}
            caster.resources["spell_slots"]["2"] = {"max": 1, "remaining": 1}
            caster.source_ref["spellcasting_ability"] = "int"
            caster.ability_mods["int"] = 3
            target.hp["current"] = 2
            encounter_repo.save(encounter)

            service = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo),
            )
            with patch("tools.services.spells.execute_spell.random.randint", side_effect=[1, 2, 3, 4]):
                result = service.execute(
                    encounter_id="enc_execute_spell_test",
                    actor_id="ent_caster_001",
                    spell_id="healing_word",
                    cast_level=2,
                    target_entity_ids=["ent_target_001"],
                    declared_action_cost="bonus_action",
                )

            updated = encounter_repo.get("enc_execute_spell_test")
            assert updated is not None
            self.assertEqual(result["spell_resolution"]["mode"], "heal")
            self.assertEqual(result["spell_resolution"]["target_id"], "ent_target_001")
            self.assertEqual(result["spell_resolution"]["healing_total"], 13)
            self.assertEqual(result["spell_resolution"]["hp_update"]["event_type"], "healing_applied")
            self.assertEqual(result["spell_resolution"]["hp_update"]["hp_after"], 12)
            self.assertEqual(updated.entities["ent_target_001"].hp["current"], 12)
            self.assertEqual(updated.entities["ent_caster_001"].resources["spell_slots"]["2"]["remaining"], 0)
            self.assertTrue(updated.entities["ent_caster_001"].action_economy["bonus_action_used"])
            encounter_repo.close()
            event_repo.close()

    def test_execute_healing_word_blocks_on_dead_target_but_still_casts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            target = encounter.entities["ent_target_001"]
            caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
            caster.resources["spell_slots"]["1"] = {"max": 2, "remaining": 2}
            caster.source_ref["spellcasting_ability"] = "int"
            caster.ability_mods["int"] = 3
            target.hp["current"] = 0
            target.combat_flags["is_dead"] = True
            encounter_repo.save(encounter)

            service = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo),
            )
            with patch("tools.services.spells.execute_spell.random.randint", side_effect=[2, 2]):
                result = service.execute(
                    encounter_id="enc_execute_spell_test",
                    actor_id="ent_caster_001",
                    spell_id="healing_word",
                    cast_level=1,
                    target_entity_ids=["ent_target_001"],
                    declared_action_cost="bonus_action",
                )

            updated = encounter_repo.get("enc_execute_spell_test")
            assert updated is not None
            self.assertEqual(result["resource_update"]["remaining_after"], 1)
            self.assertEqual(result["spell_resolution"]["hp_update"]["event_type"], "hp_unchanged")
            self.assertEqual(
                result["spell_resolution"]["hp_update"]["healing_blocked_reason"],
                "target_is_dead",
            )
            self.assertEqual(updated.entities["ent_target_001"].hp["current"], 0)
            encounter_repo.close()
            event_repo.close()

    def test_execute_seeking_spell_rerolls_missed_spell_attack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_chromatic_orb_attack_spell_definition(spell_repo_path)
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            caster.class_features["sorcerer"] = {
                "level": 5,
                "sorcery_points": {"max": 5, "current": 5},
                "metamagic": {"known_options": ["seeking_spell"]},
            }
            caster.resources["spell_slots"]["1"] = {"max": 2, "remaining": 2}
            caster.spells.append(
                {"spell_id": "chromatic_orb", "name": "Chromatic Orb", "level": 1, "casting_class": "sorcerer"}
            )
            encounter_repo.save(encounter)

            service = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, SpellDefinitionRepository(spell_repo_path)),
            )
            with patch("tools.services.spells.execute_spell.random.randint", return_value=17):
                result = service.execute(
                    encounter_id="enc_execute_spell_test",
                    actor_id="ent_caster_001",
                    spell_id="chromatic_orb",
                    cast_level=1,
                    target_entity_ids=["ent_target_001"],
                    declared_action_cost="action",
                    metamagic_options={"selected": ["seeking_spell"]},
                    attack_rolls=[
                        {
                            "final_total": 8,
                            "dice_rolls": {
                                "base_rolls": [5],
                                "chosen_roll": 5,
                                "modifier": 3,
                            },
                        }
                    ],
                    damage_rolls=[
                        [{"source": "spell:chromatic_orb:on_hit:part_0", "rolls": [8, 7, 6]}]
                    ],
                )

            updated = encounter_repo.get("enc_execute_spell_test")
            assert updated is not None
            self.assertTrue(result["spell_resolution"]["targets"][0]["attack"]["hit"])
            self.assertEqual(
                updated.entities["ent_caster_001"].class_features["sorcerer"]["sorcery_points"]["current"],
                4,
            )
            encounter_repo.close()
            event_repo.close()

    def test_execute_allows_out_of_turn_reaction_spell_and_spends_reaction_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "shield": {
                                "id": "shield",
                                "name": "Shield",
                                "level": 1,
                                "base": {"level": 1, "casting_time": "1 reaction", "concentration": False},
                                "resolution": {"mode": "no_roll", "activation": "reaction"},
                                "targeting": {"type": "self", "allowed_target_types": ["self"]},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            caster.spells.append({"spell_id": "shield", "name": "Shield", "level": 1})
            caster.resources["spell_slots"]["1"] = {"max": 2, "remaining": 2}
            caster.action_economy = {"action_used": False, "bonus_action_used": False, "reaction_used": False}
            encounter.current_entity_id = "ent_target_001"
            encounter.turn_order = ["ent_target_001", "ent_caster_001"]
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="shield",
                cast_level=1,
                declared_action_cost="reaction",
                allow_out_of_turn_actor=True,
            )

            self.assertEqual(result["spell_resolution"]["mode"], "apply_spell_instance")
            updated = encounter_repo.get("enc_execute_spell_test")
            self.assertFalse(updated.entities["ent_caster_001"].action_economy["action_used"])
            self.assertFalse(updated.entities["ent_caster_001"].action_economy["bonus_action_used"])
            self.assertTrue(updated.entities["ent_caster_001"].action_economy["reaction_used"])
            self.assertEqual(updated.entities["ent_caster_001"].resources["spell_slots"]["1"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_allows_reaction_spell_even_after_spell_slot_cast_used_this_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "shield": {
                                "id": "shield",
                                "name": "Shield",
                                "level": 1,
                                "base": {"level": 1, "casting_time": "1 reaction", "concentration": False},
                                "resolution": {"mode": "no_roll", "activation": "reaction"},
                                "targeting": {"type": "self", "allowed_target_types": ["self"]},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            caster.spells.append({"spell_id": "shield", "name": "Shield", "level": 1})
            caster.resources["spell_slots"]["1"] = {"max": 2, "remaining": 2}
            caster.action_economy = {
                "action_used": False,
                "bonus_action_used": False,
                "reaction_used": False,
                "spell_slot_cast_used_this_turn": True,
            }
            encounter.current_entity_id = "ent_target_001"
            encounter.turn_order = ["ent_target_001", "ent_caster_001"]
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="shield",
                cast_level=1,
                declared_action_cost="reaction",
                allow_out_of_turn_actor=True,
            )

            self.assertEqual(result["spell_resolution"]["mode"], "apply_spell_instance")
            updated = encounter_repo.get("enc_execute_spell_test")
            self.assertTrue(updated.entities["ent_caster_001"].action_economy["spell_slot_cast_used_this_turn"])
            self.assertTrue(updated.entities["ent_caster_001"].action_economy["reaction_used"])
            self.assertEqual(updated.entities["ent_caster_001"].resources["spell_slots"]["1"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_rejects_out_of_turn_non_reaction_spell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "magic_missile": {
                                "id": "magic_missile",
                                "name": "Magic Missile",
                                "level": 1,
                                "base": {"level": 1, "casting_time": "1 action", "concentration": False},
                                "resolution": {"mode": "no_roll", "activation": "action"},
                                "targeting": {"type": "single_target", "allowed_target_types": ["creature"]},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            caster.spells.append({"spell_id": "magic_missile", "name": "Magic Missile", "level": 1})
            caster.resources["spell_slots"]["1"] = {"max": 2, "remaining": 2}
            encounter.current_entity_id = "ent_target_001"
            encounter.turn_order = ["ent_target_001", "ent_caster_001"]
            encounter_repo.save(encounter)

            with self.assertRaisesRegex(ValueError, "out_of_turn_cast_requires_reaction"):
                ExecuteSpell(
                    encounter_repository=encounter_repo,
                    append_event=AppendEvent(event_repo),
                    spell_request=SpellRequest(encounter_repo, spell_repo),
                ).execute(
                    encounter_id="enc_execute_spell_test",
                    actor_id="ent_caster_001",
                    spell_id="magic_missile",
                    cast_level=1,
                    target_entity_ids=["ent_target_001"],
                    declared_action_cost="action",
                    allow_out_of_turn_actor=True,
                )

    def test_execute_declares_spell_and_returns_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "fireball": {
                                "id": "fireball",
                                "name": "Fireball",
                                "level": 3,
                                "base": {
                                    "level": 3,
                                    "casting_time": "1 action",
                                    "concentration": False,
                                },
                                "resolution": {"activation": "action"},
                                "targeting": {"type": "area_sphere", "allowed_target_types": ["creature"]},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter_repo.save(build_encounter())

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="fireball",
                cast_level=3,
                target_entity_ids=["ent_target_001"],
                target_point={"x": 2, "y": 2},
                declared_action_cost="action",
            )

            self.assertEqual(result["encounter_id"], "enc_execute_spell_test")
            self.assertEqual(result["actor_id"], "ent_caster_001")
            self.assertEqual(result["spell_id"], "fireball")
            self.assertEqual(result["cast_level"], 3)
            self.assertEqual(result["resource_update"]["slot_level"], 3)
            self.assertEqual(result["spell_resolution"]["mode"], "declared_only")
            self.assertIn("encounter_state", result)
            encounter_repo.close()
            event_repo.close()

    def test_execute_returns_waiting_reaction_when_counterspell_window_opens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "fireball": {
                                "id": "fireball",
                                "name": "Fireball",
                                "level": 3,
                                "base": {
                                    "level": 3,
                                    "casting_time": "1 action",
                                    "concentration": False,
                                },
                                "resolution": {"activation": "action"},
                                "targeting": {"type": "area_sphere", "allowed_target_types": ["creature"]},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_encounter()
            counterspeller = EncounterEntity(
                entity_id="ent_counter_001",
                name="Counter Mage",
                side="enemy",
                category="npc",
                controller="gm",
                position={"x": 2, "y": 2},
                hp={"current": 12, "max": 12, "temp": 0},
                ac=12,
                speed={"walk": 30, "remaining": 30},
                initiative=9,
                action_economy={"reaction_used": False},
                resources={"spell_slots": {"3": {"max": 1, "remaining": 1}}},
                spells=[{"spell_id": "counterspell", "name": "Counterspell", "level": 3}],
            )
            encounter.entities[counterspeller.entity_id] = counterspeller
            encounter.turn_order.append(counterspeller.entity_id)
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="fireball",
                cast_level=3,
                target_entity_ids=["ent_target_001"],
                target_point={"x": 2, "y": 2},
                declared_action_cost="action",
            )

            self.assertEqual(result["status"], "waiting_reaction")
            self.assertEqual(result["pending_reaction_window"]["trigger_type"], "spell_declared")
            encounter_repo.close()
            event_repo.close()

    def test_execute_returns_spell_request_error_without_declaring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "fireball": {
                                "id": "fireball",
                                "name": "Fireball",
                                "level": 3,
                                "base": {
                                    "level": 3,
                                    "casting_time": "1 action",
                                    "concentration": False,
                                },
                                "resolution": {"activation": "action"},
                                "targeting": {"type": "area_sphere", "allowed_target_types": ["creature"]},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter_repo.save(build_encounter())

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="unknown_spell",
                cast_level=3,
                target_entity_ids=["ent_target_001"],
                target_point={"x": 2, "y": 2},
                declared_action_cost="action",
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "spell_not_known")
            self.assertEqual(len(event_repo.list_all()), 0)
            caster = encounter_repo.get("enc_execute_spell_test").entities["ent_caster_001"]
            self.assertEqual(caster.resources["spell_slots"]["3"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_hex_applies_turn_effect_and_spell_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "hex": {
                                "id": "hex",
                                "name": "Hex (Temp Repo)",
                                "level": 1,
                                "base": {
                                    "level": 1,
                                    "casting_time": "bonus action",
                                    "concentration": True,
                                },
                                "resolution": {
                                    "mode": "no_roll",
                                    "activation": "bonus_action",
                                },
                                "targeting": {
                                    "type": "single_target",
                                    "allowed_target_types": ["creature"],
                                },
                                "on_cast": {
                                    "on_resolve": {
                                        "apply_turn_effects": [
                                            {"effect_template_id": "hex_mark"}
                                        ]
                                    }
                                },
                                "effect_templates": {
                                    "hex_mark": {
                                        "name": "Hexed",
                                        "trigger": "end_of_turn",
                                    }
                                },
                                "special_rules": {
                                    "retarget_on_target_drop_to_zero": {
                                        "enabled": True,
                                        "activation": "bonus_action",
                                    }
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_encounter()
            encounter.entities["ent_caster_001"].spells.append(
                {
                    "spell_id": "hex",
                    "name": "Hex On Actor",
                    "level": 2,
                }
            )
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="hex",
                cast_level=3,
                target_entity_ids=["ent_target_001"],
                declared_action_cost="bonus_action",
            )

            self.assertEqual(result["spell_resolution"]["mode"], "apply_spell_instance")
            self.assertEqual(result["spell_resolution"]["resolution_mode"], "apply_spell_instance")
            self.assertEqual(result["resource_update"]["slot_level"], 3)
            updated = encounter_repo.get("enc_execute_spell_test")
            self.assertEqual(len(updated.entities["ent_target_001"].turn_effects), 1)
            self.assertEqual(updated.entities["ent_target_001"].turn_effects[0]["source_ref"], "hex")
            self.assertEqual(len(updated.spell_instances), 1)
            self.assertEqual(updated.spell_instances[0]["spell_id"], "hex")
            self.assertEqual(updated.spell_instances[0]["targets"][0]["entity_id"], "ent_target_001")
            self.assertTrue(updated.spell_instances[0]["special_runtime"]["retargetable"])

            event = event_repo.list_by_encounter("enc_execute_spell_test")[0]
            self.assertEqual(event.payload["spell_name"], "Hex (Temp Repo)")
            self.assertEqual(event.payload["spell_level"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_hunters_mark_applies_turn_effect_and_spell_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "hunters_mark": {
                                "id": "hunters_mark",
                                "name": "Hunter's Mark (Temp Repo)",
                                "level": 1,
                                "base": {
                                    "level": 1,
                                    "casting_time": "bonus action",
                                    "concentration": True,
                                },
                                "resolution": {
                                    "mode": "no_roll",
                                    "activation": "bonus_action",
                                },
                                "targeting": {
                                    "type": "single_target",
                                    "allowed_target_types": ["creature"],
                                },
                                "on_cast": {
                                    "on_resolve": {
                                        "apply_turn_effects": [
                                            {"effect_template_id": "hunters_mark"}
                                        ]
                                    }
                                },
                                "effect_templates": {
                                    "hunters_mark": {
                                        "name": "Hunter's Marked",
                                        "trigger": "end_of_turn",
                                        "attack_bonus_damage_parts": [
                                            {
                                                "source": "spell:hunters_mark:bonus_damage",
                                                "formula": "1d6",
                                                "damage_type": "force",
                                            }
                                        ],
                                    }
                                },
                                "special_rules": {
                                    "retarget_on_target_drop_to_zero": {
                                        "enabled": True,
                                        "activation": "bonus_action",
                                    }
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_encounter()
            encounter.entities["ent_caster_001"].spells.append(
                {
                    "spell_id": "hunters_mark",
                    "name": "Hunter's Mark On Actor",
                    "level": 1,
                }
            )
            encounter.entities["ent_caster_001"].resources["spell_slots"]["1"] = {"max": 1, "remaining": 1}
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="hunters_mark",
                cast_level=1,
                target_entity_ids=["ent_target_001"],
                declared_action_cost="bonus_action",
            )

            self.assertEqual(result["spell_resolution"]["mode"], "apply_spell_instance")
            self.assertEqual(result["spell_resolution"]["resolution_mode"], "apply_spell_instance")
            self.assertEqual(result["resource_update"]["slot_level"], 1)
            updated = encounter_repo.get("enc_execute_spell_test")
            self.assertEqual(len(updated.entities["ent_target_001"].turn_effects), 1)
            self.assertEqual(updated.entities["ent_target_001"].turn_effects[0]["source_ref"], "hunters_mark")
            self.assertEqual(len(updated.spell_instances), 1)
            self.assertEqual(updated.spell_instances[0]["spell_id"], "hunters_mark")
            self.assertEqual(updated.spell_instances[0]["targets"][0]["entity_id"], "ent_target_001")
            encounter_repo.close()
            event_repo.close()

    def test_execute_disguise_self_defaults_to_self_target_and_projects_disguise_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "disguise_self": {
                                "id": "disguise_self",
                                "name": "Disguise Self",
                                "level": 1,
                                "base": {
                                    "level": 1,
                                    "casting_time": "1 action",
                                    "concentration": False,
                                },
                                "resolution": {
                                    "mode": "no_roll",
                                    "activation": "action",
                                },
                                "targeting": {
                                    "type": "self",
                                    "allowed_target_types": ["creature"],
                                },
                                "on_cast": {
                                    "on_resolve": {
                                        "apply_turn_effects": [
                                            {"effect_template_id": "disguise_self_effect"}
                                        ]
                                    }
                                },
                                "effect_templates": {
                                    "disguise_self_effect": {
                                        "name": "Disguise Self",
                                        "effect_type": "disguise_self",
                                        "trigger": "end_of_turn",
                                        "duration_model": "until_long_rest",
                                        "disguise_profile": {
                                            "appearance_name": "Town Guard",
                                            "height_delta_feet": 1,
                                            "body_shape": "lean",
                                            "physical_inspection_passes_through": True,
                                            "investigation_check_reveals_illusion": True
                                        }
                                    }
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_encounter()
            caster = encounter.entities["ent_caster_001"]
            caster.spells.append({"spell_id": "disguise_self", "name": "Disguise Self", "level": 1})
            caster.resources["spell_slots"]["1"] = {"max": 2, "remaining": 2}
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="disguise_self",
                cast_level=1,
                declared_action_cost="action",
            )

            self.assertEqual(result["spell_resolution"]["mode"], "apply_spell_instance")
            updated = encounter_repo.get("enc_execute_spell_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_caster_001"].resources["spell_slots"]["1"]["remaining"], 1)
            self.assertEqual(len(updated.entities["ent_caster_001"].turn_effects), 1)
            self.assertEqual(updated.entities["ent_caster_001"].turn_effects[0]["effect_type"], "disguise_self")
            self.assertEqual(
                updated.entities["ent_caster_001"].turn_effects[0]["disguise_profile"]["appearance_name"],
                "Town Guard",
            )
            self.assertEqual(len(updated.spell_instances), 1)
            self.assertEqual(updated.spell_instances[0]["targets"][0]["entity_id"], "ent_caster_001")
            encounter_repo.close()
            event_repo.close()

    def test_execute_default_cast_service_uses_same_spell_repository_as_spell_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            spell_repo_path.write_text(
                json.dumps(
                    {
                        "spell_definitions": {
                            "task3_shared_repo_spell": {
                                "id": "task3_shared_repo_spell",
                                "name": "Task3 Shared Repo Spell",
                                "level": 3,
                                "base": {
                                    "level": 3,
                                    "casting_time": "1 action",
                                    "concentration": False,
                                },
                                "resolution": {
                                    "activation": "action",
                                },
                                "targeting": {
                                    "type": "single_target",
                                    "allowed_target_types": ["creature"],
                                },
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_encounter()
            encounter.entities["ent_caster_001"].spells.append(
                {
                    "spell_id": "task3_shared_repo_spell",
                    "name": "Actor Fallback Name",
                    "level": 1,
                }
            )
            encounter_repo.save(encounter)

            ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_spell_test",
                actor_id="ent_caster_001",
                spell_id="task3_shared_repo_spell",
                cast_level=3,
                target_entity_ids=["ent_target_001"],
                declared_action_cost="action",
            )

            event = event_repo.list_by_encounter("enc_execute_spell_test")[0]
            self.assertEqual(event.payload["spell_name"], "Task3 Shared Repo Spell")
            self.assertEqual(event.payload["spell_level"], 3)
            encounter_repo.close()
            event_repo.close()

    def test_execute_fireball_auto_rolls_when_save_rolls_are_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_fireball_save_damage_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter_repo.save(build_fireball_save_damage_encounter())

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_fireball_save_damage_test",
                actor_id="ent_fireball_caster_001",
                spell_id="fireball",
                cast_level=4,
                target_point={"x": 5, "y": 5},
                declared_action_cost="action",
            )

            self.assertEqual(result["spell_resolution"]["mode"], "save_damage")
            self.assertEqual(len(result["spell_resolution"]["targets"]), 2)
            self.assertEqual(len(event_repo.list_all()), 5)

            updated = encounter_repo.get("enc_execute_fireball_save_damage_test")
            self.assertIsNotNone(updated)
            self.assertLess(updated.entities["ent_fireball_target_failed_001"].hp["current"], 40)
            self.assertLessEqual(updated.entities["ent_fireball_target_success_001"].hp["current"], 40)
            self.assertEqual(updated.entities["ent_fireball_caster_001"].resources["spell_slots"]["4"]["remaining"], 0)
            encounter_repo.close()
            event_repo.close()

    def test_execute_fireball_invalid_damage_rolls_returns_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_fireball_save_damage_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter_repo.save(build_fireball_save_damage_encounter())

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_fireball_save_damage_test",
                actor_id="ent_fireball_caster_001",
                spell_id="fireball",
                cast_level=4,
                target_point={"x": 5, "y": 5},
                declared_action_cost="action",
                save_rolls=[
                    {"target_id": "ent_fireball_target_failed_001", "base_roll": 10},
                    {"target_id": "ent_fireball_target_success_001", "base_roll": 14},
                ],
                damage_rolls=[6, "bad_roll"],
            )

            self.assertFalse(result["ok"])
            self.assertEqual(result["error_code"], "invalid_damage_rolls")
            self.assertEqual(len(event_repo.list_all()), 0)
            updated = encounter_repo.get("enc_execute_fireball_save_damage_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_fireball_caster_001"].resources["spell_slots"]["4"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()

    def test_execute_fireball_area_targets_respect_allowed_target_types(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_fireball_save_damage_spell_definition(spell_repo_path, allowed_target_types=["creature"])
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_fireball_save_damage_encounter()
            encounter.entities["ent_fireball_hazard_001"] = EncounterEntity(
                entity_id="ent_fireball_hazard_001",
                name="Area Hazard",
                side="enemy",
                category="hazard",
                controller="system",
                position={"x": 6, "y": 6},
                hp={"current": 30, "max": 30, "temp": 0},
                ac=10,
                speed={"walk": 0, "remaining": 0},
                initiative=0,
                source_ref={},
            )
            encounter.turn_order.append("ent_fireball_hazard_001")
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_fireball_save_damage_test",
                actor_id="ent_fireball_caster_001",
                spell_id="fireball",
                cast_level=4,
                target_point={"x": 5, "y": 5},
                declared_action_cost="action",
                save_rolls=[
                    {"target_id": "ent_fireball_target_failed_001", "base_roll": 10},
                    {"target_id": "ent_fireball_target_success_001", "base_roll": 14},
                ],
                damage_rolls=[6, 5, 4, 3, 2, 1, 6, 5],
            )

            self.assertEqual(result["spell_resolution"]["resolution_mode"], "save_damage")
            resolution_target_ids = [item["target_id"] for item in result["spell_resolution"]["targets"]]
            self.assertCountEqual(
                resolution_target_ids,
                ["ent_fireball_target_failed_001", "ent_fireball_target_success_001"],
            )
            self.assertNotIn("ent_fireball_hazard_001", resolution_target_ids)

            updated = encounter_repo.get("enc_execute_fireball_save_damage_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_fireball_hazard_001"].hp["current"], 30)
            encounter_repo.close()
            event_repo.close()

    def test_execute_fireball_returns_spell_area_overlay_in_encounter_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_fireball_save_damage_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter_repo.save(build_fireball_save_damage_encounter())

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_fireball_save_damage_test",
                actor_id="ent_fireball_caster_001",
                spell_id="fireball",
                cast_level=4,
                target_point={"x": 5, "y": 5},
                declared_action_cost="action",
                save_rolls=[
                    {"target_id": "ent_fireball_target_failed_001", "base_roll": 10},
                    {"target_id": "ent_fireball_target_success_001", "base_roll": 14},
                ],
                damage_rolls=[6, 5, 4, 3, 2, 1, 6, 5],
            )

            overlays = result["encounter_state"].get("spell_area_overlays", [])
            self.assertEqual(len(overlays), 1)
            self.assertEqual(overlays[0]["kind"], "spell_area_circle")
            self.assertEqual(overlays[0]["target_point"], {"x": 5, "y": 5, "anchor": "cell_center"})
            self.assertEqual(overlays[0]["source_spell_id"], "fireball")
            encounter_repo.close()
            event_repo.close()

    def test_execute_fireball_deals_failed_save_full_damage_and_success_half_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_fireball_save_damage_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter_repo.save(build_fireball_save_damage_encounter())

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_fireball_save_damage_test",
                actor_id="ent_fireball_caster_001",
                spell_id="fireball",
                cast_level=4,
                target_point={"x": 5, "y": 5},
                declared_action_cost="action",
                save_rolls=[
                    {"target_id": "ent_fireball_target_failed_001", "base_roll": 10},
                    {"target_id": "ent_fireball_target_success_001", "base_roll": 14},
                ],
                damage_rolls=[6, 5, 4, 3, 2, 1, 6, 5],
            )

            updated = encounter_repo.get("enc_execute_fireball_save_damage_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_fireball_target_failed_001"].hp["current"], 8)
            self.assertEqual(updated.entities["ent_fireball_target_success_001"].hp["current"], 24)
            self.assertEqual(result["spell_resolution"]["resolution_mode"], "save_damage")
            self.assertIn("encounter_state", result)
            encounter_repo.close()
            event_repo.close()

    def test_execute_fireball_applies_evasion_to_monk_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_fireball_save_damage_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_fireball_save_damage_encounter()
            encounter.entities["ent_fireball_target_failed_001"].class_features = {
                "monk": {"evasion": {"enabled": True}}
            }
            encounter.entities["ent_fireball_target_success_001"].class_features = {
                "monk": {"evasion": {"enabled": True}}
            }
            encounter_repo.save(encounter)

            ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_fireball_save_damage_test",
                actor_id="ent_fireball_caster_001",
                spell_id="fireball",
                cast_level=4,
                target_point={"x": 5, "y": 5},
                declared_action_cost="action",
                save_rolls=[
                    {"target_id": "ent_fireball_target_failed_001", "base_roll": 10},
                    {"target_id": "ent_fireball_target_success_001", "base_roll": 14},
                ],
                damage_rolls=[6, 5, 4, 3, 2, 1, 6, 5],
            )

            updated = encounter_repo.get("enc_execute_fireball_save_damage_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_fireball_target_failed_001"].hp["current"], 24)
            self.assertEqual(updated.entities["ent_fireball_target_success_001"].hp["current"], 40)
            encounter_repo.close()
            event_repo.close()

    def test_execute_fireball_does_not_apply_evasion_when_monk_is_incapacitated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_fireball_save_damage_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_fireball_save_damage_encounter()
            encounter.entities["ent_fireball_target_success_001"].class_features = {
                "monk": {"evasion": {"enabled": True}}
            }
            encounter.entities["ent_fireball_target_success_001"].conditions = ["incapacitated"]
            encounter_repo.save(encounter)

            ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_fireball_save_damage_test",
                actor_id="ent_fireball_caster_001",
                spell_id="fireball",
                cast_level=4,
                target_point={"x": 5, "y": 5},
                declared_action_cost="action",
                save_rolls=[
                    {"target_id": "ent_fireball_target_failed_001", "base_roll": 10},
                    {"target_id": "ent_fireball_target_success_001", "base_roll": 14},
                ],
                damage_rolls=[6, 5, 4, 3, 2, 1, 6, 5],
            )

            updated = encounter_repo.get("enc_execute_fireball_save_damage_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_fireball_target_success_001"].hp["current"], 24)
            encounter_repo.close()
            event_repo.close()

    def test_execute_hold_person_applies_paralyzed_and_spell_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_hold_person_save_condition_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_hold_person_save_condition_encounter()
            encounter.entities["ent_hold_person_caster_001"].resources["spell_slots"]["4"] = {"max": 1, "remaining": 1}
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_hold_person_save_condition_test",
                actor_id="ent_hold_person_caster_001",
                spell_id="hold_person",
                cast_level=4,
                target_entity_ids=["ent_hold_person_target_001", "ent_hold_person_target_002"],
                declared_action_cost="action",
                save_rolls=[
                    {"target_id": "ent_hold_person_target_001", "base_roll": 3},
                    {"target_id": "ent_hold_person_target_002", "base_roll": 4},
                ],
            )

            updated = encounter_repo.get("enc_execute_hold_person_save_condition_test")
            self.assertIsNotNone(updated)
            self.assertIn("paralyzed", updated.entities["ent_hold_person_target_001"].conditions)
            self.assertIn("paralyzed", updated.entities["ent_hold_person_target_002"].conditions)
            self.assertEqual(len(updated.spell_instances), 1)
            self.assertCountEqual(
                [target["entity_id"] for target in updated.spell_instances[0]["targets"]],
                ["ent_hold_person_target_001", "ent_hold_person_target_002"],
            )
            self.assertEqual(result["spell_resolution"]["resolution_mode"], "save_condition")
            encounter_repo.close()
            event_repo.close()

    def test_execute_hold_person_mixed_save_only_failed_target_in_single_aggregate_spell_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_hold_person_save_condition_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_hold_person_save_condition_encounter()
            encounter.entities["ent_hold_person_caster_001"].resources["spell_slots"]["4"] = {"max": 1, "remaining": 1}
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_hold_person_save_condition_test",
                actor_id="ent_hold_person_caster_001",
                spell_id="hold_person",
                cast_level=4,
                target_entity_ids=[
                    "ent_hold_person_target_001",
                    "ent_hold_person_target_001",
                    "ent_hold_person_target_002",
                ],
                declared_action_cost="action",
                save_rolls=[
                    {"target_id": "ent_hold_person_target_001", "base_roll": 3},
                    {"target_id": "ent_hold_person_target_002", "base_roll": 19},
                ],
            )

            self.assertEqual(result["spell_resolution"]["resolution_mode"], "save_condition")
            self.assertEqual(
                [item["target_id"] for item in result["spell_resolution"]["targets"]],
                ["ent_hold_person_target_001", "ent_hold_person_target_002"],
            )

            updated = encounter_repo.get("enc_execute_hold_person_save_condition_test")
            self.assertIsNotNone(updated)
            self.assertIn("paralyzed", updated.entities["ent_hold_person_target_001"].conditions)
            self.assertNotIn("paralyzed", updated.entities["ent_hold_person_target_002"].conditions)

            self.assertEqual(len(updated.spell_instances), 1)
            aggregate_instance = updated.spell_instances[0]
            self.assertEqual(
                [target["entity_id"] for target in aggregate_instance["targets"]],
                ["ent_hold_person_target_001"],
            )
            self.assertEqual(
                aggregate_instance["instance_id"],
                result["spell_resolution"]["spell_instance"]["instance_id"],
            )
            encounter_repo.close()
            event_repo.close()

    def test_execute_eldritch_blast_uses_cantrip_scaling_for_beam_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_eldritch_blast_attack_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter_repo.save(build_eldritch_blast_attack_encounter(actor_level=5))

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_eldritch_blast_attack_test",
                actor_id="ent_eldritch_caster_001",
                spell_id="eldritch_blast",
                cast_level=0,
                target_entity_ids=["ent_eldritch_target_001", "ent_eldritch_target_002"],
                declared_action_cost="action",
                attack_rolls={
                    "ent_eldritch_target_001": {
                        "final_total": 17,
                        "dice_rolls": {"base_rolls": [13], "modifier": 4},
                    },
                    "ent_eldritch_target_002": {
                        "final_total": 15,
                        "dice_rolls": {"base_rolls": [11], "modifier": 4},
                    },
                },
                damage_rolls={
                    "ent_eldritch_target_001": [8],
                    "ent_eldritch_target_002": [6],
                },
            )

            updated = encounter_repo.get("enc_execute_eldritch_blast_attack_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_eldritch_target_001"].hp["current"], 4)
            self.assertEqual(updated.entities["ent_eldritch_target_002"].hp["current"], 4)
            self.assertEqual(result["spell_resolution"]["beam_count"], 2)
            self.assertEqual(result["spell_resolution"]["resolution_mode"], "attack")
            encounter_repo.close()
            event_repo.close()

    def test_execute_eldritch_blast_adds_agonizing_blast_damage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_eldritch_blast_attack_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_eldritch_blast_attack_encounter(actor_level=1)
            encounter.entities["ent_eldritch_caster_001"].class_features = {
                "warlock": {
                    "level": 2,
                    "eldritch_invocations": {
                        "selected": [
                            {"invocation_id": "agonizing_blast", "spell_id": "eldritch_blast"},
                        ]
                    },
                }
            }
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_eldritch_blast_attack_test",
                actor_id="ent_eldritch_caster_001",
                spell_id="eldritch_blast",
                cast_level=0,
                target_entity_ids=["ent_eldritch_target_001"],
                declared_action_cost="action",
                attack_rolls={
                    "ent_eldritch_target_001": {
                        "final_total": 17,
                        "dice_rolls": {"base_rolls": [13], "modifier": 4},
                    }
                },
                damage_rolls={
                    "ent_eldritch_target_001": [
                        {"source": "spell:eldritch_blast:on_hit:part_0", "rolls": [8]},
                        {"source": "warlock:agonizing_blast:eldritch_blast", "rolls": []},
                    ]
                },
            )

            updated = encounter_repo.get("enc_execute_eldritch_blast_attack_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_eldritch_target_001"].hp["current"], 0)
            self.assertEqual(result["spell_resolution"]["targets"][0]["damage_resolution"]["total_damage"], 12)
            encounter_repo.close()
            event_repo.close()

    def test_execute_eldritch_blast_pushes_target_with_repelling_blast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_eldritch_blast_attack_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)
            encounter = build_eldritch_blast_attack_encounter(actor_level=1)
            encounter.entities["ent_eldritch_caster_001"].class_features = {
                "warlock": {
                    "level": 2,
                    "eldritch_invocations": {
                        "selected": [
                            {"invocation_id": "repelling_blast", "spell_id": "eldritch_blast"},
                        ]
                    },
                }
            }
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_eldritch_blast_attack_test",
                actor_id="ent_eldritch_caster_001",
                spell_id="eldritch_blast",
                cast_level=0,
                target_entity_ids=["ent_eldritch_target_001"],
                declared_action_cost="action",
                attack_rolls={
                    "ent_eldritch_target_001": {
                        "final_total": 17,
                        "dice_rolls": {"base_rolls": [13], "modifier": 4},
                    }
                },
                damage_rolls={"ent_eldritch_target_001": [6]},
            )

            updated = encounter_repo.get("enc_execute_eldritch_blast_attack_test")
            self.assertIsNotNone(updated)
            self.assertEqual(updated.entities["ent_eldritch_target_001"].position, {"x": 10, "y": 5})
            self.assertEqual(
                result["spell_resolution"]["targets"][0]["forced_movement"]["moved_feet"],
                10,
            )
            encounter_repo.close()
            event_repo.close()

    def test_execute_attack_spell_can_use_gaze_of_two_minds_origin_for_range_and_los(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            encounter_repo = EncounterRepository(tmp_path / "encounters.json")
            event_repo = EventRepository(tmp_path / "events.json")
            spell_repo_path = tmp_path / "spell_definitions.json"
            write_ray_of_dread_attack_spell_definition(spell_repo_path)
            spell_repo = SpellDefinitionRepository(spell_repo_path)

            caster = EncounterEntity(
                entity_id="ent_gaze_caster_001",
                name="Watcher",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 1, "y": 1},
                hp={"current": 18, "max": 18, "temp": 0},
                ac=13,
                speed={"walk": 30, "remaining": 30},
                initiative=16,
                source_ref={"caster_level": 5, "spellcasting_ability": "cha", "entity_type": "humanoid"},
                ability_mods={"cha": 4},
                proficiency_bonus=3,
                resources={"spell_slots": {"1": {"max": 1, "remaining": 1}}},
                spells=[{"spell_id": "ray_of_dread", "name": "Ray of Dread", "level": 1}],
                class_features={
                    "warlock": {
                        "level": 5,
                        "eldritch_invocations": {
                            "selected": [{"invocation_id": "gaze_of_two_minds"}]
                        },
                        "gaze_of_two_minds": {
                            "linked_entity_id": "ent_gaze_ally_001",
                            "linked_entity_name": "Scout",
                            "remaining_source_turn_ends": 1,
                        },
                    }
                },
            )
            ally = EncounterEntity(
                entity_id="ent_gaze_ally_001",
                name="Scout",
                side="ally",
                category="pc",
                controller="player",
                position={"x": 6, "y": 1},
                hp={"current": 16, "max": 16, "temp": 0},
                ac=14,
                speed={"walk": 30, "remaining": 30},
                initiative=12,
            )
            target = EncounterEntity(
                entity_id="ent_gaze_target_001",
                name="Cultist",
                side="enemy",
                category="npc",
                controller="gm",
                position={"x": 8, "y": 1},
                hp={"current": 18, "max": 18, "temp": 0},
                ac=12,
                speed={"walk": 30, "remaining": 30},
                initiative=10,
                source_ref={"entity_type": "humanoid"},
            )
            encounter = Encounter(
                encounter_id="enc_execute_gaze_spell_test",
                name="Execute Gaze Spell Test",
                status="active",
                round=1,
                current_entity_id=caster.entity_id,
                turn_order=[caster.entity_id, ally.entity_id, target.entity_id],
                entities={caster.entity_id: caster, ally.entity_id: ally, target.entity_id: target},
                map=EncounterMap(
                    map_id="map_execute_gaze_spell_test",
                    name="Gaze Spell Map",
                    description="Map for gaze spell origin tests.",
                    width=12,
                    height=12,
                    terrain=[
                        {
                            "terrain_id": "wall_between_caster_and_target",
                            "type": "wall",
                            "x": 4,
                            "y": 1,
                            "blocks_movement": True,
                            "blocks_los": True,
                        }
                    ],
                ),
            )
            encounter_repo.save(encounter)

            result = ExecuteSpell(
                encounter_repository=encounter_repo,
                append_event=AppendEvent(event_repo),
                spell_request=SpellRequest(encounter_repo, spell_repo),
            ).execute(
                encounter_id="enc_execute_gaze_spell_test",
                actor_id="ent_gaze_caster_001",
                spell_id="ray_of_dread",
                cast_level=3,
                target_entity_ids=["ent_gaze_target_001"],
                declared_action_cost="action",
                attack_rolls={
                    "ent_gaze_target_001": {
                        "final_total": 17,
                        "dice_rolls": {"base_rolls": [10], "modifier": 7},
                    }
                },
                damage_rolls={"ent_gaze_target_001": [5, 4]},
            )

            updated = encounter_repo.get("enc_execute_gaze_spell_test")
            self.assertIsNotNone(updated)
            self.assertTrue(result["spell_resolution"]["targets"][0]["attack"]["hit"])
            self.assertEqual(updated.entities["ent_gaze_target_001"].hp["current"], 9)
            self.assertEqual(updated.entities["ent_gaze_caster_001"].resources["pact_magic_slots"]["remaining"], 1)
            encounter_repo.close()
            event_repo.close()
