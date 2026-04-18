from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.class_features.paladin import UseAbjureFoes


def build_paladin(
    *,
    entity_id: str = "ent_paladin_001",
    side: str = "ally",
    x: int = 2,
    y: int = 2,
    level: int = 10,
    cha_mod: int = 3,
) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=entity_id,
        side=side,
        category="pc",
        controller="player",
        position={"x": x, "y": y},
        hp={"current": 32, "max": 32, "temp": 0},
        ac=18,
        speed={"walk": 30, "remaining": 30},
        initiative=16,
        proficiency_bonus=4,
        ability_scores={"str": 16, "dex": 10, "con": 14, "int": 10, "wis": 12, "cha": 16},
        ability_mods={"str": 3, "dex": 0, "con": 2, "int": 0, "wis": 1, "cha": cha_mod},
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
        class_features={
            "paladin": {
                "level": level,
                "channel_divinity": {"remaining_uses": 2},
            }
        },
    )


def build_enemy(*, entity_id: str, x: int, y: int, wis_mod: int = 0) -> EncounterEntity:
    return EncounterEntity(
        entity_id=entity_id,
        name=entity_id,
        side="enemy",
        category="monster",
        controller="dm",
        position={"x": x, "y": y},
        hp={"current": 20, "max": 20, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
        ability_scores={"str": 10, "dex": 10, "con": 10, "int": 8, "wis": 10, "cha": 8},
        ability_mods={"str": 0, "dex": 0, "con": 0, "int": -1, "wis": wis_mod, "cha": -1},
        action_economy={"action_used": False, "bonus_action_used": False, "reaction_used": False},
        turn_effects=[],
    )


def build_encounter(*, cha_mod: int = 3) -> Encounter:
    paladin = build_paladin(cha_mod=cha_mod)
    enemy_a = build_enemy(entity_id="ent_enemy_a_001", x=6, y=2)
    enemy_b = build_enemy(entity_id="ent_enemy_b_001", x=7, y=2)
    return Encounter(
        encounter_id="enc_abjure_test",
        name="Abjure Test",
        status="active",
        round=1,
        current_entity_id=paladin.entity_id,
        turn_order=[paladin.entity_id, enemy_a.entity_id, enemy_b.entity_id],
        entities={
            paladin.entity_id: paladin,
            enemy_a.entity_id: enemy_a,
            enemy_b.entity_id: enemy_b,
        },
        map=EncounterMap(
            map_id="map_abjure_test",
            name="Abjure Map",
            description="A simple arena.",
            width=12,
            height=12,
        ),
    )


def test_execute_spends_action_and_channel_divinity_and_applies_effects() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter())

        result = UseAbjureFoes(repo).execute(
            encounter_id="enc_abjure_test",
            actor_id="ent_paladin_001",
            target_ids=["ent_enemy_a_001"],
            save_rolls={"ent_enemy_a_001": 5},
        )

        updated = repo.get("enc_abjure_test")
        assert updated is not None
        actor = updated.entities["ent_paladin_001"]
        enemy = updated.entities["ent_enemy_a_001"]
        assert result["channel_divinity_remaining"] == 1
        assert result["action_consumed"] is True
        assert actor.action_economy["action_used"] is True
        assert f"frightened:{actor.entity_id}" in enemy.conditions
        assert any(effect["effect_type"] == "abjure_foes_restriction" for effect in enemy.turn_effects)

        repo.close()


def test_execute_rejects_when_target_count_exceeds_charisma_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter(cha_mod=1))

        with pytest.raises(ValueError, match="too_many_targets"):
            UseAbjureFoes(repo).execute(
                encounter_id="enc_abjure_test",
                actor_id="ent_paladin_001",
                target_ids=["ent_enemy_a_001", "ent_enemy_b_001"],
                save_rolls={"ent_enemy_a_001": 4, "ent_enemy_b_001": 4},
            )

        repo.close()


def test_execute_successful_save_leaves_target_unchanged() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        repo.save(build_encounter())

        result = UseAbjureFoes(repo).execute(
            encounter_id="enc_abjure_test",
            actor_id="ent_paladin_001",
            target_ids=["ent_enemy_a_001"],
            save_rolls={"ent_enemy_a_001": 19},
        )

        updated = repo.get("enc_abjure_test")
        assert updated is not None
        enemy = updated.entities["ent_enemy_a_001"]
        assert result["targets"][0]["outcome"] == "saved"
        assert enemy.conditions == []
        assert enemy.turn_effects == []

        repo.close()


def test_abjure_foes_does_not_apply_inside_enemy_aura_of_courage() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        actor = build_paladin()
        enemy_paladin = build_paladin(
            entity_id="ent_enemy_paladin_001",
            side="enemy",
            x=6,
            y=2,
            level=10,
            cha_mod=2,
        )
        covered_target = build_enemy(entity_id="ent_enemy_a_001", x=7, y=2)
        other_enemy = build_enemy(entity_id="ent_enemy_b_001", x=11, y=2)
        encounter = Encounter(
            encounter_id="enc_abjure_test",
            name="Abjure Test",
            status="active",
            round=1,
            current_entity_id=actor.entity_id,
            turn_order=[actor.entity_id, enemy_paladin.entity_id, covered_target.entity_id, other_enemy.entity_id],
            entities={
                actor.entity_id: actor,
                enemy_paladin.entity_id: enemy_paladin,
                covered_target.entity_id: covered_target,
                other_enemy.entity_id: other_enemy,
            },
            map=EncounterMap(
                map_id="map_abjure_test",
                name="Abjure Map",
                description="A simple arena.",
                width=12,
                height=12,
            ),
        )
        repo.save(encounter)

        result = UseAbjureFoes(repo).execute(
            encounter_id="enc_abjure_test",
            actor_id=actor.entity_id,
            target_ids=[covered_target.entity_id],
            save_rolls={covered_target.entity_id: 3},
        )

        updated = repo.get("enc_abjure_test")
        assert updated is not None
        updated_target = updated.entities[covered_target.entity_id]
        assert result["targets"][0]["outcome"] == "suppressed_by_aura_of_courage"
        assert updated_target.conditions == []
        assert updated_target.turn_effects == []

        repo.close()
