from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.models import Encounter, EncounterEntity, EncounterMap
from tools.repositories import EncounterRepository, EventRepository
from tools.services import AppendEvent, EncounterCastSpell
from tools.services.spells.summons.create_summoned_entity import create_summoned_entity
from tools.services.spells.summons.find_steed_builder import build_find_steed_entity


def build_paladin_caster() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_paladin_001",
        name="Paladin",
        side="ally",
        category="pc",
        controller="player",
        position={"x": 2, "y": 2},
        hp={"current": 30, "max": 30, "temp": 0},
        ac=18,
        speed={"walk": 30, "remaining": 30},
        initiative=15,
        proficiency_bonus=3,
        ability_scores={"str": 16, "dex": 10, "con": 14, "int": 10, "wis": 12, "cha": 16},
        ability_mods={"str": 3, "dex": 0, "con": 2, "int": 0, "wis": 1, "cha": 3},
    )


def build_enemy() -> EncounterEntity:
    return EncounterEntity(
        entity_id="ent_enemy_001",
        name="Enemy",
        side="enemy",
        category="monster",
        controller="gm",
        position={"x": 8, "y": 8},
        hp={"current": 18, "max": 18, "temp": 0},
        ac=14,
        speed={"walk": 30, "remaining": 30},
        initiative=10,
    )


def build_find_steed_encounter() -> Encounter:
    caster = build_paladin_caster()
    enemy = build_enemy()
    return Encounter(
        encounter_id="enc_find_steed_test",
        name="Find Steed Test",
        status="active",
        round=1,
        current_entity_id=caster.entity_id,
        turn_order=[caster.entity_id, enemy.entity_id],
        entities={caster.entity_id: caster, enemy.entity_id: enemy},
        map=EncounterMap(
            map_id="map_find_steed_test",
            name="Find Steed Map",
            description="A simple arena.",
            width=12,
            height=12,
        ),
    )


def test_build_find_steed_entity_uses_level_two_stats() -> None:
    caster = build_paladin_caster()

    summon = build_find_steed_entity(
        caster=caster,
        cast_level=2,
        summon_position={"x": 5, "y": 5},
        steed_type="celestial",
        appearance="warhorse",
        source_spell_instance_id="spell_find_steed_001",
    )

    assert summon.category == "summon"
    assert summon.size == "large"
    assert summon.ac == 12
    assert summon.hp == {"current": 25, "max": 25, "temp": 0}
    assert summon.speed["walk"] == 60
    assert "fly" not in summon.speed
    assert summon.source_ref["steed_type"] == "celestial"


def test_build_find_steed_entity_adds_flight_at_cast_level_four() -> None:
    caster = build_paladin_caster()

    summon = build_find_steed_entity(
        caster=caster,
        cast_level=4,
        summon_position={"x": 5, "y": 5},
        steed_type="fey",
        appearance="elk",
        source_spell_instance_id="spell_find_steed_001",
    )

    assert summon.speed["fly"] == 60
    assert summon.weapons[0]["damage"]["damage_type"] == "psychic"


def test_create_summoned_entity_inserts_entity_after_caster_in_turn_order() -> None:
    encounter = build_find_steed_encounter()
    caster = encounter.entities["ent_paladin_001"]
    summon = build_find_steed_entity(
        caster=caster,
        cast_level=2,
        summon_position={"x": 5, "y": 5},
        steed_type="fiend",
        appearance="wolf",
        source_spell_instance_id="spell_find_steed_001",
    )

    result = create_summoned_entity(
        encounter=encounter,
        summon=summon,
        insert_after_entity_id="ent_paladin_001",
    )

    assert encounter.turn_order == ["ent_paladin_001", "ent_enemy_001"]
    assert encounter.entities[summon.entity_id].initiative == encounter.entities["ent_paladin_001"].initiative
    assert result["shared_turn_owner_id"] == "ent_paladin_001"


def test_execute_find_steed_replaces_previous_steed_from_same_caster() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter = build_find_steed_encounter()
        caster = encounter.entities["ent_paladin_001"]
        caster.resources["spell_slots"] = {"2": {"max": 2, "remaining": 2}}
        caster.class_features["paladin"] = {"level": 5, "faithful_steed": {"free_cast_available": False}}
        caster.spells = [
            {
                "spell_id": "find_steed",
                "name": "Find Steed",
                "level": 2,
                "base": {"level": 2, "casting_time": "1 action", "concentration": False},
            }
        ]
        encounter_repo.save(encounter)

        service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
        service.execute(
            encounter_id="enc_find_steed_test",
            spell_id="find_steed",
            cast_level=2,
            target_point={"x": 5, "y": 5, "anchor": "cell_center"},
        )
        first_updated = encounter_repo.get("enc_find_steed_test")
        assert first_updated is not None
        first_summon_id = first_updated.spell_instances[0]["special_runtime"]["summon_entity_ids"][0]

        service.execute(
            encounter_id="enc_find_steed_test",
            spell_id="find_steed",
            cast_level=2,
            target_point={"x": 6, "y": 6, "anchor": "cell_center"},
        )

        updated = encounter_repo.get("enc_find_steed_test")
        assert updated is not None
        active_summon_ids = [entity_id for entity_id, entity in updated.entities.items() if entity.category == "summon"]
        assert len(active_summon_ids) == 1
        assert first_summon_id not in active_summon_ids

        encounter_repo.close()
        event_repo.close()


def test_execute_find_steed_projects_summon_into_turn_order_with_shared_initiative() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        encounter_repo = EncounterRepository(Path(tmp_dir) / "encounters.json")
        event_repo = EventRepository(Path(tmp_dir) / "events.json")
        encounter = build_find_steed_encounter()
        caster = encounter.entities["ent_paladin_001"]
        caster.resources["spell_slots"] = {"2": {"max": 2, "remaining": 2}}
        caster.class_features["paladin"] = {"level": 5, "faithful_steed": {"free_cast_available": False}}
        caster.spells = [
            {
                "spell_id": "find_steed",
                "name": "Find Steed",
                "level": 2,
                "base": {"level": 2, "casting_time": "1 action", "concentration": False},
            }
        ]
        encounter_repo.save(encounter)

        service = EncounterCastSpell(encounter_repo, AppendEvent(event_repo))
        result = service.execute(
            encounter_id="enc_find_steed_test",
            spell_id="find_steed",
            cast_level=2,
            target_point={"x": 5, "y": 5, "anchor": "cell_center"},
            include_encounter_state=True,
        )

        turn_order = result["encounter_state"]["turn_order"]
        assert [item["name"] for item in turn_order] == ["Paladin", "Enemy"]
        assert turn_order[0]["initiative"] == 15
        assert turn_order[1]["initiative"] == 10

        encounter_repo.close()
        event_repo.close()
