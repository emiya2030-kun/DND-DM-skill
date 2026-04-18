"""SpellRequest 测试。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, SpellDefinitionRepository
from tools.services.spells.spell_request import SpellRequest


def build_wizard_caster() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_caster_001",
        name="Task2 Wizard",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 1, "y": 1},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        source_ref={"caster_level": 7, "entity_type": "humanoid"},
        spells=[
            {
                "spell_id": "fireball",
                "name": "Fireball",
                "level": 3,
            },
            {
                "spell_id": "hold_person",
                "name": "Hold Person",
                "level": 2,
            },
            {
                "spell_id": "eldritch_blast",
                "name": "Eldritch Blast",
                "level": 0,
            },
            {
                "spell_id": "magic_missile",
                "name": "Magic Missile",
                "level": 1,
            },
            {
                "spell_id": "hex",
                "name": "Hex",
                "level": 1,
            },
        ],
    )


def build_humanoid_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_humanoid_001",
        name="Bandit",
        side="enemy",
        category="npc",
        controller="gm",
        position={"x": 2, "y": 1},
        hp={"current": 8, "max": 8, "temp": 0},
        ac=11,
        speed={"walk": 30, "remaining": 30},
        initiative=8,
        source_ref={"entity_type": "humanoid"},
    )


def build_wolf_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_wolf_001",
        name="Wolf",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 3, "y": 1},
        hp={"current": 11, "max": 11, "temp": 0},
        ac=13,
        speed={"walk": 40, "remaining": 40},
        initiative=9,
        source_ref={"entity_type": "beast"},
    )


def build_extra_target() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_target_extra_001",
        name="Scout",
        side="ally",
        category="npc",
        controller="gm",
        position={"x": 1, "y": 2},
        hp={"current": 9, "max": 9, "temp": 0},
        ac=12,
        speed={"walk": 30, "remaining": 30},
        initiative=7,
        source_ref={"entity_type": "humanoid"},
    )


def build_encounter() -> Encounter:
    caster = build_wizard_caster()
    humanoid = build_humanoid_target()
    wolf = build_wolf_target()
    extra = build_extra_target()
    return Encounter(
        encounter_id="enc_spell_request_test",
        name="Spell Request Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, humanoid.entity_id, wolf.entity_id, extra.entity_id],
        entities={
            caster.entity_id: caster,
            humanoid.entity_id: humanoid,
            wolf.entity_id: wolf,
            extra.entity_id: extra,
        },
        map=EncounterMap(
            map_id="map_spell_request_test",
            name="Spell Request Map",
            description="Minimal map for spell request tests.",
            width=4,
            height=4,
        ),
    )


class SpellRequestTests(unittest.TestCase):
    def _build_repositories(
        self, knowledge_payload: dict[str, object]
    ) -> tuple[EncounterRepository, SpellDefinitionRepository]:
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)

        tmp_path = Path(tmp_dir.name)
        encounter_repo = EncounterRepository(tmp_path / "encounters.json")
        self.addCleanup(encounter_repo.close)
        encounter_repo.save(build_encounter())

        knowledge_path = tmp_path / "spell_definitions.json"
        knowledge_path.write_text(json.dumps(knowledge_payload), encoding="utf-8")
        return encounter_repo, SpellDefinitionRepository(knowledge_path)

    def test_execute_rejects_unknown_spell_on_actor(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "fireball": {
                        "id": "fireball",
                        "name": "Fireball",
                        "level": 3,
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="ice_storm",
            cast_level=3,
            target_entity_ids=["ent_target_001"],
            target_point={"x": 2, "y": 2},
        )

        self.assertEqual(
            result,
            {
                "ok": False,
                "error_code": "spell_not_known",
                "message": "施法者未掌握 ice_storm",
            },
        )

    def test_execute_rejects_non_current_turn_actor(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "magic_missile": {
                        "id": "magic_missile",
                        "name": "Magic Missile",
                        "level": 1,
                        "base": {"level": 1, "casting_time": "1 action", "concentration": False},
                        "resolution": {"activation": "action"},
                        "targeting": {"allowed_target_types": ["creature"]},
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        ally_npc = EncounterEntity(
            entity_id="ent_companion_001",
            name="Companion",
            side="ally",
            category="npc",
            controller="companion_npc",
            position={"x": 1, "y": 2},
            hp={"current": 12, "max": 12, "temp": 0},
            ac=12,
            speed={"walk": 30, "remaining": 30},
            initiative=9,
            spells=[{"spell_id": "magic_missile", "name": "Magic Missile", "level": 1}],
        )
        encounter.entities[ally_npc.entity_id] = ally_npc
        encounter.turn_order.insert(1, ally_npc.entity_id)
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        with self.assertRaisesRegex(ValueError, "actor_not_current_turn_entity"):
            service.execute(
                encounter_id="enc_spell_request_test",
                actor_id=ally_npc.entity_id,
                spell_id="magic_missile",
                cast_level=1,
                target_entity_ids=["ent_target_humanoid_001"],
            )

    def test_execute_allows_out_of_turn_reaction_spell(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
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
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.spells.append({"spell_id": "shield", "name": "Shield", "level": 1})
        caster.resources["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
        encounter.current_entity_id = "ent_target_humanoid_001"
        encounter.turn_order = ["ent_target_humanoid_001", "ent_caster_001", "ent_target_wolf_001"]
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="shield",
            cast_level=1,
            declared_action_cost="reaction",
            allow_out_of_turn_actor=True,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action_cost"], "reaction")
        self.assertEqual(result["actor_id"], "ent_caster_001")

    def test_execute_rejects_casting_spells_while_raging(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "magic_missile": {
                        "id": "magic_missile",
                        "name": "Magic Missile",
                        "level": 1,
                        "base": {"level": 1, "casting_time": "1 action", "concentration": False},
                        "resolution": {"activation": "action"},
                        "targeting": {"allowed_target_types": ["creature"]},
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.class_features = {
            "barbarian": {
                "level": 5,
                "rage": {"active": True},
            }
        }
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="magic_missile",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
        )

        self.assertEqual(
            result,
            {
                "ok": False,
                "error_code": "cannot_cast_spells_while_raging",
                "message": "狂暴期间不能施法",
            },
        )

    def test_execute_rejects_out_of_turn_non_reaction_spell_even_when_override_enabled(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "magic_missile": {
                        "id": "magic_missile",
                        "name": "Magic Missile",
                        "level": 1,
                        "base": {"level": 1, "casting_time": "1 action", "concentration": False},
                        "resolution": {"activation": "action"},
                        "targeting": {"allowed_target_types": ["creature"]},
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        encounter.current_entity_id = "ent_target_humanoid_001"
        encounter.turn_order = ["ent_target_humanoid_001", "ent_caster_001", "ent_target_wolf_001"]
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        with self.assertRaisesRegex(ValueError, "out_of_turn_cast_requires_reaction"):
            service.execute(
                encounter_id="enc_spell_request_test",
                actor_id="ent_caster_001",
                spell_id="magic_missile",
                cast_level=1,
                target_entity_ids=["ent_target_humanoid_001"],
                declared_action_cost="action",
                allow_out_of_turn_actor=True,
            )

    def test_execute_returns_ok_and_prefers_repository_spell_definition(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "magic_missile": {
                        "id": "magic_missile",
                        "name": "Arcane Missile",
                        "level": 1,
                        "base": {
                            "level": 1,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "resolution": {"activation": "action"},
                        "targeting": {"allowed_target_types": ["creature"]},
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_level_bonus": None,
                        },
                        "source": "repository",
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="magic_missile",
            cast_level=1,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["spell_definition"],
            {
                "id": "magic_missile",
                "name": "Arcane Missile",
                "level": 1,
                "base": {
                    "level": 1,
                    "casting_time": "1 action",
                    "concentration": False,
                },
                "resolution": {"activation": "action"},
                "targeting": {"allowed_target_types": ["creature"]},
                "scaling": {
                    "cantrip_by_level": None,
                    "slot_level_bonus": None,
                },
                "source": "repository",
            },
        )

    def test_execute_resolves_slot_upcast_damage_scaling(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "fireball": {
                        "id": "fireball",
                        "name": "Fireball",
                        "base": {
                            "level": 3,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "targeting": {"type": "area_sphere", "allowed_target_types": ["creature"]},
                        "resolution": {"activation": "action"},
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_level_bonus": {
                                "base_slot_level": 3,
                                "additional_damage_parts": [
                                    {
                                        "formula_per_extra_level": "1d6",
                                        "damage_type": "fire",
                                    }
                                ],
                            },
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="fireball",
            cast_level=5,
            target_point={"x": 2, "y": 2},
            declared_action_cost="action",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["actor_id"], "ent_caster_001")
        self.assertEqual(result["spell_id"], "fireball")
        self.assertEqual(result["base_level"], 3)
        self.assertEqual(result["cast_level"], 5)
        self.assertEqual(result["upcast_delta"], 2)
        self.assertFalse(result["is_cantrip"])
        self.assertEqual(result["action_cost"], "action")
        self.assertEqual(result["target_entity_ids"], [])
        self.assertEqual(result["target_point"], {"x": 2, "y": 2, "anchor": "cell_center"})
        self.assertFalse(result["requires_concentration"])
        self.assertFalse(result["will_replace_concentration"])
        self.assertEqual(result["scaling_mode"], "slot")
        self.assertEqual(
            result["resolved_scaling"]["extra_damage_parts"],
            [{"formula": "2d6", "damage_type": "fire"}],
        )
        self.assertIsInstance(result["spell_definition"], dict)

    def test_execute_rejects_area_spell_missing_target_point(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "fireball": {
                        "id": "fireball",
                        "name": "Fireball",
                        "base": {
                            "level": 3,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "targeting": {"type": "area_sphere", "allowed_target_types": ["creature"]},
                        "area_template": {
                            "shape": "sphere",
                            "radius_feet": 20,
                            "render_mode": "circle_overlay",
                            "persistence": "instant",
                        },
                        "resolution": {"activation": "action"},
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_level_bonus": {"base_slot_level": 3, "additional_damage_parts": []},
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="fireball",
            cast_level=3,
            target_point=None,
            declared_action_cost="action",
        )

        self.assertEqual(result["ok"], False)
        self.assertEqual(result["error_code"], "missing_target_point")

    def test_execute_rejects_area_spell_target_point_beyond_range(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "fireball": {
                        "id": "fireball",
                        "name": "Fireball",
                        "base": {
                            "level": 3,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "targeting": {
                            "type": "area_sphere",
                            "range_feet": 150,
                            "allowed_target_types": ["creature"],
                        },
                        "area_template": {
                            "shape": "sphere",
                            "radius_feet": 20,
                            "render_mode": "circle_overlay",
                            "persistence": "instant",
                        },
                        "resolution": {"activation": "action"},
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_level_bonus": {"base_slot_level": 3, "additional_damage_parts": []},
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="fireball",
            cast_level=3,
            target_point={"x": 40, "y": 40, "anchor": "cell_center"},
            declared_action_cost="action",
        )

        self.assertEqual(result["ok"], False)
        self.assertEqual(result["error_code"], "target_point_out_of_range")

    def test_execute_reports_innate_sorcery_attack_advantage_and_save_dc_bonus(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "chromatic_orb": {
                        "id": "chromatic_orb",
                        "name": "Chromatic Orb",
                        "level": 1,
                        "base": {"level": 1, "casting_time": "1 action", "concentration": False},
                        "resolution": {"activation": "action", "mode": "attack_roll"},
                        "targeting": {"allowed_target_types": ["creature"]},
                        "requires_attack_roll": True,
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.class_features = {
            "sorcerer": {
                "level": 3,
                "innate_sorcery": {"enabled": True, "active": True, "uses_max": 2, "uses_current": 1},
            }
        }
        caster.spells.append(
            {
                "spell_id": "chromatic_orb",
                "name": "Chromatic Orb",
                "level": 1,
                "casting_class": "sorcerer",
            }
        )
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="chromatic_orb",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["spell_attack_advantage"])
        self.assertEqual(result["spell_save_dc_bonus"], 1)

    def test_execute_accepts_subtle_spell_and_returns_noticeability_metadata(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "chromatic_orb": {
                        "id": "chromatic_orb",
                        "name": "Chromatic Orb",
                        "level": 1,
                        "base": {"level": 1, "casting_time": "1 action", "concentration": False},
                        "resolution": {"activation": "action", "mode": "attack_roll"},
                        "targeting": {"allowed_target_types": ["creature"]},
                        "requires_attack_roll": True,
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.class_features = {
            "sorcerer": {
                "level": 3,
                "sorcery_points": {"max": 3, "current": 2},
            }
        }
        caster.spells.append(
            {
                "spell_id": "chromatic_orb",
                "name": "Chromatic Orb",
                "level": 1,
                "casting_class": "sorcerer",
            }
        )
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="chromatic_orb",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
            metamagic_options={"selected": ["subtle_spell"]},
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["metamagic"]["selected"], ["subtle_spell"])
        self.assertTrue(result["metamagic"]["subtle_spell"])
        self.assertEqual(result["metamagic"]["sorcery_point_cost"], 1)
        self.assertFalse(result["metamagic"]["quickened_spell"])
        self.assertFalse(result["metamagic"]["distant_spell"])
        self.assertFalse(result["metamagic"]["heightened_spell"])
        self.assertFalse(result["metamagic"]["careful_spell"])
        self.assertEqual(
            result["noticeability"],
            {
                "casting_is_perceptible": False,
                "verbal_visible": False,
                "somatic_visible": False,
                "material_visible": False,
                "spell_effect_visible": True,
            },
        )

    def test_execute_rejects_multiple_metamagic_selection(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "chromatic_orb": {
                        "id": "chromatic_orb",
                        "name": "Chromatic Orb",
                        "level": 1,
                        "base": {"level": 1, "casting_time": "1 action", "concentration": False},
                        "resolution": {"activation": "action", "mode": "attack_roll"},
                        "targeting": {"type": "single_target", "range_feet": 90, "allowed_target_types": ["creature"]},
                        "requires_attack_roll": True,
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.class_features = {"sorcerer": {"level": 5, "sorcery_points": {"max": 5, "current": 5}}}
        caster.spells.append(
            {"spell_id": "chromatic_orb", "name": "Chromatic Orb", "level": 1, "casting_class": "sorcerer"}
        )
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="chromatic_orb",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
            metamagic_options={"selected": ["subtle_spell", "quickened_spell"]},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "multiple_metamagic_not_supported")

    def test_execute_accepts_quickened_spell_and_returns_cost(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "chromatic_orb": {
                        "id": "chromatic_orb",
                        "name": "Chromatic Orb",
                        "level": 1,
                        "base": {"level": 1, "casting_time": "1 action", "concentration": False},
                        "resolution": {"activation": "action", "mode": "attack_roll"},
                        "targeting": {"type": "single_target", "range_feet": 90, "allowed_target_types": ["creature"]},
                        "requires_attack_roll": True,
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.class_features = {"sorcerer": {"level": 5, "sorcery_points": {"max": 5, "current": 5}}}
        caster.spells.append(
            {"spell_id": "chromatic_orb", "name": "Chromatic Orb", "level": 1, "casting_class": "sorcerer"}
        )
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="chromatic_orb",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
            metamagic_options={"selected": ["quickened_spell"]},
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["metamagic"]["quickened_spell"])
        self.assertEqual(result["metamagic"]["sorcery_point_cost"], 2)

    def test_execute_accepts_distant_spell_for_touch_spell(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "shocking_grasp": {
                        "id": "shocking_grasp",
                        "name": "Shocking Grasp",
                        "level": 0,
                        "base": {"level": 0, "casting_time": "1 action", "concentration": False, "range": "touch"},
                        "resolution": {"activation": "action", "mode": "attack_roll"},
                        "targeting": {
                            "type": "single_target",
                            "range_feet": 5,
                            "range_kind": "touch",
                            "allowed_target_types": ["creature"],
                        },
                        "requires_attack_roll": True,
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        encounter.map.width = 12
        encounter.entities["ent_target_humanoid_001"].position = {"x": 7, "y": 1}
        caster = encounter.entities["ent_caster_001"]
        caster.class_features = {"sorcerer": {"level": 5, "sorcery_points": {"max": 5, "current": 5}}}
        caster.spells.append(
            {"spell_id": "shocking_grasp", "name": "Shocking Grasp", "level": 0, "casting_class": "sorcerer"}
        )
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="shocking_grasp",
            cast_level=0,
            target_entity_ids=["ent_target_humanoid_001"],
            metamagic_options={"selected": ["distant_spell"]},
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["metamagic"]["distant_spell"])

    def test_execute_rejects_heightened_spell_without_target_id(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "hold_person": {
                        "id": "hold_person",
                        "name": "Hold Person",
                        "level": 2,
                        "save_ability": "wis",
                        "base": {"level": 2, "casting_time": "1 action", "concentration": True},
                        "resolution": {"activation": "action", "mode": "save"},
                        "targeting": {"type": "single_target", "range_feet": 60, "allowed_target_types": ["humanoid"]},
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.class_features = {"sorcerer": {"level": 5, "sorcery_points": {"max": 5, "current": 5}}}
        for spell in caster.spells:
            if spell.get("spell_id") == "hold_person":
                spell["casting_class"] = "sorcerer"
                break
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="hold_person",
            cast_level=2,
            target_entity_ids=["ent_target_humanoid_001"],
            metamagic_options={"selected": ["heightened_spell"]},
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "heightened_spell_requires_target")

    def test_execute_rejects_careful_spell_when_targets_exceed_cha_mod(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "burning_hands": {
                        "id": "burning_hands",
                        "name": "Burning Hands",
                        "level": 1,
                        "save_ability": "dex",
                        "base": {"level": 1, "casting_time": "1 action", "concentration": False, "range": "self"},
                        "resolution": {"activation": "action", "mode": "save"},
                        "targeting": {"type": "area_cone", "range_feet": 0, "allowed_target_types": ["creature"]},
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.ability_mods["cha"] = 1
        caster.class_features = {"sorcerer": {"level": 5, "sorcery_points": {"max": 5, "current": 5}}}
        caster.spells.append(
            {"spell_id": "burning_hands", "name": "Burning Hands", "level": 1, "casting_class": "sorcerer"}
        )
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="burning_hands",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001", "ent_target_wolf_001"],
            metamagic_options={
                "selected": ["careful_spell"],
                "careful_target_ids": [
                    "ent_target_humanoid_001",
                    "ent_target_wolf_001",
                    "ent_target_extra_001",
                ],
            },
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "careful_spell_too_many_targets")

    def test_execute_allows_two_beams_for_eldritch_blast_at_level_7_and_rejects_three(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "eldritch_blast": {
                        "id": "eldritch_blast",
                        "name": "Eldritch Blast",
                        "base": {
                            "level": 0,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "targeting": {"type": "single_target", "allowed_target_types": ["creature"]},
                        "resolution": {"activation": "action"},
                        "scaling": {
                            "cantrip_by_level": [
                                {"caster_level": 1, "beam_count": 1},
                                {"caster_level": 5, "beam_count": 2},
                                {"caster_level": 11, "beam_count": 3},
                            ],
                            "slot_level_bonus": None,
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        two_target_result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="eldritch_blast",
            cast_level=0,
            target_entity_ids=["ent_target_humanoid_001", "ent_target_humanoid_001"],
            declared_action_cost="action",
        )
        three_target_result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="eldritch_blast",
            cast_level=0,
            target_entity_ids=[
                "ent_target_humanoid_001",
                "ent_target_humanoid_001",
                "ent_target_humanoid_001",
            ],
            declared_action_cost="action",
        )

        self.assertTrue(two_target_result["ok"])
        self.assertEqual(two_target_result["resolved_scaling"]["beam_count"], 2)
        self.assertEqual(three_target_result["ok"], False)
        self.assertEqual(three_target_result["error_code"], "invalid_target_count")

    def test_execute_rejects_wrong_action_cost(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "fireball": {
                        "id": "fireball",
                        "name": "Fireball",
                        "base": {
                            "level": 3,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "targeting": {"allowed_target_types": ["creature"]},
                        "resolution": {"activation": "action"},
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_level_bonus": {"base_slot_level": 3, "additional_damage_parts": []},
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="fireball",
            cast_level=3,
            declared_action_cost="bonus_action",
        )

        self.assertEqual(result["ok"], False)
        self.assertEqual(result["error_code"], "invalid_action_cost")

    def test_execute_rejects_hold_person_non_humanoid_target(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "hold_person": {
                        "id": "hold_person",
                        "name": "Hold Person",
                        "base": {
                            "level": 2,
                            "casting_time": "1 action",
                            "concentration": True,
                        },
                        "targeting": {"allowed_target_types": ["humanoid"]},
                        "resolution": {"activation": "action"},
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_level_bonus": {"base_slot_level": 2, "additional_targets_per_extra_level": 1},
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="hold_person",
            cast_level=2,
            target_entity_ids=["ent_target_wolf_001"],
            declared_action_cost="action",
        )

        self.assertEqual(
            result,
            {
                "ok": False,
                "error_code": "invalid_target_type",
                "message": "目标 ent_target_wolf_001 不是 humanoid",
            },
        )

    def test_execute_rejects_nonzero_cast_level_for_cantrip(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "eldritch_blast": {
                        "id": "eldritch_blast",
                        "name": "Eldritch Blast",
                        "base": {
                            "level": 0,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "targeting": {"allowed_target_types": ["creature"]},
                        "resolution": {"activation": "action"},
                        "scaling": {
                            "cantrip_by_level": [
                                {"caster_level": 5, "replace_formula": "2d10"},
                                {"caster_level": 11, "replace_formula": "3d10"},
                                {"caster_level": 17, "replace_formula": "4d10"},
                            ],
                            "slot_level_bonus": None,
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="eldritch_blast",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
            declared_action_cost="action",
        )

        self.assertEqual(result["ok"], False)
        self.assertEqual(result["error_code"], "invalid_cantrip_cast_level")

    def test_execute_rejects_missing_target_entity_for_creature_spell(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "magic_missile": {
                        "id": "magic_missile",
                        "name": "Magic Missile",
                        "base": {
                            "level": 1,
                            "casting_time": "1 action",
                            "concentration": False,
                        },
                        "targeting": {"type": "single_target", "allowed_target_types": ["creature"]},
                        "resolution": {"activation": "action"},
                        "scaling": {"cantrip_by_level": None, "slot_level_bonus": None},
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="magic_missile",
            cast_level=1,
            target_entity_ids=["ent_missing_001"],
            declared_action_cost="action",
        )

        self.assertEqual(result["ok"], False)
        self.assertEqual(result["error_code"], "invalid_target")
        self.assertEqual(result["message"], "目标 ent_missing_001 不存在")

    def test_execute_rejects_invalid_target_count_for_single_target_spell(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "hold_person": {
                        "id": "hold_person",
                        "name": "Hold Person",
                        "base": {
                            "level": 2,
                            "casting_time": "1 action",
                            "concentration": True,
                        },
                        "targeting": {"type": "single_target", "allowed_target_types": ["humanoid"]},
                        "resolution": {"activation": "action"},
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_level_bonus": {"base_slot_level": 2, "additional_targets_per_extra_level": 1},
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        empty_target_result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="hold_person",
            cast_level=2,
            target_entity_ids=[],
            declared_action_cost="action",
        )

        too_many_target_result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="hold_person",
            cast_level=2,
            target_entity_ids=["ent_target_humanoid_001", "ent_target_wolf_001"],
            declared_action_cost="action",
        )

        self.assertEqual(empty_target_result["ok"], False)
        self.assertEqual(empty_target_result["error_code"], "invalid_target_count")
        self.assertEqual(too_many_target_result["ok"], False)
        self.assertEqual(too_many_target_result["error_code"], "invalid_target_count")

    def test_execute_accepts_healing_word_bonus_action_single_target(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "healing_word": {
                        "id": "healing_word",
                        "name": "Healing Word",
                        "level": 1,
                        "base": {
                            "level": 1,
                            "casting_time": "1 bonus action",
                            "concentration": False,
                        },
                        "resolution": {"mode": "heal", "activation": "bonus_action"},
                        "targeting": {
                            "type": "single_target",
                            "range_feet": 60,
                            "requires_line_of_sight": True,
                            "allowed_target_types": ["creature"],
                        },
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
        caster.resources["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="healing_word",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
            declared_action_cost="bonus_action",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["action_cost"], "bonus_action")
        self.assertEqual(result["target_entity_ids"], ["ent_target_humanoid_001"])

    def test_execute_rejects_healing_word_target_out_of_range(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "healing_word": {
                        "id": "healing_word",
                        "name": "Healing Word",
                        "level": 1,
                        "base": {
                            "level": 1,
                            "casting_time": "1 bonus action",
                            "concentration": False,
                        },
                        "resolution": {"mode": "heal", "activation": "bonus_action"},
                        "targeting": {
                            "type": "single_target",
                            "range_feet": 60,
                            "requires_line_of_sight": True,
                            "allowed_target_types": ["creature"],
                        },
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
        caster.resources["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
        encounter.entities["ent_target_humanoid_001"].position = {"x": 20, "y": 1}
        encounter.map.width = 24
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="healing_word",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
            declared_action_cost="bonus_action",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "target_out_of_range")

    def test_execute_rejects_healing_word_when_line_of_sight_blocked(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "healing_word": {
                        "id": "healing_word",
                        "name": "Healing Word",
                        "level": 1,
                        "base": {
                            "level": 1,
                            "casting_time": "1 bonus action",
                            "concentration": False,
                        },
                        "resolution": {"mode": "heal", "activation": "bonus_action"},
                        "targeting": {
                            "type": "single_target",
                            "range_feet": 60,
                            "requires_line_of_sight": True,
                            "allowed_target_types": ["creature"],
                        },
                    }
                }
            }
        )
        encounter = encounter_repo.get("enc_spell_request_test")
        self.assertIsNotNone(encounter)
        caster = encounter.entities["ent_caster_001"]
        caster.spells.append({"spell_id": "healing_word", "name": "Healing Word", "level": 1})
        caster.resources["spell_slots"] = {"1": {"max": 2, "remaining": 2}}
        encounter.entities["ent_target_humanoid_001"].position = {"x": 3, "y": 1}
        encounter.map.width = 6
        encounter.map.terrain = [{"terrain_id": "wall_01", "type": "wall", "x": 2, "y": 1, "blocks_los": True}]
        encounter_repo.save(encounter)
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="healing_word",
            cast_level=1,
            target_entity_ids=["ent_target_humanoid_001"],
            declared_action_cost="bonus_action",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "blocked_by_line_of_sight")

    def test_execute_resolves_slot_duration_bonus_for_hex(self) -> None:
        encounter_repo, spell_repo = self._build_repositories(
            {
                "spell_definitions": {
                    "hex": {
                        "id": "hex",
                        "name": "Hex",
                        "base": {
                            "level": 1,
                            "casting_time": "1 bonus action",
                            "concentration": True,
                        },
                        "targeting": {"type": "single_target", "allowed_target_types": ["creature"]},
                        "resolution": {"activation": "bonus_action"},
                        "scaling": {
                            "cantrip_by_level": None,
                            "slot_duration_bonus": [
                                {
                                    "slot_level": 2,
                                    "duration": "concentration_up_to_4_hours",
                                    "duration_zh": "专注，至多4小时",
                                },
                                {
                                    "slot_level": 3,
                                    "duration": "concentration_up_to_8_hours",
                                    "duration_zh": "专注，至多8小时",
                                },
                                {
                                    "slot_level": 5,
                                    "duration": "concentration_up_to_24_hours",
                                    "duration_zh": "专注，至多24小时",
                                },
                            ],
                        },
                    }
                }
            }
        )
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="hex",
            cast_level=3,
            target_entity_ids=["ent_target_humanoid_001"],
            declared_action_cost="bonus_action",
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["scaling_mode"], "slot")
        self.assertEqual(result["resolved_scaling"]["upcast_delta"], 2)
        self.assertEqual(
            result["resolved_scaling"]["slot_duration_bonus"],
            {
                "slot_level": 3,
                "duration": "concentration_up_to_8_hours",
                "duration_zh": "专注，至多8小时",
            },
        )

    def test_execute_returns_normalized_fallback_definition_when_repository_missing(self) -> None:
        encounter_repo, spell_repo = self._build_repositories({"spell_definitions": {}})
        service = SpellRequest(encounter_repo, spell_repo)

        result = service.execute(
            encounter_id="enc_spell_request_test",
            actor_id="ent_caster_001",
            spell_id="magic_missile",
            cast_level=1,
        )

        self.assertTrue(result["ok"])
        spell_definition = result["spell_definition"]
        self.assertEqual(spell_definition["id"], "magic_missile")
        self.assertEqual(spell_definition["name"], "Magic Missile")
        self.assertEqual(spell_definition["base"]["level"], 1)
        self.assertIn("on_cast", spell_definition)
        self.assertIn("requires_attack_roll", spell_definition)
        self.assertIn("save_ability", spell_definition)
        self.assertEqual(spell_definition["on_cast"], {})
        self.assertEqual(spell_definition["requires_attack_roll"], False)
        self.assertIsNone(spell_definition["save_ability"])
        for key in (
            "id",
            "name",
            "base",
            "resolution",
            "targeting",
            "scaling",
            "on_cast",
            "effect_templates",
            "localization",
            "usage_contexts",
            "runtime_support",
            "special_rules",
        ):
            self.assertIn(key, spell_definition)
