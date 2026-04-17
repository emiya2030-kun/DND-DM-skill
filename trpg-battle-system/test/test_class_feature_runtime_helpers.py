"""class feature 运行时共享 helper 测试。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _import_helpers():
    from tools.services.class_features.shared import (
        add_or_refresh_studied_attack_mark,
        ensure_fighter_runtime,
        get_fighter_runtime,
        resolve_extra_attack_count,
        resolve_entity_proficiencies,
    )

    return (
        add_or_refresh_studied_attack_mark,
        ensure_fighter_runtime,
        get_fighter_runtime,
        resolve_extra_attack_count,
        resolve_entity_proficiencies,
    )


def build_entity() -> object:
    return type("FakeEntity", (), {"class_features": {}})()


class ClassFeatureRuntimeHelpersTests(unittest.TestCase):
    def test_import_shared_helpers_via_package_path(self) -> None:
        _, _, _, resolve_extra_attack_count, _ = _import_helpers()
        self.assertEqual(resolve_extra_attack_count({"fighter": {}}), 1)

    def test_import_shared_helpers_then_top_level_service_export(self) -> None:
        _import_helpers()
        from tools.services import AppendEvent

        self.assertEqual(AppendEvent.__name__, "AppendEvent")

    def test_resolve_extra_attack_count_takes_highest_source_only(self) -> None:
        _, _, _, resolve_extra_attack_count, _ = _import_helpers()
        fighter_state = {
            "fighter": {
                "extra_attack_count": 2,
                "extra_attack_sources": [
                    {"source": "fighter", "attack_count": 2},
                    {"source": "other_class", "attack_count": 2},
                ],
            }
        }
        self.assertEqual(resolve_extra_attack_count(fighter_state), 2)

    def test_resolve_extra_attack_count_falls_back_to_one(self) -> None:
        _, _, _, resolve_extra_attack_count, _ = _import_helpers()
        self.assertEqual(resolve_extra_attack_count({}), 1)

    def test_add_studied_attack_mark_appends_target_once(self) -> None:
        add_or_refresh_studied_attack_mark, _, _, _, _ = _import_helpers()
        state = {"fighter": {"studied_attacks": []}}
        add_or_refresh_studied_attack_mark(state, "ent_enemy_001")
        self.assertEqual(state["fighter"]["studied_attacks"][0]["target_entity_id"], "ent_enemy_001")

    def test_add_studied_attack_mark_refreshes_existing_without_appending_duplicate(self) -> None:
        add_or_refresh_studied_attack_mark, _, _, _, _ = _import_helpers()
        state = {"fighter": {"studied_attacks": []}}
        add_or_refresh_studied_attack_mark(state, "ent_enemy_001")
        add_or_refresh_studied_attack_mark(state, "ent_enemy_001")
        self.assertEqual(len(state["fighter"]["studied_attacks"]), 1)
        self.assertEqual(state["fighter"]["studied_attacks"][0]["expires_at"], "end_of_next_turn")
        self.assertFalse(state["fighter"]["studied_attacks"][0]["consumed"])

    def test_ensure_fighter_runtime_writes_under_entity_class_features_for_object_entity(self) -> None:
        _, ensure_fighter_runtime, _, _, _ = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {}})()
        fighter = ensure_fighter_runtime(entity)
        fighter["extra_attack_count"] = 2
        self.assertEqual(entity.class_features["fighter"]["extra_attack_count"], 2)

    def test_ensure_fighter_runtime_writes_under_entity_class_features_for_dict_entity(self) -> None:
        _, ensure_fighter_runtime, _, _, _ = _import_helpers()
        entity = {}
        fighter = ensure_fighter_runtime(entity)
        fighter["extra_attack_count"] = 2
        self.assertEqual(entity["class_features"]["fighter"]["extra_attack_count"], 2)

    def test_get_fighter_runtime_reads_existing_fighter_bucket_from_entity_class_features(self) -> None:
        _, _, get_fighter_runtime, _, _ = _import_helpers()
        entity = type("FakeEntity", (), {"class_features": {"fighter": {"extra_attack_count": 2}}})()
        self.assertEqual(get_fighter_runtime(entity)["extra_attack_count"], 2)

    def test_get_fighter_runtime_ignores_bare_dict_root_fighter_key(self) -> None:
        _, _, get_fighter_runtime, _, _ = _import_helpers()
        entity = {"fighter": {"extra_attack_count": 2}}
        self.assertEqual(get_fighter_runtime(entity), {})

    def test_resolve_entity_proficiencies_returns_fighter_defaults(self) -> None:
        _, _, _, _, resolve_entity_proficiencies = _import_helpers()
        entity = build_entity()
        entity.class_features = {"fighter": {"level": 1}}

        proficiencies = resolve_entity_proficiencies(entity)

        self.assertEqual(proficiencies["weapon_proficiencies"], ["simple", "martial"])
        self.assertEqual(proficiencies["armor_training"], ["light", "medium", "heavy", "shield"])

    def test_resolve_entity_proficiencies_merges_explicit_lists(self) -> None:
        _, _, _, _, resolve_entity_proficiencies = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "fighter": {
                "level": 1,
                "weapon_proficiencies": ["simple", "martial", "improvised"],
                "armor_training": ["light", "medium", "heavy", "shield", "tower"],
            }
        }

        proficiencies = resolve_entity_proficiencies(entity)

        self.assertEqual(proficiencies["weapon_proficiencies"], ["simple", "martial", "improvised"])
        self.assertEqual(proficiencies["armor_training"], ["light", "medium", "heavy", "shield", "tower"])

    def test_resolve_entity_proficiencies_normalizes_mixed_case_armor_training(self) -> None:
        _, _, _, _, resolve_entity_proficiencies = _import_helpers()
        entity = build_entity()
        entity.class_features = {
            "fighter": {
                "level": 1,
                "armor_training": ["HEAVY", "Shield", "Tower"],
            }
        }

        proficiencies = resolve_entity_proficiencies(entity)

        self.assertEqual(
            proficiencies["armor_training"],
            ["light", "medium", "heavy", "shield", "tower"],
        )


if __name__ == "__main__":
    unittest.main()
