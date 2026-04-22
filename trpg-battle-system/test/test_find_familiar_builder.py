from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import EncounterEntity
from tools.services.spells.summons.find_familiar_builder import build_find_familiar_entity


def build_warlock_caster() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_warlock_001",
        name="Warlock",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=14,
        proficiency_bonus=2,
        ability_scores={"str": 8, "dex": 14, "con": 12, "int": 10, "wis": 12, "cha": 16},
        ability_mods={"str": -1, "dex": 2, "con": 1, "int": 0, "wis": 1, "cha": 3},
    )


def test_build_find_familiar_entity_pseudodragon_has_expected_stats() -> None:
    caster = build_warlock_caster()

    familiar = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 4},
        familiar_form="pseudodragon",
        creature_type="fey",
        source_spell_instance_id="spell_find_familiar_001",
    )

    weapon_ids = {weapon["weapon_id"] for weapon in familiar.weapons}

    assert familiar.category == "summon"
    assert familiar.size == "tiny"
    assert familiar.ac == 14
    assert familiar.hp == {"current": 10, "max": 10, "temp": 0}
    assert familiar.speed["walk"] == 15
    assert familiar.speed["fly"] == 60
    assert familiar.source_ref["familiar_form_id"] == "pseudodragon"
    assert familiar.source_ref["special_senses"]["blindsight"] == 10
    assert familiar.source_ref["special_senses"]["darkvision"] == 60
    assert "bite" in weapon_ids
    assert "sting" in weapon_ids
    multiattack = next(
        action for action in familiar.source_ref["actions_metadata"] if action["action_id"] == "multiattack"
    )
    assert multiattack["multiattack_sequences"] == [
        {
            "sequence_id": "double_bite",
            "mode": "melee",
            "steps": [
                {"type": "weapon", "weapon_id": "bite"},
                {"type": "weapon", "weapon_id": "bite"},
            ],
        }
    ]


def test_build_find_familiar_entity_owl_has_expected_stats() -> None:
    caster = build_warlock_caster()

    familiar = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 4},
        familiar_form="owl",
        creature_type="fey",
        source_spell_instance_id="spell_find_familiar_001",
    )

    weapon_ids = {weapon["weapon_id"] for weapon in familiar.weapons}
    trait_ids = {trait["trait_id"] for trait in familiar.source_ref["traits_metadata"]}

    assert familiar.name == "Owl"
    assert familiar.size == "tiny"
    assert familiar.ac == 11
    assert familiar.hp == {"current": 1, "max": 1, "temp": 0}
    assert familiar.speed["walk"] == 5
    assert familiar.speed["fly"] == 60
    assert familiar.source_ref["creature_type"] == "fey"
    assert familiar.source_ref["special_senses"]["darkvision"] == 120
    assert "flyby" in trait_ids
    assert weapon_ids == {"talons"}


def test_build_find_familiar_entity_sprite_exposes_llm_action_metadata() -> None:
    caster = build_warlock_caster()

    familiar = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 4},
        familiar_form="sprite",
        creature_type="fey",
        source_spell_instance_id="spell_find_familiar_001",
    )

    weapon_ids = {weapon["weapon_id"] for weapon in familiar.weapons}
    action_ids = {action["action_id"] for action in familiar.source_ref["actions_metadata"]}

    assert familiar.speed["fly"] == 40
    assert "needle_sword" in weapon_ids
    assert "enchanting_bow" in weapon_ids
    assert {"heart_sight", "invisibility"}.issubset(action_ids)


def test_build_find_familiar_entity_imp_tracks_magical_darkvision_and_actions() -> None:
    caster = build_warlock_caster()

    familiar = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 4},
        familiar_form="imp",
        creature_type="fiend",
        source_spell_instance_id="spell_find_familiar_001",
    )

    action_ids = {action["action_id"] for action in familiar.source_ref["actions_metadata"]}

    assert familiar.source_ref["special_senses"]["darkvision"] == 120
    assert familiar.source_ref["special_senses"]["sees_magical_darkness"] is True
    assert {"invisibility", "shape_shift"}.issubset(action_ids)


def test_build_find_familiar_entity_quasit_tracks_special_actions() -> None:
    caster = build_warlock_caster()

    familiar = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 4},
        familiar_form="quasit",
        creature_type="fiend",
        source_spell_instance_id="spell_find_familiar_001",
    )

    action_ids = {action["action_id"] for action in familiar.source_ref["actions_metadata"]}

    assert {"scare", "invisibility", "shape_shift"}.issubset(action_ids)


def test_build_find_familiar_entity_sphinx_of_wonder_tracks_reaction_metadata() -> None:
    caster = build_warlock_caster()

    familiar = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 4},
        familiar_form="sphinx_of_wonder",
        creature_type="celestial",
        source_spell_instance_id="spell_find_familiar_001",
    )

    reaction_ids = {reaction["reaction_id"] for reaction in familiar.source_ref["reactions_metadata"]}

    assert familiar.resistances == ["necrotic", "psychic", "radiant"]
    assert "burst_of_ingenuity" in reaction_ids


def test_build_find_familiar_entity_skeleton_and_zombie_track_undead_rules() -> None:
    caster = build_warlock_caster()

    skeleton = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 4},
        familiar_form="skeleton",
        creature_type="fiend",
        source_spell_instance_id="spell_find_familiar_001",
    )
    zombie = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 5},
        familiar_form="zombie",
        creature_type="fiend",
        source_spell_instance_id="spell_find_familiar_001",
    )

    skeleton_weapon_ids = {weapon["weapon_id"] for weapon in skeleton.weapons}
    zombie_trait_ids = {trait["trait_id"] for trait in zombie.source_ref["traits_metadata"]}

    assert skeleton.vulnerabilities == ["bludgeoning"]
    assert skeleton.immunities == ["poison"]
    assert {"shortsword", "shortbow"} == skeleton_weapon_ids
    assert zombie.immunities == ["poison"]
    assert "undead_fortitude" in zombie_trait_ids


def test_build_find_familiar_entity_slaad_tadpole_has_magic_resistance_and_burrow() -> None:
    caster = build_warlock_caster()

    familiar = build_find_familiar_entity(
        caster=caster,
        summon_position={"x": 4, "y": 4},
        familiar_form="slaad_tadpole",
        creature_type="fiend",
        source_spell_instance_id="spell_find_familiar_001",
    )

    trait_ids = {trait["trait_id"] for trait in familiar.source_ref["traits_metadata"]}
    weapon_ids = {weapon["weapon_id"] for weapon in familiar.weapons}

    assert familiar.speed["burrow"] == 10
    assert "magic_resistance" in trait_ids
    assert weapon_ids == {"bite"}


def test_build_find_familiar_entity_rejects_unknown_form() -> None:
    caster = build_warlock_caster()

    with pytest.raises(ValueError, match="invalid_find_familiar_form"):
        build_find_familiar_entity(
            caster=caster,
            summon_position={"x": 4, "y": 4},
            familiar_form="owlbear_cub",
            creature_type="fey",
            source_spell_instance_id="spell_find_familiar_001",
        )
