from __future__ import annotations

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository
from tools.services.spells.summons.create_summoned_entity import create_summoned_entity_by_initiative
import tempfile
from pathlib import Path


def build_owner() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_owner_001",
        name="Kael",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 30, "max": 30, "temp": 0},
        ac=15,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
    )


def build_enemy() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_001",
        name="Goblin",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 8, "y": 2},
        hp={"current": 10, "max": 10, "temp": 0},
        ac=13,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_player_summon() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_summon_001",
        name="Sphinx of Wonder",
        side="ally",
        category="summon",
        controller="player",
        position={"x": 3, "y": 2},
        hp={"current": 24, "max": 24, "temp": 0},
        ac=13,
        speed={"walk": 20, "remaining": 20, "fly": 40},
        initiative=14,
        source_ref={
            "summoner_entity_id": "ent_owner_001",
            "source_spell_id": "find_familiar",
            "summon_template": "find_familiar",
        },
    )


def build_encounter() -> Encounter:
    owner = build_owner()
    enemy = build_enemy()
    return Encounter(
        encounter_id="enc_shared_turn_test",
        name="Shared Turn Test",
        status="active",
        round=1,
        current_entity_id=owner.entity_id,
        turn_order=[owner.entity_id, enemy.entity_id],
        entities={owner.entity_id: owner, enemy.entity_id: enemy},
        map=EncounterMap(
            map_id="map_shared_turn_test",
            name="Shared Turn Test Map",
            description="Shared turn fixture.",
            width=10,
            height=10,
        ),
    )


def test_player_controlled_summon_with_summoner_id_does_not_insert_into_turn_order() -> None:
    encounter = build_encounter()
    summon = build_player_summon()

    result = create_summoned_entity_by_initiative(encounter=encounter, summon=summon)

    assert summon.entity_id in encounter.entities
    assert summon.entity_id not in encounter.turn_order
    assert result["shared_turn_owner_id"] == "ent_owner_001"


def test_repository_get_normalizes_legacy_shared_summon_turn_order() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        encounter = build_encounter()
        summon = build_player_summon()
        encounter.entities[summon.entity_id] = summon
        encounter.turn_order = ["ent_owner_001", "ent_summon_001", "ent_enemy_001"]
        repo.save(encounter)

        normalized = repo.get("enc_shared_turn_test")

        assert normalized is not None
        assert normalized.turn_order == ["ent_owner_001", "ent_enemy_001"]
        assert normalized.current_entity_id == "ent_owner_001"

        repo.close()
