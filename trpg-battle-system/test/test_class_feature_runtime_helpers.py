"""class feature 运行时共享 helper 测试。"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _import_helpers():
    from tools.services.class_features.shared import (
        add_or_refresh_studied_attack_mark,
        ensure_class_runtime,
        ensure_fighter_runtime,
        ensure_monk_runtime,
        ensure_ranger_runtime,
        ensure_rogue_runtime,
        ensure_sorcerer_runtime,
        ensure_warlock_runtime,
        get_class_runtime,
        get_fighter_runtime,
        get_monk_runtime,
        get_ranger_runtime,
        get_sorcerer_runtime,
        get_warlock_runtime,
        normalize_class_feature_options,
        resolve_extra_attack_count,
        resolve_entity_proficiencies,
        resolve_entity_save_proficiencies,
    )

    return SimpleNamespace(
        add_or_refresh_studied_attack_mark=add_or_refresh_studied_attack_mark,
        ensure_class_runtime=ensure_class_runtime,
        ensure_fighter_runtime=ensure_fighter_runtime,
        ensure_monk_runtime=ensure_monk_runtime,
        ensure_ranger_runtime=ensure_ranger_runtime,
        ensure_rogue_runtime=ensure_rogue_runtime,
        ensure_sorcerer_runtime=ensure_sorcerer_runtime,
        ensure_warlock_runtime=ensure_warlock_runtime,
        get_class_runtime=get_class_runtime,
        get_fighter_runtime=get_fighter_runtime,
        get_monk_runtime=get_monk_runtime,
        get_ranger_runtime=get_ranger_runtime,
        get_sorcerer_runtime=get_sorcerer_runtime,
        get_warlock_runtime=get_warlock_runtime,
        normalize_class_feature_options=normalize_class_feature_options,
        resolve_extra_attack_count=resolve_extra_attack_count,
        resolve_entity_proficiencies=resolve_entity_proficiencies,
        resolve_entity_save_proficiencies=resolve_entity_save_proficiencies,
    )


def build_entity() -> object:
    return type("FakeEntity", (), {"class_features": {}})()


class ClassFeatureRuntimeHelpersTests(unittest.TestCase):
    def test_import_shared_helpers_via_package_path(self) -> None:
        helpers = _import_helpers()
        self.assertEqual(helpers.resolve_extra_attack_count({"fighter": {}}), 1)

    def test_import_shared_helpers_then_top_level_service_export(self) -> None:
        _import_helpers()
        from tools.services import AppendEvent

        self.assertEqual(AppendEvent.__name__, "AppendEvent")

    def test_resolve_extra_attack_count_takes_highest_source_only(self) -> None:
        helpers = _import_helpers()
        fighter_state = {
            "fighter": {
                "extra_attack_count": 2,
                "extra_attack_sources": [
                    {"source": "fighter", "attack_count": 2},
                    {"source": "other_class", "attack_count": 2},
                ],
            }
        }
        self.assertEqual(helpers.resolve_extra_attack_count(fighter_state), 2)

    def test_resolve_extra_attack_count_falls_back_to_one(self) -> None:
        helpers = _import_helpers()
        self.assertEqual(helpers.resolve_extra_attack_count({}), 1)

    def test_add_studied_attack_mark_appends_target_once(self) -> None:
        helpers = _import_helpers()
        state = {"fighter": {"studied_attacks": []}}
        helpers.add_or_refresh_studied_attack_mark(state, "ent_enemy_001")
        self.assertEqual(state["fighter"]["studied_attacks"][0]["target_entity_id"], "ent_enemy_001")

    def test_add_studied_attack_mark_refreshes_existing_without_appending_duplicate(self) -> None:
        helpers = _import_helpers()
        state = {"fighter": {"studied_attacks": []}}
        helpers.add_or_refresh_studied_attack_mark(state, "ent_enemy_001")
        helpers.add_or_refresh_studied_attack_mark(state, "ent_enemy_001")
        self.assertEqual(len(state["fighter"]["studied_attacks"]), 1)
        self.assertEqual(state["fighter"]["studied_attacks"][0]["expires_at"], "end_of_next_turn")
        self.assertFalse(state["fighter"]["studied_attacks"][0]["consumed"])

    def test_ensure_fighter_runtime_writes_under_entity_class_features_for_object_entity(self) -> None:
        helpers = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {}})()
        fighter = helpers.ensure_fighter_runtime(entity)
        fighter["extra_attack_count"] = 2
        self.assertEqual(entity.class_features["fighter"]["extra_attack_count"], 2)

    def test_ensure_fighter_runtime_writes_under_entity_class_features_for_dict_entity(self) -> None:
        helpers = _import_helpers()
        entity = {}
        fighter = helpers.ensure_fighter_runtime(entity)
        fighter["extra_attack_count"] = 2
        self.assertEqual(entity["class_features"]["fighter"]["extra_attack_count"], 2)

    def test_get_fighter_runtime_reads_existing_fighter_bucket_from_entity_class_features(self) -> None:
        helpers = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {"fighter": {"extra_attack_count": 2}}})()
        self.assertEqual(helpers.get_fighter_runtime(entity)["extra_attack_count"], 2)

    def test_get_fighter_runtime_ignores_bare_dict_root_fighter_key(self) -> None:
        helpers = _import_helpers()
        entity = {"fighter": {"extra_attack_count": 2}}
        self.assertEqual(helpers.get_fighter_runtime(entity), {})

    def test_resolve_entity_proficiencies_returns_fighter_defaults(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"fighter": {"level": 1}}

        proficiencies = helpers.resolve_entity_proficiencies(entity)

        self.assertEqual(proficiencies["weapon_proficiencies"], ["simple", "martial"])
        self.assertEqual(proficiencies["armor_training"], ["light", "medium", "heavy", "shield"])
        self.assertEqual(proficiencies["save_proficiencies"], ["str", "con"])

    def test_resolve_entity_proficiencies_merges_explicit_lists(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "fighter": {
                "level": 1,
                "weapon_proficiencies": ["simple", "martial", "improvised"],
                "armor_training": ["light", "medium", "heavy", "shield", "tower"],
                "save_proficiencies": ["str", "con", "wis"],
            }
        }

        proficiencies = helpers.resolve_entity_proficiencies(entity)

        self.assertEqual(proficiencies["weapon_proficiencies"], ["simple", "martial", "improvised"])
        self.assertEqual(proficiencies["armor_training"], ["light", "medium", "heavy", "shield", "tower"])
        self.assertEqual(proficiencies["save_proficiencies"], ["str", "con", "wis"])

    def test_resolve_entity_proficiencies_normalizes_mixed_case_armor_training(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "fighter": {
                "level": 1,
                "armor_training": ["HEAVY", "Shield", "Tower"],
            }
        }

        proficiencies = helpers.resolve_entity_proficiencies(entity)

        self.assertEqual(
            proficiencies["armor_training"],
            ["light", "medium", "heavy", "shield", "tower"],
        )

    def test_resolve_entity_proficiencies_supports_property_based_weapon_selectors_from_class_template(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"rogue": {"level": 1}}

        proficiencies = helpers.resolve_entity_proficiencies(entity)

        self.assertIn("simple", proficiencies["weapon_proficiencies"])
        self.assertIn("martial_finesse_or_light", proficiencies["weapon_proficiencies"])
        self.assertEqual(proficiencies["armor_training"], ["light"])
        self.assertEqual(proficiencies["save_proficiencies"], ["dex", "int"])

    def test_resolve_entity_save_proficiencies_merges_class_template_and_entity_field(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"fighter": {"level": 1}}
        entity.save_proficiencies = ["wis"]

        proficiencies = helpers.resolve_entity_save_proficiencies(entity)

        self.assertEqual(proficiencies, ["str", "con", "wis"])

    def test_resolve_entity_save_proficiencies_adds_slippery_mind_wis_cha(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"rogue": {"level": 15}}

        proficiencies = helpers.resolve_entity_save_proficiencies(entity)

        self.assertEqual(proficiencies, ["dex", "int", "wis", "cha"])

    def test_ensure_class_runtime_writes_bucket_under_class_features(self) -> None:
        helpers = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {}})()
        monk = helpers.ensure_class_runtime(entity, "monk")
        monk["focus_points"] = {"max": 5, "remaining": 5}
        self.assertEqual(entity.class_features["monk"]["focus_points"]["remaining"], 5)

    def test_ensure_monk_runtime_derives_core_progression_from_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"monk": {"level": 11}}

        monk = helpers.ensure_monk_runtime(entity)

        self.assertEqual(monk["martial_arts_die"], "1d10")
        self.assertEqual(monk["focus_points"]["max"], 11)
        self.assertEqual(monk["focus_points"]["remaining"], 11)
        self.assertEqual(monk["unarmored_movement_bonus_feet"], 20)
        self.assertTrue(monk["evasion"]["enabled"])
        self.assertFalse(monk["deflect_energy"]["enabled"])

    def test_ensure_sorcerer_runtime_derives_core_progression_from_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"sorcerer": {"level": 7}}

        sorcerer = helpers.ensure_sorcerer_runtime(entity)

        self.assertEqual(sorcerer["sorcery_points"]["max"], 7)
        self.assertEqual(sorcerer["sorcery_points"]["current"], 7)
        self.assertEqual(sorcerer["innate_sorcery"]["uses_max"], 2)
        self.assertEqual(sorcerer["innate_sorcery"]["uses_current"], 2)
        self.assertFalse(sorcerer["innate_sorcery"]["active"])
        self.assertTrue(sorcerer["sorcerous_restoration"]["enabled"])
        self.assertTrue(sorcerer["sorcery_incarnate"]["enabled"])
        self.assertEqual(sorcerer["cantrips_known"], 5)
        self.assertEqual(sorcerer["prepared_spells_count"], 11)

    def test_get_sorcerer_runtime_reads_existing_bucket_from_entity_class_features(self) -> None:
        helpers = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {"sorcerer": {"level": 3, "sorcery_points": {"current": 2}}}})()

        sorcerer = helpers.get_sorcerer_runtime(entity)

        self.assertEqual(sorcerer["level"], 3)
        self.assertEqual(sorcerer["sorcery_points"]["current"], 2)

    def test_get_monk_runtime_preserves_existing_remaining_focus_points(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "monk": {
                "level": 5,
                "focus_points": {"max": 1, "remaining": 2},
            }
        }

        monk = helpers.get_monk_runtime(entity)

        self.assertEqual(monk["martial_arts_die"], "1d8")
        self.assertEqual(monk["focus_points"]["max"], 5)
        self.assertEqual(monk["focus_points"]["remaining"], 2)
        self.assertEqual(monk["unarmored_movement_bonus_feet"], 10)

    def test_ensure_rogue_runtime_refreshes_sneak_attack_damage_by_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"rogue": {"level": 7}}

        rogue = helpers.ensure_rogue_runtime(entity)

        self.assertEqual(rogue["sneak_attack"]["damage_dice"], "4d6")
        self.assertFalse(rogue["sneak_attack"]["used_this_turn"])
        self.assertTrue(rogue["uncanny_dodge"]["enabled"])
        self.assertTrue(rogue["reliable_talent"]["enabled"])
        self.assertFalse(rogue["slippery_mind"]["enabled"])

    def test_ensure_ranger_runtime_derives_core_progression_from_level_and_wisdom(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.ability_mods = {"wis": 3}
        entity.class_features = {"ranger": {"level": 14}}

        ranger = helpers.ensure_ranger_runtime(entity)

        self.assertEqual(ranger["weapon_mastery_count"], 2)
        self.assertEqual(ranger["favored_enemy"]["free_cast_uses_max"], 2)
        self.assertEqual(ranger["favored_enemy"]["free_cast_uses_remaining"], 2)
        self.assertTrue(ranger["roving"]["enabled"])
        self.assertEqual(ranger["roving"]["speed_bonus_feet"], 10)
        self.assertTrue(ranger["tireless"]["enabled"])
        self.assertEqual(ranger["tireless"]["temp_hp_uses_max"], 3)
        self.assertEqual(ranger["tireless"]["temp_hp_uses_remaining"], 3)
        self.assertTrue(ranger["natures_veil"]["enabled"])
        self.assertEqual(ranger["natures_veil"]["uses_max"], 3)
        self.assertEqual(ranger["natures_veil"]["uses_remaining"], 3)
        self.assertTrue(ranger["relentless_hunter"]["enabled"])
        self.assertFalse(ranger["precise_hunter"]["enabled"])

    def test_ensure_warlock_runtime_enables_armor_of_shadows_when_selected(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "warlock": {
                "level": 2,
                "eldritch_invocations": {
                    "selected": [{"invocation_id": "armor_of_shadows"}],
                },
            }
        }

        warlock = helpers.ensure_warlock_runtime(entity)

        self.assertTrue(warlock["armor_of_shadows"]["enabled"])

    def test_ensure_warlock_runtime_enables_fiendish_vigor_when_selected(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "warlock": {
                "level": 2,
                "eldritch_invocations": {
                    "selected": [{"invocation_id": "fiendish_vigor"}],
                },
            }
        }

        warlock = helpers.ensure_warlock_runtime(entity)

        self.assertTrue(warlock["fiendish_vigor"]["enabled"])

    def test_ensure_warlock_runtime_enables_eldritch_mind_when_selected(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "warlock": {
                "level": 2,
                "eldritch_invocations": {
                    "selected": [{"invocation_id": "eldritch_mind"}],
                },
            }
        }

        warlock = helpers.ensure_warlock_runtime(entity)

        self.assertTrue(warlock["eldritch_mind"]["enabled"])

    def test_ensure_warlock_runtime_enables_devils_sight_when_selected(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "warlock": {
                "level": 2,
                "eldritch_invocations": {
                    "selected": [{"invocation_id": "devils_sight"}],
                },
            }
        }

        warlock = helpers.ensure_warlock_runtime(entity)

        self.assertTrue(warlock["devils_sight"]["enabled"])
        self.assertEqual(warlock["devils_sight"]["range_feet"], 120)
        self.assertTrue(warlock["devils_sight"]["sees_magical_darkness"])

    def test_get_ranger_runtime_preserves_existing_remaining_uses(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.ability_mods = {"wis": 4}
        entity.class_features = {
            "ranger": {
                "level": 14,
                "favored_enemy": {"free_cast_uses_remaining": 1},
                "tireless": {"temp_hp_uses_remaining": 2},
                "natures_veil": {"uses_remaining": 1},
            }
        }

        ranger = helpers.get_ranger_runtime(entity)

        self.assertEqual(ranger["favored_enemy"]["free_cast_uses_remaining"], 1)
        self.assertEqual(ranger["tireless"]["temp_hp_uses_remaining"], 2)
        self.assertEqual(ranger["natures_veil"]["uses_remaining"], 1)

    def test_ensure_warlock_runtime_derives_core_progression_from_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"warlock": {"level": 17}}

        warlock = helpers.ensure_warlock_runtime(entity)

        self.assertEqual(warlock["invocations_known"], 9)
        self.assertEqual(warlock["cantrips_known"], 4)
        self.assertEqual(warlock["prepared_spells_count"], 14)
        self.assertTrue(warlock["magical_cunning"]["enabled"])
        self.assertTrue(warlock["contact_patron"]["enabled"])
        self.assertTrue(warlock["contact_patron"]["free_cast_available"])
        self.assertEqual(warlock["mystic_arcanum"]["6"]["remaining_uses"], 1)
        self.assertEqual(warlock["mystic_arcanum"]["7"]["remaining_uses"], 1)
        self.assertEqual(warlock["mystic_arcanum"]["8"]["remaining_uses"], 1)
        self.assertEqual(warlock["mystic_arcanum"]["9"]["remaining_uses"], 1)
        self.assertFalse(warlock["eldritch_master"]["enabled"])

    def test_get_warlock_runtime_preserves_existing_remaining_uses(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "warlock": {
                "level": 17,
                "magical_cunning": {"available": False},
                "contact_patron": {"free_cast_available": False},
                "mystic_arcanum": {
                    "6": {"remaining_uses": 0},
                    "7": {"remaining_uses": 0},
                },
            }
        }

        warlock = helpers.get_warlock_runtime(entity)

        self.assertFalse(warlock["magical_cunning"]["available"])
        self.assertFalse(warlock["contact_patron"]["free_cast_available"])
        self.assertEqual(warlock["mystic_arcanum"]["6"]["remaining_uses"], 0)
        self.assertEqual(warlock["mystic_arcanum"]["7"]["remaining_uses"], 0)

    def test_parse_class_feature_options_normalizes_known_flags(self) -> None:
        helpers = _import_helpers()
        options = helpers.normalize_class_feature_options(
            {"sneak_attack": True, "stunning_strike": {"enabled": True}}
        )
        self.assertTrue(options["sneak_attack"])
        self.assertTrue(options["stunning_strike"]["enabled"])


if __name__ == "__main__":
    unittest.main()
