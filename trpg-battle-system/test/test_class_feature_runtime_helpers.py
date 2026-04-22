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
        ensure_barbarian_runtime,
        ensure_bard_runtime,
        ensure_cleric_runtime,
        ensure_class_runtime,
        ensure_druid_runtime,
        ensure_fighter_runtime,
        ensure_monk_runtime,
        ensure_paladin_runtime,
        ensure_ranger_runtime,
        ensure_rogue_runtime,
        ensure_sorcerer_runtime,
        ensure_warlock_runtime,
        ensure_wizard_runtime,
        get_bard_runtime,
        get_barbarian_runtime,
        get_cleric_runtime,
        get_class_runtime,
        get_druid_runtime,
        get_fighter_runtime,
        get_monk_runtime,
        get_paladin_runtime,
        get_ranger_runtime,
        get_sorcerer_runtime,
        get_warlock_runtime,
        get_wizard_runtime,
        normalize_class_feature_options,
        resolve_extra_attack_count,
        resolve_entity_proficiencies,
        resolve_entity_save_proficiencies,
    )

    return SimpleNamespace(
        add_or_refresh_studied_attack_mark=add_or_refresh_studied_attack_mark,
        ensure_barbarian_runtime=ensure_barbarian_runtime,
        ensure_bard_runtime=ensure_bard_runtime,
        ensure_cleric_runtime=ensure_cleric_runtime,
        ensure_class_runtime=ensure_class_runtime,
        ensure_druid_runtime=ensure_druid_runtime,
        ensure_fighter_runtime=ensure_fighter_runtime,
        ensure_monk_runtime=ensure_monk_runtime,
        ensure_paladin_runtime=ensure_paladin_runtime,
        ensure_ranger_runtime=ensure_ranger_runtime,
        ensure_rogue_runtime=ensure_rogue_runtime,
        ensure_sorcerer_runtime=ensure_sorcerer_runtime,
        ensure_warlock_runtime=ensure_warlock_runtime,
        ensure_wizard_runtime=ensure_wizard_runtime,
        get_bard_runtime=get_bard_runtime,
        get_barbarian_runtime=get_barbarian_runtime,
        get_cleric_runtime=get_cleric_runtime,
        get_class_runtime=get_class_runtime,
        get_druid_runtime=get_druid_runtime,
        get_fighter_runtime=get_fighter_runtime,
        get_monk_runtime=get_monk_runtime,
        get_paladin_runtime=get_paladin_runtime,
        get_ranger_runtime=get_ranger_runtime,
        get_sorcerer_runtime=get_sorcerer_runtime,
        get_warlock_runtime=get_warlock_runtime,
        get_wizard_runtime=get_wizard_runtime,
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
        entity.initial_class_name = "fighter"
        entity.save_proficiencies = ["wis"]

        proficiencies = helpers.resolve_entity_save_proficiencies(entity)

        self.assertEqual(proficiencies, ["str", "con", "wis"])

    def test_resolve_entity_save_proficiencies_uses_initial_class_only_for_multiclass(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"fighter": {"level": 1}, "rogue": {"level": 1}}
        entity.source_ref = {"class_name": "rogue"}
        entity.initial_class_name = "fighter"
        entity.save_proficiencies = []

        proficiencies = helpers.resolve_entity_save_proficiencies(entity)

        self.assertEqual(proficiencies, ["str", "con"])

    def test_resolve_entity_save_proficiencies_adds_slippery_mind_wis_cha(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"rogue": {"level": 15}}

        proficiencies = helpers.resolve_entity_save_proficiencies(entity)

        self.assertEqual(proficiencies, ["dex", "int", "wis", "cha"])

    def test_resolve_entity_save_proficiencies_adds_all_saves_for_disciplined_survivor(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"monk": {"level": 14}}

        proficiencies = helpers.resolve_entity_save_proficiencies(entity)

        self.assertEqual(proficiencies, ["str", "dex", "con", "int", "wis", "cha"])

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
        self.assertTrue(monk["flurry_of_blows"]["enabled"])
        self.assertEqual(monk["flurry_of_blows"]["base_attack_count"], 3)
        self.assertEqual(monk["flurry_of_blows"]["remaining_attacks"], 0)
        self.assertTrue(monk["evasion"]["enabled"])
        self.assertTrue(monk["heightened_focus"]["enabled"])
        self.assertTrue(monk["self_restoration"]["enabled"])
        self.assertFalse(monk["perfect_focus"]["enabled"])
        self.assertFalse(monk["superior_defense"]["enabled"])
        self.assertFalse(monk["deflect_energy"]["enabled"])

    def test_ensure_monk_runtime_high_level_enables_perfect_focus_and_superior_defense(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"monk": {"level": 18}}

        monk = helpers.ensure_monk_runtime(entity)

        self.assertTrue(monk["perfect_focus"]["enabled"])
        self.assertEqual(monk["perfect_focus"]["restore_threshold"], 3)
        self.assertEqual(monk["perfect_focus"]["restore_to"], 4)
        self.assertEqual(monk["flurry_of_blows"]["base_attack_count"], 3)
        self.assertTrue(monk["superior_defense"]["enabled"])
        self.assertFalse(monk["superior_defense"]["active"])
        self.assertEqual(monk["superior_defense"]["remaining_rounds"], 0)
        self.assertEqual(monk["superior_defense"]["focus_cost"], 3)
        self.assertEqual(monk["superior_defense"]["duration_rounds"], 10)
        self.assertEqual(monk["superior_defense"]["added_resistances"], [])

    def test_ensure_fighter_runtime_derives_core_progression_from_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"fighter": {"level": 13}}

        fighter = helpers.ensure_fighter_runtime(entity)

        self.assertEqual(fighter["fighter_level"], 13)
        self.assertEqual(fighter["weapon_mastery_count"], 5)
        self.assertEqual(fighter["extra_attack_count"], 3)
        self.assertEqual(fighter["second_wind"]["max_uses"], 3)
        self.assertEqual(fighter["second_wind"]["remaining_uses"], 3)
        self.assertTrue(fighter["tactical_mind"]["enabled"])
        self.assertTrue(fighter["tactical_shift"]["enabled"])
        self.assertEqual(fighter["action_surge"]["max_uses"], 1)
        self.assertEqual(fighter["action_surge"]["remaining_uses"], 1)
        self.assertTrue(fighter["indomitable"]["enabled"])
        self.assertEqual(fighter["indomitable"]["max_uses"], 2)
        self.assertEqual(fighter["indomitable"]["remaining_uses"], 2)
        self.assertTrue(fighter["tactical_master"]["enabled"])
        self.assertTrue(fighter["tactical_master_enabled"])
        self.assertTrue(fighter["studied_attacks_feature"]["enabled"])
        self.assertEqual(fighter["turn_counters"]["attack_action_attacks_used"], 0)
        self.assertEqual(fighter["temporary_bonuses"]["extra_non_magic_action_available"], 0)

    def test_ensure_barbarian_runtime_derives_core_progression_from_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"barbarian": {"level": 15}}

        barbarian = helpers.ensure_barbarian_runtime(entity)

        self.assertEqual(barbarian["rage"]["max"], 5)
        self.assertEqual(barbarian["rage"]["remaining"], 5)
        self.assertTrue(barbarian["rage"]["persistent_rage"])
        self.assertEqual(barbarian["rage_damage_bonus"], 3)
        self.assertEqual(barbarian["weapon_mastery_count"], 4)
        self.assertTrue(barbarian["danger_sense"]["enabled"])
        self.assertTrue(barbarian["primal_knowledge"]["enabled"])
        self.assertTrue(barbarian["fast_movement"]["enabled"])
        self.assertEqual(barbarian["fast_movement"]["bonus_feet"], 10)
        self.assertTrue(barbarian["feral_instinct"]["enabled"])
        self.assertTrue(barbarian["instinctive_pounce"]["enabled"])
        self.assertTrue(barbarian["brutal_strike"]["enabled"])
        self.assertEqual(barbarian["brutal_strike"]["extra_damage_dice"], "1d10")
        self.assertTrue(barbarian["relentless_rage"]["enabled"])
        self.assertFalse(barbarian["indomitable_might"]["enabled"])

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

    def test_ensure_bard_runtime_derives_core_progression_from_level_and_charisma(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.ability_mods = {"cha": 4}
        entity.class_features = {"bard": {"level": 10}}

        bard = helpers.ensure_bard_runtime(entity)

        self.assertEqual(bard["bardic_inspiration"]["die"], "d10")
        self.assertEqual(bard["bardic_inspiration"]["uses_max"], 4)
        self.assertEqual(bard["bardic_inspiration"]["uses_current"], 4)
        self.assertEqual(bard["bardic_inspiration"]["recovery"], "short_or_long_rest")
        self.assertEqual(bard["cantrips_known"], 4)
        self.assertEqual(bard["prepared_spells_count"], 15)
        self.assertEqual(bard["expertise"]["max_skills"], 4)
        self.assertTrue(bard["jack_of_all_trades"]["enabled"])
        self.assertTrue(bard["countercharm"]["enabled"])
        self.assertTrue(bard["magical_secrets"]["enabled"])
        self.assertFalse(bard["superior_inspiration"]["enabled"])

    def test_ensure_bard_runtime_sets_standard_spellcasting_fields(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"bard": {"level": 20}}

        bard = helpers.ensure_bard_runtime(entity)

        self.assertEqual(bard["spell_preparation_mode"], "level_up_one")
        self.assertEqual(bard["always_prepared_spells"], ["power_word_heal", "power_word_kill"])

    def test_ensure_wizard_runtime_derives_core_progression_from_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"wizard": {"level": 6}}

        wizard = helpers.ensure_wizard_runtime(entity)

        self.assertEqual(wizard["spell_preparation_mode"], "long_rest_any")
        self.assertEqual(wizard["cantrips_known"], 4)
        self.assertEqual(wizard["prepared_spells_count"], 10)
        self.assertEqual(wizard["always_prepared_spells"], [])

    def test_ensure_cleric_runtime_derives_core_progression_from_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.ability_mods = {"wis": 4}
        entity.class_features = {"cleric": {"level": 10}}

        cleric = helpers.ensure_cleric_runtime(entity)

        self.assertEqual(cleric["spell_preparation_mode"], "long_rest_any")
        self.assertEqual(cleric["cantrips_known"], 5)
        self.assertEqual(cleric["prepared_spells_count"], 15)
        self.assertEqual(cleric["always_prepared_spells"], [])
        self.assertTrue(cleric["channel_divinity"]["enabled"])
        self.assertEqual(cleric["channel_divinity"]["max_uses"], 3)
        self.assertEqual(cleric["channel_divinity"]["remaining_uses"], 3)
        self.assertTrue(cleric["divine_spark"]["enabled"])
        self.assertEqual(cleric["divine_spark"]["healing_dice"], "2d8")
        self.assertEqual(cleric["divine_spark"]["range_feet"], 30)
        self.assertTrue(cleric["turn_undead"]["enabled"])
        self.assertEqual(cleric["turn_undead"]["range_feet"], 30)
        self.assertTrue(cleric["sear_undead"]["enabled"])
        self.assertEqual(cleric["sear_undead"]["damage_dice_count"], 4)
        self.assertTrue(cleric["divine_intervention"]["enabled"])
        self.assertEqual(cleric["divine_intervention"]["max_spell_level"], 5)
        self.assertEqual(cleric["divine_intervention"]["recovery"], "long_rest")
        self.assertTrue(cleric["blessed_strikes"]["enabled"])
        self.assertFalse(cleric["improved_blessed_strikes"]["enabled"])

    def test_ensure_druid_runtime_derives_core_progression_from_level(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"druid": {"level": 18}}

        druid = helpers.ensure_druid_runtime(entity)

        self.assertEqual(druid["spell_preparation_mode"], "long_rest_any")
        self.assertEqual(druid["cantrips_known"], 4)
        self.assertEqual(druid["prepared_spells_count"], 20)
        self.assertEqual(druid["always_prepared_spells"], ["speak_with_animals"])
        self.assertTrue(druid["druidic"]["enabled"])
        self.assertTrue(druid["wild_shape"]["enabled"])
        self.assertEqual(druid["wild_shape"]["max_uses"], 4)
        self.assertEqual(druid["wild_shape"]["remaining_uses"], 4)
        self.assertEqual(druid["wild_shape"]["known_forms"], 8)
        self.assertEqual(druid["wild_shape"]["max_cr"], "1")
        self.assertTrue(druid["wild_shape"]["fly_speed_allowed"])
        self.assertEqual(druid["wild_shape"]["temp_hp_formula"], "druid_level")
        self.assertTrue(druid["wild_companion"]["enabled"])
        self.assertTrue(druid["wild_resurgence"]["enabled"])
        self.assertTrue(druid["beast_spells"]["enabled"])
        self.assertFalse(druid["archdruid"]["enabled"])

    def test_ensure_druid_runtime_enables_archdruid_at_level_twenty(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"druid": {"level": 20}}

        druid = helpers.ensure_druid_runtime(entity)

        self.assertTrue(druid["archdruid"]["enabled"])
        self.assertTrue(druid["archdruid"]["evergreen_wild_shape"])
        self.assertFalse(druid["archdruid"]["nature_magician_used"])

    def test_ensure_cleric_runtime_upgrades_blessed_strikes_at_level_fourteen(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"cleric": {"level": 14}}

        cleric = helpers.ensure_cleric_runtime(entity)

        self.assertTrue(cleric["blessed_strikes"]["enabled"])
        self.assertTrue(cleric["improved_blessed_strikes"]["enabled"])

    def test_ensure_druid_runtime_preserves_existing_wild_shape_remaining_uses(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"druid": {"level": 6, "wild_shape": {"remaining_uses": 1}}}

        druid = helpers.ensure_druid_runtime(entity)

        self.assertEqual(druid["wild_shape"]["max_uses"], 3)
        self.assertEqual(druid["wild_shape"]["remaining_uses"], 1)

    def test_ensure_paladin_runtime_derives_spellcasting_progression_and_always_prepared(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"paladin": {"level": 5}}

        paladin = helpers.ensure_paladin_runtime(entity)

        self.assertEqual(paladin["spell_preparation_mode"], "long_rest_one")
        self.assertEqual(paladin["prepared_spells_count"], 6)
        self.assertEqual(paladin["always_prepared_spells"], ["divine_smite", "find_steed"])

    def test_ensure_ranger_runtime_derives_spellcasting_progression_and_always_prepared(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.class_features = {"ranger": {"level": 9}}

        ranger = helpers.ensure_ranger_runtime(entity)

        self.assertEqual(ranger["spell_preparation_mode"], "long_rest_one")
        self.assertEqual(ranger["prepared_spells_count"], 9)
        self.assertEqual(ranger["always_prepared_spells"], ["hunters_mark"])

    def test_get_wizard_runtime_reads_existing_bucket_from_entity_class_features(self) -> None:
        helpers = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {"wizard": {"level": 4}}})()

        wizard = helpers.get_wizard_runtime(entity)

        self.assertEqual(wizard["level"], 4)
        self.assertEqual(wizard["cantrips_known"], 4)

    def test_get_cleric_runtime_reads_existing_bucket_from_entity_class_features(self) -> None:
        helpers = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {"cleric": {"level": 4}}})()

        cleric = helpers.get_cleric_runtime(entity)

        self.assertEqual(cleric["level"], 4)
        self.assertEqual(cleric["cantrips_known"], 4)

    def test_get_druid_runtime_reads_existing_bucket_from_entity_class_features(self) -> None:
        helpers = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {"druid": {"level": 4}}})()

        druid = helpers.get_druid_runtime(entity)

        self.assertEqual(druid["level"], 4)
        self.assertEqual(druid["cantrips_known"], 3)

    def test_get_sorcerer_runtime_reads_existing_bucket_from_entity_class_features(self) -> None:
        helpers = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {"sorcerer": {"level": 3, "sorcery_points": {"current": 2}}}})()

        sorcerer = helpers.get_sorcerer_runtime(entity)

        self.assertEqual(sorcerer["level"], 3)
        self.assertEqual(sorcerer["sorcery_points"]["current"], 2)

    def test_get_bard_runtime_preserves_existing_bardic_inspiration_and_expertise_state(self) -> None:
        helpers = _import_helpers()
        entity = build_entity()
        entity.ability_mods = {"cha": 3}
        entity.class_features = {
            "bard": {
                "level": 5,
                "bardic_inspiration": {"uses_current": 1},
                "expertise": {"skills": ["persuasion", "performance"]},
            }
        }

        bard = helpers.get_bard_runtime(entity)

        self.assertEqual(bard["bardic_inspiration"]["die"], "d8")
        self.assertEqual(bard["bardic_inspiration"]["uses_max"], 3)
        self.assertEqual(bard["bardic_inspiration"]["uses_current"], 1)
        self.assertEqual(bard["expertise"]["skills"], ["persuasion", "performance"])
        self.assertEqual(bard["expertise"]["max_skills"], 2)
        self.assertTrue(bard["font_of_inspiration"]["enabled"])

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
